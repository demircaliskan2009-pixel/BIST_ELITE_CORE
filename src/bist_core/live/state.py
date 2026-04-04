"""Persistent runtime state — crash-safe, deterministic."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = "runtime_state.json"


def _state_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("BIST_LIVE_STATE_PATH", DEFAULT_STATE_PATH))


def _default_state() -> dict[str, Any]:
    return {
        "last_run_ts": None,
        "equity": 0.0,
        "peak_equity": 0.0,
        "drawdown": 0.0,
        "open_positions": [],
        "consecutive_losses": 0,
        "pause_until": None,
    }


def load_state(path: str | Path | None = None) -> dict[str, Any]:
    p = _state_path(path)
    if not p.exists():
        return _default_state()
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _default_state()
        out = _default_state()
        for k in out:
            if k in data:
                out[k] = data[k]
        return out
    except (json.JSONDecodeError, OSError):
        return _default_state()


def save_state(state: dict[str, Any], path: str | Path | None = None) -> None:
    p = _state_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(p)


def initialize_state(initial_equity: float = 0.0, path: str | Path | None = None) -> dict[str, Any]:
    s = _default_state()
    s["equity"] = float(initial_equity)
    s["peak_equity"] = float(initial_equity)
    save_state(s, path)
    return s


__all__ = ["load_state", "save_state", "initialize_state", "DEFAULT_STATE_PATH"]
