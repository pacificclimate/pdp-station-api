from datetime import datetime

from pcds_dap.application import StationDataset, StationDatasetService
from pcds_dap.dap import build_dataset


class FakeRepository:
    def describe(self, station_id, climatology=False):
        return StationDataset(station_id, climatology, ("obs_time", "temperature"))

    def rows(self, query):
        yield (datetime(2025, 1, 2, 3, 4), 12.5)


def test_service_describes_station_dataset():
    service = StationDatasetService(FakeRepository())

    query = service.station(42)

    assert query.columns == ("obs_time", "temperature")


def test_dataset_rows_are_lazy_and_reiterable():
    repository = FakeRepository()
    query = repository.describe(42)
    dataset = build_dataset(query, lambda: repository.rows(query))

    first = list(dataset["station_observations"].iterdata())
    second = list(dataset["station_observations"].iterdata())

    assert first == second
    assert first == [("2025-01-02T03:04:00", 12.5)]
