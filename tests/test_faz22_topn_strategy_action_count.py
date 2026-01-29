from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def test_topn_strategy_action_count(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    snapshot_root = tmp_path / "data" / "eod" / "snapshots"
    day = "2099-02-02"
    day_dir = snapshot_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    symbols = [f"SYM{i:03d}" for i in range(10)]
    (day_dir / "snapshot.csv").write_text(
        "symbol,close\n" + "\n".join(f"{sym},1.0" for sym in symbols),
        encoding="utf-8",
    )
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_root)

    outdir = tmp_path / "run_out"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "eod",
            "run",
            "--day",
            day,
            "--outdir",
            str(outdir),
            "--ignore-calendar",
            "--emit-orders",
            "--orders-strategy",
            "top_n_by_signal",
            "--orders-top-n",
            "5",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
        check=False,
    )
    assert result.returncode == 0

    orders_path = outdir / "orders" / day / "orders_intent.json"
    payload = json.loads(orders_path.read_text(encoding="utf-8"))
    actions = payload["actions"]
    assert len(actions) == 5
    action_symbols = [action["symbol"] for action in actions]
    assert action_symbols == sorted(action_symbols)

    ranked = sorted(
        symbols,
        key=lambda sym: (
            int(hashlib.sha256(sym.encode("utf-8")).hexdigest(), 16),
            sym,
        ),
    )
    assert sorted(action_symbols) == sorted(ranked[:5])
