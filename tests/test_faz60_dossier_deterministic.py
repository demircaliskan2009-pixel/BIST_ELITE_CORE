"""
FAZ60: Dossier writer linking advice + research + risk decisions.
Tests: deterministic output (stable ordering), evidence pointers, manifest inclusion.
"""

from __future__ import annotations

import json
from pathlib import Path


from bist_core.dossier import write_dossier


def test_faz60_dossier_writes_deterministic_path(tmp_path: Path) -> None:
    """write_dossier writes outdir/dossier/<day>/dossier.json."""
    day = "2099-01-15"
    evidence = {"advice_path": str(tmp_path / "advice.jsonl"), "dossier_path": str(tmp_path / "dossiers")}
    out = write_dossier(day, tmp_path, evidence)
    assert out == tmp_path / "dossier" / day / "dossier.json"
    assert out.is_file()


def test_faz60_dossier_stable_ordering(tmp_path: Path) -> None:
    """Same evidence -> same JSON output (stable key order and content)."""
    day = "2099-01-16"
    evidence = {
        "advice_path": str(tmp_path / "a.jsonl"),
        "dossier_path": str(tmp_path / "dossiers"),
        "research_path": str(tmp_path / "research"),
        "risk_notes": ["note_b", "note_a"],
    }
    out1 = write_dossier(day, tmp_path, evidence)
    content1 = out1.read_text(encoding="utf-8")
    out2 = write_dossier(day, tmp_path, evidence)
    content2 = out2.read_text(encoding="utf-8")
    assert content1 == content2
    data = json.loads(content1)
    assert data["day"] == day
    assert data["schema_version"] == 1
    assert "evidence" in data
    assert data["evidence"]["advice_path"] == str(tmp_path / "a.jsonl")
    assert data["evidence"]["risk_notes"] == ["note_a", "note_b"]


def test_faz60_dossier_evidence_pointers(tmp_path: Path) -> None:
    """Evidence includes paths and optional hashes."""
    (tmp_path / "advice.jsonl").write_text('{"x":1}\n', encoding="utf-8")
    day = "2099-01-17"
    evidence = {
        "advice_path": str(tmp_path / "advice.jsonl"),
        "dossier_path": str(tmp_path / "dossiers"),
    }
    out = write_dossier(day, tmp_path, evidence)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["evidence"]["advice_path"] == str(tmp_path / "advice.jsonl")
    assert "advice_sha256" in data["evidence"] or "dossier_path" in data["evidence"]
    assert data["dossier_json_path"] == str(out)


def test_faz60_dossier_snapshot_hash_in_evidence(tmp_path: Path) -> None:
    """snapshot_hash in evidence -> snapshot_sha256 in output."""
    day = "2099-01-18"
    evidence = {
        "advice_path": str(tmp_path / "a.jsonl"),
        "dossier_path": str(tmp_path / "dossiers"),
        "snapshot_hash": {"value": "abc123", "algo": "sha256"},
    }
    out = write_dossier(day, tmp_path, evidence)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["evidence"]["snapshot_sha256"] == "abc123"


def test_faz60_dossier_risk_allowed(tmp_path: Path) -> None:
    """risk_allowed in evidence -> in payload."""
    day = "2099-01-19"
    evidence = {
        "advice_path": str(tmp_path / "a.jsonl"),
        "dossier_path": str(tmp_path / "dossiers"),
        "risk_allowed": False,
        "risk_notes": ["blocked"],
    }
    out = write_dossier(day, tmp_path, evidence)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["risk_allowed"] is False
    assert data["evidence"]["risk_notes"] == ["blocked"]
