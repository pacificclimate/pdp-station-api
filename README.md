# pcds-dap

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
PCDS_DSN=postgresql+psycopg2://user:password@host/database poetry run pcds-dap
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
`PCDS_DAP_SPOOL_MAX_SIZE`. Set it to `0` to roll over immediately. Excel files
are limited to 1,048,575 observations plus their header row.

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
history records the UTC generation time, `pcds-dap` package version, and source
database.
