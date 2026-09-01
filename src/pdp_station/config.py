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
    value = os.environ.get("PDP_STATION_LOG_LEVEL", "INFO").strip().upper()
    try:
        return LOG_LEVELS[value]
    except KeyError as exc:
        supported = ", ".join(LOG_LEVELS)
        raise RuntimeError(
            f"PDP_STATION_LOG_LEVEL must be one of: {supported}"
        ) from exc


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_yield_per: int = 1_000
    spool_max_size: int = 1 << 30
    xlsx_engine: str = "xlsxwriter"

    @classmethod
    def from_environment(cls) -> "Settings":
        try:
            database_url = os.environ["PCDS_DSN"]
        except KeyError as exc:
            raise RuntimeError("PCDS_DSN must be set") from exc
        try:
            spool_max_size = int(
                os.environ.get("PDP_STATION_SPOOL_MAX_SIZE", str(1 << 30))
            )
        except ValueError as exc:
            raise RuntimeError("PDP_STATION_SPOOL_MAX_SIZE must be an integer") from exc
        if spool_max_size < 0:
            raise RuntimeError("PDP_STATION_SPOOL_MAX_SIZE must not be negative")
        xlsx_engine = (
            os.environ.get("PDP_STATION_XLSX_ENGINE", "xlsxwriter").strip().lower()
        )
        if xlsx_engine not in {"xlsxwriter", "rustpy"}:
            raise RuntimeError(
                "PDP_STATION_XLSX_ENGINE must be one of: xlsxwriter, rustpy"
            )
        return cls(
            database_url=database_url,
            spool_max_size=spool_max_size,
            xlsx_engine=xlsx_engine,
        )
