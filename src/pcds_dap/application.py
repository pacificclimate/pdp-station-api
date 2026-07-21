"""Station dataset use cases."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StationDataset:
    station_id: int
    climatology: bool
    columns: tuple[str, ...]


class StationNotFoundError(LookupError):
    """No published station matches a requested identifier."""


class StationRepository(Protocol):
    def published_station_id(self, station_id: int) -> int | None: ...

    def station_id(self, network: str, native_id: str) -> int | None: ...

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
        published_station_id = self.repository.published_station_id(station_id)
        if published_station_id is None:
            raise StationNotFoundError(f"Station {station_id} was not found")
        return self.repository.describe(published_station_id, climatology=climatology)

    def public_station(
        self, network: str, native_id: str, climatology: bool = False
    ) -> StationDataset:
        station_id = self.repository.station_id(network, native_id)
        if station_id is None:
            raise StationNotFoundError(f"Station {network}/{native_id} was not found")
        return self.station(station_id, climatology=climatology)
