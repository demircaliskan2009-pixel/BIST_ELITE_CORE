"""Phase 6A: Deterministic paper execution realism — comprehensive tests.

Coverage:
  - BookContext validation (is_valid, is_crossed, spread_bps, mid_price)
  - FillPricer: BUY fills from ask side
  - FillPricer: SELL fills from bid side
  - FillPricer: spread-aware pricing
  - FillPricer: slippage increases with size
  - FillPricer: insufficient liquidity rejection
  - FillPricer: excessive spread rejection
  - FillPricer: invalid / crossed book rejection
  - FillPricer: deterministic replay equivalence
  - ExecutionEngine PAPER mode with book
  - ExecutionEngine PAPER mode without book (degraded)
  - ExecutionEngine rejection paths (book_invalid, book_crossed, excessive_spread,
    excessive_slippage, insufficient_liquidity)
  - SyntheticFillFactory: from approved decision
  - SyntheticFillFactory: rejected decision raises ValueError
  - SyntheticFillFactory: fill_price sourcing (realistic vs price_hint fallback)
  - Integration: approved signal → execution → SyntheticFill → PositionTracker
  - Integration: rejected execution → no portfolio mutation
  - Integration: deterministic replay end-to-end
  - Telemetry evidence fields populated correctly
"""

from __future__ import annotations

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.fill_pricer import FillPricer, FillPricerConfig
from crypto_core.execution.models import (
    BookContext,
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    OrderIntent,
    RejectionReason,
    SlippageResult,
)
from crypto_core.guard.models import NoTradeDecision
from crypto_core.portfolio.fills import SyntheticFill, SyntheticFillFactory
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000

# Typical BTC book
_BID = 49_900.0
_ASK = 50_100.0
_MID = 50_000.0
_SPREAD_BPS = (_ASK - _BID) / _MID * 10_000.0  # 40 bps

_DEFAULT_DEPTH = 1.0  # 1 BTC visible on each side


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _book(
    bid: float = _BID,
    ask: float = _ASK,
    bid_size: float | None = _DEFAULT_DEPTH,
    ask_size: float | None = _DEFAULT_DEPTH,
    bid_level_count: int = 5,
    ask_level_count: int = 5,
) -> BookContext:
    return BookContext(
        bid_price=bid,
        ask_price=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        bid_level_count=bid_level_count,
        ask_level_count=ask_level_count,
    )


def _approved_risk(system_state: SystemState = SystemState.NORMAL) -> RiskEvaluation:
    edge = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=_T0_NS,
        is_valid=True,
        block_reason=None,
    )
    return RiskEvaluation(
        decision=RiskDecision.APPROVED,
        block_reason=None,
        system_state=system_state,
        edge_signal=edge,
        no_trade_decision=NoTradeDecision.allow(),
        evidence={},
        timestamp_ns=_T0_NS,
    )


def _request(
    intent: OrderIntent = OrderIntent.BUY,
    size: float = 0.01,
    book: BookContext | None = _book(),
    symbol: str = "BTCUSDT",
) -> ExecutionRequest:
    return ExecutionRequest(
        symbol=symbol,
        exchange="binance",
        intent=intent,
        size=size,
        price_hint=_MID,
        risk_evaluation=_approved_risk(),
        timestamp_ns=_T0_NS,
        book=book,
    )


def _paper_engine(pricer_cfg: FillPricerConfig | None = None) -> ExecutionEngine:
    cfg = ExecutionConfig(
        mode=ExecutionMode.PAPER,
        supported_symbols=frozenset({"BTCUSDT", "ETHUSDT"}),
        fill_pricer=pricer_cfg,
    )
    return ExecutionEngine(cfg)


# ---------------------------------------------------------------------------
# 1. BookContext validation
# ---------------------------------------------------------------------------


class TestBookContext:
    def test_valid_book(self) -> None:
        b = _book()
        assert b.is_valid is True
        assert b.is_crossed is False

    def test_mid_price(self) -> None:
        b = _book(bid=49_900.0, ask=50_100.0)
        assert b.mid_price == pytest.approx(50_000.0)

    def test_spread_bps(self) -> None:
        b = _book(bid=49_900.0, ask=50_100.0)
        # spread = 200 USD, mid = 50000 → 40 bps
        assert b.spread_bps == pytest.approx(40.0, rel=1e-4)

    def test_crossed_book_detected(self) -> None:
        b = BookContext(bid_price=50_100.0, ask_price=50_000.0)
        assert b.is_valid is False
        assert b.is_crossed is True

    def test_locked_book_detected(self) -> None:
        # ask == bid → locked
        b = BookContext(bid_price=50_000.0, ask_price=50_000.0)
        assert b.is_valid is False
        assert b.is_crossed is True

    def test_negative_bid_invalid(self) -> None:
        b = BookContext(bid_price=-1.0, ask_price=50_000.0)
        assert b.is_valid is False

    def test_zero_bid_invalid(self) -> None:
        b = BookContext(bid_price=0.0, ask_price=50_000.0)
        assert b.is_valid is False

    def test_spread_bps_zero_mid_returns_inf(self) -> None:
        # Edge case: both prices zero
        b = BookContext(bid_price=0.0, ask_price=0.0)
        assert b.spread_bps == float("inf")

    def test_frozen(self) -> None:
        b = _book()
        with pytest.raises((AttributeError, TypeError)):
            b.bid_price = 1.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. FillPricer — BUY fills from ask side
# ---------------------------------------------------------------------------


class TestFillPricerBuy:
    def test_buy_fill_above_mid(self) -> None:
        pricer = FillPricer()
        result = pricer.price_fill(OrderIntent.BUY, 0.01, _book())
        assert isinstance(result, SlippageResult)
        # BUY fill must be > mid (paying half-spread + impact)
        assert result.fill_price > _MID

    def test_buy_fill_at_or_above_ask(self) -> None:
        # Without depth, only half-spread applied; with tiny size: near ask
        pricer = FillPricer()
        b = _book(bid_size=None, ask_size=None)  # no depth = no impact
        result = pricer.price_fill(OrderIntent.BUY, 0.0001, b)
        assert isinstance(result, SlippageResult)
        # fill_price should be ≈ mid + half_spread = mid * (1 + 20bps/10000)
        expected = _MID * (1.0 + 20.0 / 10_000.0)
        assert result.fill_price == pytest.approx(expected, rel=1e-6)

    def test_buy_uses_ask_size_for_participation(self) -> None:
        # ask_size=0.1 BTC, size=0.01 BTC → participation=10%
        b = _book(ask_size=0.1, bid_size=5.0)
        pricer = FillPricer(FillPricerConfig(max_participation_pct=15.0))
        result = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        assert isinstance(result, SlippageResult)
        assert result.participation_pct == pytest.approx(10.0, rel=1e-6)

    def test_buy_fill_evidence_contains_required_fields(self) -> None:
        pricer = FillPricer()
        result = pricer.price_fill(OrderIntent.BUY, 0.01, _book())
        assert isinstance(result, SlippageResult)
        ev = result.evidence
        assert "bid_price" in ev
        assert "ask_price" in ev
        assert "mid_price" in ev
        assert "fill_price" in ev
        assert "spread_bps" in ev
        assert "fill_cost_bps" in ev


# ---------------------------------------------------------------------------
# 3. FillPricer — SELL fills from bid side
# ---------------------------------------------------------------------------


class TestFillPricerSell:
    def test_sell_fill_below_mid(self) -> None:
        pricer = FillPricer()
        result = pricer.price_fill(OrderIntent.SELL, 0.01, _book())
        assert isinstance(result, SlippageResult)
        assert result.fill_price < _MID

    def test_sell_fill_at_or_below_bid(self) -> None:
        b = _book(bid_size=None, ask_size=None)  # no depth = no impact
        pricer = FillPricer()
        result = pricer.price_fill(OrderIntent.SELL, 0.0001, b)
        assert isinstance(result, SlippageResult)
        # fill_price ≈ mid - half_spread = mid * (1 - 20bps/10000)
        expected = _MID * (1.0 - 20.0 / 10_000.0)
        assert result.fill_price == pytest.approx(expected, rel=1e-6)

    def test_sell_uses_bid_size_for_participation(self) -> None:
        b = _book(bid_size=0.2, ask_size=5.0)
        pricer = FillPricer(FillPricerConfig(max_participation_pct=15.0))
        result = pricer.price_fill(OrderIntent.SELL, 0.01, b)
        assert isinstance(result, SlippageResult)
        # participation = 0.01 / 0.2 * 100 = 5.0%
        assert result.participation_pct == pytest.approx(5.0, rel=1e-6)

    def test_sell_symmetry_with_buy_no_depth(self) -> None:
        """BUY and SELL have symmetric cost from mid when no depth available."""
        b = _book(bid_size=None, ask_size=None)
        pricer = FillPricer()
        buy_r = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        sell_r = pricer.price_fill(OrderIntent.SELL, 0.01, b)
        assert isinstance(buy_r, SlippageResult)
        assert isinstance(sell_r, SlippageResult)
        # Both should have same slippage_bps (symmetric cost)
        assert buy_r.slippage_bps == pytest.approx(sell_r.slippage_bps, rel=1e-9)
        # fill_price symmetric around mid
        assert buy_r.fill_price - _MID == pytest.approx(_MID - sell_r.fill_price, rel=1e-6)


# ---------------------------------------------------------------------------
# 4. Slippage model — spread-aware, size-sensitive, bounded
# ---------------------------------------------------------------------------


class TestSlippageModel:
    def test_zero_depth_yields_zero_impact(self) -> None:
        pricer = FillPricer()
        b = _book(bid_size=None, ask_size=None)
        result = pricer.price_fill(OrderIntent.BUY, 1.0, b)
        assert isinstance(result, SlippageResult)
        assert result.slippage_component_bps == pytest.approx(0.0)
        assert result.participation_pct is None

    def test_impact_increases_with_size(self) -> None:
        """Larger size → higher participation → higher slippage bps."""
        b = _book(ask_size=1.0)  # 1 BTC on ask
        pricer = FillPricer(FillPricerConfig(max_participation_pct=50.0))
        small = pricer.price_fill(OrderIntent.BUY, 0.1, b)
        large = pricer.price_fill(OrderIntent.BUY, 0.5, b)
        assert isinstance(small, SlippageResult)
        assert isinstance(large, SlippageResult)
        assert large.slippage_component_bps > small.slippage_component_bps

    def test_fill_price_monotone_with_size_buy(self) -> None:
        """Bigger BUY pays more — fill_price increases with size."""
        b = _book(ask_size=2.0)
        pricer = FillPricer(FillPricerConfig(max_participation_pct=60.0))
        r1 = pricer.price_fill(OrderIntent.BUY, 0.1, b)
        r2 = pricer.price_fill(OrderIntent.BUY, 1.0, b)
        assert isinstance(r1, SlippageResult)
        assert isinstance(r2, SlippageResult)
        assert r2.fill_price > r1.fill_price

    def test_fill_price_monotone_with_size_sell(self) -> None:
        """Bigger SELL gets worse price — fill_price decreases with size."""
        b = _book(bid_size=2.0)
        pricer = FillPricer(FillPricerConfig(max_participation_pct=60.0))
        r1 = pricer.price_fill(OrderIntent.SELL, 0.1, b)
        r2 = pricer.price_fill(OrderIntent.SELL, 1.0, b)
        assert isinstance(r1, SlippageResult)
        assert isinstance(r2, SlippageResult)
        assert r2.fill_price < r1.fill_price

    def test_spread_component_is_half_spread(self) -> None:
        pricer = FillPricer()
        result = pricer.price_fill(OrderIntent.BUY, 0.001, _book(bid_size=None, ask_size=None))
        assert isinstance(result, SlippageResult)
        assert result.spread_component_bps == pytest.approx(_SPREAD_BPS / 2.0, rel=1e-6)

    def test_total_slippage_bps_equals_half_spread_plus_impact(self) -> None:
        b = _book(ask_size=1.0)
        pricer = FillPricer(FillPricerConfig(size_impact_coefficient=1.0))
        result = pricer.price_fill(OrderIntent.BUY, 0.1, b)  # 10% participation
        assert isinstance(result, SlippageResult)
        # impact_bps = 1.0 * 10.0 = 10.0
        # slippage_bps = half_spread + 10.0
        expected = _SPREAD_BPS / 2.0 + 10.0
        assert result.slippage_bps == pytest.approx(expected, rel=1e-6)

    def test_deterministic_replay(self) -> None:
        b = _book()
        pricer = FillPricer()
        r1 = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        r2 = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        assert isinstance(r1, SlippageResult)
        assert isinstance(r2, SlippageResult)
        assert r1.fill_price == r2.fill_price
        assert r1.slippage_bps == r2.slippage_bps


# ---------------------------------------------------------------------------
# 5. FillPricer rejection paths
# ---------------------------------------------------------------------------


class TestFillPricerRejections:
    def test_invalid_book_zero_bid(self) -> None:
        pricer = FillPricer()
        b = BookContext(bid_price=0.0, ask_price=50_000.0)
        result = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        assert result == RejectionReason.BOOK_INVALID

    def test_invalid_book_negative_ask(self) -> None:
        pricer = FillPricer()
        b = BookContext(bid_price=49_900.0, ask_price=-1.0)
        result = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        assert result == RejectionReason.BOOK_INVALID

    def test_crossed_book_rejected(self) -> None:
        pricer = FillPricer()
        b = BookContext(bid_price=50_100.0, ask_price=50_000.0)
        result = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        assert result == RejectionReason.BOOK_CROSSED

    def test_locked_book_rejected(self) -> None:
        pricer = FillPricer()
        b = BookContext(bid_price=50_000.0, ask_price=50_000.0)
        result = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        assert result == RejectionReason.BOOK_CROSSED

    def test_excessive_spread_rejected(self) -> None:
        pricer = FillPricer(FillPricerConfig(max_spread_bps=10.0))
        # spread = 40 bps > 10 bps limit
        result = pricer.price_fill(OrderIntent.BUY, 0.01, _book())
        assert result == RejectionReason.EXCESSIVE_SPREAD

    def test_insufficient_liquidity_rejected(self) -> None:
        pricer = FillPricer(FillPricerConfig(max_participation_pct=5.0))
        # ask_size=0.1 BTC, size=0.01 BTC → participation=10% > 5% limit
        b = _book(ask_size=0.1, bid_size=5.0)
        result = pricer.price_fill(OrderIntent.BUY, 0.01, b)
        assert result == RejectionReason.INSUFFICIENT_LIQUIDITY

    def test_insufficient_liquidity_sell_rejected(self) -> None:
        pricer = FillPricer(FillPricerConfig(max_participation_pct=5.0))
        b = _book(bid_size=0.1, ask_size=5.0)
        result = pricer.price_fill(OrderIntent.SELL, 0.01, b)
        assert result == RejectionReason.INSUFFICIENT_LIQUIDITY

    def test_excessive_slippage_rejected(self) -> None:
        # Force high slippage by making participation very high
        # Ask_size=0.1 BTC, size=0.05 → 50% participation
        # impact_bps = 0.5 * 50.0 = 25.0; slippage = 20 + 25 = 45 bps > 30 limit
        pricer = FillPricer(
            FillPricerConfig(
                max_slippage_bps=30.0,
                max_participation_pct=60.0,
                size_impact_coefficient=0.5,
            )
        )
        b = _book(ask_size=0.1, bid_size=5.0)
        result = pricer.price_fill(OrderIntent.BUY, 0.05, b)
        assert result == RejectionReason.EXCESSIVE_SLIPPAGE

    def test_no_depth_no_participation_rejection(self) -> None:
        """If depth unavailable, participation gate is skipped (can't enforce it)."""
        pricer = FillPricer(FillPricerConfig(max_participation_pct=0.001))
        b = _book(bid_size=None, ask_size=None)
        # Even with tiny participation limit, no depth → no rejection
        result = pricer.price_fill(OrderIntent.BUY, 9999.0, b)
        # Might hit slippage limit, but NOT insufficient_liquidity
        assert result != RejectionReason.INSUFFICIENT_LIQUIDITY


# ---------------------------------------------------------------------------
# 6. ExecutionEngine — PAPER mode with book
# ---------------------------------------------------------------------------


class TestExecutionEnginePaperWithBook:
    def test_paper_buy_fill_uses_realistic_price(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request(intent=OrderIntent.BUY))
        assert dec.allowed is True
        assert dec.fill_price is not None
        assert dec.fill_price > _MID  # BUY pays above mid

    def test_paper_sell_fill_uses_realistic_price(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request(intent=OrderIntent.SELL))
        assert dec.allowed is True
        assert dec.fill_price is not None
        assert dec.fill_price < _MID  # SELL receives below mid

    def test_paper_decision_has_ref_prices(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert dec.ref_mid_price == pytest.approx(_MID)
        assert dec.ref_bid_price == pytest.approx(_BID)
        assert dec.ref_ask_price == pytest.approx(_ASK)

    def test_paper_decision_has_spread_bps(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert dec.spread_bps is not None
        assert dec.spread_bps == pytest.approx(_SPREAD_BPS, rel=1e-4)

    def test_paper_decision_has_slippage_bps(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert dec.slippage_bps is not None
        assert dec.slippage_bps > 0.0

    def test_paper_decision_has_order_id(self) -> None:
        import uuid

        engine = _paper_engine()
        dec = engine.execute(_request())
        assert dec.order_id is not None
        uuid.UUID(dec.order_id)

    def test_paper_mode_set_correctly(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert dec.mode == ExecutionMode.PAPER

    def test_paper_fill_evidence_contains_fill_mode(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert dec.evidence.get("fill_mode") == "paper_realistic"

    def test_paper_participation_populated_when_depth_available(self) -> None:
        engine = _paper_engine()
        # ask_size=1.0 BTC, size=0.1 → 10%
        dec = engine.execute(_request(size=0.1, book=_book(ask_size=1.0)))
        assert dec.allowed is True
        assert dec.participation_pct == pytest.approx(10.0, rel=1e-4)

    def test_paper_participation_none_when_no_depth(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request(book=_book(bid_size=None, ask_size=None)))
        assert dec.allowed is True
        assert dec.participation_pct is None


# ---------------------------------------------------------------------------
# 7. ExecutionEngine — PAPER mode without book (degraded)
# ---------------------------------------------------------------------------


class TestExecutionEnginePaperDegraded:
    def test_paper_no_book_allowed_by_default(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request(book=None))
        # Default: require_book_for_paper=False → degraded mode
        assert dec.allowed is True

    def test_paper_no_book_uses_price_hint(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request(book=None))
        # fill_price falls back to price_hint = 50_000.0
        assert dec.fill_price == pytest.approx(_MID)

    def test_paper_no_book_degraded_evidence(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request(book=None))
        assert dec.evidence.get("fill_mode") == "degraded_price_hint"

    def test_paper_no_book_no_spread_bps(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request(book=None))
        # No book → no spread data
        assert dec.spread_bps is None
        assert dec.slippage_bps is None

    def test_paper_require_book_rejects_none_book(self) -> None:
        cfg = FillPricerConfig(require_book_for_paper=True)
        engine = _paper_engine(pricer_cfg=cfg)
        dec = engine.execute(_request(book=None))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.BOOK_UNAVAILABLE


# ---------------------------------------------------------------------------
# 8. ExecutionEngine — PAPER mode book rejection paths
# ---------------------------------------------------------------------------


class TestExecutionEnginePaperRejections:
    def test_invalid_book_rejected(self) -> None:
        engine = _paper_engine()
        b = BookContext(bid_price=0.0, ask_price=50_000.0)
        dec = engine.execute(_request(book=b))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.BOOK_INVALID

    def test_crossed_book_rejected(self) -> None:
        engine = _paper_engine()
        b = BookContext(bid_price=50_100.0, ask_price=50_000.0)
        dec = engine.execute(_request(book=b))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.BOOK_CROSSED

    def test_excessive_spread_rejected(self) -> None:
        cfg = FillPricerConfig(max_spread_bps=10.0)
        engine = _paper_engine(pricer_cfg=cfg)
        dec = engine.execute(_request())  # spread = 40 bps > 10 limit
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.EXCESSIVE_SPREAD

    def test_insufficient_liquidity_rejected(self) -> None:
        cfg = FillPricerConfig(max_participation_pct=1.0)
        engine = _paper_engine(pricer_cfg=cfg)
        # ask_size=0.1 BTC, size=0.01 → 10% > 1% limit
        b = _book(ask_size=0.1)
        dec = engine.execute(_request(size=0.01, book=b))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.INSUFFICIENT_LIQUIDITY

    def test_excessive_slippage_rejected(self) -> None:
        cfg = FillPricerConfig(
            max_slippage_bps=5.0,  # very tight: 5 bps limit; spread already ~40 bps
        )
        engine = _paper_engine(pricer_cfg=cfg)
        dec = engine.execute(_request())
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.EXCESSIVE_SLIPPAGE

    def test_rejection_has_no_fill_price(self) -> None:
        cfg = FillPricerConfig(max_spread_bps=5.0)
        engine = _paper_engine(pricer_cfg=cfg)
        dec = engine.execute(_request())
        assert dec.allowed is False
        assert dec.fill_price is None

    def test_rejection_has_no_order_id(self) -> None:
        cfg = FillPricerConfig(max_spread_bps=5.0)
        engine = _paper_engine(pricer_cfg=cfg)
        dec = engine.execute(_request())
        assert dec.order_id is None

    def test_rejection_evidence_contains_rejection_key(self) -> None:
        cfg = FillPricerConfig(max_spread_bps=5.0)
        engine = _paper_engine(pricer_cfg=cfg)
        dec = engine.execute(_request())
        assert "fill_pricing_rejection" in dec.evidence


# ---------------------------------------------------------------------------
# 9. SyntheticFillFactory
# ---------------------------------------------------------------------------


def _allowed_decision(
    fill_price: float | None = None,
    mode: ExecutionMode = ExecutionMode.PAPER,
) -> ExecutionDecision:
    return ExecutionDecision(
        allowed=True,
        rejection_reason=None,
        mode=mode,
        order_id="test-order-id",
        evidence={"order_id": "test-order-id"},
        timestamp_ns=_T0_NS,
        fill_price=fill_price,
    )


def _rejected_decision() -> ExecutionDecision:
    return ExecutionDecision(
        allowed=False,
        rejection_reason=RejectionReason.EXCESSIVE_SPREAD,
        mode=ExecutionMode.PAPER,
        order_id=None,
        evidence={},
        timestamp_ns=_T0_NS,
    )


class TestSyntheticFillFactory:
    def test_from_approved_decision_creates_fill(self) -> None:
        dec = _allowed_decision(fill_price=50_020.0)
        req = _request()
        fill = SyntheticFillFactory.from_decision(dec, req)
        assert isinstance(fill, SyntheticFill)

    def test_fill_uses_decision_fill_price(self) -> None:
        dec = _allowed_decision(fill_price=50_020.0)
        fill = SyntheticFillFactory.from_decision(dec, _request())
        assert fill.fill_price == pytest.approx(50_020.0)

    def test_fill_falls_back_to_price_hint_when_no_fill_price(self) -> None:
        dec = _allowed_decision(fill_price=None)
        fill = SyntheticFillFactory.from_decision(dec, _request())
        # fallback: price_hint = 50_000.0
        assert fill.fill_price == pytest.approx(_MID)

    def test_fill_symbol_from_request(self) -> None:
        fill = SyntheticFillFactory.from_decision(_allowed_decision(), _request(symbol="ETHUSDT"))
        assert fill.symbol == "ETHUSDT"

    def test_fill_intent_from_request(self) -> None:
        fill_buy = SyntheticFillFactory.from_decision(_allowed_decision(), _request(intent=OrderIntent.BUY))
        fill_sell = SyntheticFillFactory.from_decision(_allowed_decision(), _request(intent=OrderIntent.SELL))
        assert fill_buy.intent == OrderIntent.BUY
        assert fill_sell.intent == OrderIntent.SELL

    def test_fill_quantity_from_request(self) -> None:
        fill = SyntheticFillFactory.from_decision(_allowed_decision(), _request(size=0.123))
        assert fill.quantity == pytest.approx(0.123)

    def test_fill_order_id_from_decision(self) -> None:
        fill = SyntheticFillFactory.from_decision(_allowed_decision(), _request())
        assert fill.order_id == "test-order-id"

    def test_fill_mode_from_decision(self) -> None:
        fill = SyntheticFillFactory.from_decision(_allowed_decision(mode=ExecutionMode.DRY_RUN), _request())
        assert fill.mode == ExecutionMode.DRY_RUN

    def test_rejected_decision_raises(self) -> None:
        with pytest.raises(ValueError, match="rejected"):
            SyntheticFillFactory.from_decision(_rejected_decision(), _request())

    def test_leverage_default_is_one(self) -> None:
        fill = SyntheticFillFactory.from_decision(_allowed_decision(), _request())
        assert fill.leverage == pytest.approx(1.0)

    def test_leverage_custom(self) -> None:
        fill = SyntheticFillFactory.from_decision(_allowed_decision(), _request(), leverage=2.5)
        assert fill.leverage == pytest.approx(2.5)

    def test_leverage_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="leverage"):
            SyntheticFillFactory.from_decision(_allowed_decision(), _request(), leverage=3.1)

    def test_leverage_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="leverage"):
            SyntheticFillFactory.from_decision(_allowed_decision(), _request(), leverage=0.0)

    def test_fill_is_frozen(self) -> None:
        fill = SyntheticFillFactory.from_decision(_allowed_decision(), _request())
        with pytest.raises((AttributeError, TypeError)):
            fill.fill_price = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 10. Integration: execution approval → fill → portfolio update
# ---------------------------------------------------------------------------


class TestPortfolioIntegration:
    def test_approved_paper_fill_updates_position(self) -> None:
        engine = _paper_engine()
        tracker = PositionTracker(initial_nav_usd=100_000.0)
        req = _request(intent=OrderIntent.BUY, size=0.1)
        dec = engine.execute(req)
        assert dec.allowed is True

        fill = SyntheticFillFactory.from_decision(dec, req)
        tracker.apply_fill(fill)

        snap = tracker.portfolio_snapshot()
        assert snap.active_position_count == 1
        # Notional ≈ 0.1 BTC × fill_price
        assert snap.total_notional_usd == pytest.approx(0.1 * dec.fill_price, rel=1e-6)  # type: ignore[arg-type]

    def test_rejected_execution_produces_no_fill(self) -> None:
        cfg = FillPricerConfig(max_spread_bps=5.0)
        engine = _paper_engine(pricer_cfg=cfg)
        tracker = PositionTracker(initial_nav_usd=100_000.0)
        req = _request()
        dec = engine.execute(req)
        assert dec.allowed is False

        # Must not call SyntheticFillFactory — guard in test enforces this
        with pytest.raises(ValueError):
            SyntheticFillFactory.from_decision(dec, req)

        snap = tracker.portfolio_snapshot()
        assert snap.active_position_count == 0  # no mutation

    def test_buy_then_sell_closes_position(self) -> None:
        engine = _paper_engine()
        tracker = PositionTracker(initial_nav_usd=100_000.0)

        buy_req = _request(intent=OrderIntent.BUY, size=0.1)
        buy_dec = engine.execute(buy_req)
        assert buy_dec.allowed is True
        tracker.apply_fill(SyntheticFillFactory.from_decision(buy_dec, buy_req))

        sell_req = _request(intent=OrderIntent.SELL, size=0.1)
        sell_dec = engine.execute(sell_req)
        assert sell_dec.allowed is True
        tracker.apply_fill(SyntheticFillFactory.from_decision(sell_dec, sell_req))

        snap = tracker.portfolio_snapshot()
        assert snap.active_position_count == 0

    def test_full_pipeline_approved_to_fill(self) -> None:
        """Signal approval path: engine.execute → fill → tracker → snapshot."""
        engine = _paper_engine()
        tracker = PositionTracker(initial_nav_usd=50_000.0)

        req = _request(intent=OrderIntent.BUY, size=0.05)
        dec = engine.execute(req)
        assert dec.allowed is True
        assert dec.fill_price is not None

        fill = SyntheticFillFactory.from_decision(dec, req)
        assert fill.fill_price == dec.fill_price

        tracker.apply_fill(fill)
        snap = tracker.portfolio_snapshot()
        assert snap.active_position_count == 1
        assert snap.gross_exposure_pct > 0.0

    def test_deterministic_replay_end_to_end(self) -> None:
        """Identical inputs → identical execution decision and fill price."""
        engine1 = _paper_engine()
        engine2 = _paper_engine()
        req = _request(intent=OrderIntent.BUY, size=0.05)

        dec1 = engine1.execute(req)
        dec2 = engine2.execute(req)

        assert dec1.allowed == dec2.allowed
        assert dec1.fill_price == dec2.fill_price
        assert dec1.slippage_bps == dec2.slippage_bps
        assert dec1.spread_bps == dec2.spread_bps

    def test_identical_fills_produce_identical_portfolio_snapshot(self) -> None:
        engine1 = _paper_engine()
        engine2 = _paper_engine()
        req = _request(size=0.1)

        t1 = PositionTracker(initial_nav_usd=100_000.0)
        t2 = PositionTracker(initial_nav_usd=100_000.0)

        dec1 = engine1.execute(req)
        dec2 = engine2.execute(req)

        t1.apply_fill(SyntheticFillFactory.from_decision(dec1, req))
        t2.apply_fill(SyntheticFillFactory.from_decision(dec2, req))

        snap1 = t1.portfolio_snapshot(snapshot_ns=_T0_NS)
        snap2 = t2.portfolio_snapshot(snapshot_ns=_T0_NS)
        assert snap1.total_notional_usd == pytest.approx(snap2.total_notional_usd)


# ---------------------------------------------------------------------------
# 11. Telemetry evidence completeness
# ---------------------------------------------------------------------------


class TestTelemetryEvidence:
    def test_approved_paper_evidence_has_fill_mode(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert "fill_mode" in dec.evidence
        assert dec.evidence["fill_mode"] == "paper_realistic"

    def test_approved_paper_evidence_has_mid_price(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert "mid_price" in dec.evidence

    def test_approved_paper_evidence_has_spread_bps(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert "spread_bps" in dec.evidence

    def test_approved_paper_evidence_has_fill_cost_bps(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        assert "fill_cost_bps" in dec.evidence

    def test_approved_paper_evidence_fill_price_consistent(self) -> None:
        engine = _paper_engine()
        dec = engine.execute(_request())
        # evidence["fill_price"] should round to same value as dec.fill_price
        ev_fp = dec.evidence.get("fill_price")
        assert ev_fp is not None
        assert abs(float(ev_fp) - dec.fill_price) < 0.01  # type: ignore[arg-type]

    def test_rejected_evidence_has_fill_pricing_rejection(self) -> None:
        cfg = FillPricerConfig(max_spread_bps=5.0)
        engine = _paper_engine(pricer_cfg=cfg)
        dec = engine.execute(_request())
        assert dec.allowed is False
        assert "fill_pricing_rejection" in dec.evidence

    def test_dry_run_has_no_fill_price(self) -> None:
        cfg_e = ExecutionConfig(mode=ExecutionMode.DRY_RUN)
        engine = ExecutionEngine(cfg_e)
        dec = engine.execute(_request())
        assert dec.allowed is True
        assert dec.fill_price is None
        assert dec.spread_bps is None
