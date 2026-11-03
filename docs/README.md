# Documentation

The user guide is a Sphinx site using Furo. It builds independently of the API:
no application installation, database, Poetry, or historical PDP checkout is
required. Python 3.12 is used in CI.

## Build and preview

From the repository root:

```console
python3 -m venv /tmp/pdp-docs
/tmp/pdp-docs/bin/pip install -r docs/requirements.txt
python3 docs/import_portal.py
/tmp/pdp-docs/bin/sphinx-build -d docs/_build/doctrees -b html --fail-on-warning --keep-going docs/source docs/_build/html
python3 -m http.server 8080 --directory docs/_build/html
```

Open http://localhost:8080. Edit the RST files in `docs/source`; generated HTML
is ignored by Git. `docs/station-data.md` remains a short repository entry point.

The opening base URL note uses the PCDS route `/met-data-portal-pcds/api/data`
from `portainer-deployment/apps/dev/met-data-portal-pcds/docker-compose.yaml`
(the `mdp_pcds_data` router), on `https://services.pacificclimate.org`.
Update that note if the deployment route changes; building the docs does not
require a checkout of the deployment repo. Sphinx inserts the UTC build date
through `|today|`. All subsequent API examples use the literal `[base_url]`
placeholder defined by the note.

## Portal user guide

Portal instructions are maintained in `station-data-portal/docs/user/` and
imported into the generated, ignored `docs/source/portal/` directory. Do not
edit the generated copy. Like the historical PDP build, the importer reads
`docs/user/manifest.yaml` and copies only the files listed there, preserving
its recursive directory structure. PyYAML parses the manifest with `safe_load`.
Only documentation and image file types are accepted; configuration and
executable files are rejected, and missing listed files fail the import.

`docs/portal-source.json` pins the portal to a full commit SHA. Normal builds
fetch that immutable source from GitHub; they never follow a moving branch.
The importer reads the portal version from that commit's `package.json` and
adds it and the source revision to the guide. The API version remains separate.
Network or source errors fail the import rather than falling back to stale files.
Run the importer before Sphinx, including when building locally. CI does both.

To preview uncommitted portal guide changes from a sibling checkout:

```console
python3 docs/import_portal.py --local-preview ../station-data-portal
/tmp/pdp-docs/bin/sphinx-build -E -b html --fail-on-warning --keep-going docs/source docs/_build/html
```

The imported page is marked Local preview. Do not publish that output; rerun
the normal pinned import before producing a deployable site.

When releasing a portal update, first commit and push its guide, then update
`revision` in `docs/portal-source.json` to the full SHA containing that guide.
Rebuild and deploy the documentation image for the API and portal being served.
An API-only release retains the existing portal pin. A guide correction can
advance the pin independently if it still describes the deployed portal.

## Brand colours

The theme uses the supplied **PCIC Style Quick Reference** palette. Colour
settings live in `docs/source/conf.py`; heading and callout styling lives in
`docs/source/_static/pcic.css`. Light mode uses dark blue links and titles,
dark green section headings, neutral web surfaces, and pale green callouts.
Medium green accents the page title. Dark mode uses light blue and light green
on Furo's dark neutral surfaces, since the reference does not define dark mode.
Warning and danger accents use the guide's semantic amber and red. Typography
continues to use the theme's system fonts.

## Static serving container

Build the HTML first, then run these commands from the repository root:

```console
docker build -f docker/docs.Dockerfile \
  --build-arg API_VERSION="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["tool"]["poetry"]["version"])')" \
  --build-arg DOCS_REVISION="$(git rev-parse HEAD)" \
  -t pdp-station-api-docs docs/_build/html
docker run --rm -p 8080:80 pdp-station-api-docs
```

The build context contains only generated static files. Nginx serves them on
port 80; the container does not include Python, Sphinx, or the API. If hosting
under a prefix such as `/station-docs/`, redirect `/station-docs` to its trailing
slash form and strip the prefix when forwarding to Nginx. Do not add an SPA
fallback: missing documentation pages should return 404.

## Publishing and API versions

The separate **Documentation Container** workflow builds and checks the site and
Nginx container for pushes and pull requests. Pushes and manual workflow runs
publish `pcic/pdp-station-api-docs` using the same Docker Hub secrets as the API
workflow. Pull requests never log in or publish. No deployment is performed.

The visible API version comes directly from `tool.poetry.version` in
`pyproject.toml`. Release tag builds fail if the tag differs from that version.
Docker's pinned `metadata-action` generates image tags and OCI labels; the
API version label is explicitly set to the package version. A small shell step
reads that version from `pyproject.toml` for the action and container build.

Published image tags are:

- `X.Y.Z` for a matching release tag.
- `sha-<full-commit-sha>` and `api-X.Y.Z-docs-<full-commit-sha>` for each build.
- `branch-<sanitized-branch-name>` for branch builds.
- `latest` additionally for `main`.

Deploy the API release and the corresponding docs image together in your
deployment configuration. For example, pair `pcic/pdp-station-api:0.1.6` with
`pcic/pdp-station-api-docs:0.1.6` after both workflows have published that release.
For documentation-only corrections, build from a branch retaining the deployed
API version and select the resulting `api-X.Y.Z-docs-<full-commit-sha>` tag (or
image digest). Avoid `latest` when the API is pinned to a release.

This pairing is deliberate: a static site cannot detect a deployment changing
independently. Updating the API's deployment must also select the matching docs
image. Existing release tags that predate this workflow do not automatically
gain documentation images.

## Migration scope

The guide adapts `pdp:pcds-only`'s `doc/source/pcds.rst` Station Listings and
Advanced/Programmatic Usage, plus relevant FAQ and contributor guidance. Routes,
formats, time handling, and examples describe this API. The old developer
autodoc and raster portal material are excluded. Map UI instructions come from
the separately pinned portal guide rather than the historical PDP copy. The
raster Power user HOWTO describes separate catalog and mapping services, so it
is not presented as a station API feature. The original repository is unchanged.
