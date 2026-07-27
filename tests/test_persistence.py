from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from pdp_station.application import AggregateSelection
from pdp_station.persistence import DEFAULT_CONTACT, PycdsStationRepository


def test_contact_includes_name_and_email_when_available():
    assert (
        PycdsStationRepository._contact("Ada Lovelace", "ada@example.org")
        == "Ada Lovelace <ada@example.org>"
    )


def test_contact_uses_email_without_name():
    assert (
        PycdsStationRepository._contact(None, "observations@example.org")
        == "observations@example.org"
    )


def test_contact_falls_back_when_email_is_missing():
    assert PycdsStationRepository._contact("No Email", None) == DEFAULT_CONTACT


def test_generation_history_contains_date_version_and_database():
    history = PycdsStationRepository._generation_history(
        "metnorth",
        generated_at=datetime(2026, 7, 21, 12, 34, 56, tzinfo=timezone.utc),
        package_version="1.2.3",
    )

    assert history == (
        "Generated 2026-07-21T12:34:56+00:00 by pdp-station-api 1.2.3 "
        "from database metnorth"
    )


class RecordingSession:
    def __init__(self):
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return ()

    def close(self):
        pass


class RecordingSessions:
    def __init__(self):
        self.session = RecordingSession()

    def __call__(self):
        return self.session


def test_aggregate_station_query_uses_postgresql_filter_operators():
    sessions = RecordingSessions()
    repository = PycdsStationRepository(sessions)
    selection = AggregateSelection(
        networks=("FLNRO-WMB",),
        variables=("air_temperature_time: point",),
        frequencies=("1-hourly",),
        polygon="POLYGON ((-123 49, -122 49, -122 50, -123 49))",
        only_with_climatology=True,
    )

    repository.aggregate_stations(selection)

    sql = str(sessions.session.statement.compile(dialect=postgresql.dialect()))
    assert "JOIN crmp.meta_station" in sql
    assert "JOIN crmp.meta_network" in sql
    assert "regexp_split_to_array" in sql
    assert "&& ARRAY[" in sql
    assert "ST_Intersects" in sql
    assert "unique_variable_tags @> ARRAY[" in sql
    assert "meta_network.publish IS true" in sql
    assert "meta_station.publish IS true" in sql
