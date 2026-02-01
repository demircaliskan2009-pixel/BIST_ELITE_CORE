"""
FAZ98: trace_id generation in one place; inject into log/event payloads via get_trace_id().
Single source: generate_trace_id(); context: set_trace_id / get_trace_id / with_trace_id.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

_trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def generate_trace_id() -> str:
    """Generate a new trace_id (UUID4 hex). Single place for trace_id creation."""
    return uuid.uuid4().hex


def get_trace_id() -> Optional[str]:
    """Return current trace_id from context, or None."""
    return _trace_id_var.get()


def set_trace_id(trace_id: Optional[str]) -> None:
    """Set current trace_id in context. Pass None to clear."""
    _trace_id_var.set(trace_id)


@contextmanager
def with_trace_id(trace_id: Optional[str] = None) -> Iterator[str]:
    """
    Context manager: set trace_id for the block (generate if not provided), then clear on exit.
    """
    tid = trace_id if trace_id is not None else generate_trace_id()
    token = _trace_id_var.set(tid)
    try:
        yield tid
    finally:
        _trace_id_var.reset(token)


def inject_trace_id(payload: dict) -> dict:
    """
    Inject current trace_id into a dict (e.g. event payload). Mutates and returns payload.
    Only adds trace_id if get_trace_id() is set and key not already present.
    """
    if "trace_id" in payload:
        return payload
    tid = get_trace_id()
    if tid is not None:
        payload["trace_id"] = tid
    return payload


__all__ = ["generate_trace_id", "get_trace_id", "set_trace_id", "with_trace_id", "inject_trace_id"]
