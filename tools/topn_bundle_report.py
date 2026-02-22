#!/usr/bin/env python3
"""FAZ584: TopN horizon bundle report — HTML+JSON+CSV with advice. Offline, deterministic."""
from __future__ import annotations

import csv
import html
import json
import os
import sys
from pathlib import Path

HORIZONS = (1, 3, 5, 20)
CSV_COLUMNS = (
    "day", "horizon_days", "rank", "symbol", "score", "p_up", "p_gt_cost",
    "mu_hat", "sigma_hat", "decision_raw", "has_artifact", "artifact_path", "headline",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_topn(reports_dir: Path, day: str, horizon: int) -> list[dict] | None:
    """Load topn_h{H}.csv or .json. Returns rows (already sorted) or None if missing."""
    for ext in ("csv", "json"):
        p = reports_dir / f"topn_h{horizon}.{ext}"
        if not p.is_file():
            continue
        try:
            if ext == "csv":
                with p.open(newline="", encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                return rows
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("rows") or []
        except (json.JSONDecodeError, OSError, csv.Error):
            pass
    return None


def _read_ask_artifact(ask_path: Path) -> dict | None:
    """Read ask JSON. Returns {decision_raw, score, text} or None."""
    if not ask_path.is_file():
        return None
    try:
        data = json.loads(ask_path.read_text(encoding="utf-8"))
        dec = data.get("decision_raw") or (data.get("Decision") or {}).get("decision_raw")
        score = data.get("score")
        if score is None and "Decision" in data:
            score = (data["Decision"] or {}).get("score")
        text = data.get("text") or ""
        return {"decision_raw": str(dec or "PASS"), "score": float(score or 0.0), "text": str(text)}
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def _build_advice_fallback(symbol: str, day: str, snapshot_root: Path) -> dict:
    """Build advice via advisor. Returns {decision_raw, score, text}."""
    try:
        sys.path.insert(0, str(_repo_root() / "src"))
        from bist_core.services.advisor import build_advice_for_symbol
        advice = build_advice_for_symbol(symbol, day, root=snapshot_root)
        return {
            "decision_raw": advice.decision_raw or "PASS",
            "score": float(advice.score or 0.0),
            "text": (advice.text or "").strip(),
        }
    except Exception:
        return {"decision_raw": "PASS", "score": 0.0, "text": "Güvenli mod: NoDecision. Veri veya karar üretilemedi."}


def _headline(text: str) -> str:
    """First line of text, trimmed."""
    if not text:
        return ""
    first = (text or "").split("\n")[0].strip()
    return first[:200] if first else ""


def _run_bundle(
    day: str,
    horizon: int,
    top_n: int,
    reports_root: Path,
    snapshot_root: Path,
    out_root: Path | None = None,
) -> list[dict] | None:
    """
    Build bundle rows. Returns list of dicts with CSV_COLUMNS keys, or None if topn missing.
    """
    reports_dir = reports_root / day
    topn_rows = _load_topn(reports_dir, day, horizon)
    if topn_rows is None:
        return None

    base = out_root if out_root is not None else (reports_root.parent if reports_root.name == "reports" else reports_root)
    ask_dir = base / "ask" / day

    rows: list[dict] = []
    for rank, row in enumerate(topn_rows[:top_n], 1):
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            continue

        ask_path = ask_dir / f"{symbol}.json"
        artifact = _read_ask_artifact(ask_path)
        if artifact is None:
            artifact = _build_advice_fallback(symbol, day, snapshot_root)

        headline = _headline(artifact.get("text") or "")

        rows.append({
            "day": day,
            "horizon_days": horizon,
            "rank": rank,
            "symbol": symbol,
            "score": row.get("score"),
            "p_up": row.get("p_up"),
            "p_gt_cost": row.get("p_gt_cost"),
            "mu_hat": row.get("mu_hat"),
            "sigma_hat": row.get("sigma_hat"),
            "decision_raw": artifact.get("decision_raw", "PASS"),
            "has_artifact": ask_path.is_file(),
            "artifact_path": str(ask_path) if ask_path.is_file() else "",
            "headline": headline,
            "_text": artifact.get("text") or "",
        })

    return rows


def _write_outputs(reports_dir: Path, horizon: int, day: str, rows: list[dict]) -> None:
    """Write topn_bundle_h{H}.json, .csv, .html."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    h = horizon

    report = {
        "schema_version": 1,
        "day": day,
        "horizon_days": horizon,
        "rows": [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in rows
        ],
    }

    json_path = reports_dir / f"topn_bundle_h{h}.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    csv_path = reports_dir / f"topn_bundle_h{h}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r[c]) for c in CSV_COLUMNS})

    html_path = reports_dir / f"topn_bundle_h{h}.html"
    lines = [
        "<!DOCTYPE html>",
        "<html lang='tr'>",
        "<head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>TopN Bundle {day} H{h}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:1em;max-width:40em}",
        "table{width:100%;border-collapse:collapse}td,th{border:1px solid #ccc;padding:.4em;text-align:left}",
        "",
        "a{color:#06c}summary{cursor:pointer}</style>",
        "</head>",
        "<body>",
        f"<h1>TopN Bundle {day} (H{h})</h1>",
        "<table><thead><tr>",
        "".join(f"<th>{html.escape(c)}</th>" for c in ("rank", "symbol", "score", "decision_raw", "headline")),
        "</tr></thead><tbody>",
    ]
    for r in rows:
        rank = r.get("rank", "")
        symbol = r.get("symbol", "")
        score = r.get("score", "")
        dec = r.get("decision_raw", "")
        headline = html.escape((r.get("headline") or "")[:80])
        text = html.escape(r.get("_text", "") or "")
        lines.append(
            f"<tr><td>{rank}</td><td>{symbol}</td><td>{score}</td><td>{dec}</td>"
            f"<td><details><summary>{headline}</summary><pre>{text}</pre></details></td></tr>"
        )
    lines.extend(["</tbody></table>", "</body>", "</html>"])
    html_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="FAZ584: TopN horizon bundle report")
    p.add_argument("--day", required=True, help="YYYY-MM-DD")
    p.add_argument("--horizon", type=int, required=True, choices=HORIZONS)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--reports-root", default="data/log/reports")
    p.add_argument("--snapshot-root", default=None)
    args = p.parse_args()

    repo = _repo_root()
    reports_root = Path(args.reports_root)
    if not reports_root.is_absolute():
        reports_root = (repo / reports_root).resolve()

    snapshot_root = args.snapshot_root or os.environ.get("BIST_CORE_SNAPSHOT_DIR", "data/eod/snapshots")
    snapshot_root = Path(snapshot_root)
    if not snapshot_root.is_absolute():
        snapshot_root = (repo / snapshot_root).resolve()

    reports_dir = reports_root / args.day
    rows = _run_bundle(
        day=args.day,
        horizon=args.horizon,
        top_n=args.top,
        reports_root=reports_root,
        snapshot_root=snapshot_root,
    )

    if rows is None:
        print(f"topn_h{args.horizon} not found", file=sys.stderr)
        return 2

    try:
        _write_outputs(reports_dir, args.horizon, args.day, rows)
        print(f"topn_bundle_h{args.horizon} -> {reports_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
