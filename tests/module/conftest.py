"""Shared fixtures for module tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _bist_edge_gate_threshold_for_curated_bars(monkeypatch: pytest.MonkeyPatch) -> None:
    """RANGE/enter_small paths sharpen to ~0.36; default gate 0.45 would block them."""
    monkeypatch.setenv("BIST_EDGE_GATE_THRESHOLD", "0.25")
