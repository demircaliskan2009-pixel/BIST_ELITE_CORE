from __future__ import annotations

import csv
import shutil
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Dict, List


def detect_malformed_snapshot_rows(path: Path) -> List[Dict[str, object]]:
    """
    FAZ549: Detect malformed rows in snapshot.csv. Returns list of invalid rows with line_no, reason.
    Deterministic: same file -> same result. Fail-closed: malformed -> skip row, continue.
    """
    invalid: List[Dict[str, object]] = []
    if not path.is_file():
        return invalid
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):
                sym = (row.get("symbol") or "").strip()
                if not sym:
                    invalid.append({"line_no": i, "reason": "missing_symbol", "row": dict(row)})
                    continue
                c = row.get("close")
                if c is None or (isinstance(c, str) and c.strip() == ""):
                    invalid.append({"line_no": i, "reason": "missing_close", "row": dict(row)})
                    continue
                try:
                    val = float(c)
                    if not (val > 0 and val < 1e12):
                        invalid.append({"line_no": i, "reason": "invalid_close_range", "row": dict(row)})
                except (TypeError, ValueError):
                    invalid.append({"line_no": i, "reason": "invalid_close_numeric", "row": dict(row)})
    except (OSError, csv.Error):
        invalid.append({"line_no": 0, "reason": "read_error", "row": {}})
    return invalid


def build_invalid_rows_report(invalid: List[Dict[str, object]]) -> Dict[str, object]:
    """
    FAZ550: Build report from invalid rows. Deterministic: same invalid list -> same report.
    """
    return {
        "schema_version": 1,
        "invalid_count": len(invalid),
        "invalid_rows": invalid,
    }


def validate_snapshot(path: Path) -> tuple[int, Dict[str, object]]:
    """
    FAZ550: Validate snapshot; return (exit_code, report). Exit 0 when valid, 1 when invalid.
    """
    invalid = detect_malformed_snapshot_rows(path)
    report = build_invalid_rows_report(invalid)
    exit_code = 1 if invalid else 0
    return exit_code, report


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_snapshot_hash_manifest(snapshot_csv_path: Path) -> Dict[str, object]:
    day = snapshot_csv_path.parent.name
    size = snapshot_csv_path.stat().st_size
    return {
        "schema_version": 1,
        "day": day,
        "snapshot_path": str(snapshot_csv_path),
        "sha256": compute_sha256(snapshot_csv_path),
        "bytes": int(size),
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def build_eod_snapshot(
    day: str,
    snapshot_src_dir: Path | str,
    outdir: Path | str,
) -> Dict[str, object]:
    """
    Build EOD snapshot for a day: write <outdir>/<day>/snapshot.csv and
    <outdir>/<day>/_snapshot_hash.json (sha256). Source is taken from
    snapshot_src_dir/<day>/snapshot.csv or snapshot_src_dir/<day>.csv.
    Does NOT create outdir/<day>/ when source is missing (no side-effect).
    """
    src = Path(snapshot_src_dir)
    out = Path(outdir)
    src_csv = src / day / "snapshot.csv"
    src_alt = src / (day + ".csv")
    if src_csv.is_file():
        source_path = src_csv
    elif src_alt.is_file():
        source_path = src_alt
    else:
        raise FileNotFoundError(
            f"No snapshot source for day {day}: expected {src_csv} or {src_alt}"
        )

    day_dir = out / day
    day_dir.mkdir(parents=True, exist_ok=True)
    dest_csv = day_dir / "snapshot.csv"

    if source_path.resolve() != dest_csv.resolve():
        shutil.copy2(source_path, dest_csv)

    hash_manifest = build_snapshot_hash_manifest(dest_csv)
    atomic_write_json(day_dir / "_snapshot_hash.json", hash_manifest)
    return hash_manifest
