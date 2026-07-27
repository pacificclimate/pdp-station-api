"""Station dataset use cases."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class StationDataset:
    station_id: int
    climatology: bool
    columns: tuple[str, ...]
    global_attributes: Mapping[str, Any] = field(default_factory=dict)
    time_attributes: Mapping[str, Any] = field(default_factory=dict)
    variable_attributes: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    from_date: date | None = None
    to_date: date | None = None


@dataclass(frozen=True)
class NetworkSummary:
    name: str
    display_name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class StationSummary:
    station_id: int
    native_id: str
    name: str | None = None


@dataclass(frozen=True)
class AggregateSelection:
    networks: tuple[str, ...] = ()
    variables: tuple[str, ...] = ()
    frequencies: tuple[str, ...] = ()
    from_date: date | None = None
    to_date: date | None = None
    polygon: str | None = None
    only_with_climatology: bool = False
    climatology: bool = False
    clip_dates: bool = False
    data_format: str = "nc"


@dataclass(frozen=True)
class AggregateStation:
    station_id: int
    network: str
    native_id: str


class StationNotFoundError(LookupError):
    """No published station matches a requested identifier."""


class StationRepository(Protocol):
    def networks(self) -> tuple[NetworkSummary, ...]: ...

    def network(self, name: str) -> NetworkSummary | None: ...

    def stations(self, network: str) -> tuple[StationSummary, ...]: ...

    def published_station_id(self, station_id: int) -> int | None: ...

    def station_id(self, network: str, native_id: str) -> int | None: ...

    def describe(
        self, station_id: int, climatology: bool = False
    ) -> StationDataset: ...

    def rows(self, dataset: StationDataset) -> Any: ...

    def aggregate_stations(
        self, selection: AggregateSelection
    ) -> tuple[AggregateStation, ...]: ...


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

    def networks(self) -> tuple[NetworkSummary, ...]:
        return tuple(
            sorted(
                self.repository.networks(),
                key=lambda network: (
                    (network.display_name or network.name).casefold(),
                    network.name.casefold(),
                ),
            )
        )

    def network_stations(
        self, network: str
    ) -> tuple[NetworkSummary, tuple[StationSummary, ...]]:
        summary = self.repository.network(network)
        if summary is None:
            raise StationNotFoundError(f"Network {network} was not found")
        stations = sorted(
            self.repository.stations(network),
            key=lambda station: (
                station.native_id.casefold(),
                (station.name or "").casefold(),
                station.station_id,
            ),
        )
        return summary, tuple(stations)
