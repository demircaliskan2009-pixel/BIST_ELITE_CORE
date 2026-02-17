"""FAZ230: KAP malformed handling — skip malformed HTML gracefully, no crash."""
from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.events.kap_ingest import ingest_kap_html
from bist_core.providers.events.kap_html import KapHtmlEventsProvider


FIXTURES_KAP = Path(__file__).resolve().parent / "fixtures" / "kap"


def test_faz230_malformed_unclosed_html_no_crash() -> None:
    """Malformed HTML with unclosed tags -> parse what we can or empty; no exception."""
    path = FIXTURES_KAP / "malformed_unclosed.html"
    if not path.is_file():
        pytest.skip("malformed_unclosed.html fixture not present")
    data = ingest_kap_html(path)
    assert "events" in data
    assert "hash" in data
    assert "source" in data
    assert isinstance(data["events"], list)


def test_faz230_non_html_no_crash() -> None:
    """Plain text file (non-HTML) -> empty events; no exception."""
    path = FIXTURES_KAP / "non_html.txt"
    if not path.is_file():
        pytest.skip("non_html.txt fixture not present")
    data = ingest_kap_html(path)
    assert "events" in data
    assert isinstance(data["events"], list)
    assert data["events"] == []


def test_faz230_broken_markup_returns_empty_or_partial() -> None:
    """Broken markup (missing columns) -> skip invalid rows; no crash."""
    path = FIXTURES_KAP / "broken_markup.html"
    if not path.is_file():
        pytest.skip("broken_markup.html fixture not present")
    data = ingest_kap_html(path)
    assert "events" in data
    assert isinstance(data["events"], list)
    # Row has only 2 cells; required 4 -> skipped
    assert len(data["events"]) == 0


def test_faz230_provider_malformed_graceful(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """KapHtmlEventsProvider with malformed HTML returns list (events or error_marker); no crash."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_KAP_CACHE_DIR", str(tmp_path))

    malformed = FIXTURES_KAP / "non_html.txt"
    if not malformed.is_file():
        pytest.skip("non_html.txt fixture not present")

    # Write plain text to cache for day (no table structure)
    (tmp_path / "2024-06-15.html").write_text(malformed.read_text(), encoding="utf-8")

    provider = KapHtmlEventsProvider(raw_dir=tmp_path)
    events = provider.fetch_events_for_day("2024-06-15")
    assert isinstance(events, list)


def test_faz230_minimal_still_parses() -> None:
    """Regression: valid minimal HTML still parses correctly."""
    path = FIXTURES_KAP / "minimal.html"
    assert path.is_file()
    data = ingest_kap_html(path)
    assert len(data["events"]) == 1
    assert data["events"][0]["symbol"] == "ASELS"
    assert "Minimal Notice" in data["events"][0]["title"]


def test_faz230_empty_html_no_crash() -> None:
    """Empty table -> empty events; no crash."""
    path = FIXTURES_KAP / "empty.html"
    assert path.is_file()
    data = ingest_kap_html(path)
    assert data["events"] == []
