"""Application logging configuration."""

import logging


def configure_logging(level: str) -> None:
    """Configure a simple process-wide logging baseline."""

    logging.basicConfig(level=level.upper())
