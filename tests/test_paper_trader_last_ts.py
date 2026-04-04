"""Tests for _last_bar_ts helper — timestamp extraction from various bar formats."""

from types import SimpleNamespace

from bist_core.live.paper_trader import _last_bar_ts


def test_last_bar_ts_str_attr():
    b = [SimpleNamespace(timestamp="2026-03-17T12:00:00Z")]
    assert _last_bar_ts(b) == "2026-03-17T12:00:00Z"


def test_last_bar_ts_int_attr():
    b = [SimpleNamespace(timestamp=1679035200)]
    assert _last_bar_ts(b) == "1679035200"


def test_last_bar_ts_time_attr():
    b = [SimpleNamespace(time="2026-03-17T12:00:00Z")]
    assert _last_bar_ts(b) == "2026-03-17T12:00:00Z"


def test_last_bar_ts_dict_item():
    b = [{"time": "2026-03-17T12:00:00Z"}]
    assert _last_bar_ts(b) == "2026-03-17T12:00:00Z"


def test_last_bar_ts_empty():
    assert _last_bar_ts([]) is None
