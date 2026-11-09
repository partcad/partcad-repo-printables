#
# partcad-repo-printables, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""Tests of the Printables plugin, with Printables answered from a table.

The models below have the shape api.printables.com answers 'print(id:)' with -
the fields this asks for - with values made up; the API itself is a stand-in
that answers the way the real one was seen to: GraphQL errors in a 200, a
paid model's files refused to nobody, and a 401 in plain text for any request
carrying a token it does not take. Nothing here touches the network.
"""

import base64
import importlib.util
import json
import os
import re
import runpy
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN = os.path.join(_HERE, "printables_repo.py")
_SPEC = importlib.util.spec_from_file_location("printables_repo_under_test", _PLUGIN)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)
rm = plugin.rm

API = plugin.API
FILES = "https://files.printables.com/media/prints/"


def _jwt(claims):
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return "%s.%s.c2ln" % (part({"alg": "RS256", "typ": "JWT"}), part(claims))


GOOD = _jwt({"sub": "1", "exp": 1893456000})  # 2030-01-01 00:00 UTC
STALE = _jwt({"sub": "1", "exp": 1})


def _file(file_id, name, folder=""):
    return {"id": str(file_id), "name": name, "folder": folder, "fileSize": 1000}


CLIP = {
    "id": "271731",
    "name": "Cable clip",
    "slug": "cable-clip",
    "price": None,
    "premium": False,
    "user": {"handle": "ann_1", "publicUsername": "Ann"},
    "license": {
        "name": "Creative Commons — Attribution  — Noncommercial",
        "abbreviation": "CC-BY-NC",
        "content": '<a rel="license" href="http://creativecommons.org/licenses/by-nc/4.0/">CC</a>',
    },
    "stls": [_file(5, "clip.stl"), _file(6, "clip.step"), _file(7, "clip.f3d"), _file(8, "base.stl", "Extras")],
    # Numbered apart from the model files: the same 5 as 'clip.stl'.
    "otherFiles": [_file(5, "drawing.scad"), _file(9, "notes.pdf")],
    "gcodes": [_file(5, "clip_mk4.bgcode", "MK4 G-codes")],
    "slas": [],
}

DRAGON = {
    "id": "525789",
    "name": "Articulated Dragon",
    "slug": "articulated-dragon",
    "price": "5.00",
    "premium": True,
    "user": {"handle": "maker", "publicUsername": "Maker"},
    "license": {"name": "Standard Digital File License", "abbreviation": "Standard Digital File", "content": ""},
    "stls": [_file(20, "dragon.3mf", "Dragon_v2"), _file(21, "dragon.stl", "Dragon_v2_Straight")],
    "otherFiles": [],
    "gcodes": [],
    "slas": [],
}


class Api:
    """api.printables.com and files.printables.com, answering from what is in it."""

    def __init__(self):
        self.models = {"271731": CLIP, "525789": DRAGON}
        self.search = []
        self.files = {}
        self.tokens = {GOOD}
        self.asked = []

    def __call__(self, url, headers=None, data=None, method=None, timeout=60):
        auth = dict(headers or {}).get("Authorization")
        if url != API:
            self.asked.append((url, None, auth))
            if url in self.files:
                return rm.Response(200, {}, self.files[url], url)
            return rm.Response(404, {}, b"Not Found", url)
        self.asked.append((data["operationName"], data.get("variables"), auth))
        if auth is not None and auth[len("Bearer ") :] not in self.tokens:
            return rm.Response(401, {"Content-Type": "text/plain"}, b"Token is invalid", url)
        answer = getattr(self, data["operationName"])(data["variables"], auth)
        if isinstance(answer, rm.Response):
            return answer
        return rm.Response(200, {}, json.dumps(answer).encode(), url)

    def PrintablesModel(self, variables, auth):
        return {"data": {"print": self.models.get(variables["id"])}}

    def PrintablesSearch(self, variables, auth):
        return {"data": {"searchPrints2": {"items": self.search[: variables["limit"]]}}}

    def PrintablesDownload(self, variables, auth):
        model = self.models[variables["printId"]]
        if (model["price"] or model["premium"]) and not auth:
            return {
                "data": {
                    "getDownloadLink": {
                        "ok": False,
                        "errors": [
                            {"field": "non_field_error", "messages": ["cannot_download_premium_file_as_anonymous_user"]}
                        ],
                        "output": None,
                    }
                }
            }
        link = "%s%s/%s/%s" % (FILES, model["id"], variables["fileType"], variables["id"])
        return {"data": {"getDownloadLink": {"ok": True, "errors": None, "output": {"link": link, "ttl": 86400}}}}

    def PrintablesMe(self, variables, auth):
        if not auth:
            return rm.Response(401, {"Content-Type": "text/plain"}, b"user_is_not_authenticated", API)
        return {"data": {"me": {"id": "1", "handle": "ann_1", "publicUsername": "Ann"}}}


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("PARTCAD_PRINTABLES_CACHE", str(tmp_path))
    monkeypatch.delenv("PRINTABLES_TOKEN", raising=False)

    def make(token=""):
        made = plugin.Printables({"parameters": {"token": token}})
        made.http.request = Api()
        return made

    return make


def _graphql_asked(made, operation):
    return [(variables, auth) for name, variables, auth in made.http.request.asked if name == operation]


# --- models and their files ------------------------------------------------------


def test_a_model_is_its_best_file(site):
    config = site().get("objects/part/271731")
    assert config["type"] == "step"
    assert config["desc"] == "Cable clip: clip.step"
    assert config["parameters"]["file"]["default"] == "6"
    assert config["url"] == "https://www.printables.com/model/271731-cable-clip"
    assert config["author"] == "Ann"


def test_a_creative_commons_licence_is_named_by_the_link_printables_gives_with_it():
    assert plugin._license(CLIP["license"]) == "CC BY-NC 4.0"
    zero = {"name": "Creative Commons — Public Domain", "content": "creativecommons.org/publicdomain/zero/1.0/"}
    assert plugin._license(zero) == "CC0 1.0"
    assert plugin._license(DRAGON["license"]) == "Standard Digital File License"


def test_a_file_is_named_by_its_number_or_by_its_name_after_its_folder(site):
    made = site()
    assert made.get("objects/part/271731;file=8")["path"].endswith("/Extras_base.stl")
    assert made.get("objects/part/271731;file=Extras/base.stl")["desc"] == "Cable clip: Extras/base.stl"
    assert made.get("objects/part/271731;format=stl")["path"].endswith("/clip.stl")


def test_a_file_of_another_list_is_named_with_the_list_so_the_same_number_is_not_two_files(site, capsys):
    made = site()
    assert made.get("objects/part/271731;file=5")["type"] == "stl"
    assert made.get("objects/part/271731;file=other-5")["type"] == "scad"
    assert rm.serve(made, "objects/part/271731;file=gcode-5") is None
    assert "'MK4 G-codes/clip_mk4.bgcode' of 271731 is not a file PartCAD reads" in capsys.readouterr().err


def test_a_model_that_is_not_there_is_not_found_and_nonsense_costs_no_request(site, capsys):
    made = site()
    assert rm.serve(made, "objects/part/42") is None
    assert "model 42: not found" in capsys.readouterr().err
    assert rm.serve(made, "objects/part/271731-cable-clip") is None
    assert "is not a Printables model id" in capsys.readouterr().err
    assert [name for name, *_ in made.http.request.asked] == ["PrintablesModel"]


def test_graphql_errors_are_said_rather_than_taken_for_an_answer(site, capsys):
    made = site()
    made.http.request.PrintablesModel = lambda variables, auth: {
        "errors": [{"message": "Cannot query field 'stls' on type 'PrintType'."}],
        "data": None,
    }
    assert rm.serve(made, "objects/part/271731") is None
    assert "model 271731: Cannot query field 'stls' on type 'PrintType'." in capsys.readouterr().err


# --- downloads -------------------------------------------------------------------


def test_a_free_models_file_is_downloaded_as_nobody_even_with_a_token(site):
    made = site(STALE)
    made.http.request.files[FILES + "271731/stl/6"] = b"ISO-10303-21;"
    config = made.get("objects/part/271731")
    assert base64.b64decode(made.get("files/" + config["path"])) == b"ISO-10303-21;"
    assert _graphql_asked(made, "PrintablesDownload") == [({"id": "6", "printId": "271731", "fileType": "stl"}, None)]
    assert (FILES + "271731/stl/6", None, None) in made.http.request.asked


def test_a_file_of_another_list_is_asked_for_as_that_list(site):
    made = site()
    made.http.request.files[FILES + "271731/other/5"] = b"cube();"
    config = made.get("objects/part/271731;file=other-5")
    assert base64.b64decode(made.get("files/" + config["path"])) == b"cube();"
    assert _graphql_asked(made, "PrintablesDownload")[0][0] == {"id": "5", "printId": "271731", "fileType": "other"}


def test_a_paid_models_file_says_it_needs_the_buyers_sign_in(site, capsys):
    made = site()
    config = made.get("objects/part/525789")
    assert config["type"] == "3mf" and config["desc"] == "Articulated Dragon: Dragon_v2/dragon.3mf"
    assert rm.serve(made, "files/" + config["path"]) is None
    err = capsys.readouterr().err
    assert "a paid model" in err and "pc login //pub/collection/printables:printables_repo" in err
    assert _graphql_asked(made, "PrintablesDownload") == []


def test_a_paid_models_file_is_downloaded_with_the_token_and_the_token_goes_nowhere_else(site):
    made = site(GOOD)
    made.http.request.files[FILES + "525789/stl/20"] = b"3mf"
    config = made.get("objects/part/525789")
    assert base64.b64decode(made.get("files/" + config["path"])) == b"3mf"
    assert _graphql_asked(made, "PrintablesDownload")[0][1] == "Bearer " + GOOD
    assert _graphql_asked(made, "PrintablesModel")[0][1] is None
    assert (FILES + "525789/stl/20", None, None) in made.http.request.asked


def test_a_token_printables_no_longer_takes_is_said_to_be_one(site, capsys):
    made = site(STALE)
    config = made.get("objects/part/525789")
    assert rm.serve(made, "files/" + config["path"]) is None
    err = capsys.readouterr().err
    assert "Printables did not take the token" in err and "short-lived" in err and "pc login" in err


def test_a_free_file_refused_to_nobody_is_asked_for_again_with_the_token(site):
    made = site(GOOD)
    api = made.http.request
    api.files[FILES + "271731/stl/6"] = b"step"
    refuse = api.PrintablesDownload

    def download(variables, auth):
        if not auth:
            return {"data": {"getDownloadLink": {"ok": False, "errors": [{"messages": ["anonymous_user"]}]}}}
        return refuse(variables, auth)

    api.PrintablesDownload = download
    config = made.get("objects/part/271731")
    assert base64.b64decode(made.get("files/" + config["path"])) == b"step"
    assert [auth for _, auth in _graphql_asked(made, "PrintablesDownload")] == [None, "Bearer " + GOOD]


def test_what_printables_says_of_a_refused_download_is_passed_on(site, capsys):
    made = site()
    made.http.request.PrintablesDownload = lambda variables, auth: {
        "data": {"getDownloadLink": {"ok": False, "errors": [{"messages": ["files_cannot_be_downloaded"]}]}}
    }
    config = made.get("objects/part/271731")
    assert rm.serve(made, "files/" + config["path"]) is None
    assert "was not handed over: files_cannot_be_downloaded" in capsys.readouterr().err


# --- search ----------------------------------------------------------------------


def test_a_search_names_a_part_per_file_from_one_request(site):
    made = site()
    made.http.request.search = [CLIP]
    hits = made.get("search/part?q=cable+clip&limit=5")
    # 'clip.stl' is 'clip.step' in another format; the f3d, the PDF and the
    # G-code are not parts.
    assert list(hits) == ["271731;file=6", "271731;file=8", "271731;file=other-5"]
    assert hits["271731;file=other-5"]["type"] == "scad"
    assert [name for name, *_ in made.http.request.asked] == ["PrintablesSearch"]
    ((variables, auth),) = _graphql_asked(made, "PrintablesSearch")
    assert variables == {"query": "cable clip", "limit": 15, "offset": 0} and auth is None


def test_a_search_asks_for_free_models_only():
    assert "paid: free" in plugin._SEARCH and "ordering: best_match" in plugin._SEARCH


# --- logging in --------------------------------------------------------------------


class BrowserNeeded(BaseException):
    pass


class Callback:
    """PartCAD's 'partcad_login', replaying: raises the first time, returns what the browser sent after."""

    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def open_browser(self, url, capture, title=None, guide=None, require="all", done_when=None, timeout=600):
        spec = {"url": url, "capture": capture, "title": title, "guide": guide, "done_when": done_when}
        self.calls.append(spec)
        if len(self.calls) > len(self.results):
            raise BrowserNeeded(spec)
        return self.results[len(self.calls) - 1]


def test_a_token_printables_takes_is_kept_without_a_browser(site):
    made = site(GOOD)
    callback = Callback()
    result = rm.login(made, callback)
    assert result["parameters"] == {"token": GOOD}
    assert result["message"] == "Already logged in to Printables as ann_1 (its token expires 2030-01-01 00:00 UTC)"
    assert callback.calls == []
    assert _graphql_asked(made, "PrintablesMe") == [({}, "Bearer " + GOOD)]


def test_a_stale_token_opens_printables_and_asks_for_its_cookie(site):
    callback = Callback()
    with pytest.raises(BrowserNeeded):
        rm.login(site(STALE), callback)
    (spec,) = callback.calls
    assert spec["url"] == "https://www.printables.com/" and spec["title"] == "Printables"
    assert spec["capture"] == [
        {
            "name": "token",
            "cookie": {"url": "https://www.printables.com/", "name": "auth.access_token"},
            "match": plugin._JWT,
        }
    ]
    assert spec["done_when"] == {"fetch": {"url": API + "?query=%7Bme%7Bid%7D%7D", "status": 200}}
    assert [step["url"] for step in spec["guide"]] == [
        "https://account.prusa3d.com/login*",
        "https://account.prusa3d.com/login*",
        "https://www.printables.com/*",
    ]


def test_only_a_jwt_counts_as_the_cookie_a_visitor_has_none_of():
    for visitor in ("", "false", "undefined", "null", "Bearer", "%22%22"):
        assert not re.search(plugin._JWT, visitor)
    assert re.search(plugin._JWT, GOOD)


def test_what_the_browser_captured_is_checked_and_becomes_the_token(site):
    made = site()
    result = rm.login(made, Callback([{"token": " %s " % GOOD}]))
    assert result["parameters"] == {"token": GOOD}
    assert result["message"].startswith("Logged in to Printables as ann_1")


def test_a_capture_printables_does_not_take_fails_the_login(site):
    with pytest.raises(RuntimeError, match="does not take what the login captured"):
        rm.login(site(), Callback([{"token": STALE}]))


def test_a_printables_that_cannot_be_asked_is_not_taken_for_a_refusal(site):
    made = site(GOOD)
    made.http.request.PrintablesMe = lambda variables, auth: rm.Response(503, {}, b"", API)
    with pytest.raises(rm.SiteError, match="answered HTTP 503"):
        made.whoami({"token": GOOD})


def test_a_token_that_says_no_expiry_is_named_without_one(site):
    token = _jwt({"sub": "1"})
    made = site()
    made.http.request.tokens.add(token)
    assert made.whoami({"token": token}) == "ann_1"


def test_the_expiry_is_read_off_the_token_for_the_user_only():
    assert plugin._expiry(GOOD) == time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(1893456000))
    assert plugin._expiry("not-a-jwt") is None
    assert plugin._expiry("a.!!!.c") is None


# --- what PartCAD runs ---------------------------------------------------------------


def test_partcad_runs_it_and_reads_the_answer_from_output():
    result = runpy.run_path(_PLUGIN, init_globals={"request": {"key": "meta", "parameters": {}}}, run_name="get")
    assert result["output"]["result"]["manufacturable"] is False
    assert result["output"]["result"]["searchKinds"] == ["part"]


def test_partcad_runs_its_login(monkeypatch):
    monkeypatch.delenv("PRINTABLES_TOKEN", raising=False)
    callback = Callback()
    with pytest.raises(BrowserNeeded):
        runpy.run_path(
            _PLUGIN,
            init_globals={"request": {"api": "login", "parameters": {"token": ""}}, "partcad_login": callback},
            run_name="login",
        )
    assert callback.calls[0]["url"] == "https://www.printables.com/"
