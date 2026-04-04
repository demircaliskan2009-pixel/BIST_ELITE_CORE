"""Portfolio engine v2 — sector caps, edge-priority selection, nonlinear capital weights."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

# Same floors as decision_engine_v2 / live portfolio hard gate.
_V2_HARD_EDGE_MIN = 0.60
_V2_HARD_CONF_MIN = 0.55


@dataclass
class PositionCandidate:
    symbol: str
    edge: float
    confidence: float
    sector: str


@dataclass
class PortfolioAllocation:
    symbol: str
    weight: float


def compute_portfolio_allocation(
    candidates: List[PositionCandidate],
    max_positions: int = 5,
) -> List[PortfolioAllocation]:
    if not candidates:
        return []

    # --- SCORE (EDGE PRIORITY) ---
    scored = sorted(
        candidates,
        key=lambda x: (x.edge * 0.7 + x.confidence * 0.3),
        reverse=True,
    )

    selected: List[PositionCandidate] = []
    sector_count: Dict[str, int] = {}

    for c in scored:
        # --- SECTOR CAP (max 2 per sector) ---
        if sector_count.get(c.sector, 0) >= 2:
            continue

        selected.append(c)
        sector_count[c.sector] = sector_count.get(c.sector, 0) + 1

        if len(selected) >= max_positions:
            break

    if not selected:
        return []

    # --- CAPITAL ALLOCATION (NONLINEAR EDGE) ---
    # 1) compute raw scores
    scores: List[float] = []
    for c in selected:
        s = (c.edge**2.2) * (0.3 + 0.7 * c.confidence)
        scores.append(s)

    total_score = sum(scores)

    # 2) normalize FIRST
    if total_score > 0:
        weights = [s / total_score for s in scores]
    else:
        weights = [0.0] * len(scores)

    # 3–4) cap AFTER normalization — water-filling via level λ (x_i = min(max, λ·w_i), Σx=1)
    # n>=3: 40% hard cap; n<3: soft cap to limit concentration while keeping full deployment.
    n_w = max(1, len(weights))
    if n_w >= 3:
        max_weight = 0.40
    else:
        max_weight = 0.75  # soft cap for small portfolios

    # --- WATER-FILLING CAP ALGORITHM ---
    def mass(lam: float) -> float:
        return sum(min(max_weight, lam * w) for w in weights)

    if n_w == 1:
        final_weights = [1.0]
    else:
        cap_sum = mass(1.0)
        if cap_sum >= 1.0 - 1e-15:
            lam = 1.0
        else:
            hi = 1.0
            while mass(hi) < 1.0 - 1e-15:
                hi *= 2.0
            lo = 0.0
            for _ in range(64):
                mid = (lo + hi) * 0.5
                if mass(mid) < 1.0:
                    lo = mid
                else:
                    hi = mid
            lam = hi
        min_weight = 0.02

        raw = [min(max_weight, lam * w) for w in weights]

        floored: List[float] = []
        deficit = 0.0

        # 1) apply floor and track deficit
        for x in raw:
            if x > 0 and x < min_weight:
                deficit += min_weight - x
                floored.append(min_weight)
            else:
                floored.append(x)

        # 2) remove deficit proportionally ONLY from weights above floor
        available = sum(x - min_weight for x in floored if x > min_weight)

        if available > 0 and deficit > 0 and deficit <= available + 1e-14:
            adjusted: List[float] = []
            for x in floored:
                if x > min_weight:
                    reduction = (x - min_weight) / available * deficit
                    adjusted.append(x - reduction)
                else:
                    adjusted.append(x)
            final_weights = adjusted
        elif deficit > available + 1e-14:
            # not enough capacity to fund floor → drop weakest positions
            pairs = list(enumerate(floored))
            pairs.sort(key=lambda x: (x[1], x[0]))

            remaining = pairs.copy()

            while True:
                total_rem = sum(w for _, w in remaining)
                if total_rem <= 1.0:
                    break

                remaining.pop(0)

                if not remaining:
                    break

            if not remaining:
                raise RuntimeError("PORTFOLIO_ALLOCATION_FAILED_NO_VALID_WEIGHTS")

            # rebuild normalized weights
            final_weights = [0.0] * len(floored)
            total = sum(w for _, w in remaining)

            if total > 0:
                for idx, w in remaining:
                    final_weights[idx] = w / total
            else:
                raise RuntimeError("PORTFOLIO_ALLOCATION_ZERO_TOTAL")
        else:
            final_weights = floored

    weights = final_weights

    total_final = sum(weights)
    if abs(total_final - 1.0) > 1e-6:
        raise RuntimeError(
            f"PORTFOLIO_ALLOCATION_SUM_INVALID: {total_final}"
        )

    weight_cap = 1.0 if n_w == 1 else max_weight
    if not all(0.0 <= w <= weight_cap + 1e-6 for w in weights):
        raise RuntimeError("PORTFOLIO_ALLOCATION_CONSTRAINT_VIOLATION")

    allocations: List[PortfolioAllocation] = []

    for c, w in zip(selected, weights):
        allocations.append(PortfolioAllocation(c.symbol, w))

    return allocations


def apply_portfolio_v2_to_trades(
    scan_results: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    *,
    max_positions: int = 5,
) -> List[PortfolioAllocation]:
    """Build candidates from ``scan_results``, allocate weights, scale ``trades`` ``size``, log PORTFOLIO_V2."""
    candidates: List[PositionCandidate] = []
    for symbol_data in scan_results:
        if not isinstance(symbol_data, dict):
            continue
        sym = str(symbol_data.get("symbol", "")).strip()
        if not sym:
            continue
        dec = symbol_data.get("decision")
        if not isinstance(dec, dict) or dec.get("edge_score") is None:
            raise RuntimeError("EDGE_SSOT_VIOLATION")
        try:
            edge = float(dec["edge_score"])
            conf = float(symbol_data["confidence"])
        except (TypeError, ValueError):
            raise RuntimeError("EDGE_SSOT_VIOLATION") from None
        if edge != edge:
            raise RuntimeError("EDGE_SSOT_VIOLATION")
        if edge < _V2_HARD_EDGE_MIN or conf < _V2_HARD_CONF_MIN:
            print(
                {
                    "PORTFOLIO_HARD_GATE_REJECT": {
                        "symbol": sym.upper(),
                        "phase": "portfolio_v2_candidate",
                        "reason": (
                            "edge_below_0_60"
                            if edge < _V2_HARD_EDGE_MIN
                            else "confidence_below_0_55"
                        ),
                        "edge": float(edge),
                        "confidence": float(conf),
                        "edge_floor": _V2_HARD_EDGE_MIN,
                        "confidence_floor": _V2_HARD_CONF_MIN,
                    }
                },
                flush=True,
            )
            continue
        sector = str(symbol_data.get("sector", "unknown"))
        candidates.append(
            PositionCandidate(
                symbol=sym,
                edge=edge,
                confidence=conf,
                sector=sector,
            )
        )

    allocations = compute_portfolio_allocation(candidates, max_positions=max_positions)
    allocation_map = {a.symbol: a.weight for a in allocations}

    print(
        {
            "PORTFOLIO_V2": {
                "selected": [a.symbol for a in allocations],
                "weights": allocation_map,
            }
        },
        flush=True,
    )

    for trade in trades:
        if not isinstance(trade, dict):
            continue
        tsym = str(trade.get("symbol", "")).strip()
        if tsym in allocation_map:
            if trade.get("_v2_scaled"):
                continue
            weight = float(allocation_map[tsym])
            try:
                trade["size"] = float(trade.get("size", 0.0) or 0.0)
            except (TypeError, ValueError):
                trade["size"] = 0.0
            trade["size"] *= weight
            trade["_v2_scaled"] = True
        else:
            trade["size"] = 0.0

    return allocations
