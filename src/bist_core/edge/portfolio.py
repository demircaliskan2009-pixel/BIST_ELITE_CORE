from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from bist_core.edge.orchestrator import PRDV3MasterOrchestratorConfig, PRDV3MasterOrchestratorResult, run_prdv3_master_orchestrator
from bist_core.edge.registry import EdgeDefinition
from bist_core.features.feature_registry import get_feature
from bist_core.models.ohlcv import OHLCVBar
from bist_core.risk.correlation_engine import CorrelationEngine
from bist_core.risk.sector_mapper import get_sector


@dataclass(frozen=True)
class PRDV3PortfolioEngineConfig:
    orchestrator_config: PRDV3MasterOrchestratorConfig = field(default_factory=PRDV3MasterOrchestratorConfig)
    max_total_exposure_pct: float = 0.30
    max_per_trade_pct: float = 0.10
    max_concurrent_positions: int = 5
    max_sector_positions: int = 2
    max_similar_trades: int = 2
    correlation_threshold: float = 0.80
    correlation_lookback: int = 20


@dataclass(frozen=True)
class PRDV3PortfolioDecision:
    symbol: str
    approved: bool
    selected_edge_id: str | None
    edge_state: str | None
    edge_score: float
    robustness_strength: float
    allocation_pct: float
    position_size: float
    risk: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "approved": self.approved,
            "selected_edge_id": self.selected_edge_id,
            "edge_state": self.edge_state,
            "edge_score": self.edge_score,
            "robustness_strength": self.robustness_strength,
            "allocation_pct": self.allocation_pct,
            "position_size": self.position_size,
            "risk": self.risk,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PRDV3PortfolioTradePlanEntry:
    symbol: str
    edge: str
    allocation_pct: float
    position_size: float
    risk: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "edge": self.edge,
            "allocation_pct": self.allocation_pct,
            "position_size": self.position_size,
            "risk": self.risk,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PRDV3PortfolioRiskReport:
    total_trades: int
    total_exposure: float
    remaining_cash: float
    risk_distribution: dict[str, Any]
    rejected_symbols: tuple[str, ...]
    logs: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "total_exposure": self.total_exposure,
            "remaining_cash": self.remaining_cash,
            "risk_distribution": dict(self.risk_distribution),
            "rejected_symbols": list(self.rejected_symbols),
            "logs": [dict(log) for log in self.logs],
        }


@dataclass(frozen=True)
class PRDV3PortfolioEngineResult:
    valid: bool
    portfolio_decisions: tuple[PRDV3PortfolioDecision, ...]
    total_exposure: float
    risk_report: PRDV3PortfolioRiskReport
    trade_plan: tuple[PRDV3PortfolioTradePlanEntry, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "portfolio_decisions": [decision.to_dict() for decision in self.portfolio_decisions],
            "total_exposure": self.total_exposure,
            "risk_report": self.risk_report.to_dict(),
            "trade_plan": [entry.to_dict() for entry in self.trade_plan],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class _PortfolioCandidate:
    symbol: str
    selected_edge_id: str
    edge_state: str
    edge_score: float
    robustness_strength: float
    drawdown: float
    proposed_allocation_pct: float
    proposed_position_size: float
    proposed_risk: float
    volatility_factor: float
    drawdown_factor: float
    sector: str
    bars: tuple[OHLCVBar, ...]
    reason: str


def _round_value(value: float) -> float:
    return round(float(value), 6)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _empty_result(reason: str, logs: list[dict[str, Any]] | None = None, rejected_symbols: Sequence[str] | None = None) -> PRDV3PortfolioEngineResult:
    report = PRDV3PortfolioRiskReport(
        total_trades=0,
        total_exposure=0.0,
        remaining_cash=0.0,
        risk_distribution={
            "allocation_pct_by_symbol": {},
            "risk_amount_by_symbol": {},
            "edge_state_by_symbol": {},
            "sector_by_symbol": {},
        },
        rejected_symbols=tuple(sorted(rejected_symbols or ())),
        logs=tuple(logs or ()),
    )
    return PRDV3PortfolioEngineResult(
        valid=False,
        portfolio_decisions=(),
        total_exposure=0.0,
        risk_report=report,
        trade_plan=(),
        reason=reason,
    )


def _validate_config(config: PRDV3PortfolioEngineConfig) -> str | None:
    if not math.isfinite(float(config.max_total_exposure_pct)) or not 0.0 < float(config.max_total_exposure_pct) <= 1.0:
        return "invalid_config:max_total_exposure_pct"
    if not math.isfinite(float(config.max_per_trade_pct)) or not 0.0 < float(config.max_per_trade_pct) <= 1.0:
        return "invalid_config:max_per_trade_pct"
    if float(config.max_per_trade_pct) > float(config.max_total_exposure_pct):
        return "invalid_config:max_per_trade_pct_gt_total"
    if int(config.max_concurrent_positions) < 1:
        return "invalid_config:max_concurrent_positions"
    if int(config.max_sector_positions) < 1:
        return "invalid_config:max_sector_positions"
    if int(config.max_similar_trades) < 1:
        return "invalid_config:max_similar_trades"
    if not math.isfinite(float(config.correlation_threshold)) or not -1.0 <= float(config.correlation_threshold) <= 1.0:
        return "invalid_config:correlation_threshold"
    if int(config.correlation_lookback) < 2:
        return "invalid_config:correlation_lookback"
    return None


def _normalize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = str(symbol or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _normalize_symbol_data(symbol_data: Mapping[str, Sequence[OHLCVBar]]) -> dict[str, tuple[OHLCVBar, ...]]:
    normalized: dict[str, tuple[OHLCVBar, ...]] = {}
    for symbol, bars in symbol_data.items():
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            continue
        normalized[normalized_symbol] = tuple(bars)
    return normalized


def _portfolio_orchestrator_config(config: PRDV3PortfolioEngineConfig) -> PRDV3MasterOrchestratorConfig:
    allocation_config = replace(
        config.orchestrator_config.allocation_config,
        max_exposure_pct=min(
            float(config.orchestrator_config.allocation_config.max_exposure_pct),
            float(config.max_per_trade_pct) * 100.0,
        ),
    )
    return replace(config.orchestrator_config, allocation_config=allocation_config)


def _selected_score(result: PRDV3MasterOrchestratorResult) -> float:
    for log in reversed(result.logs):
        if log.get("event") == "edge_selection_completed":
            return _round_value(float(log.get("score", 0.0) or 0.0))
    return 0.0


def _selected_evaluation(result: PRDV3MasterOrchestratorResult):
    if result.selected_edge_id is None:
        return None
    for evaluation in result.edge_evaluations:
        if evaluation.edge_id == result.selected_edge_id:
            return evaluation
    return None


def _robustness_strength(positive_window_ratio: float, overfit_gap: float) -> float:
    if not math.isfinite(float(positive_window_ratio)) or not math.isfinite(float(overfit_gap)):
        return 0.0
    return _round_value(_clamp01(float(positive_window_ratio)) / (1.0 + max(float(overfit_gap), 0.0)))


def _volatility_factor(bars: Sequence[OHLCVBar], orchestrator_config: PRDV3MasterOrchestratorConfig) -> float:
    atr_series = get_feature("atr_14")(bars)
    if not atr_series or atr_series[-1] is None:
        return 0.0
    atr_value = float(atr_series[-1])
    close_value = float(bars[-1].close)
    if not math.isfinite(atr_value) or atr_value <= 0.0 or not math.isfinite(close_value) or close_value <= 0.0:
        return 0.0
    atr_ratio = atr_value / close_value
    reference = float(orchestrator_config.allocation_config.volatility_reference_atr_ratio)
    return _round_value(_clamp01(reference / max(atr_ratio, 1e-9)))


def _candidate_from_result(
    symbol: str,
    bars: Sequence[OHLCVBar],
    result: PRDV3MasterOrchestratorResult,
    orchestrator_config: PRDV3MasterOrchestratorConfig,
) -> _PortfolioCandidate | None:
    if result.selected_edge_id is None or result.selected_edge_state is None:
        return None
    if result.selected_edge_state.status not in {"ACTIVE", "WARNING"}:
        return None
    if result.allocation.approved is not True:
        return None
    if float(result.allocation.exposure_amount) <= 0.0:
        return None

    evaluation = _selected_evaluation(result)
    if evaluation is None:
        return None
    if evaluation.validation_result.valid is not True or evaluation.robustness_result.valid is not True:
        return None

    positive_window_ratio = float(evaluation.robustness_result.metrics.get("walk_forward_positive_test_window_ratio", 0.0))
    overfit_gap = float(evaluation.robustness_result.metrics.get("walk_forward_avg_expectancy_gap", 0.0))
    drawdown = float(evaluation.validation_result.metrics.get("max_drawdown", 0.0))
    score = _selected_score(result)
    proposed_allocation_pct = _round_value(float(result.allocation.position_size_pct) / 100.0)
    volatility_factor = _volatility_factor(bars, orchestrator_config)
    if score <= 0.0 or proposed_allocation_pct <= 0.0 or volatility_factor <= 0.0:
        return None

    drawdown_reference = float(orchestrator_config.allocation_config.max_drawdown_reference)
    drawdown_factor = _round_value(_clamp01(1.0 / (1.0 + (max(drawdown, 0.0) / drawdown_reference))))
    robustness = _robustness_strength(positive_window_ratio, overfit_gap)
    reason = (
        f"selected_edge_id={result.selected_edge_id}; edge_state={result.selected_edge_state.status};"
        f" edge_score={score:.6f}; robustness_strength={robustness:.6f};"
        f" max_drawdown={drawdown:.6f}; proposed_allocation_pct={proposed_allocation_pct:.6f}"
    )
    return _PortfolioCandidate(
        symbol=symbol,
        selected_edge_id=result.selected_edge_id,
        edge_state=result.selected_edge_state.status,
        edge_score=score,
        robustness_strength=robustness,
        drawdown=_round_value(drawdown),
        proposed_allocation_pct=proposed_allocation_pct,
        proposed_position_size=_round_value(float(result.allocation.exposure_amount)),
        proposed_risk=_round_value(float(result.allocation.risk_amount)),
        volatility_factor=volatility_factor,
        drawdown_factor=drawdown_factor,
        sector=get_sector(symbol),
        bars=tuple(bars),
        reason=reason,
    )


def _ranking_key(candidate: _PortfolioCandidate) -> tuple[float, float, float, str]:
    return (-candidate.edge_score, -candidate.robustness_strength, candidate.drawdown, candidate.symbol)


def _returns_signature(bars: Sequence[OHLCVBar], lookback: int) -> list[float]:
    closes = [float(bar.close) for bar in bars if float(bar.close) > 0.0]
    if len(closes) < 3:
        return []
    trailing = closes[-(lookback + 1) :]
    returns: list[float] = []
    for previous, current in zip(trailing, trailing[1:]):
        if previous <= 0.0:
            return []
        returns.append((current / previous) - 1.0)
    return returns


def _similar_trade_count(
    candidate: _PortfolioCandidate,
    accepted: Sequence[_PortfolioCandidate],
    correlation_engine: CorrelationEngine,
    config: PRDV3PortfolioEngineConfig,
) -> int:
    candidate_signature = _returns_signature(candidate.bars, config.correlation_lookback)
    if len(candidate_signature) < 2:
        return 0
    similar_count = 0
    for existing in accepted:
        existing_signature = _returns_signature(existing.bars, config.correlation_lookback)
        if len(existing_signature) < 2:
            continue
        correlation = correlation_engine.correlation(candidate_signature, existing_signature)
        if float(correlation) >= float(config.correlation_threshold):
            similar_count += 1
    return similar_count


def _weight(candidate: _PortfolioCandidate) -> float:
    return max(candidate.edge_score, 0.0) * max(candidate.volatility_factor, 0.0) * max(candidate.drawdown_factor, 0.0)


def _allocate_fractions(candidates: Sequence[_PortfolioCandidate], config: PRDV3PortfolioEngineConfig) -> tuple[dict[str, float], float]:
    caps = {
        candidate.symbol: min(float(config.max_per_trade_pct), float(candidate.proposed_allocation_pct))
        for candidate in candidates
    }
    weights = {candidate.symbol: _weight(candidate) for candidate in candidates}
    allocations = {candidate.symbol: 0.0 for candidate in candidates}
    active = [candidate.symbol for candidate in candidates if caps[candidate.symbol] > 0.0 and weights[candidate.symbol] > 0.0]
    remaining = float(config.max_total_exposure_pct)

    while active and remaining > 1e-12:
        total_weight = sum(weights[symbol] for symbol in active)
        if total_weight <= 0.0:
            break

        capped_any = False
        next_active: list[str] = []
        for symbol in active:
            proposed = remaining * (weights[symbol] / total_weight)
            room = caps[symbol] - allocations[symbol]
            if proposed >= room - 1e-12:
                allocations[symbol] += room
                remaining -= room
                capped_any = True
            else:
                next_active.append(symbol)

        if capped_any:
            active = next_active
            continue

        for symbol in active:
            proposed = remaining * (weights[symbol] / total_weight)
            allocations[symbol] += proposed
        remaining = 0.0

    return {symbol: _round_value(value) for symbol, value in allocations.items() if value > 0.0}, _round_value(remaining)


def run_prdv3_multi_symbol_portfolio_engine(
    edges: Sequence[EdgeDefinition],
    symbols: Sequence[str],
    symbol_data: Mapping[str, Sequence[OHLCVBar]],
    equity: float,
    config: PRDV3PortfolioEngineConfig | None = None,
) -> PRDV3PortfolioEngineResult:
    config = config or PRDV3PortfolioEngineConfig()
    config_error = _validate_config(config)
    logs: list[dict[str, Any]] = []
    if config_error is not None:
        logs.append({"event": "portfolio_blocked", "reason": config_error})
        return _empty_result(config_error, logs=logs)
    if not math.isfinite(float(equity)) or float(equity) <= 0.0:
        logs.append({"event": "portfolio_blocked", "reason": "invalid_current_equity"})
        return _empty_result("invalid_current_equity", logs=logs)

    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        logs.append({"event": "portfolio_blocked", "reason": "no_symbols"})
        return _empty_result("NO TRADE: no_symbols", logs=logs)

    normalized_data = _normalize_symbol_data(symbol_data)
    orchestrator_config = _portfolio_orchestrator_config(config)
    correlation_engine = CorrelationEngine()
    decisions: dict[str, PRDV3PortfolioDecision] = {}
    candidates: list[_PortfolioCandidate] = []
    rejected_symbols: list[str] = []

    for symbol in normalized_symbols:
        bars = normalized_data.get(symbol)
        if not bars:
            rejected_symbols.append(symbol)
            decisions[symbol] = PRDV3PortfolioDecision(
                symbol=symbol,
                approved=False,
                selected_edge_id=None,
                edge_state=None,
                edge_score=0.0,
                robustness_strength=0.0,
                allocation_pct=0.0,
                position_size=0.0,
                risk=0.0,
                reason="missing_symbol_data",
            )
            logs.append({"event": "symbol_skipped", "symbol": symbol, "reason": "missing_symbol_data"})
            continue

        result = run_prdv3_master_orchestrator(edges, bars, float(equity), orchestrator_config)
        candidate = _candidate_from_result(symbol, bars, result, orchestrator_config)
        if candidate is None:
            rejected_symbols.append(symbol)
            decisions[symbol] = PRDV3PortfolioDecision(
                symbol=symbol,
                approved=False,
                selected_edge_id=result.selected_edge_id,
                edge_state=None if result.selected_edge_state is None else result.selected_edge_state.status,
                edge_score=_selected_score(result),
                robustness_strength=0.0,
                allocation_pct=0.0,
                position_size=0.0,
                risk=0.0,
                reason=result.reason,
            )
            logs.append({"event": "symbol_rejected", "symbol": symbol, "reason": result.reason})
            continue

        candidates.append(candidate)
        logs.append(
            {
                "event": "symbol_candidate_ready",
                "symbol": symbol,
                "edge": candidate.selected_edge_id,
                "edge_state": candidate.edge_state,
                "edge_score": candidate.edge_score,
                "robustness_strength": candidate.robustness_strength,
            }
        )

    ranked_candidates = tuple(sorted(candidates, key=_ranking_key))
    selected_candidates: list[_PortfolioCandidate] = []
    sector_counts: dict[str, int] = {}

    for candidate in ranked_candidates:
        if len(selected_candidates) >= int(config.max_concurrent_positions):
            rejected_symbols.append(candidate.symbol)
            decisions[candidate.symbol] = PRDV3PortfolioDecision(
                symbol=candidate.symbol,
                approved=False,
                selected_edge_id=candidate.selected_edge_id,
                edge_state=candidate.edge_state,
                edge_score=candidate.edge_score,
                robustness_strength=candidate.robustness_strength,
                allocation_pct=0.0,
                position_size=0.0,
                risk=0.0,
                reason="max_concurrent_positions",
            )
            logs.append({"event": "symbol_rejected", "symbol": candidate.symbol, "reason": "max_concurrent_positions"})
            continue

        if candidate.sector != "other" and sector_counts.get(candidate.sector, 0) >= int(config.max_sector_positions):
            rejected_symbols.append(candidate.symbol)
            decisions[candidate.symbol] = PRDV3PortfolioDecision(
                symbol=candidate.symbol,
                approved=False,
                selected_edge_id=candidate.selected_edge_id,
                edge_state=candidate.edge_state,
                edge_score=candidate.edge_score,
                robustness_strength=candidate.robustness_strength,
                allocation_pct=0.0,
                position_size=0.0,
                risk=0.0,
                reason="sector_cluster",
            )
            logs.append({"event": "symbol_rejected", "symbol": candidate.symbol, "reason": "sector_cluster", "sector": candidate.sector})
            continue

        similar_trade_count = _similar_trade_count(candidate, selected_candidates, correlation_engine, config)
        if similar_trade_count >= int(config.max_similar_trades):
            rejected_symbols.append(candidate.symbol)
            decisions[candidate.symbol] = PRDV3PortfolioDecision(
                symbol=candidate.symbol,
                approved=False,
                selected_edge_id=candidate.selected_edge_id,
                edge_state=candidate.edge_state,
                edge_score=candidate.edge_score,
                robustness_strength=candidate.robustness_strength,
                allocation_pct=0.0,
                position_size=0.0,
                risk=0.0,
                reason="correlation_cluster",
            )
            logs.append({"event": "symbol_rejected", "symbol": candidate.symbol, "reason": "correlation_cluster", "similar_trade_count": similar_trade_count})
            continue

        selected_candidates.append(candidate)
        if candidate.sector != "other":
            sector_counts[candidate.sector] = sector_counts.get(candidate.sector, 0) + 1

    if not selected_candidates:
        logs.append({"event": "portfolio_blocked", "reason": "no_valid_trades"})
        for candidate in ranked_candidates:
            decisions.setdefault(
                candidate.symbol,
                PRDV3PortfolioDecision(
                    symbol=candidate.symbol,
                    approved=False,
                    selected_edge_id=candidate.selected_edge_id,
                    edge_state=candidate.edge_state,
                    edge_score=candidate.edge_score,
                    robustness_strength=candidate.robustness_strength,
                    allocation_pct=0.0,
                    position_size=0.0,
                    risk=0.0,
                    reason="no_valid_trades",
                ),
            )
        empty = _empty_result("NO TRADE: no_valid_trades", logs=logs, rejected_symbols=rejected_symbols)
        return PRDV3PortfolioEngineResult(
            valid=False,
            portfolio_decisions=tuple(decisions[symbol] for symbol in sorted(decisions)),
            total_exposure=0.0,
            risk_report=empty.risk_report,
            trade_plan=(),
            reason="NO TRADE: no_valid_trades",
        )

    allocation_map, remaining_exposure_pct = _allocate_fractions(selected_candidates, config)
    trade_plan_entries: list[PRDV3PortfolioTradePlanEntry] = []
    allocation_pct_by_symbol: dict[str, float] = {}
    risk_amount_by_symbol: dict[str, float] = {}
    edge_state_by_symbol: dict[str, str] = {}
    sector_by_symbol: dict[str, str] = {}

    for candidate in selected_candidates:
        allocation_pct = float(allocation_map.get(candidate.symbol, 0.0))
        if allocation_pct <= 0.0:
            rejected_symbols.append(candidate.symbol)
            decisions[candidate.symbol] = PRDV3PortfolioDecision(
                symbol=candidate.symbol,
                approved=False,
                selected_edge_id=candidate.selected_edge_id,
                edge_state=candidate.edge_state,
                edge_score=candidate.edge_score,
                robustness_strength=candidate.robustness_strength,
                allocation_pct=0.0,
                position_size=0.0,
                risk=0.0,
                reason="portfolio_exposure_exhausted",
            )
            logs.append({"event": "symbol_rejected", "symbol": candidate.symbol, "reason": "portfolio_exposure_exhausted"})
            continue

        scale = allocation_pct / max(candidate.proposed_allocation_pct, 1e-9)
        position_size = _round_value(float(equity) * allocation_pct)
        risk_amount = _round_value(candidate.proposed_risk * scale)
        reason = (
            f"ranked_portfolio_trade; {candidate.reason}; final_allocation_pct={allocation_pct:.6f};"
            f" volatility_factor={candidate.volatility_factor:.6f}; drawdown_factor={candidate.drawdown_factor:.6f}"
        )
        decisions[candidate.symbol] = PRDV3PortfolioDecision(
            symbol=candidate.symbol,
            approved=True,
            selected_edge_id=candidate.selected_edge_id,
            edge_state=candidate.edge_state,
            edge_score=candidate.edge_score,
            robustness_strength=candidate.robustness_strength,
            allocation_pct=_round_value(allocation_pct),
            position_size=position_size,
            risk=risk_amount,
            reason=reason,
        )
        trade_plan_entries.append(
            PRDV3PortfolioTradePlanEntry(
                symbol=candidate.symbol,
                edge=candidate.selected_edge_id,
                allocation_pct=_round_value(allocation_pct),
                position_size=position_size,
                risk=risk_amount,
                reason=reason,
            )
        )
        allocation_pct_by_symbol[candidate.symbol] = _round_value(allocation_pct)
        risk_amount_by_symbol[candidate.symbol] = risk_amount
        edge_state_by_symbol[candidate.symbol] = candidate.edge_state
        sector_by_symbol[candidate.symbol] = candidate.sector
        logs.append({"event": "trade_planned", "symbol": candidate.symbol, "edge": candidate.selected_edge_id, "allocation_pct": _round_value(allocation_pct)})

    total_exposure = _round_value(sum(entry.allocation_pct for entry in trade_plan_entries))
    remaining_cash = _round_value(float(equity) * max(remaining_exposure_pct, 0.0) + float(equity) * max(1.0 - float(config.max_total_exposure_pct), 0.0))
    risk_report = PRDV3PortfolioRiskReport(
        total_trades=len(trade_plan_entries),
        total_exposure=total_exposure,
        remaining_cash=remaining_cash,
        risk_distribution={
            "allocation_pct_by_symbol": allocation_pct_by_symbol,
            "risk_amount_by_symbol": risk_amount_by_symbol,
            "edge_state_by_symbol": edge_state_by_symbol,
            "sector_by_symbol": sector_by_symbol,
        },
        rejected_symbols=tuple(sorted(set(rejected_symbols))),
        logs=tuple(logs),
    )

    if not trade_plan_entries:
        return PRDV3PortfolioEngineResult(
            valid=False,
            portfolio_decisions=tuple(decisions[symbol] for symbol in sorted(decisions)),
            total_exposure=0.0,
            risk_report=risk_report,
            trade_plan=(),
            reason="NO TRADE: no_valid_trades",
        )

    return PRDV3PortfolioEngineResult(
        valid=True,
        portfolio_decisions=tuple(decisions[symbol] for symbol in sorted(decisions)),
        total_exposure=total_exposure,
        risk_report=risk_report,
        trade_plan=tuple(trade_plan_entries),
        reason="portfolio_allocated",
    )


__all__ = [
    "PRDV3PortfolioDecision",
    "PRDV3PortfolioEngineConfig",
    "PRDV3PortfolioEngineResult",
    "PRDV3PortfolioRiskReport",
    "PRDV3PortfolioTradePlanEntry",
    "run_prdv3_multi_symbol_portfolio_engine",
]
