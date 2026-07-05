"""Tests for the deterministic paper attested operational 30-day gate decision (v1, attestation-only)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_attested_operational_thirty_day_gate_decision as gate_module
from crypto_core.validation.paper_attested_operational_day_evidence import (
    PaperAttestedOperationalDayEvidence,
    build_paper_attested_operational_day_evidence,
    paper_attested_operational_day_evidence_digest,
)
from crypto_core.validation.paper_attested_operational_thirty_day_gate_decision import (
    PaperAttestedOperationalThirtyDayGateDecision,
    PaperAttestedOperationalThirtyDayGateDecisionError,
    PaperAttestedOperationalThirtyDayGateDecisionStatus,
    build_paper_attested_operational_thirty_day_gate_decision,
    paper_attested_operational_thirty_day_gate_decision_digest,
    paper_attested_operational_thirty_day_gate_decision_to_dict,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)

_DAY_NS = 86_400_000_000_000
_BASE_INDEX = 19_700
_MARKET = "BTC-PERPETUAL"
_CORRELATION = "corr-1"
_HEX_A = "a" * 64
_HEX_B = "b" * 64


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


def _rc(code: str) -> str:
    return f"paper_attested_operational_thirty_day_gate_decision:{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _window(
    index: int,
    *,
    suffix: str = "0",
    market_symbol: str = _MARKET,
) -> PaperDeterministicTimeWindowEvidence:
    started_at_ns = index * _DAY_NS
    duration_ns = 3_600_000_000_000
    payload: dict[str, object] = {
        "schema_version": "paper-deterministic-time-window-evidence.v1",
        "time_window_version": "paper-deterministic-time-window.v1",
        "status": PaperDeterministicTimeWindowEvidenceStatus.READY,
        "ready": True,
        "window_id": f"window-{index}-{suffix}",
        "methodology_id": "method-1",
        "timestamp_policy": "injected_deterministic_ns.v1",
        "run_id": f"run-{index}-{suffix}",
        "aggregate_id": f"agg-{index}-{suffix}",
        "correlation_id": _CORRELATION,
        "market_symbol": market_symbol,
        "expected_metrics_summary_digest": _HEX_A,
        "metrics_summary_digest": _HEX_A,
        "summary_ready": True,
        "summary_readiness_verdict": "PAPER_STAGE4_CANDIDATE",
        "started_at_ns": started_at_ns,
        "stopped_at_ns": started_at_ns + duration_ns,
        "window_duration_ns": duration_ns,
        "sample_observation_count": 5,
        "sample_eligible": True,
        "session_bridge_count": 1,
        "episode_count_total": 1,
        "event_count": 1,
        "computed_event_count": 1,
        "no_realized_event_count": 0,
        "source_event_digest_count": 1,
        "closed_units_total": "1",
        "realized_pnl_total": "1",
        "abs_realized_pnl_total": "1",
        "reason_codes": (),
        "metadata": (),
    }
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **payload)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _day(
    index: int,
    *,
    correlation_id: str = _CORRELATION,
    market_symbol: str = _MARKET,
    attestor_id: str = "operator-1",
    attestation_id: str | None = None,
    evidence_id: str | None = None,
) -> PaperAttestedOperationalDayEvidence:
    window = _window(index, market_symbol=market_symbol)
    return build_paper_attested_operational_day_evidence(
        (window,),
        expected_session_window_digests=(window.time_window_digest,),
        attested_utc_day_index=index,
        attestor_id=attestor_id,
        attestation_id=attestation_id or f"attestation-{index}",
        operational_day_evidence_id=evidence_id or f"operational-day-{index}",
        correlation_id=correlation_id,
        metadata={"purpose": "attested operational day"},
    )


def _days(start: int, count: int) -> tuple[PaperAttestedOperationalDayEvidence, ...]:
    return tuple(_day(start + offset) for offset in range(count))


def _reseal_day(day: PaperAttestedOperationalDayEvidence, **changes: object) -> PaperAttestedOperationalDayEvidence:
    seed = replace(day, **changes)  # type: ignore[arg-type]
    return replace(seed, attested_operational_day_evidence_digest=paper_attested_operational_day_evidence_digest(seed))


def _anchors(days: tuple[PaperAttestedOperationalDayEvidence, ...]) -> tuple[str, ...]:
    return tuple(day.attested_operational_day_evidence_digest for day in days)


def _build(
    days: tuple[PaperAttestedOperationalDayEvidence, ...] | None = None,
    **overrides: object,
) -> PaperAttestedOperationalThirtyDayGateDecision:
    if days is None:
        days = _days(_BASE_INDEX, 30)
    if "expected_operational_day_evidence_digests" in overrides:
        anchors = overrides.pop("expected_operational_day_evidence_digests")
    else:
        anchors = _anchors(days)
    payload: dict[str, object] = {
        "expected_operational_day_evidence_digests": anchors,
        "gate_decision_id": overrides.pop("gate_decision_id", "gate-1"),
        "correlation_id": overrides.pop("correlation_id", _CORRELATION),
        "metadata": overrides.pop("metadata", {"purpose": "attested thirty day gate"}),
    }
    payload.update(overrides)
    return build_paper_attested_operational_thirty_day_gate_decision(days, **payload)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# 1. Public API
# --------------------------------------------------------------------------------------------------


def test_public_api_exports_present() -> None:
    assert set(gate_module.__all__) == {
        "PaperAttestedOperationalThirtyDayGateDecision",
        "PaperAttestedOperationalThirtyDayGateDecisionError",
        "PaperAttestedOperationalThirtyDayGateDecisionStatus",
        "build_paper_attested_operational_thirty_day_gate_decision",
        "paper_attested_operational_thirty_day_gate_decision_digest",
        "paper_attested_operational_thirty_day_gate_decision_to_dict",
    }


def test_status_enum_values() -> None:
    assert PaperAttestedOperationalThirtyDayGateDecisionStatus.READY.value == "READY"
    assert PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED.value == "REJECTED"


def test_output_is_frozen() -> None:
    decision = _build()
    with pytest.raises(FrozenInstanceError):
        decision.ready = False  # type: ignore[misc]


# --------------------------------------------------------------------------------------------------
# 2. READY + satisfied (exactly 30) and selection determinism
# --------------------------------------------------------------------------------------------------


def test_ready_satisfied_thirty_days() -> None:
    days = _days(_BASE_INDEX, 30)
    decision = _build(days)
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.READY
    assert decision.ready is True
    assert decision.reason_codes == ()
    assert decision.attested_operational_thirty_day_gate_decided is True
    assert decision.attested_operational_thirty_day_gate_satisfied is True
    assert decision.day_count == 30
    assert decision.consecutive_day_count == 30
    assert decision.minimum_consecutive_utc_days == 30
    assert decision.market_symbol == _MARKET
    assert decision.gate_basis == "consecutive_attested_utc_epoch_days.v1"
    assert decision.gate_scope == "attested_operational_days_only_not_machine_proven.v1"
    assert decision.gate_policy_id == "minimum_30_consecutive_attested_utc_days.v1"
    assert decision.selected_start_utc_day_index == _BASE_INDEX
    assert decision.selected_end_utc_day_index == _BASE_INDEX + 29
    assert decision.selected_utc_day_indices == tuple(range(_BASE_INDEX, _BASE_INDEX + 30))
    assert decision.supplied_utc_day_indices == tuple(range(_BASE_INDEX, _BASE_INDEX + 30))
    assert decision.selected_operational_day_evidence_digests == _anchors(days)
    assert decision.verified_operational_day_evidence_digests == _anchors(days)
    # Generic return-series-gate namespace stays false; only the attested field satisfies.
    assert decision.thirty_day_gate_satisfied is False
    assert decision.thirty_day_gate_decided is False


def test_ready_satisfied_selects_first_thirty_of_thirty_five() -> None:
    days = _days(_BASE_INDEX, 35)
    decision = _build(days)
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.READY
    assert decision.attested_operational_thirty_day_gate_satisfied is True
    assert decision.day_count == 35
    assert decision.consecutive_day_count == 35
    assert decision.selected_start_utc_day_index == _BASE_INDEX
    assert decision.selected_end_utc_day_index == _BASE_INDEX + 29
    assert decision.selected_utc_day_indices == tuple(range(_BASE_INDEX, _BASE_INDEX + 30))
    assert decision.supplied_utc_day_indices == tuple(range(_BASE_INDEX, _BASE_INDEX + 35))
    assert decision.selected_operational_day_evidence_digests == _anchors(days)[:30]
    assert decision.supplied_operational_day_evidence_digests == _anchors(days)


def test_ready_binds_per_day_provenance() -> None:
    days = _days(_BASE_INDEX, 30)
    decision = _build(days)
    assert decision.operational_day_evidence_ids == tuple(
        f"operational-day-{i}" for i in range(_BASE_INDEX, _BASE_INDEX + 30)
    )
    assert decision.attestation_ids == tuple(f"attestation-{i}" for i in range(_BASE_INDEX, _BASE_INDEX + 30))
    assert decision.attestor_ids == tuple("operator-1" for _ in range(30))
    assert decision.per_day_session_counts == tuple(1 for _ in range(30))
    assert all(len(digests) == 1 and _is_hex64(digests[0]) for digests in decision.per_day_window_digests)
    assert decision.per_day_run_ids == tuple((f"run-{i}-0",) for i in range(_BASE_INDEX, _BASE_INDEX + 30))


# --------------------------------------------------------------------------------------------------
# 3. READY + not satisfied (1..29 consecutive)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("count", [1, 15, 29])
def test_ready_not_satisfied_short_run(count: int) -> None:
    decision = _build(_days(_BASE_INDEX, count))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.READY
    assert decision.ready is True
    assert decision.attested_operational_thirty_day_gate_decided is True
    assert decision.attested_operational_thirty_day_gate_satisfied is False
    assert decision.day_count == count
    assert decision.consecutive_day_count == count
    assert decision.selected_start_utc_day_index == 0
    assert decision.selected_end_utc_day_index == 0
    assert decision.selected_utc_day_indices == ()
    assert decision.selected_operational_day_evidence_digests == ()
    assert decision.supplied_utc_day_indices == tuple(range(_BASE_INDEX, _BASE_INDEX + count))


# --------------------------------------------------------------------------------------------------
# 4. Ordering / consecutiveness
# --------------------------------------------------------------------------------------------------


def test_gap_rejects() -> None:
    days = (_day(_BASE_INDEX), _day(_BASE_INDEX + 1), _day(_BASE_INDEX + 3))
    decision = _build(days)
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("utc_day_indices_not_consecutive") in decision.reason_codes
    assert decision.attested_operational_thirty_day_gate_decided is False
    assert decision.operational_days_consumed is False


def test_unsorted_rejects() -> None:
    days = (_day(_BASE_INDEX + 2), _day(_BASE_INDEX + 1), _day(_BASE_INDEX))
    decision = _build(days)
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("utc_day_indices_unsorted") in decision.reason_codes


def test_duplicate_index_rejects() -> None:
    # Two wrappers over the same day index (different evidence/attestation ids) => replay of a UTC day.
    day_a = _day(_BASE_INDEX)
    day_b = _day(_BASE_INDEX, attestation_id="attestation-x", evidence_id="operational-day-x")
    decision = _build((day_a, day_b))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("duplicate_utc_day_index") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 5. Duplicate / replay matrix
# --------------------------------------------------------------------------------------------------


def test_duplicate_attestation_id_rejects() -> None:
    days = (_day(_BASE_INDEX, attestation_id="same"), _day(_BASE_INDEX + 1, attestation_id="same"))
    decision = _build(days)
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("duplicate_attestation_id") in decision.reason_codes


def test_duplicate_evidence_id_rejects() -> None:
    days = (_day(_BASE_INDEX, evidence_id="same"), _day(_BASE_INDEX + 1, evidence_id="same"))
    decision = _build(days)
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("duplicate_operational_day_evidence_id") in decision.reason_codes


def test_duplicate_attestor_id_allowed() -> None:
    # Same operator signs consecutive days -> allowed (natural attestation pattern).
    decision = _build(_days(_BASE_INDEX, 30))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.READY
    assert len(set(decision.attestor_ids)) == 1


def test_replayed_session_run_id_across_days_rejects() -> None:
    day_a = _day(_BASE_INDEX)
    # Reseal day_b to carry day_a's run id in its session list (replayed window run across days).
    day_b = _day(_BASE_INDEX + 1)
    day_b = _reseal_day(day_b, session_run_ids=day_a.session_run_ids)
    decision = _build((day_a, day_b), expected_operational_day_evidence_digests=_anchors((day_a, day_b)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("duplicate_session_run_id_across_days") in decision.reason_codes


def test_replayed_session_window_digest_across_days_rejects() -> None:
    day_a = _day(_BASE_INDEX)
    day_b = _day(_BASE_INDEX + 1)
    day_b = _reseal_day(day_b, verified_session_window_digests=day_a.verified_session_window_digests)
    decision = _build((day_a, day_b), expected_operational_day_evidence_digests=_anchors((day_a, day_b)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("duplicate_session_window_digest_across_days") in decision.reason_codes


def test_replayed_session_window_id_across_days_rejects() -> None:
    day_a = _day(_BASE_INDEX)
    day_b = _day(_BASE_INDEX + 1)
    day_b = _reseal_day(day_b, session_window_ids=day_a.session_window_ids)
    decision = _build((day_a, day_b), expected_operational_day_evidence_digests=_anchors((day_a, day_b)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("duplicate_session_window_id_across_days") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 6. Digest tamper / anchor
# --------------------------------------------------------------------------------------------------


def test_day_digest_tamper_rejects() -> None:
    days = _days(_BASE_INDEX, 3)
    tampered = replace(days[1], operational_day_evidence_id="tampered")
    supplied = (days[0], tampered, days[2])
    decision = _build(supplied, expected_operational_day_evidence_digests=_anchors(days))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_digest_mismatch") in decision.reason_codes


def test_anchor_mismatch_rejects() -> None:
    days = _days(_BASE_INDEX, 3)
    anchors = (
        days[0].attested_operational_day_evidence_digest,
        _HEX_B,
        days[2].attested_operational_day_evidence_digest,
    )
    decision = _build(days, expected_operational_day_evidence_digests=anchors)
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_digest_mismatch") in decision.reason_codes


def test_anchor_count_mismatch_raises() -> None:
    days = _days(_BASE_INDEX, 3)
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match="anchor_count_mismatch"):
        _build(days, expected_operational_day_evidence_digests=(_HEX_A, _HEX_B))


def test_forged_non_serializable_day_rejects_without_type_error() -> None:
    forged = replace(_day(_BASE_INDEX), metadata=(("purpose", object()),))  # type: ignore[arg-type]
    decision = _build((forged,), expected_operational_day_evidence_digests=(_HEX_A,))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_digest_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 7. Day status / provenance / coherence / flags
# --------------------------------------------------------------------------------------------------


def test_day_not_ready_rejects() -> None:
    day = _reseal_day(_day(_BASE_INDEX), ready=False)
    decision = _build((day,), expected_operational_day_evidence_digests=_anchors((day,)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_not_ready") in decision.reason_codes


def test_day_not_attested_rejects() -> None:
    day = _reseal_day(_day(_BASE_INDEX), operator_attested_operational_day=False)
    decision = _build((day,), expected_operational_day_evidence_digests=_anchors((day,)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_not_attested") in decision.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"attestation_source": "other.v1"},
        {"attestation_scope": "other.v1"},
        {"attestation_version": "other.v1"},
        {"operational_origin": "other.v1"},
        {"utc_day_policy": "other.v1"},
    ],
)
def test_day_provenance_invalid_rejects(changes: dict) -> None:
    day = _reseal_day(_day(_BASE_INDEX), **changes)
    decision = _build((day,), expected_operational_day_evidence_digests=_anchors((day,)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_provenance_invalid") in decision.reason_codes


def test_day_schema_invalid_rejects() -> None:
    day = _reseal_day(_day(_BASE_INDEX), schema_version="x.v0")
    decision = _build((day,), expected_operational_day_evidence_digests=_anchors((day,)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_schema_invalid") in decision.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"machine_time_origin_proven": True},
        {"timestamp_origin_proven": True},
        {"real_wall_clock_used": True},
        {"real_time_paper_operation_proven": True},
        {"operational_day_machine_proven": True},
        {"operational_readiness": True},
        {"prdv4_stage4_complete": True},
        {"thirty_day_gate_satisfied": True},
        {"live_ready": True},
        {"real_orders_enabled": True},
        {"paper_only": False},
        {"session_windows_consumed": False},
    ],
)
def test_day_unsafe_flags_reject(changes: dict) -> None:
    day = _reseal_day(_day(_BASE_INDEX), **changes)
    decision = _build((day,), expected_operational_day_evidence_digests=_anchors((day,)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_unsafe_flags") in decision.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"day_duration_ns": 999},
        {"day_start_ns": 0},
        {"day_end_ns": 0},
        {"session_count": 0},
        {"session_run_ids": ("run-x", "run-y")},
    ],
)
def test_day_coherence_invalid_rejects(changes: dict) -> None:
    day = _reseal_day(_day(_BASE_INDEX), **changes)
    decision = _build((day,), expected_operational_day_evidence_digests=_anchors((day,)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_coherence_invalid") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 8. Cross-day scope
# --------------------------------------------------------------------------------------------------


def test_market_mismatch_rejects() -> None:
    day_a = _day(_BASE_INDEX)
    day_b = _day(_BASE_INDEX + 1, market_symbol="ETH-PERPETUAL")
    decision = _build((day_a, day_b))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("market_symbol_mismatch") in decision.reason_codes


def test_day_correlation_mismatch_rejects() -> None:
    day_a = _day(_BASE_INDEX)
    day_b = _day(_BASE_INDEX + 1, correlation_id="corr-2")
    decision = _build((day_a, day_b))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("correlation_id_mismatch") in decision.reason_codes


def test_gate_correlation_mismatch_rejects() -> None:
    decision = _build(_days(_BASE_INDEX, 3), correlation_id="corr-other")
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("correlation_id_mismatch") in decision.reason_codes


def test_trailing_extra_day_invalid_rejects_whole() -> None:
    # 30 valid consecutive days + 1 malformed trailing day: the whole artifact must reject (all-valid rule).
    days = _days(_BASE_INDEX, 30)
    bad_tail = _reseal_day(_day(_BASE_INDEX + 30), operational_readiness=True)
    decision = _build((*days, bad_tail), expected_operational_day_evidence_digests=_anchors((*days, bad_tail)))
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    assert _rc("operational_day_unsafe_flags") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 9. Raise matrix
# --------------------------------------------------------------------------------------------------


def test_empty_days_raises() -> None:
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match="days_malformed"):
        build_paper_attested_operational_thirty_day_gate_decision(
            (),
            expected_operational_day_evidence_digests=(),
            gate_decision_id="gate-1",
            correlation_id=_CORRELATION,
        )


def test_non_tuple_days_raises() -> None:
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match="days_malformed"):
        _build([_day(_BASE_INDEX)])  # type: ignore[arg-type]


def test_wrong_day_type_raises() -> None:
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match="days_malformed"):
        _build(("not-a-day",), expected_operational_day_evidence_digests=(_HEX_A,))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_anchor", ["", "xyz", "A" * 64, "a" * 63, _LiarStr("a" * 64)])
def test_invalid_anchor_raises(bad_anchor: object) -> None:
    with pytest.raises(
        PaperAttestedOperationalThirtyDayGateDecisionError, match="expected_operational_day_evidence_digest_invalid"
    ):
        _build(_days(_BASE_INDEX, 1), expected_operational_day_evidence_digests=(bad_anchor,))


@pytest.mark.parametrize(
    ("field_name", "reason"),
    [("gate_decision_id", "gate_decision_id_invalid"), ("correlation_id", "correlation_id_invalid")],
)
@pytest.mark.parametrize("bad_value", ["", "  padded  ", "with\x00control", _LiarStr("id")])
def test_malformed_ids_raise(field_name: str, reason: str, bad_value: object) -> None:
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match=reason):
        _build(_days(_BASE_INDEX, 1), **{field_name: bad_value})


@pytest.mark.parametrize("metadata", [{1: "x"}, {"k": 2}, {"k": "v\x00"}, {" k": "v"}, "not-a-mapping"])
def test_malformed_metadata_raises(metadata: object) -> None:
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match="metadata_malformed"):
        _build(_days(_BASE_INDEX, 1), metadata=metadata)


@pytest.mark.parametrize("token_id", ["deribit-gate", "order-flow-x", "scheduler-run", "real_money_test", "bist-gate"])
def test_forbidden_scope_token_raises(token_id: str) -> None:
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match="scope_violation"):
        _build(_days(_BASE_INDEX, 1), gate_decision_id=token_id)


def test_clock_token_raises() -> None:
    with pytest.raises(PaperAttestedOperationalThirtyDayGateDecisionError, match="clock_token_forbidden"):
        _build(_days(_BASE_INDEX, 1), gate_decision_id="wall_clock-gate")


# --------------------------------------------------------------------------------------------------
# 10. Determinism / serializer
# --------------------------------------------------------------------------------------------------


def test_deterministic_same_inputs_same_digest() -> None:
    days = _days(_BASE_INDEX, 30)
    first = _build(days)
    second = _build(days)
    assert first == second
    assert (
        first.attested_operational_thirty_day_gate_decision_digest
        == second.attested_operational_thirty_day_gate_decision_digest
    )


def test_self_digest_reproves() -> None:
    decision = _build()
    assert _is_hex64(decision.attested_operational_thirty_day_gate_decision_digest)
    assert (
        paper_attested_operational_thirty_day_gate_decision_digest(decision)
        == decision.attested_operational_thirty_day_gate_decision_digest
    )


def test_to_dict_covers_every_field_and_digest_excludes_only_self() -> None:
    decision = _build()
    payload = paper_attested_operational_thirty_day_gate_decision_to_dict(decision)
    field_names = {field.name for field in fields(decision)}
    assert set(payload.keys()) == field_names
    without_self = {k: v for k, v in payload.items() if k != "attested_operational_thirty_day_gate_decision_digest"}
    assert _canonical(without_self) == decision.attested_operational_thirty_day_gate_decision_digest
    assert payload["status"] == "READY"
    assert payload["metadata"] == [["purpose", "attested thirty day gate"]]
    assert payload["per_day_run_ids"][0] == [f"run-{_BASE_INDEX}-0"]


def test_tampered_digest_detectable() -> None:
    decision = _build()
    tampered = replace(decision, prdv4_stage4_complete=True)
    assert (
        paper_attested_operational_thirty_day_gate_decision_digest(tampered)
        != decision.attested_operational_thirty_day_gate_decision_digest
    )


# --------------------------------------------------------------------------------------------------
# 11. Field invariants
# --------------------------------------------------------------------------------------------------

_ALWAYS_FALSE_FIELDS = (
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
    "operational_day_machine_proven",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "real_wall_clock_used",
    "real_time_paper_operation_proven",
    "operational_readiness",
    "prdv4_stage4_complete",
    "completion_ready",
    "stage4_completion_decided",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "stage4_comparator_invoked",
    "edge_proven",
    "profitability_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "connector_invoked",
    "private_api_ready",
    "scheduler_enabled",
    "auto_loop_enabled",
    "production_execution",
    "real_orders_enabled",
    "order_routed",
    "real_money_enabled",
    "real_capital_reserved",
    "real_account_equity_used",
    "real_capital_used",
    "live_api_called",
)


@pytest.mark.parametrize("count", [3, 30])
def test_always_false_fields_on_ready_paths(count: int) -> None:
    decision = _build(_days(_BASE_INDEX, count))
    assert decision.ready is True
    for field_name in _ALWAYS_FALSE_FIELDS:
        assert getattr(decision, field_name) is False, field_name
    assert decision.paper_only is True
    assert decision.operational_days_consumed is True


def test_always_false_fields_on_rejected_path() -> None:
    decision = _build(_days(_BASE_INDEX, 1), correlation_id="corr-other")
    assert decision.status is PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED
    for field_name in _ALWAYS_FALSE_FIELDS:
        assert getattr(decision, field_name) is False, field_name
    assert decision.attested_operational_thirty_day_gate_decided is False
    assert decision.attested_operational_thirty_day_gate_satisfied is False
    assert decision.operational_days_consumed is False


def test_default_false_fields_in_dataclass() -> None:
    field_map = {field.name: field for field in fields(PaperAttestedOperationalThirtyDayGateDecision)}
    assert field_map["prdv4_stage4_complete"].default is False
    assert field_map["thirty_day_gate_satisfied"].default is False
    assert field_map["machine_time_origin_proven"].default is False


# --------------------------------------------------------------------------------------------------
# 12. AST / source forbidden surface
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(gate_module.__file__).read_text(encoding="utf-8")


def _module_ast() -> ast.Module:
    return ast.parse(_module_source())


def test_only_allowed_upstream_import() -> None:
    forbidden_modules = ("datetime", "time", "os", "socket", "subprocess", "threading", "asyncio", "pathlib")
    forbidden_endswith = (
        "stage4_comparator",
        "paper_stage4_comparison_evidence",
        "paper_stage4_completion_decision",
        "paper_sharpe_evidence",
        "paper_vs_backtest_methodology",
        "paper_edge_identity_evidence",
        "paper_stage4_backtest_baseline_evidence",
        "paper_30day_evidence_gate_decision",
        "paper_deterministic_time_window_adapter",
    )
    forbidden_prefixes = (
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.runtime",
        "crypto_core.venue",
        "crypto_core.data",
    )
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules, alias.name
                assert not alias.name.startswith(forbidden_prefixes), alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden_modules, module
            assert not module.endswith(forbidden_endswith), module
            assert not module.startswith(forbidden_prefixes), module
            for alias in node.names:
                assert "readiness" not in alias.name, alias.name
                assert "paper_adapter" not in alias.name, alias.name


def test_no_forbidden_calls_in_source() -> None:
    call_names: set[str] = set()
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_names.add(node.func.attr)
    for forbidden in ("open", "Path", "time_ns", "now", "utcnow", "monotonic", "perf_counter", "compare_stage4"):
        assert forbidden not in call_names, forbidden


def test_no_always_false_field_assigned_true_in_source() -> None:
    source = _module_source()
    assert "prdv4_stage4_complete: bool = False" in source
    assert "thirty_day_gate_satisfied: bool = False" in source
    assert "machine_time_origin_proven: bool = False" in source
    # Word-boundary lookbehind so ``thirty_day_gate_satisfied`` does not match inside the longer, legitimately
    # True-settable ``attested_operational_thirty_day_gate_satisfied`` field name / docstring.
    for field_name in _ALWAYS_FALSE_FIELDS:
        assert re.search(rf"(?<![A-Za-z0-9_]){field_name}\s*=\s*True", source) is None, field_name
        assert re.search(rf'(?<![A-Za-z0-9_])"{field_name}":\s*True', source) is None, field_name
