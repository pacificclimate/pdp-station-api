"""PyCDS-backed persistence boundary."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
from typing import Any

from pycds.orm.native_matviews import VarsPerHistory
from pycds.orm.station_queries import query_one_station
from pycds.orm.tables import Contact, History, Network, Station, Variable
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from .application import StationDataset

DEFAULT_CONTACT = "pcic.support@uvic.ca"
TIME_ATTRIBUTES = {
    "axis": "T",
    "long_name": "observation time",
    "standard_name": "time",
}


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
            global_attributes = self._global_attributes(session, station_id)
            variable_attributes = self._variable_attributes(
                session, station_id, climatology
            )
        return StationDataset(
            station_id,
            climatology,
            columns,
            global_attributes=global_attributes,
            time_attributes=TIME_ATTRIBUTES,
            variable_attributes=variable_attributes,
        )

    def _global_attributes(self, session: Session, station_id: int) -> dict[str, Any]:
        statement = (
            select(
                Station.native_id,
                Network.name.label("network_name"),
                Contact.name.label("contact_name"),
                Contact.email.label("contact_email"),
                History.station_name,
                History.elevation,
                func.ST_X(History.the_geom).label("longitude"),
                func.ST_Y(History.the_geom).label("latitude"),
            )
            .join(Network, Station.network_id == Network.id)
            .outerjoin(Contact, Network.contact_id == Contact.id)
            .outerjoin(History, History.station_id == Station.id)
            .where(Station.id == station_id)
            .order_by(History.sdate.desc().nullslast(), History.id.desc().nullslast())
            .limit(1)
        )
        row = session.execute(statement).one()
        database_name = self._database_name(session)
        attributes: dict[str, Any] = {
            "name": f"{database_name}/{row.network_name}",
            "owner": "PCIC",
            "version": 0.2,
            "contact": self._contact(row.contact_name, row.contact_email),
            "station_id": row.native_id,
            "network": row.network_name,
            "history": self._generation_history(database_name),
        }
        optional = {
            "station_name": row.station_name,
            "elevation": row.elevation,
            "longitude": row.longitude,
            "latitude": row.latitude,
        }
        attributes.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return attributes

    @staticmethod
    def _database_name(session: Session) -> str:
        bind = session.get_bind()
        url = getattr(bind, "url", None)
        if url is None:
            url = bind.engine.url
        return url.database or "database"

    @staticmethod
    def _generation_history(
        database_name: str,
        generated_at: datetime | None = None,
        package_version: str | None = None,
    ) -> str:
        generated_at = generated_at or datetime.now(timezone.utc)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        generated_at = generated_at.astimezone(timezone.utc)
        package_version = package_version or version("pcds-dap")
        timestamp = generated_at.isoformat(timespec="seconds")
        return (
            f"Generated {timestamp} by pcds-dap {package_version} "
            f"from database {database_name}"
        )

    @staticmethod
    def _contact(name: str | None, email: str | None) -> str:
        email = email.strip() if email else ""
        name = name.strip() if name else ""
        if not email:
            return DEFAULT_CONTACT
        return f"{name} <{email}>" if name else email

    def _variable_attributes(
        self, session: Session, station_id: int, climatology: bool
    ) -> dict[str, dict[str, Any]]:
        is_climatological = Variable.cell_method.op("~")(r"(within|over)")
        statement = (
            select(
                Variable.name,
                Variable.display_name,
                Variable.description,
                Variable.standard_name,
                Variable.unit,
                Variable.cell_method,
            )
            .select_from(VarsPerHistory)
            .join(History, History.id == VarsPerHistory.history_id)
            .join(Variable, Variable.id == VarsPerHistory.vars_id)
            .where(
                History.station_id == station_id,
                is_climatological if climatology else ~is_climatological,
            )
            .distinct()
            .order_by(Variable.name)
        )
        attributes = {}
        for row in session.execute(statement):
            name = str(row.name).lower()
            values = {
                "name": name,
                "display_name": row.display_name,
                "long_name": row.description,
                "standard_name": row.standard_name,
                "units": row.unit,
                "cell_methods": row.cell_method,
                "cell_method": row.cell_method,
                "missing_value": float("nan"),
            }
            attributes[name] = {
                key: value for key, value in values.items() if value is not None
            }
        return attributes

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
