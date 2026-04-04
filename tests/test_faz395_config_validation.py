"""FAZ395: Config validation on load — invalid config fails; valid loads."""

from __future__ import annotations

import json
from pathlib import Path


from bist_core.config import load_core_config_strict


def test_faz395_config_invalid_fails(tmp_path: Path) -> None:
    """Invalid core config (missing key, wrong type) must return (None, CONFIG_INVALID)."""
    bad1 = tmp_path / "bad1.json"
    bad1.write_text("{}", encoding="utf-8")
    cfg, err = load_core_config_strict(bad1)
    assert cfg is None
    assert err == "CONFIG_INVALID"

    bad2 = tmp_path / "bad2.json"
    bad2.write_text('{"timezone":"Europe/Istanbul","default_spread_bps_max":"not_a_number"}', encoding="utf-8")
    cfg, err = load_core_config_strict(bad2)
    assert cfg is None
    assert err == "CONFIG_INVALID"


def test_faz395_config_valid_loads(tmp_path: Path) -> None:
    """Valid core config must load and return (dict, None)."""
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "timezone": "Europe/Istanbul",
                "default_spread_bps_max": 80,
                "default_adv_tl_min": 30000000,
                "default_auction_ratio_max": 0.15,
                "default_price_band_pct": 20,
                "risk_per_trade": 0.015,
            }
        ),
        encoding="utf-8",
    )
    cfg, err = load_core_config_strict(valid)
    assert err is None
    assert cfg is not None
    assert cfg["timezone"] == "Europe/Istanbul"
    assert cfg["default_spread_bps_max"] == 80


def test_faz395_config_missing_returns_missing(tmp_path: Path) -> None:
    """Missing config file must return (None, CONFIG_MISSING)."""
    cfg, err = load_core_config_strict(tmp_path / "nonexistent.json")
    assert cfg is None
    assert err == "CONFIG_MISSING"
