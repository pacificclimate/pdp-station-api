"""Development server entry point."""

from copy import deepcopy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from .config import log_level_from_environment


def logging_config(level: int) -> dict:
    """Extend Uvicorn's configuration without changing its formatting."""
    config = deepcopy(LOGGING_CONFIG)
    config["loggers"]["pdp_station"] = {
        "handlers": ["default"],
        "level": level,
        "propagate": False,
    }
    return config


def main():
    level = log_level_from_environment()
    uvicorn.run(
        "pdp_station.web:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_config=logging_config(level),
        log_level=level,
    )


if __name__ == "__main__":
    main()
