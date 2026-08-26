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

Database rows are fetched in batches of 10,000 by default. Set
`PDP_STATION_DATABASE_YIELD_PER` to a positive row count to tune the tradeoff
between database round trips and memory use. For example, a performance test
with generous container memory can use:

```console
PDP_STATION_DATABASE_YIELD_PER=100000 \
PCDS_DSN=postgresql+psycopg2://user:password@host/database \
poetry run pdp-station-api
```

The setting is a row count, not a byte limit. Pivoted rows become wider as a
station has more variables, so the memory represented by 100,000 rows varies
between stations.

For targeted query-plan diagnostics, set a comma-separated list of numeric
station IDs in `PDP_STATION_EXPLAIN_ANALYZE_STATION_IDS`. The service logs the
exact SQL, parameters, and PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`
plan before retrieving each selected station. For example:

```console
PDP_STATION_EXPLAIN_ANALYZE_STATION_IDS=2338,3301
```

This option executes each selected observation query twice: once to produce
the plan and once to produce the download. It should be enabled temporarily
and only for specific stations. The analysis also warms PostgreSQL's cache, so
the subsequent download timing is not an unbiased cold-query measurement.

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

The initial endpoint shape is:

```text
/dap/stations/{station_id}.dds
/dap/stations/{station_id}.das
/dap/stations/{station_id}.dods
/dap/stations/{station_id}.ascii
/dap/climatologies/{station_id}.{response}
/dap/raw/{network}/{native_id}.{response}
/dap/climo/{network}/{native_id}.{response}
```

In addition to the standard DAP responses, `xlsx` and `nc` generate Excel and
NetCDF4 downloads. These formats are assembled in a `SpooledTemporaryFile` so
small responses stay in memory and larger responses automatically roll over to
disk. The rollover threshold defaults to 1 GiB and can be set in bytes with
`PDP_STATION_SPOOL_MAX_SIZE`. Set it to `0` to roll over immediately. Excel files
are limited to 1,048,575 observations plus their header row.

Excel generation uses Python XlsxWriter by default. Set
`PDP_STATION_XLSX_ENGINE=rustpy` to use the experimental Rust-backed
`rustpy-xlsxwriter` engine for direct and aggregate XLSX downloads. The default
can be selected explicitly with `PDP_STATION_XLSX_ENGINE=xlsxwriter`. Debug XLSX
timing records include the selected engine so equivalent requests can be
compared directly.
If a constraint produces no observation rows, the Rust-backed path delegates
that workbook to XlsxWriter so the data sheet still contains its column header
row.

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
error response. `PDP_STATION_AGGREGATE_MAX_STATIONS` limits a selection to 1,000
stations by default.

Aggregate generation logs a 16-character SHA-256 fingerprint of the normalized
request at debug level. Preflight, station retrieval, and completion messages
share this identifier. Mid-stream failures are logged at error level with a
traceback and the active station's numeric ID, network, and native ID, allowing
a truncated client download to be correlated with server logs without logging
the polygon or other raw request parameters.

Debug logs also report preflight selection and metadata timing. For each
station they report time to the first query row, time retrieving the remaining
rows, time serializing the requested format, and time writing and finalizing
the ZIP member, together with row and uncompressed-byte counts. The `query`
value is the sum of `first_row` and `remaining_rows`. Time suspended while
waiting for the client to consume a streamed chunk is deliberately excluded.
Excel responses add a second timing record that separates metadata generation,
PyDAP row normalization, XlsxWriter cell and XML generation, workbook
finalization, and copying the completed XLSX from its spool. The XLSX `write`
value excludes the separately measured database iteration and normalization
times.

The service also provides a small HTML catalog. `/` lists published networks,
and `/networks/{network}` lists that network's published stations. Station
links open the corresponding public DAP HTML download form.

Pydap builds its HTML breadcrumbs mechanically from each segment of a dataset
URL. Intermediate paths such as `/dap/raw` and `/dap/raw/{network}` are not DAP
datasets in this service, so exact ASGI routes redirect them to `/` and
`/networks/{network}` respectively. Equivalent redirects cover climatology and
numeric-ID paths. These shims keep pydap's generated breadcrumbs useful without
overriding or depending on its internal Jinja templates. Both trailing- and
non-trailing-slash forms are handled because the broader `/dap` mount would
otherwise consume trailing-slash paths before Starlette could normalize them.
The `/dap` and `/dap/` roots also redirect to `/`, which makes pydap's generated
“Home” breadcrumb return to the network catalog.

Numeric PyCDS station IDs provide the canonical low-level API. The `raw` and
`climo` routes provide a user-facing compatibility interface that resolves a
published network and native station ID to the internal station ID. Responses
are served directly through DAP; the legacy `.rsql` path component is not used.

Each dataset includes `NC_GLOBAL` station, network, contact, location, and
elevation attributes. Horizontal coordinates are derived only from station
history geometry. Network contact details are used when available and default
to `pcic.support@uvic.ca`. Observation variables include their PyCDS display
name, description, CF standard name, units, and cell-method metadata. Time is
exposed as an ISO-8601 string with time-coordinate metadata.
The global dataset name is prefixed by the SQLAlchemy database name, and its
history records the UTC generation time, `pdp-station-api` package version, and source
database.
