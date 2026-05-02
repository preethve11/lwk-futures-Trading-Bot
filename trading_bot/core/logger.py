"""Compatibility wrapper for structured logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.logging import setup_logging as _setup_logging


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    log_file: str | None = None,
    json_logs: bool = True,
) -> logging.Logger:
    """Configure structured logging for legacy callers."""
    return _setup_logging(level=level, log_dir=log_dir, log_file=log_file, json_logs=json_logs)
