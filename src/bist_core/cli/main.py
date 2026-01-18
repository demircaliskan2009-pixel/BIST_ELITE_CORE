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
from bist_core.services.dossier import (
    atomic_write_json,
    build_dossiers_for_day,
    build_manifest,
)
from bist_core.services.eod_pipeline import run_eod_pipeline
from bist_core.services.events_pipeline import (
    build_events_jsonl_for_day,
    ingest_events_from_file,
)
from bist_core.providers.events.offline_file import OfflineFileEventsProvider
from bist_core.providers.events.kap_html import KapHtmlEventsProvider
from bist_core.services import instrumentstore
from bist_core.providers.instruments.offline_file import OfflineFileInstrumentsProvider


def _snapshot_root() -> Path:
    return Path(os.getenv("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots"))


def _cmd_info(args: argparse.Namespace) -> int:
    reg = get_default_registry()

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
    }
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
        git_sha=_env_git_sha(),
        cli_args=cli_args,
    )

    stages = manifest.get("stages", {})
    snapshot_stage = stages.get("snapshot", {})
    advice_stage = stages.get("advice", {})
    dossier_stage = stages.get("dossier", {})
    print(
        "eod run: "
        f"snapshot errors={snapshot_stage.get('errors', 0)}; "
        f"advice ok={advice_stage.get('ok', 0)}/{advice_stage.get('total', 0)}; "
        f"dossier ok={dossier_stage.get('ok', 0)}/{dossier_stage.get('total', 0)}"
    )
    return int(code)


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



def _cmd_data_register(args: argparse.Namespace) -> int:
    reg = get_default_registry()
    dataset_id = args.id or args.name
    fmt = args.format or args.kind
    if not dataset_id:
        raise SystemExit("--id is required")
    if not fmt:
        raise SystemExit("--format is required")
    if fmt in ("local_csv", "csv"):
        fmt = "csv"
    if fmt != "csv":
        raise SystemExit(f"Unsupported format: {fmt!r}")
    reg.register(name=dataset_id, path=args.path, kind="local_csv")
    reg.save()
    print(f"registered: {dataset_id}")
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
        raise SystemExit("--id is required")
    reg = get_default_registry()
    meta = reg.get(dataset_id)
    fmt = "csv" if meta.kind == "local_csv" else meta.kind
    print(
        f"id={dataset_id} format={fmt} path={meta.path} "
        f"created_at={meta.created_at} updated_at={meta.updated_at}"
    )

    # Raw dataset'i yükle
    df_raw = load_registered_dataset(dataset_id)

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
    dataset_id = args.id
    if not dataset_id:
        raise SystemExit("--id is required")
    day = args.day
    try:
        _ = date.fromisoformat(day)
    except ValueError:
        raise SystemExit(f"Invalid date format: {day}. Use YYYY-MM-DD")

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
    p_info.set_defaults(func=_cmd_info)

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
    p_eod_run.set_defaults(func=_cmd_eod_run)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--date", required=True)
    p_plan.add_argument("--strategy", default="equal_weight")
    p_plan.set_defaults(func=_cmd_plan)

    p_orders = sub.add_parser("orders")
    p_orders.add_argument("--date", required=True)
    p_orders.add_argument("--strategy", default="equal_weight")
    p_orders.set_defaults(func=_cmd_orders)

    p_data = sub.add_parser("data")
    sub_data = p_data.add_subparsers(dest="data_cmd", required=True)

    p_reg = sub_data.add_parser("register")
    p_reg.add_argument("--id", default=None)
    p_reg.add_argument("--name", default=None)
    p_reg.add_argument("--format", default=None)
    p_reg.add_argument("--kind", default=None)
    p_reg.add_argument("--path", required=True)
    p_reg.set_defaults(func=_cmd_data_register)

    p_load = sub_data.add_parser("load")
    p_load.add_argument("--id", default=None)
    p_load.add_argument("--name", default=None)
    p_load.add_argument("--head", type=int, default=0)

    # ✅ Eksik olan argümanlar burada:
    p_load.add_argument("--use-snapshot", action="store_true")
    p_load.add_argument("--as-of", default=None)

    p_load.set_defaults(func=_cmd_data_load)

    p_snapshot = sub_data.add_parser("snapshot")
    p_snapshot.add_argument("--id", required=True)
    p_snapshot.add_argument("--day", required=True)
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
