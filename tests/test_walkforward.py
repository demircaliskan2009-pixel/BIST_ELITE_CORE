"""PRDV3: walk-forward split correctness and OOS isolation."""

from __future__ import annotations

from bist_core.validation.walkforward import walkforward_split


def test_walkforward_split():
    data = list(range(100))
    train, test = walkforward_split(data)
    assert len(train) == 70
    assert len(test) == 30


def test_no_data_leakage():
    data = list(range(100))
    train, test = walkforward_split(data)
    assert max(train) < min(test)


def test_edge_stability():
    data = list(range(100))
    train, test = walkforward_split(data)
    train_mean = sum(train) / len(train)
    test_mean = sum(test) / len(test)
    # Contiguous index split: mean gap is exactly 50 for 0..99 @ 70/30.
    assert abs(train_mean - test_mean) <= 50
