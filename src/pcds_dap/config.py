"""Runtime configuration."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_yield_per: int = 1_000
    spool_max_size: int = 1 << 30

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
        return cls(database_url=database_url, spool_max_size=spool_max_size)
