# pdp-station-api

A streaming DAP2 service for PCIC station observations. It replaces the
station-data portion of PDP's `pcds-only` backend while keeping protocol,
database, and web-server concerns independent.

## Architecture

1. `persistence` owns SQLAlchemy/PyCDS queries and streaming database sessions.
2. `application` describes station datasets without depending on HTTP or DAP.
3. `dap` adapts a station dataset to pydap's synchronous WSGI interface.
4. `web` provides the ASGI application and mounts the WSGI DAP app at `/dap`.

The supported Python versions are 3.12 and 3.13. Current pydap requires at
least 3.12, and PyCDS currently requires Python earlier than 3.14.

## Development

PyCDS currently installs the source distribution of `psycopg2`, so PostgreSQL
client development files (including `pg_config`) must be installed first.

```console
poetry install
poetry run pytest
PCDS_DSN=postgresql+psycopg2://user:password@host/database poetry run pdp-station-api
```

## Container image

Build and run the production image locally with:

```console
docker build -f docker/Dockerfile -t pdp-station-api .
docker run --rm -p 8000:8000 \
  -e PCDS_DSN=postgresql+psycopg2://user:password@host/database \
  pdp-station-api
```

GitHub Actions tests every push and pull request on Python 3.12 and 3.13.
Pushes also publish `pcic/pdp-station-api:<branch-or-tag>` to Docker Hub. The
`main` branch additionally publishes `pcic/pdp-station-api:latest`, and tags of
the form `X.Y.Z` publish a matching versioned image. Docker publishing requires
the same `pcicdevops_at_dockerhub_username` and
`pcicdevops_at_dockerhub_password` repository secrets used by other PCIC
services.

Application logging defaults to `INFO`. Set `PDP_STATION_LOG_LEVEL` to `DEBUG`,
`INFO`, `WARNING`, `ERROR`, or `CRITICAL`; for example, aggregate request and
station progress messages can be enabled with:

```console
PDP_STATION_LOG_LEVEL=DEBUG \
PCDS_DSN=postgresql+psycopg2://user:password@host/database \
poetry run pdp-station-api
```

## Kubernetes readiness

`GET /readyz` verifies that the service can acquire a database connection and
that every table, view, and materialized view it reads exists. It also checks
that the configured role has `USAGE` on their schema and effective `SELECT`
privilege on each relation. These are PostgreSQL catalog checks and do not scan
station or observation data. The endpoint returns plain-text `ok` with status
`200` when the service can accept traffic and status `503` when a check fails.
`GET /readyz?verbose` reports existence, schema `USAGE`, and `SELECT` status for
each required relation. Raw database exception details are written only to
server logs.

```yaml
readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
  periodSeconds: 10
  timeoutSeconds: 5
```

## URL hierarchy

All paths are application-relative. A reverse-proxy prefix such as
`/prime/api/data` may precede them. Bracketed annotations describe behavior;
`[/]` means that both trailing- and non-trailing-slash forms are accepted.

```text
/
├── /readyz[?verbose]                         [readiness]
├── /networks/{network}                       [HTML station catalog]
├── /agg[/]                                   [aggregate ZIP]
│                                                GET, POST, QUERY, OPTIONS
│
├── /dap
│   ├── /stations/{station_id}.{response}     [raw observations]
│   ├── /climatologies/{station_id}.{response}[climatology]
│   ├── /raw/{network}/{native_id}.{response} [raw observations]
│   └── /climo/{network}/{native_id}.{response}
│                                                [climatology]
│
└── Legacy compatibility                      [307 redirects]
    ├── /pcds/agg[/]
    │       → /agg
    └── /pcds/lister
        ├── [/]
        │       → /
        ├── /{raw|climo}[/]
        │       → /
        ├── /{raw|climo}/{network}[/]
        │       → /networks/{network}
        ├── /raw/{network}/{native_id}
        │       → /dap/raw/{network}/{native_id}.html
        ├── /climo/{network}/{native_id}
        │       → /dap/climo/{network}/{native_id}.html
        ├── /raw/{network}/{native_id}.rsql.{format}
        │       → resolve (network, native_id) to station_id
        │       → /dap/stations/{station_id}.{format}
        └── /climo/{network}/{native_id}.csql.{format}
                → resolve (network, native_id) to station_id
                → /dap/climatologies/{station_id}.{format}
```

The application root lists published networks. Network catalog pages link to
the public `network/native_id` DAP HTML forms. Numeric `station_id` routes are
the corresponding low-level database-ID interface; the two identifier forms
remain separate.

Canonical DAP responses are `dds`, `das`, `dods`, `asc`, `ascii`, `html`,
`ver`, `xlsx`, `nc`, and `csv`. Legacy SQL-handler URLs also accept `xls` and
redirect it to `xlsx`.

Intermediate breadcrumb paths under `/dap` redirect to the catalog: `/dap`,
`/dap/raw`, `/dap/climo`, `/dap/stations`, and `/dap/climatologies` go to `/`,
while `/dap/raw/{network}` and `/dap/climo/{network}` go to the corresponding
network page. These redirects support both trailing-slash forms.

## Direct station downloads

In addition to the standard DAP responses, `xlsx` and `nc` generate Excel and
NetCDF4 downloads. These formats are assembled in a `SpooledTemporaryFile` so
small responses stay in memory and larger responses automatically roll over to
disk. The rollover threshold defaults to 1 GiB and can be set in bytes with
`PDP_STATION_SPOOL_MAX_SIZE`. Set it to `0` to roll over immediately. Excel files
are limited to 1,048,575 observations plus their header row.

Excel generation uses Python XlsxWriter by default. Set
`PDP_STATION_XLSX_ENGINE=rustpy` to use the experimental Rust-backed
`rustpy-xlsxwriter` engine for direct and aggregate XLSX downloads. The default
can be selected explicitly with `PDP_STATION_XLSX_ENGINE=xlsxwriter`.
If a constraint produces no observation rows, the Rust-backed path delegates
that workbook to XlsxWriter so the data sheet still contains its column header
row.

Each dataset includes `NC_GLOBAL` station, network, contact, location, and
elevation attributes. Horizontal coordinates are derived only from station
history geometry. Network contact details are used when available and default
to `pcic.support@uvic.ca`. Observation variables include their PyCDS display
name, description, CF standard name, units, and cell-method metadata. Time is
exposed as an ISO-8601 string with time-coordinate metadata. The global dataset
name is prefixed by the SQLAlchemy database name, and its history records the
UTC generation time, `pdp-station-api` package version, and source database.

## Aggregate downloads

`/agg` selects multiple published stations and returns a ZIP archive containing
one data file per station and a `variables.csv` index in each network folder.
The preferred interface is the safe, idempotent HTTP `QUERY` method defined by
RFC 10008. `POST` accepts the same body for compatibility with clients and
proxies that do not yet support `QUERY`; the legacy `GET` query-string contract
is also supported during migration.

```console
curl -X QUERY http://localhost:8000/agg \
  -H 'Content-Type: application/json' \
  --data '{
    "networks": ["FLNRO-WMB", "BC-TS"],
    "from_date": "2020-01-01",
    "to_date": "2020-12-31",
    "polygon": "MULTIPOLYGON (((-123.60 49.41, -123.60 49.45, -123.54 49.45, -123.54 49.41, -123.60 49.41)))",
    "clip_dates": true,
    "format": "nc"
  }' --output pcds_data.zip
```

JSON accepts `networks`, `variables`, and `frequencies` as lists. Dates may use
`YYYY-MM-DD` or the legacy `YYYY/MM/DD` form. The legacy form names
(`network-name`, `input-vars`, `input-freq`, `input-polygon`, `data-format`,
`cliptodate`, and the download flags) are accepted in query strings and
form-encoded bodies. Variable and frequency filters determine which stations
are included; as in PDP, they do not remove columns from the station files.

Before starting a response, the service resolves the complete station set,
enforces its limit, and loads each station's metadata and variable description.
This catches likely failures without running the expensive observation queries.
It then emits the ZIP signature and streams each member with ZIP data
descriptors as its `obs_raw` query completes. Individual NetCDF and Excel
members still use the configured spool threshold because those formats require
finalization before their bytes can be read.

Once the ZIP signature has been sent, an observation-query or serialization
failure can only terminate the download; it cannot be changed into an HTTP
error response.

Aggregate generation logs a 16-character SHA-256 fingerprint of the normalized
request at debug level. Preflight, station retrieval, and completion messages
share this identifier. Mid-stream failures are logged at error level with a
traceback and the active station's numeric ID, network, and native ID, allowing
a truncated client download to be correlated with server logs without logging
the polygon or other raw request parameters.

## Legacy compatibility

Legacy redirects preserve the query string. The `307` response also preserves
the HTTP method and body for aggregate requests. `.rsql` and `.csql` are
accepted only at this compatibility boundary because they expose historical
`pydap.handlers.sql` implementation details.

The legacy lister hierarchy begins at the observed public path
`/pcds/lister`. Deployment-level prefixes remain the reverse proxy's
responsibility.

Redirect targets are relative, so proxy prefixes are preserved without being
known by the application. For example, development may expose the legacy
service under `/met-data-portal-pcds/api/data` and this service under
`/prime/api/data` while both applications operate on the hierarchy above.

See [Station data URLs](docs/station-data.md) for constraint and download
examples adapted from the PDP user documentation.
