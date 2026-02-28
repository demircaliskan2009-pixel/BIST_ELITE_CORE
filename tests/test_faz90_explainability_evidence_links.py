"""FAZ90: Explainability — reasons[], evidence_refs[]; explain.json linked from dossier evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


from bist_core.advisory.explain import EXPLAIN_SCHEMA_VERSION, build_explain, write_explain
from bist_core.dossier.write import update_dossier_evidence, write_dossier


def test_faz90_build_explain_deterministic() -> None:
    """Same reasons + evidence_refs -> same explain dict and same file hash."""
    reasons = ["signal strength above threshold", "portfolio rebalance rule"]
    evidence_refs = ["advice_path", "dossier/2025-01-23/dossier.json"]

    out1 = build_explain(reasons, evidence_refs)
    out2 = build_explain(reasons, evidence_refs)
    assert out1 == out2
    assert out1["schema_version"] == EXPLAIN_SCHEMA_VERSION
    assert out1["reasons"] == sorted(reasons)
    assert out1["evidence_refs"] == sorted(evidence_refs)


def test_faz90_explain_same_input_same_output_hash(tmp_path: Path) -> None:
    """Identical reasons/evidence_refs -> byte-identical explain.json."""
    reasons = ["rule A", "rule B"]
    refs = ["ref1", "ref2"]
    data = build_explain(reasons, refs)
    p1 = tmp_path / "out1" / "explain.json"
    p2 = tmp_path / "out2" / "explain.json"
    write_explain(p1, data)
    write_explain(p2, data)
    assert hashlib.sha256(p1.read_bytes()).hexdigest() == hashlib.sha256(p2.read_bytes()).hexdigest()


def test_faz90_explain_structure() -> None:
    """build_explain produces schema_version, reasons (sorted), evidence_refs (sorted)."""
    data = build_explain(["z", "a"], ["path2", "path1"])
    assert data["schema_version"] == 1
    assert data["reasons"] == ["a", "z"]
    assert data["evidence_refs"] == ["path1", "path2"]


def test_faz90_dossier_evidence_links_explain_path(tmp_path: Path) -> None:
    """explain.json path is linked in dossier evidence via update_dossier_evidence."""
    day = "2025-01-23"
    outdir = tmp_path / "out"
    explain_path = outdir / day / "explain.json"
    explain_path.parent.mkdir(parents=True, exist_ok=True)

    explain_data = build_explain(
        ["advisory rebalance triggered"],
        ["advice_path", "advisory_plan.json"],
    )
    write_explain(explain_path, explain_data)
    assert explain_path.is_file()

    # Create initial dossier
    write_dossier(day, outdir, {"advice_path": str(outdir / day / "advice.jsonl")})
    dossier_file = outdir / "dossier" / day / "dossier.json"
    assert dossier_file.is_file()
    before = json.loads(dossier_file.read_text(encoding="utf-8"))
    assert "explain_path" not in before.get("evidence", {})

    # Link explain_path into dossier
    updated = update_dossier_evidence(outdir, day, {"explain_path": str(explain_path)})
    assert updated is not None
    after = json.loads(dossier_file.read_text(encoding="utf-8"))
    assert after["evidence"]["explain_path"] == str(explain_path)
