Programmatic access
===================

Download one station
--------------------

Replace the HTML form's extension with a download format:

.. list-table:: Response formats
   :header-rows: 1
   :widths: 25 75

   * - Extension
     - Response
   * - ``csv``
     - Comma-separated values
   * - ``ascii`` or ``asc``
     - OPeNDAP text response
   * - ``xlsx``
     - Excel workbook
   * - ``nc``
     - NetCDF4 file with metadata
   * - ``dds`` / ``das``
     - Dataset structure / attributes
   * - ``dods``
     - DAP2 binary response for OPeNDAP clients
   * - ``html``
     - Interactive dataset form
   * - ``ver``
     - DAP server version response

.. code-block:: console

   curl --fail --location \
     '[base_url]/dap/raw/EC/1010066.csv' \
     --output station.csv

Use ``[base_url]/dap/climo/`` instead of ``[base_url]/dap/raw/`` for climatologies. The ``.ver``
response is protocol/server information, not the documentation release label.

Select variables and observations
---------------------------------

OPeNDAP constraint expressions follow ``?``. A comma-separated list selects
columns; expressions separated by ``&`` filter observation rows. Without a
column selection, all available variables are returned.

For a dataset exposing ``air_temperature`` and ``time``, this selects those
columns and observations below freezing:

.. code-block:: text

   [base_url]/dap/raw/EC/1010066.csv?station_observations.air_temperature,station_observations.time&station_observations.air_temperature<0

Check the actual variable names and temperature units in ``.dds`` and ``.das``
first. These names are examples, not a guarantee for every station.

Time comparisons use quoted ISO date/time strings. To select observations
within 2020, use an inclusive lower bound and an exclusive upper bound:

.. code-block:: text

   station_observations.time>="2020-01-01T00:00:00"&station_observations.time<"2021-01-01T00:00:00"

Encode the constraint expression when constructing a URL programmatically.
The following example uses only Python's standard library:

.. code-block:: python

   from shutil import copyfileobj
   from urllib.parse import quote
   from urllib.request import urlopen

   base_url = "[base_url]"  # Replace with the URL in the opening note.
   network, native_id = "EC", "1010066"
   constraint = (
       "station_observations.air_temperature,station_observations.time"
       '&station_observations.time>="2020-01-01T00:00:00"'
       '&station_observations.time<"2021-01-01T00:00:00"'
       "&station_observations.air_temperature<0"
   )
   path = f"/dap/raw/{quote(network, safe='')}/{quote(native_id, safe='')}.csv"
   url = base_url.rstrip("/") + path + "?" + quote(constraint, safe="")
   with urlopen(url, timeout=120) as response, open("station.csv", "wb") as output:
       copyfileobj(response, output)

Encode the expression after constructing its syntax; do not encode the entire
URL, including its ``?`` separator. A request can legitimately return no rows
when no observations satisfy the constraints.

Automate larger downloads
-------------------------

Use :doc:`aggregate` to retrieve multiple stations as one ZIP archive. For
individual station requests, start with a small date range, verify the result,
and then expand the request. Save responses directly to disk rather than
holding large downloads in memory.
