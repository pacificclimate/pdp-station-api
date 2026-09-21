# Station data URLs

This service replaces PDP's `pcds-only` station-data backend. The examples
below are application-relative so they remain valid behind different public
proxy prefixes.

## Browse stations

`/` lists the published observation networks. `/networks/{network}` lists the
published stations in one network and links each station to its DAP HTML form.
For example:

```text
/networks/EC
/dap/raw/EC/1010066.html
```

The equivalent climatology form is:

```text
/dap/climo/EC/1010066.html
```

## Download a station dataset

Replace `html` with a response format to download data directly:

```text
/dap/raw/{network}/{native_id}.csv
/dap/raw/{network}/{native_id}.ascii
/dap/raw/{network}/{native_id}.xlsx
/dap/raw/{network}/{native_id}.nc
/dap/raw/{network}/{native_id}.dds
/dap/raw/{network}/{native_id}.das
/dap/raw/{network}/{native_id}.dods
```

Use `/dap/climo/...` instead of `/dap/raw/...` for climatology data. Numeric
PyCDS station IDs are also available through the lower-level
`/dap/stations/{station_id}.{response}` and
`/dap/climatologies/{station_id}.{response}` routes.

Pydap constraint expressions follow the `?` in the URL. For example, this
requests only air temperature and time from a raw station dataset:

```text
/dap/raw/EC/1010066.csv?station_observations.air_temperature,station_observations.time
```

Variable names can be inspected in the dataset's `.dds` response or selected
with the HTML form. URL-encode constraint expressions when constructing a URL
programmatically.

## Aggregate downloads

`/agg` selects multiple stations by network, variable, frequency, date, and
polygon, then streams a ZIP archive. The current JSON `QUERY` interface and
the legacy query-string and form field names are documented in the
[README](../README.md#aggregate-downloads).

## Compatibility with PDP links

Historical PDP documentation showed URLs such as:

```text
/data/pcds/lister/raw/EC/1010066.rsql.csv
```

That full prefix belonged to the original PDP portal. In a standalone
`pcds-only` deployment the application route starts at `/lister`; the reverse
proxy supplies whatever public prefix is configured. This service redirects
the lister form to the canonical route:

```text
/lister/raw/EC/1010066.rsql.csv
    -> /dap/raw/EC/1010066.csv
```

The same compatibility applies to `.csql` climatology URLs, station and
network catalog pages, and `/pcds/agg`. Redirects use HTTP 307 and preserve the
query string. Legacy `.xls` responses redirect to `.xlsx`.
