from __future__ import annotations

from datetime import date as Date
import json
import os
from pathlib import Path
import platform
import time
from typing import Iterable, Optional

from bist_core import config
from bist_core.services.advisor import build_advice_for_symbol
from bist_core.services.dossier import (
    atomic_write_json,
    build_dossiers_for_day,
    build_manifest,
)
from bist_core.services.marketdata import MarketData
from bist_core.services.events_pipeline import build_events_jsonl_for_day, ingest_events_from_file
from bist_core.providers.events.offline_file import OfflineFileEventsProvider
from bist_core.services import instrumentstore
from bist_core.providers.instruments.offline_file import OfflineFileInstrumentsProvider
from bist_core.services import castore
from bist_core.providers.corporate_actions.offline_file import (
    OfflineFileCorporateActionsProvider,
)
from bist_core.services import instrument_timeline
from bist_core.services import trading_calendar
from bist_core.services import snapshot_integrity


def run_eod_pipeline(
    day: Date | str,
    snapshot_root: Path | str,
    outdir: Path | str,
    strict: bool = False,
    symbols: Optional[list[str]] = None,
    regex: Optional[str] = None,
    limit: Optional[int] = None,
    jsonl: bool = True,
    events_provider: Optional[str] = None,
    events_input: Optional[Path | str] = None,
    events_outdir: Optional[Path | str] = None,
    instruments_provider: Optional[str] = None,
    instruments_input: Optional[Path | str] = None,
    instruments_outdir: Optional[Path | str] = None,
    ca_provider: Optional[str] = None,
    ca_input: Optional[Path | str] = None,
    ca_outdir: Optional[Path | str] = None,
    resolve_aliases: bool = False,
    calendar_file: Optional[Path | str] = None,
    ignore_calendar: bool = False,
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
        "events": {"total": 0, "ok": 0, "errors": 0, "path": "", "notes": []},
        "instruments": {"total": 0, "ok": 0, "errors": 0, "path": "", "notes": []},
        "corporate_actions": {"total": 0, "ok": 0, "errors": 0, "path": "", "notes": []},
        "universe": {"total": 0, "ok": 0, "errors": 0, "path": "", "notes": []},
        "calendar": {"ok": True, "errors": 0, "path": "", "notes": []},
    }
    instruments_manifest = None
    corporate_actions_manifest = None
    universe_manifest = None

    calendar_path = Path(calendar_file) if calendar_file is not None else None
    if ignore_calendar:
        stages["calendar"] = {"ok": True, "errors": 0, "path": "", "notes": ["ignored"]}
    else:
        calendar_gate = trading_calendar.gate_day(day_str, calendar_path)
        stages["calendar"] = {
            "ok": bool(calendar_gate["ok"]),
            "errors": len(calendar_gate["errors"]),
            "path": calendar_gate.get("path", ""),
            "notes": calendar_gate.get("notes", []),
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
        manifest["calendar"] = stages["calendar"]
        atomic_write_json(out_path / "_pipeline_manifest.json", manifest)
        stage_errors = (
            stages["snapshot"]["errors"]
            + stages["advice"]["errors"]
            + stages["dossier"]["errors"]
            + stages["events"]["errors"]
            + stages["instruments"]["errors"]
            + stages["corporate_actions"]["errors"]
            + stages["universe"]["errors"]
            + stages["calendar"]["errors"]
        )
        return manifest, 2 if strict and stage_errors > 0 else 0

    try:
        hash_manifest = snapshot_integrity.build_snapshot_hash_manifest(snapshot_path)
        snapshot_integrity.atomic_write_json(
            snapshot_path.parent / "_snapshot_hash.json",
            hash_manifest,
        )
    except Exception:
        stages["snapshot"]["errors"] += 1
        stages["snapshot"]["notes"] = stages["snapshot"]["notes"] + ["snapshot_hash_error"]

    if not stages["calendar"]["ok"]:
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
        manifest["calendar"] = stages["calendar"]
        atomic_write_json(out_path / "_pipeline_manifest.json", manifest)
        stage_errors = (
            stages["snapshot"]["errors"]
            + stages["advice"]["errors"]
            + stages["dossier"]["errors"]
            + stages["events"]["errors"]
            + stages["instruments"]["errors"]
            + stages["corporate_actions"]["errors"]
            + stages["universe"]["errors"]
            + stages["calendar"]["errors"]
        )
        return manifest, 2 if strict and stage_errors > 0 else 0

    base_symbols = _load_symbols(root, day_str)
    filtered = _filter_symbols(base_symbols, symbols, regex, limit)
    sorted_symbols = sorted(filtered)
    if resolve_aliases:
        try:
            instruments_path = (
                Path(instruments_outdir) / "instruments.jsonl"
                if instruments_outdir is not None
                else (config.REPO_ROOT / "data" / "eod" / "instruments" / day_str / "instruments.jsonl")
            )
            if instruments_input and not instruments_path.exists():
                instruments_path = Path(instruments_input)
            actions_path = (
                Path(ca_outdir) / "actions.jsonl"
                if ca_outdir is not None
                else (config.REPO_ROOT / "data" / "eod" / "corporate_actions" / day_str / "actions.jsonl")
            )
            timeline, errors = instrument_timeline.build_timeline(
                day_str,
                instruments_path,
                actions_path,
            )
            alias_map = timeline.get("alias_map", {})
            remapped = []
            seen = set()
            for sym in sorted_symbols:
                target = alias_map.get(sym, sym)
                if target not in seen:
                    remapped.append(target)
                    seen.add(target)
            sorted_symbols = remapped
            if errors:
                stages["universe"]["errors"] = len(errors)
                stages["universe"]["notes"] = ["alias_resolution_errors"]
        except Exception:
            stages["universe"]["errors"] = 1
            stages["universe"]["notes"] = ["alias_resolution_failed"]

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

    events_manifest = None
    if events_provider and (events_provider == "kap_html" or events_input):
        try:
            if events_provider == "kap_html":
                pull_dir = out_path / "events_pull" / day_str
                pull_dir.mkdir(parents=True, exist_ok=True)
                pull_out = pull_dir / "events.jsonl"
                provider = OfflineFileEventsProvider(Path(events_input)) if events_input else None
                if provider is None:
                    from bist_core.providers.events.kap_html import KapHtmlEventsProvider
                    provider = KapHtmlEventsProvider()
                pull_manifest = build_events_jsonl_for_day(
                    day_str,
                    provider,
                    pull_out,
                    atomic=True,
                )

                ingest_outdir = (
                    Path(events_outdir)
                    if events_outdir is not None
                    else config.REPO_ROOT / "data" / "eod" / "events" / day_str
                )
                ingest_outdir.mkdir(parents=True, exist_ok=True)
                ingest_manifest = ingest_events_from_file(
                    day_str,
                    pull_out,
                    ingest_outdir,
                )
                total_errors = pull_manifest["rejected"] + ingest_manifest["rejected"]
                stages["events"] = {
                    "total": pull_manifest["total_in"],
                    "ok": ingest_manifest["accepted"],
                    "errors": total_errors,
                    "path": str(ingest_outdir),
                    "notes": [],
                }
            elif events_provider != "offline_file":
                stages["events"]["errors"] = 1
                stages["events"]["notes"] = ["unsupported_provider"]
            else:
                pull_dir = out_path / "events_pull" / day_str
                pull_dir.mkdir(parents=True, exist_ok=True)
                pull_out = pull_dir / "events.jsonl"
                provider = OfflineFileEventsProvider(Path(events_input))
                pull_manifest = build_events_jsonl_for_day(
                    day_str,
                    provider,
                    pull_out,
                    atomic=True,
                )

                ingest_outdir = (
                    Path(events_outdir)
                    if events_outdir is not None
                    else config.REPO_ROOT / "data" / "eod" / "events" / day_str
                )
                ingest_outdir.mkdir(parents=True, exist_ok=True)
                ingest_manifest = ingest_events_from_file(
                    day_str,
                    pull_out,
                    ingest_outdir,
                )
                total_errors = pull_manifest["rejected"] + ingest_manifest["rejected"]
                stages["events"] = {
                    "total": pull_manifest["total_in"],
                    "ok": ingest_manifest["accepted"],
                    "errors": total_errors,
                    "path": str(ingest_outdir),
                    "notes": [],
                }
        except Exception as exc:
            stages["events"]["errors"] = 1
            stages["events"]["notes"] = [f"events_error:{exc.__class__.__name__}"]
    else:
        stages["events"]["notes"] = ["events_skipped"]

    if instruments_provider:
        try:
            if instruments_provider != "offline_file":
                stages["instruments"]["errors"] = 1
                stages["instruments"]["notes"] = ["unsupported_provider"]
            else:
                if not instruments_input:
                    stages["instruments"]["errors"] = 1
                    stages["instruments"]["notes"] = ["missing_input"]
                else:
                    instruments_dir = (
                        Path(instruments_outdir)
                        if instruments_outdir is not None
                        else config.REPO_ROOT / "data" / "eod" / "instruments" / day_str
                    )
                    instruments_dir.mkdir(parents=True, exist_ok=True)
                    provider = OfflineFileInstrumentsProvider(Path(instruments_input))
                    provider.pull(day_str, instruments_dir)
                    records, errors = instrumentstore.parse_instruments(
                        instruments_dir / "instruments.jsonl",
                        source=provider.name,
                    )
                    deduped = instrumentstore.dedupe_instruments(records)
                    instrumentstore.atomic_write_jsonl(
                        instruments_dir / "instruments.jsonl",
                        deduped,
                    )
                    instruments_manifest = instrumentstore.build_manifest(
                        day_str,
                        instruments_dir,
                        total=len(records),
                        ok=len(deduped) - len(errors),
                        errors=errors,
                        runtime_ms=0,
                        provenance={"cli_args": {}},
                        args_summary={},
                    )
                    instrumentstore.atomic_write_json(
                        instruments_dir / "_manifest.json",
                        instruments_manifest,
                    )
                    stages["instruments"] = {
                        "total": instruments_manifest["total"],
                        "ok": instruments_manifest["ok"],
                        "errors": instruments_manifest["errors"],
                        "path": str(instruments_dir),
                        "notes": [],
                    }
        except Exception as exc:
            stages["instruments"]["errors"] = 1
            stages["instruments"]["notes"] = [f"instruments_error:{exc.__class__.__name__}"]

    if ca_provider:
        try:
            if ca_provider != "offline_file":
                stages["corporate_actions"]["errors"] = 1
                stages["corporate_actions"]["notes"] = ["unsupported_provider"]
            else:
                if not ca_input:
                    stages["corporate_actions"]["errors"] = 1
                    stages["corporate_actions"]["notes"] = ["missing_input"]
                else:
                    ca_dir = (
                        Path(ca_outdir)
                        if ca_outdir is not None
                        else config.REPO_ROOT / "data" / "eod" / "corporate_actions" / day_str
                    )
                    ca_dir.mkdir(parents=True, exist_ok=True)
                    provider = OfflineFileCorporateActionsProvider(Path(ca_input))
                    provider.pull(day_str, ca_dir)
                    records, errors = castore.parse_actions(ca_dir / "actions.jsonl")
                    deduped = castore.dedupe_actions(records)
                    castore.atomic_write_jsonl(ca_dir / "actions.jsonl", deduped)
                    corporate_actions_manifest = castore.build_manifest(
                        day_str,
                        ca_dir,
                        total=len(records),
                        ok=len(deduped) - len(errors),
                        errors=errors,
                        runtime_ms=0,
                        provenance={"cli_args": {}},
                        args_summary={},
                    )
                    castore.atomic_write_json(
                        ca_dir / "_manifest.json",
                        corporate_actions_manifest,
                    )
                    stages["corporate_actions"] = {
                        "total": corporate_actions_manifest["total"],
                        "ok": corporate_actions_manifest["ok"],
                        "errors": corporate_actions_manifest["errors"],
                        "path": str(ca_dir),
                        "notes": [],
                    }
        except Exception as exc:
            stages["corporate_actions"]["errors"] = 1
            stages["corporate_actions"]["notes"] = [f"ca_error:{exc.__class__.__name__}"]
    else:
        stages["corporate_actions"]["notes"] = ["ca_skipped"]

    instruments_dir = (
        Path(instruments_outdir)
        if instruments_outdir is not None
        else config.REPO_ROOT / "data" / "eod" / "instruments" / day_str
    )
    ca_dir = (
        Path(ca_outdir)
        if ca_outdir is not None
        else config.REPO_ROOT / "data" / "eod" / "corporate_actions" / day_str
    )
    if instruments_dir.exists() and (instruments_dir / "instruments.jsonl").exists():
        try:
            universe_dir = out_path / "universe" / day_str
            universe_dir.mkdir(parents=True, exist_ok=True)
            timeline, universe_manifest = instrument_timeline.resolve_timeline(
                day_str,
                instruments_dir / "instruments.jsonl",
                ca_dir / "actions.jsonl",
                universe_dir,
                args={"day": day_str},
            )
            stages["universe"] = {
                "total": len(timeline.get("resolved", [])),
                "ok": len(timeline.get("resolved", [])) - universe_manifest["errors"],
                "errors": universe_manifest["errors"],
                "path": str(universe_dir),
                "notes": [],
            }
        except Exception as exc:
            stages["universe"]["errors"] = 1
            stages["universe"]["notes"] = [f"universe_error:{exc.__class__.__name__}"]
    else:
        stages["universe"]["notes"] = ["universe_skipped"]

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
    manifest["instruments_manifest"] = instruments_manifest
    manifest["corporate_actions_manifest"] = corporate_actions_manifest
    manifest["universe_manifest"] = universe_manifest
    manifest["calendar"] = stages["calendar"]
    atomic_write_json(out_path / "_pipeline_manifest.json", manifest)

    stage_errors = (
        stages["snapshot"]["errors"]
        + stages["advice"]["errors"]
        + stages["dossier"]["errors"]
        + stages["events"]["errors"]
        + stages["instruments"]["errors"]
        + stages["corporate_actions"]["errors"]
        + stages["universe"]["errors"]
        + stages["calendar"]["errors"]
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
