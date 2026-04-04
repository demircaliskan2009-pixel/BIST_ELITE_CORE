"""FAZ155: KAP cache loader — BIST_KAP_CACHE_DIR env support."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.providers.events.kap_html import KapHtmlEventsProvider


def test_faz155_bist_kap_cache_dir_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BIST_KAP_CACHE_DIR used when set; provider reads from that path."""
    fixture = Path(__file__).resolve().parent / "fixtures" / "kap" / "sample.html"
    cache_dir = tmp_path / "kap_cache"
    cache_dir.mkdir()
    (cache_dir / "2099-01-01.html").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("BIST_KAP_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "0")

    provider = KapHtmlEventsProvider(cache_only=True)
    assert str(provider.raw_dir) == str(cache_dir)
    events = provider.fetch_events_for_day("2099-01-01")
    assert not any(e.get("error_marker") for e in events if isinstance(e, dict))
    assert len(events) >= 1


def test_faz155_cache_dir_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BIST_KAP_CACHE_DIR overrides BIST_KAP_RAW_DIR."""
    cache_dir = tmp_path / "direct_cache"
    cache_dir.mkdir()
    (cache_dir / "2099-01-01.html").write_text("<html><body>x</body></html>", encoding="utf-8")
    raw_root = tmp_path / "raw_root"
    raw_root.mkdir()
    monkeypatch.setenv("BIST_KAP_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("BIST_KAP_RAW_DIR", str(raw_root))
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "0")

    provider = KapHtmlEventsProvider(cache_only=True)
    assert str(provider.raw_dir) == str(cache_dir)


def test_faz155_param_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit raw_dir param overrides BIST_KAP_CACHE_DIR."""
    monkeypatch.setenv("BIST_KAP_CACHE_DIR", "/nonexistent")
    provider = KapHtmlEventsProvider(raw_dir=tmp_path, cache_only=True)
    assert provider.raw_dir == tmp_path
