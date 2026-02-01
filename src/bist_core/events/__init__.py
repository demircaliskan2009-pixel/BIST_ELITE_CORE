"""Events ingest: KAP HTML -> events.json (hash + source, deterministic ids)."""
from __future__ import annotations

from bist_core.events.kap_ingest import ingest_kap_html, write_events_json

__all__ = ["ingest_kap_html", "write_events_json"]
