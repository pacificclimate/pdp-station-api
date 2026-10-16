Station listings
================

Open ``[base_url]/`` to browse published observation networks.
Choose a network to see its station catalog at ``[base_url]/networks/{network}``.
Each station links to an OPeNDAP HTML form where you can inspect the dataset
and construct a download request.

For example, an EC station has these URLs (see the :ref:`base URL note <base-url>`):

.. code-block:: text

   [base_url]/networks/EC
   [base_url]/dap/raw/EC/1010066.html
   [base_url]/dap/climo/EC/1010066.html

``raw`` selects observations; ``climo`` selects climatology data where available.
Availability depends on the network and station in the deployed database.

Station identifiers
-------------------

The public routes identify a station by its network name and the identifier
assigned by that network (``native_id``). Preserve identifiers as strings,
including any leading zeros. URL-encode each path component when constructing
URLs in a script.

The API also accepts internal numeric database identifiers at
``[base_url]/dap/stations/{station_id}.{format}`` and
``[base_url]/dap/climatologies/{station_id}.{format}``. These are a separate identifier
system: a numeric network-assigned identifier is not necessarily a database ID.

Inspect metadata
----------------

Replace ``.html`` with ``.dds`` to inspect the dataset structure and variable
names, or ``.das`` to inspect attributes such as units, descriptions, station
location, and network contact information.

.. code-block:: console

   curl --fail '[base_url]/dap/raw/EC/1010066.dds'
   curl --fail '[base_url]/dap/raw/EC/1010066.das'

Variable names and measurement methods can differ between networks. Inspect the
metadata before applying examples to another station.
