"""Connectors: KAP, Matriks terminal and other disclosure/data ingesters (fixture-first, no network in tests)."""
from bist_core.connectors.kap import ingest_from_html, ingest_from_json, normalize_to_knowledge_doc
from bist_core.connectors.matriks_terminal_adapter import MatriksTerminalAdapter

__all__ = [
    "ingest_from_html",
    "ingest_from_json",
    "normalize_to_knowledge_doc",
    "MatriksTerminalAdapter",
]
