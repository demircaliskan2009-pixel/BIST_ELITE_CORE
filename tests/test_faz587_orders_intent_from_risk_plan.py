"""FAZ587: orders_intent draft from risk_plan. Synthetic fixtures, deterministic."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

PLAN_FIELDS = (
    "day",
    "horizon_days",
    "rank",
    "symbol",
    "capital_try",
    "risk_pct",
    "risk_try",
    "atr",
    "stop_atr_mult",
    "stop_distance",
    "qty",
    "tp_r_mult",
    "tp_distance",
    "notes",
)


def _run_orders_intent(
    day: str,
    horizon: int,
    top: int = 5,
    reports_root: Path | None = None,
    side: str = "BUY",
    order_type: str = "MARKET",
    limit_price_mode: str = "NONE",
    snapshot_root: Path | None = None,
) -> tuple[int, str, str]:
    """Run orders_intent_from_risk_plan.py. Returns (exit_code, stdout, stderr)."""
    args = [
        sys.executable,
        str(_repo / "tools" / "orders_intent_from_risk_plan.py"),
        "--day",
        day,
        "--horizon",
        str(horizon),
        "--top",
        str(top),
        "--side",
        side,
        "--order-type",
        order_type,
        "--limit-price-mode",
        limit_price_mode,
    ]
    if reports_root:
        args.extend(["--reports-root", str(reports_root)])
    if snapshot_root:
        args.extend(["--snapshot-root", str(snapshot_root)])
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout or "", r.stderr or ""


def _write_risk_plan_csv(reports_dir: Path, day: str, horizon: int, rows: list[dict]) -> None:
    """Write risk_plan_h{H}.csv."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"risk_plan_h{horizon}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PLAN_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r[c]) for c in PLAN_FIELDS})


def test_draft_schema(tmp_path: Path) -> None:
    """Draft has draft:true, draft_reason, day, actions."""
    reports_root = tmp_path / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_risk_plan_csv(
        reports_dir,
        "2025-03-15",
        1,
        [
            {
                "day": "2025-03-15",
                "horizon_days": 1,
                "rank": 1,
                "symbol": "AAA",
                "qty": 10,
                "capital_try": 30000,
                "risk_pct": 0.02,
                "risk_try": 600,
                "atr": 2.0,
                "stop_atr_mult": 2.0,
                "stop_distance": 4.0,
                "tp_r_mult": 2.0,
                "tp_distance": 8.0,
                "notes": "",
            },
        ],
    )

    code, _, _ = _run_orders_intent("2025-03-15", 1, reports_root=reports_root)
    assert code == 0
    data = json.loads((reports_dir / "orders_intent_draft_h1.json").read_text(encoding="utf-8"))
    assert data["draft"] is True
    assert data["draft_reason"] == "generated_from_risk_plan"
    assert data["day"] == "2025-03-15"
    assert "actions" in data
    assert len(data["actions"]) == 1
    assert data["actions"][0]["symbol"] == "AAA"
    assert data["actions"][0]["side"] == "BUY"
    assert data["actions"][0]["qty"] == 10
    assert data["actions"][0]["order_type"] == "MARKET"


def test_qty_zero_skipped(tmp_path: Path) -> None:
    """qty==0 -> skip from actions, in skipped with notes."""
    reports_root = tmp_path / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_risk_plan_csv(
        reports_dir,
        "2025-03-15",
        1,
        [
            {
                "day": "2025-03-15",
                "horizon_days": 1,
                "rank": 1,
                "symbol": "AAA",
                "qty": 0,
                "capital_try": 30000,
                "risk_pct": 0.02,
                "risk_try": 600,
                "atr": 2.0,
                "stop_atr_mult": 2.0,
                "stop_distance": 4.0,
                "tp_r_mult": 2.0,
                "tp_distance": 8.0,
                "notes": "TooSmall",
            },
            {
                "day": "2025-03-15",
                "horizon_days": 1,
                "rank": 2,
                "symbol": "BBB",
                "qty": 5,
                "capital_try": 30000,
                "risk_pct": 0.02,
                "risk_try": 600,
                "atr": 2.0,
                "stop_atr_mult": 2.0,
                "stop_distance": 4.0,
                "tp_r_mult": 2.0,
                "tp_distance": 8.0,
                "notes": "",
            },
        ],
    )

    code, _, _ = _run_orders_intent("2025-03-15", 1, reports_root=reports_root)
    assert code == 0
    data = json.loads((reports_dir / "orders_intent_draft_h1.json").read_text(encoding="utf-8"))
    assert len(data["actions"]) == 1
    assert data["actions"][0]["symbol"] == "BBB"
    assert len(data.get("skipped", [])) == 1
    assert data["skipped"][0]["symbol"] == "AAA"
    assert "TooSmall" in data["skipped"][0].get("reason", "")


def test_deterministic_ordering(tmp_path: Path) -> None:
    """Same input -> identical output. Order: rank then symbol."""
    reports_root = tmp_path / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_risk_plan_csv(
        reports_dir,
        "2025-03-15",
        1,
        [
            {
                "day": "2025-03-15",
                "horizon_days": 1,
                "rank": 2,
                "symbol": "BBB",
                "qty": 5,
                "capital_try": 30000,
                "risk_pct": 0.02,
                "risk_try": 600,
                "atr": 2.0,
                "stop_atr_mult": 2.0,
                "stop_distance": 4.0,
                "tp_r_mult": 2.0,
                "tp_distance": 8.0,
                "notes": "",
            },
            {
                "day": "2025-03-15",
                "horizon_days": 1,
                "rank": 1,
                "symbol": "AAA",
                "qty": 10,
                "capital_try": 30000,
                "risk_pct": 0.02,
                "risk_try": 600,
                "atr": 2.0,
                "stop_atr_mult": 2.0,
                "stop_distance": 4.0,
                "tp_r_mult": 2.0,
                "tp_distance": 8.0,
                "notes": "",
            },
        ],
    )

    _run_orders_intent("2025-03-15", 1, reports_root=reports_root)
    j1 = (reports_dir / "orders_intent_draft_h1.json").read_text(encoding="utf-8")
    _run_orders_intent("2025-03-15", 1, reports_root=reports_root)
    j2 = (reports_dir / "orders_intent_draft_h1.json").read_text(encoding="utf-8")
    assert j1 == j2

    data = json.loads(j1)
    symbols = [a["symbol"] for a in data["actions"]]
    assert symbols == ["AAA", "BBB"]


def test_missing_risk_plan_exit_2(tmp_path: Path) -> None:
    """Missing risk_plan => exit 2."""
    reports_root = tmp_path / "reports"
    (reports_root / "2025-03-15").mkdir(parents=True)

    code, _, stderr = _run_orders_intent("2025-03-15", 1, reports_root=reports_root)
    assert code == 2
    assert "risk_plan" in stderr.lower() or "not found" in stderr.lower()


def test_side_and_order_type(tmp_path: Path) -> None:
    """--side SELL and --order-type LIMIT are applied."""
    reports_root = tmp_path / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_risk_plan_csv(
        reports_dir,
        "2025-03-15",
        1,
        [
            {
                "day": "2025-03-15",
                "horizon_days": 1,
                "rank": 1,
                "symbol": "AAA",
                "qty": 10,
                "capital_try": 30000,
                "risk_pct": 0.02,
                "risk_try": 600,
                "atr": 2.0,
                "stop_atr_mult": 2.0,
                "stop_distance": 4.0,
                "tp_r_mult": 2.0,
                "tp_distance": 8.0,
                "notes": "",
            },
        ],
    )

    code, _, _ = _run_orders_intent("2025-03-15", 1, reports_root=reports_root, side="SELL", order_type="LIMIT")
    assert code == 0
    data = json.loads((reports_dir / "orders_intent_draft_h1.json").read_text(encoding="utf-8"))
    assert data["actions"][0]["side"] == "SELL"
    assert data["actions"][0]["order_type"] == "LIMIT"


def test_draft_exportable_to_ticket(tmp_path: Path) -> None:
    """Draft can be consumed by order_ticket_export."""
    reports_root = tmp_path / "reports"
    reports_dir = reports_root / "2025-03-15"
    _write_risk_plan_csv(
        reports_dir,
        "2025-03-15",
        1,
        [
            {
                "day": "2025-03-15",
                "horizon_days": 1,
                "rank": 1,
                "symbol": "AAA",
                "qty": 10,
                "capital_try": 30000,
                "risk_pct": 0.02,
                "risk_try": 600,
                "atr": 2.0,
                "stop_atr_mult": 2.0,
                "stop_distance": 4.0,
                "tp_r_mult": 2.0,
                "tp_distance": 8.0,
                "notes": "",
            },
        ],
    )

    _run_orders_intent("2025-03-15", 1, reports_root=reports_root)
    draft_path = reports_dir / "orders_intent_draft_h1.json"
    out_dir = tmp_path / "out" / "order_ticket" / "2025-03-15"

    from tools.order_ticket_export import run

    code, err, written = run(draft_path, out_dir)
    assert code == 0, err
    assert (out_dir / "order_ticket.csv").is_file()
    assert (out_dir / "order_ticket.txt").is_file()
