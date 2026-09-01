from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from pdp_station.application import AggregateSelection
from pdp_station.persistence import (
    DEFAULT_CONTACT,
    REQUIRED_RELATIONS,
    PycdsStationRepository,
)


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
    def __init__(self, rows=()):
        self.statement = None
        self.closed = False
        self.rows = rows

    def execute(self, statement):
        self.statement = statement
        return self

    def __iter__(self):
        return iter(self.rows)

    def scalar_one(self):
        return 1

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class RecordingSessions:
    def __init__(self, rows=()):
        self.session = RecordingSession(rows)

    def __call__(self):
        return self.session


def readiness_rows(**overrides):
    rows = []
    for relation in REQUIRED_RELATIONS:
        values = dict(
            relation_name=relation,
            exists=True,
            has_schema_usage=True,
            has_select=True,
        )
        values.update(overrides)
        rows.append(SimpleNamespace(**values))
    return tuple(rows)


def test_readiness_checks_required_relations_and_closes_session():
    sessions = RecordingSessions(readiness_rows())
    repository = PycdsStationRepository(sessions)

    checks = repository.ready()

    sql = str(sessions.session.statement.compile(dialect=postgresql.dialect()))
    assert "to_regclass" not in sql
    assert "pg_catalog.pg_namespace" in sql
    assert "pg_catalog.pg_class" in sql
    assert "has_schema_privilege" in sql
    assert "has_table_privilege" in sql
    assert all(check.ready for check in checks)
    assert sessions.session.closed


def test_readiness_returns_relation_and_privilege_failures():
    sessions = RecordingSessions(readiness_rows(has_select=False))
    repository = PycdsStationRepository(sessions)

    checks = repository.ready()

    assert all(check.exists for check in checks)
    assert all(check.schema_usage for check in checks)
    assert not any(check.select for check in checks)
    assert not any(check.ready for check in checks)


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
    assert "AS TEXT[]" in sql
    assert "&& ARRAY[" in sql
    assert "ST_Intersects" in sql
    assert "unique_variable_tags @> ARRAY[" in sql
    assert "meta_network.publish IS true" in sql
    assert "meta_station.publish IS true" in sql
