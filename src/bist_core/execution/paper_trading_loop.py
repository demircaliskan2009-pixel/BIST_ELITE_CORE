"""Paper trading loop — PRD Phase E orchestration.

Runs a deterministic cycle: scan → risk check → execute → log.
Pure stdlib, no network.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.brain.ranking_engine import RankedSignal, RankingEngine
from bist_core.brain.scanner_engine import ScannerEngine
from bist_core.brain.strategy_engine import StrategyEngine
from bist_core.execution.paper_engine import PaperExecutionEngine, SlippageModel
from bist_core.ops.ops_logger import OpsLogger
from bist_core.risk.trade_risk_engine import RiskGateResult, RiskProfile, TradeRiskGate


class PaperTradingLoop:
    """Deterministic paper trading cycle: scan → risk → execute → log."""

    def __init__(
        self,
        strategy_engine: StrategyEngine | None = None,
        scanner_engine: ScannerEngine | None = None,
        ranking_engine: RankingEngine | None = None,
        risk_gate: TradeRiskGate | None = None,
        execution_engine: PaperExecutionEngine | None = None,
        ops_logger: OpsLogger | None = None,
    ) -> None:
        self._ranking = ranking_engine or RankingEngine()
        self._strategy = strategy_engine or StrategyEngine()
        self._scanner = scanner_engine or ScannerEngine(
            strategy_engine=self._strategy,
            ranking_engine=self._ranking,
        )
        self._risk = risk_gate or TradeRiskGate(RiskProfile())
        self._engine = execution_engine or PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=5.0),
            fee_bps=10.0,
        )
        self._logger = ops_logger

    def run_cycle(
        self,
        symbol_dataset: Dict[str, Sequence[OHLCVBar]],
    ) -> Dict[str, Any]:
        scan_result = self._scanner.scan(symbol_dataset)
        signals = scan_result.signals

        approved: list[tuple[RankedSignal, RiskGateResult]] = []
        rejected: list[RiskGateResult] = []

        for sig in signals:
            decision_dict = sig.to_dict()
            result = self._risk.evaluate(decision_dict)
            if result.approved:
                approved.append((sig, result))
            else:
                rejected.append(result)
                if self._logger is not None:
                    self._logger.log_risk_rejection(
                        symbol=sig.symbol,
                        reason=result.reason,
                        violations=result.violations,
                    )

        executed: list[Dict[str, Any]] = []

        for sig, risk_result in approved:
            size = risk_result.position_size if risk_result.position_size > 0 else 10
            market_price = sig.entry

            trade = self._engine.execute_decision(
                symbol=sig.symbol,
                entry=sig.entry,
                stop=sig.stop,
                target=sig.target,
                position_size=size,
                market_price=market_price,
                entry_time=str(sig.timestamp),
            )

            if trade is not None:
                executed.append(trade.to_dict())
                if self._logger is not None:
                    self._logger.log_order(
                        order_id=trade.trade_id,
                        symbol=trade.symbol,
                        order_type="MARKET",
                        size=trade.position_size,
                        entry=trade.entry_price,
                        status="FILLED",
                    )

        if self._logger is not None:
            for sig in signals:
                self._logger.log_decision(
                    symbol=sig.symbol,
                    entry=sig.entry,
                    stop=sig.stop,
                    target=sig.target,
                    timestamp=str(sig.timestamp),
                    reasoning=sig.reasoning,
                )

        return {
            "signals": len(signals),
            "approved": len(approved),
            "rejected": len(rejected),
            "executed": len(executed),
        }
