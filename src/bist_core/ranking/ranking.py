"""Ranking Engine — rank scanner outputs into best trade candidates."""

from __future__ import annotations

import math
from typing import Any

REQUIRED_FIELDS = ("symbol", "score", "signal_strength", "volatility", "trend")
SCORE_WEIGHT = 0.5
SIGNAL_WEIGHT = 0.3
VOL_WEIGHT = 0.2


def _has_required_fields(candidate: dict) -> bool:
    for k in REQUIRED_FIELDS:
        if k not in candidate:
            return False
    return True


def _valid_float(v: Any) -> bool:
    if v is None:
        return False
    try:
        f = float(v)
        return not math.isnan(f)
    except (TypeError, ValueError):
        return False


def _is_valid(candidate: dict) -> bool:
    if not _has_required_fields(candidate):
        return False
    if not _valid_float(candidate.get("score")):
        return False
    if not _valid_float(candidate.get("signal_strength")):
        return False
    if not _valid_float(candidate.get("volatility")):
        return False
    return True


def _normalize(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    return (x - lo) / (hi - lo)


class RankingEngine:
    """Rank scanner outputs into best trade candidates.

    Deterministic, fail-closed, no randomness.
    """

    def rank(self, candidates: list[dict]) -> list[dict]:
        """Rank candidates by final_score descending, assign rank 1..n.

        Skips candidates with missing fields, NaN, or invalid types.
        """
        valid: list[dict] = []
        for c in candidates:
            if not _is_valid(c):
                continue
            valid.append(c)

        if not valid:
            return []

        scores = [float(c["score"]) for c in valid]
        signals = [float(c["signal_strength"]) for c in valid]
        vols = [float(c["volatility"]) for c in valid]

        score_lo, score_hi = min(scores), max(scores)
        sig_lo, sig_hi = min(signals), max(signals)
        vol_lo, vol_hi = min(vols), max(vols)

        results: list[dict] = []
        for c in valid:
            s = float(c["score"])
            sig = float(c["signal_strength"])
            v = float(c["volatility"])
            norm_s = _normalize(s, score_lo, score_hi)
            norm_sig = _normalize(sig, sig_lo, sig_hi)
            norm_v = _normalize(v, vol_lo, vol_hi)
            final_score = (
                SCORE_WEIGHT * norm_s
                + SIGNAL_WEIGHT * norm_sig
                + VOL_WEIGHT * norm_v
            )
            confidence = min(max(final_score, 0.0), 1.0)
            results.append({
                "symbol": str(c["symbol"]),
                "final_score": final_score,
                "confidence": confidence,
                "rank": 0,
            })

        results.sort(key=lambda r: r["final_score"], reverse=True)
        for i, r in enumerate(results, start=1):
            r["rank"] = i
        return results
