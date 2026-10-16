Migrating old PDP URLs
======================

Historical station URLs used ``.rsql`` for observations and ``.csql`` for
climatologies. The API accepts these through its compatibility routes and
redirects to the current dataset URLs. For example:

.. code-block:: text

   [base_url]/lister/raw/EC/1010066.rsql.csv
       -> [base_url]/dap/stations/{resolved_station_id}.csv

Both ``[base_url]/lister`` and ``[base_url]/pcds/lister`` prefixes are accepted. Extensionless station
pages redirect to the public ``[base_url]/dap/raw/{network}/{native_id}.html`` forms.
Legacy ``.xls`` requests redirect to ``.xlsx``. ``[base_url]/pcds/agg`` redirects to
``[base_url]/agg``. Redirects preserve query strings and use HTTP 307, preserving the
method and body.

Use ``curl --location`` or enable redirect handling in your client. For new
scripts, prefer the current routes described in :doc:`programmatic`.

Public deployment prefixes remain part of ``[base_url]``. Older public links
used the separate ``/data/pcds`` mount. Supporting those links requires the
proxy to serve both the old lister route and its canonical destination beneath
that mount. Compatibility depends on that proxy routing as well as the API.
