from webob import Request

from pcds_dap.application import StationDataset, StationDatasetService
from pcds_dap.dap import StationDapApplication


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
        yield ("2025-01-02T03:04:00", 12.5)


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
