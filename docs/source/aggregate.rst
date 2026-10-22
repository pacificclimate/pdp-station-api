Multiple-station downloads
==========================

``[base_url]/agg`` returns a ZIP archive containing one file per selected station,
organized by network, with a ``variables.csv`` description file in each network
folder. Send JSON with HTTP ``QUERY``; ``POST`` accepts the same body when your
client or proxy does not support ``QUERY``.

.. code-block:: console

   curl --fail --location -X QUERY '[base_url]/agg' \
     -H 'Content-Type: application/json' \
     --data '{
       "networks": ["FLNRO-WMB", "BC-TS"],
       "from_date": "2020-01-01",
       "to_date": "2020-12-31",
       "polygon": "POLYGON ((-123.60 49.41, -123.60 49.45, -123.54 49.45, -123.54 49.41, -123.60 49.41))",
       "clip_dates": true,
       "format": "nc"
     }' --output stations.zip

Selection options
-----------------

.. list-table:: JSON fields
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Meaning
   * - ``station_ids``
     - Optional non-empty list of positive database station IDs, not native or history IDs.
   * - ``networks``
     - List of observation network names.
   * - ``variables``
     - List of variable names used to select stations.
   * - ``frequencies``
     - List of observation frequencies used to select stations.
   * - ``from_date``, ``to_date``
     - Date bounds in ``YYYY-MM-DD`` format, used to select stations by coverage.
   * - ``polygon``
     - WKT Polygon or MultiPolygon, with longitude then latitude coordinates.
   * - ``clip_dates``
     - Also restrict downloaded observations to the date bounds (default false).
   * - ``climatology``
     - Download climatologies instead of raw observations (default false).
   * - ``only_with_climatology``
     - Select only stations with climatology data (default false).
   * - ``format``
     - ``nc`` (default), ``csv``, ``xlsx``, ``ascii``, or ``asc``.

Date coverage can overlap a requested range even when a station has gaps within
that range. Date clipping includes both the start and end dates.

.. important::

   Variable and frequency filters select stations; they do not remove columns
   from the downloaded station files. Use a single-station OPeNDAP constraint
   to select specific columns. Without ``clip_dates: true``, date selection does
   not clip the downloaded observations.

Selecting stations by ID
-----------------------

For one station or an explicit selection, pass database station IDs. A network
list is not required. For example, using ``POST`` for proxy compatibility:

.. code-block:: console

   curl --fail --location -X POST '[base_url]/agg' \
     -H 'Content-Type: application/json' \
     --data '{"station_ids": [41, 42], "format": "csv"}' \
     --output selected-stations.zip

Legacy GET query strings and form-encoded POST/QUERY bodies accept
``station-ids=41,42``. JSON ``station_ids`` must be an integer list; strings,
booleans, fractional numbers and non-positive integers are not accepted. Duplicate
IDs are removed and ID order does not affect the selection or request fingerprint.
Do not supply both ``station_ids`` and ``station-ids`` in one request.

IDs intersect with all other supplied selection filters. An ID outside a supplied
network or polygon is excluded. Omit those criteria when downloading an explicit
selection independently of them. Publication restrictions always apply, and
unknown or unpublished IDs do not produce station files. If no stations match,
the existing response is HTTP 200 with an empty ZIP, without network indexes.
Omitting the ID parameter preserves existing selection behaviour. Explicit empty
input, null, malformed IDs or conflicting parameter names returns HTTP 422 before
streaming; it never broadens the selection to all stations.

To download climatologies, add ``"climatology": true``. To clip observations,
add ``"from_date": "2020-01-01", "to_date": "2020-12-31", "clip_dates": true``.
Without clipping, dates only affect station selection. All existing file formats
and archive member names remain unchanged.

Large requests
--------------

Deployments can limit the number of stations in a request. Narrow the station
selection if your request exceeds that limit. Check that the ZIP archive opens
successfully before using it: a failure after streaming starts can interrupt
the download rather than return an HTTP error page.
