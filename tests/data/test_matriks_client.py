"""Matriks client unit tests — auth header, error handling, bar fetching, adapter integration.

All tests mock HTTP; no real network calls are made.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bist_core.data.matriks_client import (
    MatriksAPIError,
    MatriksClient,
    NetworkDisabledError,
    fetch_and_prepare_bars,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(body: Any, status: int = 200) -> MagicMock:
    """Build a mock urllib response object."""
    encoded = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = encoded
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


_SAMPLE_BARS = [
    {"symbol": "GARAN", "date": "2026-01-15", "open": 30.5, "high": 31.0, "low": 30.0, "close": 30.8, "volume": 1_000_000},
    {"symbol": "GARAN", "date": "2026-01-16", "open": 30.8, "high": 32.0, "low": 30.5, "close": 31.5, "volume": 1_200_000},
]


@pytest.fixture(autouse=True)
def _enable_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable network guard for all tests (no real HTTP is made; urlopen is mocked)."""
    monkeypatch.setenv("BIST_CORE_NETWORK_ENABLED", "1")


# ── Network guard ─────────────────────────────────────────────────────────

class TestNetworkGuard:
    def test_raises_when_network_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BIST_CORE_NETWORK_ENABLED", raising=False)
        client = MatriksClient(token="tok")
        with pytest.raises(NetworkDisabledError, match="disabled"):
            client.get_bars("GARAN", "2026-01-01", "2026-01-31")

    def test_allowed_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BIST_CORE_NETWORK_ENABLED", "1")
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_BARS)):
            client = MatriksClient(token="tok")
            bars = client.get_bars("GARAN", "2026-01-01", "2026-01-31")
            assert len(bars) == 2


# ── Authentication ────────────────────────────────────────────────────────

class TestAuthentication:
    def test_bearer_token_in_header(self) -> None:
        client = MatriksClient(token="my_secret_token")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer my_secret_token"

    def test_no_auth_when_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MATRIKS_API_TOKEN", raising=False)
        client = MatriksClient(token="")
        headers = client._headers()
        assert "Authorization" not in headers

    def test_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MATRIKS_API_TOKEN", "env_token_123")
        client = MatriksClient()
        headers = client._headers()
        assert headers["Authorization"] == "Bearer env_token_123"


# ── Error handling ────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_empty_response_raises(self) -> None:
        resp = _mock_response(b"")
        with patch("bist_core.data.matriks_client.urlopen", return_value=resp):
            client = MatriksClient(token="t")
            with pytest.raises(MatriksAPIError, match="Empty response"):
                client.get_bars("X", "2026-01-01", "2026-01-31")

    def test_malformed_json_raises(self) -> None:
        resp = _mock_response(b"not json at all{{{")
        with patch("bist_core.data.matriks_client.urlopen", return_value=resp):
            client = MatriksClient(token="t")
            with pytest.raises(MatriksAPIError, match="Malformed JSON"):
                client.get_bars("X", "2026-01-01", "2026-01-31")

    def test_http_error_raises(self) -> None:
        from urllib.error import HTTPError
        exc = HTTPError("url", 403, "Forbidden", {}, BytesIO(b""))
        with patch("bist_core.data.matriks_client.urlopen", side_effect=exc):
            client = MatriksClient(token="t")
            with pytest.raises(MatriksAPIError, match="403"):
                client.get_bars("X", "2026-01-01", "2026-01-31")

    def test_url_error_raises(self) -> None:
        from urllib.error import URLError
        exc = URLError("Connection refused")
        with patch("bist_core.data.matriks_client.urlopen", side_effect=exc):
            client = MatriksClient(token="t")
            with pytest.raises(MatriksAPIError, match="URL error"):
                client.get_bars("X", "2026-01-01", "2026-01-31")

    def test_unexpected_response_type_raises(self) -> None:
        resp = _mock_response(b'"just a string"')
        with patch("bist_core.data.matriks_client.urlopen", return_value=resp):
            client = MatriksClient(token="t")
            with pytest.raises(MatriksAPIError, match="Unexpected response"):
                client.get_bars("X", "2026-01-01", "2026-01-31")

    def test_dict_without_bars_key_raises(self) -> None:
        resp = _mock_response({"status": "ok"})
        with patch("bist_core.data.matriks_client.urlopen", return_value=resp):
            client = MatriksClient(token="t")
            with pytest.raises(MatriksAPIError, match="no bar list"):
                client.get_bars("X", "2026-01-01", "2026-01-31")


# ── Bar fetching ──────────────────────────────────────────────────────────

class TestBarFetching:
    def test_get_bars_list_response(self) -> None:
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_BARS)):
            client = MatriksClient(token="t")
            bars = client.get_bars("GARAN", "2026-01-15", "2026-01-16")
            assert len(bars) == 2
            assert bars[0]["symbol"] == "GARAN"

    def test_get_bars_dict_with_bars_key(self) -> None:
        payload = {"bars": _SAMPLE_BARS, "meta": {}}
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(payload)):
            client = MatriksClient(token="t")
            bars = client.get_bars("GARAN", "2026-01-15", "2026-01-16")
            assert len(bars) == 2

    def test_get_bars_dict_with_data_key(self) -> None:
        payload = {"data": _SAMPLE_BARS}
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(payload)):
            client = MatriksClient(token="t")
            bars = client.get_bars("GARAN", "2026-01-15", "2026-01-16")
            assert len(bars) == 2

    def test_base_url_configurable(self) -> None:
        client = MatriksClient(base_url="https://custom.api.com/v2/", token="t")
        assert client.base_url == "https://custom.api.com/v2"


# ── Adapter integration ──────────────────────────────────────────────────

class TestAdapterIntegration:
    def test_fetch_and_prepare_bars(self) -> None:
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_BARS)):
            client = MatriksClient(token="t")
            bars = fetch_and_prepare_bars("GARAN", "2026-01-15", "2026-01-16", client=client)
            assert len(bars) == 2
            assert bars[0].symbol == "GARAN"
            assert bars[0].timestamp < bars[1].timestamp

    def test_fetch_and_prepare_rejects_zero_volume(self) -> None:
        raw = [
            {"symbol": "X", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 0},
            {"symbol": "X", "date": "2026-01-02", "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 100},
        ]
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(raw)):
            client = MatriksClient(token="t")
            bars = fetch_and_prepare_bars("X", "2026-01-01", "2026-01-02", client=client, reject_zero_volume=True)
            assert len(bars) == 1
            assert bars[0].volume == 100

    def test_fetch_and_prepare_network_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BIST_CORE_NETWORK_ENABLED", raising=False)
        with pytest.raises(NetworkDisabledError):
            fetch_and_prepare_bars("X", "2026-01-01", "2026-01-02")


# ── Determinism ───────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_response_same_output(self) -> None:
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_BARS)):
            c = MatriksClient(token="t")
            r1 = c.get_bars("GARAN", "2026-01-15", "2026-01-16")
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_BARS)):
            c = MatriksClient(token="t")
            r2 = c.get_bars("GARAN", "2026-01-15", "2026-01-16")
        assert r1 == r2
