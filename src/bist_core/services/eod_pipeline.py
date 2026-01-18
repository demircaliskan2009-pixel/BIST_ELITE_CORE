from __future__ import annotations

from datetime import date as Date
import json
import os
from pathlib import Path
import platform
import time
from typing import Iterable, Optional

from bist_core.services.advisor import build_advice_for_symbol
from bist_core.services.dossier import (
    atomic_write_json,
    build_dossiers_for_day,
    build_manifest,
)
from bist_core.services.marketdata import MarketData


def run_eod_pipeline(
    day: Date | str,
    snapshot_root: Path | str,
    outdir: Path | str,
    strict: bool = False,
    symbols: Optional[list[str]] = None,
    regex: Optional[str] = None,
    limit: Optional[int] = None,
    jsonl: bool = True,
    git_sha: Optional[str] = None,
    cli_args: Optional[dict] = None,
) -> tuple[dict, int]:
    start = time.perf_counter()
    day_str = day.isoformat() if isinstance(day, Date) else str(day)
    root = Path(snapshot_root)
    out_path = Path(outdir)
    out_path.mkdir(parents=True, exist_ok=True)

    snapshot_path = root / day_str / "snapshot.csv"
    stages = {
        "snapshot": {"ok": True, "errors": 0, "notes": []},
        "advice": {"total": 0, "ok": 0, "errors": 0, "path": ""},
        "dossier": {"total": 0, "ok": 0, "errors": 0, "path": ""},
    }

    if not snapshot_path.exists():
        stages["snapshot"]["ok"] = False
        stages["snapshot"]["errors"] = 1
        stages["snapshot"]["notes"] = ["snapshot_missing"]
        runtime_ms = int((time.perf_counter() - start) * 1000)
        manifest = _pipeline_manifest(
            day_str,
            root,
            out_path,
            stages,
            runtime_ms,
            git_sha=git_sha,
            cli_args=cli_args or {},
        )
        atomic_write_json(out_path / "_pipeline_manifest.json", manifest)
        return manifest, 2 if strict else 0

    base_symbols = _load_symbols(root, day_str)
    filtered = _filter_symbols(base_symbols, symbols, regex, limit)
    sorted_symbols = sorted(filtered)

    advice_path = out_path / ("advice.jsonl" if jsonl else "advice.json")
    advice_records, advice_errors = _build_advice_records(
        sorted_symbols,
        day_str,
        root,
    )
    _write_advice(advice_path, advice_records, jsonl=jsonl)
    stages["advice"] = {
        "total": len(advice_records),
        "ok": len(advice_records) - advice_errors,
        "errors": advice_errors,
        "path": str(advice_path),
    }

    dossier_dir = out_path / "dossiers"
    dossier_dir.mkdir(parents=True, exist_ok=True)
    dossiers, runtime_ms, dossier_prov = build_dossiers_for_day(
        day_str,
        root=root,
        symbols=symbols,
        regex=regex,
        limit=limit,
    )
    dossiers_sorted = sorted(
        dossiers, key=lambda d: d.get("symbol", "")
    )
    for dossier in dossiers_sorted:
        symbol = dossier.get("symbol", "UNKNOWN")
        atomic_write_json(dossier_dir / f"{symbol}.json", dossier)
    dossier_manifest = build_manifest(
        day_str,
        dossier_dir,
        dossiers_sorted,
        runtime_ms,
        dossier_prov,
    )
    atomic_write_json(dossier_dir / "_manifest.json", dossier_manifest)
    stages["dossier"] = {
        "total": dossier_manifest["total"],
        "ok": dossier_manifest["ok"],
        "errors": dossier_manifest["errors"],
        "path": str(dossier_dir),
    }

    runtime_ms = int((time.perf_counter() - start) * 1000)
    manifest = _pipeline_manifest(
        day_str,
        root,
        out_path,
        stages,
        runtime_ms,
        git_sha=git_sha,
        cli_args=cli_args or {},
    )
    atomic_write_json(out_path / "_pipeline_manifest.json", manifest)

    stage_errors = (
        stages["snapshot"]["errors"]
        + stages["advice"]["errors"]
        + stages["dossier"]["errors"]
    )
    return manifest, 2 if strict and stage_errors > 0 else 0


def _pipeline_manifest(
    day_str: str,
    snapshot_root: Path,
    outdir: Path,
    stages: dict,
    runtime_ms: int,
    git_sha: Optional[str],
    cli_args: dict,
) -> dict:
    return {
        "schema_version": 1,
        "day": day_str,
        "snapshot_root": str(snapshot_root),
        "outdir": str(outdir),
        "stages": stages,
        "runtime_ms": int(runtime_ms),
        "provenance": {
            "python": _python_version(),
            "platform": platform.platform(),
            "cli_args": cli_args,
            "git_sha": git_sha,
        },
    }


def _build_advice_records(
    symbols: Iterable[str],
    day_str: str,
    snapshot_root: Path,
) -> tuple[list[dict], int]:
    records: list[dict] = []
    errors = 0
    for symbol in symbols:
        try:
            advice = build_advice_for_symbol(symbol, day_str, root=snapshot_root)
            payload = {
                "symbol": advice.symbol,
                "day": day_str,
                "decision_raw": advice.decision_raw,
                "score": advice.score,
                "signals": advice.signals,
                "plan": advice.plan,
                "text": advice.text,
            }
            if isinstance(advice.text, str) and "Güvenli mod" in advice.text:
                errors += 1
        except Exception as exc:
            err = exc.__class__.__name__
            payload = {
                "symbol": symbol,
                "day": day_str,
                "decision_raw": "PASS",
                "score": 0.0,
                "signals": [],
                "plan": None,
                "text": (
                    f"Güvenli mod: {err}. "
                    "Veri veya karar üretilemedi; snapshot ve konfigürasyonu kontrol edin."
                ),
            }
            errors += 1
        records.append(payload)
    return records, errors


def _write_advice(path: Path, records: list[dict], jsonl: bool) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    if jsonl:
        with tmp_path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False))
                f.write("\n")
    else:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def _load_symbols(snapshot_root: Path, day_str: str) -> list[str]:
    try:
        md = MarketData(snapshot_root)
        return md.symbols(day_str)
    except Exception:
        return []


def _filter_symbols(
    base_symbols: list[str],
    symbols: Optional[list[str]],
    regex: Optional[str],
    limit: Optional[int],
) -> list[str]:
    ordered = list(base_symbols)
    if symbols:
        requested = [s for s in symbols if s]
        requested_set = set(requested)
        ordered = [s for s in ordered if s in requested_set]
        missing = [s for s in requested if s not in set(ordered)]
        ordered.extend(missing)

    if regex:
        try:
            import re

            matcher = re.compile(regex)
            ordered = [s for s in ordered if matcher.search(s)]
        except re.error:
            ordered = []

    if isinstance(limit, int) and limit >= 0:
        ordered = ordered[:limit]

    return ordered


def _python_version() -> str:
    return os.sys.version.split()[0]
