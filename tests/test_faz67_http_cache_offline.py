"""
FAZ67: Offline-first HTTP client with deterministic disk cache (TTL, sha256 key, response metadata).
Fixture mode for tests (no network). Research stage integration. No new deps.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch


from bist_core.http_cache import HttpClient, get_cached, _cache_key, _subdir_path
from bist_core.research.cache import build_research_cache


# ---- Unit: cache key and paths ----


def test_faz67_cache_key_deterministic() -> None:
    """Cache key is sha256(url) hex; same URL -> same key."""
    url = "https://example.com/research/2099-01-01"
    k1 = _cache_key(url)
    k2 = _cache_key(url)
    assert k1 == k2
    assert len(k1) == 64
    assert k1 == hashlib.sha256(url.encode("utf-8")).hexdigest()
    assert _cache_key("https://other.com") != k1


def test_faz67_subdir_path_spreads_by_key_prefix(tmp_path: Path) -> None:
    """Cache files go under key[:2]/key[2:4]/key.suffix."""
    key = "aabbccdd" + "e" * 56
    p = _subdir_path(tmp_path, key, ".meta.json")
    assert p == tmp_path / "aa" / "bb" / (key + ".meta.json")


# ---- Unit: HttpClient ----


def test_faz67_fixture_mode_cache_miss_returns_error(tmp_path: Path) -> None:
    """Fixture mode: no network; cache miss -> (None, 'cache_miss')."""
    client = HttpClient(cache_dir=tmp_path, ttl_seconds=3600, fixture_mode=True)
    resp, err = client.get("https://example.com/not-cached")
    assert resp is None
    assert err == "cache_miss"


def test_faz67_fixture_mode_cache_hit_returns_cached(tmp_path: Path) -> None:
    """Fixture mode: cache hit -> returns cached response metadata + body."""
    url = "https://example.com/cached"
    key = _cache_key(url)
    meta_path = _subdir_path(tmp_path, key, ".meta.json")
    body_path = _subdir_path(tmp_path, key, ".body")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "url": url,
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "cached_at": "2099-01-01T12:00:00.000Z",
                "ttl_seconds": 86400,
            }
        ),
        encoding="utf-8",
    )
    body_path.write_bytes(b'[{"id":"r1","title":"Cached"}]')

    client = HttpClient(cache_dir=tmp_path, ttl_seconds=3600, fixture_mode=True)
    resp, err = client.get(url)
    assert err is None
    assert resp is not None
    assert resp["status_code"] == 200
    assert resp["from_cache"] is True
    assert resp["body"] == b'[{"id":"r1","title":"Cached"}]'


def test_faz67_non_fixture_cache_hit_returns_cached(tmp_path: Path) -> None:
    """Non-fixture: cache hit within TTL returns cached response (no network)."""
    url = "https://example.com/cached"
    key = _cache_key(url)
    meta_path = _subdir_path(tmp_path, key, ".meta.json")
    body_path = _subdir_path(tmp_path, key, ".body")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "url": url,
                "status_code": 200,
                "headers": {},
                "cached_at": "2099-01-01T12:00:00.000Z",
                "ttl_seconds": 86400,
            }
        ),
        encoding="utf-8",
    )
    body_path.write_bytes(b"cached body")
    client = HttpClient(cache_dir=tmp_path, ttl_seconds=3600, fixture_mode=False)
    resp, err = client.get(url)
    assert err is None
    assert resp is not None
    assert resp["body"] == b"cached body"
    assert resp["from_cache"] is True


def test_faz67_ttl_expired_refetches_when_not_fixture(tmp_path: Path) -> None:
    """Cached entry past TTL: when not fixture mode, refetch (mock urlopen to avoid network)."""
    url = "https://example.com/old"
    key = _cache_key(url)
    meta_path = _subdir_path(tmp_path, key, ".meta.json")
    body_path = _subdir_path(tmp_path, key, ".body")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "url": url,
                "status_code": 200,
                "headers": {},
                "cached_at": "1999-01-01T00:00:00.000Z",
                "ttl_seconds": 1,
            }
        ),
        encoding="utf-8",
    )
    body_path.write_bytes(b"old")
    client = HttpClient(cache_dir=tmp_path, ttl_seconds=3600, fixture_mode=False)
    with patch("bist_core.http_cache.urlopen", side_effect=OSError("no network")):
        resp, err = client.get(url, ttl_seconds=1)
    assert err is not None
    assert "fetch_error" in err or "Error" in err or "OSError" in err


def test_faz67_get_cached_convenience(tmp_path: Path) -> None:
    """get_cached() is a convenience one-off call."""
    url = "https://example.com/x"
    key = _cache_key(url)
    meta_path = _subdir_path(tmp_path, key, ".meta.json")
    body_path = _subdir_path(tmp_path, key, ".body")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "url": url,
                "status_code": 200,
                "headers": {},
                "cached_at": "2099-06-01T00:00:00.000Z",
                "ttl_seconds": 86400,
            }
        ),
        encoding="utf-8",
    )
    body_path.write_bytes(b"ok")
    resp, err = get_cached(url, tmp_path, ttl_seconds=3600, fixture_mode=True)
    assert err is None
    assert resp is not None and resp["body"] == b"ok"


# ---- Research stage integration ----


def test_faz67_research_url_fixture_mode_uses_cache_only(tmp_path: Path) -> None:
    """Research source=url with offline=True uses HTTP cache; cache miss -> error_marker in entries."""
    research_dir = tmp_path / "2099-01-15" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = tmp_path / ".http_cache"
    # No cache seeded -> fixture mode (offline) -> cache_miss
    result = build_research_cache(
        "2099-01-15",
        tmp_path,
        source="url",
        offline=True,
        research_url="https://example.com/research/2099-01-15",
        http_cache_dir=cache_dir,
    )
    assert result["errors"] >= 1
    entries_path = research_dir / "entries.jsonl"
    assert entries_path.is_file()
    lines = entries_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    first = json.loads(lines[0])
    assert first.get("error_marker") == "cache_miss" or first.get("error_marker", "").startswith("cache_miss")


def test_faz67_research_url_fixture_mode_hit_returns_entries(tmp_path: Path) -> None:
    """Research source=url, offline=True, with pre-seeded cache -> entries from cache."""
    url = "https://example.com/research/2099-01-15"
    key = _cache_key(url)
    cache_dir = tmp_path / ".http_cache"
    meta_path = _subdir_path(cache_dir, key, ".meta.json")
    body_path = _subdir_path(cache_dir, key, ".body")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    body_json = [
        {"id": "e1", "title": "Entry 1", "day": "2099-01-15"},
        {"id": "e2", "title": "Entry 2"},
    ]
    meta_path.write_text(
        json.dumps(
            {
                "url": url,
                "status_code": 200,
                "headers": {},
                "cached_at": "2099-01-15T10:00:00.000Z",
                "ttl_seconds": 86400,
            }
        ),
        encoding="utf-8",
    )
    body_path.write_bytes(json.dumps(body_json).encode("utf-8"))

    result = build_research_cache(
        "2099-01-15",
        tmp_path,
        source="url",
        offline=True,
        research_url=url,
        http_cache_dir=cache_dir,
    )
    assert result["errors"] == 0
    assert result["count"] == 2
    entries_path = tmp_path / "2099-01-15" / "research" / "entries.jsonl"
    assert entries_path.is_file()
    lines = entries_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    assert e1.get("id") in ("e1", "url_0")
    assert e1.get("title") in ("Entry 1", None) or "Entry" in str(e1.get("title", ""))


def test_faz67_research_stub_unchanged_without_url(tmp_path: Path) -> None:
    """Research source=stub (or kap) without research_url -> stub entries, no HTTP."""
    result = build_research_cache(
        "2099-01-15",
        tmp_path,
        source="stub",
        offline=True,
    )
    assert result["errors"] == 0
    assert result["count"] == 2
    entries_path = tmp_path / "2099-01-15" / "research" / "entries.jsonl"
    lines = entries_path.read_text(encoding="utf-8").strip().splitlines()
    assert any("stub_1" in line for line in lines)
