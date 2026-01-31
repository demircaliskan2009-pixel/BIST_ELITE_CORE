"""Connectors: KAP and other disclosure/data ingesters (fixture-first, no network in tests)."""
from bist_core.connectors.kap import ingest_from_html, ingest_from_json, normalize_to_knowledge_doc

__all__ = ["ingest_from_html", "ingest_from_json", "normalize_to_knowledge_doc"]
