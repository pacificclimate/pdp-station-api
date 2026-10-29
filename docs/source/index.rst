Station Data documentation
==========================

.. _base-url:

.. note::

   As of |today| (the documentation build date, UTC), the base URL is
   https://services.pacificclimate.org/met-data-portal-pcds/api/data.

   Throughout this guide, ``[base_url]`` refers to this address, without a
   trailing slash. Replace ``[base_url]`` with this URL before running an
   example. For another deployment, substitute that deployment's base URL.

Download weather and climate observations from the Provincial Climate Data Set
(PCDS), inspect station metadata, and automate downloads across observation
networks. The API guide describes pdp-station-api version |release|.
The portal guide identifies its own portal version and source revision.

For the interactive map, filters, station table, previews and downloads, see
:doc:`portal/root`.

For API access, start with :doc:`stations` to find a station, then use
:doc:`programmatic` to select variables and observations. For multiple stations, see
:doc:`aggregate`.

For example, ``[base_url]/networks/EC`` opens the EC station catalog.

.. toctree::
   :maxdepth: 2
   :caption: Portal user guide

   portal/root

.. toctree::
   :maxdepth: 2
   :caption: API user guide

   stations
   programmatic
   aggregate
   compatibility
   faq
   contributing

About this guide
----------------

This guide adapts the Station Listings and Advanced/Programmatic Usage sections
of the historical `PCIC Data Portal documentation
<https://github.com/pacificclimate/pdp/tree/pcds-only/doc>`_, together with applicable FAQ
and contribution guidance. The portal user guide is imported from a pinned commit of
``station-data-portal``; its source is maintained alongside the UI. The
former climate coverage portals are outside this guide's scope. The old developer
reference and raster-specific Power user HOWTO do not describe this service.

The displayed version is embedded when the documentation is built. Operators
deploy the documentation image alongside its matching API release and the portal
revision shown in the portal guide; it does not query a running API to discover
its version.
