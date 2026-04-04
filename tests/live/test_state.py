"""Tests for persistent state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.live.state import initialize_state, load_state, save_state


def test_state_persistence(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    s = {"equity": 100000.0, "peak_equity": 100000.0, "last_run_ts": "2024-01-01T10:00:00"}
    save_state(s, p)
    loaded = load_state(p)
    assert loaded["equity"] == 100000.0
    assert loaded["peak_equity"] == 100000.0


def test_state_initialize(tmp_path: Path) -> None:
    p = tmp_path / "init_state.json"
    s = initialize_state(initial_equity=50000.0, path=p)
    assert s["equity"] == 50000.0
    assert s["peak_equity"] == 50000.0
    loaded = load_state(p)
    assert loaded["equity"] == 50000.0
