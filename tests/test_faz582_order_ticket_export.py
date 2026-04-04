"""FAZ582: Order ticket export — CSV + TXT from orders_intent v2. Deterministic, offline."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


_repo = Path(__file__).resolve().parents[1]
_fixture = _repo / "tools" / "fixtures" / "orders_intent_valid.json"


def _run_export(orders_path: Path, out_dir: Path | None = None) -> tuple[int, str, str]:
    """Run order_ticket_export.py. Returns (exit_code, stdout, stderr)."""
    args = [sys.executable, str(_repo / "tools" / "order_ticket_export.py"), "--orders", str(orders_path)]
    if out_dir:
        args.extend(["--out", str(out_dir)])
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=10)
    return r.returncode, r.stdout or "", r.stderr or ""


def test_files_created(tmp_path: Path) -> None:
    """Export creates order_ticket.csv and order_ticket.txt."""
    out_dir = tmp_path / "tickets"
    code, _, _ = _run_export(_fixture, out_dir)
    assert code == 0
    assert (out_dir / "order_ticket.csv").is_file()
    assert (out_dir / "order_ticket.txt").is_file()


def test_csv_header_exact(tmp_path: Path) -> None:
    """CSV header is exactly day,symbol,side,qty,order_type,limit_price,notes."""
    out_dir = tmp_path / "tickets"
    _run_export(_fixture, out_dir)
    with (out_dir / "order_ticket.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == ["day", "symbol", "side", "qty", "order_type", "limit_price", "notes"]


def test_stable_ordering(tmp_path: Path) -> None:
    """Actions sorted by symbol then side."""
    orders_file = tmp_path / "multi.json"
    orders_file.write_text(
        json.dumps(
            {
                "day": "2025-01-15",
                "actions": [
                    {"symbol": "BBB", "side": "SELL"},
                    {"symbol": "AAA", "side": "BUY"},
                    {"symbol": "AAA", "side": "SELL"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "tickets"
    _run_export(orders_file, out_dir)
    with (out_dir / "order_ticket.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    symbols = [r["symbol"] for r in rows]
    assert symbols == ["AAA", "AAA", "BBB"]
    assert rows[0]["side"] == "BUY"
    assert rows[1]["side"] == "SELL"


def test_deterministic_text_output(tmp_path: Path) -> None:
    """Same input => same TXT output."""
    out_dir = tmp_path / "tickets"
    _run_export(_fixture, out_dir)
    txt1 = (out_dir / "order_ticket.txt").read_text(encoding="utf-8")

    # Re-run to same dir (overwrite)
    _run_export(_fixture, out_dir)
    txt2 = (out_dir / "order_ticket.txt").read_text(encoding="utf-8")
    assert txt1 == txt2


def test_unsupported_order_type_exit_1(tmp_path: Path) -> None:
    """Unsupported order_type => exit 1, deterministic error."""
    orders_file = tmp_path / "bad_type.json"
    orders_file.write_text(
        json.dumps(
            {
                "day": "2025-01-15",
                "actions": [{"symbol": "ASELS", "side": "BUY", "order_type": "STOP"}],
            }
        ),
        encoding="utf-8",
    )
    code, _, stderr = _run_export(orders_file, tmp_path / "out")
    assert code == 1
    assert "order_type_unsupported" in stderr or "STOP" in stderr


def test_missing_file_exit_2(tmp_path: Path) -> None:
    """Missing orders file => exit 2."""
    code, _, stderr = _run_export(tmp_path / "nonexistent.json", tmp_path / "out")
    assert code == 2
    assert "orders_file" in stderr or "not_found" in stderr.lower()


def test_order_type_default_market(tmp_path: Path) -> None:
    """Missing order_type => MARKET."""
    orders_file = tmp_path / "orders.json"
    orders_file.write_text(
        json.dumps({"day": "2025-01-20", "actions": [{"symbol": "X", "side": "BUY"}]}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    code, _, _ = _run_export(orders_file, out_dir)
    assert code == 0
    with (out_dir / "order_ticket.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["order_type"] == "MARKET"
    assert rows[0]["limit_price"] == ""
