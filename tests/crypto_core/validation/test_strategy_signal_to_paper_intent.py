"""Tests for the strategy-signal-to-paper-intent bridge — deterministic, paper-only, fail-closed mapping from
a digest-bound ``StrategySpec`` + signal into the inert ``PaperOrderIntentRequest`` contract. Covers happy
path, spec-digest binding, signal-vs-spec consistency, fail-closed validation, determinism, forbidden-surface
exclusion (alias-resistant), non-overclaim, and the canonical serializer."""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.strategy.spec import (
    StrategySpec,
    StrategySpecMarketType,
    strategy_spec_digest,
    strategy_spec_to_dict,
    validate_strategy_spec,
)
from crypto_core.validation import strategy_signal_to_paper_intent as bridge_module
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    paper_order_intent_request_digest,
)
from crypto_core.validation.strategy_signal_to_paper_intent import (
    StrategySignalToPaperIntentError,
    StrategySignalToPaperIntentStatus,
    build_strategy_signal_to_paper_intent,
    strategy_signal_to_paper_intent_digest,
    strategy_signal_to_paper_intent_to_dict,
)

_HEX_CAP = "a" * 64
_HEX_BAD = "d" * 64


class _SneakyStr(str):
    """A ``str`` subclass that lies about being non-empty — must never pass the exact-plain-string gate."""

    def strip(self, *args, **kwargs):  # noqa: D401 - adversarial override
        return "definitely-not-empty"


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _spec() -> StrategySpec:
    """A genuine, validator-accepted StrategySpec whose instrument universe includes BTC-PERPETUAL."""
    payload = {
        "schema_version": "strategy-spec.v1",
        "strategy_id": "alpha-funding-carry",
        "strategy_version": "1.0.0",
        "strategy_family": "carry",
        "edge_family": "funding_basis_carry",
        "instrument_universe": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
        "market_type": "usdt_perp",
        "venue_assumptions": ["perp_linear"],
        "timeframe": "1h",
        "bar_definition": "time_1h",
        "entry_conditions": ["funding_positive"],
        "exit_conditions": ["funding_neutral"],
        "invalidation_conditions": ["regime_break"],
        "risk_caps": {"max_leverage": 2.0},
        "data_requirements": {"funding_rate": "1h"},
        "feature_requirements": {"funding_zscore": "rolling"},
        "latency_sensitivity": "low",
        "funding_sensitivity": "high",
        "fee_model_requirement": "taker_10bps",
        "slippage_model_requirement": "depth_aware",
        "expected_regime": "ranging",
        "failure_modes": ["funding_flip"],
        "kill_switch_triggers": ["max_dd"],
        "telemetry_fields": ["funding"],
        "promotion_requirements": ["walk_forward"],
    }
    result = validate_strategy_spec(payload)
    assert result.accepted, result.rejection_reasons + result.needs_research_reasons
    assert result.spec is not None
    return result.spec


def _build(spec: StrategySpec | None = None, **overrides):
    spec = spec if spec is not None else _spec()
    kwargs = {
        "expected_spec_digest": strategy_spec_digest(spec),
        "signal_id": "sig-1",
        "run_id": "run-1",
        "correlation_id": "corr-1",
        "market_symbol": "BTC-PERPETUAL",
        "side": PaperOrderSide.BUY,
        "intent_type": PaperOrderIntentType.MARKET,
        "requested_units": "10",
        "requested_notional": "100",
        "capacity_decision_digest": _HEX_CAP,
        "limit_price": None,
    }
    kwargs.update(overrides)
    return build_strategy_signal_to_paper_intent(spec, **kwargs)


# --------------------------------------------------------------------------------------------------
# 1. Happy path
# --------------------------------------------------------------------------------------------------


def test_valid_signal_is_ready_and_produces_request_digest():
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.READY
    assert bridge.ready is True
    assert bridge.rejection_reasons == ()
    assert bridge.strategy_id == "alpha-funding-carry"
    assert bridge.strategy_version == "1.0.0"
    assert bridge.market_symbol == "BTC-PERPETUAL"
    assert bridge.side == "BUY"
    assert bridge.intent_type == "MARKET"
    assert _is_hex64(bridge.paper_order_intent_request_digest)
    assert _is_hex64(bridge.bridge_digest)


def test_limit_signal_with_price_is_ready():
    bridge = _build(intent_type=PaperOrderIntentType.LIMIT, limit_price="100")
    assert bridge.status is StrategySignalToPaperIntentStatus.READY
    assert _is_hex64(bridge.paper_order_intent_request_digest)


def test_bridge_digest_is_deterministic():
    a = _build()
    b = _build()
    assert a.bridge_digest == b.bridge_digest
    assert strategy_signal_to_paper_intent_to_dict(a) == strategy_signal_to_paper_intent_to_dict(b)


# --------------------------------------------------------------------------------------------------
# 2. Digest / provenance binding
# --------------------------------------------------------------------------------------------------


def test_wrong_expected_spec_digest_cannot_be_ready():
    bridge = _build(expected_spec_digest=_HEX_BAD)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:spec_digest_mismatch" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_bound_digests_appear_in_canonical_dict():
    spec = _spec()
    payload = strategy_signal_to_paper_intent_to_dict(_build(spec))
    assert payload["expected_spec_digest"] == strategy_spec_digest(spec)
    assert payload["spec_digest"] == strategy_spec_digest(spec)
    assert payload["capacity_decision_digest"] == _HEX_CAP
    assert _is_hex64(payload["paper_order_intent_request_digest"])


def test_changed_bound_field_changes_bridge_digest():
    base = _build()
    other = _build(signal_id="sig-2")
    assert base.bridge_digest != other.bridge_digest
    diff_units = _build(requested_units="11")
    assert base.bridge_digest != diff_units.bridge_digest


def test_request_digest_is_empty_on_rejection():
    bridge = _build(requested_units="0")
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.paper_order_intent_request_digest == ""


# --------------------------------------------------------------------------------------------------
# 3. Fail-closed validation
# --------------------------------------------------------------------------------------------------


def test_symbol_not_in_universe_cannot_be_ready():
    bridge = _build(market_symbol="SOL-PERPETUAL")
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:signal_symbol_not_in_universe" in bridge.rejection_reasons


def test_unsupported_market_type_cannot_be_ready():
    spec = replace(_spec(), market_type=StrategySpecMarketType.SPOT)
    bridge = build_strategy_signal_to_paper_intent(
        spec,
        expected_spec_digest=strategy_spec_digest(spec),
        signal_id="sig-1",
        run_id="run-1",
        correlation_id="corr-1",
        market_symbol="BTC-PERPETUAL",
        side=PaperOrderSide.BUY,
        intent_type=PaperOrderIntentType.MARKET,
        requested_units="10",
        requested_notional="100",
        capacity_decision_digest=_HEX_CAP,
    )
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:spec_market_type_unsupported" in bridge.rejection_reasons


@pytest.mark.parametrize("bad_side", ["BUY", "buy", "HOLD", "LONG", None, 1])
def test_raw_or_invalid_side_raises(bad_side):
    # Strict enum boundary: a raw/lookalike string (even the correct value "BUY") never passes.
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(side=bad_side)


@pytest.mark.parametrize("bad_type", ["MARKET", "market", "STOP", None, 1])
def test_raw_or_invalid_intent_type_raises(bad_type):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(intent_type=bad_type)


@pytest.mark.parametrize("bad_units", ["0", "-1", "1e5", "abc", "1.", ".5", " 1"])
def test_non_positive_or_malformed_units_cannot_be_ready(bad_units):
    bridge = _build(requested_units=bad_units)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:signal_units_invalid" in bridge.rejection_reasons


@pytest.mark.parametrize("bad_notional", ["0", "-5", "nan", "Infinity"])
def test_non_positive_or_malformed_notional_cannot_be_ready(bad_notional):
    bridge = _build(requested_notional=bad_notional)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:signal_notional_invalid" in bridge.rejection_reasons


def test_limit_without_price_cannot_be_ready():
    bridge = _build(intent_type=PaperOrderIntentType.LIMIT, limit_price=None)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:signal_limit_price_invalid" in bridge.rejection_reasons


def test_market_with_price_cannot_be_ready():
    bridge = _build(intent_type=PaperOrderIntentType.MARKET, limit_price="100")
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:signal_limit_price_invalid" in bridge.rejection_reasons


@pytest.mark.parametrize("bad", [None, object(), 123, "spec", {"strategy_id": "x"}])
def test_wrong_typed_spec_raises(bad):
    with pytest.raises(StrategySignalToPaperIntentError):
        build_strategy_signal_to_paper_intent(
            bad,
            expected_spec_digest=_HEX_CAP,
            signal_id="sig-1",
            run_id="run-1",
            correlation_id="corr-1",
            market_symbol="BTC-PERPETUAL",
            side="BUY",
            intent_type="MARKET",
            requested_units="10",
            requested_notional="100",
            capacity_decision_digest=_HEX_CAP,
        )


@pytest.mark.parametrize("bad_digest", ["", "x", "g" * 64, "A" * 64, "a" * 63])
def test_malformed_expected_spec_digest_raises(bad_digest):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(expected_spec_digest=bad_digest)


@pytest.mark.parametrize("bad_digest", ["", "nope", "A" * 64])
def test_malformed_capacity_decision_digest_raises(bad_digest):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(capacity_decision_digest=bad_digest)


@pytest.mark.parametrize("field", ["signal_id", "run_id", "correlation_id", "market_symbol", "side", "intent_type"])
@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_required_strings_raise(field, bad):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(**{field: bad})


@pytest.mark.parametrize("field", ["signal_id", "run_id", "correlation_id", "market_symbol"])
def test_str_subclass_required_strings_raise(field):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(**{field: _SneakyStr("x")})


@pytest.mark.parametrize(
    "forbidden",
    ["live_run", "deribit-btc", "shadow_sig", "route_id", "BIST100", "scheduler"],
)
def test_forbidden_token_in_ids_raises(forbidden):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(run_id=forbidden)


def test_forbidden_token_in_metadata_raises():
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(metadata={"venue": "deribit"})


@pytest.mark.parametrize(
    "bad_meta", [{"k": 1}, {1: "v"}, [("k", "v")], "kv", {"k": _SneakyStr("v")}, {_SneakyStr("k"): "v"}]
)
def test_malformed_metadata_raises(bad_meta):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(metadata=bad_meta)


@pytest.mark.parametrize("bad_units", [10, 10.0, True, None])
def test_non_string_units_raises(bad_units):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(requested_units=bad_units)


@pytest.mark.parametrize("bad_price", [100, 100.0, True])
def test_non_string_limit_price_raises(bad_price):
    with pytest.raises(StrategySignalToPaperIntentError):
        _build(intent_type=PaperOrderIntentType.LIMIT, limit_price=bad_price)


def test_request_construction_failure_is_rejected_not_crash(monkeypatch):
    def _boom(**_kwargs):
        raise RuntimeError("builder exploded")

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _boom)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:paper_order_intent_request_construction_failed" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


# --- Full StrategySpec validation enforced (digest match alone is never sufficient) ---


@pytest.mark.parametrize(
    "override",
    [
        {"strategy_id": ""},
        {"entry_conditions": ()},
        {"risk_caps": {"max_leverage": 10.0}},
        {"funding_sensitivity": "unknown"},
        {"failure_modes": ("bist_crash",)},
    ],
)
def test_digest_valid_but_invalid_spec_cannot_be_ready(override):
    spec = replace(_spec(), **override)
    bridge = _build(spec)  # _build re-derives expected_spec_digest from this spec (digest matches)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:spec_invalid" in bridge.rejection_reasons


def test_deribit_in_venue_assumptions_cannot_be_ready():
    spec = replace(_spec(), venue_assumptions=("deribit",))
    bridge = _build(spec)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:spec_scope_violation" in bridge.rejection_reasons


def test_bist_in_nested_spec_mapping_cannot_be_ready():
    spec = replace(_spec(), data_requirements={"bist_feed": "1h"})
    bridge = _build(spec)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:spec_scope_violation" in bridge.rejection_reasons


# --- Builder output re-proof: exact type, recomputed digest, payload equality ---


def test_builder_wrong_type_is_rejected(monkeypatch):
    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", lambda **_k: object())
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:request_type_mismatch" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_builder_foreign_request_is_rejected(monkeypatch):
    def _foreign(**_kwargs):
        # A genuine but FOREIGN request (ETH/SELL/LIMIT) while the bridge signal is BTC/BUY/MARKET.
        return build_paper_order_intent_request(
            request_id="sig-1",
            capacity_decision_digest=_HEX_CAP,
            market_symbol="ETH-PERPETUAL",
            side=PaperOrderSide.SELL,
            intent_type=PaperOrderIntentType.LIMIT,
            requested_notional="100",
            requested_units="10",
            limit_price="50",
            correlation_id="corr-1",
            metadata=None,
        )

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _foreign)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:request_payload_mismatch" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_builder_digest_mismatch_is_rejected(monkeypatch):
    def _tampered(**kwargs):
        real = build_paper_order_intent_request(**kwargs)  # the real (un-patched) admission builder
        return replace(real, request_digest="0" * 64)

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _tampered)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:request_digest_mismatch" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


@pytest.mark.parametrize(
    "override",
    [
        {"paper_only": False},
        {"real_orders_enabled": True},
        {"real_money_enabled": True},
        {"schema_version": "paper-order-intent-request.v2"},
    ],
)
def test_builder_unsafe_or_wrong_schema_request_is_rejected(monkeypatch, override):
    # A self-consistent (re-sealed) request that is unsafe / wrong-schema must never bind a READY bridge.
    def _unsafe(**kwargs):
        real = build_paper_order_intent_request(**kwargs)
        tampered = replace(real, **override)
        return replace(tampered, request_digest=paper_order_intent_request_digest(tampered))

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _unsafe)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:request_safety_violation" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


class _LiarStr(str):
    """A ``str`` subclass whose ``__eq__`` always lies True — must never pass the request field reproof."""

    def __eq__(self, _other):  # noqa: D105 - adversarial: always claims equality
        return True

    def __ne__(self, _other):  # noqa: D105
        return False

    def __hash__(self):  # noqa: D105 - keep hashable for the frozen dataclass
        return hash(str(self))


@pytest.mark.parametrize(
    "override",
    [
        {"request_id": _LiarStr("foreign-signal")},
        {"schema_version": _LiarStr("foreign-schema.v9")},
        {"capacity_decision_digest": _LiarStr("b" * 64)},
        {"requested_units": _LiarStr("1")},
        {"requested_notional": _LiarStr("1")},
        {"limit_price": _LiarStr("999")},
        {"metadata": ((_LiarStr("k"), _LiarStr("v")),)},
    ],
)
def test_builder_equality_liar_request_is_rejected(monkeypatch, override):
    # A self-consistent (re-sealed) request whose internal fields are equality-liar / str-subclass values must
    # never bind a READY bridge. With raw exact-type validation BEFORE JSON normalization, a str-subclass field
    # (foreign OR correct content) is rejected at the raw-type boundary, so a lying __eq__ never even reaches
    # the content equality.
    def _liar(**kwargs):
        real = build_paper_order_intent_request(**kwargs)
        tampered = replace(real, **override)
        return replace(tampered, request_digest=paper_order_intent_request_digest(tampered))

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _liar)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False
    assert "strategy_signal_to_paper_intent:request_payload_type_violation" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_builder_non_plain_request_digest_is_rejected(monkeypatch):
    # A request carrying a non-plain (str-subclass) ``request_digest`` with WRONG content must never bind a
    # READY bridge: the raw serializer payload is exact-type validated before JSON normalization, so the
    # subclass is rejected at the raw-type boundary regardless of content.
    def _wrong_digest(**kwargs):
        real = build_paper_order_intent_request(**kwargs)  # the real (un-patched) admission builder
        return replace(real, request_digest=_LiarStr("c" * 64))

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _wrong_digest)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False
    assert "strategy_signal_to_paper_intent:request_payload_type_violation" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


@pytest.mark.parametrize(
    "override",
    [
        {"request_id": _LiarStr("sig-1")},
        {"schema_version": _LiarStr("paper-order-intent-request.v1")},
        {"capacity_decision_digest": _LiarStr(_HEX_CAP)},
        {"market_symbol": _LiarStr("BTC-PERPETUAL")},
        {"correlation_id": _LiarStr("corr-1")},
        {"requested_units": _LiarStr("10")},
        {"requested_notional": _LiarStr("100")},
    ],
)
def test_builder_correct_content_str_subclass_is_rejected(monkeypatch, override):
    # The exact Codex P2 class: a str-subclass field with CORRECT content must STILL reject. The raw public-
    # serializer payload is exact-type validated BEFORE JSON normalization, so a subclass cannot be laundered
    # into a plain str by the round-trip and then pass the content equality on identical content.
    def _subclassed(**kwargs):
        real = build_paper_order_intent_request(**kwargs)
        tampered = replace(real, **override)
        return replace(tampered, request_digest=paper_order_intent_request_digest(tampered))

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _subclassed)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False
    assert "strategy_signal_to_paper_intent:request_payload_type_violation" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_builder_correct_content_request_digest_subclass_is_rejected(monkeypatch):
    # The exact Codex P2 probe: request_digest = LiarStr(real.request_digest) with CORRECT content must REJECT,
    # not READY — exact-type validation on the raw serializer payload precedes JSON normalization.
    def _subclassed_digest(**kwargs):
        real = build_paper_order_intent_request(**kwargs)
        return replace(real, request_digest=_LiarStr(real.request_digest))

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _subclassed_digest)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False
    assert "strategy_signal_to_paper_intent:request_payload_type_violation" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_builder_correct_content_limit_price_subclass_is_rejected(monkeypatch):
    # A LIMIT request whose limit_price carries CORRECT content as a str-subclass must reject at the raw-type
    # boundary.
    def _subclassed(**kwargs):
        real = build_paper_order_intent_request(**kwargs)
        tampered = replace(real, limit_price=_LiarStr("100"))
        return replace(tampered, request_digest=paper_order_intent_request_digest(tampered))

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _subclassed)
    bridge = _build(intent_type=PaperOrderIntentType.LIMIT, limit_price="100")
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False
    assert "strategy_signal_to_paper_intent:request_payload_type_violation" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_builder_correct_content_metadata_subclass_is_rejected(monkeypatch):
    # Metadata key/value carrying CORRECT expected content as str-subclass must reject at the raw exact-type
    # boundary: the lower serializer's list comprehension keeps the element types, so the subclass survives to
    # the raw payload and is caught before JSON normalization.
    def _subclassed(**kwargs):
        real = build_paper_order_intent_request(**kwargs)
        tampered = replace(real, metadata=((_LiarStr("operator"), _LiarStr("alice")),))
        return replace(tampered, request_digest=paper_order_intent_request_digest(tampered))

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _subclassed)
    bridge = _build(metadata={"operator": "alice"})
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False
    assert "strategy_signal_to_paper_intent:request_payload_type_violation" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_raw_request_payload_exact_shape_accepts_genuine_and_rejects_subclass():
    # The raw exact-type validator accepts the genuine serializer shape and rejects str-subclass values (even
    # correct content), metadata element subclasses, and unexpected keys — BEFORE any JSON normalization.
    request = build_paper_order_intent_request(
        request_id="sig-1",
        capacity_decision_digest=_HEX_CAP,
        market_symbol="BTC-PERPETUAL",
        side=PaperOrderSide.BUY,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional="100",
        requested_units="10",
        limit_price=None,
        correlation_id="corr-1",
        metadata={"operator": "alice"},
    )
    raw = bridge_module._raw_request_payload(request)
    assert bridge_module._is_exact_raw_request_payload(raw) is True
    # Correct-content str subclass on request_digest -> non-exact raw payload (JSON would have normalized it).
    raw_bad_digest = dict(raw)
    raw_bad_digest["request_digest"] = _LiarStr(raw_bad_digest["request_digest"])
    assert bridge_module._is_exact_raw_request_payload(raw_bad_digest) is False
    # Metadata element subclass is rejected.
    raw_bad_meta = dict(raw)
    raw_bad_meta["metadata"] = [[_LiarStr("operator"), "alice"]]
    assert bridge_module._is_exact_raw_request_payload(raw_bad_meta) is False
    # Unexpected / missing keys are rejected.
    raw_extra = dict(raw)
    raw_extra["unexpected"] = "x"
    assert bridge_module._is_exact_raw_request_payload(raw_extra) is False
    raw_missing = dict(raw)
    del raw_missing["request_id"]
    assert bridge_module._is_exact_raw_request_payload(raw_missing) is False


def test_builder_stateful_metadata_request_toctou_is_rejected(monkeypatch):
    # Request-boundary TOCTOU: the digest reproof and the equality reproof must derive from ONE canonical
    # snapshot. A self-consistent re-sealed request whose ``metadata`` yields FOREIGN pairs on the first read
    # (what an old two-read digest helper would see) and EXPECTED (empty) pairs on a later read (what the
    # equality snapshot would see) must fail closed — never READY with a foreign payload digest bound. This
    # test fails if ``_reprove_request`` ever reads the digest and the equality snapshot from different reads.
    foreign_metadata = (("operator", "mallory"),)

    class _StatefulMetadata(tuple):
        """Outer metadata container yielding foreign pairs on the first read, expected (empty) on later reads."""

        def __new__(cls):
            return super().__new__(cls)

        def __init__(self):
            super().__init__()
            self._reads = 0

        def __iter__(self):
            self._reads += 1
            return iter(foreign_metadata) if self._reads == 1 else iter(())

    def _stateful(**kwargs):
        real = build_paper_order_intent_request(**kwargs)  # genuine, metadata=()
        foreign = replace(real, metadata=foreign_metadata)
        foreign_digest = paper_order_intent_request_digest(foreign)
        # Re-sealed to the FOREIGN payload digest, but carrying a metadata container that reads empty later.
        return replace(real, metadata=_StatefulMetadata(), request_digest=foreign_digest)

    monkeypatch.setattr(bridge_module, "build_paper_order_intent_request", _stateful)
    bridge = _build()
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False
    assert "strategy_signal_to_paper_intent:request_payload_mismatch" in bridge.rejection_reasons
    assert bridge.paper_order_intent_request_digest == ""


def test_request_snapshot_digest_matches_public_helper():
    # Prove the bridge's snapshot-derived request digest equals the lower-contract public helper for a genuine
    # request, so recomputing the bound digest from the single captured snapshot (rather than a second read of
    # the request object) is digest-equivalent.
    request = build_paper_order_intent_request(
        request_id="sig-1",
        capacity_decision_digest=_HEX_CAP,
        market_symbol="BTC-PERPETUAL",
        side=PaperOrderSide.BUY,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional="100",
        requested_units="10",
        limit_price=None,
        correlation_id="corr-1",
        metadata={"operator": "alice"},
    )
    raw = bridge_module._raw_request_payload(request)
    assert bridge_module._is_exact_raw_request_payload(raw)
    snapshot = bridge_module._canonical_request_snapshot(raw)
    assert snapshot is not None
    assert bridge_module._request_snapshot_digest(snapshot) == paper_order_intent_request_digest(request)


# --- Single canonical spec snapshot (digest + validation see the same one read) ---


def test_spec_serializer_called_exactly_once_on_source(monkeypatch):
    spec = _spec()
    original = bridge_module.strategy_spec_to_dict
    calls = {"n": 0}

    def _counting(arg):
        if arg is spec:  # count only reads of the (potentially mutable) SOURCE spec
            calls["n"] += 1
        return original(arg)

    monkeypatch.setattr(bridge_module, "strategy_spec_to_dict", _counting)
    _build(spec)
    assert calls["n"] == 1


def test_stateful_spec_cannot_be_ready():
    # A stateful risk_caps whose leverage changes on each materialization must not let the digest read and the
    # validation read diverge. With a single snapshot, the caller's expected digest (one read) cannot match the
    # bridge snapshot (a later read), so the bridge fails closed instead of READYing inconsistent payloads.
    class _StatefulRiskCaps(Mapping):
        def __init__(self):
            self._reads = 0

        def keys(self):
            self._reads += 1  # each full dict() materialization counts as one read
            return ("max_leverage",)

        def __iter__(self):
            return iter(("max_leverage",))

        def __getitem__(self, key):
            if key == "max_leverage":
                return float(self._reads)
            raise KeyError(key)

        def __len__(self):
            return 1

    spec = replace(_spec(), risk_caps=_StatefulRiskCaps())
    bridge = _build(spec)  # _build derives expected_spec_digest from a different read of the same spec
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert bridge.ready is False


def test_whitespace_strategy_id_cannot_be_ready():
    spec = replace(_spec(), strategy_id="  alpha-funding-carry  ")
    bridge = _build(spec)
    assert bridge.status is StrategySignalToPaperIntentStatus.REJECTED
    assert "strategy_signal_to_paper_intent:spec_noncanonical" in bridge.rejection_reasons


# --------------------------------------------------------------------------------------------------
# 4. Determinism / immutability
# --------------------------------------------------------------------------------------------------


def test_build_does_not_mutate_spec_input():
    spec = _spec()
    before = strategy_spec_to_dict(spec)
    _build(spec)
    after = strategy_spec_to_dict(spec)
    assert before == after


def test_bridge_is_frozen():
    bridge = _build()
    with pytest.raises(FrozenInstanceError):
        bridge.ready = False  # type: ignore[misc]


def test_digest_recompute_matches_self_digest():
    bridge = _build()
    assert strategy_signal_to_paper_intent_digest(bridge) == bridge.bridge_digest


# --------------------------------------------------------------------------------------------------
# 5. Forbidden surfaces (static analysis)
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(bridge_module.__file__).read_text(encoding="utf-8")


_FORBIDDEN_RUNTIME_ROOTS = frozenset(
    {
        "time",
        "datetime",
        "random",
        "uuid",
        "secrets",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "asyncio",
        "threading",
        "multiprocessing",
        "subprocess",
        "os",
        "pathlib",
        "shutil",
        "signal",
        "selectors",
    }
)
_ALLOWED_IMPORT_ROOTS = frozenset(
    {"__future__", "hashlib", "json", "re", "collections", "dataclasses", "decimal", "enum", "crypto_core"}
)
_FORBIDDEN_BUILTIN_CALLS = frozenset({"open", "eval", "exec", "compile", "__import__", "input"})
_FORBIDDEN_IMPORT_FRAGMENTS = (
    "service.readiness",
    "execution.paper_adapter",
    "paper_live_service",
    "paper_shadow_session_controller",
    "connector",
    "scheduler",
    "runtime",
    "orchestrator",
    "venue",
)


def _collect_imports(tree: ast.AST) -> tuple[list[str], dict[str, str]]:
    modules: list[str] = []
    alias_to_root: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
                root = alias.name.split(".")[0]
                alias_to_root[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
            root = node.module.split(".")[0]
            for alias in node.names:
                alias_to_root[alias.asname or alias.name] = root
    return modules, alias_to_root


def test_no_forbidden_module_imports():
    modules, _ = _collect_imports(ast.parse(_module_source()))
    for module in modules:
        root = module.split(".")[0]
        assert root in _ALLOWED_IMPORT_ROOTS, f"unexpected import root: {module}"
        assert root not in _FORBIDDEN_RUNTIME_ROOTS, f"forbidden runtime import: {module}"
        for fragment in _FORBIDDEN_IMPORT_FRAGMENTS:
            assert fragment not in module, f"forbidden import surface: {module}"
    cc_imports = sorted(m for m in modules if m.startswith("crypto_core"))
    assert cc_imports == [
        "crypto_core.strategy.spec",
        "crypto_core.validation.paper_order_intent_admission",
    ]


def test_no_forbidden_runtime_calls_alias_resistant():
    tree = ast.parse(_module_source())
    _, alias_to_root = _collect_imports(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            root = func
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                resolved = alias_to_root.get(root.id, root.id)
                assert resolved not in _FORBIDDEN_RUNTIME_ROOTS, f"forbidden runtime call via '{root.id}'"
        elif isinstance(func, ast.Name):
            assert func.id not in _FORBIDDEN_BUILTIN_CALLS, f"forbidden builtin call: {func.id}"
            assert alias_to_root.get(func.id) not in _FORBIDDEN_RUNTIME_ROOTS, f"forbidden call via bound '{func.id}'"


# --------------------------------------------------------------------------------------------------
# 6. Non-overclaim / scope
# --------------------------------------------------------------------------------------------------


def test_paper_only_and_safety_flags():
    bridge = _build()
    assert bridge.paper_only is True
    for flag in (
        "real_orders_enabled",
        "real_money_enabled",
        "capital_reserved",
        "order_routed",
        "venue_order_id_created",
        "execution_authorized",
        "fill_created",
        "pnl_computed",
        "position_mutated",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
    ):
        assert getattr(bridge, flag) is False, flag


def test_non_overclaim_flags_false():
    bridge = _build()
    assert bridge.prdv4_stage4_complete is False
    assert bridge.live_ready is False
    assert bridge.shadow_ready is False
    assert bridge.profitability_proven is False
    assert bridge.edge_proven is False


# --------------------------------------------------------------------------------------------------
# 7. Operator-readable serializer
# --------------------------------------------------------------------------------------------------


def test_serializer_exact_keys_and_json_safe():
    payload = strategy_signal_to_paper_intent_to_dict(_build())
    expected_keys = {
        "schema_version",
        "status",
        "ready",
        "strategy_id",
        "strategy_version",
        "signal_id",
        "run_id",
        "correlation_id",
        "expected_spec_digest",
        "spec_digest",
        "market_symbol",
        "side",
        "intent_type",
        "requested_units",
        "requested_notional",
        "limit_price",
        "capacity_decision_digest",
        "paper_order_intent_request_digest",
        "rejection_reasons",
        "metadata",
        "bridge_digest",
        "paper_only",
        "real_orders_enabled",
        "real_money_enabled",
        "capital_reserved",
        "order_routed",
        "venue_order_id_created",
        "execution_authorized",
        "fill_created",
        "pnl_computed",
        "position_mutated",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "profitability_proven",
        "edge_proven",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["status"] == "READY"
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert isinstance(dumped, str)


def test_side_and_intent_type_serialized_as_plain_str():
    bridge = _build()
    payload = strategy_signal_to_paper_intent_to_dict(bridge)
    # Exact plain str values (enum objects must never leak into the dataclass/serializer/digest).
    assert type(bridge.side) is str
    assert type(bridge.intent_type) is str
    assert type(payload["side"]) is str
    assert type(payload["intent_type"]) is str
    assert payload["side"] == "BUY"
    assert payload["intent_type"] == "MARKET"
    # Determinism preserved.
    assert strategy_signal_to_paper_intent_digest(bridge) == bridge.bridge_digest


def test_metadata_is_bound_and_changes_digest():
    base = _build()
    with_meta = _build(metadata={"operator": "alice"})
    assert with_meta.metadata == (("operator", "alice"),)
    assert with_meta.bridge_digest != base.bridge_digest
