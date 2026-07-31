import logging

import pytest

from pdp_station.__main__ import logging_config
from pdp_station.config import Settings, log_level_from_environment


def test_log_level_defaults_to_info(monkeypatch):
    monkeypatch.delenv("PDP_STATION_LOG_LEVEL", raising=False)

    assert log_level_from_environment() == logging.INFO


def test_log_level_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("PDP_STATION_LOG_LEVEL", " debug ")

    assert log_level_from_environment() == logging.DEBUG


def test_invalid_log_level_is_rejected(monkeypatch):
    monkeypatch.setenv("PDP_STATION_LOG_LEVEL", "verbose")

    with pytest.raises(RuntimeError, match="PDP_STATION_LOG_LEVEL must be one of"):
        log_level_from_environment()


def test_logging_config_reuses_uvicorn_formatter_and_handler():
    config = logging_config(logging.DEBUG)

    assert config["loggers"]["pdp_station"] == {
        "handlers": ["default"],
        "level": logging.DEBUG,
        "propagate": False,
    }
    assert config["handlers"]["default"]["formatter"] == "default"
    assert config["formatters"]["default"]["()"] == ("uvicorn.logging.DefaultFormatter")


def test_xlsx_engine_defaults_to_xlsxwriter(monkeypatch):
    monkeypatch.setenv("PCDS_DSN", "postgresql://example/database")
    monkeypatch.delenv("PDP_STATION_XLSX_ENGINE", raising=False)

    assert Settings.from_environment().xlsx_engine == "xlsxwriter"


def test_xlsx_engine_is_configurable(monkeypatch):
    monkeypatch.setenv("PCDS_DSN", "postgresql://example/database")
    monkeypatch.setenv("PDP_STATION_XLSX_ENGINE", " RUSTPY ")

    assert Settings.from_environment().xlsx_engine == "rustpy"


def test_invalid_xlsx_engine_is_rejected(monkeypatch):
    monkeypatch.setenv("PCDS_DSN", "postgresql://example/database")
    monkeypatch.setenv("PDP_STATION_XLSX_ENGINE", "unknown")

    with pytest.raises(RuntimeError, match="PDP_STATION_XLSX_ENGINE"):
        Settings.from_environment()
