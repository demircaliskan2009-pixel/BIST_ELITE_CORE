from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date, timedelta
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.services.eod_pipeline import run_eod_pipeline
from bist_core.services import trading_calendar


@dataclass
class DayResult:
    day: str
    status: str
    returncode: int
    manifest_path: str
    calendar_reason: str
    calendar_errors: List[str]


def run_eod_batch(
    start_day: str,
    end_day: str,
    outdir: Path,
    *,
    snapshot_root: Path,
    strict: bool = False,
    calendar_file: Optional[Path] = None,
    ignore_calendar: bool = False,
    run_kwargs: Optional[dict] = None,
) -> tuple[dict, int]:
    start = time.perf_counter()
    run_kwargs = dict(run_kwargs or {})
    outdir.mkdir(parents=True, exist_ok=True)

    errors: List[str] = []
    days: List[DayResult] = []

    try:
        start_date = Date.fromisoformat(start_day)
        end_date = Date.fromisoformat(end_day)
    except Exception:
        errors.append("InvalidDateRange")
        manifest = _index_manifest(
            start_day,
            end_day,
            outdir,
            days,
            errors,
            int((time.perf_counter() - start) * 1000),
            run_kwargs,
        )
        _atomic_write_json(outdir / "_index_manifest.json", manifest)
        return manifest, 2 if strict else 0

    if start_date > end_date:
        errors.append("InvalidDateRange")

    current = start_date
    while current <= end_date:
        day_str = current.isoformat()
        if ignore_calendar:
            ok = True
            reason = "ignored"
            cal_errors: List[str] = []
        else:
            ok, reason, cal_errors, _ = trading_calendar.is_trading_day(
                day_str, calendar_file
            )

        if cal_errors:
            days.append(
                DayResult(
                    day=day_str,
                    status="error",
                    returncode=2,
                    manifest_path="",
                    calendar_reason=reason,
                    calendar_errors=cal_errors,
                )
            )
        elif not ok:
            days.append(
                DayResult(
                    day=day_str,
                    status="skipped",
                    returncode=0,
                    manifest_path="",
                    calendar_reason=reason,
                    calendar_errors=[],
                )
            )
        else:
            day_outdir = outdir / day_str
            manifest, code = run_eod_pipeline(
                day_str,
                snapshot_root=snapshot_root,
                outdir=day_outdir,
                strict=strict,
                calendar_file=calendar_file,
                ignore_calendar=ignore_calendar,
                **run_kwargs,
            )
            days.append(
                DayResult(
                    day=day_str,
                    status="ok" if code == 0 else "error",
                    returncode=int(code),
                    manifest_path=str(day_outdir / "_pipeline_manifest.json"),
                    calendar_reason=reason,
                    calendar_errors=[],
                )
            )
        current = current + timedelta(days=1)

    if errors:
        overall_errors = errors
    else:
        overall_errors = [e for d in days for e in d.calendar_errors]

    manifest = _index_manifest(
        start_day,
        end_day,
        outdir,
        days,
        overall_errors,
        int((time.perf_counter() - start) * 1000),
        run_kwargs,
    )
    _atomic_write_json(outdir / "_index_manifest.json", manifest)

    failed = any(d.returncode != 0 or d.status == "error" for d in days) or bool(errors)
    return manifest, 2 if strict and failed else 0


def _index_manifest(
    start_day: str,
    end_day: str,
    outdir: Path,
    days: List[DayResult],
    errors: List[str],
    runtime_ms: int,
    run_kwargs: dict,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "start_day": start_day,
        "end_day": end_day,
        "outdir": str(outdir),
        "days": [
            {
                "day": d.day,
                "status": d.status,
                "returncode": d.returncode,
                "manifest_path": d.manifest_path,
                "calendar_reason": d.calendar_reason,
                "calendar_errors": d.calendar_errors,
            }
            for d in days
        ],
        "errors": errors,
        "runtime_ms": int(runtime_ms),
        "provenance": {"cli_args": run_kwargs},
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
