import logging

import pytest

from pcds_dap.__main__ import logging_config
from pcds_dap.config import log_level_from_environment


def test_log_level_defaults_to_info(monkeypatch):
    monkeypatch.delenv("PCDS_DAP_LOG_LEVEL", raising=False)

    assert log_level_from_environment() == logging.INFO


def test_log_level_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("PCDS_DAP_LOG_LEVEL", " debug ")

    assert log_level_from_environment() == logging.DEBUG


def test_invalid_log_level_is_rejected(monkeypatch):
    monkeypatch.setenv("PCDS_DAP_LOG_LEVEL", "verbose")

    with pytest.raises(RuntimeError, match="PCDS_DAP_LOG_LEVEL must be one of"):
        log_level_from_environment()


def test_logging_config_reuses_uvicorn_formatter_and_handler():
    config = logging_config(logging.DEBUG)

    assert config["loggers"]["pcds_dap"] == {
        "handlers": ["default"],
        "level": logging.DEBUG,
        "propagate": False,
    }
    assert config["handlers"]["default"]["formatter"] == "default"
    assert config["formatters"]["default"]["()"] == ("uvicorn.logging.DefaultFormatter")
