from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date, timedelta
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from bist_core.services.eod_pipeline import locate_manifest, run_eod_pipeline
from bist_core.services import trading_calendar
from bist_core.services import snapshot_integrity


@dataclass
class DayResult:
    day: str
    status: str
    exit_code: int
    manifest_path: str
    reason: str
    errors: List[str]


def run_eod_batch(
    start_day: str,
    end_day: str,
    outdir: Path,
    *,
    snapshot_root: Path,
    strict: bool = False,
    calendar_file: Optional[Path] = None,
    ignore_calendar: bool = False,
    resume: bool = False,
    rerun_failed: bool = False,
    max_failures: int = 0,
    dry_run: bool = False,
    run_kwargs: Optional[dict] = None,
) -> tuple[dict, int]:
    start = time.perf_counter()
    run_kwargs = dict(run_kwargs or {})
    outdir.mkdir(parents=True, exist_ok=True)

    errors: List[str] = []
    days: List[DayResult] = []
    stopped_early = False
    stop_reason = ""
    failures = 0

    if max_failures < 0:
        errors.append("InvalidMaxFailures")
        manifest = _index_manifest(
            start_day,
            end_day,
            outdir,
            days,
            errors,
            int((time.perf_counter() - start) * 1000),
            run_kwargs,
            calendar_file=calendar_file,
            ignore_calendar=ignore_calendar,
            resume=resume,
            rerun_failed=rerun_failed,
            max_failures=max_failures,
            stopped_early=True,
            stop_reason="invalid_max_failures",
        )
        _atomic_write_json(outdir / "_index_manifest.json", manifest)
        return manifest, 2

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
            calendar_file=calendar_file,
            ignore_calendar=ignore_calendar,
            resume=resume,
            rerun_failed=rerun_failed,
            max_failures=max_failures,
            stopped_early=True,
            stop_reason="invalid_date_range",
        )
        _atomic_write_json(outdir / "_index_manifest.json", manifest)
        return manifest, 2 if strict else 0

    if start_date > end_date:
        errors.append("InvalidDateRange")

    prior_index = None
    resume_errors: List[str] = []
    if resume:
        prior_index, resume_errors = _load_prior_index(outdir / "_index_manifest.json")
        if resume_errors and not dry_run:
            errors.extend(resume_errors)

    current = start_date
    while current <= end_date:
        day_str = current.isoformat()
        day_outdir = outdir / day_str
        if max_failures > 0 and failures >= max_failures:
            stopped_early = True
            stop_reason = "max_failures_reached"
            break

        if resume:
            manifest_path = locate_manifest(outdir, day_str) or (day_outdir / "_pipeline_manifest.json")
            resume_decision = _decide_resume_day(
                day_str,
                manifest_path,
                prior_index,
                rerun_failed,
            )
            if resume_decision is not None:
                if dry_run:
                    planned = _plan_from_resume(resume_decision)
                    days.append(planned)
                else:
                    days.append(resume_decision)
                    if resume_decision.exit_code != 0:
                        failures += 1
                current = current + timedelta(days=1)
                continue

        if ignore_calendar:
            ok = True
            reason = "ignored"
            cal_errors: List[str] = []
        else:
            ok, reason, cal_errors, _ = trading_calendar.is_trading_day(day_str, calendar_file)

        if cal_errors:
            errors.extend(cal_errors)
            days.append(
                DayResult(
                    day=day_str,
                    status="error_calendar",
                    exit_code=2,
                    manifest_path="",
                    reason=reason,
                    errors=cal_errors,
                )
            )
            failures += 1
        elif not ok:
            days.append(
                DayResult(
                    day=day_str,
                    status="planned_skipped_calendar" if dry_run else "skipped_calendar",
                    exit_code=0,
                    manifest_path="",
                    reason=reason,
                    errors=[],
                )
            )
        else:
            if dry_run:
                days.append(
                    DayResult(
                        day=day_str,
                        status="planned_run",
                        exit_code=0,
                        manifest_path="",
                        reason="planned",
                        errors=[],
                    )
                )
                current = current + timedelta(days=1)
                continue
            manifest, code = run_eod_pipeline(
                day_str,
                snapshot_root=snapshot_root,
                outdir=day_outdir,
                strict=strict,
                calendar_file=calendar_file,
                ignore_calendar=ignore_calendar,
                **run_kwargs,
            )
            stage_errors = _pipeline_errors(manifest)
            day_error = code != 0 or stage_errors > 0
            written_manifest_path = locate_manifest(outdir, day_str) or (day_outdir / "_pipeline_manifest.json")
            days.append(
                DayResult(
                    day=day_str,
                    status="ok" if not day_error else "error",
                    exit_code=2 if day_error else 0,
                    manifest_path=str(written_manifest_path),
                    reason="pipeline",
                    errors=[],
                )
            )
            if day_error:
                failures += 1
        current = current + timedelta(days=1)

    remaining_days = []
    if stopped_early:
        remaining_days = _remaining_days(current, end_date)
        for day_str in remaining_days:
            days.append(
                DayResult(
                    day=day_str,
                    status="not_run",
                    exit_code=0,
                    manifest_path="",
                    reason="max_failures_reached",
                    errors=[],
                )
            )

    overall_errors = list(errors)

    manifest = _index_manifest(
        start_day,
        end_day,
        outdir,
        days,
        overall_errors,
        int((time.perf_counter() - start) * 1000),
        run_kwargs,
        calendar_file=calendar_file,
        ignore_calendar=ignore_calendar,
        resume=resume,
        rerun_failed=rerun_failed,
        max_failures=max_failures,
        stopped_early=stopped_early,
        stop_reason=stop_reason,
        dry_run=dry_run,
    )
    _atomic_write_json(outdir / "_index_manifest.json", manifest)

    failed = any(d.exit_code != 0 or d.status.startswith("error") for d in days) or bool(errors)
    calendar_errors = any(d.status == "error_calendar" for d in days)
    if dry_run and strict:
        return manifest, 2 if calendar_errors else 0
    return manifest, 2 if strict and (failed or stopped_early) else 0


def _index_manifest(
    start_day: str,
    end_day: str,
    outdir: Path,
    days: List[DayResult],
    errors: List[str],
    runtime_ms: int,
    run_kwargs: dict,
    *,
    calendar_file: Optional[Path],
    ignore_calendar: bool,
    resume: bool,
    rerun_failed: bool,
    max_failures: int,
    stopped_early: bool,
    stop_reason: str,
    dry_run: bool,
) -> Dict[str, Any]:
    summary = _build_summary(days)
    return {
        "schema_version": 2,
        "start_day": start_day,
        "end_day": end_day,
        "outdir": str(outdir),
        "calendar": {
            "file": str(calendar_file) if calendar_file else None,
            "ignore": bool(ignore_calendar),
        },
        "resume": {
            "enabled": bool(resume),
            "rerun_failed": bool(rerun_failed),
            "max_failures": int(max_failures),
        },
        "dry_run": bool(dry_run),
        "stopped_early": bool(stopped_early),
        "stop_reason": stop_reason or "",
        "days": [
            {
                "day": d.day,
                "status": d.status,
                "exit_code": d.exit_code,
                "pipeline_manifest_path": d.manifest_path,
                "calendar": {
                    "ok": d.status not in {"error_calendar", "skipped_calendar"},
                    "reason": d.reason,
                    "errors": d.errors,
                },
                "notes": [],
            }
            for d in days
        ],
        "summary": summary,
        "errors": errors,
        "runtime_ms": int(runtime_ms),
        "provenance": {"cli_args": run_kwargs},
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _load_prior_index(path: Path) -> tuple[Optional[dict], List[str]]:
    if not path.exists():
        return None, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, ["ResumeIndexParseError"]
    if not isinstance(payload, dict):
        return None, ["ResumeIndexSchemaError"]
    return payload, []


def _decide_resume_day(
    day_str: str,
    manifest_path: Path,
    prior_index: Optional[dict],
    rerun_failed: bool,
) -> Optional[DayResult]:
    prior_day = _find_prior_day(prior_index, day_str) if prior_index else None
    if prior_day is not None:
        exit_code = int(prior_day.get("exit_code") or prior_day.get("returncode") or 0)
        status = prior_day.get("status", "")
        if exit_code == 0 and status in {"ok", "skipped", "skipped_calendar", "skipped_ok_existing"}:
            return DayResult(
                day=day_str,
                status="skipped_ok_existing",
                exit_code=0,
                manifest_path=str(prior_day.get("pipeline_manifest_path") or prior_day.get("manifest_path") or ""),
                reason="resume_index",
                errors=[],
            )
        if exit_code != 0 and not rerun_failed:
            return DayResult(
                day=day_str,
                status="skipped_failed_existing",
                exit_code=2,
                manifest_path=str(prior_day.get("pipeline_manifest_path") or prior_day.get("manifest_path") or ""),
                reason="resume_index",
                errors=[],
            )
        return None

    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return DayResult(
            day=day_str,
            status="error",
            exit_code=2,
            manifest_path=str(manifest_path),
            reason="manifest_parse_error",
            errors=["ManifestParseError"],
        )
    if not isinstance(payload, dict):
        return DayResult(
            day=day_str,
            status="error",
            exit_code=2,
            manifest_path=str(manifest_path),
            reason="manifest_schema_error",
            errors=["ManifestSchemaError"],
        )
    return DayResult(
        day=day_str,
        status="skipped_ok_existing",
        exit_code=0,
        manifest_path=str(manifest_path),
        reason="manifest_only",
        errors=[],
    )


def _find_prior_day(prior_index: Optional[dict], day_str: str) -> Optional[dict]:
    if not prior_index:
        return None
    days = prior_index.get("days", [])
    for item in days:
        if isinstance(item, dict) and item.get("day") == day_str:
            return item
    return None


def _build_summary(days: List[DayResult]) -> Dict[str, int]:
    total = len(days)
    ran = sum(1 for d in days if d.status in {"ok", "error", "error_calendar"})
    skipped_ok_existing = sum(1 for d in days if d.status == "skipped_ok_existing")
    skipped_calendar = sum(1 for d in days if d.status == "skipped_calendar")
    skipped_failed_existing = sum(1 for d in days if d.status == "skipped_failed_existing")
    not_run = sum(1 for d in days if d.status == "not_run")
    planned_run = sum(1 for d in days if d.status == "planned_run")
    planned_skipped_calendar = sum(1 for d in days if d.status == "planned_skipped_calendar")
    planned_skipped_ok = sum(1 for d in days if d.status == "planned_skipped_ok_existing")
    planned_skipped_failed = sum(1 for d in days if d.status == "planned_skipped_failed_existing")
    errors = sum(1 for d in days if d.exit_code != 0)
    return {
        "total": total,
        "ran": ran,
        "skipped_ok_existing": skipped_ok_existing,
        "skipped_calendar": skipped_calendar,
        "skipped_failed_existing": skipped_failed_existing,
        "not_run": not_run,
        "planned_run": planned_run,
        "planned_skipped_calendar": planned_skipped_calendar,
        "planned_skipped_ok_existing": planned_skipped_ok,
        "planned_skipped_failed_existing": planned_skipped_failed,
        "errors": errors,
    }


def _remaining_days(current: Date, end_date: Date) -> List[str]:
    days: List[str] = []
    day = current
    while day <= end_date:
        days.append(day.isoformat())
        day = day + timedelta(days=1)
    return days


def _pipeline_errors(manifest: dict | None) -> int:
    if not isinstance(manifest, dict):
        return 0
    stages = manifest.get("stages", {})
    if not isinstance(stages, dict):
        return 0
    total = 0
    for name, stage in stages.items():
        if name == "features":
            continue
        if isinstance(stage, dict):
            total += int(stage.get("errors", 0))
    return total


def _plan_from_resume(decision: DayResult) -> DayResult:
    if decision.status == "skipped_ok_existing":
        return DayResult(
            day=decision.day,
            status="planned_skipped_ok_existing",
            exit_code=0,
            manifest_path=decision.manifest_path,
            reason=decision.reason,
            errors=[],
        )
    if decision.status == "skipped_failed_existing":
        return DayResult(
            day=decision.day,
            status="planned_skipped_failed_existing",
            exit_code=0,
            manifest_path=decision.manifest_path,
            reason=decision.reason,
            errors=[],
        )
    return DayResult(
        day=decision.day,
        status="planned_run",
        exit_code=0,
        manifest_path=decision.manifest_path,
        reason=decision.reason,
        errors=[],
    )


def audit_eod_batch(outdir: Path, deep: bool = False, strict: bool = False) -> tuple[dict, int]:
    start = time.perf_counter()
    errors: List[str] = []
    index_path = outdir / "_index_manifest.json"
    if not index_path.exists():
        errors.append("MissingIndexManifest")
        errors_sorted = sorted(errors)
        manifest = _audit_manifest(
            outdir,
            [],
            errors_sorted,
            int((time.perf_counter() - start) * 1000),
            deep=deep,
        )
        _atomic_write_json(outdir / "_audit_manifest.json", manifest)
        return manifest, 2 if strict and errors_sorted else 0
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        errors.append("IndexParseError")
        errors_sorted = sorted(errors)
        manifest = _audit_manifest(
            outdir,
            [],
            errors_sorted,
            int((time.perf_counter() - start) * 1000),
            deep=deep,
        )
        _atomic_write_json(outdir / "_audit_manifest.json", manifest)
        return manifest, 2 if strict and errors_sorted else 0
    if not isinstance(index, dict) or index.get("schema_version") != 2:
        errors.append("IndexSchemaVersion")
    days = index.get("days", [])
    if not isinstance(days, list):
        errors.append("IndexDaysSchemaError")
        days = []
    day_entries = [d for d in days if isinstance(d, dict) and d.get("day")]
    day_entries.sort(key=lambda d: d.get("day", ""))
    listed_days = {d.get("day") for d in day_entries}

    for entry in day_entries:
        status = entry.get("status", "")
        day = entry.get("day", "")
        if status in {"skipped_calendar", "planned_skipped_calendar"}:
            continue
        manifest_path = entry.get("pipeline_manifest_path") or ""
        if status in {"ok", "error"}:
            if not manifest_path:
                errors.append(f"MissingPipelineManifest:{day}")
                continue
            path = Path(manifest_path)
            if not path.exists():
                path = locate_manifest(outdir, day) or path
            if not path.exists():
                errors.append(f"MissingPipelineManifest:{day}")
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                errors.append(f"PipelineManifestUnreadable:{day}")
                continue
            if not isinstance(payload, dict):
                errors.append(f"PipelineManifestSchemaError:{day}")
                continue
            if "schema_version" not in payload:
                errors.append(f"PipelineManifestSchemaVersionMissing:{day}")
            snapshot_root = payload.get("snapshot_root")
            prov = payload.get("provenance", {}) if isinstance(payload.get("provenance", {}), dict) else {}
            snap = prov.get("snapshot_hash")
            if not isinstance(snapshot_root, str):
                errors.append(f"SnapshotRootMissing:{day}")
            else:
                errors.extend(_audit_snapshot_hash(snapshot_root, day, snap))
            if deep:
                errors.extend(_audit_pipeline_artifacts(payload, day))

    for item in sorted(outdir.iterdir(), key=lambda p: p.name):
        if not item.is_dir():
            continue
        manifest_file = item / "_pipeline_manifest.json"
        if manifest_file.exists() and item.name not in listed_days:
            errors.append(f"UnlistedDayManifest:{item.name}")

    errors_sorted = sorted(errors)
    manifest = _audit_manifest(
        outdir,
        day_entries,
        errors_sorted,
        int((time.perf_counter() - start) * 1000),
        deep=deep,
    )
    _atomic_write_json(outdir / "_audit_manifest.json", manifest)
    if errors_sorted and strict:
        return manifest, 2
    return manifest, 0


def _audit_manifest(
    outdir: Path,
    days: List[dict],
    errors: List[str],
    runtime_ms: int,
    *,
    deep: bool,
) -> dict:
    summary = _audit_summary(days, errors)
    return {
        "schema_version": 1,
        "outdir": str(outdir),
        "days": days,
        "errors": errors,
        "summary": summary,
        "runtime_ms": int(runtime_ms),
        "deep": bool(deep),
    }


def _audit_snapshot_hash(snapshot_root: str, day: str, snapshot_hash: object) -> list[str]:
    errors: list[str] = []
    snapshot_path = Path(snapshot_root) / day / "snapshot.csv"
    if not snapshot_path.exists():
        errors.append(f"SnapshotMissing:{day}")
        return errors
    if not isinstance(snapshot_hash, dict):
        errors.append(f"MissingSnapshotHash:{day}")
        return errors
    algo = snapshot_hash.get("algo")
    value = snapshot_hash.get("value")
    if algo != "sha256" or not isinstance(value, str) or not value:
        errors.append(f"MissingSnapshotHash:{day}")
        return errors
    actual = snapshot_integrity.compute_sha256(snapshot_path)
    if actual != value:
        errors.append(f"SnapshotHashMismatch:{day}")
    return errors


def _audit_summary(days: List[dict], errors: List[str]) -> dict:
    summary = {
        "total": 0,
        "ok": 0,
        "error": 0,
        "skipped_calendar": 0,
        "skipped_ok_existing": 0,
        "not_run": 0,
        "planned": 0,
        "errors": len(errors),
    }
    for day in days:
        if not isinstance(day, dict):
            continue
        status = str(day.get("status", ""))
        summary["total"] += 1
        if status == "ok":
            summary["ok"] += 1
        if status.startswith("error"):
            summary["error"] += 1
        if status == "skipped_calendar":
            summary["skipped_calendar"] += 1
        if status == "skipped_ok_existing":
            summary["skipped_ok_existing"] += 1
        if status == "not_run":
            summary["not_run"] += 1
        if status.startswith("planned_"):
            summary["planned"] += 1
    return summary


def _audit_pipeline_artifacts(manifest: dict, day: str) -> list[str]:
    errors: list[str] = []
    stages = manifest.get("stages", {})
    if not isinstance(stages, dict):
        return errors

    def stage_ok_count(stage_name: str) -> int:
        stage = stages.get(stage_name, {})
        if isinstance(stage, dict):
            return int(stage.get("ok", 0) or 0)
        return 0

    def stage_total(stage_name: str) -> int:
        stage = stages.get(stage_name, {})
        if isinstance(stage, dict):
            return int(stage.get("total", 0) or 0)
        return 0

    def stage_path(stage_name: str) -> Optional[str]:
        stage = stages.get(stage_name, {})
        if isinstance(stage, dict):
            path = stage.get("path")
            if isinstance(path, str) and path:
                return path
        return None

    def stage_notes(stage_name: str) -> list[str]:
        stage = stages.get(stage_name, {})
        if isinstance(stage, dict):
            notes = stage.get("notes", [])
            if isinstance(notes, list):
                return [str(n) for n in notes]
        return []

    def require_file(stage_name: str) -> None:
        path = stage_path(stage_name)
        if not path or not Path(path).is_file():
            errors.append(f"MissingArtifact:{day}:{stage_name}")

    def require_dir(stage_name: str) -> None:
        path = stage_path(stage_name)
        if not path or not Path(path).is_dir():
            errors.append(f"MissingArtifact:{day}:{stage_name}")

    if stage_ok_count("advice") > 0:
        require_file("advice")
    if stage_ok_count("dossier") > 0:
        require_dir("dossier")
    if stage_total("events") > 0:
        require_dir("events")
    if stage_total("instruments") > 0:
        require_dir("instruments")
    if stage_total("corporate_actions") > 0:
        require_dir("corporate_actions")

    universe_stage = stages.get("universe", {})
    universe_notes = stage_notes("universe")
    if isinstance(universe_stage, dict) and "universe_skipped" not in universe_notes:
        require_dir("universe")

    return errors
