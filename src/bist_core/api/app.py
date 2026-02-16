"""FAZ185: FastAPI app — /health, /ask, /scan. Offline only, BIST-only scope."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def _snapshot_root() -> Path:
    return Path(os.getenv("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots"))


def _is_bist_symbol(symbol: str) -> bool:
    """BIST symbol format: 2-6 chars, uppercase alphanumeric."""
    if not symbol or len(symbol) < 2 or len(symbol) > 6:
        return False
    return symbol.isalnum() and symbol.isupper()


def _guard_network_off() -> None:
    """Raise if network is allowed (API must run offline by default)."""
    if os.environ.get("BIST_CORE_ALLOW_NETWORK", "").lower() in ("1", "true", "yes"):
        raise HTTPException(status_code=503, detail="API runs offline only; BIST_CORE_ALLOW_NETWORK must not be set")


def _latest_snapshot_day(snapshots_dir: Path) -> Optional[str]:
    if not snapshots_dir.exists():
        return None
    latest: Optional[date] = None
    for entry in snapshots_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            day = date.fromisoformat(entry.name)
        except ValueError:
            continue
        if latest is None or day > latest:
            latest = day
    return latest.isoformat() if latest else None


# --- Pydantic models ---
class AskRequest(BaseModel):
    symbol: str = Field(..., min_length=2, max_length=6)
    day: Optional[str] = None
    horizon: Optional[str] = Field(None, pattern="^(short|mid|long)$")
    risk: Optional[str] = Field(None, pattern="^(low|med|high)$")
    capital: Optional[float] = None
    max_loss_tl: Optional[float] = None


class ScanRequest(BaseModel):
    day: Optional[str] = None
    top_n: int = Field(default=10, ge=1, le=100)
    horizon: Optional[str] = Field(None, pattern="^(short|mid|long)$")
    risk: Optional[str] = Field(None, pattern="^(low|med|high)$")
    capital: Optional[float] = None
    max_loss_tl: Optional[float] = None
    exclusions: Optional[str] = None


# --- App ---
app = FastAPI(
    title="BIST Elite Core API",
    description="Local UI — offline only, BIST-only. Wraps CLI ask/scan.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """FAZ193: Liveness probe."""
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest) -> dict[str, Any]:
    """FAZ186: Ask advice for symbol. BIST-only, offline."""
    _guard_network_off()
    sym = req.symbol.strip().upper()
    if not _is_bist_symbol(sym):
        raise HTTPException(status_code=400, detail="BIST scope only: symbol must be 2-6 uppercase alphanumeric")

    base = _snapshot_root()
    day_str = req.day
    if not day_str:
        day_str = _latest_snapshot_day(base)
    if not day_str:
        day_str = date.today().isoformat()

    from bist_core.services.advisor import build_advice_for_symbol

    try:
        advice = build_advice_for_symbol(sym, day_str, root=base)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "symbol": advice.symbol,
        "day": day_str,
        "decision_raw": advice.decision_raw,
        "score": advice.score,
        "text": (advice.text or "")[:200],
    }


@app.post("/scan")
def scan(req: ScanRequest) -> dict[str, Any]:
    """FAZ187: Ranked scan. BIST-only, offline."""
    _guard_network_off()
    base = _snapshot_root()
    day_str = req.day or _latest_snapshot_day(base)
    if not day_str:
        raise HTTPException(status_code=400, detail="No snapshots; provide day or run eod pipeline")

    from bist_core.services.marketdata import MarketData
    from bist_core.services.advisor import build_advice_for_symbol

    try:
        md = MarketData(base)
        symbols = md.symbols(day_str)
    except Exception:
        symbols = []
    exclusions = {s.strip().upper() for s in (req.exclusions or "").split(",") if s.strip()}
    symbols = [s for s in symbols if _is_bist_symbol(s) and s not in exclusions]
    symbols = sorted(symbols)

    results: list[dict[str, Any]] = []
    for sym in symbols:
        try:
            advice = build_advice_for_symbol(sym, day_str, root=base)
            results.append({
                "symbol": advice.symbol,
                "score": advice.score,
                "rationale": (advice.text or "").split("\n")[0][:80],
            })
        except Exception:
            results.append({"symbol": sym, "score": 0.0, "rationale": "error"})
    results.sort(key=lambda x: (-x["score"], x["symbol"]))
    ranked = results[: req.top_n]

    return {"day": day_str, "ranked": ranked}
