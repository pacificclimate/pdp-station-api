# News / Release Notes

<!--
Add new releases above older releases using this structure:

## X.Y.Z

*Release Date: YYYY-Mon-DD*

Briefly summarize the release, followed by a list of its notable changes.
-->

## 0.1.1

*Release Date: 2026-Aug-26*

Pin PyCDS version dependency

## 0.1.0

*Release Date: 2026-Aug-26*

Initial release of `pdp-station-api`, a streaming DAP2 service for PCIC station
observations and a replacement for the station-data portion of PDP's
`pcds-only` backend.

- Serve raw observations and climatologies through numeric station-ID and
  network/native-ID DAP routes.
- Provide DDS, DAS, DODS, ASCII, CSV, XLSX, and NetCDF4 station downloads.
- Provide aggregate ZIP downloads using JSON `QUERY` and `POST` requests, with
  compatibility for PDP's legacy `GET` query-string interface.
- Stream database results and aggregate ZIP members to bound application memory
  use, while spooling formats that require finalization.
- Include an HTML network and station catalog with compatible Pydap breadcrumb
  redirects.
- Provide PostgreSQL-aware readiness checks for required relations, schema
  access, and effective read privileges.
- Publish a production container image with automated tests for Python 3.12 and
  3.13.
