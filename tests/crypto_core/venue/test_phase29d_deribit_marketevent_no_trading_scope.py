from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path("src/crypto_core/venue/deribit_marketevent_normalizer.py")


def test_phase29d_normalizer_has_no_network_or_trading_imports_or_methods() -> None:
    source = SOURCE.read_text(encoding="utf-8").lower()
    tree = ast.parse(source)
    imports: set[str] = set()
    function_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            function_names.add(node.name)

    assert {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}.isdisjoint(imports)
    assert {"connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)
    for forbidden in (
        "api_key",
        "api_secret",
        "getenv",
        "place_order",
        "submit_order",
        "cancel_order",
        "executionmode.live",
        "paper_execution",
        "shadow_execution",
    ):
        assert forbidden not in source


def test_phase29d_new_docs_and_source_do_not_reference_legacy_equity_system() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            SOURCE,
            Path("docs/crypto_core/DERIBIT_MARKETEVENT_NORMALIZATION_29A.md"),
            Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_29F.md"),
        )
    )

    assert "BIST" not in combined
