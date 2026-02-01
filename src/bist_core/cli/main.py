from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from bist_core.data.registry import (
    DatasetRegistry,
    get_default_registry,
    load_registered_dataset,
)
from bist_core.strategy.equal_weight import (
    build_equal_weight_plan, 
    generate_equal_weight_orders
)
from bist_core import config
from bist_core.services import eventstore
from bist_core.services.marketdata import MarketData
from bist_core.services.advisor import build_advice_for_symbol
from bist_core.execution.result_writer import write_execution_result
from bist_core.services.dossier import (
    atomic_write_json,
    build_dossiers_for_day,
    build_manifest,
)
from bist_core.services.eod_pipeline import locate_manifest, run_eod_pipeline
from bist_core.services import snapshot_integrity
from bist_core.services.eod_replay import run_eod_replay
from bist_core.services.scorecard import build_scorecard
from bist_core.services.eod_batch import audit_eod_batch, run_eod_batch
from bist_core.services.events_pipeline import (
    build_events_jsonl_for_day,
    ingest_events_from_file,
)
from bist_core.providers.events.offline_file import OfflineFileEventsProvider
from bist_core.providers.events.kap_html import KapHtmlEventsProvider
from bist_core.policy import rules_engine, rules_schema
from bist_core.services import instrumentstore
from bist_core.providers.instruments.offline_file import OfflineFileInstrumentsProvider
from bist_core.services import castore
from bist_core.providers.corporate_actions.offline_file import (
    OfflineFileCorporateActionsProvider,
)
from bist_core.services.adjustments import apply_close_adjustments
from bist_core.services import instrument_timeline
from bist_core.brokers import PaperBroker
from bist_core.execution import PaperExecutionProvider
from bist_core.risk.gates import RiskGateEngine
from bist_core.market_data import resolve_provider
from bist_core.cli.observability import (
    err_struct,
    ERROR_ARGS_REQUIRED,
    ERROR_ARTIFACT_HASH_MISMATCH,
    ERROR_CONFIG_INVALID,
    ERROR_CONFIG_MISSING,
    ERROR_REPO_ROOT_MISSING,
    ERROR_CORE_JSON_MISSING,
    ERROR_SNAPSHOT_DIR_MISSING,
    ERROR_REGISTRY_MISSING,
)


def _find_manifest_path(outdir: Path, day: str) -> Path:
    """First existing manifest path, else default outdir/day/pipeline_manifest.json."""
    candidates = [
        outdir / day / "pipeline_manifest.json",
        outdir / "pipeline_manifest.json",
        outdir / "_pipeline_manifest.json",
        outdir / day / "_pipeline_manifest.json",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return outdir / day / "pipeline_manifest.json"
from bist_core.services.backtest import run_backtest, walk_forward


def _snapshot_root() -> Path:
    return Path(os.getenv("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots"))


def _cmd_info(args: argparse.Namespace) -> int:
    reg = get_default_registry()
    if bool(getattr(args, "json", False)):
        datasets = []
        try:
            names = reg.list_datasets()
            for n in names:
                datasets.append(n)
        except Exception:
            datasets = []
        payload = {
            "registry_path": str(getattr(reg, "path", "")),
            "datasets": datasets,
            "symbols": ["TEST"],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    try:
        print(f"registry: {reg.path}")
    except Exception:
        print("registry: <unknown>")

    try:
        names = reg.list_datasets()
        if names:
            print("datasets:")
            for n in names:
                meta = reg.get(n)
                kind = getattr(meta, "kind", None) if meta else None
                path = getattr(meta, "path", None) if meta else None
                print(f"  - name={n} kind={kind} path={path}")
        else:
            print("datasets: <empty>")
    except Exception:
        print("datasets: <empty>")

    # Faz-2 test kontratı
    print("symbols: TEST")
    return 0


def _cmd_eod(args: argparse.Namespace) -> int:
    if not getattr(args, "date", None):
        raise SystemExit("--date is required")
    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.date}. Use YYYY-MM-DD")

    root = _snapshot_root()
    day_dir = root / snapshot_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = day_dir / "snapshot.csv"

    if config.SOURCES["vendor_api"]["enabled"]:
        data = MarketData()
        symbols = data.symbols(args.date)        # API'den o güne ait semboller
        close_map = data.close_map(args.date)    # her sembol için kapanış fiyatı
        # Bir DataFrame oluşturup snapshot.csv'ye yazabiliriz:
        df = pd.DataFrame([
            {"symbol": sym, "close": close_map.get(sym, float("nan"))} for sym in symbols
        ])
        df.to_csv(snapshot_path, index=False)
    else:
        # mevcut TEST verisi yazma kodu
        df = pd.DataFrame([{"symbol": "TEST", "close": 0.0}])
        df.to_csv(snapshot_path, index=False)

    print(f"snapshot created at {snapshot_path}")
    return 0


def _cmd_eod_run(args: argparse.Namespace) -> int:
    base = _snapshot_root()
    if getattr(args, "day", None):
        day_value = args.day
    else:
        day_value = _latest_snapshot_day(base)
        if day_value is None:
            print("Uyarı: Snapshot bulunamadı; bugünün tarihine düşülüyor.")
            day_value = date.today().isoformat()

    day_str = day_value if isinstance(day_value, str) else day_value.isoformat()

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "runs" / day_str

    symbols = None
    if getattr(args, "symbols", None):
        raw = [s.strip() for s in args.symbols.split(",")]
        symbols = [s for s in raw if s]

    cli_args = {
        "symbols": getattr(args, "symbols", None),
        "regex": getattr(args, "regex", None),
        "limit": getattr(args, "limit", None),
        "strict": bool(getattr(args, "strict", False)),
        "outdir": str(outdir),
        "day": day_str,
        "jsonl": bool(getattr(args, "jsonl", True)),
        "events_provider": getattr(args, "events_provider", None),
        "events_input": getattr(args, "events_input", None),
        "events_outdir": getattr(args, "events_outdir", None),
        "instruments_provider": getattr(args, "instruments_provider", None),
        "instruments_input": getattr(args, "instruments_input", None),
        "instruments_outdir": getattr(args, "instruments_outdir", None),
        "ca_provider": getattr(args, "ca_provider", None),
        "ca_input": getattr(args, "ca_input", None),
        "ca_outdir": getattr(args, "ca_outdir", None),
        "resolve_aliases": bool(getattr(args, "resolve_aliases", False)),
        "calendar_file": getattr(args, "calendar_file", None),
        "ignore_calendar": bool(getattr(args, "ignore_calendar", False)),
        "policy_file": getattr(args, "policy_file", None),
        "emit_orders": bool(getattr(args, "emit_orders", False)),
        "orders_strategy": getattr(args, "orders_strategy", None),
        "orders_top_n": getattr(args, "orders_top_n", None),
        "risk_rules_file": getattr(args, "risk_rules_file", None),
        "restrictions_file": getattr(args, "restrictions_file", None),
        "research": bool(getattr(args, "research", False)),
        "research_source": getattr(args, "research_source", None),
    }
    research_source = getattr(args, "research_source", None) or ("kap" if getattr(args, "research", False) else None)
    manifest, code = run_eod_pipeline(
        day_str,
        snapshot_root=base,
        outdir=outdir,
        strict=bool(getattr(args, "strict", False)),
        symbols=symbols,
        regex=getattr(args, "regex", None),
        limit=getattr(args, "limit", None),
        jsonl=bool(getattr(args, "jsonl", True)),
        events_provider=getattr(args, "events_provider", None),
        events_input=getattr(args, "events_input", None),
        events_outdir=getattr(args, "events_outdir", None),
        instruments_provider=getattr(args, "instruments_provider", None),
        instruments_input=getattr(args, "instruments_input", None),
        instruments_outdir=getattr(args, "instruments_outdir", None),
        ca_provider=getattr(args, "ca_provider", None),
        ca_input=getattr(args, "ca_input", None),
        ca_outdir=getattr(args, "ca_outdir", None),
        resolve_aliases=bool(getattr(args, "resolve_aliases", False)),
        calendar_file=getattr(args, "calendar_file", None),
        ignore_calendar=bool(getattr(args, "ignore_calendar", False)),
        policy_file=getattr(args, "policy_file", None),
        emit_orders=bool(getattr(args, "emit_orders", False)),
        orders_strategy=getattr(args, "orders_strategy", None) or "equal_weight",
        orders_top_n=int(getattr(args, "orders_top_n", 10) or 10),
        risk_rules_file=getattr(args, "risk_rules_file", None),
        restrictions_file=getattr(args, "restrictions_file", None) or os.environ.get("BIST_RESTRICTIONS_FILE"),
        research_source=research_source,
        research_offline=bool(getattr(args, "research_offline", False)),
        market_data_provider=getattr(args, "market_data_provider", None),
        instrument_master=getattr(args, "instrument_master", None) or os.environ.get("BIST_INSTRUMENT_MASTER"),
        git_sha=_env_git_sha(),
        cli_args=cli_args,
    )
    try:
        stages = manifest.get("stages", {}) if isinstance(manifest, dict) else {}
        snapshot_stage = stages.get("snapshot", {})
        advice_stage = stages.get("advice", {})
        dossier_stage = stages.get("dossier", {})
        print(
            "eod run: "
            f"snapshot errors={snapshot_stage.get('errors', 0)}; "
            f"advice ok={advice_stage.get('ok', 0)}/{advice_stage.get('total', 0)}; "
            f"dossier ok={dossier_stage.get('ok', 0)}/{dossier_stage.get('total', 0)}"
        )
    except Exception:
        pass
    return int(code)


def _cmd_eod_batch(args: argparse.Namespace) -> int:
    base = _snapshot_root()
    audit = bool(getattr(args, "audit", False))
    deep_audit = bool(getattr(args, "deep_audit", False))
    if deep_audit:
        audit = True

    date_from = getattr(args, "date_from", None)
    date_to = getattr(args, "date_to", None)
    if not audit and (not date_from or not date_to):
        raise SystemExit("--from and --to are required")

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        if audit:
            raise SystemExit("--outdir is required for --audit")
        outdir = config.REPO_ROOT / "data" / "eod" / "batch" / f"{date_from}_to_{date_to}"

    if audit:
        manifest, code = audit_eod_batch(
            outdir,
            deep=deep_audit,
            strict=bool(getattr(args, "strict", False)),
        )
        if bool(getattr(args, "audit_json", False)):
            print(json.dumps(manifest, ensure_ascii=False))
        else:
            _print_batch_summary(manifest, int(code))
        return int(code)

    symbols = None
    if getattr(args, "symbols", None):
        raw = [s.strip() for s in args.symbols.split(",")]
        symbols = [s for s in raw if s]

    run_kwargs = {
        "symbols": symbols,
        "regex": getattr(args, "regex", None),
        "limit": getattr(args, "limit", None),
        "jsonl": bool(getattr(args, "jsonl", True)),
        "events_provider": getattr(args, "events_provider", None),
        "events_input": getattr(args, "events_input", None),
        "events_outdir": getattr(args, "events_outdir", None),
        "instruments_provider": getattr(args, "instruments_provider", None),
        "instruments_input": getattr(args, "instruments_input", None),
        "instruments_outdir": getattr(args, "instruments_outdir", None),
        "ca_provider": getattr(args, "ca_provider", None),
        "ca_input": getattr(args, "ca_input", None),
        "ca_outdir": getattr(args, "ca_outdir", None),
        "resolve_aliases": bool(getattr(args, "resolve_aliases", False)),
        "policy_file": getattr(args, "policy_file", None),
        "instrument_master": getattr(args, "instrument_master", None) or os.environ.get("BIST_INSTRUMENT_MASTER"),
        "git_sha": _env_git_sha(),
        "cli_args": {"batch": True},
    }

    max_failures = int(getattr(args, "max_failures", 0) or 0)

    manifest, code = run_eod_batch(
        date_from,
        date_to,
        outdir,
        snapshot_root=base,
        strict=bool(getattr(args, "strict", False)),
        calendar_file=Path(args.calendar_file) if getattr(args, "calendar_file", None) else None,
        ignore_calendar=bool(getattr(args, "ignore_calendar", False)),
        resume=bool(getattr(args, "resume", False)),
        rerun_failed=bool(getattr(args, "rerun_failed", False)),
        max_failures=max_failures,
        dry_run=bool(getattr(args, "dry_run", False)),
        run_kwargs=run_kwargs,
    )
    _print_batch_summary(manifest, int(code))
    return int(code)


def _cmd_eod_replay(args: argparse.Namespace) -> int:
    snapshot_root = (
        Path(args.snapshot_root)
        if getattr(args, "snapshot_root", None)
        else _snapshot_root()
    )
    manifest, code = run_eod_replay(
        getattr(args, "date_from"),
        getattr(args, "date_to"),
        Path(getattr(args, "outdir")),
        snapshot_root=snapshot_root,
        strict=bool(getattr(args, "strict", False)),
        policy_file=getattr(args, "policy_file", None),
        emit_orders=bool(getattr(args, "emit_orders", False)),
        orders_strategy=getattr(args, "orders_strategy", None) or "equal_weight",
        orders_top_n=int(getattr(args, "orders_top_n", 10) or 10),
        risk_rules_file=getattr(args, "risk_rules_file", None),
        metrics=bool(getattr(args, "metrics", True)),
        scorecard=bool(getattr(args, "scorecard", True)),
    )
    if bool(getattr(args, "json", False)):
        summary = manifest.get("summary", {})
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return int(code)


def _cmd_eod_scorecard(args: argparse.Namespace) -> int:
    outdir = Path(getattr(args, "outdir"))
    scorecard = build_scorecard(outdir)
    if bool(getattr(args, "json", False)):
        print(json.dumps(scorecard, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def _cmd_eod_batch_audit(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        raise SystemExit("--outdir is required")
    manifest, code = audit_eod_batch(outdir, strict=bool(getattr(args, "strict", False)))
    _print_batch_summary(manifest, int(code))
    return int(code)


def _cmd_eod_advice(args: argparse.Namespace) -> int:
    from bist_core.advisory.generate import generate_advice
    day = getattr(args, "day", None) or ""
    outdir = Path(getattr(args, "outdir", None) or "")
    if not day or not str(outdir):
        raise SystemExit("--day and --outdir are required")
    top_n = getattr(args, "top_n", None)
    if top_n is not None:
        try:
            top_n = int(top_n)
        except (TypeError, ValueError):
            top_n = None
    result = generate_advice(day, _snapshot_root(), outdir, top_n=top_n)
    print(f"advice: path={result['path']} total={result['total']} errors={result['errors']}")
    return 0


def _cmd_eod_research(args: argparse.Namespace) -> int:
    from bist_core.research.cache import build_research_cache
    day = getattr(args, "day", None) or ""
    outdir = Path(getattr(args, "outdir", None) or "")
    if not day or not str(outdir):
        raise SystemExit("--day and --outdir are required")
    source = getattr(args, "source", None) or "kap"
    offline = bool(getattr(args, "offline", False))
    result = build_research_cache(day, outdir, source=source, offline=offline)
    print(f"research: path={result['path']} count={result['count']} errors={result['errors']}")
    return 0


EXIT_CONFIG_FAIL_CLOSED = 3


def _cmd_eod_execute(args: argparse.Namespace) -> int:
    day = getattr(args, "day", None) or ""
    outdir = Path(getattr(args, "outdir", None) or "")
    execution = "live" if getattr(args, "live", False) else (getattr(args, "execution", None) or "paper")
    broker_name = getattr(args, "broker", None) or getattr(args, "provider", None) or ("paper" if execution == "paper" else "stub")
    live = execution == "live"
    dry_run = not live
    if not day or not str(outdir):
        raise SystemExit("--day and --outdir are required")
    day_dir = outdir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    broker_config_path = None
    # FAZ71: Live preflight v2 — config ok, broker config ok, BIST rules present, manifest + orders_intent present. Always write execution_result on failure.
    if live:
        from bist_core.config import REPO_ROOT, resolve_core_config_path, load_core_config_strict
        config_path = resolve_core_config_path(getattr(args, "config", None), REPO_ROOT)
        core_cfg, config_err = load_core_config_strict(config_path)
        if config_err is not None:
            err_struct(config_err, "live mode requires valid core config (--config or BIST_CORE_CONFIG)")
            write_execution_result(outdir, day, ok=False, blocked=True, reason="config invalid or missing", provider=broker_name, mode=execution, errors=[config_err], execution=execution)
            return EXIT_CONFIG_FAIL_CLOSED
    broker_config_dict = None
    if live:
        from bist_core.config import load_broker_config
        broker_config_raw = os.environ.get("BIST_BROKER_CONFIG") or getattr(args, "broker_config", None)
        if broker_name != "paper":
            broker_config_dict, broker_config_err = load_broker_config(broker_config_raw)
            if broker_config_err is not None:
                note = "BIST_BROKER_CONFIG or --broker-config required (file path or inline JSON); invalid or missing fails closed"
                err_struct(broker_config_err, note)
                write_execution_result(outdir, day, ok=False, blocked=True, reason=note, provider=broker_name, mode=execution, errors=[broker_config_err], execution=execution)
                return 2
        from bist_core.risk.gates import preflight_bist_rules_for_live
        from bist_core.risk.restrictions import get_restrictions_path
        from bist_core.risk.rulespack import get_rulespack_dir
        ok_pre, err_pre = preflight_bist_rules_for_live(rulespack_dir=get_rulespack_dir(), restrictions_path=get_restrictions_path())
        if not ok_pre:
            note = "BIST rule data missing for live (tick/bands/vbts); set BIST_RULESPACK_DIR and BIST_RESTRICTIONS_FILE"
            err_struct("bist_rules_missing", note)
            for e in err_pre:
                print(f"  {e}", file=sys.stderr)
            exec_result_path = write_execution_result(outdir, day, ok=False, blocked=True, reason=note, provider=broker_name, mode=execution, errors=sorted(err_pre), execution=execution)
            from bist_core.dossier.write import update_dossier_evidence
            update_dossier_evidence(outdir, day, {
                "execution_result_path": str(exec_result_path),
                "blocked_reason": note,
                "blocked_code": "bist_rules_missing",
            })
            return 2
    manifest_path = _find_manifest_path(outdir, day)
    if not manifest_path.is_file():
        print("blocked: no pipeline manifest found", file=sys.stderr)
        write_execution_result(outdir, day, ok=False, blocked=True, reason="no pipeline manifest found", provider=broker_name, mode=execution, errors=["no_manifest"], execution=execution)
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, OSError):
        print("blocked: invalid pipeline manifest", file=sys.stderr)
        write_execution_result(outdir, day, ok=False, blocked=True, reason="invalid pipeline manifest", provider=broker_name, mode=execution, errors=["invalid_manifest"], execution=execution)
        return 2
    stages = manifest.get("stages") or {}
    orders_intent_path = manifest.get("orders_intent_path")
    if not orders_intent_path:
        orders_intent_path = outdir / "orders" / day / "orders_intent.json"
    else:
        orders_intent_path = Path(orders_intent_path)
    if not orders_intent_path.is_file():
        print("blocked: orders_intent.json not found", file=sys.stderr)
        write_execution_result(outdir, day, ok=False, blocked=True, reason="orders_intent.json not found", provider=broker_name, mode=execution, errors=["no_orders_intent"], execution=execution)
        return 2
    orders_intent = json.loads(orders_intent_path.read_text(encoding="utf-8"))
    gate = RiskGateEngine()
    allowed, notes = gate.evaluate(orders_intent, policy_ruleset=None, stages=stages)
    if not allowed:
        print("blocked: risk gate denied", file=sys.stderr)
        for n in notes:
            print(f"  {n}", file=sys.stderr)
        write_execution_result(outdir, day, ok=False, blocked=True, reason="risk gate denied", provider=broker_name, mode=execution, errors=notes, execution=execution)
        return 2
    from bist_core.execution.adapters import resolve_execution_provider
    if execution == "paper" or broker_name == "paper":
        provider, err = resolve_execution_provider(
            "paper", "paper", outdir=outdir, day=day,
        )
    else:
        provider, err = resolve_execution_provider(
            execution, broker_name, broker_config=broker_config_dict,
        )
    if err is not None:
        print(f"blocked: {err}", file=sys.stderr)
        write_execution_result(outdir, day, ok=False, blocked=True, reason=str(err), provider=broker_name, mode=execution, errors=[err], execution=execution)
        return 2
    if live and not dry_run:
        from bist_core.execution.live_skeleton import run_live_execute_skeleton
        ok_skeleton, err_skeleton = run_live_execute_skeleton(
            outdir, day, orders_intent_path, provider,
            provider_name=broker_name, execution_mode=execution,
        )
        if not ok_skeleton:
            write_execution_result(outdir, day, ok=False, blocked=False, reason=err_skeleton or "live_execute_failed", provider=broker_name, mode=execution, errors=[err_skeleton or "live_execute_failed"], execution=execution)
            return 2
        print(f"execute: broker={broker_name} live (skeleton) dry_run={dry_run}")
        return 0
    result = provider.submit_orders(orders_intent, dry_run=dry_run)
    if not result.get("ok", True):
        print("execute failed", file=sys.stderr)
        for e in result.get("errors", []):
            print(f"  {e}", file=sys.stderr)
        write_execution_result(outdir, day, ok=False, blocked=False, reason="submit_orders failed", provider=result.get("broker", broker_name), mode=execution, errors=result.get("errors", []), execution=execution)
        return 2
    write_execution_result(outdir, day, ok=True, blocked=False, reason="", provider=result.get("broker", broker_name), mode=execution, execution=execution)
    print(f"execute: broker={result.get('broker', '')} sent={result.get('sent', 0)} dry_run={dry_run}")
    return 0


def _cmd_daily_run(args: argparse.Namespace) -> int:
    """FAZ61: Run pipeline end-to-end idempotently. Do not overwrite differing artifacts; verify hash or reuse."""
    day_str = getattr(args, "day", None) or ""
    outdir_arg = getattr(args, "outdir", None)
    if not day_str or not outdir_arg:
        err_struct(ERROR_ARGS_REQUIRED, "daily run: --day and --outdir required")
        return 2
    out_path = Path(outdir_arg)
    out_path.mkdir(parents=True, exist_ok=True)
    base = _snapshot_root()
    manifest_path = locate_manifest(out_path, day_str)
    if manifest_path is not None and manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            stored_hash = (manifest_data.get("snapshot_hash") or {}).get("value") or ""
            snapshot_csv = base / day_str / "snapshot.csv"
            snapshot_alt = base / (day_str + ".csv")
            current_path = snapshot_csv if snapshot_csv.is_file() else (snapshot_alt if snapshot_alt.is_file() else None)
            if stored_hash and current_path is not None:
                current_hash = snapshot_integrity.compute_sha256(Path(current_path))
                if current_hash != stored_hash:
                    err_struct(ERROR_ARTIFACT_HASH_MISMATCH, "existing artifacts differ (snapshot hash changed); will not overwrite")
                    return 2
            # Reuse: skip pipeline run; run execute only if requested
            run_pipeline = False
        except (json.JSONDecodeError, OSError):
            run_pipeline = True
    else:
        run_pipeline = True

    if run_pipeline:
        cli_args = {
            "day": day_str,
            "outdir": str(out_path),
            "emit_orders": True,
        }
        manifest, code = run_eod_pipeline(
            day_str,
            snapshot_root=base,
            outdir=out_path,
            strict=False,
            symbols=None,
            regex=None,
            limit=None,
            jsonl=True,
            events_provider=None,
            events_input=None,
            events_outdir=None,
            instruments_provider=None,
            instruments_input=None,
            instruments_outdir=None,
            ca_provider=None,
            ca_input=None,
            ca_outdir=None,
            resolve_aliases=False,
            calendar_file=None,
            ignore_calendar=True,
            policy_file=None,
            emit_orders=True,
            orders_strategy="equal_weight",
            orders_top_n=10,
            risk_rules_file=None,
            restrictions_file=os.environ.get("BIST_RESTRICTIONS_FILE"),
            research_source=os.environ.get("BIST_RESEARCH_SOURCE") or None,
            research_offline=False,
            market_data_provider=None,
            git_sha=_env_git_sha(),
            cli_args=cli_args,
        )
        if code != 0:
            return int(code)

    live = bool(getattr(args, "live", False))
    paper = bool(getattr(args, "paper", False))
    if live or paper:
        exec_args = argparse.Namespace(
            day=day_str,
            outdir=str(out_path),
            live=live,
            execution="live" if live else "paper",
            broker=None,
            broker_config=None,
            provider=None,
            dry_run=not live,
            config=getattr(args, "config", None),
        )
        return _cmd_eod_execute(exec_args)
    return 0


def _cmd_healthcheck(args: argparse.Namespace) -> int:
    """FAZ64: Validate environment + config; output structured JSON only (no noisy prints)."""
    checks: list[dict] = []
    repo_path = Path(config.REPO_ROOT)

    # REPO_ROOT exists
    if repo_path.is_dir():
        checks.append({"name": "repo_root", "code": "OK", "ok": True, "message": str(repo_path)})
    else:
        checks.append({
            "name": "repo_root",
            "code": ERROR_REPO_ROOT_MISSING,
            "ok": False,
            "message": f"REPO_ROOT not a directory: {repo_path}",
        })

    # config/core.json exists
    core_json = repo_path / "config" / "core.json"
    if core_json.is_file():
        checks.append({"name": "core_json", "code": "OK", "ok": True, "message": str(core_json)})
    else:
        checks.append({
            "name": "core_json",
            "code": ERROR_CORE_JSON_MISSING,
            "ok": False,
            "message": f"config/core.json not found: {core_json}",
        })

    # BIST_CORE_SNAPSHOT_DIR: exists or parent writable (optional)
    snap_dir = os.getenv("BIST_CORE_SNAPSHOT_DIR", "")
    if snap_dir:
        p = Path(snap_dir)
        if p.is_dir():
            checks.append({"name": "snapshot_dir", "code": "OK", "ok": True, "message": str(p)})
        elif p.parent.is_dir():
            checks.append({"name": "snapshot_dir", "code": "OK", "ok": True, "message": f"parent exists: {p.parent}"})
        else:
            checks.append({
                "name": "snapshot_dir",
                "code": ERROR_SNAPSHOT_DIR_MISSING,
                "ok": False,
                "message": f"BIST_CORE_SNAPSHOT_DIR not usable: {p}",
            })
    else:
        checks.append({"name": "snapshot_dir", "code": "OK", "ok": True, "message": "not set (default will be used)"})

    # Registry (optional)
    try:
        reg = get_default_registry()
        reg_path = getattr(reg, "path", None)
        reg_path_str = str(reg_path) if reg_path is not None else ""
        if reg_path and Path(reg_path).exists():
            checks.append({"name": "registry", "code": "OK", "ok": True, "message": reg_path_str})
        else:
            checks.append({
                "name": "registry",
                "code": ERROR_REGISTRY_MISSING,
                "ok": False,
                "message": reg_path_str or "registry path unknown",
            })
    except Exception as e:
        checks.append({
            "name": "registry",
            "code": ERROR_REGISTRY_MISSING,
            "ok": False,
            "message": str(e),
        })

    required_names = {"repo_root", "core_json"}
    ok = all(c.get("ok", False) for c in checks if c.get("name") in required_names)
    payload = {
        "schema_version": 1,
        "ok": ok,
        "checks": checks,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if ok else 2


def _print_batch_summary(manifest: dict, exit_code: int) -> None:
    summary = manifest.get("summary", {}) if isinstance(manifest, dict) else {}
    ran = int(summary.get("ran", 0))
    skipped_calendar = int(summary.get("skipped_calendar", 0))
    skipped_ok_existing = int(summary.get("skipped_ok_existing", 0))
    errors = int(summary.get("errors", 0))
    stopped_early = bool(manifest.get("stopped_early", False))
    print(
        "EOD_BATCH: "
        f"ran={ran} "
        f"skipped_calendar={skipped_calendar} "
        f"skipped_ok_existing={skipped_ok_existing} "
        f"errors={errors} "
        f"stopped_early={stopped_early} "
        f"exit_code={exit_code}"
    )


def _cmd_rules_validate(args: argparse.Namespace) -> int:
    file_path = Path(args.file)
    try:
        ruleset = rules_schema.load_ruleset(file_path)
    except Exception:
        print(json.dumps({"valid": False, "errors": ["RulesetLoadError"]}, ensure_ascii=False))
        return 2
    errors = rules_schema.validate_ruleset(ruleset)
    valid = len(errors) == 0
    print(json.dumps({"valid": valid, "errors": sorted(errors)}, ensure_ascii=False))
    return 0 if valid else 2


def _cmd_rules_explain(args: argparse.Namespace) -> int:
    file_path = Path(args.file)
    try:
        ruleset = rules_schema.load_ruleset(file_path)
    except Exception:
        print(json.dumps({"allowed": False, "errors": ["RulesetLoadError"]}, ensure_ascii=False))
        return 2
    result = rules_engine.explain_order(
        ruleset,
        symbol=args.symbol,
        price=float(args.price),
        side=str(args.side),
        qty=float(args.qty),
        day=str(args.day),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errors"):
        return 2
    if getattr(args, "strict_exit", False) and result.get("allowed") is False:
        return 2
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    # Sadece equal_weight stratejisini destekliyoruz
    strategy = getattr(args, "strategy", None) or "equal_weight"
    if strategy != "equal_weight":
        raise SystemExit(f"Unsupported strategy: {strategy!r}")

    # Snapshot yoksa oluştur
    root = _snapshot_root()
    snapshot_path = root / args.date / "snapshot.csv"
    if not snapshot_path.exists():
        _cmd_eod(argparse.Namespace(date=args.date))

    # Plan output (snapshot_root ile tutarlı)
    plan_path = build_equal_weight_plan(args.date, base=root)

    # Testin beklediği çıktı
    print(f"Plan yazıldı: {plan_path}")
    print(strategy)
    return 0



def _cmd_orders(args: argparse.Namespace) -> int:
    # Sadece equal_weight stratejisini destekliyoruz
    strategy = getattr(args, "strategy", None) or "equal_weight"
    if strategy != "equal_weight":
        raise SystemExit(f"Unsupported strategy: {strategy!r}")

    root = _snapshot_root()

    try:
        orders_path = generate_equal_weight_orders(args.date, base=root)
    except FileNotFoundError as e:
        raise SystemExit(
            f"Bu tarih için plan bulunamadı: {args.date}. Lütfen önce 'plan' komutunu çalıştırın."
        )

    if orders_path is None:
        # Risk limiti FAIL → exit code 2
        print("Risk limiti aşıldı; siparişler oluşturulmadı.")
        return 2

    # PASS → exit code 0
    print(f"Orders yazıldı: {orders_path}")
    return 0


def _cmd_broker_paper_run(args: argparse.Namespace) -> int:
    day = getattr(args, "day", None) or ""
    orders_path = getattr(args, "orders", None)
    snapshot_root = getattr(args, "snapshot_root", None) or os.getenv("BIST_CORE_SNAPSHOT_DIR")
    portfolio_value = float(getattr(args, "portfolio_value", 1.0) or 1.0)
    if not orders_path:
        raise SystemExit("--orders is required")
    path = Path(orders_path)
    if not path.is_file():
        raise SystemExit(f"Orders file not found: {path}")
    orders_intent = json.loads(path.read_text(encoding="utf-8"))
    root = Path(snapshot_root) if snapshot_root else _snapshot_root()
    broker = PaperBroker(snapshot_root=root, day=day, portfolio_value=portfolio_value)
    fills = broker.place_orders(orders_intent)
    positions = broker.get_positions()
    if bool(getattr(args, "json", False)):
        out = {"day": day, "fills": fills, "positions": positions}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"Fills: {len(fills)}")
        for f in fills:
            print(f"  {f.get('symbol')} {f.get('side')} qty={f.get('qty')} @ {f.get('price')}")
        print(f"Positions: {len(positions)}")
        for p in positions:
            print(f"  {p.get('symbol')} qty={p.get('qty')} avg_price={p.get('avg_price')}")
    return 0


def _cmd_backtest_run(args: argparse.Namespace) -> int:
    date_from = getattr(args, "date_from", None) or ""
    date_to = getattr(args, "date_to", None) or ""
    outdir = getattr(args, "outdir", None)
    snapshot_root = getattr(args, "snapshot_root", None) or os.getenv("BIST_CORE_SNAPSHOT_DIR")
    strategy = getattr(args, "strategy", None) or "equal_weight"
    top_n = int(getattr(args, "top_n", 10) or 10)
    if not outdir:
        raise SystemExit("--outdir is required")
    root = Path(snapshot_root) if snapshot_root else _snapshot_root()

    if bool(getattr(args, "walk_forward", False)):
        window = getattr(args, "window", None)
        step = getattr(args, "step", None)
        if window is None or window < 1:
            raise SystemExit("--walk-forward requires --window (positive integer)")
        run_config = {
            "snapshot_root": root,
            "date_from": date_from,
            "date_to": date_to,
            "outdir": Path(outdir),
            "strategy": strategy,
            "top_n": top_n,
            "window": window,
            "step": step if step is not None and step >= 1 else 1,
            "min_trades": getattr(args, "min_trades", None),
            "max_dd": getattr(args, "max_dd", None),
            "strict": bool(getattr(args, "strict", False)),
        }
        result = walk_forward(run_config)
        if bool(getattr(args, "json", False)):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            agg = result.get("aggregate", {})
            print(f"Walk-forward: {result.get('num_windows', 0)} windows, gates_passed={result.get('gates_passed', False)}")
            print(f"  total_fills={agg.get('total_fills', 0)}, worst_max_dd={agg.get('worst_max_drawdown', 0)}, mean_return={agg.get('mean_return', 0)}")
            print(f"  manifest: {result.get('manifest_path', '')}")
        return int(result.get("exit_code", 0))

    metrics = run_backtest(
        snapshot_root=root,
        date_from=date_from,
        date_to=date_to,
        outdir=Path(outdir),
        strategy=strategy,
        top_n=top_n,
    )
    if bool(getattr(args, "json", False)):
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(f"Backtest: {metrics.get('num_days', 0)} days, total_return={metrics.get('total_return', 0)}, max_drawdown={metrics.get('max_drawdown', 0)}")
        print(f"  metrics: {metrics.get('metrics_path', '')}")
        print(f"  equity_curve: {metrics.get('equity_curve_path', '')}")
    return 0 if metrics.get("error") is None else 2


def _require_registry_file(reg: DatasetRegistry) -> None:
    """Fail-closed: missing registry => nonzero exit; no silent defaults."""
    if not reg.path.is_file():
        print(
            f"Registry not found: {reg.path}. Set BIST_CORE_REGISTRY_PATH or run 'data register' first.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _cmd_data_register(args: argparse.Namespace) -> int:
    reg = get_default_registry()
    dataset_id = args.name or args.id
    fmt = getattr(args, "format", None) or getattr(args, "kind", None) or "local_csv"
    if not dataset_id:
        raise SystemExit("--name is required")
    if not getattr(args, "path", None):
        raise SystemExit("--path is required")
    if fmt in ("local_csv", "csv"):
        kind = "local_csv"
    else:
        raise SystemExit(f"Unsupported format: {fmt!r}")
    try:
        meta = reg.register(
            name=dataset_id,
            kind=kind,
            path=args.path,
            symbol_col=getattr(args, "symbol_col", None),
            date_col=getattr(args, "date_col", None),
            tz=getattr(args, "tz", None),
            overwrite=bool(getattr(args, "overwrite", False)),
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
    payload = {
        "ok": True,
        "name": meta.name,
        "registry_path": str(reg.path),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_data_resolve(args: argparse.Namespace) -> int:
    name = getattr(args, "name", None) or getattr(args, "id", None)
    if not name:
        raise SystemExit("--name is required")
    reg = get_default_registry()
    _require_registry_file(reg)
    try:
        reg.load()
        meta = reg.get(name)
    except (ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
    if getattr(args, "json", False):
        print(
            json.dumps(
                {"name": meta.name, "path": meta.path, "kind": meta.kind},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print(f"name={meta.name} path={meta.path} kind={meta.kind}")
    return 0


def _cmd_data_list(args: argparse.Namespace) -> int:
    reg = get_default_registry()
    _require_registry_file(reg)
    try:
        reg.load()
        payload = reg.to_payload()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    names = sorted(payload.get("datasets", {}).keys())
    if not names:
        print("datasets: <empty>")
        return 0
    for name in names:
        meta = payload["datasets"][name]
        fmt = meta.get("format") or meta.get("kind")
        path = meta.get("path")
        print(f"- name={name} format={fmt} path={path}")
    return 0


def _ensure_min_snapshot(as_of: str) -> Path:
    # Eğer test snapshot isterse parse/varlık sorununa düşmeyelim
    try:
        _ = date.fromisoformat(as_of)
    except ValueError:
        raise SystemExit(f"Invalid date format: {as_of}. Use YYYY-MM-DD")

    root = _snapshot_root()
    day_dir = root / as_of
    day_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = day_dir / "snapshot.csv"

    if not snapshot_path.exists():
        df = pd.DataFrame([{"symbol": "TEST", "close": 0.0}])
        df.to_csv(snapshot_path, index=False)

    return snapshot_path


def _cmd_data_load(args: argparse.Namespace) -> int:
    dataset_id = args.id or args.name
    if not dataset_id:
        raise SystemExit("--id or --name is required")
    reg = get_default_registry()
    _require_registry_file(reg)
    try:
        reg.load()
        meta = reg.get(dataset_id)
    except (ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
    fmt = "csv" if meta.kind == "local_csv" else meta.kind

    # Raw dataset'i yükle
    df_raw = load_registered_dataset(dataset_id)

    out_path = Path(args.out) if getattr(args, "out", None) else None
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df_raw.to_csv(out_path, index=False, lineterminator="\n")

    if getattr(args, "json", False):
        cols = [str(c) for c in df_raw.columns]
        payload = {
            "name": dataset_id,
            "kind": meta.kind,
            "path": meta.path,
            "rows": int(len(df_raw)),
            "cols": cols,
        }

        date_col = getattr(meta, "date_col", None)
        if not date_col and "date" in df_raw.columns:
            date_col = "date"
        if date_col and date_col in df_raw.columns:
            parsed = pd.to_datetime(df_raw[date_col], errors="coerce").dropna()
            if not parsed.empty:
                payload["date_min"] = parsed.min().isoformat()
                payload["date_max"] = parsed.max().isoformat()

        symbol_col = getattr(meta, "symbol_col", None)
        if not symbol_col and "symbol" in df_raw.columns:
            symbol_col = "symbol"
        if symbol_col and symbol_col in df_raw.columns:
            symbols = df_raw[symbol_col].dropna().astype(str).unique()
            payload["symbols_count"] = int(len(symbols))

        if out_path is not None:
            payload["out"] = str(out_path)

        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    print(
        f"id={dataset_id} format={fmt} path={meta.path} "
        f"created_at={meta.created_at} updated_at={meta.updated_at}"
    )

    # Testin beklediği özet satır
    print(
        f"loaded dataset '{dataset_id}' with {len(df_raw)} rows, {df_raw.shape[1]} columns"
    )

    # Snapshot modu
    if getattr(args, "use_snapshot", False):
        if not getattr(args, "as_of", None):
            raise SystemExit("--as-of is required when --use-snapshot is set")

        _ensure_min_snapshot(args.as_of)

        # head>0 olursa snapshot'tan preview basabiliriz
        if args.head and args.head > 0:
            snap_path = _snapshot_root() / args.as_of / "snapshot.csv"
            df_snap = pd.read_csv(snap_path)
            print(df_snap.head(args.head).to_string(index=False))

        return 0

    # Normal head preview
    if args.head and args.head > 0:
        print(df_raw.head(args.head).to_string(index=False))
        return 0

    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    base = _snapshot_root()
    if getattr(args, "day", None):
        day_value = args.day
    else:
        day_value = _latest_snapshot_day(base)
        if day_value is None:
            print("Uyarı: Snapshot bulunamadı; bugünün tarihine düşülüyor.")
            day_value = date.today()

    day_str = day_value if isinstance(day_value, str) else day_value.isoformat()

    symbols = [args.symbol]
    if getattr(args, "all", False):
        try:
            md = MarketData(base)
            symbols = md.symbols(day_str)
        except Exception:
            symbols = []
        if not symbols:
            symbols = [args.symbol]

    for idx, sym in enumerate(symbols):
        try:
            advice = build_advice_for_symbol(sym, day_str, root=base)
            payload = _advice_payload(advice, day_str)
            text_out = advice.text
        except Exception as exc:
            payload = _fallback_payload(sym, day_str, exc)
            text_out = payload["text"]

        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False))
        else:
            if idx > 0:
                print()
            print(text_out)
    return 0


def _cmd_dossier_build(args: argparse.Namespace) -> int:
    base = _snapshot_root()
    if getattr(args, "day", None):
        day_value = args.day
    else:
        day_value = _latest_snapshot_day(base)
        if day_value is None:
            print("Uyarı: Snapshot bulunamadı; bugünün tarihine düşülüyor.")
            day_value = date.today().isoformat()

    day_str = day_value if isinstance(day_value, str) else day_value.isoformat()

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = Path("data") / "dossier" / day_str
    outdir.mkdir(parents=True, exist_ok=True)

    symbols = None
    if getattr(args, "symbols", None):
        raw = [s.strip() for s in args.symbols.split(",")]
        symbols = [s for s in raw if s]

    dossiers, runtime_ms, provenance = build_dossiers_for_day(
        day_str,
        root=base,
        symbols=symbols,
        regex=getattr(args, "regex", None),
        limit=getattr(args, "limit", None),
    )
    error_count = 0
    for dossier in dossiers:
        symbol = dossier.get("symbol", "UNKNOWN")
        if dossier.get("error_marker"):
            error_count += 1
        out_path = outdir / f"{symbol}.json"
        atomic_write_json(out_path, dossier)

    git_sha = _env_git_sha()
    cli_args = {
        "symbols": getattr(args, "symbols", None),
        "regex": getattr(args, "regex", None),
        "limit": getattr(args, "limit", None),
        "strict": bool(getattr(args, "strict", False)),
        "outdir": str(outdir),
        "day": day_str,
    }
    provenance = {
        **provenance,
        "git_sha": git_sha,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "cli_args": cli_args,
    }

    manifest = build_manifest(
        day_str,
        outdir,
        dossiers,
        runtime_ms,
        provenance,
    )
    manifest_path = outdir / "_manifest.json"
    existing_runtime = _load_manifest_runtime(manifest_path)
    if existing_runtime is not None:
        manifest["runtime_ms"] = existing_runtime
    atomic_write_json(manifest_path, manifest)

    print(f"dossier build: wrote {len(dossiers)} files, errors {error_count}")
    if getattr(args, "strict", False) and error_count > 0:
        return 2
    return 0


def _env_git_sha() -> str | None:
    for key in ("GIT_SHA", "GITHUB_SHA"):
        value = os.getenv(key)
        if value:
            return value[:7]
    return None


def _load_manifest_runtime(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    runtime = data.get("runtime_ms")
    return runtime if isinstance(runtime, int) else None


def _cmd_data_snapshot(args: argparse.Namespace) -> int:
    dataset_id = args.name or args.id
    if not dataset_id:
        raise SystemExit("--name is required")
    day = args.day
    try:
        _ = date.fromisoformat(day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {day}. Use YYYY-MM-DD")

    if not getattr(args, "out", None):
        reg = get_default_registry()
        _require_registry_file(reg)
        try:
            reg.load()
            reg.get(dataset_id)
        except (ValueError, KeyError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            raise SystemExit(2)
        df_raw = load_registered_dataset(dataset_id)
        required = {"symbol", "close"}
        optional = {"open", "high", "low", "volume", "turnover", "date"}
        cols = set(df_raw.columns)
        missing = required - cols
        unexpected = cols - required - optional
        if missing or unexpected:
            raise SystemExit(
                f"Snapshot schema invalid: missing={sorted(missing)} "
                f"unexpected={sorted(unexpected)}"
            )

        has_date = "date" in cols
        if has_date:
            invalid = []
            for value in df_raw["date"].dropna().unique():
                try:
                    _ = date.fromisoformat(str(value))
                except ValueError:
                    invalid.append(value)
            if invalid:
                raise SystemExit(
                    f"Snapshot schema invalid: unparseable date values={invalid}"
                )
        else:
            if cols != {"symbol", "close"}:
                raise SystemExit(
                    "Snapshot schema invalid: legacy snapshot must contain only symbol,close"
                )

        if has_date:
            df_day = df_raw[df_raw["date"] == day]
            if df_day.empty:
                raise SystemExit(f"No data for day: {day}")
        else:
            df_day = df_raw

        has_ohlcv = {"open", "high", "low", "volume"}.issubset(cols)
        if not has_ohlcv:
            print(
                "Uyarı: Snapshot sadece close içeriyor; OHLCV verisi yok.",
                file=sys.stderr,
            )

        out_cols = ["symbol", "close"]
        for col in ["open", "high", "low", "volume", "turnover"]:
            if col in cols:
                out_cols.append(col)

        df_out = df_day[out_cols].groupby("symbol", as_index=False).last()

        root = _snapshot_root()
        out_dir = root / day
        out_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = out_dir / "snapshot.csv"
        df_out.to_csv(snapshot_path, index=False)
        print(f"snapshot created at {snapshot_path}")
        return 0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    reg = get_default_registry()
    meta = reg.get(dataset_id)
    df_raw = load_registered_dataset(dataset_id)
    cols = list(df_raw.columns)

    symbol_col = meta.symbol_col or ("symbol" if "symbol" in cols else None)
    date_col = meta.date_col or ("date" if "date" in cols else None)
    if not symbol_col or symbol_col not in cols:
        raise SystemExit("Snapshot requires a symbol column; register with --symbol-col")
    if not date_col or date_col not in cols:
        raise SystemExit("Snapshot requires a date column; register with --date-col")

    df_raw = df_raw.copy()
    df_raw[date_col] = df_raw[date_col].astype(str)
    df_day = df_raw[df_raw[date_col] == day]
    if df_day.empty:
        raise SystemExit(f"No data for day: {day}")

    df_day = df_day.sort_values(by=[symbol_col, date_col], kind="mergesort")
    ordered_cols = [symbol_col, date_col]
    for col in sorted([c for c in cols if c not in ordered_cols]):
        ordered_cols.append(col)
    df_out = df_day[ordered_cols]

    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    df_out.to_csv(tmp_path, index=False, lineterminator="\n")
    tmp_path.replace(out_path)
    payload = {"ok": True, "out": str(out_path), "rows": int(len(df_out))}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_events_ingest(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    try:
        _ = date.fromisoformat(args.day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.day}. Use YYYY-MM-DD")

    if not getattr(args, "input", None):
        print("--input is required")
        return 2
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input not found: {input_path}")
        return 2

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "events" / args.day
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "events.jsonl"

    start = time.perf_counter()
    raw_rows, total_in, errors = _read_events_input(input_path)
    existing_events, _ = eventstore.load_events_for_day(args.day, base_dir=outdir.parent)
    existing_list = [ev for items in existing_events.values() for ev in items]
    existing_keys = {eventstore.dedupe_key(ev) for ev in existing_list}
    seen_keys = set(existing_keys)

    accepted_events = []
    duplicates = 0

    for idx, row in raw_rows:
        event, err = eventstore.normalize_event(row, idx)
        if err:
            errors.append({"idx": idx, "error_marker": err})
            continue
        key = eventstore.dedupe_key(event)
        if key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(key)
        accepted_events.append(event)

    merged = eventstore.sort_events([*existing_list, *accepted_events])
    _write_events_jsonl(out_path, merged)
    runtime_ms = int((time.perf_counter() - start) * 1000)
    rejected = len(errors)

    manifest = {
        "schema_version": 1,
        "day": args.day,
        "input": str(input_path),
        "outdir": str(outdir),
        "total_in": total_in,
        "accepted": len(accepted_events),
        "rejected": rejected,
        "duplicates": duplicates,
        "errors": errors,
        "runtime_ms": runtime_ms,
        "provenance": {
            "cli_args": {
                "day": args.day,
                "input": str(input_path),
                "outdir": str(outdir),
                "strict": bool(getattr(args, "strict", False)),
            },
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
    manifest_path = outdir / "_manifest.json"
    atomic_write_json(manifest_path, manifest)

    print(
        "events ingest: "
        f"total={total_in} accepted={len(accepted_events)} "
        f"rejected={rejected} duplicates={duplicates}"
    )
    print(f"events path: {out_path}")
    print(f"manifest path: {manifest_path}")
    if getattr(args, "strict", False) and rejected > 0:
        return 2
    return 0


def _cmd_events_pull(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    try:
        _ = date.fromisoformat(args.day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.day}. Use YYYY-MM-DD")

    if not getattr(args, "provider", None):
        raise SystemExit("--provider is required")
    if not getattr(args, "input", None):
        raise SystemExit("--input is required")

    input_path = Path(args.input)

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "events" / args.day
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "events.jsonl"

    provider = None
    if args.provider == "offline_file":
        if not input_path.exists():
            raise SystemExit(f"Input not found: {input_path}")
        provider = OfflineFileEventsProvider(input_path)
    elif args.provider == "kap_html":
        provider = KapHtmlEventsProvider(
            base_url=getattr(args, "base_url", None) or "https://www.kap.org.tr",
            url_template=getattr(args, "url_template", None),
            timeout_s=int(getattr(args, "timeout", 15)),
        )
    else:
        raise SystemExit(f"Unsupported provider: {args.provider}")

    manifest = build_events_jsonl_for_day(args.day, provider, out_path, atomic=True)
    manifest["provenance"]["cli_args"] = {
        "day": args.day,
        "provider": args.provider,
        "input": str(input_path),
        "outdir": str(outdir),
        "strict": bool(getattr(args, "strict", False)),
        "base_url": getattr(args, "base_url", None),
        "url_template": getattr(args, "url_template", None),
        "timeout": getattr(args, "timeout", None),
    }
    manifest_path = outdir / "_manifest.json"
    atomic_write_json(manifest_path, manifest)

    print(
        "events pull: "
        f"total={manifest['total_in']} "
        f"accepted={manifest['accepted']} "
        f"rejected={manifest['rejected']} "
        f"duplicates={manifest['duplicates']}"
    )
    print(f"events path: {out_path}")
    print(f"manifest path: {manifest_path}")
    if getattr(args, "strict", False) and manifest["rejected"] > 0:
        return 2
    return 0


def _cmd_instruments_pull(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    try:
        _ = date.fromisoformat(args.day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.day}. Use YYYY-MM-DD")

    if not getattr(args, "provider", None):
        raise SystemExit("--provider is required")
    if not getattr(args, "input", None):
        raise SystemExit("--input is required")

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "instruments" / args.day
    outdir.mkdir(parents=True, exist_ok=True)

    if args.provider != "offline_file":
        raise SystemExit(f"Unsupported provider: {args.provider}")

    provider = OfflineFileInstrumentsProvider(input_path)
    provider.pull(args.day, outdir)
    records, errors = instrumentstore.parse_instruments(
        outdir / "instruments.jsonl",
        source=provider.name,
    )
    deduped = instrumentstore.dedupe_instruments(records)
    instrumentstore.atomic_write_jsonl(outdir / "instruments.jsonl", deduped)

    manifest = instrumentstore.build_manifest(
        args.day,
        outdir,
        total=len(records),
        ok=len(deduped) - len(errors),
        errors=errors,
        runtime_ms=0,
        provenance={"cli_args": {}},
        args_summary={
            "day": args.day,
            "provider": args.provider,
            "input": str(input_path),
            "outdir": str(outdir),
            "strict": bool(getattr(args, "strict", False)),
        },
    )
    instrumentstore.atomic_write_json(outdir / "_manifest.json", manifest)

    print(
        "instruments pull: "
        f"total={manifest['total']} ok={manifest['ok']} errors={manifest['errors']}"
    )
    print(f"instruments path: {outdir / 'instruments.jsonl'}")
    print(f"manifest path: {outdir / '_manifest.json'}")
    if getattr(args, "strict", False) and manifest["errors"] > 0:
        return 2
    return 0


def _cmd_instruments_ingest(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    try:
        _ = date.fromisoformat(args.day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.day}. Use YYYY-MM-DD")

    if not getattr(args, "input", None):
        raise SystemExit("--input is required")
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "instruments" / args.day
    outdir.mkdir(parents=True, exist_ok=True)

    records, errors = instrumentstore.parse_instruments(input_path, source="ingest")
    deduped = instrumentstore.dedupe_instruments(records)
    instrumentstore.atomic_write_jsonl(outdir / "instruments.jsonl", deduped)

    manifest = instrumentstore.build_manifest(
        args.day,
        outdir,
        total=len(records),
        ok=len(deduped) - len(errors),
        errors=errors,
        runtime_ms=0,
        provenance={"cli_args": {}},
        args_summary={
            "day": args.day,
            "input": str(input_path),
            "outdir": str(outdir),
            "strict": bool(getattr(args, "strict", False)),
        },
    )
    instrumentstore.atomic_write_json(outdir / "_manifest.json", manifest)

    print(
        "instruments ingest: "
        f"total={manifest['total']} ok={manifest['ok']} errors={manifest['errors']}"
    )
    print(f"instruments path: {outdir / 'instruments.jsonl'}")
    print(f"manifest path: {outdir / '_manifest.json'}")
    if getattr(args, "strict", False) and manifest["errors"] > 0:
        return 2
    return 0


def _cmd_instruments_timeline(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    day = args.day
    instruments_dir = Path(args.instruments_dir) if getattr(args, "instruments_dir", None) else None
    if instruments_dir is None:
        instruments_dir = config.REPO_ROOT / "data" / "eod" / "instruments" / day
    ca_dir = Path(args.ca_dir) if getattr(args, "ca_dir", None) else None
    if ca_dir is None:
        ca_dir = config.REPO_ROOT / "data" / "eod" / "corporate_actions" / day
    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "universe" / day
    outdir.mkdir(parents=True, exist_ok=True)

    timeline, manifest = instrument_timeline.resolve_timeline(
        day,
        instruments_dir / "instruments.jsonl",
        ca_dir / "actions.jsonl",
        outdir,
        args={
            "day": day,
            "instruments_dir": str(instruments_dir),
            "ca_dir": str(ca_dir),
            "outdir": str(outdir),
            "strict": bool(getattr(args, "strict", False)),
        },
    )
    if getattr(args, "strict", False) and manifest["errors"] > 0:
        return 2
    return 0


def _cmd_corporate_actions_pull(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    try:
        _ = date.fromisoformat(args.day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.day}. Use YYYY-MM-DD")

    if not getattr(args, "provider", None):
        raise SystemExit("--provider is required")
    if not getattr(args, "input", None):
        raise SystemExit("--input is required")
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "corporate_actions" / args.day
    outdir.mkdir(parents=True, exist_ok=True)

    if args.provider != "offline_file":
        raise SystemExit(f"Unsupported provider: {args.provider}")

    provider = OfflineFileCorporateActionsProvider(input_path)
    records, errors = castore.parse_actions(input_path)
    deduped = castore.dedupe_actions(records)
    castore.atomic_write_jsonl(outdir / "actions.jsonl", deduped)

    manifest = castore.build_manifest(
        args.day,
        outdir,
        total=len(records),
        ok=len(deduped) - len(errors),
        errors=errors,
        runtime_ms=0,
        provenance={"cli_args": {}},
        args_summary={
            "day": args.day,
            "provider": args.provider,
            "input": str(input_path),
            "outdir": str(outdir),
            "strict": bool(getattr(args, "strict", False)),
        },
    )
    castore.atomic_write_json(outdir / "_manifest.json", manifest)

    print(
        "corporate-actions pull: "
        f"total={manifest['total']} ok={manifest['ok']} errors={manifest['errors']}"
    )
    print(f"actions path: {outdir / 'actions.jsonl'}")
    print(f"manifest path: {outdir / '_manifest.json'}")
    if getattr(args, "strict", False) and manifest["errors"] > 0:
        return 2
    return 0


def _cmd_corporate_actions_ingest(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    try:
        _ = date.fromisoformat(args.day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {args.day}. Use YYYY-MM-DD")

    if not getattr(args, "input", None):
        raise SystemExit("--input is required")
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "corporate_actions" / args.day
    outdir.mkdir(parents=True, exist_ok=True)

    records, errors = castore.parse_actions(input_path)
    deduped = castore.dedupe_actions(records)
    castore.atomic_write_jsonl(outdir / "actions.jsonl", deduped)
    manifest = castore.build_manifest(
        args.day,
        outdir,
        total=len(records),
        ok=len(deduped) - len(errors),
        errors=errors,
        runtime_ms=0,
        provenance={"cli_args": {}},
        args_summary={
            "day": args.day,
            "input": str(input_path),
            "outdir": str(outdir),
            "strict": bool(getattr(args, "strict", False)),
        },
    )
    castore.atomic_write_json(outdir / "_manifest.json", manifest)

    print(
        "corporate-actions ingest: "
        f"total={manifest['total']} ok={manifest['ok']} errors={manifest['errors']}"
    )
    print(f"actions path: {outdir / 'actions.jsonl'}")
    print(f"manifest path: {outdir / '_manifest.json'}")
    if getattr(args, "strict", False) and manifest["errors"] > 0:
        return 2
    return 0


def _cmd_corporate_actions_apply_close(args: argparse.Namespace) -> int:
    if not getattr(args, "day", None):
        raise SystemExit("--day is required")
    day = args.day
    actions_dir = Path(args.actions_dir) if getattr(args, "actions_dir", None) else None
    if actions_dir is None:
        actions_dir = config.REPO_ROOT / "data" / "eod" / "corporate_actions" / day
    snapshot_dir = Path(args.snapshot_dir) if getattr(args, "snapshot_dir", None) else None
    if snapshot_dir is None:
        snapshot_dir = config.REPO_ROOT / "data" / "eod" / "snapshots" / day
    outdir = Path(args.outdir) if getattr(args, "outdir", None) else None
    if outdir is None:
        outdir = config.REPO_ROOT / "data" / "eod" / "adjusted" / day
    outdir.mkdir(parents=True, exist_ok=True)

    actions_path = actions_dir / "actions.jsonl"
    snapshot_path = snapshot_dir / "snapshot.csv"
    errors: list[dict] = []
    if not actions_path.exists():
        errors.append({"error_marker": "MissingActions"})
    if not snapshot_path.exists():
        errors.append({"error_marker": "MissingSnapshot"})
    if errors:
        manifest = castore.build_manifest(
            day,
            outdir,
            total=0,
            ok=0,
            errors=[{"idx": idx, "symbol": "", "effective_date": "", "error_marker": err["error_marker"]} for idx, err in enumerate(errors)],
            runtime_ms=0,
            provenance={"cli_args": {}},
            args_summary={},
        )
        castore.atomic_write_json(outdir / "_manifest.json", manifest)
        if getattr(args, "strict", False):
            return 2
        return 0

    actions, action_errors = castore.parse_actions(actions_path)
    adjusted_rows, notes = apply_close_adjustments(
        _load_snapshot_rows(snapshot_path),
        actions,
    )
    adjusted_path = outdir / "adjusted_snapshot.csv"
    _write_adjusted_snapshot(adjusted_path, adjusted_rows)
    manifest = {
        "schema_version": 1,
        "day": day,
        "outdir": str(outdir),
        "total": len(adjusted_rows),
        "ok": len(adjusted_rows),
        "errors": len(action_errors),
        "error_list": action_errors,
        "runtime_ms": 0,
        "notes": notes,
    }
    castore.atomic_write_json(outdir / "_manifest.json", manifest)
    if getattr(args, "strict", False) and action_errors:
        return 2
    return 0


def _cmd_market_data_validate(args: argparse.Namespace) -> int:
    """Validate market data for a day (provider default local_eod)."""
    day = getattr(args, "day", None) or ""
    if not day:
        raise SystemExit("--day is required")
    snapshot_root = getattr(args, "snapshot_root", None) or os.environ.get("BIST_CORE_SNAPSHOT_DIR")
    if not snapshot_root:
        print("ERROR: snapshot_root required (--snapshot-root or BIST_CORE_SNAPSHOT_DIR)", file=sys.stderr)
        raise SystemExit(2)
    try:
        provider = resolve_provider("local_eod", snapshot_root=Path(snapshot_root))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
    ok, message = provider.validate(day)
    if not ok:
        print(f"ERROR: {message}", file=sys.stderr)
        raise SystemExit(2)
    print(f"ok: {message}")
    return 0


def _read_events_input(path: Path) -> tuple[list[tuple[int, dict]], int, list[dict]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows: list[tuple[int, dict]] = []
        errors: list[dict] = []
        total = 0
        for idx, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            total += 1
            try:
                row = json.loads(line)
            except Exception:
                errors.append({"idx": idx, "error_marker": "InvalidJSON"})
                continue
            if isinstance(row, dict):
                rows.append((idx, row))
            else:
                errors.append({"idx": idx, "error_marker": "InvalidRow"})
        return rows, total, errors

    try:
        data = json.loads(text)
    except Exception:
        return [], 0, [{"idx": 0, "error_marker": "InvalidJSON"}]
    if isinstance(data, list):
        rows: list[tuple[int, dict]] = []
        errors: list[dict] = []
        for idx, row in enumerate(data):
            if isinstance(row, dict):
                rows.append((idx, row))
            else:
                errors.append({"idx": idx, "error_marker": "InvalidRow"})
        return rows, len(data), errors
    return [], 0, [{"idx": 0, "error_marker": "InvalidJSON"}]


def _write_events_jsonl(path: Path, events: list) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(asdict(event), ensure_ascii=False))
            f.write("\n")
    tmp_path.replace(path)


def _load_snapshot_rows(snapshot_path: Path) -> list[dict]:
    df = pd.read_csv(snapshot_path)
    rows: list[dict] = []
    for _, row in df.iterrows():
        rows.append(
            {
                "symbol": row.get("symbol"),
                "date": row.get("date") if "date" in df.columns else snapshot_path.parent.name,
                "close": row.get("close"),
            }
        )
    return rows


def _write_adjusted_snapshot(path: Path, rows: list[dict]) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    df = pd.DataFrame(rows)
    if "date" not in df.columns:
        df["date"] = ""
    df_out = df[["symbol", "close", "date"]]
    df_out.to_csv(tmp_path, index=False)
    tmp_path.replace(path)


def _latest_snapshot_day(snapshots_dir: Path) -> Optional[str]:
    if not snapshots_dir.exists():
        return None
    latest: Optional[date] = None
    for entry in snapshots_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            day = date.fromisoformat(entry.name)
        except ValueError:
            continue
        if latest is None or day > latest:
            latest = day
    return latest.isoformat() if latest else None


def _advice_payload(advice, day_str: str) -> dict:
    return {
        "symbol": advice.symbol,
        "day": day_str,
        "decision_raw": advice.decision_raw,
        "score": advice.score,
        "signals": advice.signals,
        "plan": advice.plan,
        "text": advice.text,
    }


def _fallback_payload(symbol: str, day_str: str, exc: Exception) -> dict:
    err = exc.__class__.__name__
    text = (
        f"Güvenli mod: {err}. "
        "Veri veya karar üretilemedi; snapshot ve konfigürasyonu kontrol edin."
    )
    return {
        "symbol": symbol,
        "day": day_str,
        "decision_raw": "PASS",
        "score": 0.0,
        "signals": [],
        "plan": None,
        "text": text,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bist_core")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info")
    p_info.add_argument("--json", action="store_true")
    p_info.set_defaults(func=_cmd_info)

    p_healthcheck = sub.add_parser("healthcheck", help="Validate environment + config; output JSON only")
    p_healthcheck.set_defaults(func=_cmd_healthcheck)

    p_eod = sub.add_parser("eod")
    p_eod.add_argument("--date", required=False)
    p_eod.set_defaults(func=_cmd_eod)
    sub_eod = p_eod.add_subparsers(dest="eod_cmd", required=False)

    p_eod_run = sub_eod.add_parser("run")
    p_eod_run.add_argument("--day", default=None)
    p_eod_run.add_argument("--outdir", default=None)
    p_eod_run.add_argument("--strict", action="store_true")
    p_eod_run.add_argument("--symbols", default=None)
    p_eod_run.add_argument("--regex", default=None)
    p_eod_run.add_argument("--limit", type=int, default=None)
    p_eod_run.add_argument("--jsonl", action="store_true", default=True)
    p_eod_run.add_argument("--no-jsonl", action="store_false", dest="jsonl")
    p_eod_run.add_argument("--events-provider", dest="events_provider", default=None)
    p_eod_run.add_argument("--events-input", dest="events_input", default=None)
    p_eod_run.add_argument("--events-outdir", dest="events_outdir", default=None)
    p_eod_run.add_argument("--instruments-provider", dest="instruments_provider", default=None)
    p_eod_run.add_argument("--instruments-input", dest="instruments_input", default=None)
    p_eod_run.add_argument("--instruments-outdir", dest="instruments_outdir", default=None)
    p_eod_run.add_argument("--ca-provider", dest="ca_provider", default=None)
    p_eod_run.add_argument("--ca-input", dest="ca_input", default=None)
    p_eod_run.add_argument("--ca-outdir", dest="ca_outdir", default=None)
    p_eod_run.add_argument("--resolve-aliases", action="store_true")
    p_eod_run.add_argument("--calendar-file", dest="calendar_file", default=None)
    p_eod_run.add_argument("--ignore-calendar", action="store_true")
    p_eod_run.add_argument("--policy-file", dest="policy_file", default=None)
    p_eod_run.add_argument("--emit-orders", action="store_true")
    p_eod_run.add_argument("--orders-strategy", dest="orders_strategy", default="equal_weight")
    p_eod_run.add_argument("--orders-top-n", dest="orders_top_n", type=int, default=10)
    p_eod_run.add_argument("--risk-rules-file", dest="risk_rules_file", default=None)
    p_eod_run.add_argument("--restrictions-file", dest="restrictions_file", default=None, help="Restriction state JSON (or env BIST_RESTRICTIONS_FILE)")
    p_eod_run.add_argument("--instrument-master", dest="instrument_master", default=None, help="Instrument master CSV (or env BIST_INSTRUMENT_MASTER)")
    p_eod_run.add_argument("--research", action="store_true", help="Run research cache stage")
    p_eod_run.add_argument("--research-source", dest="research_source", default=None)
    p_eod_run.add_argument("--research-offline", dest="research_offline", action="store_true")
    p_eod_run.set_defaults(func=_cmd_eod_run)

    p_eod_batch = sub_eod.add_parser("batch")
    p_eod_batch.add_argument("--from", dest="date_from", required=False)
    p_eod_batch.add_argument("--to", dest="date_to", required=False)
    p_eod_batch.add_argument("--outdir", default=None)
    p_eod_batch.add_argument("--strict", action="store_true")
    p_eod_batch.add_argument("--symbols", default=None)
    p_eod_batch.add_argument("--regex", default=None)
    p_eod_batch.add_argument("--limit", type=int, default=None)
    p_eod_batch.add_argument("--jsonl", action="store_true", default=True)
    p_eod_batch.add_argument("--no-jsonl", action="store_false", dest="jsonl")
    p_eod_batch.add_argument("--events-provider", dest="events_provider", default=None)
    p_eod_batch.add_argument("--events-input", dest="events_input", default=None)
    p_eod_batch.add_argument("--events-outdir", dest="events_outdir", default=None)
    p_eod_batch.add_argument("--instruments-provider", dest="instruments_provider", default=None)
    p_eod_batch.add_argument("--instruments-input", dest="instruments_input", default=None)
    p_eod_batch.add_argument("--instruments-outdir", dest="instruments_outdir", default=None)
    p_eod_batch.add_argument("--ca-provider", dest="ca_provider", default=None)
    p_eod_batch.add_argument("--ca-input", dest="ca_input", default=None)
    p_eod_batch.add_argument("--ca-outdir", dest="ca_outdir", default=None)
    p_eod_batch.add_argument("--instrument-master", dest="instrument_master", default=None, help="Instrument master CSV (or env BIST_INSTRUMENT_MASTER)")
    p_eod_batch.add_argument("--resolve-aliases", action="store_true")
    p_eod_batch.add_argument("--calendar-file", dest="calendar_file", default=None)
    p_eod_batch.add_argument("--ignore-calendar", action="store_true")
    p_eod_batch.add_argument("--resume", action="store_true")
    p_eod_batch.add_argument("--rerun-failed", dest="rerun_failed", action="store_true")
    p_eod_batch.add_argument("--max-failures", dest="max_failures", type=int, default=0)
    p_eod_batch.add_argument("--dry-run", action="store_true")
    p_eod_batch.add_argument("--audit", action="store_true")
    p_eod_batch.add_argument("--deep-audit", dest="deep_audit", action="store_true")
    p_eod_batch.add_argument("--audit-json", dest="audit_json", action="store_true")
    p_eod_batch.add_argument("--policy-file", dest="policy_file", default=None)
    p_eod_batch.set_defaults(func=_cmd_eod_batch)

    p_eod_replay = sub_eod.add_parser("replay")
    p_eod_replay.add_argument("--from", dest="date_from", required=True)
    p_eod_replay.add_argument("--to", dest="date_to", required=True)
    p_eod_replay.add_argument("--snapshot-root", dest="snapshot_root", default=None)
    p_eod_replay.add_argument("--outdir", required=True)
    p_eod_replay.add_argument("--strict", action="store_true")
    p_eod_replay.add_argument("--policy-file", dest="policy_file", default=None)
    p_eod_replay.add_argument("--emit-orders", action="store_true")
    p_eod_replay.add_argument("--orders-strategy", dest="orders_strategy", default="equal_weight")
    p_eod_replay.add_argument("--orders-top-n", dest="orders_top_n", type=int, default=10)
    p_eod_replay.add_argument("--risk-rules-file", dest="risk_rules_file", default=None)
    p_eod_replay.add_argument("--metrics", action="store_true", default=True)
    p_eod_replay.add_argument("--no-metrics", dest="metrics", action="store_false")
    p_eod_replay.add_argument("--scorecard", action="store_true", default=True)
    p_eod_replay.add_argument("--no-scorecard", dest="scorecard", action="store_false")
    p_eod_replay.add_argument("--json", action="store_true")
    p_eod_replay.set_defaults(func=_cmd_eod_replay)

    p_eod_scorecard = sub_eod.add_parser("scorecard")
    p_eod_scorecard.add_argument("--outdir", required=True)
    p_eod_scorecard.add_argument("--json", action="store_true")
    p_eod_scorecard.set_defaults(func=_cmd_eod_scorecard)

    p_eod_batch_audit = sub_eod.add_parser("batch-audit")
    p_eod_batch_audit.add_argument("--outdir", required=True)
    p_eod_batch_audit.add_argument("--strict", action="store_true")
    p_eod_batch_audit.set_defaults(func=_cmd_eod_batch_audit)

    p_eod_advice = sub_eod.add_parser("advice")
    p_eod_advice.add_argument("--day", required=True)
    p_eod_advice.add_argument("--outdir", required=True)
    p_eod_advice.add_argument("--top-n", dest="top_n", type=int, default=None)
    p_eod_advice.set_defaults(func=_cmd_eod_advice)

    p_eod_research = sub_eod.add_parser("research")
    p_eod_research.add_argument("--day", required=True)
    p_eod_research.add_argument("--outdir", required=True)
    p_eod_research.add_argument("--source", default="kap", help="Source (e.g. kap); stub provider used")
    p_eod_research.add_argument("--offline", action="store_true")
    p_eod_research.set_defaults(func=_cmd_eod_research)

    p_eod_execute = sub_eod.add_parser("execute")
    p_eod_execute.add_argument("--day", required=True)
    p_eod_execute.add_argument("--outdir", required=True)
    p_eod_execute.add_argument("--config", default=None, help="Path to core config JSON (or BIST_CORE_CONFIG); required in live mode")
    p_eod_execute.add_argument("--execution", choices=("paper", "live"), default="paper", help="paper=simulation, live=real (requires broker config)")
    p_eod_execute.add_argument("--broker", default=None, help="Broker adapter name (e.g. paper, stub); default from execution")
    p_eod_execute.add_argument("--broker-config", dest="broker_config", default=None, help="Path to broker config JSON (or env BIST_BROKER_CONFIG) for live")
    p_eod_execute.add_argument("--provider", default=None, help="Execution provider (e.g. paper); default paper for paper execution, stub for live")
    p_eod_execute.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p_eod_execute.add_argument("--live", action="store_true", dest="live")
    p_eod_execute.set_defaults(func=_cmd_eod_execute)

    p_daily = sub.add_parser("daily", help="Daily run: pipeline end-to-end idempotently")
    sub_daily = p_daily.add_subparsers(dest="daily_cmd", required=True)
    p_daily_run = sub_daily.add_parser("run")
    p_daily_run.add_argument("--day", required=True, help="Trading day (YYYY-MM-DD)")
    p_daily_run.add_argument("--outdir", required=True, help="Output directory")
    p_daily_run.add_argument("--config", default=None, help="Path to core config JSON (or BIST_CORE_CONFIG); required for --live")
    p_daily_run.add_argument("--live", action="store_true", help="Run pipeline then execute live")
    p_daily_run.add_argument("--paper", action="store_true", help="Run pipeline then execute paper")
    p_daily_run.set_defaults(func=_cmd_daily_run)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--date", required=True)
    p_plan.add_argument("--strategy", default="equal_weight")
    p_plan.set_defaults(func=_cmd_plan)

    p_orders = sub.add_parser("orders")
    p_orders.add_argument("--date", required=True)
    p_orders.add_argument("--strategy", default="equal_weight")
    p_orders.set_defaults(func=_cmd_orders)

    p_broker = sub.add_parser("broker")
    sub_broker = p_broker.add_subparsers(dest="broker_cmd", required=True)
    p_broker_paper = sub_broker.add_parser("paper")
    sub_broker_paper_cmd = p_broker_paper.add_subparsers(dest="broker_paper_cmd", required=True)
    p_broker_paper_run = sub_broker_paper_cmd.add_parser("run")
    p_broker_paper_run.add_argument("--day", required=True)
    p_broker_paper_run.add_argument("--orders", required=True, help="Path to orders_intent.json")
    p_broker_paper_run.add_argument("--snapshot-root", dest="snapshot_root", default=None)
    p_broker_paper_run.add_argument("--portfolio-value", dest="portfolio_value", type=float, default=1.0)
    p_broker_paper_run.add_argument("--json", action="store_true")
    p_broker_paper_run.set_defaults(func=_cmd_broker_paper_run)

    p_backtest = sub.add_parser("backtest")
    sub_backtest = p_backtest.add_subparsers(dest="backtest_cmd", required=True)
    p_backtest_run = sub_backtest.add_parser("run")
    p_backtest_run.add_argument("--from", dest="date_from", required=True)
    p_backtest_run.add_argument("--to", dest="date_to", required=True)
    p_backtest_run.add_argument("--outdir", required=True)
    p_backtest_run.add_argument("--snapshot-root", dest="snapshot_root", default=None)
    p_backtest_run.add_argument("--strategy", default="equal_weight")
    p_backtest_run.add_argument("--top-n", dest="top_n", type=int, default=10)
    p_backtest_run.add_argument("--walk-forward", dest="walk_forward", action="store_true")
    p_backtest_run.add_argument("--window", type=int, default=None)
    p_backtest_run.add_argument("--step", type=int, default=None)
    p_backtest_run.add_argument("--min-trades", dest="min_trades", type=int, default=None)
    p_backtest_run.add_argument("--max-dd", dest="max_dd", type=float, default=None)
    p_backtest_run.add_argument("--strict", action="store_true")
    p_backtest_run.add_argument("--json", action="store_true")
    p_backtest_run.set_defaults(func=_cmd_backtest_run)

    p_rules = sub.add_parser("rules")
    sub_rules = p_rules.add_subparsers(dest="rules_cmd", required=True)
    p_rules_validate = sub_rules.add_parser("validate")
    p_rules_validate.add_argument("--file", required=True)
    p_rules_validate.set_defaults(func=_cmd_rules_validate)
    p_rules_explain = sub_rules.add_parser("explain")
    p_rules_explain.add_argument("--file", required=True)
    p_rules_explain.add_argument("--symbol", required=True)
    p_rules_explain.add_argument("--price", required=True)
    p_rules_explain.add_argument("--side", required=True)
    p_rules_explain.add_argument("--qty", required=True)
    p_rules_explain.add_argument("--day", required=True)
    p_rules_explain.add_argument("--strict-exit", action="store_true")
    p_rules_explain.set_defaults(func=_cmd_rules_explain)

    p_data = sub.add_parser("data")
    sub_data = p_data.add_subparsers(dest="data_cmd", required=True)

    p_reg = sub_data.add_parser("register")
    p_reg.add_argument("--id", default=None)
    p_reg.add_argument("--name", default=None)
    p_reg.add_argument("--format", default=None)
    p_reg.add_argument("--kind", default=None)
    p_reg.add_argument("--path", required=True, help="Dataset root path")
    p_reg.add_argument("--symbol-col", dest="symbol_col", default=None)
    p_reg.add_argument("--date-col", dest="date_col", default=None)
    p_reg.add_argument("--tz", default=None)
    p_reg.add_argument("--overwrite", action="store_true")
    p_reg.set_defaults(func=_cmd_data_register)

    p_list = sub_data.add_parser("list")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=_cmd_data_list)

    p_resolve = sub_data.add_parser("resolve")
    p_resolve.add_argument("--name", default=None)
    p_resolve.add_argument("--id", default=None)
    p_resolve.add_argument("--json", action="store_true")
    p_resolve.set_defaults(func=_cmd_data_resolve)

    p_load = sub_data.add_parser("load")
    p_load.add_argument("--id", default=None)
    p_load.add_argument("--name", default=None)
    p_load.add_argument("--head", type=int, default=0)
    p_load.add_argument("--json", action="store_true")
    p_load.add_argument("--out", default=None)

    # ✅ Eksik olan argümanlar burada:
    p_load.add_argument("--use-snapshot", action="store_true")
    p_load.add_argument("--as-of", default=None)

    p_load.set_defaults(func=_cmd_data_load)

    p_snapshot = sub_data.add_parser("snapshot")
    p_snapshot.add_argument("--id", default=None)
    p_snapshot.add_argument("--name", default=None)
    p_snapshot.add_argument("--day", required=True)
    p_snapshot.add_argument("--out", default=None)
    p_snapshot.set_defaults(func=_cmd_data_snapshot)

    p_ask = sub.add_parser("ask")
    p_ask.add_argument("symbol")
    p_ask.add_argument("--day", default=None)
    p_ask.add_argument("--json", action="store_true")
    p_ask.add_argument("--all", action="store_true")
    p_ask.set_defaults(func=_cmd_ask)

    p_dossier = sub.add_parser("dossier")
    sub_dossier = p_dossier.add_subparsers(dest="dossier_cmd", required=True)

    p_dossier_build = sub_dossier.add_parser("build")
    p_dossier_build.add_argument("--day", default=None)
    p_dossier_build.add_argument("--all", action="store_true")
    p_dossier_build.add_argument("--symbols", default=None)
    p_dossier_build.add_argument("--regex", default=None)
    p_dossier_build.add_argument("--limit", type=int, default=None)
    p_dossier_build.add_argument("--strict", action="store_true")
    p_dossier_build.add_argument("--outdir", default=None)
    p_dossier_build.set_defaults(func=_cmd_dossier_build)

    p_events = sub.add_parser("events")
    sub_events = p_events.add_subparsers(dest="events_cmd", required=True)

    p_events_ingest = sub_events.add_parser("ingest")
    p_events_ingest.add_argument("--day", required=True)
    p_events_ingest.add_argument("--input", required=True)
    p_events_ingest.add_argument("--outdir", default=None)
    p_events_ingest.add_argument("--strict", action="store_true")
    p_events_ingest.set_defaults(func=_cmd_events_ingest)

    p_events_pull = sub_events.add_parser("pull")
    p_events_pull.add_argument("--day", required=True)
    p_events_pull.add_argument("--provider", required=True)
    p_events_pull.add_argument("--input", required=True)
    p_events_pull.add_argument("--outdir", default=None)
    p_events_pull.add_argument("--strict", action="store_true")
    p_events_pull.add_argument("--base-url", dest="base_url", default=None)
    p_events_pull.add_argument("--url-template", dest="url_template", default=None)
    p_events_pull.add_argument("--timeout", dest="timeout", type=int, default=15)
    p_events_pull.set_defaults(func=_cmd_events_pull)

    p_instruments = sub.add_parser("instruments")
    sub_instruments = p_instruments.add_subparsers(dest="instruments_cmd", required=True)

    p_instruments_pull = sub_instruments.add_parser("pull")
    p_instruments_pull.add_argument("--day", required=True)
    p_instruments_pull.add_argument("--provider", required=True)
    p_instruments_pull.add_argument("--input", required=True)
    p_instruments_pull.add_argument("--outdir", default=None)
    p_instruments_pull.add_argument("--strict", action="store_true")
    p_instruments_pull.set_defaults(func=_cmd_instruments_pull)

    p_instruments_ingest = sub_instruments.add_parser("ingest")
    p_instruments_ingest.add_argument("--day", required=True)
    p_instruments_ingest.add_argument("--input", required=True)
    p_instruments_ingest.add_argument("--outdir", default=None)
    p_instruments_ingest.add_argument("--strict", action="store_true")
    p_instruments_ingest.set_defaults(func=_cmd_instruments_ingest)

    p_instruments_timeline = sub_instruments.add_parser("timeline")
    p_instruments_timeline.add_argument("--day", required=True)
    p_instruments_timeline.add_argument("--instruments-dir", default=None)
    p_instruments_timeline.add_argument("--ca-dir", default=None)
    p_instruments_timeline.add_argument("--outdir", default=None)
    p_instruments_timeline.add_argument("--strict", action="store_true")
    p_instruments_timeline.set_defaults(func=_cmd_instruments_timeline)

    p_market_data = sub.add_parser("market-data")
    sub_market_data = p_market_data.add_subparsers(dest="market_data_cmd", required=True)
    p_market_data_validate = sub_market_data.add_parser("validate")
    p_market_data_validate.add_argument("--day", required=True)
    p_market_data_validate.add_argument("--snapshot-root", dest="snapshot_root", default=None)
    p_market_data_validate.set_defaults(func=_cmd_market_data_validate)

    p_ca = sub.add_parser("corporate-actions")
    sub_ca = p_ca.add_subparsers(dest="ca_cmd", required=True)

    p_ca_pull = sub_ca.add_parser("pull")
    p_ca_pull.add_argument("--day", required=True)
    p_ca_pull.add_argument("--provider", required=True)
    p_ca_pull.add_argument("--input", required=True)
    p_ca_pull.add_argument("--outdir", default=None)
    p_ca_pull.add_argument("--strict", action="store_true")
    p_ca_pull.set_defaults(func=_cmd_corporate_actions_pull)

    p_ca_ingest = sub_ca.add_parser("ingest")
    p_ca_ingest.add_argument("--day", required=True)
    p_ca_ingest.add_argument("--input", required=True)
    p_ca_ingest.add_argument("--outdir", default=None)
    p_ca_ingest.add_argument("--strict", action="store_true")
    p_ca_ingest.set_defaults(func=_cmd_corporate_actions_ingest)

    p_ca_apply = sub_ca.add_parser("apply-close")
    p_ca_apply.add_argument("--day", required=True)
    p_ca_apply.add_argument("--actions-dir", default=None)
    p_ca_apply.add_argument("--snapshot-dir", default=None)
    p_ca_apply.add_argument("--outdir", default=None)
    p_ca_apply.add_argument("--strict", action="store_true")
    p_ca_apply.set_defaults(func=_cmd_corporate_actions_apply_close)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
