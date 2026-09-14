"""Server-side logging: one INFO line per request with duration, one line per error with context."""
import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. under uvicorn reload)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Quiet down noisy third-party loggers a bit.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
