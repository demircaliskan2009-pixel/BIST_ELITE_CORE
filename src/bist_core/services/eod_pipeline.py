from __future__ import annotations

import csv
from datetime import date as Date
import json
import os
from pathlib import Path
import platform
import time
from typing import Iterable, Optional

from bist_core import config
from bist_core.services.advisor import build_advice_for_symbol
from bist_core.services.adjustments import build_adjust_factors
from bist_core.services.dossier import (
    atomic_write_json,
    build_dossiers_for_day,
    build_manifest,
)
from bist_core.services.marketdata import MarketData
from bist_core.services.events_pipeline import (
    build_events_jsonl_for_day,
    ingest_events_from_file,
    _provider_raw_cache,
)
from bist_core.providers.events.offline_file import OfflineFileEventsProvider
from bist_core.services import instrumentstore
from bist_core.services.features import (
    compute_features,
    load_history as features_load_history,
    write_features,
)
from bist_core.providers.instruments.offline_file import OfflineFileInstrumentsProvider
from bist_core.services import castore
from bist_core.providers.corporate_actions.offline_file import (
    OfflineFileCorporateActionsProvider,
)
from bist_core.services import instrument_timeline
from bist_core.services import trading_calendar
from bist_core.services import snapshot_integrity
from bist_core.policy import rules_engine, rules_schema
from bist_core.strategies import resolve_strategy
from bist_core.risk import load_risk_rules, validate_orders_intent
from bist_core.risk.gates import gate_order_rules
from bist_core.risk.rulespack import get_rulespack_dir, load_rulespack
from bist_core.services import instrument_master as instrument_master_mod
from bist_core.services import corporate_actions_canon
from bist_core.services import price_adjust


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
    policy_file: Optional[Path | str] = None,
    emit_orders: bool = False,
    orders_strategy: str = "equal_weight",
    orders_top_n: int = 10,
    risk_rules_file: Optional[Path | str] = None,
    instrument_master: Optional[Path | str] = None,
    ignore_instrument_master: bool = False,
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
        "features": {"total": 0, "ok": True, "errors": 0, "path": "", "notes": []},
        "calendar": {"ok": True, "errors": 0, "path": "", "notes": []},
        "policy": {"ok": True, "errors": 0, "notes": []},
        "instrument_master": {"ok": True, "errors": 0, "notes": []},
        "price_adjust": {"ok": True, "errors": 0, "path": "", "notes": []},
    }
    instruments_manifest = None
    corporate_actions_manifest = None
    universe_manifest = None
    events_pull_raw_cache = None
    pipeline_manifest_to_write = None

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

    snapshot_hash = None
    policy_effective = (
        str(policy_file) if policy_file is not None else os.getenv("BIST_CORE_POLICY_FILE")
    )
    policy_errors: list[str] = []
    policy_prov = None
    policy_ruleset = None
    if policy_effective:
        policy_path = Path(policy_effective)
        policy_prov = {"file": str(policy_path), "hash": {"algo": "sha256", "value": ""}}
        try:
            policy_prov["hash"]["value"] = snapshot_integrity.compute_sha256(policy_path)
        except Exception:
            policy_errors.append("PolicyHashError")
        try:
            ruleset = rules_schema.load_ruleset(policy_path)
            policy_errors.extend(rules_schema.validate_ruleset(ruleset))
            if not policy_errors:
                policy_ruleset = ruleset
        except Exception:
            policy_errors.append("PolicyLoadError")
        if policy_errors:
            policy_errors = sorted(set(policy_errors))
            stages["policy"]["ok"] = False
            stages["policy"]["errors"] = len(policy_errors)
            stages["policy"]["notes"] = policy_errors
    try:
        hash_manifest = snapshot_integrity.build_eod_snapshot(
            day_str, root, root
        )
        snapshot_hash = {"algo": "sha256", "value": hash_manifest["sha256"]}
        snapshot_path = root / day_str / "snapshot.csv"
    except FileNotFoundError:
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
            snapshot_hash=None,
            policy_prov=policy_prov,
        )
        manifest["calendar"] = stages["calendar"]
        if events_pull_raw_cache is not None:
            manifest.setdefault("events", {})["raw_cache"] = events_pull_raw_cache
        pipeline_manifest_to_write = manifest
        _write_pipeline_manifest(out_path, day_str, manifest)
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
    except Exception:
        stages["snapshot"]["errors"] += 1
        stages["snapshot"]["notes"] = stages["snapshot"]["notes"] + ["snapshot_hash_error"]
        snapshot_path = root / day_str / "snapshot.csv"

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
            snapshot_hash=snapshot_hash,
            policy_prov=policy_prov,
        )
        manifest["calendar"] = stages["calendar"]
        if events_pull_raw_cache is not None:
            manifest.setdefault("events", {})["raw_cache"] = events_pull_raw_cache
        pipeline_manifest_to_write = manifest
        _write_pipeline_manifest(out_path, day_str, manifest)
        stage_errors = (
            stages["snapshot"]["errors"]
            + stages["advice"]["errors"]
            + stages["dossier"]["errors"]
            + stages["events"]["errors"]
            + stages["instruments"]["errors"]
            + stages["corporate_actions"]["errors"]
            + stages["universe"]["errors"]
            + stages["calendar"]["errors"]
            + stages["policy"]["errors"]
        )
        return manifest, 2 if strict and stage_errors > 0 else 0

    if policy_errors and strict:
        runtime_ms = int((time.perf_counter() - start) * 1000)
        manifest = _pipeline_manifest(
            day_str,
            root,
            out_path,
            stages,
            runtime_ms,
            git_sha=git_sha,
            cli_args=cli_args or {},
            snapshot_hash=snapshot_hash,
            policy_prov=policy_prov,
        )
        manifest["calendar"] = stages["calendar"]
        if events_pull_raw_cache is not None:
            manifest.setdefault("events", {})["raw_cache"] = events_pull_raw_cache
        pipeline_manifest_to_write = manifest
        _write_pipeline_manifest(out_path, day_str, manifest)
        stage_errors = (
            stages["snapshot"]["errors"]
            + stages["advice"]["errors"]
            + stages["dossier"]["errors"]
            + stages["events"]["errors"]
            + stages["instruments"]["errors"]
            + stages["corporate_actions"]["errors"]
            + stages["universe"]["errors"]
            + stages["calendar"]["errors"]
            + stages["policy"]["errors"]
        )
        return manifest, 2 if stage_errors > 0 else 0

    base_symbols, eod_raw_cache = _load_symbols(root, day_str)
    filtered = _filter_symbols(base_symbols, symbols, regex, limit)
    sorted_symbols = sorted(filtered)
    instrument_master_prov: Optional[dict] = None
    unknown_symbols: list[str] = []
    instrument_resolution: Optional[dict] = None
    symbol_to_id: dict = {}
    if instrument_master and not ignore_instrument_master:
        master_path = Path(instrument_master)
        master_set, meta, symbol_to_id = instrument_master_mod.load_instrument_master(master_path)
        instrument_master_prov = meta
        unknown_symbols = sorted(
            s for s in sorted_symbols if (s or "").strip().upper() not in master_set
        )
        if unknown_symbols:
            stages["instrument_master"]["ok"] = False
            stages["instrument_master"]["errors"] = len(unknown_symbols)
            stages["instrument_master"]["notes"] = unknown_symbols
        if symbol_to_id:
            instrument_resolution = instrument_master_mod.resolve_symbols(
                list(sorted_symbols), symbol_to_id
            )
    else:
        stages["instrument_master"]["notes"] = ["ignored"] if ignore_instrument_master else []
    safe_mode_reason: Optional[str] = None
    if resolve_aliases:
        instruments_path = (
            Path(instruments_outdir) / "instruments.jsonl"
            if instruments_outdir is not None
            else (config.REPO_ROOT / "data" / "eod" / "instruments" / day_str / "instruments.jsonl")
        )
        if instruments_input and not instruments_path.is_file():
            instruments_path = Path(instruments_input)
        actions_path = (
            Path(ca_outdir) / "actions.jsonl"
            if ca_outdir is not None
            else (config.REPO_ROOT / "data" / "eod" / "corporate_actions" / day_str / "actions.jsonl")
        )
        if not instruments_path.is_file() or not actions_path.is_file():
            stages["universe"]["ok"] = False
            stages["universe"]["errors"] = 1
            stages["universe"]["notes"] = ["instruments_or_ca_missing"]
            safe_mode_reason = "Alias resolution skipped (instruments/CA missing)."
        else:
            try:
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
                    stages["universe"]["notes"] = stages["universe"].get("notes", []) + ["alias_resolution_errors"]
            except Exception:
                stages["universe"]["errors"] = 1
                stages["universe"]["notes"] = stages["universe"].get("notes", []) + ["alias_resolution_failed"]
                safe_mode_reason = "Alias resolution failed (exception)."

    advice_path = out_path / ("advice.jsonl" if jsonl else "advice.json")
    advice_records, advice_errors = _build_advice_records(
        sorted_symbols,
        day_str,
        root,
        safe_mode_reason=safe_mode_reason,
    )
    _write_advice(advice_path, advice_records, jsonl=jsonl)
    stages["advice"] = {
        "total": len(advice_records),
        "ok": len(advice_records) - advice_errors,
        "errors": advice_errors,
        "path": str(advice_path),
    }

    try:
        def _context_provider(sym: str, d: str) -> dict:
            return features_load_history(root, sym, d, lookback_days=21)

        feature_rows, feature_notes = compute_features(
            list(sorted_symbols),
            day_str,
            _context_provider,
        )
        feat_path = write_features(out_path, day_str, feature_rows)
        stages["features"] = {
            "total": len(feature_rows),
            "ok": len(feature_notes) == 0,
            "errors": len(feature_notes),
            "path": str(feat_path),
            "notes": list(dict.fromkeys(feature_notes)),
        }
        if feature_notes:
            stages["features"]["ok"] = False
    except Exception:
        stages["features"]["ok"] = False
        stages["features"]["errors"] = 1
        stages["features"]["notes"] = ["feature_compute_error"]

    orders_intent_path_written: Optional[Path] = None
    if emit_orders:
        orders_dir = out_path / "orders" / day_str
        orders_dir.mkdir(parents=True, exist_ok=True)
        orders_path = orders_dir / "orders_intent.json"
        orders_payload, orders_notes, orders_ok = _build_orders_intent(
            day_str,
            universe=sorted_symbols,
            advice_records=advice_records,
            strategy=orders_strategy,
            top_n=orders_top_n,
            policy_ruleset=policy_ruleset,
            policy_errors=policy_errors,
        )
        risk_rules, risk_errors = load_risk_rules(risk_rules_file)
        if risk_errors:
            orders_payload["actions"] = []
            orders_notes = sorted(set(orders_notes + risk_errors))
            orders_ok = False
        elif risk_rules is not None:
            risk_ok, risk_notes = validate_orders_intent(orders_payload, risk_rules)
            if not risk_ok:
                orders_payload["actions"] = []
                orders_notes = sorted(set(orders_notes + risk_notes))
                orders_ok = False
        rulespack_dir = get_rulespack_dir()
        if rulespack_dir.is_dir():
            pack, _ = load_rulespack(rulespack_dir)
            if pack.get("tick_sizes") or pack.get("price_bands"):
                order_rule_errors: list[str] = []
                for action in orders_payload.get("actions") or []:
                    if not isinstance(action, dict):
                        continue
                    ref_price = action.get("ref_price")
                    try:
                        ref_p = float(ref_price) if ref_price is not None else None
                    except (TypeError, ValueError):
                        ref_p = None
                    result = gate_order_rules(action, pack, ref_price=ref_p)
                    if not result.get("ok"):
                        order_rule_errors.extend(result.get("errors", []))
                if order_rule_errors:
                    orders_ok = False
                    orders_notes = sorted(set(orders_notes + order_rule_errors))
        orders_payload["notes"] = sorted(set(orders_payload.get("notes", []) + orders_notes))
        atomic_write_json(orders_path, orders_payload)
        orders_intent_path_written = orders_path
        order_errors_count = 0 if orders_ok else 1
        stages["orders"] = {
            "ok": int(orders_ok),
            "total": 1,
            "errors": order_errors_count,
            "path": str(orders_path),
            "notes": orders_notes,
        }

    dossier_dir = out_path / "dossiers"
    dossier_dir.mkdir(parents=True, exist_ok=True)
    dossiers, runtime_ms, dossier_prov = build_dossiers_for_day(
        day_str,
        root=root,
        symbols=symbols,
        regex=regex,
        limit=limit,
        snapshot_hash=snapshot_hash,
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
                    base_url = os.getenv("BIST_KAP_BASE_URL", "https://www.kap.org.tr")
                    url_tpl = os.getenv("BIST_KAP_URL_TEMPLATE") or os.getenv("BIST_KAP_EVENTS_URL_TEMPLATE")
                    provider = KapHtmlEventsProvider(
                        base_url=base_url,
                        url_template=url_tpl or None,
                    )
                pull_manifest = build_events_jsonl_for_day(
                    day_str,
                    provider,
                    pull_out,
                    atomic=True,
                )
                events_pull_raw_cache = pull_manifest.get("raw_cache")

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
                events_pull_raw_cache = pull_manifest.get("raw_cache")

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
                    snapshot_csv = root / day_str / "snapshot.csv"
                    factors_path = out_path / "adjust_factors.json"
                    if snapshot_csv.is_file():
                        try:
                            with snapshot_csv.open("r", encoding="utf-8", newline="") as f:
                                reader = csv.DictReader(f)
                                rows = list(reader)
                            symbol_col = "symbol" if rows and "symbol" in (rows[0] or {}) else None
                            if symbol_col:
                                symbols = sorted({r.get(symbol_col) or "" for r in rows if r.get(symbol_col)})
                                series = [{"symbol": s, "date": day_str} for s in symbols]
                                factors_list, _ = build_adjust_factors(series, deduped)
                                atomic_write_json(
                                    factors_path,
                                    {"schema_version": 1, "day": day_str, "factors": factors_list},
                                )
                                corporate_actions_manifest["factors_path"] = str(factors_path)
                        except Exception:
                            pass
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
    canonical_errors = 0
    canon_out = out_path / day_str / "corporate_actions" / "actions_canonical.jsonl"
    if (ca_dir / "actions.jsonl").is_file():
        _, canonical_errors = corporate_actions_canon.canonicalize_actions_file(
            ca_dir / "actions.jsonl",
            canon_out,
            symbol_to_id,
        )
        if canon_out.is_file() and symbol_to_id:
            price_adj_out = out_path / day_str
            adj_errors, adj_notes = price_adjust.build_adjusted_prices(
                snapshot_root=root,
                days=[day_str],
                canonical_actions_path=canon_out,
                symbol_to_id=symbol_to_id,
                out_dir=price_adj_out,
                strict=strict,
            )
            stages["price_adjust"] = {
                "ok": adj_errors == 0,
                "errors": adj_errors,
                "path": str(price_adj_out),
                "notes": adj_notes,
            }
        else:
            stages["price_adjust"]["notes"] = ["skipped"]
    else:
        stages["price_adjust"]["notes"] = ["skipped"]
    stages["corporate_actions"]["canonical_errors"] = canonical_errors
    if canonical_errors > 0:
        stages["corporate_actions"]["notes"] = stages["corporate_actions"].get("notes", []) + [
            f"canonical_errors:{canonical_errors}",
        ]
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
        if not stages["universe"].get("notes"):
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
        snapshot_hash=snapshot_hash,
        policy_prov=policy_prov,
        eod_raw_cache=eod_raw_cache,
        orders_intent_path=orders_intent_path_written,
    )
    manifest["instruments_manifest"] = instruments_manifest
    manifest["corporate_actions_manifest"] = corporate_actions_manifest
    manifest["universe_manifest"] = universe_manifest
    manifest["calendar"] = stages["calendar"]
    if events_pull_raw_cache is not None:
        manifest.setdefault("events", {})["raw_cache"] = events_pull_raw_cache
    if instrument_resolution is not None:
        manifest["instrument_resolution"] = instrument_resolution
    pipeline_manifest_to_write = manifest
    try:
        stage_errors = (
            stages["snapshot"]["errors"]
            + stages["advice"]["errors"]
            + stages["dossier"]["errors"]
            + stages["events"]["errors"]
            + stages["instruments"]["errors"]
            + stages["corporate_actions"]["errors"]
            + stages["corporate_actions"].get("canonical_errors", 0)
            + stages["universe"]["errors"]
            + stages["calendar"]["errors"]
            + stages["policy"]["errors"]
            + stages["price_adjust"].get("errors", 0)
            + (1 if stages.get("orders", {}).get("ok", 1) == 0 else 0)
        )
        return manifest, 2 if strict and stage_errors > 0 else 0
    finally:
        if pipeline_manifest_to_write is not None:
            _write_pipeline_manifest(out_path, day_str, pipeline_manifest_to_write)


def _pipeline_manifest(
    day_str: str,
    snapshot_root: Path,
    outdir: Path,
    stages: dict,
    runtime_ms: int,
    git_sha: Optional[str],
    cli_args: dict,
    snapshot_hash: Optional[dict],
    policy_prov: Optional[dict],
    eod_raw_cache: Optional[dict] = None,
    orders_intent_path: Optional[Path] = None,
) -> dict:
    out = {
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
            "snapshot_hash": snapshot_hash,
            "policy": policy_prov,
        },
    }
    if eod_raw_cache is not None:
        out["raw_cache"] = eod_raw_cache
    if orders_intent_path is not None:
        out["orders_intent_path"] = str(orders_intent_path)
    return out


def locate_manifest(outdir: Path | str, day: str) -> Optional[Path]:
    """
    Find pipeline manifest file with fallback order (no hardcoded single path):
    outdir/<day>/pipeline_manifest.json -> outdir/pipeline_manifest.json -> outdir/_pipeline_manifest.json.
    Returns first path that exists, or None.
    """
    base = Path(outdir)
    for candidate in (
        base / day / "pipeline_manifest.json",
        base / "pipeline_manifest.json",
        base / "_pipeline_manifest.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def _write_pipeline_manifest(out_path: Path, day_str: str, manifest: dict) -> None:
    """Write pipeline manifest to three deterministic locations (same content):
    (a) out_path/pipeline_manifest.json  (root)
    (b) out_path/<day_str>/pipeline_manifest.json  (day-scoped; parent dir created)
    (c) out_path/_pipeline_manifest.json  (backward compatibility)
    Uses existing atomic_write_json helper."""
    root_path = out_path / "pipeline_manifest.json"
    day_path = out_path / day_str / "pipeline_manifest.json"
    legacy_path = out_path / "_pipeline_manifest.json"
    day_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(root_path, manifest)
    atomic_write_json(day_path, manifest)
    atomic_write_json(legacy_path, manifest)


def _build_orders_intent(
    day_str: str,
    *,
    universe: list[str],
    advice_records: list[dict],
    strategy: str,
    top_n: int,
    policy_ruleset: Optional[dict],
    policy_errors: list[str],
) -> tuple[dict, list[str], bool]:
    notes: list[str] = []
    blocked_by_policy = False

    if policy_errors:
        blocked_by_policy = True
        notes.append("blocked_by_policy")
    if policy_ruleset is not None:
        allowed, _ = rules_engine.evaluate(
            policy_ruleset,
            trading_context={"day": day_str},
        )
        if not allowed:
            blocked_by_policy = True
            notes.append("blocked_by_policy")

    params = {"top_n": top_n}
    try:
        strategy_impl = resolve_strategy(strategy)
    except ValueError:
        notes.append("strategy_not_found")
        payload = {
            "schema_version": 1,
            "strategy": {"name": str(strategy), "params": params},
            "day": day_str,
            "universe_size": len(universe),
            "actions": [],
            "notes": sorted(set(notes)),
        }
        return payload, payload["notes"], False

    payload = strategy_impl.build_intent(
        day=day_str,
        universe=universe,
        advice_records=advice_records,
        params=params,
    )
    notes = list(payload.get("notes", []))

    if blocked_by_policy:
        payload["actions"] = []
        notes.append("blocked_by_policy")
        payload["notes"] = sorted(set(notes))
        return payload, payload["notes"], False

    notes = sorted(set(notes))
    payload["notes"] = notes
    if not payload.get("actions"):
        if "no_actions" not in payload["notes"]:
            payload["notes"].append("no_actions")
        payload["notes"] = sorted(set(payload["notes"]))
    return payload, payload["notes"], True


def _build_advice_records(
    symbols: Iterable[str],
    day_str: str,
    snapshot_root: Path,
    safe_mode_reason: Optional[str] = None,
) -> tuple[list[dict], int]:
    records: list[dict] = []
    errors = 0
    for symbol in symbols:
        try:
            advice = build_advice_for_symbol(symbol, day_str, root=snapshot_root)
            text = advice.text
            if safe_mode_reason:
                prefix = f"Güvenli mod: {safe_mode_reason} "
                text = (prefix + (text or "")) if text else prefix
            payload = {
                "symbol": advice.symbol,
                "day": day_str,
                "decision_raw": advice.decision_raw,
                "score": advice.score,
                "signals": advice.signals,
                "plan": advice.plan,
                "text": text,
            }
            if isinstance(text, str) and "Güvenli mod" in text:
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


def _load_symbols(snapshot_root: Path, day_str: str) -> tuple[list[str], Optional[dict]]:
    try:
        md = MarketData(snapshot_root)
        symbols = md.symbols(day_str)
        raw_cache = _provider_raw_cache(md._prov)
        return symbols, raw_cache
    except Exception:
        return [], None


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
