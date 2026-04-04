from __future__ import annotations

import json
from pathlib import Path

from bist_core.advisory.generate import generate_advice


class _FakeModel:
    def predict(self, features):
        # features order is alphabetical by symbol from close_map
        # AAA -> 0.5, BBB -> 2.0, CCC -> 1.0
        return [0.5, 2.0, 1.0]


def test_scan_top_n_preserves_rank_order_with_model_plugin(tmp_path: Path) -> None:
    snap_root = tmp_path / "snaps"
    day_dir = snap_root / "2099-01-01"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(
        """symbol,close
AAA,10
BBB,20
CCC,30
""",
        encoding="utf-8",
    )

    outdir = tmp_path / "out"
    res = generate_advice(
        "2099-01-01",
        snap_root,
        outdir,
        top_n=2,
        model_plugin=_FakeModel(),
    )

    records = res["records"]
    assert [r["symbol"] for r in records] == ["BBB", "CCC"]
    assert [float(r["score"]) for r in records] == [2.0, 1.0]

    target = outdir / "advice" / "2099-01-01" / "advice_records.jsonl"
    lines = [json.loads(x) for x in target.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert [r["symbol"] for r in lines] == ["BBB", "CCC"]
