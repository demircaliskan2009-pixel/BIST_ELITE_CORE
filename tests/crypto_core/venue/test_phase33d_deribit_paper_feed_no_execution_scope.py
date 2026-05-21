from __future__ import annotations

import ast
import inspect
from pathlib import Path

import crypto_core.venue.deribit_paper_feed as paper_feed

SOURCE = Path("src/crypto_core/venue/deribit_paper_feed.py")
DOC = Path("docs/crypto_core/DERIBIT_PAPER_FEED_PIPELINE_33A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_33F.md")


def test_phase33d_paper_feed_module_has_no_network_or_execution_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
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
    assert {"authenticate", "cancel_order", "create_order", "login", "place_order", "submit_order"}.isdisjoint(
        function_names
    )


def test_phase33d_paper_feed_source_avoids_trading_runtime_scope() -> None:
    source = inspect.getsource(paper_feed).lower()

    for forbidden in (
        "api_key",
        "api_secret",
        "crypto_core.execution",
        "crypto_core.service",
        "executionmode.live",
        "orderintent",
        "place_order",
        "submit_order",
        "shadow_execution",
    ):
        assert forbidden not in source
    assert "os.environ" not in source
    assert "getenv" not in source


def test_phase33d_docs_and_source_do_not_reference_legacy_equity_system() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (SOURCE, DOC, SUMMARY))

    assert "BIST" not in combined
