"""
FAZ97: Config migration — v1 -> v2 -> ... . CLI load uses this before validation.
Core config: v1 (no schema_version) -> v2 (schema_version: 2). Deterministic.
"""

from __future__ import annotations

from typing import Any, Dict

CORE_CONFIG_SCHEMA_VERSION = 2


def migrate_core_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate core config to latest schema version. Mutates and returns data.
    v1 (missing schema_version) -> v2: add schema_version: 2.
    v2+ -> return as-is.
    """
    if not isinstance(data, dict):
        return data
    version = data.get("schema_version")
    if version is None:
        data["schema_version"] = CORE_CONFIG_SCHEMA_VERSION
        return data
    if isinstance(version, int) and version >= CORE_CONFIG_SCHEMA_VERSION:
        return data
    # Future: if version == 2 and CORE_CONFIG_SCHEMA_VERSION == 3, apply v2->v3
    if isinstance(version, int) and version < CORE_CONFIG_SCHEMA_VERSION:
        data["schema_version"] = CORE_CONFIG_SCHEMA_VERSION
    return data


__all__ = ["migrate_core_config", "CORE_CONFIG_SCHEMA_VERSION"]
