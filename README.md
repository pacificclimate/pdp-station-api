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

Application logging defaults to `INFO`. Set `PDP_STATION_LOG_LEVEL` to `DEBUG`,
`INFO`, `WARNING`, `ERROR`, or `CRITICAL`; for example, aggregate request and
station progress messages can be enabled with:

```console
PDP_STATION_LOG_LEVEL=DEBUG \
PCDS_DSN=postgresql+psycopg2://user:password@host/database \
poetry run pdp-station-api
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
