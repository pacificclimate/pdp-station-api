from webob import Request

from pcds_dap.application import StationDataset, StationDatasetService
from pcds_dap.dap import StationDapApplication


class FakeRepository:
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


def test_unknown_path_is_not_found():
    app = StationDapApplication(StationDatasetService(FakeRepository()))

    response = Request.blank("/not-a-station.dds").get_response(app)

    assert response.status_code == 404
