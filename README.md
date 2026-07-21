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
```

The service deliberately uses numeric PyCDS station IDs. A compatibility
resolver for legacy `network/native_id` URLs belongs in the application layer
and can be added once the required old URL contract is fixed.
