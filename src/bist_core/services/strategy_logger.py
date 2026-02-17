"""Strategy registry — log every proposed strategy from ask/scan. JSONL append. Fail-closed."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


STRATEGY_LOG_SCHEMA_VERSION = 1


def _default_log_path() -> Path:
    env_path = os.environ.get("BIST_CORE_STRATEGY_LOG")
    if env_path:
        return Path(env_path)
    from bist_core import config
    return config.REPO_ROOT / "data" / "log" / "strategies.jsonl"


def log_strategy(
    symbol: str,
    day: str,
    source: str,
    *,
    horizon: Optional[str] = None,
    risk: Optional[str] = None,
    capital: Optional[float] = None,
    max_loss_tl: Optional[float] = None,
    score: Optional[float] = None,
    decision_raw: Optional[str] = None,
    rank: Optional[int] = None,
    plan: Optional[dict[str, Any]] = None,
    log_path: Optional[Path] = None,
) -> None:
    """
    Append a strategy record to strategies.jsonl. Fail-closed: raises on write error.
    Deterministic keys. No network.
    """
    path = log_path if log_path is not None else _default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    params: dict[str, Any] = {}
    if horizon is not None:
        params["horizon"] = horizon
    if risk is not None:
        params["risk"] = risk
    if capital is not None:
        params["capital"] = capital
    if max_loss_tl is not None:
        params["max_loss_tl"] = max_loss_tl

    strategy_detail: dict[str, Any] = {}
    if score is not None:
        strategy_detail["score"] = round(score, 6)
    if decision_raw is not None:
        strategy_detail["decision_raw"] = decision_raw
    if rank is not None:
        strategy_detail["rank"] = rank
    if plan is not None and isinstance(plan, dict):
        entry = plan.get("entry")
        stop = plan.get("stop")
        t1 = plan.get("t1")
        if entry is not None or stop is not None or t1 is not None:
            strategy_detail["plan"] = {
                k: round(float(v), 6) if isinstance(v, (int, float)) else v
                for k, v in [("entry", entry), ("stop", stop), ("t1", t1)]
                if v is not None
            }

    record = {
        "schema_version": STRATEGY_LOG_SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "day": day,
        "source": source,
        "params": params,
        "strategy_detail": strategy_detail,
    }

    line = json.dumps(record, ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
