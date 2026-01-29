"""FAZ37: Broker interface + paper broker — deterministic fills; positions update."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz37_paper_fills_deterministic(tmp_path: Path) -> None:
    """Same orders_intent + same snapshot => same fills (deterministic)."""
    from bist_core.brokers import PaperBroker

    day = "2099-05-01"
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text(
        "symbol,close\nAAA,10.0\nBBB,20.0\n",
        encoding="utf-8",
    )
    orders_intent = {
        "schema_version": 1,
        "day": day,
        "actions": [
            {"symbol": "AAA", "side": "BUY", "weight": 0.5},
            {"symbol": "BBB", "side": "BUY", "weight": 0.5},
        ],
        "notes": [],
    }
    broker1 = PaperBroker(snapshot_root=snapshot_root, day=day, portfolio_value=1.0)
    fills1 = broker1.place_orders(orders_intent)
    broker2 = PaperBroker(snapshot_root=snapshot_root, day=day, portfolio_value=1.0)
    fills2 = broker2.place_orders(orders_intent)
    assert len(fills1) == 2
    assert len(fills2) == 2
    for i, (f1, f2) in enumerate(zip(fills1, fills2)):
        assert f1["symbol"] == f2["symbol"]
        assert f1["price"] == f2["price"]
        assert f1["qty"] == f2["qty"]
        assert f1["notional"] == f2["notional"]
    assert fills1[0]["symbol"] == "AAA"
    assert fills1[0]["price"] == 10.0
    assert fills1[0]["qty"] == 0.05  # 0.5 * 1.0 / 10.0
    assert fills1[1]["symbol"] == "BBB"
    assert fills1[1]["price"] == 20.0
    assert fills1[1]["qty"] == 0.025  # 0.5 * 1.0 / 20.0


def test_faz37_positions_update(tmp_path: Path) -> None:
    """After place_orders, get_positions returns positions matching fills."""
    from bist_core.brokers import PaperBroker

    day = "2099-05-02"
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,50.0\n",
        encoding="utf-8",
    )
    orders_intent = {
        "schema_version": 1,
        "day": day,
        "actions": [
            {"symbol": "AAA", "side": "BUY", "weight": 0.6},
            {"symbol": "BBB", "side": "BUY", "weight": 0.4},
        ],
        "notes": [],
    }
    broker = PaperBroker(snapshot_root=snapshot_root, day=day, portfolio_value=1.0)
    fills = broker.place_orders(orders_intent)
    positions = broker.get_positions()
    assert len(fills) == 2
    assert len(positions) == 2
    by_symbol = {p["symbol"]: p for p in positions}
    assert "AAA" in by_symbol
    assert "BBB" in by_symbol
    assert by_symbol["AAA"]["qty"] == 0.006  # 0.6/100
    assert by_symbol["BBB"]["qty"] == 0.008  # 0.4/50
    assert by_symbol["AAA"]["avg_price"] == 100.0
    assert by_symbol["BBB"]["avg_price"] == 50.0


def test_faz37_cli_broker_paper_run(tmp_path: Path) -> None:
    """CLI: bist_core broker paper run --day ... --orders <path> runs and outputs fills/positions."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    day = "2099-05-03"
    snapshot_root = tmp_path / "snapshots"
    (snapshot_root / day).mkdir(parents=True)
    (snapshot_root / day / "snapshot.csv").write_text(
        "symbol,close\nX,5.0\n",
        encoding="utf-8",
    )
    orders_path = tmp_path / "orders_intent.json"
    orders_path.write_text(
        json.dumps({
            "schema_version": 1,
            "day": day,
            "actions": [{"symbol": "X", "side": "BUY", "weight": 1.0}],
            "notes": [],
        }),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "broker",
            "paper",
            "run",
            "--day",
            day,
            "--orders",
            str(orders_path),
            "--snapshot-root",
            str(snapshot_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["day"] == day
    assert len(out["fills"]) == 1
    assert out["fills"][0]["symbol"] == "X"
    assert out["fills"][0]["price"] == 5.0
    assert out["fills"][0]["qty"] == 0.2  # 1.0 * 1.0 / 5.0
    assert len(out["positions"]) == 1
    assert out["positions"][0]["symbol"] == "X"
    assert out["positions"][0]["qty"] == 0.2
