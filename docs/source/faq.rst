Frequently asked questions
==========================

How do I get help or report a problem?
--------------------------------------

See :doc:`contributing`. Include the request, the result you expected, the result
you received, and the API version shown in this guide.

Why does a download take time?
------------------------------

The service constructs datasets from station observations for each request.
Large time ranges and many stations require more work than small selections.
NetCDF and Excel files must be finalized before their bytes can be sent.
Try one station and a short date range first, then expand your selection.

How do I interpret time values?
-------------------------------

This API exposes times as ISO-8601 strings. Do not apply the historical portal's
recipe that treated every time value as a floating-point number of days since
1970. Inspect the response's metadata and column names before processing it.

Station observations can have gaps and changing measurement frequencies.
Do not assume evenly spaced timestamps or infer a measurement for a missing
timestep.

How do I interpret variables and units?
---------------------------------------

The ``.das`` response and NetCDF attributes describe variables, including units,
standard names, and cell methods where available. Similar display names can
represent different measurements, such as instantaneous temperature and daily
maximum temperature. Check the metadata before combining observations.

Why does my aggregate contain variables or dates I did not select?
------------------------------------------------------------------

Aggregate variable filters select stations, not columns. Date filters select
stations by coverage unless ``clip_dates`` is true. See :doc:`aggregate`.

Which download format should I use?
-----------------------------------

CSV works well for tabular processing; NetCDF includes structured metadata;
XLSX is convenient for spreadsheets. Excel downloads are limited to 1,048,575
observation rows plus a header. Reduce the date range or choose another format
for larger datasets.

Why is my download empty or incomplete?
---------------------------------------

A valid selection can contain no observations, particularly within a gap in a
station's record. Check the station and constraints. For an incomplete ZIP,
retry with a smaller selection and report repeatable failures with the request
time and URL. An HTTP success status alone does not guarantee a streamed archive
completed successfully.
