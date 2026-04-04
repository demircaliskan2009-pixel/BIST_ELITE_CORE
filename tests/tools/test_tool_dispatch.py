from __future__ import annotations

from bist_core.tools.tool_dispatch import dispatch_tool


def test_dispatch_tool_debug_symbol(monkeypatch) -> None:
    monkeypatch.setattr(
        "bist_core.tools.tool_dispatch.inspect_symbol_state",
        lambda symbol: {"status": "ok", "symbol": symbol, "score_breakdown": {}, "current_price_context": {}},
    )

    got = dispatch_tool("debug_symbol", {"symbol": "ASELS"})

    assert got["status"] == "ok"
    assert got["intent"] == "debug_symbol"
    assert got["symbols"] == ["ASELS"]
    assert got["data"]["symbol"] == "ASELS"


def test_dispatch_tool_fails_closed_for_unsupported_intent() -> None:
    got = dispatch_tool("unknown_tool", {"symbol": "ASELS"})

    assert got["status"] == "rejected"
    assert got["output"] == "INSUFFICIENT EVIDENCE"


def test_dispatch_tool_fails_closed_when_tool_returns_rejection(monkeypatch) -> None:
    monkeypatch.setattr(
        "bist_core.tools.tool_dispatch.validate_dataset",
        lambda symbol: {"status": "rejected", "reason": "SYMBOL NOT FOUND", "output": "INSUFFICIENT EVIDENCE"},
    )

    got = dispatch_tool("debug_dataset", {"symbol": "MISSING"})

    assert got["status"] == "rejected"
    assert got["output"] == "INSUFFICIENT EVIDENCE"
