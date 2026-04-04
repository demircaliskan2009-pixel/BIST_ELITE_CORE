"""Matriks provider — network off by default."""

from __future__ import annotations

import os

import pytest

from bist_core.data.matriks_provider import MatriksProvider


def test_matriks_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATRIKS_ENABLED", raising=False)
    m = MatriksProvider()
    assert m.get_price("ASELS") is None


def test_fetch_disabled_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATRIKS_ENABLED", raising=False)
    m = MatriksProvider()
    assert m.fetch("ASELS", period="1m") is None


def test_fetch_returns_bars_when_network_and_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MATRIKS_ENABLED", "1")
    monkeypatch.setenv("MATRIKS_TOKEN", "x")
    m = MatriksProvider()
    monkeypatch.setattr(m, "_fetch", lambda _sym: 100.0)
    out = m.fetch("ASELS", period="1m")
    assert out is not None
    assert len(out) == 60
    assert all(b.symbol == "ASELS" and float(b.close) == 100.0 for b in out)
