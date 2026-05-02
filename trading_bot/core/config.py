"""Compatibility wrapper for the platform Pydantic settings."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings, load_settings


Config = Settings


def load_config(config_path: Path | None = None, project_root: Path | None = None) -> Settings:
    """Load validated settings for legacy CLI callers."""
    return load_settings(config_path=config_path, project_root=project_root)
