"""Portfolio engine v2 — selection, sector cap, weights."""

from __future__ import annotations

from bist_core.portfolio_engine_v2 import (
    PositionCandidate,
    PortfolioAllocation,
    apply_portfolio_v2_to_trades,
    compute_portfolio_allocation,
)


def test_empty_candidates() -> None:
    assert compute_portfolio_allocation([]) == []


def test_selects_top_edge_symbols() -> None:
    cands = [
        PositionCandidate("A", 0.3, 0.5, "x"),
        PositionCandidate("B", 0.9, 0.5, "y"),
        PositionCandidate("C", 0.5, 0.5, "z"),
    ]
    out = compute_portfolio_allocation(cands, max_positions=2)
    assert [a.symbol for a in out] == ["B", "C"]


def test_sector_cap_max_two() -> None:
    cands = [
        PositionCandidate("A1", 0.9, 0.6, "bank"),
        PositionCandidate("A2", 0.88, 0.6, "bank"),
        PositionCandidate("A3", 0.87, 0.6, "bank"),
        PositionCandidate("B1", 0.5, 0.6, "tech"),
    ]
    out = compute_portfolio_allocation(cands, max_positions=5)
    syms = [a.symbol for a in out]
    assert syms.count("A1") + syms.count("A2") + syms.count("A3") <= 2
    assert "B1" in syms


def test_weights_sum_to_one() -> None:
    cands = [
        PositionCandidate("A", 0.8, 0.7, "s1"),
        PositionCandidate("B", 0.6, 0.6, "s2"),
    ]
    out = compute_portfolio_allocation(cands, max_positions=5)
    s = sum(a.weight for a in out)
    assert abs(s - 1.0) < 1e-9


def test_higher_edge_higher_weight() -> None:
    cands = [
        PositionCandidate("LOW", 0.4, 0.8, "a"),
        PositionCandidate("HIGH", 0.95, 0.8, "b"),
    ]
    out = compute_portfolio_allocation(cands, max_positions=2)
    m = {a.symbol: a.weight for a in out}
    assert m["HIGH"] > m["LOW"]


def test_no_weight_exceeds_cap_after_allocation() -> None:
    cands = [
        PositionCandidate("A", 0.95, 0.9, "s1"),
        PositionCandidate("B", 0.9, 0.9, "s2"),
        PositionCandidate("C", 0.5, 0.8, "s3"),
    ]
    out = compute_portfolio_allocation(cands, max_positions=5)
    for a in out:
        assert a.weight <= 0.40 + 1e-9
    assert abs(sum(x.weight for x in out) - 1.0) < 1e-9


def test_apply_portfolio_v2_second_pass_does_not_rescale() -> None:
    scan = [
        {
            "symbol": "A",
            "confidence": 0.8,
            "sector": "x",
            "decision": {"edge_score": 0.9},
        },
    ]
    trades = [{"symbol": "A", "size": 1000.0}]
    apply_portfolio_v2_to_trades(scan, trades)
    first = float(trades[0]["size"])
    apply_portfolio_v2_to_trades(scan, trades)
    assert trades[0]["size"] == first
    assert trades[0].get("_v2_scaled") is True


def test_apply_portfolio_v2_to_trades_scales_and_zeros() -> None:
    scan = [
        {
            "symbol": "A",
            "confidence": 0.8,
            "sector": "x",
            "decision": {"edge_score": 0.9},
        },
        {
            "symbol": "B",
            "confidence": 0.8,
            "sector": "y",
            "decision": {"edge_score": 0.65},
        },
    ]
    trades = [
        {"symbol": "A", "size": 1000.0},
        {"symbol": "B", "size": 1000.0},
        {"symbol": "Z", "size": 500.0},
    ]
    alloc = apply_portfolio_v2_to_trades(scan, trades)
    assert isinstance(alloc, list)
    assert all(isinstance(a, PortfolioAllocation) for a in alloc)
    za = next(t for t in trades if t["symbol"] == "Z")
    assert za["size"] == 0.0
    assert trades[0]["size"] > 0.0 and trades[1]["size"] > 0.0
    assert abs(trades[0]["size"] + trades[1]["size"] - 1000.0) < 1e-6
