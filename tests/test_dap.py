from datetime import datetime

import numpy as np
from webob import Request

from pcds_dap.application import StationDataset, StationDatasetService
from pcds_dap.dap import StationDapApplication, build_dataset


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
