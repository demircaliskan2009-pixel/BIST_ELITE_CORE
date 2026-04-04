"""Configuration: system config, paths, loaders, SOURCES."""

from __future__ import annotations

from bist_core.config.loader import (
    CORE,
    CORE_SCHEMA_V1_REQUIRED,
    DATA_DIR,
    EOD_SNAPSHOT_DIR,
    REPO_ROOT,
    SAMPLES_DIR,
    SOURCES,
    load_broker_config,
    load_config,
    load_core_config_strict,
    resolve_core_config_path,
)
from bist_core.config.system_config import CONFIG, SystemConfig

__all__ = [
    "CONFIG",
    "SystemConfig",
    "CORE",
    "CORE_SCHEMA_V1_REQUIRED",
    "DATA_DIR",
    "EOD_SNAPSHOT_DIR",
    "REPO_ROOT",
    "SAMPLES_DIR",
    "SOURCES",
    "load_broker_config",
    "load_config",
    "load_core_config_strict",
    "resolve_core_config_path",
]
