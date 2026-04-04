"""FAZ98: trace_id generation in one place; propagation into log/event payloads."""

from __future__ import annotations

import io
import json


from bist_core.cli.observability import log_struct
from bist_core.trace import (
    generate_trace_id,
    get_trace_id,
    inject_trace_id,
    set_trace_id,
    with_trace_id,
)


def test_faz98_generate_trace_id() -> None:
    """generate_trace_id returns non-empty string (single place for creation)."""
    tid = generate_trace_id()
    assert isinstance(tid, str)
    assert len(tid) >= 16
    assert tid.isalnum()
    assert generate_trace_id() != generate_trace_id()


def test_faz98_log_struct_injects_trace_id() -> None:
    """When trace_id is set, log_struct payload includes trace_id."""
    buf = io.StringIO()
    tid = generate_trace_id()
    set_trace_id(tid)
    try:
        log_struct("info", "TEST", "message", stream=buf)
        line = buf.getvalue().strip()
        payload = json.loads(line)
        assert payload.get("trace_id") == tid
        assert payload.get("level") == "info"
        assert payload.get("code") == "TEST"
    finally:
        set_trace_id(None)


def test_faz98_with_trace_id_propagates() -> None:
    """with_trace_id context: log_struct payload has trace_id."""
    buf = io.StringIO()
    with with_trace_id() as tid:
        log_struct("info", "TEST", "msg", stream=buf)
        payload = json.loads(buf.getvalue().strip())
        assert payload.get("trace_id") == tid
    assert get_trace_id() is None


def test_faz98_inject_trace_id_event_payload() -> None:
    """inject_trace_id adds trace_id to event dict when set."""
    with with_trace_id("abc123"):
        event = {"event": "eod_run", "day": "2025-01-01"}
        inject_trace_id(event)
        assert event.get("trace_id") == "abc123"
        assert event.get("event") == "eod_run"
    event2 = {"x": 1}
    inject_trace_id(event2)
    assert "trace_id" not in event2 or event2.get("trace_id") is None


def test_faz98_no_trace_id_when_unset() -> None:
    """When trace_id not set, log_struct payload has no trace_id (or omit key)."""
    set_trace_id(None)
    buf = io.StringIO()
    log_struct("info", "CODE", "msg", stream=buf)
    payload = json.loads(buf.getvalue().strip())
    assert "trace_id" not in payload or payload.get("trace_id") is None
