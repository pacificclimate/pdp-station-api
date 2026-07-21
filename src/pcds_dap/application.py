"""Station dataset use cases."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StationDataset:
    station_id: int
    climatology: bool
    columns: tuple[str, ...]


class StationRepository(Protocol):
    def describe(
        self, station_id: int, climatology: bool = False
    ) -> StationDataset: ...

    def rows(self, dataset: StationDataset) -> Any: ...


class StationDatasetService:
    def __init__(self, repository: StationRepository):
        self.repository = repository

    def station(self, station_id: int, climatology: bool = False) -> StationDataset:
        if station_id <= 0:
            raise ValueError("station_id must be a positive integer")
        return self.repository.describe(station_id, climatology=climatology)
