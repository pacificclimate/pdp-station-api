from datetime import datetime

import numpy as np
import h5netcdf
import openpyxl
from webob import Request

from pcds_dap.application import StationDataset, StationDatasetService
from pcds_dap.dap import StationDapApplication, build_dataset
from pcds_dap.responses import NetCDFResponse, XLSXResponse, _spool


class FakeRepository:
    def published_station_id(self, station_id):
        return station_id if station_id == 42 else None

    def station_id(self, network, native_id):
        if (network, native_id) == ("FLNRO-WMB", "1002"):
            return 42
        return None

    def describe(self, station_id, climatology=False):
        return StationDataset(station_id, climatology, ("obs_time", "temperature"))

    def rows(self, query):
        yield (datetime(2025, 1, 2, 3, 4), 12.5)


def test_dds_describes_station_sequence():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank("/stations/42.dds").get_response(app)

    assert response.status_code == 200
    assert "Sequence" in response.text
    assert "String obs_time" in response.text
    assert "Float64 temperature" in response.text


def test_public_identifier_dds_matches_numeric_station_dds():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    numeric = Request.blank("/stations/42.dds").get_response(app)
    public = Request.blank("/raw/FLNRO-WMB/1002.dds").get_response(app)

    assert public.status_code == 200
    assert public.text == numeric.text


def test_dap_accepts_mount_prefix_retained_by_wsgi_bridge():
    app = StationDapApplication(
        StationDatasetService(FakeRepository()), mount_path="/dap"
    )

    response = Request.blank("/dap/raw/FLNRO-WMB/1002.dds").get_response(app)

    assert response.status_code == 200
    assert "station_42" in response.text


def test_public_climatology_route_resolves_station():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank("/climo/FLNRO-WMB/1002.dds").get_response(app)

    assert response.status_code == 200
    assert "station_42" in response.text


def test_unknown_public_station_is_not_found():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank("/raw/unknown/station.dds").get_response(app)

    assert response.status_code == 404


def test_unpublished_or_unknown_numeric_station_is_not_found():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank("/stations/99.dds").get_response(app)

    assert response.status_code == 404


def test_unknown_path_is_not_found():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank("/not-a-station.dds").get_response(app)

    assert response.status_code == 404


def test_das_contains_global_time_and_variable_metadata():
    description = StationDataset(
        42,
        False,
        ("obs_time", "temperature"),
        global_attributes={
            "network": "FLNRO-WMB",
            "contact": "pcic.support@uvic.ca",
            "longitude": -123.1,
            "latitude": 49.2,
        },
        time_attributes={
            "axis": "T",
            "standard_name": "time",
            "long_name": "observation time",
        },
        variable_attributes={
            "temperature": {
                "display_name": "Temperature (Point)",
                "standard_name": "air_temperature",
                "units": "celsius",
                "cell_methods": "time: point",
            }
        },
    )
    dataset = build_dataset(description, lambda: iter(()))
    app = StationDapApplication(StationDatasetService(FakeRepository()))
    app.service.repository.describe = lambda station_id, climatology=False: description

    response = Request.blank("/stations/42.das").get_response(app)

    assert response.status_code == 200
    assert "NC_GLOBAL" in response.text
    assert 'String contact "pcic.support@uvic.ca"' in response.text
    assert "Float64 longitude -123.1" in response.text
    assert 'String axis "T"' in response.text
    assert 'String standard_name "air_temperature"' in response.text
    assert 'String cell_methods "time: point"' in response.text
    assert dataset["station_observations"]["obs_time"].dtype == "<U0"


def test_rows_serialize_iso_time_and_missing_observations():
    description = StationDataset(42, False, ("obs_time", "temperature"))
    dataset = build_dataset(
        description,
        lambda: iter(((datetime(1970, 1, 2), None),)),
    )

    rows = list(dataset["station_observations"].iterdata())

    assert rows[0][0] == "1970-01-02T00:00:00"
    assert np.isnan(rows[0][1])


def test_dods_encodes_iso_time_strings():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank("/stations/42.dods").get_response(app)

    assert response.status_code == 200
    assert b"Data:\n" in response.body


def test_xlsx_response_contains_data_and_metadata(tmp_path):
    description = StationDataset(
        42,
        False,
        ("obs_time", "temperature"),
        global_attributes={"network": "FLNRO-WMB"},
        variable_attributes={"temperature": {"units": "celsius"}},
    )
    dataset = build_dataset(
        description,
        lambda: iter(((datetime(2025, 1, 2, 3, 4), 12.5),)),
    )
    path = tmp_path / "station.xlsx"
    path.write_bytes(b"".join(XLSXResponse(dataset)))

    workbook = openpyxl.load_workbook(path, read_only=True)
    assert workbook["Global attributes"]["A2"].value == "network"
    assert workbook["station_observations"]["A2"].value == "2025-01-02T03:04:00"
    assert workbook["station_observations"]["B2"].value == 12.5
    assert list(workbook.sheetnames) == [
        "Global attributes",
        "Variable attributes",
        "station_observations",
    ]


def test_netcdf_response_contains_data_and_metadata(tmp_path):
    description = StationDataset(
        42,
        False,
        ("obs_time", "temperature"),
        global_attributes={"network": "FLNRO-WMB"},
        time_attributes={"axis": "T"},
        variable_attributes={"temperature": {"units": "celsius"}},
    )
    dataset = build_dataset(
        description,
        lambda: iter(((datetime(2025, 1, 2, 3, 4), 12.5),)),
    )
    path = tmp_path / "station.nc"
    path.write_bytes(b"".join(NetCDFResponse(dataset)))

    with h5netcdf.File(path, "r") as result:
        assert result.attrs["network"] == "FLNRO-WMB"
        assert result.variables["obs_time"][0] == b"2025-01-02T03:04:00"
        assert result.variables["obs_time"].attrs["axis"] == "T"
        assert result.variables["temperature"][0] == 12.5
        assert result.variables["temperature"].attrs["units"] == "celsius"


def test_download_routes_are_recognized():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    assert Request.blank("/stations/42.xlsx").get_response(app).status_code == 200
    assert Request.blank("/stations/42.nc").get_response(app).status_code == 200


def test_netcdf_download_honors_dap_projection(tmp_path):
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank(
        "/stations/42.nc?station_observations.temperature"
    ).get_response(app)
    path = tmp_path / "projected.nc"
    path.write_bytes(response.body)

    assert response.status_code == 200
    with h5netcdf.File(path, "r") as result:
        assert list(result.variables) == ["temperature"]
        assert result.variables["temperature"][0] == 12.5


def test_zero_spool_threshold_rolls_over_immediately():
    dataset = build_dataset(StationDataset(42, False, ()), lambda: iter(()))
    dataset._pcds_spool_max_size = 0

    stream = _spool(dataset)
    try:
        assert stream._rolled
    finally:
        stream.close()
