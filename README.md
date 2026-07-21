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
