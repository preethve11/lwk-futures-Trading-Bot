"""
Structured logging setup. File + console, JSON optional.
"""

from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    log_file: Optional[str] = None,
    json_logs: bool = False,
) -> logging.Logger:
    """
    Configure root logger: console and optional file.
    Never log API keys or secrets.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger("trading_bot")
    root.setLevel(log_level)
    root.handlers.clear()

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=date_fmt)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_dir and log_file:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / log_file
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)

    return root
