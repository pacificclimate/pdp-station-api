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
    database_yield_per: int = 10_000
    spool_max_size: int = 1 << 30
    aggregate_max_stations: int = 1_000
    explain_analyze_station_ids: frozenset[int] = frozenset()
    xlsx_engine: str = "xlsxwriter"

    @classmethod
    def from_environment(cls) -> "Settings":
        try:
            database_url = os.environ["PCDS_DSN"]
        except KeyError as exc:
            raise RuntimeError("PCDS_DSN must be set") from exc
        try:
            database_yield_per = int(
                os.environ.get("PDP_STATION_DATABASE_YIELD_PER", "10000")
            )
        except ValueError as exc:
            raise RuntimeError(
                "PDP_STATION_DATABASE_YIELD_PER must be an integer"
            ) from exc
        if database_yield_per <= 0:
            raise RuntimeError(
                "PDP_STATION_DATABASE_YIELD_PER must be a positive integer"
            )
        explain_value = os.environ.get("PDP_STATION_EXPLAIN_ANALYZE_STATION_IDS", "")
        try:
            explain_analyze_station_ids = frozenset(
                int(value.strip())
                for value in explain_value.split(",")
                if value.strip()
            )
        except ValueError as exc:
            raise RuntimeError(
                "PDP_STATION_EXPLAIN_ANALYZE_STATION_IDS must contain "
                "comma-separated integers"
            ) from exc
        if any(station_id <= 0 for station_id in explain_analyze_station_ids):
            raise RuntimeError(
                "PDP_STATION_EXPLAIN_ANALYZE_STATION_IDS must contain positive integers"
            )
        try:
            spool_max_size = int(
                os.environ.get("PDP_STATION_SPOOL_MAX_SIZE", str(1 << 30))
            )
        except ValueError as exc:
            raise RuntimeError("PDP_STATION_SPOOL_MAX_SIZE must be an integer") from exc
        if spool_max_size < 0:
            raise RuntimeError("PDP_STATION_SPOOL_MAX_SIZE must not be negative")
        try:
            aggregate_max_stations = int(
                os.environ.get("PDP_STATION_AGGREGATE_MAX_STATIONS", "1000")
            )
        except ValueError as exc:
            raise RuntimeError(
                "PDP_STATION_AGGREGATE_MAX_STATIONS must be an integer"
            ) from exc
        if aggregate_max_stations <= 0:
            raise RuntimeError(
                "PDP_STATION_AGGREGATE_MAX_STATIONS must be a positive integer"
            )
        xlsx_engine = (
            os.environ.get("PDP_STATION_XLSX_ENGINE", "xlsxwriter").strip().lower()
        )
        if xlsx_engine not in {"xlsxwriter", "rustpy"}:
            raise RuntimeError(
                "PDP_STATION_XLSX_ENGINE must be one of: xlsxwriter, rustpy"
            )
        return cls(
            database_url=database_url,
            database_yield_per=database_yield_per,
            spool_max_size=spool_max_size,
            aggregate_max_stations=aggregate_max_stations,
            explain_analyze_station_ids=explain_analyze_station_ids,
            xlsx_engine=xlsx_engine,
        )
