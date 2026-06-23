"""Tests for the paper end-to-end episode — deterministic, paper-only, fail-closed binding of one episode.

Binds the strategy-signal→paper-intent bridge, the paper episode run result (intent → fill → position →
MTM), and the realized-PnL event (→ realized PnL) into one digest-bound artifact. Covers the happy path,
digest/provenance binding, cross-artifact consistency, fail-closed validation, determinism, raw/canonical
adversariality, forbidden-surface exclusion (alias-resistant), non-overclaim, and the serializer."""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_end_to_end_episode as episode_module
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_end_to_end_episode import (
    PaperEndToEndEpisodeError,
    PaperEndToEndEpisodeStatus,
    build_paper_end_to_end_episode,
    paper_end_to_end_episode_digest,
    paper_end_to_end_episode_to_dict,
)
from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunResult,
    paper_episode_run_result_digest,
    run_paper_episode,
)
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    apply_paper_fill_to_position,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlEvent,
    compute_paper_realized_pnl_event,
    paper_realized_pnl_event_digest,
)
from crypto_core.validation.strategy_signal_to_paper_intent import (
    StrategySignalToPaperIntent,
    build_strategy_signal_to_paper_intent,
)

_HEX_CAP = "a" * 64
_HEX_BAD = "d" * 64
_SYMBOL = "BTC-PERPETUAL"
_CORR = "corr-ep"
_RUN = "run-ep"

# Shared ids so the episode runner's internal fill/transition/state and the separately-reconstructed
# realized-PnL chain produce the SAME digests (the runner does not expose its intermediates).
_CHAIN_IDS: dict[str, object] = {
    "fill_simulation_id": "fillsim-1",
    "position_transition_id": "trans-1",
    "new_position_state_id": "newpos-1",
    "pnl_report_id": "pnl-1",
    "episode_run_id": "ep-run-1",
    "correlation_id": _CORR,
}


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


# --------------------------------------------------------------------------------------------------
# Strategy-signal bridge fixture (signal -> inert paper order intent request)
# --------------------------------------------------------------------------------------------------


def _spec() -> StrategySpec:
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


def _bridge(**overrides) -> StrategySignalToPaperIntent:
    spec = _spec()
    kwargs = {
        "expected_spec_digest": strategy_spec_digest(spec),
        "signal_id": "sig-1",
        "run_id": _RUN,
        "correlation_id": _CORR,
        "market_symbol": _SYMBOL,
        "side": PaperOrderSide.SELL,
        "intent_type": PaperOrderIntentType.MARKET,
        "requested_units": "4",
        "requested_notional": "200",
        "capacity_decision_digest": _HEX_CAP,
        "limit_price": None,
    }
    kwargs.update(overrides)
    return build_strategy_signal_to_paper_intent(spec, **kwargs)


# --------------------------------------------------------------------------------------------------
# Deterministic chain fixtures (intent -> fill -> position -> realized PnL), shared-digest by design
# --------------------------------------------------------------------------------------------------


def _prior_long():
    return build_paper_position_state(
        position_state_id="pos-1",
        market_symbol=_SYMBOL,
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price="100",
        transition_count=0,
        correlation_id="corr-pos",
    )


def _order_intent(*, side: PaperOrderSide = PaperOrderSide.SELL, requested_units: str = "4"):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_capacity_draft(),
        cap_policy,
        requested_notional="200",
        requested_units=requested_units,
        correlation_id="corr-capacity",
    )
    request = build_paper_order_intent_request(
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=_SYMBOL,
        side=side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id="intent-1", correlation_id="corr-intent")


def _make_capacity_draft():
    from crypto_core.validation.paper_allocator_intent_draft import (
        PaperAllocatorIntentDraft,
        PaperAllocatorIntentDraftStatus,
        paper_allocator_intent_draft_digest,
    )

    fields: dict[str, object] = {
        "schema_version": "paper-allocator-intent-draft.v1",
        "status": PaperAllocatorIntentDraftStatus.DRAFT_READY,
        "sleeve_id": "sleeve-alpha",
        "policy_id": "policy-alpha",
        "readiness_digest": "a" * 64,
        "promotion_readiness_journal_entry_digest": "a" * 64,
        "promotion_readiness_payload_digest": "a" * 64,
        "promotion_candidate_journal_entry_digest": "a" * 64,
        "decision_journal_entry_digest": "a" * 64,
        "decision_journal_payload_digest": "a" * 64,
        "eligible_count": 2,
        "blocked_count": 0,
        "insufficient_count": 0,
        "blockers": (),
        "correlation_id": "corr-draft",
        "metadata": (),
    }
    draft = PaperAllocatorIntentDraft(**fields, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _snapshot(*, reference_price: str = "50"):
    return build_paper_fill_market_snapshot(
        snapshot_id="snap-1", market_symbol=_SYMBOL, reference_price=reference_price, available_units=None
    )


def _policy():
    return build_paper_fill_policy(
        policy_id="fill-policy-1", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )


def _mark(*, mark_price: str = "60"):
    return build_paper_mark_snapshot(
        mark_snapshot_id="mark-1", market_symbol=_SYMBOL, mark_price=mark_price, correlation_id="corr-mark"
    )


def _episode_run(order_intent=None, prior=None, snapshot=None, policy=None, mark=None) -> PaperEpisodeRunResult:
    return run_paper_episode(
        order_intent if order_intent is not None else _order_intent(),
        prior if prior is not None else _prior_long(),
        snapshot if snapshot is not None else _snapshot(),
        policy if policy is not None else _policy(),
        mark if mark is not None else _mark(),
        **_CHAIN_IDS,  # type: ignore[arg-type]
    )


def _realized_event(order_intent=None, prior=None, snapshot=None, policy=None) -> PaperRealizedPnlEvent:
    """Reconstruct the SAME fill/transition/state the runner used (shared ids) and compute realized PnL."""
    order_intent = order_intent if order_intent is not None else _order_intent()
    prior = prior if prior is not None else _prior_long()
    fill = simulate_paper_fill(
        order_intent,
        snapshot if snapshot is not None else _snapshot(),
        policy if policy is not None else _policy(),
        fill_simulation_id=_CHAIN_IDS["fill_simulation_id"],  # type: ignore[arg-type]
        correlation_id=_CHAIN_IDS["correlation_id"],  # type: ignore[arg-type]
    )
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=_CHAIN_IDS["position_transition_id"],  # type: ignore[arg-type]
        new_position_state_id=_CHAIN_IDS["new_position_state_id"],  # type: ignore[arg-type]
        correlation_id=_CHAIN_IDS["correlation_id"],  # type: ignore[arg-type]
    )
    assert new_state is not None
    return compute_paper_realized_pnl_event(
        prior,
        fill,
        transition,
        new_state,
        realized_pnl_event_id="rpnl-1",
        correlation_id=_CHAIN_IDS["correlation_id"],  # type: ignore[arg-type]
    )


def _build(*, bridge=None, episode_run=None, realized=None, **overrides):
    bridge = bridge if bridge is not None else _bridge()
    episode_run = episode_run if episode_run is not None else _episode_run()
    realized = realized if realized is not None else _realized_event()
    kwargs = {
        "expected_bridge_digest": bridge.bridge_digest,
        "expected_episode_run_digest": episode_run.episode_run_digest,
        "expected_realized_pnl_event_digest": realized.realized_pnl_event_digest,
        "episode_id": "e2e-1",
        "run_id": _RUN,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_end_to_end_episode(bridge, episode_run, realized, **kwargs)


# --------------------------------------------------------------------------------------------------
# 1. Happy path
# --------------------------------------------------------------------------------------------------


def test_valid_chain_is_ready():
    episode = _build()
    assert episode.status is PaperEndToEndEpisodeStatus.READY
    assert episode.ready is True
    assert episode.rejection_reasons == ()
    assert episode.market_symbol == _SYMBOL
    assert episode.side == "SELL"
    assert episode.fill_side == "SELL"
    assert episode.strategy_id == "alpha-funding-carry"
    assert episode.realized_pnl_status == "COMPUTED"
    assert episode.realized_pnl == "-200"  # closed 4 * (50 - 100)
    assert episode.closed_units == "4"
    assert _is_hex64(episode.episode_digest)


def test_all_consumed_digests_are_bound():
    bridge, episode_run, realized = _bridge(), _episode_run(), _realized_event()
    episode = _build(bridge=bridge, episode_run=episode_run, realized=realized)
    assert episode.bridge_digest == bridge.bridge_digest
    assert episode.episode_run_digest == episode_run.episode_run_digest
    assert episode.realized_pnl_event_digest == realized.realized_pnl_event_digest
    assert episode.paper_order_intent_request_digest == bridge.paper_order_intent_request_digest
    assert episode.fill_simulation_result_digest == episode_run.fill_simulation_result_digest
    assert episode.position_transition_digest == episode_run.position_transition_digest
    assert episode.new_position_state_digest == episode_run.new_position_state_digest


def test_shared_chain_digests_match_between_episode_and_realized():
    episode_run, realized = _episode_run(), _realized_event()
    assert episode_run.fill_simulation_result_digest == realized.fill_simulation_result_digest
    assert episode_run.position_transition_digest == realized.position_transition_digest
    assert episode_run.prior_position_state_digest == realized.prior_position_state_digest
    assert episode_run.new_position_state_digest == realized.new_position_state_digest


def test_episode_digest_deterministic():
    a = _build()
    b = _build()
    assert a.episode_digest == b.episode_digest
    assert paper_end_to_end_episode_to_dict(a) == paper_end_to_end_episode_to_dict(b)


def test_digest_recompute_matches_self_digest():
    episode = _build()
    assert paper_end_to_end_episode_digest(episode) == episode.episode_digest


def test_changed_bound_field_changes_episode_digest():
    base = _build()
    other = _build(episode_id="e2e-2")
    assert base.episode_digest != other.episode_digest


# --------------------------------------------------------------------------------------------------
# 2. Digest / provenance binding
# --------------------------------------------------------------------------------------------------


def test_wrong_expected_bridge_digest_cannot_be_ready():
    episode = _build(expected_bridge_digest=_HEX_BAD)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:bridge_digest_mismatch" in episode.rejection_reasons


def test_wrong_expected_episode_run_digest_cannot_be_ready():
    episode = _build(expected_episode_run_digest=_HEX_BAD)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:episode_run_digest_mismatch" in episode.rejection_reasons


def test_wrong_expected_realized_digest_cannot_be_ready():
    episode = _build(expected_realized_pnl_event_digest=_HEX_BAD)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:realized_pnl_event_digest_mismatch" in episode.rejection_reasons


def test_tampered_bridge_digest_cannot_be_ready():
    forged = replace(_bridge(), bridge_digest=_HEX_BAD)
    episode = _build(bridge=forged, expected_bridge_digest=_HEX_BAD)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:bridge_digest_mismatch" in episode.rejection_reasons


# --------------------------------------------------------------------------------------------------
# 3. Cross-artifact consistency
# --------------------------------------------------------------------------------------------------


def test_symbol_mismatch_cannot_be_ready():
    bridge = _bridge(market_symbol="ETH-PERPETUAL")  # spec universe includes ETH-PERPETUAL
    episode = _build(bridge=bridge)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:symbol_mismatch" in episode.rejection_reasons


def test_side_mismatch_cannot_be_ready():
    bridge = _bridge(side=PaperOrderSide.BUY)  # realized fill side is SELL
    episode = _build(bridge=bridge)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:side_mismatch" in episode.rejection_reasons


def test_correlation_mismatch_cannot_be_ready():
    bridge = _bridge(correlation_id="corr-other")
    episode = _build(bridge=bridge, correlation_id="corr-other")
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:correlation_mismatch" in episode.rejection_reasons


def test_caller_correlation_mismatch_cannot_be_ready():
    # All artifacts agree on _CORR, but the caller-supplied correlation_id differs.
    episode = _build(correlation_id="corr-different")
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:correlation_mismatch" in episode.rejection_reasons


def test_run_id_mismatch_cannot_be_ready():
    episode = _build(run_id="run-different")
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:run_id_mismatch" in episode.rejection_reasons


def test_foreign_realized_event_chain_digest_mismatch():
    # A realized event from a DIFFERENT chain (different prior avg) does not share the episode's digests.
    foreign_prior = build_paper_position_state(
        position_state_id="pos-2",
        market_symbol=_SYMBOL,
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price="123",
        transition_count=0,
        correlation_id="corr-pos",
    )
    foreign = _realized_event(prior=foreign_prior)
    episode = _build(realized=foreign, expected_realized_pnl_event_digest=foreign.realized_pnl_event_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:chain_digest_mismatch" in episode.rejection_reasons


# --------------------------------------------------------------------------------------------------
# 4. Status / safety
# --------------------------------------------------------------------------------------------------


def test_bridge_not_ready_cannot_be_ready():
    rejected = _bridge(market_symbol="SOL-PERPETUAL")  # not in spec universe -> REJECTED bridge
    episode = _build(bridge=rejected, expected_bridge_digest=rejected.bridge_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:bridge_not_ready" in episode.rejection_reasons


def test_fill_rejected_episode_cannot_be_ready():
    # An episode whose fill was REJECTED is FILL_REJECTED (not COMPUTED) and cannot bind a READY episode.
    rejected_run = run_paper_episode(
        _order_intent(),
        _prior_long(),
        build_paper_fill_market_snapshot(
            snapshot_id="snap-1", market_symbol=_SYMBOL, reference_price="50", available_units="0"
        ),
        _policy(),
        _mark(),
        **_CHAIN_IDS,  # type: ignore[arg-type]
    )
    episode = _build(episode_run=rejected_run, expected_episode_run_digest=rejected_run.episode_run_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:episode_run_not_computed" in episode.rejection_reasons


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"real_orders_enabled": True}, "paper_end_to_end_episode:bridge_unsafe_flags"),
        ({"real_money_enabled": True}, "paper_end_to_end_episode:bridge_unsafe_flags"),
        ({"live_ready": True}, "paper_end_to_end_episode:bridge_unsafe_flags"),
        ({"prdv4_stage4_complete": True}, "paper_end_to_end_episode:bridge_unsafe_flags"),
    ],
)
def test_unsafe_bridge_flags_cannot_be_ready(override, expected_reason):
    base = _bridge()
    tampered = replace(base, **override)
    resealed = replace(tampered, bridge_digest=episode_module.strategy_signal_to_paper_intent_digest(tampered))
    episode = _build(bridge=resealed, expected_bridge_digest=resealed.bridge_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert expected_reason in episode.rejection_reasons


def test_unsafe_realized_flags_cannot_be_ready():
    base = _realized_event()
    tampered = replace(base, real_money_enabled=True)
    resealed = replace(tampered, realized_pnl_event_digest=paper_realized_pnl_event_digest(tampered))
    episode = _build(realized=resealed, expected_realized_pnl_event_digest=resealed.realized_pnl_event_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:realized_pnl_event_unsafe_flags" in episode.rejection_reasons


def test_unsafe_episode_flags_cannot_be_ready():
    base = _episode_run()
    tampered = replace(base, order_routed=True)
    resealed = replace(tampered, episode_run_digest=paper_episode_run_result_digest(tampered))
    episode = _build(episode_run=resealed, expected_episode_run_digest=resealed.episode_run_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:episode_run_unsafe_flags" in episode.rejection_reasons


# --------------------------------------------------------------------------------------------------
# 5. Call-level malformed input (raises)
# --------------------------------------------------------------------------------------------------


def _call(bridge, episode_run, realized, **overrides):
    """Call the builder directly with valid anchors (so a bad artifact reaches the isinstance gate)."""
    kwargs = {
        "expected_bridge_digest": _HEX_CAP,
        "expected_episode_run_digest": _HEX_CAP,
        "expected_realized_pnl_event_digest": _HEX_CAP,
        "episode_id": "e2e-1",
        "run_id": _RUN,
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_paper_end_to_end_episode(bridge, episode_run, realized, **kwargs)


@pytest.mark.parametrize("bad", [None, object(), 123, "bridge"])
def test_wrong_typed_bridge_raises(bad):
    with pytest.raises(PaperEndToEndEpisodeError):
        _call(bad, _episode_run(), _realized_event())


@pytest.mark.parametrize("bad", [None, object(), 123])
def test_wrong_typed_episode_run_raises(bad):
    with pytest.raises(PaperEndToEndEpisodeError):
        _call(_bridge(), bad, _realized_event())


@pytest.mark.parametrize("bad", [None, object(), 123])
def test_wrong_typed_realized_raises(bad):
    with pytest.raises(PaperEndToEndEpisodeError):
        _call(_bridge(), _episode_run(), bad)


@pytest.mark.parametrize("field", ["episode_id", "run_id", "correlation_id"])
@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_required_strings_raise(field, bad):
    with pytest.raises(PaperEndToEndEpisodeError):
        _build(**{field: bad})


@pytest.mark.parametrize(
    "field", ["expected_bridge_digest", "expected_episode_run_digest", "expected_realized_pnl_event_digest"]
)
@pytest.mark.parametrize("bad", ["", "x", "g" * 64, "A" * 64, "a" * 63])
def test_malformed_expected_digests_raise(field, bad):
    with pytest.raises(PaperEndToEndEpisodeError):
        _build(**{field: bad})


@pytest.mark.parametrize("bad_meta", [{"k": 1}, {1: "v"}, [("k", "v")], "kv"])
def test_malformed_metadata_raises(bad_meta):
    with pytest.raises(PaperEndToEndEpisodeError):
        _build(metadata=bad_meta)


@pytest.mark.parametrize("forbidden", ["live_run", "deribit-x", "shadow_y", "route_id", "BIST100", "scheduler"])
def test_forbidden_token_in_ids_raises(forbidden):
    with pytest.raises(PaperEndToEndEpisodeError):
        _build(episode_id=forbidden)


def test_forbidden_token_in_metadata_raises():
    with pytest.raises(PaperEndToEndEpisodeError):
        _build(metadata={"venue": "deribit"})


# --------------------------------------------------------------------------------------------------
# 6. Raw / canonical adversariality
# --------------------------------------------------------------------------------------------------


class _SneakyStr(str):
    """A ``str`` subclass that lies about being non-empty — must never pass the exact-plain-string gate."""

    def strip(self, *args, **kwargs):  # noqa: D401 - adversarial override
        return "definitely-not-empty"


class _LiarStr(str):
    """A ``str`` subclass whose ``__eq__`` always lies True — must never pass cross-consistency."""

    def __eq__(self, _other):  # noqa: D105 - adversarial
        return True

    def __ne__(self, _other):  # noqa: D105
        return False

    def __hash__(self):  # noqa: D105 - keep hashable
        return hash(str(self))


@pytest.mark.parametrize("field", ["episode_id", "run_id", "correlation_id"])
def test_str_subclass_required_strings_raise(field):
    with pytest.raises(PaperEndToEndEpisodeError):
        _build(**{field: _SneakyStr("x")})


def test_equality_liar_bridge_side_cannot_be_ready():
    # A bridge whose side is an equality-liar str must not pass the side cross-check: the probe compares
    # exact plain-string content (a str subclass collapses to "").
    base = _bridge()
    tampered = replace(base, side=_LiarStr("SELL"))
    resealed = replace(tampered, bridge_digest=episode_module.strategy_signal_to_paper_intent_digest(tampered))
    episode = _build(bridge=resealed, expected_bridge_digest=resealed.bridge_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:side_mismatch" in episode.rejection_reasons
    assert episode.side == ""  # str subclass collapsed to empty in the bound artifact


def test_equality_liar_correlation_cannot_be_ready():
    base = _bridge()
    tampered = replace(base, correlation_id=_LiarStr(_CORR))
    resealed = replace(tampered, bridge_digest=episode_module.strategy_signal_to_paper_intent_digest(tampered))
    episode = _build(bridge=resealed, expected_bridge_digest=resealed.bridge_digest)
    assert episode.status is PaperEndToEndEpisodeStatus.REJECTED
    assert "paper_end_to_end_episode:correlation_mismatch" in episode.rejection_reasons


# --------------------------------------------------------------------------------------------------
# 7. Determinism / immutability
# --------------------------------------------------------------------------------------------------


def test_episode_is_frozen():
    episode = _build()
    with pytest.raises(FrozenInstanceError):
        episode.ready = False  # type: ignore[misc]


def test_build_inputs_not_mutated():
    bridge, episode_run, realized = _bridge(), _episode_run(), _realized_event()
    before = (bridge.bridge_digest, episode_run.episode_run_digest, realized.realized_pnl_event_digest)
    _build(bridge=bridge, episode_run=episode_run, realized=realized)
    after = (bridge.bridge_digest, episode_run.episode_run_digest, realized.realized_pnl_event_digest)
    assert before == after


# --------------------------------------------------------------------------------------------------
# 8. Forbidden surfaces (static analysis)
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(episode_module.__file__).read_text(encoding="utf-8")


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
    {"__future__", "hashlib", "json", "re", "collections", "dataclasses", "enum", "crypto_core"}
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
        "crypto_core.validation.paper_episode_runner",
        "crypto_core.validation.paper_realized_pnl",
        "crypto_core.validation.strategy_signal_to_paper_intent",
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
# 9. Non-overclaim / scope
# --------------------------------------------------------------------------------------------------


def test_paper_only_and_safety_flags():
    episode = _build()
    assert episode.paper_only is True
    for flag in (
        "real_orders_enabled",
        "real_money_enabled",
        "capital_reserved",
        "capital_mutated",
        "balance_mutated",
        "order_routed",
        "venue_order_id_created",
        "exchange_order_id_created",
        "client_order_id_created",
        "route_id_created",
        "execution_instruction_created",
        "execution_authorized",
        "live_position_mutated",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
    ):
        assert getattr(episode, flag) is False, flag


def test_non_overclaim_flags_false():
    episode = _build()
    assert episode.prdv4_stage4_complete is False
    assert episode.live_ready is False
    assert episode.shadow_ready is False
    assert episode.profitability_proven is False
    assert episode.edge_proven is False
    assert episode.production_execution is False


# --------------------------------------------------------------------------------------------------
# 10. Operator-readable serializer
# --------------------------------------------------------------------------------------------------


def test_serializer_keys_and_json_safe():
    payload = paper_end_to_end_episode_to_dict(_build())
    assert payload["status"] == "READY"
    assert payload["realized_pnl"] == "-200"
    assert payload["prdv4_stage4_complete"] is False
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert isinstance(dumped, str)


def test_metadata_is_bound_and_changes_digest():
    base = _build()
    with_meta = _build(metadata={"operator": "alice"})
    assert with_meta.metadata == (("operator", "alice"),)
    assert with_meta.episode_digest != base.episode_digest
