"""FAZ73: Link graph between knowledge docs <-> advice records <-> dossier evidence. Stable ids, deterministic ordering."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.graph.link_graph import (
    LINK_GRAPH_SCHEMA_VERSION,
    NODE_DOSSIER,
    write_link_graph,
    _collect_knowledge_doc_ids,
    _collect_advice_record_ids,
    _collect_evidence_keys,
)


def test_write_link_graph_output_path(tmp_path: Path) -> None:
    """write_link_graph writes outdir/graph/<day>/links.json."""
    day = "2025-01-15"
    out = write_link_graph(day, tmp_path)
    assert out == tmp_path / "graph" / day / "links.json"
    assert out.is_file()


def test_links_json_schema_and_ordering(tmp_path: Path) -> None:
    """links.json has schema_version, day, nodes (knowledge_docs, advice_records, evidence, dossier), links; deterministic ordering."""
    day = "2025-01-15"
    write_link_graph(day, tmp_path)
    data = json.loads((tmp_path / "graph" / day / "links.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == LINK_GRAPH_SCHEMA_VERSION
    assert data["day"] == day
    assert "nodes" in data
    nodes = data["nodes"]
    assert "knowledge_docs" in nodes
    assert "advice_records" in nodes
    assert "evidence" in nodes
    assert "dossier" in nodes
    assert isinstance(nodes["knowledge_docs"], list)
    assert isinstance(nodes["advice_records"], list)
    assert isinstance(nodes["evidence"], list)
    assert "links" in data
    assert isinstance(data["links"], list)
    # Deterministic: keys in JSON are sorted (sort_keys=True)
    raw = (tmp_path / "graph" / day / "links.json").read_text(encoding="utf-8")
    assert '"day"' in raw
    assert '"links"' in raw
    assert '"nodes"' in raw
    assert '"schema_version"' in raw


def test_link_graph_with_research_and_advice(tmp_path: Path) -> None:
    """When research entries and advice records exist, nodes and links include them."""
    day = "2025-01-15"
    research_dir = tmp_path / day / "research"
    research_dir.mkdir(parents=True)
    entries_path = research_dir / "entries.jsonl"
    entries_path.write_text(
        '{"id": "doc-a", "day": "2025-01-15", "source": "kap", "title": "T1", "body": "", "tickers": ["X"]}\n'
        '{"id": "doc-b", "day": "2025-01-15", "source": "kap", "title": "T2", "body": "", "tickers": []}\n',
        encoding="utf-8",
    )
    advice_dir = tmp_path / "advice" / day
    advice_dir.mkdir(parents=True)
    advice_path = advice_dir / "advice_records.jsonl"
    advice_path.write_text(
        '{"symbol": "THYAO", "score": 0.1, "side": "BUY", "reason": "r", "inputs": {"close": 42.0}}\n'
        '{"symbol": "AKBNK", "score": -0.05, "side": "SELL", "reason": "r", "inputs": {"close": 38.0}}\n',
        encoding="utf-8",
    )
    dossier_dir = tmp_path / "dossier" / day
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "dossier.json"
    dossier_path.write_text(
        json.dumps({
            "schema_version": 1,
            "day": day,
            "evidence": {"advice_path": str(advice_path), "research_path": str(research_dir), "orders_intent_path": ""},
            "dossier_json_path": str(dossier_path),
        }, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    out = write_link_graph(
        day, tmp_path,
        research_path=research_dir,
        advice_path=advice_path,
        dossier_json_path=dossier_path,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["nodes"]["knowledge_docs"]) == 2
    assert "doc-a" in data["nodes"]["knowledge_docs"]
    assert "doc-b" in data["nodes"]["knowledge_docs"]
    assert data["nodes"]["knowledge_docs"] == sorted(data["nodes"]["knowledge_docs"])
    assert len(data["nodes"]["advice_records"]) == 2
    assert data["nodes"]["advice_records"] == sorted(data["nodes"]["advice_records"])
    assert "advice_path" in data["nodes"]["evidence"]
    assert "research_path" in data["nodes"]["evidence"]
    assert "orders_intent_path" in data["nodes"]["evidence"]
    assert data["nodes"]["evidence"] == sorted(data["nodes"]["evidence"])
    assert data["nodes"]["dossier"] == str(dossier_path)
    links = data["links"]
    doc_to_evidence = [l for l in links if l["type"] == "doc_to_evidence"]
    advice_to_evidence = [l for l in links if l["type"] == "advice_to_evidence"]
    evidence_in_dossier = [l for l in links if l["type"] == "evidence_in_dossier"]
    assert len(doc_to_evidence) == 2
    assert all(l["to"] == "research_path" for l in doc_to_evidence)
    assert len(advice_to_evidence) == 2
    assert all(l["to"] == "advice_path" for l in advice_to_evidence)
    assert len(evidence_in_dossier) == 3
    assert all(l["to"] == NODE_DOSSIER for l in evidence_in_dossier)
    assert links == sorted(links, key=lambda x: (x["type"], x["from"], x["to"]))


def test_deterministic_ordering_same_inputs_same_output(tmp_path: Path) -> None:
    """Same inputs produce identical links.json (stable ids and link order)."""
    day = "2025-01-16"
    research_dir = tmp_path / day / "research"
    research_dir.mkdir(parents=True)
    (research_dir / "entries.jsonl").write_text(
        '{"id": "k1", "day": "2025-01-16", "source": "s", "title": "T", "body": "", "tickers": []}\n',
        encoding="utf-8",
    )
    advice_dir = tmp_path / "advice" / day
    advice_dir.mkdir(parents=True)
    advice_path = advice_dir / "advice_records.jsonl"
    advice_path.write_text('{"symbol": "X", "score": 0.0, "side": "HOLD", "reason": "r", "inputs": {"close": 1.0}}\n', encoding="utf-8")
    dossier_dir = tmp_path / "dossier" / day
    dossier_dir.mkdir(parents=True)
    dossier_path = dossier_dir / "dossier.json"
    dossier_path.write_text(
        json.dumps({"schema_version": 1, "day": day, "evidence": {"advice_path": "x", "research_path": "y"}, "dossier_json_path": str(dossier_path)}, sort_keys=True),
        encoding="utf-8",
    )
    out1 = write_link_graph(day, tmp_path, research_path=research_dir, advice_path=advice_path, dossier_json_path=dossier_path)
    out2 = write_link_graph(day, tmp_path, research_path=research_dir, advice_path=advice_path, dossier_json_path=dossier_path)
    text1 = out1.read_text(encoding="utf-8")
    text2 = out2.read_text(encoding="utf-8")
    assert text1 == text2
    assert json.loads(text1) == json.loads(text2)


def test_collect_knowledge_doc_ids_uses_id_or_doc_id(tmp_path: Path) -> None:
    """_collect_knowledge_doc_ids uses entry 'id' or 'doc_id' for stable id."""
    path = tmp_path / "entries.jsonl"
    path.write_text(
        '{"id": "my-doc-1", "day": "2025-01-15", "source": "kap"}\n'
        '{"doc_id": "my-doc-2", "day": "2025-01-15"}\n',
        encoding="utf-8",
    )
    ids = _collect_knowledge_doc_ids(tmp_path)
    assert "my-doc-1" in ids
    assert "my-doc-2" in ids
    assert ids == sorted(ids)


def test_collect_advice_record_ids_stable_per_line(tmp_path: Path) -> None:
    """_collect_advice_record_ids returns stable sha256-based ids, sorted."""
    path = tmp_path / "advice_records.jsonl"
    path.write_text(
        '{"symbol": "A", "score": 0.1, "side": "BUY", "reason": "r", "inputs": {"close": 10.0}}\n'
        '{"symbol": "B", "score": -0.1, "side": "SELL", "reason": "r", "inputs": {"close": 20.0}}\n',
        encoding="utf-8",
    )
    ids = _collect_advice_record_ids(path)
    assert len(ids) == 2
    assert all(len(i) == 16 and all(c in "0123456789abcdef" for c in i) for i in ids)
    assert ids == sorted(ids)


def test_collect_evidence_keys_from_dossier(tmp_path: Path) -> None:
    """_collect_evidence_keys returns sorted keys from dossier.json evidence."""
    path = tmp_path / "dossier.json"
    path.write_text(
        json.dumps({"evidence": {"advice_path": "x", "research_path": "y", "orders_intent_path": "z"}, "day": "2025-01-15"}, sort_keys=True),
        encoding="utf-8",
    )
    keys = _collect_evidence_keys(path)
    assert keys == ["advice_path", "orders_intent_path", "research_path"]


def test_empty_inputs_still_writes_valid_links(tmp_path: Path) -> None:
    """When no research/advice/dossier paths, write_link_graph still writes valid links.json with empty nodes."""
    day = "2025-01-17"
    out = write_link_graph(day, tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["nodes"]["knowledge_docs"] == []
    assert data["nodes"]["advice_records"] == []
    assert data["nodes"]["evidence"] == []
    assert data["nodes"]["dossier"] == ""
    assert data["links"] == []
