from datetime import datetime, timezone

from pcds_dap.persistence import DEFAULT_CONTACT, PycdsStationRepository


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
        "Generated 2026-07-21T12:34:56+00:00 by pcds-dap 1.2.3 from database metnorth"
    )
