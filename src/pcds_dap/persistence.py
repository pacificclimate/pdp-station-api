"""PyCDS-backed persistence boundary."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pycds.orm.station_queries import query_one_station
from pycds.orm.tables import Network, Station
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .application import StationDataset


class PycdsStationRepository:
    """Build and stream a pivoted query for one station."""

    def __init__(self, sessions: sessionmaker[Session], yield_per: int = 1_000):
        self._sessions = sessions
        self._yield_per = yield_per

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._sessions()
        try:
            yield session
        finally:
            session.close()

    def describe(self, station_id: int, climatology: bool = False) -> StationDataset:
        with self._session() as session:
            statement = query_one_station(session, station_id, climo=climatology)
            columns = tuple(column.key for column in statement.selected_columns)
        return StationDataset(station_id, climatology, columns)

    def published_station_id(self, station_id: int) -> int | None:
        statement = (
            select(Station.id)
            .join(Network, Station.network_id == Network.id)
            .where(
                Station.id == station_id,
                Network.publish.is_(True),
                Station.publish.is_(True),
            )
        )
        with self._session() as session:
            return session.scalar(statement)

    def station_id(self, network: str, native_id: str) -> int | None:
        statement = (
            select(Station.id)
            .join(Network, Station.network_id == Network.id)
            .where(
                Network.name == network,
                Station.native_id == native_id,
                Network.publish.is_(True),
                Station.publish.is_(True),
            )
            .order_by(Station.id)
            .limit(1)
        )
        with self._session() as session:
            return session.scalar(statement)

    def rows(self, dataset: StationDataset) -> Iterator[tuple[Any, ...]]:
        # The generator owns the session for the entire response iteration.
        with self._session() as session:
            statement = query_one_station(
                session, dataset.station_id, climo=dataset.climatology
            ).execution_options(stream_results=True, yield_per=self._yield_per)
            for row in session.execute(statement):
                yield tuple(row)


def create_repository(database_url: str, yield_per: int = 1_000):
    engine: Engine = create_engine(database_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    return PycdsStationRepository(sessions, yield_per=yield_per)
