"""Tests for the paper session sequence — deterministic ordering of episode results, paper-only, fail-closed."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_session_sequence
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
    PaperEpisodeRunResult,
    PaperEpisodeRunStatus,
    paper_episode_run_result_digest,
    run_paper_episode,
)
from crypto_core.validation.paper_fill_simulator import build_paper_fill_market_snapshot, build_paper_fill_policy
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot
from crypto_core.validation.paper_position_state import build_flat_paper_position_state
from crypto_core.validation.paper_session_sequence import (
    PaperSessionSequenceError,
    PaperSessionSequenceStatus,
    build_paper_session_sequence,
    paper_session_sequence_result_digest,
    paper_session_sequence_result_to_dict,
)

_EXPECTED_RESULT_KEYS = {
    "schema_version",
    "paper_session_id",
    "status",
    "market_symbol",
    "episode_count",
    "episode_run_digests",
    "first_episode_run_digest",
    "last_episode_run_digest",
    "computed_episode_count",
    "fill_rejected_episode_count",
    "rejected_episode_count",
    "final_position_state_digest",
    "final_pnl_report_digest",
    "reason_codes",
    "correlation_id",
    "metadata",
    "paper_session_sequence_digest",
    "paper_only",
    "session_sequence_computed",
    "scheduler_enabled",
    "auto_loop_enabled",
    "live_api_called",
    "connector_invoked",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "realized_pnl_computed",
    "total_pnl_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
}

_SAFE_FALSE_FLAGS = (
    "scheduler_enabled",
    "auto_loop_enabled",
    "live_api_called",
    "connector_invoked",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "realized_pnl_computed",
    "total_pnl_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
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


def _intent(*, market_symbol: str = "BTC-PERPETUAL"):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(), cap_policy, requested_notional="100000", requested_units="10", correlation_id="corr-capacity"
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


def _episode(suffix: str, *, rejected: bool = False, market_symbol: str = "BTC-PERPETUAL") -> PaperEpisodeRunResult:
    intent = _intent(market_symbol=market_symbol)
    prior = build_flat_paper_position_state(
        position_state_id=f"pos-{suffix}", market_symbol=market_symbol, correlation_id="corr-pos"
    )
    snapshot = build_paper_fill_market_snapshot(
        snapshot_id=f"snap-{suffix}",
        market_symbol=market_symbol,
        reference_price="50",
        available_units=("0" if rejected else None),
    )
    policy = build_paper_fill_policy(
        policy_id=f"fill-policy-{suffix}", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )
    mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"mark-{suffix}", market_symbol=market_symbol, mark_price="60", correlation_id="corr-mark"
    )
    return run_paper_episode(
        intent,
        prior,
        snapshot,
        policy,
        mark,
        fill_simulation_id=f"fillsim-{suffix}",
        position_transition_id=f"trans-{suffix}",
        new_position_state_id=f"newpos-{suffix}",
        pnl_report_id=f"pnl-{suffix}",
        episode_run_id=f"ep-{suffix}",
        correlation_id="corr-ep",
    )


def _session(episodes=None, **overrides: object):
    base: dict[str, object] = {"paper_session_id": "sess-1", "correlation_id": "corr-sess"}
    base.update(overrides)
    eps = episodes if episodes is not None else [_episode("1")]
    return build_paper_session_sequence(eps, **base)  # type: ignore[arg-type]


def _forge_episode(episode: PaperEpisodeRunResult, **overrides: object) -> PaperEpisodeRunResult:
    forged = replace(episode, **overrides)
    return replace(forged, episode_run_digest=paper_episode_run_result_digest(forged))


# --------------------------------------------------------------------------------------------------
# Happy paths / counts / order
# --------------------------------------------------------------------------------------------------


def test_single_computed_episode_session() -> None:
    episode = _episode("1")
    result = _session([episode])
    assert result.status is PaperSessionSequenceStatus.COMPUTED
    assert result.episode_count == 1
    assert result.computed_episode_count == 1
    assert result.fill_rejected_episode_count == 0
    assert result.rejected_episode_count == 0
    assert result.episode_run_digests == (episode.episode_run_digest,)
    assert result.first_episode_run_digest == episode.episode_run_digest
    assert result.last_episode_run_digest == episode.episode_run_digest
    assert result.final_position_state_digest == episode.new_position_state_digest
    assert result.final_pnl_report_digest == episode.pnl_report_digest
    assert result.reason_codes == ()
    assert _is_hex64(result.paper_session_sequence_digest)


def test_multiple_computed_preserve_order() -> None:
    e1, e2, e3 = _episode("1"), _episode("2"), _episode("3")
    result = _session([e1, e2, e3])
    assert result.episode_count == 3
    assert result.computed_episode_count == 3
    assert result.episode_run_digests == (e1.episode_run_digest, e2.episode_run_digest, e3.episode_run_digest)
    assert result.final_position_state_digest == e3.new_position_state_digest


def test_mixed_statuses_counts() -> None:
    e1, e2, e3 = _episode("1"), _episode("2", rejected=True), _episode("3")
    result = _session([e1, e2, e3])
    assert result.episode_count == 3
    assert result.computed_episode_count == 2
    assert result.fill_rejected_episode_count == 1
    assert result.rejected_episode_count == 0


def test_all_fill_rejected_has_no_final_digests() -> None:
    e1, e2 = _episode("1", rejected=True), _episode("2", rejected=True)
    result = _session([e1, e2])
    assert result.computed_episode_count == 0
    assert result.fill_rejected_episode_count == 2
    assert result.final_position_state_digest is None
    assert result.final_pnl_report_digest is None


def test_final_digests_from_last_computed_episode() -> None:
    computed_a, rejected_b = _episode("1"), _episode("2", rejected=True)
    result = _session([computed_a, rejected_b])
    # last COMPUTED in order is computed_a (rejected_b carries no position/pnl).
    assert result.final_position_state_digest == computed_a.new_position_state_digest
    assert result.final_pnl_report_digest == computed_a.pnl_report_digest


# --------------------------------------------------------------------------------------------------
# Fail-closed: shape / types / digests
# --------------------------------------------------------------------------------------------------


def test_empty_episode_list_rejected() -> None:
    with pytest.raises(PaperSessionSequenceError, match="episodes_empty"):
        _session([])


def test_wrong_typed_episode_rejected() -> None:
    with pytest.raises(PaperSessionSequenceError, match="episode_malformed"):
        _session([{"x": 1}])


def test_non_sequence_episodes_rejected() -> None:
    with pytest.raises(PaperSessionSequenceError, match="episodes_malformed"):
        _session(_episode("1"))  # a single result, not a sequence


def test_episode_digest_mismatch_rejected() -> None:
    forged = replace(_episode("1"), episode_run_digest="d" * 64)
    with pytest.raises(PaperSessionSequenceError, match="episode_digest_mismatch"):
        _session([forged])


def test_forged_malformed_episode_rejected() -> None:
    forged = _forge_episode(_episode("1"), schema_version="paper-episode-run-result.v2")
    with pytest.raises(PaperSessionSequenceError, match="episode_malformed"):
        _session([forged])


def test_forged_unsafe_flag_episode_rejected() -> None:
    forged = _forge_episode(_episode("1"), capital_mutated=True)
    with pytest.raises(PaperSessionSequenceError, match="episode_unsafe_flags"):
        _session([forged])


def test_forged_status_reason_inconsistency_rejected() -> None:
    forged = _forge_episode(_episode("1"), reason_codes=("unexpected",))
    with pytest.raises(PaperSessionSequenceError, match="episode_inconsistent"):
        _session([forged])


def test_forged_fill_rejected_with_pnl_digest_rejected() -> None:
    forged = _forge_episode(_episode("1", rejected=True), pnl_report_digest="a" * 64)
    with pytest.raises(PaperSessionSequenceError, match="episode_inconsistent"):
        _session([forged])


def test_forged_computed_missing_new_position_digest_rejected() -> None:
    forged = _forge_episode(_episode("1"), new_position_state_digest=None)
    with pytest.raises(PaperSessionSequenceError, match="episode_inconsistent"):
        _session([forged])


def test_forged_reserved_rejected_status_rejected() -> None:
    forged = _forge_episode(_episode("1"), status=PaperEpisodeRunStatus.REJECTED)
    with pytest.raises(PaperSessionSequenceError, match="episode_status_invalid"):
        _session([forged])


def test_duplicate_episode_digest_rejected() -> None:
    episode = _episode("1")
    with pytest.raises(PaperSessionSequenceError, match="duplicate_episode_digest"):
        _session([episode, episode])


def test_duplicate_episode_id_rejected() -> None:
    e1 = _episode("1")
    e2 = _forge_episode(_episode("2"), episode_run_id="ep-1")  # same id, different digest
    with pytest.raises(PaperSessionSequenceError, match="duplicate_episode_id"):
        _session([e1, e2])


def test_symbol_mismatch_across_episodes_rejected() -> None:
    btc, eth = _episode("1"), _episode("2", market_symbol="ETH-PERPETUAL")
    with pytest.raises(PaperSessionSequenceError, match="symbol_mismatch"):
        _session([btc, eth])


def test_non_serializable_episode_routes_to_digest_mismatch() -> None:
    # A forged episode with a non-JSON-serializable field cannot produce a recomputable canonical digest;
    # per the digest-boundary rule this must hit the *_digest_mismatch path, not generic malformed.
    forged = replace(_episode("1"), market_symbol=object())  # type: ignore[arg-type]
    with pytest.raises(PaperSessionSequenceError, match="episode_digest_mismatch"):
        _session([forged])


def test_forged_episode_duplicate_metadata_keys_rejected() -> None:
    # Sorted but duplicate-keyed metadata is forged provenance (the runner's Mapping path can't emit it).
    forged = _forge_episode(_episode("1"), metadata=(("key", "a"), ("key", "b")))
    with pytest.raises(PaperSessionSequenceError, match="episode_malformed"):
        _session([forged])


# --------------------------------------------------------------------------------------------------
# Fail-closed: scope / metadata
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [("paper_session_id", "scheduler-1"), ("correlation_id", "live_feed")],
)
def test_session_scope_violation_rejected(field: str, value: str) -> None:
    with pytest.raises(PaperSessionSequenceError, match="scope_violation"):
        _session(**{field: value})


def test_forged_child_episode_forbidden_token_rejected() -> None:
    forged = _forge_episode(_episode("1"), episode_run_id="connector-1")
    with pytest.raises(PaperSessionSequenceError, match="episode_scope_violation"):
        _session([forged])


def test_session_metadata_malformed_rejected() -> None:
    with pytest.raises(PaperSessionSequenceError, match="metadata_malformed"):
        _session(metadata={"k": 5})  # type: ignore[dict-item]


def test_session_metadata_forbidden_token_rejected() -> None:
    with pytest.raises(PaperSessionSequenceError, match="scope_violation"):
        _session(metadata={"note": "scheduler enabled"})


# --------------------------------------------------------------------------------------------------
# Determinism / immutability / no-leak
# --------------------------------------------------------------------------------------------------


def test_session_digest_deterministic() -> None:
    episodes = [_episode("1"), _episode("2")]
    r1 = build_paper_session_sequence(episodes, paper_session_id="sess-1", correlation_id="corr-sess")
    r2 = build_paper_session_sequence(episodes, paper_session_id="sess-1", correlation_id="corr-sess")
    assert r1 == r2
    assert r1.paper_session_sequence_digest == r2.paper_session_sequence_digest
    assert paper_session_sequence_result_digest(r1) == r1.paper_session_sequence_digest


def test_output_immutable() -> None:
    result = _session()
    with pytest.raises(FrozenInstanceError):
        result.status = PaperSessionSequenceStatus.REJECTED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.episode_count = 9  # type: ignore[misc]


def test_input_episodes_not_mutated() -> None:
    e1, e2 = _episode("1"), _episode("2")
    before = (paper_episode_run_result_digest(e1), paper_episode_run_result_digest(e2))
    _session([e1, e2])
    after = (paper_episode_run_result_digest(e1), paper_episode_run_result_digest(e2))
    assert before == after
    assert e1.episode_run_digest == before[0]


def test_result_dict_keys_and_safe_flags() -> None:
    payload = paper_session_sequence_result_to_dict(_session())
    assert set(payload) == _EXPECTED_RESULT_KEYS
    assert payload["paper_only"] is True
    assert payload["session_sequence_computed"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    assert payload["status"] == "COMPUTED"


def test_result_dict_has_no_forbidden_value_fields() -> None:
    payload = paper_session_sequence_result_to_dict(_session())
    for token in _BARE_FORBIDDEN_KEYS:
        assert token not in payload


def test_module_imports_only_validation_layer_and_no_decimal() -> None:
    source = Path(paper_session_sequence.__file__).read_text(encoding="utf-8")
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
    assert "decimal" not in imported


# --------------------------------------------------------------------------------------------------
# End-to-end: real episodes → session
# --------------------------------------------------------------------------------------------------


def test_end_to_end_two_real_episodes_sequenced() -> None:
    computed = _episode("1")
    rejected = _episode("2", rejected=True)
    assert computed.status is PaperEpisodeRunStatus.COMPUTED
    assert rejected.status is PaperEpisodeRunStatus.FILL_REJECTED

    result = build_paper_session_sequence([computed, rejected], paper_session_id="sess-e2e", correlation_id="corr-sess")
    assert result.status is PaperSessionSequenceStatus.COMPUTED
    assert result.market_symbol == "BTC-PERPETUAL"
    assert result.episode_count == 2
    assert result.computed_episode_count == 1
    assert result.fill_rejected_episode_count == 1
    assert result.episode_run_digests == (computed.episode_run_digest, rejected.episode_run_digest)
    assert result.final_position_state_digest == computed.new_position_state_digest
    assert result.final_pnl_report_digest == computed.pnl_report_digest
    assert paper_session_sequence_result_digest(result) == result.paper_session_sequence_digest
