from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from bist_core.providers.events.kap_html import KapHtmlEventsProvider
from bist_core.services.events_pipeline import build_events_jsonl_for_day


def _fixture_html(repo_root: Path) -> bytes:
    return (repo_root / "tests" / "fixtures" / "kap_sample.html").read_bytes()


def test_kap_html_cache_only_hit_sets_raw_path_and_sha(tmp_path: Path) -> None:
    day = "2099-01-01"
    repo_root = Path(__file__).resolve().parents[1]
    html_bytes = _fixture_html(repo_root)

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{day}.html"
    raw_file.write_bytes(html_bytes)

    provider = KapHtmlEventsProvider(
        base_url="https://example.invalid",
        raw_dir=raw_dir,
        cache_only=True,
    )
    rows = provider.fetch_events_for_day(day)

    assert rows
    assert not any("error_marker" in r for r in rows)
    assert provider.raw_path == str(raw_file)
    assert provider.raw_sha256 == hashlib.sha256(html_bytes).hexdigest()
    assert provider.cache_only is True


def test_events_pipeline_manifest_includes_raw_cache(tmp_path: Path) -> None:
    day = "2099-01-01"
    repo_root = Path(__file__).resolve().parents[1]
    html_bytes = _fixture_html(repo_root)

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{day}.html"
    raw_file.write_bytes(html_bytes)

    provider = KapHtmlEventsProvider(
        base_url="https://example.invalid",
        raw_dir=raw_dir,
        cache_only=True,
    )

    out_path = tmp_path / "out" / day / "events.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_events_jsonl_for_day(day, provider, out_path, atomic=True)

    assert manifest["raw_cache"] is not None
    assert manifest["raw_cache"]["path"] == str(raw_file)
    assert manifest["raw_cache"]["sha256"] == hashlib.sha256(html_bytes).hexdigest()
    assert manifest["raw_cache"]["cache_only"] is True


def test_kap_html_cache_only_miss_failclosed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day = "2099-01-02"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "1")

    provider = KapHtmlEventsProvider(
        base_url="https://example.invalid",
        raw_dir=raw_dir,
        cache_only=True,
    )
    rows = provider.fetch_events_for_day(day)

    assert rows
    assert "CacheMiss" in rows[0].get("error_marker", "")
