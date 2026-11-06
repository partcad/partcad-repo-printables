# Printables for PartCAD

Serves Printables' models as PartCAD parts, published as
`//pub/collection/printables/models`.

**Nothing is listed.** A model site's catalog is not something to enumerate,
so `pc list parts` of this package is empty, as is `pc list packages`. A part is
asked for by name, and found with `pc search parts`:

```shell
pc search parts -P //pub/collection/printables/models -k "cable clip"
pc inspect "//pub/collection/printables/models:271731"
```

**No geometry is vendored.** Every file is fetched from Printables the first
time a part is built, and kept by PartCAD from then on.

**Nothing here is manufacturable.** The package says `manufacturable: false`,
and so does the plugin of what it serves: an upload to a model site says
nothing about whether, or how, it is made to be made.

Requires PartCAD 0.9.3 or newer: the first release with `pc login`, which is how
the plugin is given a paid model's buyer's sign-in. Its repository plugins may
also search their own catalog (`searchKinds`) and resolve a parametrized name
themselves (`instanceKinds`); both are described under "Repositories" in
PartCAD's documentation.

## Names

A model is a part per file of it that PartCAD reads, and the name says which.
A model is named by its number, as in `printables.com/model/271731-cable-clip`:

| Name | Is |
| --- | --- |
| `271731` | the model's best file |
| `271731;format=stl` | its best STL |
| `271731;file=1234824` | one of its model files, by its number on Printables |
| `271731;file=<name>` | or by its name; a file in a folder after the folder, `Dragon_v2/Dragon_v2.3mf` |
| `271731;file=other-<number>` | a file of the model's "Other files", by its number |

Printables keeps a model's files in four lists - model files, other files,
G-codes and SLA files - and numbers each list on its own, so a number names a
model file, and a file of another list is named with the list in front of its
number (`other-`, `gcode-`, `sla-`; nothing PartCAD reads is ever a G-code or an
SLA file, but naming one says so rather than "not found"). The site does not
show these numbers; `pc info` of a part does, as its `file`, and a search names
every hit by one. A name is a folder and a file because a model can have one
file name in two folders, one variant each.

Both may be given, and must then agree; a third, `source`, and the plugin's
own `formats` are under [Parameters](#parameters). "Best" is by format, in
this order unless `formats` says otherwise, and among files of one format the first in the designer's order:

| Format | Read as PartCAD part type | Extensions |
| --- | --- | --- |
| `step` | `step` | `.step`, `.stp` |
| `brep` | `brep` | `.brep`, `.brp` |
| `3mf` | `3mf` | `.3mf` |
| `stl` | `stl` | `.stl` |
| `obj` | `obj` | `.obj` |
| `glb` | `gltf` | `.glb` |
| `scad` | `scad` | `.scad` |

An exact boundary representation beats a mesh of it, and 3MF knows its units
where STL does not. A `.gltf` is not served, since the buffers it names beside
itself do not come with it; an OpenSCAD source is last, because on a model site
it is usually the customizable source of the meshes beside it. A file in any
other format - Fusion 360, SketchUp, AMF, a G-code, a picture - is not a part. A
name that asks for one, or for a file the model has not got, is not found, and
the plugin says why.

These names are resolved by the plugin rather than by PartCAD applying the
parameters to a base part, because another file is another `path` and maybe
another `type`. `pc info` of a part shows the `file` and `format` it resolved
to, which is what to write to pin it: the best file of a model can change when
its designer uploads another.

## Search

`pc search parts -k <words>` asks Printables' own search (`searchPrints2`,
best match first), and answers with names of the form above - one per file, so
a hit is everything needed to fetch its geometry. Two files that differ only in
their extension (`clip.step`, `clip.stl`) are one part in two formats, and only
the better is named; a model with no file PartCAD reads is not a hit. `--limit`
caps the hits (20 by default); the plugin asks for three times as many models,
whose files come with them, so a search is one request.

Only free models are searched for. A hit is a name to build, and a paid model
builds only for whoever bought it; they can still name it by its number.

A search is never cached by PartCAD; the plugin keeps what the site answered for
ten minutes.

## Credentials

**None are needed for a free model.** A model's details, its files and a search
are Printables' to give anyone, and so are a free model's files: the plugin asks
for all of them as nobody.

**A paid model's files take the Printables user who bought it.** Printables
signs in with a Prusa Account, and keeps the signed-in user's access token in
the `auth.access_token` cookie of printables.com. Log in once, and PartCAD keeps
the token as your own parameter of the plugin:

```shell
pc login //pub/collection/printables:printables_repo
```

That opens your browser on printables.com - in PartCAD's own profile of it, with
PartCAD's extension in it - and points at the "Log in" control. Sign in to your
Prusa Account there (e-mail and password, or Google, Apple or Facebook); when
Printables' API answers that browser's own session with you, the extension
hands the cookie to PartCAD, the plugin checks it by asking the API who it is,
and PartCAD saves it in your `~/.partcad/config.yaml`. `pc login` checks a saved
token first and opens the browser only when Printables no longer takes it.

Or give the token by hand - the value of the `auth.access_token` cookie of
printables.com in a browser signed in to it - either way, never in a package:

```shell
export PRINTABLES_TOKEN=...       # read by the plugin; see the note on Docker below
```

```yaml
# ~/.partcad/config.yaml
parameters:
  "//pub/collection/printables:printables_repo":
    token: "..."
```

**The token is short-lived.** It is a Prusa Account access token, which the
website renews as it is used and which, by what is known of it, lasts minutes
rather than days; `pc login` says when the one it saved expires. When a paid
model's download says Printables did not take the token, run `pc login` again.
A token Printables no longer takes makes the API refuse every request it is
sent with, even one that needs none - which is why the plugin sends it with
nothing but a paid model's download.

The token is sent as `Authorization: Bearer` to `api.printables.com`, with the
request for a paid model's file's download link and nothing else - never with a
model's details or a search, and never to `files.printables.com`, where the link
points. Whether you bought a model is not something the API tells anyone else,
so with a token a paid model's files are taken to be yours; if they are not,
Printables says so and the plugin passes it on.

**Docker.** PartCAD runs a plugin in its Python sandbox, and the `docker` sandbox
does not carry PartCAD's environment into its container, so an environment
variable does not reach the plugin there. The repository parameter does, being
part of what PartCAD hands the plugin; use that (`pc login` does), or
`pythonSandbox: venv`.

## Parameters

The plugin's parameters, declared in `partcad.yaml`, are a default for every
Printables part:

| Parameter | Default | What it is |
| --- | --- | --- |
| `formats` | all, in the order above | The formats to take a model in, best first, separated by commas. A format left out is not taken - `stl,3mf` is meshes only - unless a part asks for it by its own `format` or `file`. |
| `source` | `auto` | Which of a model's files: Printables has no preview meshes of its own - and a free model's files need no login at all - so `auto` and `original` are the same here and `preview` finds nothing. |
| `token` | empty | The `auth.access_token` cookie of printables.com, signed in. Only a paid model's files need it, and only its buyer's; it is short-lived. `PRINTABLES_TOKEN` gives it too. |

They are yours to set without touching this package - every one of them, the
credentials included, and the OAuth or API-key settings beside them:

- in your own `~/.partcad/config.yaml`, by the plugin's name, which is where
  `pc login` keeps the credentials:

  ```yaml
  parameters:
    "//pub/collection/printables:printables_repo":
      formats: stl,3mf
  ```

- or, for anything but the credentials, in a package of your own, as an enrich
  of the plugin and a package it serves - `//printables_meshes:<model>` in a
  package at the root:

  ```yaml
  repositories:
    meshes_repo:
      type: enrich
      source: //pub/collection/printables:printables_repo
      with:
        formats: stl,3mf
  dependencies:
    printables_meshes:
      type: external
      plugin: :meshes_repo
  ```

A part's own `file`, `format` and `source` override them for that part - in its
name (`271731;format=stl`), or in the `with` of an enrich of the part:

```yaml
parts:
  clip:
    type: enrich
    source: //pub/collection/printables/models:271731
    with:
      format: stl
```

PartCAD keys what it caches of this package on your overrides of the plugin's
parameters, so a change to one - logging in, too - takes effect at once. An
environment variable is not seen there: after setting one, `pc update`
refreshes what was cached without it.

## Logging in with nobody at the screen

An AI agent, or a script, logs in without a browser:

```shell
pc login --agent //pub/collection/printables:printables_repo
pc login --agent --set token=... //pub/collection/printables:printables_repo
```

The first prints what a person would do in the browser instead of opening one -
where to sign in, what to copy, and the command that hands it over - and exits
with status 3. It says that a free model's files need no login at all, and where in a signed-in browser the token is. The second hands over what the person found; the
plugin checks it with Printables before PartCAD keeps it. `pc mcp`'s `login`
tool works the same way.

## Status

Printables is asked through the GraphQL API its own website uses,
`https://api.printables.com/graphql/`. It has no published schema and turns
introspection off; what the plugin asks is what was found to work. The website
itself, www.printables.com, turns away this plugin's requests with a Cloudflare
bot check; the plugin says what it is and does not ask the website for anything.

Run against the live API on 2026-11-05, with the plugin's own User-Agent and no
sign-in:

- **A model** (`print(id:)`): its name, slug, author, licence, price, and its
  four file lists with each file's number, name, folder and size. A model that
  is not there is `null`.
- **Search** (`searchPrints2`, `paid: free`, `ordering: best_match`, up to 100
  at a time), with each hit's files in the same answer.
- **Downloads** (`getDownloadLink`): for a free model's model file and other
  file, a link to `files.printables.com` good for a day, which hands the file
  to the plugin (a 130 KB STEP, byte for byte). For a paid model's file, as
  nobody: refused, `cannot_download_premium_file_as_anonymous_user`.
- **A token the API does not take**: HTTP 401, `Token is invalid`, in plain
  text, on any request at all, public ones included.
- **Where the token is read from**: the API reads it from
  `Authorization: Bearer` and from a cookie named `auth.access_token` (a bogus
  value in that cookie is refused as one; under other names it is ignored), and
  answers GraphQL over GET as over POST. `me { id handle publicUsername }` is a
  valid question, answered with a 401 when nobody is signed in.
- **The Prusa Account sign-in form** (`account.prusa3d.com/login/`, which
  answers this plugin): the e-mail field `#id_email` first, then the password
  `#id_password`, which the page hides until the e-mail is in.
- **End to end with PartCAD**: `pc info` of `271731` (its STEP, downloaded and
  built: one solid, 1644.7 mm³) and of `271731;format=stl`, `pc export -t stl`
  of it, and `pc search parts -k "cable clip"`. A paid model resolves, and
  building it says it needs its buyer's sign-in.

Not run, for want of a Printables account, and written to what is known:

- **Logging in.** That the website keeps the token in the `auth.access_token`
  cookie, and that it is a Prusa Account JWT, comes from a third-party browser
  extension that reads it (Thingport) and from PrusaSlicer, which hands its
  Prusa Account token to the Printables website; the API's reading a cookie of
  that very name bears both out. The capture waits for the API's `me` to answer
  the browser's own session with 200, which needs that cookie to be sent to
  `api.printables.com` as well - which the API's reading it, and its allowing
  the website's origin to send cookies, suggest. The "Log in" control of the
  website could not be seen, so where the guide points on printables.com is a
  guess; on the Prusa Account form it is not.
- **A signed-in download** of a paid model, by its buyer, and what the API says
  to a signed-in user who did not buy it (passed on as it is).
- **How long a token lasts.** "Minutes" is the third party's word; `pc login`
  reports the expiry the token itself states.

`pc login` was run against the live site in a real (headed) Chrome with
PartCAD's extension: from where it was tested, www.printables.com put
Cloudflare's "Verify you are human" in front of its pages, which the
extension's bar asks the person to confirm, and nothing else. Signing in
through Prusa Account, and the `auth.access_token` cookie it is expected to
leave, were not seen live, for want of an account.

## Layout

| Path | Purpose |
| --- | --- |
| `partcad.yaml` | `//pub/collection/printables`; the `models` external dependency and the `printables_repo` repository that serves it. |
| `printables_repo.py` | The repository plugin: how Printables is asked, and how it is logged in to. |
| `remote_models.py` | What every model-site plugin shares, byte for byte: the names, the formats, HTTP and its cache, the keys PartCAD asks, logging in. The same file is in partcad-repo-thingiverse, partcad-repo-makerworld, partcad-repo-grabcad, partcad-repo-printables and partcad-repo-cults3d; `remote_models.sha256` is its digest, and a test fails when the two disagree - change it in all five. |
| `test_*.py` | The tests. Nothing in them touches the network. |

```shell
python -m pytest
```

When what the plugin answers changes - here or in `remote_models.py` - raise
`CACHE_VERSION` in `printables_repo.py`: PartCAD keys everything it caches of
this package on it.

## Caching

PartCAD keeps every answer the plugin gives, files included, under its own
cache, apart from a search. The plugin keeps what Printables answered under
`~/.cache/partcad-printables/` (or `$PARTCAD_PRINTABLES_CACHE`): a model's
details for a day (an answer that carried GraphQL errors not at all), a search
for ten minutes, and a request that came to
nothing for a while too, so that a refused or throttled run is not repeated in
full by the next one - a 404 for a day, anything else for five minutes. A
download link is never kept: each is fresh, and each counts as a download of
the model on Printables. Delete the directory to start over.

Every request says what it is: `User-Agent: Mozilla/5.0 (compatible;
PartCAD-printables/<version>; +https://github.com/partcad/partcad-repo-printables)`.

## Licensing

The code here is Apache-2.0 (`LICENSE`). Each model carries its own licence,
which the part states (`license`): a Creative Commons one by its name and
version (`CC BY-NC-SA 4.0`, `CC0 1.0`), read off the link Printables gives with
it, and any other by the name Printables gives it - a paid model's is commonly
the "Standard Digital File License". It is the designer's, not this package's,
and Printables' own terms of use apply to using the site.
