from __future__ import annotations

from pathlib import Path

from bist_core.services.dossier import atomic_write_json


def build_scorecard(replay_outdir: Path) -> dict:
    outdir = Path(replay_outdir)
    manifest_path = outdir / "_replay_manifest.json"
    payload = {}
    if manifest_path.exists():
        payload = _load_json(manifest_path)

    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    total_days = int(summary.get("total", 0))
    ok_days = int(summary.get("ok", 0))
    error_days = int(summary.get("error", 0))
    orders_emitted_days = int(summary.get("orders_emitted_days", 0))
    orders_no_actions_days = int(summary.get("orders_no_actions_days", 0))
    orders_blocked_days = int(summary.get("orders_blocked_days", 0))

    orders_emitted_rate = _safe_rate(orders_emitted_days, total_days)
    orders_blocked_rate = _safe_rate(orders_blocked_days, orders_emitted_days or total_days)

    strategy_names = _collect_strategy_names(payload.get("days", []))
    consistency = len(strategy_names) <= 1

    scorecard = {
        "schema_version": 1,
        "total_days": total_days,
        "ok_days": ok_days,
        "error_days": error_days,
        "orders_emitted_days": orders_emitted_days,
        "orders_no_actions_days": orders_no_actions_days,
        "orders_blocked_days": orders_blocked_days,
        "orders_emitted_rate": orders_emitted_rate,
        "orders_blocked_rate": orders_blocked_rate,
        "consistency": bool(consistency),
    }
    atomic_write_json(outdir / "scorecard.json", scorecard)
    return scorecard


def _collect_strategy_names(days: list[dict]) -> set[str]:
    names: set[str] = set()
    for day_entry in days:
        manifest_path = day_entry.get("pipeline_manifest_path")
        if not manifest_path:
            continue
        path = Path(manifest_path)
        if not path.exists():
            continue
        manifest = _load_json(path)
        orders_stage = manifest.get("stages", {}).get("orders", {})
        if not isinstance(orders_stage, dict):
            continue
        orders_path = orders_stage.get("path")
        if not orders_path:
            continue
        orders_payload = _load_json(Path(orders_path))
        strategy = orders_payload.get("strategy", {})
        name = strategy.get("name")
        if name:
            names.add(str(name))
    return names


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _load_json(path: Path) -> dict:
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
