from datetime import datetime
from io import BytesIO
import csv
import logging
from zipfile import ZipFile

import h5netcdf
import openpyxl
import pytest
from starlette.testclient import TestClient

from pdp_station.application import (
    AggregateSelection,
    AggregateStation,
    NetworkSummary,
    StationDataset,
    StationDatasetService,
)
from pdp_station.aggregate import (
    parse_selection,
    prepare_archive,
    request_fingerprint,
    stream_archive,
)
from pdp_station.web import create_app


class FakeAggregateRepository:
    def __init__(self, fail_rows=False):
        self.last_selection = None
        self.describe_calls = 0
        self.rows_calls = 0
        self.fail_rows = fail_rows

    def networks(self):
        return (NetworkSummary("FLNRO-WMB"), NetworkSummary("BC-TS"))

    def network(self, name):
        return next(
            (network for network in self.networks() if network.name == name), None
        )

    def stations(self, network):
        return ()

    def aggregate_stations(self, selection):
        self.last_selection = selection
        stations = (
            AggregateStation(41, "BC-TS", "A001"),
            AggregateStation(42, "FLNRO-WMB", "1002"),
        )
        if selection.networks:
            stations = tuple(
                station for station in stations if station.network in selection.networks
            )
        return stations

    def published_station_id(self, station_id):
        return station_id if station_id in {41, 42} else None

    def describe(self, station_id, climatology=False):
        self.describe_calls += 1
        network = "BC-TS" if station_id == 41 else "FLNRO-WMB"
        return StationDataset(
            station_id,
            climatology,
            ("obs_time", "temperature"),
            global_attributes={"network": network},
            time_attributes={"axis": "T"},
            variable_attributes={
                "temperature": {
                    "standard_name": "air_temperature",
                    "cell_methods": "time: point",
                    "units": "celsius",
                }
            },
        )

    def rows(self, dataset):
        self.rows_calls += 1
        if self.fail_rows:
            raise RuntimeError("observation query failed")
        rows = (
            (datetime(2019, 12, 31, 12), 1.0),
            (datetime(2020, 1, 15, 12), 2.0),
            (datetime(2021, 1, 1, 12), 3.0),
        )
        for row in rows:
            if dataset.from_date and row[0].date() < dataset.from_date:
                continue
            if dataset.to_date and row[0].date() > dataset.to_date:
                continue
            yield row


def _zip(response):
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    return ZipFile(BytesIO(response.content))


def test_query_json_returns_station_netcdf_and_variable_index():
    repository = FakeAggregateRepository()
    client = TestClient(create_app(repository=repository))

    response = client.request(
        "QUERY",
        "/agg",
        json={"networks": ["FLNRO-WMB"], "format": "nc"},
    )

    with _zip(response) as archive:
        assert archive.namelist() == [
            "FLNRO-WMB/1002.nc",
            "FLNRO-WMB/variables.csv",
        ]
        with h5netcdf.File(BytesIO(archive.read("FLNRO-WMB/1002.nc")), "r") as dataset:
            assert dataset.attrs["network"] == "FLNRO-WMB"
            assert list(dataset.variables["temperature"][:]) == [1.0, 2.0, 3.0]
        variable_index = archive.read("FLNRO-WMB/variables.csv").decode()
        assert "variable,standard_name,cell_method,unit" in variable_index
        assert "temperature,air_temperature,time: point,celsius" in variable_index
    assert repository.last_selection.networks == ("FLNRO-WMB",)


def test_legacy_get_contract_selects_networks_and_ascii_format():
    repository = FakeAggregateRepository()
    client = TestClient(create_app(repository=repository))

    response = client.get(
        "/agg/",
        params={"network-name": "BC-TS,FLNRO-WMB", "data-format": "ascii"},
    )

    with _zip(response) as archive:
        assert archive.namelist() == [
            "BC-TS/A001.ascii",
            "FLNRO-WMB/1002.ascii",
            "BC-TS/variables.csv",
            "FLNRO-WMB/variables.csv",
        ]


def test_legacy_csv_format_returns_csv_with_iso_times_and_missing_values():
    client = TestClient(create_app(repository=FakeAggregateRepository()))

    response = client.get(
        "/agg/",
        params={"network-name": "FLNRO-WMB", "data-format": "csv"},
    )

    with _zip(response) as archive:
        assert archive.namelist() == [
            "FLNRO-WMB/1002.csv",
            "FLNRO-WMB/variables.csv",
        ]
        rows = list(
            csv.reader(archive.read("FLNRO-WMB/1002.csv").decode().splitlines())
        )
        assert rows == [
            ["obs_time", "temperature"],
            ["2019-12-31T12:00:00", "1.0"],
            ["2020-01-15T12:00:00", "2.0"],
            ["2021-01-01T12:00:00", "3.0"],
        ]


def test_post_form_contract_clips_station_rows_to_dates():
    repository = FakeAggregateRepository()
    client = TestClient(create_app(repository=repository))

    response = client.post(
        "/agg",
        data={
            "network-name": "FLNRO-WMB",
            "from-date": "2020/01/01",
            "to-date": "2020/12/31",
            "cliptodate": "cliptodate",
            "data-format": "ascii",
        },
    )

    with _zip(response) as archive:
        data = archive.read("FLNRO-WMB/1002.ascii").decode()
    assert "2020-01-15T12:00:00" in data
    assert "2019-12-31T12:00:00" not in data
    assert "2021-01-01T12:00:00" not in data


def test_invalid_format_is_rejected_before_download_starts():
    client = TestClient(create_app(repository=FakeAggregateRepository()))

    response = client.request("QUERY", "/agg", json={"format": "unsupported"})

    assert response.status_code == 422
    assert "format must be one of" in response.json()["error"]


def test_invalid_polygon_is_rejected_before_database_query():
    repository = FakeAggregateRepository()
    client = TestClient(create_app(repository=repository))

    response = client.request(
        "QUERY", "/agg", json={"format": "nc", "polygon": "not geometry"}
    )

    assert response.status_code == 422
    assert response.json() == {"error": "polygon is not valid WKT"}
    assert repository.last_selection is None


def test_aggregate_options_advertises_query_content_types():
    client = TestClient(create_app(repository=FakeAggregateRepository()))

    response = client.options("/agg")

    assert response.status_code == 204
    assert response.headers["allow"] == "GET, POST, QUERY, OPTIONS"
    assert "application/json" in response.headers["accept-query"]


def test_metadata_is_preflighted_but_rows_start_after_zip_signature():
    repository = FakeAggregateRepository()
    service = StationDatasetService(repository)
    prepared = prepare_archive(
        service,
        AggregateSelection(networks=("FLNRO-WMB",), data_format="ascii"),
    )

    assert repository.describe_calls == 1
    assert repository.rows_calls == 0

    stream = stream_archive(service, prepared, spool_max_size=1024)
    assert next(stream) == b"PK"
    assert repository.rows_calls == 0
    next(stream)  # Remaining local-file header bytes.
    assert repository.rows_calls == 0
    list(stream)
    assert repository.rows_calls == 1


def test_request_fingerprint_uses_normalized_parameters():
    json_selection = parse_selection(
        {
            "format": "nc",
            "networks": ["FLNRO-WMB", "BC-TS"],
            "from_date": "2020-01-01",
        }
    )
    legacy_selection = parse_selection(
        {
            "from-date": "2020/01/01",
            "network-name": "FLNRO-WMB,BC-TS",
            "data-format": "nc",
        }
    )

    fingerprint = request_fingerprint(json_selection)
    assert fingerprint == request_fingerprint(legacy_selection)
    assert len(fingerprint) == 16


def test_midstream_error_logs_request_and_station(caplog):
    repository = FakeAggregateRepository(fail_rows=True)
    service = StationDatasetService(repository)
    prepared = prepare_archive(
        service,
        AggregateSelection(networks=("FLNRO-WMB",), data_format="ascii"),
    )

    with caplog.at_level(logging.DEBUG, logger="pdp_station.aggregate"):
        with pytest.raises(RuntimeError, match="observation query failed"):
            list(stream_archive(service, prepared, spool_max_size=1024))

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        f"Aggregate request {prepared.request_id} retrieving station "
        "FLNRO-WMB/1002 (42)" == message
        for message in messages
    )
    error = next(record for record in caplog.records if record.levelno == logging.ERROR)
    assert prepared.request_id in error.getMessage()
    assert "FLNRO-WMB/1002 (42)" in error.getMessage()
    assert error.aggregate_request_id == prepared.request_id
    assert error.station_id == 42
    assert error.exc_info is not None


def test_aggregate_can_use_rustpy_xlsx_engine():
    repository = FakeAggregateRepository()
    service = StationDatasetService(repository)
    prepared = prepare_archive(
        service,
        AggregateSelection(networks=("FLNRO-WMB",), data_format="xlsx"),
    )

    archive = b"".join(
        stream_archive(
            service,
            prepared,
            spool_max_size=1024,
            xlsx_engine="rustpy",
        )
    )

    workbook_data = ZipFile(BytesIO(archive)).read("FLNRO-WMB/1002.xlsx")
    workbook = openpyxl.load_workbook(BytesIO(workbook_data), read_only=True)
    assert workbook["station_observations"]["B2"].value == 1.0
    workbook.close()
