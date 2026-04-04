"""Deterministic adaptive thresholds, market regime, edge memory, validation metrics."""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.live.edge_distribution_fix import apply_edge_distribution_adjustments
from bist_core.live.market_regime import aggregate_vol_trend_from_snap, detect_market_regime
from bist_core.live.symbol_edge_memory import SymbolEdgeMemory
from bist_core.models.ohlcv import OHLCVBar


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _mean(vals: Sequence[float]) -> float:
    if not vals:
        return 0.0
    return float(sum(vals)) / float(len(vals))


def _variance(vals: Sequence[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return float(sum((v - m) ** 2 for v in vals)) / float(len(vals))


@dataclass(frozen=True)
class CycleSample:
    selected: int
    portfolio_empty: bool
    actions: Tuple[str, ...]
    confidences: Tuple[float, ...]
    portfolio_scores: Tuple[float, ...]


class AdaptiveLiveController:
    """
    Rolling-window self-tuning + market regime + symbol edge memory.
    Confidence gate range: [0.08, 0.25], position fraction gate: [0.001, 0.01].
    """

    def __init__(self, *, window: int = 50) -> None:
        self._window = max(5, int(window))
        self._ring: Deque[CycleSample] = deque(maxlen=self._window)
        self._min_conf = 0.1
        self._min_pf = 0.002
        self._min_conf_fb = 0.08
        self._min_pf_fb = 0.001
        self._all_actions: List[str] = []
        self._all_confidences: List[float] = []
        self._all_scores: List[float] = []
        self._empty_cycle_count = 0
        self._prev_selected: Optional[int] = None
        self._turnover_abs: List[float] = []
        self._all_selected: List[int] = []
        self._regime_history: Deque[str] = deque(maxlen=500)
        self._portfolio_quality: Deque[float] = deque(maxlen=500)
        self._edge_memory = SymbolEdgeMemory()
        self._last_cycle_actions_count = 0

    def begin_cycle(self) -> dict[str, float]:
        """Call at start of each outer loop: rolling gate update from prior window."""
        return self.thresholds_for_next_cycle()

    def prepare_portfolio_phase(
        self,
        per_symbol: dict[str, dict[str, Any]],
        fe: FeatureEngineV2,
        cycle_actions: Sequence[str],
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, Any]]:
        """
        After symbol loop: regime from snapshot, regime-aware thresholds, edge scores for ranking.
        Returns (threshold_overrides, edge_scores, regime_debug).
        """
        avg_vol, avg_trend_abs = aggregate_vol_trend_from_snap(per_symbol, fe)
        regime = detect_market_regime(avg_vol, avg_trend_abs)
        self._regime_history.append(regime)

        base = self._snapshot_thresholds()
        thr = dict(base)
        risk_mult = 1.0

        if regime == "TRENDING":
            thr["min_conf"] = _clamp(thr["min_conf"] * 0.93, 0.08, 0.25)
            thr["min_pf"] = _clamp(thr["min_pf"] * 1.02, 0.001, 0.01)
            thr["min_conf_fb"] = _clamp(thr["min_conf_fb"] * 0.94, 0.08, 0.22)
            thr["min_pf_fb"] = _clamp(thr["min_pf_fb"] * 1.01, 0.001, 0.008)
            risk_mult = 1.05
        elif regime == "CHOPPY":
            thr["min_conf"] = _clamp(thr["min_conf"] * 1.08, 0.08, 0.25)
            thr["min_pf"] = _clamp(thr["min_pf"] * 0.82, 0.001, 0.01)
            thr["min_conf_fb"] = _clamp(thr["min_conf_fb"] * 1.05, 0.08, 0.25)
            thr["min_pf_fb"] = _clamp(thr["min_pf_fb"] * 0.85, 0.001, 0.008)
            risk_mult = 0.88
        elif regime == "CALM":
            thr["min_conf"] = _clamp(thr["min_conf"] * 1.04, 0.08, 0.25)
            thr["min_pf"] = _clamp(thr["min_pf"] * 1.03, 0.001, 0.01)
            risk_mult = 0.92
        # MIXED: no extra multiplier

        # Stability boost: high turnover + low action diversity → tighten
        recent_turn = _mean(self._turnover_abs[-20:]) if len(self._turnover_abs) >= 5 else 0.0
        div = len({str(a) for a in cycle_actions}) if cycle_actions else 0
        self._last_cycle_actions_count = div
        if recent_turn > 2.5 and div <= 2:
            thr["min_conf"] = _clamp(thr["min_conf"] * 1.05, 0.08, 0.25)
            thr["min_pf"] = _clamp(thr["min_pf"] * 1.02, 0.001, 0.01)

        thr["risk_budget_mult"] = risk_mult

        try:
            ag = float(os.environ.get("BIST_ADAPTIVE_THRESHOLD_MULT", "1.0"))
        except ValueError:
            ag = 1.0
        ag = max(0.88, min(1.08, ag))
        for _k in ("min_conf", "min_conf_fb"):
            thr[_k] = _clamp(thr[_k] * ag, 0.08, 0.25)

        edge_scores: dict[str, float] = {}
        for sym, pack in per_symbol.items():
            if not isinstance(pack, dict):
                continue
            dec = pack.get("decision")
            if not isinstance(dec, dict):
                continue
            conf = float(dec.get("confidence") or 0.0)
            bars = pack.get("bars")
            mom_abs = 0.0
            if isinstance(bars, list) and len(bars) >= 50:
                ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
                if len(ohlcv) >= 50:
                    feat = fe.extract(ohlcv)
                    tr = float(feat.get("trend", 0.0) or 0.0)
                    bm = dec.get("brain_momentum")
                    try:
                        if bm is not None and float(bm) == float(bm):
                            mom_abs = abs(float(bm))
                        else:
                            mom_abs = abs(tr)
                    except (TypeError, ValueError):
                        mom_abs = abs(tr)
            edge_scores[str(sym).strip().upper()] = self._edge_memory.projected_edge_score(
                sym, confidence=conf, momentum_abs=mom_abs
            )

        edge_scores, _edge_dist_dbg = apply_edge_distribution_adjustments(
            edge_scores, per_symbol, fe, regime
        )
        print(
            {"EDGE_DISTRIBUTION_FIXED": True, "edge_distribution": _edge_dist_dbg},
            flush=True,
        )

        debug = {
            "market_regime": regime,
            "avg_volatility": round(avg_vol, 8),
            "avg_trend_abs": round(avg_trend_abs, 8),
            "edge_distribution": _edge_dist_dbg,
        }
        return thr, edge_scores, debug

    def finalize_after_portfolio(
        self,
        per_symbol: dict[str, dict[str, Any]],
        portfolio_payload: dict[str, Any],
        fe: FeatureEngineV2,
    ) -> None:
        """Update edge memory + portfolio quality from realized portfolio rows."""
        selected_syms = {
            str(p.get("symbol", "")).strip().upper()
            for p in portfolio_payload.get("PORTFOLIO", [])
            if isinstance(p, dict)
        }
        for sym, pack in per_symbol.items():
            if not isinstance(pack, dict):
                continue
            dec = pack.get("decision")
            if not isinstance(dec, dict):
                continue
            conf = float(dec.get("confidence") or 0.0)
            mom_abs = 0.0
            bars = pack.get("bars")
            if isinstance(bars, list) and len(bars) >= 50:
                ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
                if len(ohlcv) >= 50:
                    feat = fe.extract(ohlcv)
                    tr = float(feat.get("trend", 0.0) or 0.0)
                    bm = dec.get("brain_momentum")
                    try:
                        if bm is not None and float(bm) == float(bm):
                            mom_abs = abs(float(bm))
                        else:
                            mom_abs = abs(tr)
                    except (TypeError, ValueError):
                        mom_abs = abs(tr)
            us = str(sym).strip().upper()
            self._edge_memory.record(
                us,
                confidence=conf,
                momentum_abs=mom_abs,
                selected_in_portfolio=(us in selected_syms),
            )

        rows = [p for p in portfolio_payload.get("PORTFOLIO", []) if isinstance(p, dict)]
        if rows:
            confs = [float(r.get("confidence", 0.0)) for r in rows]
            scores = [float(r.get("score", 0.0)) for r in rows]
            ac = len({str(r.get("action", "")) for r in rows})
            avg_c = _mean(confs)
            sv = _variance(scores) if len(scores) >= 2 else 0.0
            pq = avg_c * float(ac) * max(sv, 1e-12)
            self._portfolio_quality.append(pq)

    def record_cycle(
        self,
        *,
        selected: int,
        portfolio_empty: bool,
        actions: Sequence[str],
        confidences: Sequence[float],
        portfolio_scores: Sequence[float],
    ) -> None:
        self._ring.append(
            CycleSample(
                selected=int(selected),
                portfolio_empty=bool(portfolio_empty),
                actions=tuple(str(a) for a in actions),
                confidences=tuple(float(c) for c in confidences if _finite(c)),
                portfolio_scores=tuple(float(s) for s in portfolio_scores if _finite(s)),
            )
        )
        self._all_actions.extend(str(a) for a in actions)
        self._all_confidences.extend(float(c) for c in confidences if _finite(c))
        self._all_scores.extend(float(s) for s in portfolio_scores if _finite(s))
        if portfolio_empty:
            self._empty_cycle_count += 1
        if self._prev_selected is not None:
            self._turnover_abs.append(abs(float(selected) - float(self._prev_selected)))
        self._prev_selected = int(selected)
        self._all_selected.append(int(selected))

    def thresholds_for_next_cycle(self) -> dict[str, float]:
        """Deterministic nudge from last ``window`` cycles toward avg_selected ≈ 2.5."""
        if len(self._ring) < 3:
            return self._snapshot_thresholds()

        recent = list(self._ring)
        avg_sel = _mean([float(c.selected) for c in recent])
        err = 2.5 - avg_sel
        self._min_conf = _clamp(0.15 - err * 0.035, 0.08, 0.25)
        self._min_pf = _clamp(0.0045 - err * 0.0008, 0.001, 0.01)
        self._min_conf_fb = _clamp(self._min_conf - 0.02, 0.08, min(0.22, self._min_conf))
        self._min_pf_fb = _clamp(self._min_pf * 0.55, 0.001, min(0.008, self._min_pf))

        empty_rate = sum(1 for c in recent if c.portfolio_empty) / float(len(recent))
        if empty_rate > 0.2:
            self._min_conf = _clamp(self._min_conf - 0.015, 0.08, 0.25)
            self._min_pf = _clamp(self._min_pf - 0.0004, 0.001, 0.01)

        return self._snapshot_thresholds()

    def _snapshot_thresholds(self) -> dict[str, float]:
        return {
            "min_conf": float(self._min_conf),
            "min_pf": float(self._min_pf),
            "min_conf_fb": float(self._min_conf_fb),
            "min_pf_fb": float(self._min_pf_fb),
        }

    def build_report(self, *, total_cycles: int) -> dict[str, Any]:
        """Full-run metrics + regime distribution + edge snapshot + portfolio quality."""
        sel_vals = [float(x) for x in self._all_selected]
        avg_selected = _mean(sel_vals) if sel_vals else 0.0

        uniq_actions = sorted(set(self._all_actions))
        action_diversity = len(uniq_actions)

        conf_var = _variance(self._all_confidences) if len(self._all_confidences) >= 2 else 0.0
        conf_spread = 0.0
        if len(self._all_confidences) >= 2:
            conf_spread = max(self._all_confidences) - min(self._all_confidences)
        score_var = _variance(self._all_scores) if len(self._all_scores) >= 2 else 0.0

        avg_turnover = _mean(self._turnover_abs) if self._turnover_abs else 0.0

        score_flat = len(self._all_scores) < 2
        score_diverse = False
        if len(self._all_scores) >= 2:
            score_diverse = _variance(self._all_scores) >= 1e-6 or len(
                {round(s, 4) for s in self._all_scores}
            ) >= 2

        rules = {
            "avg_selected_ok": avg_selected >= 2.5,
            "action_diversity_ok": action_diversity >= 3,
            "confidence_variance_ok": conf_spread >= 0.25,
            "no_empty_portfolio_cycles_ok": self._empty_cycle_count == 0,
            "score_distribution_ok": (not score_flat) and score_diverse,
        }
        passed = sum(1 for v in rules.values() if v)
        stability_score = passed / 5.0

        regime_dist: Dict[str, int] = {}
        for r in self._regime_history:
            regime_dist[r] = regime_dist.get(r, 0) + 1

        pq_list = list(self._portfolio_quality)
        pq_avg = _mean(pq_list) if pq_list else 0.0
        pq_improving = False
        if len(pq_list) >= 10:
            first = _mean(pq_list[: len(pq_list) // 2])
            second = _mean(pq_list[len(pq_list) // 2 :])
            pq_improving = second >= first

        edge_snap = self._edge_memory.snapshot_all()
        edge_vals = list(edge_snap.values())
        edge_spread = _variance(edge_vals) if len(edge_vals) >= 2 else 0.0

        return {
            "avg_selected": round(avg_selected, 6),
            "action_diversity": int(action_diversity),
            "confidence_variance": round(conf_var, 8),
            "confidence_spread": round(conf_spread, 8),
            "portfolio_score_variance": round(score_var, 12),
            "empty_portfolio_cycles": int(self._empty_cycle_count),
            "avg_portfolio_turnover_abs": round(avg_turnover, 6),
            "total_cycles": int(total_cycles),
            "stability_score": round(stability_score, 6),
            "hard_rules": rules,
            "frozen_thresholds": self._snapshot_thresholds(),
            "market_regime_distribution": regime_dist,
            "edge_scores": edge_snap,
            "edge_score_variance": round(edge_spread, 10),
            "portfolio_quality_avg": round(pq_avg, 10),
            "portfolio_quality_improving": pq_improving,
        }


def _finite(x: float) -> bool:
    try:
        v = float(x)
        return v == v
    except (TypeError, ValueError):
        return False


def adaptive_enabled() -> bool:
    return os.environ.get("BIST_ADAPTIVE_MODE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def adaptive_window_size() -> int:
    raw = os.environ.get("BIST_ADAPTIVE_WINDOW", "50").strip()
    try:
        w = int(raw)
        return max(5, min(200, w))
    except ValueError:
        return 50


__all__ = [
    "AdaptiveLiveController",
    "CycleSample",
    "adaptive_enabled",
    "adaptive_window_size",
]
