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

Large requests
--------------

Deployments can limit the number of stations in a request. Narrow the station
selection if your request exceeds that limit. Check that the ZIP archive opens
successfully before using it: a failure after streaming starts can interrupt
the download rather than return an HTTP error page.
