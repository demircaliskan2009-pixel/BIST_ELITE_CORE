"""FAZ97: Config migration — v1 -> v2; CLI load uses migration."""

from __future__ import annotations

import json
from pathlib import Path


from bist_core.config import load_core_config_strict
from bist_core.config_migrate import CORE_CONFIG_SCHEMA_VERSION, migrate_core_config


def test_faz97_migrate_v1_to_v2() -> None:
    """v1 (no schema_version) -> migrated with schema_version 2."""
    v1 = {
        "timezone": "Europe/Istanbul",
        "default_spread_bps_max": 80,
        "default_adv_tl_min": 30000000,
        "default_auction_ratio_max": 0.15,
        "default_price_band_pct": 20.0,
        "risk_per_trade": 0.015,
    }
    out = migrate_core_config(v1)
    assert out.get("schema_version") == CORE_CONFIG_SCHEMA_VERSION
    assert out.get("timezone") == "Europe/Istanbul"
    assert "schema_version" in out


def test_faz97_migrate_v2_unchanged() -> None:
    """v2 (schema_version 2) -> unchanged."""
    v2 = {
        "schema_version": 2,
        "timezone": "UTC",
        "default_spread_bps_max": 50,
        "default_adv_tl_min": 10000000,
        "default_auction_ratio_max": 0.10,
        "default_price_band_pct": 15.0,
        "risk_per_trade": 0.01,
    }
    out = migrate_core_config(v2)
    assert out.get("schema_version") == 2
    assert out.get("timezone") == "UTC"


def test_faz97_load_core_config_strict_returns_migrated(tmp_path: Path) -> None:
    """load_core_config_strict uses migration: v1 file -> loaded config has schema_version 2."""
    core_path = tmp_path / "core.json"
    v1_content = {
        "timezone": "Europe/Istanbul",
        "default_spread_bps_max": 80,
        "default_adv_tl_min": 30000000,
        "default_auction_ratio_max": 0.15,
        "default_price_band_pct": 20.0,
        "risk_per_trade": 0.015,
    }
    core_path.write_text(json.dumps(v1_content, indent=2), encoding="utf-8")
    cfg, err = load_core_config_strict(core_path)
    assert err is None
    assert cfg is not None
    assert cfg.get("schema_version") == CORE_CONFIG_SCHEMA_VERSION
    assert cfg.get("timezone") == "Europe/Istanbul"


def test_faz97_migrate_deterministic() -> None:
    """Same v1 input -> same migrated output (schema_version 2)."""
    v1 = {
        "timezone": "UTC",
        "default_spread_bps_max": 100,
        "default_adv_tl_min": 0,
        "default_auction_ratio_max": 0.2,
        "default_price_band_pct": 10.0,
        "risk_per_trade": 0.02,
    }
    out1 = migrate_core_config(dict(v1))
    out2 = migrate_core_config(dict(v1))
    assert out1["schema_version"] == out2["schema_version"] == CORE_CONFIG_SCHEMA_VERSION
