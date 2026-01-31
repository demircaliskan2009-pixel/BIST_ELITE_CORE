"""
FAZ62: Model plugin interface predict(features)->scores; baseline implementation; advisory wiring.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.models.base import ModelPlugin
from bist_core.models.baseline import BaselineModel
from bist_core.advisory.generate import generate_advice, _score_to_side


def test_faz62_baseline_predict_returns_scores_same_order() -> None:
    """BaselineModel.predict(features) returns one score per row, same order."""
    model = BaselineModel()
    features = [
        {"symbol": "A", "close": 10.0},
        {"symbol": "B", "close": 20.0},
    ]
    scores = model.predict(features)
    assert len(scores) == 2
    assert scores[0] != scores[1]
    assert all(isinstance(s, (int, float)) for s in scores)


def test_faz62_baseline_deterministic() -> None:
    """Same features -> same scores (deterministic)."""
    model = BaselineModel()
    features = [{"symbol": "X", "close": 100.0}]
    s1 = model.predict(features)
    s2 = model.predict(features)
    assert s1 == s2
    assert len(s1) == 1


def test_faz62_baseline_empty_features() -> None:
    """Empty features -> empty scores."""
    model = BaselineModel()
    assert model.predict([]) == []


def test_faz62_baseline_missing_close_defaults_zero() -> None:
    """Missing close defaults to 0."""
    model = BaselineModel()
    scores = model.predict([{"symbol": "Z"}])
    assert len(scores) == 1
    assert isinstance(scores[0], (int, float))


def test_faz62_model_plugin_protocol() -> None:
    """BaselineModel satisfies ModelPlugin (has predict)."""
    model = BaselineModel()
    assert hasattr(model, "predict")
    assert callable(getattr(model, "predict"))


def test_faz62_score_to_side() -> None:
    """_score_to_side maps positive/negative/zero to BUY/SELL/HOLD."""
    assert _score_to_side(0.1) == "BUY"
    assert _score_to_side(-0.1) == "SELL"
    assert _score_to_side(0.0) == "HOLD"


def test_faz62_generate_advice_with_model_plugin(tmp_path: Path) -> None:
    """generate_advice with model_plugin uses model scores; records have score/side from model."""
    day = "2099-01-20"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / day).mkdir(exist_ok=True)
    (snap_dir / day / "snapshot.csv").write_text(
        "symbol,date,close\nAAA,2099-01-20,10\nBBB,2099-01-20,20\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    model = BaselineModel()
    result = generate_advice(
        day, snap_dir, outdir, model_plugin=model
    )
    assert result["total"] == 2
    assert result["errors"] == 0
    records = result["records"]
    assert len(records) == 2
    by_symbol = {r["symbol"]: r for r in records}
    assert "AAA" in by_symbol and "BBB" in by_symbol
    for r in records:
        assert "score" in r
        assert r["side"] in ("BUY", "SELL", "HOLD")
        assert r["reason"] == "model"
    path = Path(result["path"])
    target = path / "advice_records.jsonl"
    assert target.is_file()
    lines = target.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        rec = json.loads(line)
        assert rec["symbol"] in ("AAA", "BBB")
        assert "score" in rec


def test_faz62_generate_advice_without_model_plugin_uses_advisor(tmp_path: Path) -> None:
    """Without model_plugin, generate_advice uses advisor (build_advice_for_symbol)."""
    day = "2099-01-21"
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / day).mkdir(exist_ok=True)
    (snap_dir / day / "snapshot.csv").write_text(
        "symbol,date,close\nCCC,2099-01-21,30\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    result = generate_advice(day, snap_dir, outdir, model_plugin=None)
    assert result["total"] >= 1
    assert any(r["symbol"] == "CCC" for r in result["records"])
    # Reason comes from advisor (not "model")
    ccc = next(r for r in result["records"] if r["symbol"] == "CCC")
    assert "reason" in ccc
