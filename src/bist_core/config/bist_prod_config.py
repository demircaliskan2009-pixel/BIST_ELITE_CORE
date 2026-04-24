"""BIST Production Configuration — single source of truth.

Loads config/bist_prod.json and exposes all trading parameters
as typed, frozen attributes. All modules MUST read from this
instead of defining local constants.

Fail-closed: if config is missing or invalid, the system stops.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Final, FrozenSet

_CONFIG_PATH: Final[Path] = Path(__file__).resolve().parents[3] / "config" / "bist_prod.json"


@dataclass(frozen=True)
class EventEntryConfig:
    stop_pct: float
    min_rr: float
    atr_period: int
    swing_lookback: int


@dataclass(frozen=True)
class EventPolicyConfig:
    entry_kinds: FrozenSet[str]
    block_kinds: FrozenSet[str]
    soft_negative_kinds: FrozenSet[str]
    neutral_kinds: FrozenSet[str]
    size_multipliers: Dict[str, float]
    confidence_positive: float
    confidence_soft_negative: float
    positive_event_boost: float
    lookback_days: int
    event_entry: EventEntryConfig


@dataclass(frozen=True)
class PortfolioConfig:
    max_positions: int
    max_per_symbol: int
    max_entries_per_ts: int
    risk_per_trade_pct: float
    max_notional_pct: float
    initial_equity: float
    daily_loss_limit_pct: float
    max_drawdown_kill_pct: float
    min_position_size: int
    max_position_size: int


@dataclass(frozen=True)
class ScoringConfig:
    lookback: int
    min_trades: int
    min_threshold: float


@dataclass(frozen=True)
class ExecutionConfig:
    slippage_bps: float
    commission_bps: float
    exchange_fee_bps: float


@dataclass(frozen=True)
class BistProdConfig:
    """Frozen BIST production configuration."""

    market: str
    version: str
    frozen: bool
    event_policy: EventPolicyConfig
    portfolio: PortfolioConfig
    scoring: ScoringConfig
    execution: ExecutionConfig


def _parse_config(raw: Dict[str, Any]) -> BistProdConfig:
    """Parse raw JSON dict into typed frozen config."""
    ep = raw["event_policy"]
    ee = ep["event_entry"]
    pf = raw["portfolio"]
    sc = raw["scoring"]
    ex = raw["execution"]

    return BistProdConfig(
        market=raw["market"],
        version=raw["version"],
        frozen=raw["frozen"],
        event_policy=EventPolicyConfig(
            entry_kinds=frozenset(ep["entry_kinds"]),
            block_kinds=frozenset(ep["block_kinds"]),
            soft_negative_kinds=frozenset(ep["soft_negative_kinds"]),
            neutral_kinds=frozenset(ep["neutral_kinds"]),
            size_multipliers=dict(ep["size_multipliers"]),
            confidence_positive=ep["confidence_multipliers"]["positive"],
            confidence_soft_negative=ep["confidence_multipliers"]["soft_negative"],
            positive_event_boost=ep["positive_event_boost"],
            lookback_days=ep["lookback_days"],
            event_entry=EventEntryConfig(
                stop_pct=ee["stop_pct"],
                min_rr=ee["min_rr"],
                atr_period=ee["atr_period"],
                swing_lookback=ee["swing_lookback"],
            ),
        ),
        portfolio=PortfolioConfig(
            max_positions=pf["max_positions"],
            max_per_symbol=pf["max_per_symbol"],
            max_entries_per_ts=pf["max_entries_per_ts"],
            risk_per_trade_pct=pf["risk_per_trade_pct"],
            max_notional_pct=pf["max_notional_pct"],
            initial_equity=pf["initial_equity"],
            daily_loss_limit_pct=pf["daily_loss_limit_pct"],
            max_drawdown_kill_pct=pf["max_drawdown_kill_pct"],
            min_position_size=pf["min_position_size"],
            max_position_size=pf["max_position_size"],
        ),
        scoring=ScoringConfig(
            lookback=sc["lookback"],
            min_trades=sc["min_trades"],
            min_threshold=sc["min_threshold"],
        ),
        execution=ExecutionConfig(
            slippage_bps=ex["slippage_bps"],
            commission_bps=ex["commission_bps"],
            exchange_fee_bps=ex["exchange_fee_bps"],
        ),
    )


def load_bist_config(path: Path | None = None) -> BistProdConfig:
    """Load and validate BIST production config.

    Fail-closed: raises on missing file or invalid schema.
    """
    p = path or _CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"BIST config not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    cfg = _parse_config(raw)
    if cfg.market != "bist":
        raise ValueError(f"Expected market='bist', got '{cfg.market}'")
    return cfg


# Module-level singleton — loaded once at import time.
# All modules should import BIST_CONFIG from here.
try:
    BIST_CONFIG: BistProdConfig = load_bist_config()
except FileNotFoundError:
    # Allow import in test environments without config file.
    # Modules must check BIST_CONFIG is not None before use.
    BIST_CONFIG = None  # type: ignore[assignment]


__all__ = [
    "BIST_CONFIG",
    "BistProdConfig",
    "EventEntryConfig",
    "EventPolicyConfig",
    "ExecutionConfig",
    "PortfolioConfig",
    "ScoringConfig",
    "load_bist_config",
]
