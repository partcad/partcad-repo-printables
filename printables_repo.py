#
# partcad-repo-printables, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""A PartCAD 'basic' repository plugin that serves Printables models as parts.

Published as ``//pub/universe/printables/models``. Nothing is listed: a part is
asked for by the model's number (the one in printables.com/model/<number>-<slug>),
and is one file of that model.

    3161                             the model's best file (see remote_models.FORMATS)
    3161;format=stl                  its best STL
    3161;file=49068                  one of its files, by its id on Printables
    525789;file=Dragon_v2/Dragon_v2.3mf   or by its name, after the folder it is in

Printables is asked through the GraphQL API its own website uses,
api.printables.com, which answers this plugin as it is - the website's pages
turn it away with a bot check. A model's details, its files and a search need
no sign-in, and nor does downloading a free model's files. A paid model's files
take the signed-in Printables (Prusa Account) user who bought it: 'pc login'
picks the token up from the user's browser (see 'Printables.login_spec'), or it
is given as PRINTABLES_TOKEN or as the repository's 'token' parameter.

PartCAD runs this script once per key (via runpy) with the key in
``request["key"]``, and with ``__name__ == "login"`` for 'pc login'; the answer
goes in ``output``. What the keys mean, and everything else that is the same for
every model site, is in remote_models.py.
"""

import base64
import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse

# When this plugin's answers stopped meaning what they meant before. PartCAD
# keys everything it caches of this package on it, so raise it with any change
# to what is answered - here or in remote_models.py.
#
# v1: models as parts, one per file of any of a model's file lists.
# v2: a part's 'source' parameter, and the plugin's 'formats' and 'source' preferences;
#     'login' says what to do with nobody at the screen.
CACHE_VERSION = 2


def _shared():
    """remote_models.py, beside this script, under a name of this plugin's own."""
    name = "_partcad_printables_remote_models"
    if name not in sys.modules:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote_models.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


rm = _shared()

WEB = "https://www.printables.com"
# With the slash: without it the API answers a redirect, which a POST does not follow.
API = "https://api.printables.com/graphql/"
LOGIN_COMMAND = "pc login //pub/universe/printables:printables_repo"

# A model's details are kept for a day; an answer that carried GraphQL errors
# is not kept at all (see '_graphql').
_MODEL_TTL = rm.DAY

# A model's files come in four lists, and the download mutation is told which
# one a file is in. Each list numbers its files on its own, so one number can be
# a model file and an "other file" of the same model: the model files proper -
# STL, 3MF, STEP, SCAD and the like - are named by their number alone, and a
# file of any other list by its number after the list's ('other-120058').
_LISTS = (
    ("stls", "stl", ""),
    ("otherFiles", "other", "other-"),
    ("gcodes", "gcode", "gcode-"),
    ("slas", "sla", "sla-"),
)

_FILE_FIELDS = "id name folder fileSize"
_MODEL_FIELDS = (
    "id name slug price premium user { handle publicUsername } license { name abbreviation content } "
    + " ".join("%s { %s }" % (field, _FILE_FIELDS) for field, _, _ in _LISTS)
)
_MODEL = "query PrintablesModel($id: ID!) { print(id: $id) { %s } }" % _MODEL_FIELDS
# The files come with the hits, so a search is one request rather than one per
# model. Free models only: a hit is a name to build, and a paid one builds only
# for whoever bought it (naming it still works, for them).
_SEARCH = (
    "query PrintablesSearch($query: String!, $limit: Int, $offset: Int) { searchPrints2(query: $query, "
    "printType: print, paid: free, ordering: best_match, limit: $limit, offset: $offset) { items { %s } } }"
    % _MODEL_FIELDS
)
_DOWNLOAD = (
    "mutation PrintablesDownload($id: ID!, $printId: ID!, $fileType: DownloadFileTypeEnum!) { "
    "getDownloadLink(id: $id, printId: $printId, fileType: $fileType, source: model_detail) "
    "{ ok errors { field messages } output { link ttl } } }"
)
_ME = "query PrintablesMe { me { id handle publicUsername } }"

# What the website keeps the user's token in: a Prusa Account access token, a
# JWT, which the API takes as 'Authorization: Bearer' - and reads from this
# cookie too, which is what lets the browser's own session be asked 'who am I'.
TOKEN_COOKIE = "auth.access_token"
_JWT = "^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$"
_CC = re.compile(r"creativecommons\.org/(?:licenses/([a-z-]+)|publicdomain/(zero))/(\d+(?:\.\d+)?)", re.IGNORECASE)


def model_url(model_id, slug=None):
    return "%s/model/%s-%s" % (WEB, model_id, slug) if slug else "%s/model/%s" % (WEB, model_id)


def _license(value):
    """'CC BY-NC-SA 4.0' for a Creative Commons licence, read off the link Printables gives with it; else its name."""
    if not isinstance(value, dict):
        return None
    found = _CC.search(value.get("content") or "")
    if found:
        kind, zero, version = found.groups()
        return "CC0 %s" % version if zero else "CC %s %s" % (kind.upper(), version)
    return value.get("name") or value.get("abbreviation") or None


def _bearer(token):
    return {"Authorization": "Bearer " + token} if token else None


def _expiry(token):
    """When a JWT says it expires, as text; None when it does not say. Read for the user, not trusted."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(claims["exp"])))
    except (IndexError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def _messages(answer):
    """What a mutation's 'errors' say, as one line."""
    said = []
    for error in (answer or {}).get("errors") or []:
        if isinstance(error, dict):
            said += [str(m) for m in error.get("messages") or [] if m]
    return ", ".join(said)


class Printables(rm.Site):
    NAME = "printables"
    TITLE = "Printables"
    URL = WEB
    DESC = "Models on Printables, a part per file, by the model's number. Nothing is listed; search instead."
    VERSION = CACHE_VERSION
    LOGIN_INSTRUCTIONS = (
        "A free model's files need no login at all; only a paid model's do, and only for the account that bought it. "
        "What is needed then is the 'auth.access_token' cookie of printables.com, from a browser signed in to "
        "Printables: the browser's developer tools show it, under Application (or Storage) > Cookies. It is short- "
        "lived."
    )
    CREDENTIALS = {"token": "PRINTABLES_TOKEN"}

    def __init__(self, request=None):
        super().__init__(request)
        self.token = rm.credential(self.request, "token", "PRINTABLES_TOKEN")

    def valid_id(self, model_id):
        return model_id.isdigit()

    def usable(self, file):
        # Whether the user bought a paid model is not something the API tells
        # anyone but them, so with a token it is taken that they did.
        return bool(self.token) or not file.extra.get("paid")

    # -- the API --

    def _graphql(self, operation, query, variables, what, ttl=0, token=None):
        """The 'data' of a GraphQL answer; a SiteError for one that says what went wrong instead."""
        answer = self.http.json(
            API,
            what,
            headers=_bearer(token),
            data={"operationName": operation, "query": query, "variables": variables},
            ttl=ttl,
            # An answer that carries errors is a 200 like any other; it is not kept.
            valid=lambda value: isinstance(value, dict) and not value.get("errors"),
        )
        if not isinstance(answer, dict):
            raise rm.SiteError("printables: %s: the API did not answer with GraphQL" % what)
        if answer.get("errors"):
            said = "; ".join(str(e.get("message")) for e in answer["errors"] if isinstance(e, dict))
            raise rm.SiteError("printables: %s: %s" % (what, said or "the API answered with errors"))
        return answer.get("data") or {}

    def _model(self, data):
        """A Model out of a 'print' of the API, every file of every list in it."""
        model_id = str(data["id"])
        paid = bool(data.get("price") or data.get("premium"))
        files = []
        for field, kind, prefix in _LISTS:
            for entry in data.get(field) or []:
                if not isinstance(entry, dict) or entry.get("id") is None or not entry.get("name"):
                    continue
                # One name can be in two folders of a model (a variant each), so
                # a file's name is the folder it is in and its own.
                folder = (entry.get("folder") or "").strip("/")
                files.append(
                    rm.File(
                        prefix + str(entry["id"]),
                        folder + "/" + entry["name"] if folder else entry["name"],
                        size=entry.get("fileSize"),
                        number=str(entry["id"]),
                        kind=kind,
                        paid=paid,
                    )
                )
        user = data.get("user") or {}
        return rm.Model(
            model_id,
            title=data.get("name"),
            url=model_url(model_id, data.get("slug")),
            author=user.get("publicUsername") or user.get("handle"),
            license=_license(data.get("license")),
            files=files,
        )

    def model(self, model_id):
        found = self._graphql("PrintablesModel", _MODEL, {"id": model_id}, "model %s" % model_id, ttl=_MODEL_TTL)
        if not isinstance(found.get("print"), dict):
            raise rm.NotFound("printables: model %s: not found" % model_id)
        return self._model(found["print"])

    def _link(self, model, file, token):
        """What the download mutation answers for 'file', asked as the user of 'token', or as nobody."""
        what = "a download link for %s of model %s" % (file.name, model.id)
        variables = {"id": file.extra["number"], "printId": model.id, "fileType": file.extra["kind"]}
        try:
            # Never cached: every answer is a fresh link, and a count of downloads.
            return (
                self._graphql("PrintablesDownload", _DOWNLOAD, variables, what, token=token).get("getDownloadLink")
                or {}
            )
        except rm.NeedsCredentials:
            raise rm.NeedsCredentials(
                "printables: %s: Printables did not take the token. Its tokens are short-lived; run '%s' "
                "again, or give a new one as PRINTABLES_TOKEN or the 'token' parameter" % (what, LOGIN_COMMAND)
            ) from None

    def download(self, model, file):
        what = "%s of model %s" % (file.name, model.id)
        needs = (
            "printables: %s is a file of a paid model, which only the Printables user who bought it may "
            "download: run '%s' as them, or give their token as PRINTABLES_TOKEN or the 'token' parameter "
            "(see the README)" % (what, LOGIN_COMMAND)
        )
        # A free model's files are anybody's and are asked for as nobody: a
        # token is short-lived, and the API refuses every request that carries
        # one it no longer takes, even a request that needs none.
        signed_in = bool(file.extra.get("paid"))
        if signed_in and not self.token:
            raise rm.NeedsCredentials(needs)
        answer = self._link(model, file, self.token if signed_in else None)
        if not answer.get("ok") and not signed_in and self.token and "anonymous" in _messages(answer):
            answer = self._link(model, file, self.token)
        link = (answer.get("output") or {}).get("link")
        if answer.get("ok") and link:
            return self.http.download(link, what)
        said = _messages(answer)
        if "anonymous" in said:
            raise rm.NeedsCredentials("%s (Printables said: %s)" % (needs, said))
        raise rm.SiteError("printables: %s was not handed over: %s" % (what, said or "no link came back"))

    def search(self, text, limit):
        found = self._graphql(
            "PrintablesSearch",
            _SEARCH,
            {"query": text, "limit": limit, "offset": 0},
            "a search for '%s'" % text,
            ttl=600,
        )
        items = (found.get("searchPrints2") or {}).get("items") or []
        return [self._model(item) for item in items if isinstance(item, dict) and item.get("id") is not None]

    # -- logging in --

    def whoami(self, credentials):
        token = credentials.get("token")
        if not token:
            return None
        status, answer = self.http.probe(
            API,
            "who the Printables token is",
            headers=_bearer(token),
            data={"operationName": "PrintablesMe", "query": _ME, "variables": {}},
        )
        # The API answers a token it does not take, and no token at all, with
        # a 401 and a line of text ('Token is invalid').
        if status in (401, 403):
            return None
        me = ((answer or {}).get("data") or {}).get("me") if isinstance(answer, dict) else None
        if status != 200 or (isinstance(answer, dict) and answer.get("errors") and me is None):
            raise rm.SiteError("printables: asking who the token is answered HTTP %d" % status)
        if not isinstance(me, dict):
            return None
        who = me.get("handle") or me.get("publicUsername") or "a Printables user"
        until = _expiry(token)
        return "%s (its token expires %s)" % (who, until) if until else who

    def login_spec(self):
        # Signing in to Printables is signing in to a Prusa Account, on
        # account.prusa3d.com, which sends the browser back to Printables with
        # the token in a cookie. A visitor has no such cookie, and one left over
        # from an earlier session can be expired until the site has renewed it,
        # so the capture waits until the API answers the browser's own session
        # with somebody - asked over GET, which the API answers as it does POST.
        return {
            "url": WEB + "/",
            "title": "Printables",
            "capture": [{"name": "token", "cookie": {"url": WEB + "/", "name": TOKEN_COOKIE}, "match": _JWT}],
            "done_when": {"fetch": {"url": API + "?query=" + urllib.parse.quote("{me{id}}"), "status": 200}},
            "guide": [
                # The account's form shows the password only once the e-mail
                # is in, and the first entry that shows is the one pointed at.
                {
                    "url": "https://account.prusa3d.com/login*",
                    "selector": "#id_password",
                    "text": "Your Prusa Account password, then 'Log in'",
                },
                {
                    "url": "https://account.prusa3d.com/login*",
                    "selector": "#id_email",
                    "text": "Printables signs in with a Prusa Account: its e-mail, then 'Continue' - or Google, "
                    "Apple or Facebook below",
                },
                {
                    "url": WEB + "/*",
                    "selector": "a[href*='/login'], a[href*='account.prusa3d.com']",
                    "text": "Log in to Printables (with a Prusa Account)",
                },
            ],
        }


def get(key):
    return rm.serve(Printables(globals().get("request")), key)


# Last, so that everything above is defined when PartCAD runs this.
if __name__ == "get":
    output = {"result": get(request["key"])}  # noqa: F821 - injected by the runtime
elif __name__ == "login":
    output = {"result": rm.login(Printables(globals().get("request")), globals().get("partcad_login"))}
else:
    output = {}
