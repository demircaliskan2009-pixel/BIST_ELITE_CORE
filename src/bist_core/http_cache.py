"""
FAZ67: Offline-first HTTP client with deterministic disk cache (TTL, sha256 key, response metadata).
Fixture mode: no network, cache-only for tests. Uses urllib only (no new deps).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.request import Request, urlopen


def _cache_key(url: str) -> str:
    """Deterministic cache key from URL (sha256 hex)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _subdir_path(cache_dir: Path, key: str, suffix: str) -> Path:
    """Path under cache_dir/key[:2]/key[2:4]/key.suffix for even spread."""
    return cache_dir / key[:2] / key[2:4] / f"{key}{suffix}"


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


class HttpClient:
    """
    Offline-first HTTP client with disk cache.
    Cache key: sha256(url). Metadata (status, headers, cached_at, ttl) + body stored on disk.
    Fixture mode: never open network; cache miss returns (None, 'cache_miss').
    """

    def __init__(
        self,
        cache_dir: Path | str,
        ttl_seconds: int = 86400,
        fixture_mode: bool = False,
        timeout_seconds: int = 15,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.fixture_mode = fixture_mode
        self.timeout_seconds = timeout_seconds

    def get(self, url: str, ttl_seconds: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        GET url. Returns (response_dict, error).
        response_dict: { "status_code", "headers", "body" (bytes), "from_cache" }.
        error: None on success; else "cache_miss", "fetch_error", etc.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        key = _cache_key(url)
        meta_path = _subdir_path(self.cache_dir, key, ".meta.json")
        body_path = _subdir_path(self.cache_dir, key, ".body")

        # Offline-first: try cache
        if meta_path.is_file() and body_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                cached_at = meta.get("cached_at") or ""
                try:
                    cached_ts = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                except Exception:
                    cached_ts = None
                if cached_ts:
                    age = (datetime.now(timezone.utc) - cached_ts).total_seconds()
                    if age <= ttl:
                        body = body_path.read_bytes()
                        return (
                            {
                                "status_code": meta.get("status_code", 0),
                                "headers": meta.get("headers", {}),
                                "body": body,
                                "from_cache": True,
                            },
                            None,
                        )
            except (OSError, json.JSONDecodeError):
                pass

        if self.fixture_mode:
            return None, "cache_miss"

        # Fetch and cache
        try:
            request = Request(url, headers={"User-Agent": "bist-core-http-cache/1"})
            with urlopen(request, timeout=self.timeout_seconds) as resp:
                body = resp.read()
            status_code = getattr(resp, "status", 200)
            headers = dict(resp.headers) if hasattr(resp, "headers") else {}
        except Exception as exc:
            return None, f"fetch_error:{exc.__class__.__name__}"

        cached_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        meta = {
            "url": url,
            "status_code": status_code,
            "headers": headers,
            "cached_at": cached_at,
            "ttl_seconds": ttl,
        }
        _atomic_write_json(meta_path, meta)
        _atomic_write_bytes(body_path, body)
        return (
            {
                "status_code": status_code,
                "headers": headers,
                "body": body,
                "from_cache": False,
            },
            None,
        )


def get_cached(
    url: str,
    cache_dir: Path | str,
    ttl_seconds: int = 86400,
    fixture_mode: bool = False,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Convenience: one-off GET with cache. Returns (response_dict, error)."""
    client = HttpClient(
        cache_dir=Path(cache_dir),
        ttl_seconds=ttl_seconds,
        fixture_mode=fixture_mode,
    )
    return client.get(url)
