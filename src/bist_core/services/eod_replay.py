from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date, timedelta
from pathlib import Path
import os
import time
from typing import Optional

from bist_core.services.dossier import atomic_write_json
from bist_core.services.eod_pipeline import run_eod_pipeline
from bist_core.services.scorecard import build_scorecard
from bist_core.services import snapshot_integrity
from bist_core.services import trading_calendar


@dataclass
class ReplayDay:
    day: str
    status: str
    exit_code: int
    pipeline_manifest_path: str


def run_eod_replay(
    date_from: str,
    date_to: str,
    outdir: Path | str,
    *,
    snapshot_root: Path | str,
    strict: bool = False,
    policy_file: Optional[Path | str] = None,
    emit_orders: bool = False,
    orders_strategy: str = "equal_weight",
    orders_top_n: int = 10,
    metrics: bool = True,
    scorecard: bool = True,
) -> tuple[dict, int]:
    start = time.perf_counter()
    out_path = Path(outdir)
    out_path.mkdir(parents=True, exist_ok=True)
    snapshot_root_path = Path(snapshot_root)

    current = Date.fromisoformat(date_from)
    end_date = Date.fromisoformat(date_to)
    days: list[ReplayDay] = []

    orders_emitted_days = 0
    orders_blocked_days = 0
    orders_no_actions_days = 0
    ok_days = 0
    error_days = 0

    policy_effective = (
        str(policy_file) if policy_file is not None else os.getenv("BIST_CORE_POLICY_FILE")
    )
    policy_prov = None
    if policy_effective:
        policy_path = Path(policy_effective)
        policy_prov = {"file": str(policy_path), "hash": {"algo": "sha256", "value": ""}}
        try:
            policy_prov["hash"]["value"] = snapshot_integrity.compute_sha256(policy_path)
        except Exception:
            policy_prov["hash"]["value"] = ""

    while current <= end_date:
        day_str = current.isoformat()
        ok, reason, cal_errors, _ = trading_calendar.is_trading_day(day_str, None)
        if cal_errors:
            days.append(
                ReplayDay(
                    day=day_str,
                    status="error_calendar",
                    exit_code=2,
                    pipeline_manifest_path="",
                )
            )
            error_days += 1
            current = current + timedelta(days=1)
            continue
        if not ok:
            days.append(
                ReplayDay(
                    day=day_str,
                    status="skipped_calendar",
                    exit_code=0,
                    pipeline_manifest_path="",
                )
            )
            current = current + timedelta(days=1)
            continue

        day_outdir = out_path / day_str
        manifest, code = run_eod_pipeline(
            day_str,
            snapshot_root=snapshot_root_path,
            outdir=day_outdir,
            strict=strict,
            policy_file=policy_file,
            emit_orders=emit_orders,
            orders_strategy=orders_strategy,
            orders_top_n=orders_top_n,
        )
        stage_errors = _pipeline_errors(manifest)
        day_error = code != 0 or stage_errors > 0
        status = "error" if day_error else "ok"
        if day_error:
            error_days += 1
        else:
            ok_days += 1

        orders_stage = manifest.get("stages", {}).get("orders")
        if isinstance(orders_stage, dict):
            orders_emitted_days += 1
            notes = orders_stage.get("notes", [])
            if orders_stage.get("ok") == 0:
                orders_blocked_days += 1
            if "no_actions" in notes:
                orders_no_actions_days += 1

        days.append(
            ReplayDay(
                day=day_str,
                status=status,
                exit_code=int(code),
                pipeline_manifest_path=str(day_outdir / "_pipeline_manifest.json"),
            )
        )
        current = current + timedelta(days=1)

    runtime_ms = int((time.perf_counter() - start) * 1000)
    total_days = len(days)
    summary = {
        "total": total_days,
        "ok": ok_days,
        "error": error_days,
        "orders_emitted_days": orders_emitted_days,
        "orders_no_actions_days": orders_no_actions_days,
        "orders_blocked_days": orders_blocked_days,
        "runtime_ms": runtime_ms,
    }
    replay_manifest = {
        "schema_version": 1,
        "range": {"from": date_from, "to": date_to},
        "outdir": str(out_path),
        "days": [
            {
                "day": entry.day,
                "status": entry.status,
                "exit_code": entry.exit_code,
                "pipeline_manifest_path": entry.pipeline_manifest_path,
            }
            for entry in days
        ],
        "summary": summary,
        "policy": policy_prov,
    }
    atomic_write_json(out_path / "_replay_manifest.json", replay_manifest)

    if metrics:
        metrics_payload = {
            "schema_version": 1,
            "total_days": total_days,
            "ok_days": ok_days,
            "error_days": error_days,
            "orders_emitted_days": orders_emitted_days,
            "orders_blocked_days": orders_blocked_days,
            "no_actions_days": orders_no_actions_days,
        }
        atomic_write_json(out_path / "metrics.json", metrics_payload)

    if scorecard:
        build_scorecard(out_path)

    exit_code = 2 if strict and error_days > 0 else 0
    return replay_manifest, exit_code


def _pipeline_errors(manifest: dict | None) -> int:
    if not isinstance(manifest, dict):
        return 0
    stages = manifest.get("stages", {})
    if not isinstance(stages, dict):
        return 0
    total = 0
    for stage in stages.values():
        if isinstance(stage, dict):
            total += int(stage.get("errors", 0))
    return total
