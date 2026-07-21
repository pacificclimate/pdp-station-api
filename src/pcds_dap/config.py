"""Runtime configuration."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    database_yield_per: int = 1_000

    @classmethod
    def from_environment(cls) -> "Settings":
        try:
            database_url = os.environ["PCDS_DSN"]
        except KeyError as exc:
            raise RuntimeError("PCDS_DSN must be set") from exc
        return cls(database_url=database_url)
