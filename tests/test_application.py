from datetime import datetime

import pytest

from pcds_dap.application import (
    StationDataset,
    StationDatasetService,
    StationNotFoundError,
)
from pcds_dap.dap import build_dataset


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


def test_service_describes_station_dataset():
    service = StationDatasetService(FakeRepository())

    query = service.station(42)

    assert query.columns == ("obs_time", "temperature")


def test_service_rejects_unpublished_or_unknown_numeric_station():
    service = StationDatasetService(FakeRepository())

    with pytest.raises(StationNotFoundError):
        service.station(99)


def test_service_resolves_public_station_identifier():
    service = StationDatasetService(FakeRepository())

    query = service.public_station("FLNRO-WMB", "1002")

    assert query.station_id == 42


def test_service_rejects_unknown_public_station_identifier():
    service = StationDatasetService(FakeRepository())

    with pytest.raises(StationNotFoundError):
        service.public_station("unknown", "station")


def test_dataset_rows_are_lazy_and_reiterable():
    repository = FakeRepository()
    query = repository.describe(42)
    dataset = build_dataset(query, lambda: repository.rows(query))

    first = list(dataset["station_observations"].iterdata())
    second = list(dataset["station_observations"].iterdata())

    assert first == second
    assert first == [("2025-01-02T03:04:00", 12.5)]
