"""Tests for the deterministic paper episode runner — single-step orchestration, paper-only, fail-closed."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_episode_runner
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunnerError,
    PaperEpisodeRunStatus,
    paper_episode_run_result_digest,
    paper_episode_run_result_to_dict,
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
from crypto_core.validation.paper_pnl_report import (
    build_paper_mark_snapshot,
    compute_paper_pnl_report,
    paper_mark_snapshot_digest,
)
from crypto_core.validation.paper_position_state import (
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
)

_EXPECTED_RESULT_KEYS = {
    "schema_version",
    "episode_run_id",
    "status",
    "market_symbol",
    "order_intent_digest",
    "prior_position_state_digest",
    "fill_market_snapshot_digest",
    "fill_policy_digest",
    "fill_simulation_result_digest",
    "fill_status",
    "position_transition_digest",
    "transition_status",
    "new_position_state_digest",
    "mark_snapshot_digest",
    "pnl_report_digest",
    "reason_codes",
    "correlation_id",
    "metadata",
    "episode_run_digest",
    "paper_only",
    "episode_run_computed",
    "fill_simulated",
    "position_state_updated",
    "pnl_report_computed",
    "realized_pnl_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "live_api_called",
    "scheduler_enabled",
    "connector_invoked",
}

_SAFE_FALSE_FLAGS = (
    "realized_pnl_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "live_api_called",
    "scheduler_enabled",
    "connector_invoked",
)

_BARE_FORBIDDEN_KEYS = (
    "venue_order_id",
    "exchange_order_id",
    "client_order_id",
    "route_id",
    "execution_instruction",
    "order_id",
    "position_id",
    "realized_pnl",
    "total_pnl",
    "unrealized_pnl",
    "equity",
    "margin",
    "balance",
    "capital",
    "scheduler",
    "auto_loop",
    "connector",
)

_RUN_IDS: dict[str, object] = {
    "fill_simulation_id": "fillsim-1",
    "position_transition_id": "trans-1",
    "new_position_state_id": "pos-2",
    "pnl_report_id": "pnl-1",
    "episode_run_id": "ep-1",
    "correlation_id": "corr-ep",
}


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _make_draft() -> PaperAllocatorIntentDraft:
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


def _intent(*, market_symbol: str = "BTC-PERPETUAL", requested_units: str = "10", requested_notional: str = "100000"):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(),
        cap_policy,
        requested_notional=requested_notional,
        requested_units=requested_units,
        correlation_id="corr-capacity",
    )
    request = build_paper_order_intent_request(
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=market_symbol,
        side=PaperOrderSide.BUY,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id="intent-1", correlation_id="corr-intent")


def _snapshot(*, reference_price: str = "50", available_units: str | None = None, market_symbol: str = "BTC-PERPETUAL"):
    return build_paper_fill_market_snapshot(
        snapshot_id="snap-1",
        market_symbol=market_symbol,
        reference_price=reference_price,
        available_units=available_units,
    )


def _policy(*, allow_partial_fill: bool = False, slippage_bps: str = "0", fee_rate_bps: str = "0"):
    return build_paper_fill_policy(
        policy_id="fill-policy-1",
        slippage_bps=slippage_bps,
        fee_rate_bps=fee_rate_bps,
        allow_partial_fill=allow_partial_fill,
    )


def _prior(*, market_symbol: str = "BTC-PERPETUAL"):
    return build_flat_paper_position_state(
        position_state_id="pos-1", market_symbol=market_symbol, correlation_id="corr-pos"
    )


def _mark(*, mark_price: str = "60", market_symbol: str = "BTC-PERPETUAL"):
    return build_paper_mark_snapshot(
        mark_snapshot_id="mark-1", market_symbol=market_symbol, mark_price=mark_price, correlation_id="corr-mark"
    )


def _run(intent=None, prior=None, snapshot=None, policy=None, mark=None, **id_overrides: object):
    ids: dict[str, object] = {**_RUN_IDS, **id_overrides}
    return run_paper_episode(
        intent if intent is not None else _intent(),
        prior if prior is not None else _prior(),
        snapshot if snapshot is not None else _snapshot(),
        policy if policy is not None else _policy(),
        mark if mark is not None else _mark(),
        **ids,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------------------------------


def test_filled_episode_computed() -> None:
    result = _run()
    assert result.status is PaperEpisodeRunStatus.COMPUTED
    assert result.fill_status == "FILLED"
    assert result.transition_status == "APPLIED"
    assert result.episode_run_computed is True
    assert result.fill_simulated is True
    assert result.position_state_updated is True
    assert result.pnl_report_computed is True
    assert result.new_position_state_digest is not None
    assert result.pnl_report_digest is not None
    assert result.reason_codes == ()
    assert _is_hex64(result.episode_run_digest)


def test_partially_filled_episode_computed() -> None:
    result = _run(snapshot=_snapshot(available_units="4"), policy=_policy(allow_partial_fill=True))
    assert result.status is PaperEpisodeRunStatus.COMPUTED
    assert result.fill_status == "PARTIALLY_FILLED"
    assert result.transition_status == "APPLIED"
    assert result.position_state_updated is True
    assert result.pnl_report_computed is True
    assert result.pnl_report_digest is not None


def test_rejected_fill_episode_fill_rejected() -> None:
    result = _run(snapshot=_snapshot(available_units="0"), policy=_policy(allow_partial_fill=False))
    assert result.status is PaperEpisodeRunStatus.FILL_REJECTED
    assert result.fill_status == "REJECTED"
    assert result.transition_status == "REJECTED"
    assert result.episode_run_computed is False
    assert result.position_state_updated is False
    assert result.pnl_report_computed is False
    assert result.new_position_state_digest is None
    assert result.pnl_report_digest is None
    assert "fill_rejected" in result.reason_codes
    assert "insufficient_liquidity" in result.reason_codes
    assert list(result.reason_codes) == sorted(result.reason_codes)


def test_result_binds_all_child_digests() -> None:
    intent, prior, snapshot, policy, mark = _intent(), _prior(), _snapshot(), _policy(), _mark()
    result = _run(intent=intent, prior=prior, snapshot=snapshot, policy=policy, mark=mark)
    assert result.order_intent_digest == intent.intent_digest
    assert result.prior_position_state_digest == prior.position_state_digest
    assert result.fill_market_snapshot_digest == snapshot.snapshot_digest
    assert result.fill_policy_digest == policy.policy_digest
    assert result.mark_snapshot_digest == mark.mark_snapshot_digest
    for digest in (
        result.fill_simulation_result_digest,
        result.position_transition_digest,
        result.new_position_state_digest,
        result.pnl_report_digest,
        result.episode_run_digest,
    ):
        assert _is_hex64(digest)


def test_episode_digest_deterministic() -> None:
    intent, prior, snapshot, policy, mark = _intent(), _prior(), _snapshot(), _policy(), _mark()
    r1 = _run(intent=intent, prior=prior, snapshot=snapshot, policy=policy, mark=mark)
    r2 = _run(intent=intent, prior=prior, snapshot=snapshot, policy=policy, mark=mark)
    assert r1 == r2
    assert r1.episode_run_digest == r2.episode_run_digest
    assert paper_episode_run_result_digest(r1) == r1.episode_run_digest


# --------------------------------------------------------------------------------------------------
# Fail-closed: types / digests / symbol
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_inputs_raise() -> None:
    good = (_intent(), _prior(), _snapshot(), _policy(), _mark())
    labels = (
        "order_intent_malformed",
        "prior_position_state_malformed",
        "fill_market_snapshot_malformed",
        "fill_policy_malformed",
        "mark_snapshot_malformed",
    )
    for index, label in enumerate(labels):
        args = list(good)
        args[index] = {"x": 1}  # type: ignore[assignment]
        with pytest.raises(PaperEpisodeRunnerError, match=label):
            run_paper_episode(*args, **_RUN_IDS)  # type: ignore[arg-type]


def test_order_intent_digest_mismatch_raises() -> None:
    forged = replace(_intent(), intent_digest="d" * 64)
    with pytest.raises(PaperEpisodeRunnerError, match="order_intent_digest_mismatch"):
        _run(intent=forged)


def test_prior_position_digest_mismatch_raises() -> None:
    forged = replace(_prior(), position_state_digest="d" * 64)
    with pytest.raises(PaperEpisodeRunnerError, match="prior_position_state_digest_mismatch"):
        _run(prior=forged)


def test_fill_market_snapshot_digest_mismatch_raises() -> None:
    forged = replace(_snapshot(), snapshot_digest="d" * 64)
    with pytest.raises(PaperEpisodeRunnerError, match="fill_market_snapshot_digest_mismatch"):
        _run(snapshot=forged)


def test_fill_policy_digest_mismatch_raises() -> None:
    forged = replace(_policy(), policy_digest="d" * 64)
    with pytest.raises(PaperEpisodeRunnerError, match="fill_policy_digest_mismatch"):
        _run(policy=forged)


def test_mark_snapshot_digest_mismatch_raises() -> None:
    forged = replace(_mark(), mark_snapshot_digest="d" * 64)
    with pytest.raises(PaperEpisodeRunnerError, match="mark_snapshot_digest_mismatch"):
        _run(mark=forged)


def test_symbol_mismatch_prior_raises() -> None:
    with pytest.raises(PaperEpisodeRunnerError, match="symbol_mismatch"):
        _run(prior=_prior(market_symbol="ETH-PERPETUAL"))


def test_symbol_mismatch_snapshot_raises() -> None:
    with pytest.raises(PaperEpisodeRunnerError, match="symbol_mismatch"):
        _run(snapshot=_snapshot(market_symbol="ETH-PERPETUAL"))


def test_symbol_mismatch_mark_raises() -> None:
    with pytest.raises(PaperEpisodeRunnerError, match="symbol_mismatch"):
        _run(mark=_mark(market_symbol="ETH-PERPETUAL"))


# --------------------------------------------------------------------------------------------------
# Fail-closed: forged self-consistent child artifacts (digest recomputed, structure still re-proven)
# --------------------------------------------------------------------------------------------------


def test_forged_self_consistent_order_intent_rejected() -> None:
    from crypto_core.validation.paper_order_intent import paper_order_intent_digest

    forged = replace(_intent(), order_routed=True)
    forged = replace(forged, intent_digest=paper_order_intent_digest(forged))
    with pytest.raises(PaperEpisodeRunnerError, match="fill_simulation_failed"):
        _run(intent=forged)


def test_forged_self_consistent_position_rejected() -> None:
    from crypto_core.validation.paper_position_state import paper_position_state_digest

    forged = replace(_prior(), capital_mutated=True)
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperEpisodeRunnerError, match="position_transition_failed"):
        _run(prior=forged)


def test_forged_self_consistent_fill_snapshot_rejected() -> None:
    from crypto_core.validation.paper_fill_simulator import paper_fill_market_snapshot_digest

    forged = replace(_snapshot(), reference_price="0")
    forged = replace(forged, snapshot_digest=paper_fill_market_snapshot_digest(forged))
    with pytest.raises(PaperEpisodeRunnerError, match="fill_simulation_failed"):
        _run(snapshot=forged)


def test_forged_self_consistent_fill_policy_rejected() -> None:
    from crypto_core.validation.paper_fill_simulator import paper_fill_policy_digest

    forged = replace(_policy(), slippage_bps="-1")
    forged = replace(forged, policy_digest=paper_fill_policy_digest(forged))
    with pytest.raises(PaperEpisodeRunnerError, match="fill_simulation_failed"):
        _run(policy=forged)


def _forged_mark(**overrides: object):
    """A digest-valid but structurally forged mark snapshot (digest recomputed over the tampered payload)."""
    forged = replace(_mark(), **overrides)
    return replace(forged, mark_snapshot_digest=paper_mark_snapshot_digest(forged))


def _rejected_run(mark):
    """Run a rejected-fill episode (insufficient liquidity, no partial) with the supplied mark snapshot."""
    return _run(snapshot=_snapshot(available_units="0"), policy=_policy(allow_partial_fill=False), mark=mark)


def test_forged_self_consistent_mark_snapshot_rejected() -> None:
    # COMPUTED path: the runner-level mark re-proof now rejects this before compute_paper_pnl_report.
    forged = _forged_mark(mark_price="0")
    assert paper_mark_snapshot_digest(forged) == forged.mark_snapshot_digest  # self-consistent
    with pytest.raises(PaperEpisodeRunnerError, match="mark_snapshot_malformed"):
        _run(mark=forged)


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"mark_price": "0"}, "mark_snapshot_malformed"),
        ({"mark_price": "-5"}, "mark_snapshot_malformed"),
        ({"mark_price": "60.0"}, "mark_snapshot_malformed"),
        ({"mark_price": "1e3"}, "mark_snapshot_malformed"),
        ({"mark_source_id": "connector-1"}, "mark_snapshot_scope_violation"),
        ({"observed_at_ns": -1}, "mark_snapshot_malformed"),
        ({"observed_at_ns": True}, "mark_snapshot_malformed"),
    ],
)
def test_rejected_fill_forged_mark_snapshot_rejected(overrides: dict[str, object], match: str) -> None:
    forged = _forged_mark(**overrides)
    assert paper_mark_snapshot_digest(forged) == forged.mark_snapshot_digest  # passes digest boundary
    with pytest.raises(PaperEpisodeRunnerError, match=match):
        _rejected_run(forged)


def test_rejected_fill_forged_mark_noncanonical_metadata_rejected() -> None:
    # Unsorted metadata tuple is noncanonical; digest recomputes over it, structural re-proof rejects it.
    forged = _forged_mark(metadata=(("b", "2"), ("a", "1")))
    assert paper_mark_snapshot_digest(forged) == forged.mark_snapshot_digest
    with pytest.raises(PaperEpisodeRunnerError, match="mark_snapshot_malformed"):
        _rejected_run(forged)


def test_rejected_fill_valid_mark_still_fill_rejected() -> None:
    result = _rejected_run(_mark())
    assert result.status is PaperEpisodeRunStatus.FILL_REJECTED
    assert result.new_position_state_digest is None
    assert result.pnl_report_digest is None
    assert "fill_rejected" in result.reason_codes


def test_forged_unsafe_intent_via_flag_rejected() -> None:
    from crypto_core.validation.paper_order_intent import paper_order_intent_digest

    forged = replace(_intent(), real_orders_enabled=True)
    forged = replace(forged, intent_digest=paper_order_intent_digest(forged))
    with pytest.raises(PaperEpisodeRunnerError, match="fill_simulation_failed"):
        _run(intent=forged)


# --------------------------------------------------------------------------------------------------
# Fail-closed: runner-level ids / scope / metadata
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("episode_run_id", "scheduler-1"),
        ("correlation_id", "live_feed"),
        ("fill_simulation_id", "place_order"),
        ("position_transition_id", "route_id-x"),
        ("new_position_state_id", "connector-1"),
        ("pnl_report_id", "deribit-run"),
    ],
)
def test_scope_violation_raises(field: str, value: str) -> None:
    with pytest.raises(PaperEpisodeRunnerError, match="scope_violation"):
        _run(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "fill_simulation_id",
        "position_transition_id",
        "new_position_state_id",
        "pnl_report_id",
        "episode_run_id",
        "correlation_id",
    ],
)
def test_blank_id_raises(field: str) -> None:
    with pytest.raises(PaperEpisodeRunnerError, match=f"{field}_invalid"):
        _run(**{field: "  "})


def test_metadata_malformed_raises() -> None:
    with pytest.raises(PaperEpisodeRunnerError, match="metadata_malformed"):
        _run(metadata={"k": 5})  # type: ignore[dict-item]


def test_metadata_forbidden_token_raises() -> None:
    with pytest.raises(PaperEpisodeRunnerError, match="scope_violation"):
        _run(metadata={"note": "scheduler enabled"})


# --------------------------------------------------------------------------------------------------
# Determinism / immutability / no-leak
# --------------------------------------------------------------------------------------------------


def test_inputs_not_mutated() -> None:
    from crypto_core.validation.paper_fill_simulator import paper_fill_market_snapshot_digest, paper_fill_policy_digest
    from crypto_core.validation.paper_order_intent import paper_order_intent_digest
    from crypto_core.validation.paper_pnl_report import paper_mark_snapshot_digest
    from crypto_core.validation.paper_position_state import paper_position_state_digest

    intent, prior, snapshot, policy, mark = _intent(), _prior(), _snapshot(), _policy(), _mark()
    before = (
        paper_order_intent_digest(intent),
        paper_position_state_digest(prior),
        paper_fill_market_snapshot_digest(snapshot),
        paper_fill_policy_digest(policy),
        paper_mark_snapshot_digest(mark),
    )
    _run(intent=intent, prior=prior, snapshot=snapshot, policy=policy, mark=mark)
    after = (
        paper_order_intent_digest(intent),
        paper_position_state_digest(prior),
        paper_fill_market_snapshot_digest(snapshot),
        paper_fill_policy_digest(policy),
        paper_mark_snapshot_digest(mark),
    )
    assert before == after
    assert intent.intent_digest == before[0]


def test_output_immutable() -> None:
    result = _run()
    with pytest.raises(FrozenInstanceError):
        result.status = PaperEpisodeRunStatus.REJECTED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.episode_run_digest = "x"  # type: ignore[misc]


def test_result_dict_keys_and_safe_flags() -> None:
    payload = paper_episode_run_result_to_dict(_run())
    assert set(payload) == _EXPECTED_RESULT_KEYS
    assert payload["paper_only"] is True
    assert payload["episode_run_computed"] is True
    assert payload["fill_simulated"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    assert payload["status"] == "COMPUTED"


def test_result_dict_has_no_forbidden_value_fields() -> None:
    payload = paper_episode_run_result_to_dict(_run())
    for token in _BARE_FORBIDDEN_KEYS:
        assert token not in payload


def test_scheduler_connector_only_as_false_attestations() -> None:
    payload = paper_episode_run_result_to_dict(_run())
    assert payload["scheduler_enabled"] is False
    assert payload["connector_invoked"] is False
    # bare value-form keys must be absent
    for token in ("scheduler", "auto_loop", "connector"):
        assert token not in payload


def test_module_imports_only_validation_layer_and_no_decimal() -> None:
    source = Path(paper_episode_runner.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            imported.append(node.module)
    forbidden_prefixes = (
        "crypto_core.venue",
        "crypto_core.execution",
        "crypto_core.runtime",
        "crypto_core.service",
        "crypto_core.session",
        "crypto_core.data",
        "crypto_core.portfolio",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.audit",
    )
    for module in imported:
        for prefix in forbidden_prefixes:
            assert module != prefix and not module.startswith(prefix + "."), f"forbidden import: {module}"
        if module.startswith("crypto_core"):
            assert module.startswith("crypto_core.validation"), f"unexpected crypto_core import: {module}"
    # The runner performs no arithmetic; it must not pull in the decimal module at all.
    assert "decimal" not in imported


def test_high_precision_episode_deterministic() -> None:
    reference = "50.000000000000000000000000000000000001"
    intent, prior, snapshot, policy, mark = (
        _intent(),
        _prior(),
        _snapshot(reference_price=reference),
        _policy(),
        _mark(mark_price="60"),
    )
    r1 = _run(intent=intent, prior=prior, snapshot=snapshot, policy=policy, mark=mark)
    r2 = _run(intent=intent, prior=prior, snapshot=snapshot, policy=policy, mark=mark)
    assert r1.status is PaperEpisodeRunStatus.COMPUTED
    assert r1.episode_run_digest == r2.episode_run_digest
    assert r1.fill_simulation_result_digest == r2.fill_simulation_result_digest


def test_rejected_fill_creates_no_new_state_or_pnl() -> None:
    result = _run(snapshot=_snapshot(available_units="0"))
    assert result.new_position_state_digest is None
    assert result.pnl_report_digest is None
    assert result.position_state_updated is False
    assert result.pnl_report_computed is False


# --------------------------------------------------------------------------------------------------
# End-to-end cross-check: runner binds exactly the digests of the manually-run child operations
# --------------------------------------------------------------------------------------------------


def test_end_to_end_chain_binds_child_outputs() -> None:
    intent, prior, snapshot, policy, mark = _intent(), _prior(), _snapshot(), _policy(), _mark()

    fill = simulate_paper_fill(intent, snapshot, policy, fill_simulation_id="fillsim-1", correlation_id="corr-ep")
    transition, new_state = apply_paper_fill_to_position(
        prior, fill, transition_id="trans-1", new_position_state_id="pos-2", correlation_id="corr-ep"
    )
    assert new_state is not None
    pnl = compute_paper_pnl_report(new_state, mark, pnl_report_id="pnl-1", correlation_id="corr-ep")

    result = _run(intent=intent, prior=prior, snapshot=snapshot, policy=policy, mark=mark)
    assert result.status is PaperEpisodeRunStatus.COMPUTED
    assert result.fill_simulation_result_digest == fill.result_digest
    assert result.position_transition_digest == transition.transition_digest
    assert result.new_position_state_digest == new_state.position_state_digest
    assert result.pnl_report_digest == pnl.pnl_report_digest
    # MTM cross-check: 10 units opened at 50, marked at 60 → unrealized 100 (computed by child only).
    assert pnl.unrealized_pnl == "100"
