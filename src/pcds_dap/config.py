"""Runtime configuration."""

from dataclasses import dataclass
import logging
import os


LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def log_level_from_environment() -> int:
    value = os.environ.get("PCDS_DAP_LOG_LEVEL", "INFO").strip().upper()
    try:
        return LOG_LEVELS[value]
    except KeyError as exc:
        supported = ", ".join(LOG_LEVELS)
        raise RuntimeError(f"PCDS_DAP_LOG_LEVEL must be one of: {supported}") from exc


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_yield_per: int = 1_000
    spool_max_size: int = 1 << 30
    aggregate_max_stations: int = 1_000

    @classmethod
    def from_environment(cls) -> "Settings":
        try:
            database_url = os.environ["PCDS_DSN"]
        except KeyError as exc:
            raise RuntimeError("PCDS_DSN must be set") from exc
        try:
            spool_max_size = int(
                os.environ.get("PCDS_DAP_SPOOL_MAX_SIZE", str(1 << 30))
            )
        except ValueError as exc:
            raise RuntimeError("PCDS_DAP_SPOOL_MAX_SIZE must be an integer") from exc
        if spool_max_size < 0:
            raise RuntimeError("PCDS_DAP_SPOOL_MAX_SIZE must not be negative")
        try:
            aggregate_max_stations = int(
                os.environ.get("PCDS_DAP_AGGREGATE_MAX_STATIONS", "1000")
            )
        except ValueError as exc:
            raise RuntimeError(
                "PCDS_DAP_AGGREGATE_MAX_STATIONS must be an integer"
            ) from exc
        if aggregate_max_stations <= 0:
            raise RuntimeError(
                "PCDS_DAP_AGGREGATE_MAX_STATIONS must be a positive integer"
            )
        return cls(
            database_url=database_url,
            spool_max_size=spool_max_size,
            aggregate_max_stations=aggregate_max_stations,
        )
