"""Tests for the deterministic paper attested operational-day evidence (v1, attestation-only)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_attested_operational_day_evidence as operational_module
from crypto_core.validation.paper_attested_operational_day_evidence import (
    PaperAttestedOperationalDayEvidence,
    PaperAttestedOperationalDayEvidenceError,
    PaperAttestedOperationalDayEvidenceStatus,
    build_paper_attested_operational_day_evidence,
    paper_attested_operational_day_evidence_digest,
    paper_attested_operational_day_evidence_to_dict,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)

_DAY_NS = 86_400_000_000_000
_DAY_INDEX = 19_700
_DAY_START = _DAY_INDEX * _DAY_NS
_DAY_END = (_DAY_INDEX + 1) * _DAY_NS
_MARKET = "BTC-PERPETUAL"
_CORRELATION = "corr-1"
_HEX_A = "a" * 64
_HEX_B = "b" * 64


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


def _rc(code: str) -> str:
    return f"paper_attested_operational_day_evidence:{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _window(
    *,
    started_at_ns: int = _DAY_START,
    duration_ns: int = 3_600_000_000_000,
    window_id: str = "window-1",
    run_id: str = "run-1",
    aggregate_id: str = "agg-1",
    market_symbol: str = _MARKET,
    metrics_summary_digest: str = _HEX_A,
    **overrides: object,
) -> PaperDeterministicTimeWindowEvidence:
    stopped_at_ns = started_at_ns + duration_ns
    payload: dict[str, object] = {
        "schema_version": "paper-deterministic-time-window-evidence.v1",
        "time_window_version": "paper-deterministic-time-window.v1",
        "status": PaperDeterministicTimeWindowEvidenceStatus.READY,
        "ready": True,
        "window_id": window_id,
        "methodology_id": "method-1",
        "timestamp_policy": "injected_deterministic_ns.v1",
        "run_id": run_id,
        "aggregate_id": aggregate_id,
        "correlation_id": _CORRELATION,
        "market_symbol": market_symbol,
        "expected_metrics_summary_digest": metrics_summary_digest,
        "metrics_summary_digest": metrics_summary_digest,
        "summary_ready": True,
        "summary_readiness_verdict": "PAPER_STAGE4_CANDIDATE",
        "started_at_ns": started_at_ns,
        "stopped_at_ns": stopped_at_ns,
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
    payload.update(overrides)
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **payload)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _reseal_window(
    window: PaperDeterministicTimeWindowEvidence, **changes: object
) -> PaperDeterministicTimeWindowEvidence:
    seed = replace(window, **changes)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _build(
    windows: tuple[PaperDeterministicTimeWindowEvidence, ...] | None = None,
    **overrides: object,
) -> PaperAttestedOperationalDayEvidence:
    if windows is None:
        windows = (_window(),)
    if "expected_session_window_digests" in overrides:
        expected_digests = overrides.pop("expected_session_window_digests")
    else:
        expected_digests = tuple(w.time_window_digest for w in windows)
    payload: dict[str, object] = {
        "expected_session_window_digests": expected_digests,
        "attested_utc_day_index": overrides.pop("attested_utc_day_index", _DAY_INDEX),
        "attestor_id": overrides.pop("attestor_id", "operator-1"),
        "attestation_id": overrides.pop("attestation_id", "attestation-1"),
        "operational_day_evidence_id": overrides.pop("operational_day_evidence_id", "operational-day-1"),
        "correlation_id": overrides.pop("correlation_id", _CORRELATION),
        "metadata": overrides.pop("metadata", {"purpose": "attested operational day"}),
    }
    payload.update(overrides)
    return build_paper_attested_operational_day_evidence(windows, **payload)  # type: ignore[arg-type]


def _three_windows() -> tuple[PaperDeterministicTimeWindowEvidence, ...]:
    return (
        _window(
            started_at_ns=_DAY_START, duration_ns=3_600_000_000_000, window_id="w1", run_id="r1", aggregate_id="a1"
        ),
        _window(
            started_at_ns=_DAY_START + 7_200_000_000_000,
            duration_ns=3_600_000_000_000,
            window_id="w2",
            run_id="r2",
            aggregate_id="a2",
            metrics_summary_digest=_HEX_B,
        ),
        _window(
            started_at_ns=_DAY_START + 14_400_000_000_000,
            duration_ns=3_600_000_000_000,
            window_id="w3",
            run_id="r3",
            aggregate_id="a3",
            metrics_summary_digest="c" * 64,
        ),
    )


# --------------------------------------------------------------------------------------------------
# 1. Public API
# --------------------------------------------------------------------------------------------------


def test_public_api_exports_present() -> None:
    assert set(operational_module.__all__) == {
        "PaperAttestedOperationalDayEvidence",
        "PaperAttestedOperationalDayEvidenceError",
        "PaperAttestedOperationalDayEvidenceStatus",
        "build_paper_attested_operational_day_evidence",
        "paper_attested_operational_day_evidence_digest",
        "paper_attested_operational_day_evidence_to_dict",
    }


def test_status_enum_values() -> None:
    assert PaperAttestedOperationalDayEvidenceStatus.READY.value == "READY"
    assert PaperAttestedOperationalDayEvidenceStatus.REJECTED.value == "REJECTED"


def test_output_is_frozen() -> None:
    evidence = _build()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]


# --------------------------------------------------------------------------------------------------
# 2. READY one-window / multi-window
# --------------------------------------------------------------------------------------------------


def test_ready_single_window() -> None:
    evidence = _build()
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert evidence.session_count == 1
    assert evidence.minimum_sessions_per_day == 1
    assert evidence.operator_attested_operational_day is True
    assert evidence.attested_utc_day_index == _DAY_INDEX
    assert evidence.day_start_ns == _DAY_START
    assert evidence.day_end_ns == _DAY_END
    assert evidence.day_duration_ns == _DAY_NS
    assert evidence.utc_day_policy == "utc_epoch_day_index.v1"
    assert evidence.attestation_source == "operator_attested_not_machine_proven.v1"
    assert evidence.attestation_scope == "single_utc_day_digest_bound_paper_windows.v1"
    assert evidence.attestation_version == "paper-attested-operational-day-attestation.v1"
    assert evidence.operational_origin == "operator_attested_not_machine_proven.v1"
    assert evidence.market_symbol == _MARKET


def test_ready_multi_window_binds_lists() -> None:
    windows = _three_windows()
    evidence = _build(windows)
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.READY
    assert evidence.session_count == 3
    assert evidence.session_window_ids == ("w1", "w2", "w3")
    assert evidence.session_run_ids == ("r1", "r2", "r3")
    assert evidence.session_aggregate_ids == ("a1", "a2", "a3")
    assert evidence.verified_session_window_digests == tuple(w.time_window_digest for w in windows)
    assert evidence.expected_session_window_digests == tuple(w.time_window_digest for w in windows)
    assert evidence.session_started_at_ns_list == tuple(w.started_at_ns for w in windows)
    assert evidence.session_stopped_at_ns_list == tuple(w.stopped_at_ns for w in windows)
    assert evidence.session_window_duration_ns_list == tuple(w.window_duration_ns for w in windows)
    assert evidence.session_metrics_summary_digests == tuple(w.metrics_summary_digest for w in windows)
    assert evidence.source_event_digest_counts == (1, 1, 1)


# --------------------------------------------------------------------------------------------------
# 3. Boundary inclusion
# --------------------------------------------------------------------------------------------------


def test_window_at_day_start_boundary_ready() -> None:
    window = _window(started_at_ns=_DAY_START, duration_ns=3_600_000_000_000)
    assert _build((window,)).status is PaperAttestedOperationalDayEvidenceStatus.READY


def test_window_stops_at_day_end_boundary_ready() -> None:
    window = _window(started_at_ns=_DAY_END - 3_600_000_000_000, duration_ns=3_600_000_000_000)
    assert _build((window,)).status is PaperAttestedOperationalDayEvidenceStatus.READY


def test_window_starts_one_ns_before_day_rejects() -> None:
    window = _window(started_at_ns=_DAY_START - 1, duration_ns=3_600_000_000_000)
    evidence = _build((window,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_outside_attested_day") in evidence.reason_codes


def test_window_stops_one_ns_after_day_rejects() -> None:
    window = _window(started_at_ns=_DAY_END - 3_600_000_000_000 + 1, duration_ns=3_600_000_000_000)
    evidence = _build((window,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_outside_attested_day") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 4-6. Ordering / overlap
# --------------------------------------------------------------------------------------------------


def test_adjacent_windows_accept() -> None:
    first = _window(started_at_ns=_DAY_START, duration_ns=3_600_000_000_000, window_id="w1", run_id="r1")
    second = _window(
        started_at_ns=_DAY_START + 3_600_000_000_000,
        duration_ns=3_600_000_000_000,
        window_id="w2",
        run_id="r2",
        metrics_summary_digest=_HEX_B,
    )
    assert _build((first, second)).status is PaperAttestedOperationalDayEvidenceStatus.READY


def test_overlapping_windows_reject() -> None:
    first = _window(started_at_ns=_DAY_START, duration_ns=3_600_000_000_000, window_id="w1", run_id="r1")
    second = _window(
        started_at_ns=_DAY_START + 1_800_000_000_000,
        duration_ns=3_600_000_000_000,
        window_id="w2",
        run_id="r2",
        metrics_summary_digest=_HEX_B,
    )
    evidence = _build((first, second))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_windows_overlap") in evidence.reason_codes


def test_unordered_windows_reject() -> None:
    first = _window(
        started_at_ns=_DAY_START + 7_200_000_000_000, duration_ns=3_600_000_000_000, window_id="w1", run_id="r1"
    )
    second = _window(
        started_at_ns=_DAY_START,
        duration_ns=3_600_000_000_000,
        window_id="w2",
        run_id="r2",
        metrics_summary_digest=_HEX_B,
    )
    evidence = _build((first, second))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_windows_unordered") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 7-9. Distinctness / market
# --------------------------------------------------------------------------------------------------


def test_duplicate_window_digest_rejects() -> None:
    window = _window()
    evidence = _build(
        (window, window),
        expected_session_window_digests=(window.time_window_digest, window.time_window_digest),
    )
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("duplicate_session_window_digest") in evidence.reason_codes


def test_duplicate_run_id_rejects() -> None:
    first = _window(started_at_ns=_DAY_START, duration_ns=3_600_000_000_000, window_id="w1", run_id="dup")
    second = _window(
        started_at_ns=_DAY_START + 7_200_000_000_000,
        duration_ns=3_600_000_000_000,
        window_id="w2",
        run_id="dup",
        metrics_summary_digest=_HEX_B,
    )
    evidence = _build((first, second))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("duplicate_session_run_id") in evidence.reason_codes


def test_market_mismatch_rejects() -> None:
    first = _window(started_at_ns=_DAY_START, duration_ns=3_600_000_000_000, window_id="w1", run_id="r1")
    second = _window(
        started_at_ns=_DAY_START + 7_200_000_000_000,
        duration_ns=3_600_000_000_000,
        window_id="w2",
        run_id="r2",
        market_symbol="ETH-PERPETUAL",
        metrics_summary_digest=_HEX_B,
    )
    evidence = _build((first, second))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("market_symbol_mismatch") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 10-12. Digest tamper / anchor
# --------------------------------------------------------------------------------------------------


def test_digest_tamper_rejects() -> None:
    tampered = replace(_window(), window_id="tampered")
    evidence = _build((tampered,), expected_session_window_digests=(_window().time_window_digest,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_digest_mismatch") in evidence.reason_codes


def test_expected_anchor_mismatch_rejects() -> None:
    evidence = _build(expected_session_window_digests=(_HEX_B,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_digest_mismatch") in evidence.reason_codes


def test_anchor_count_mismatch_raises() -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="anchor_count_mismatch"):
        _build(expected_session_window_digests=(_HEX_A, _HEX_B))


def test_forged_non_serializable_window_rejects_without_type_error() -> None:
    forged = replace(_window(), metadata=(("purpose", object()),))  # type: ignore[arg-type]
    evidence = _build((forged,), expected_session_window_digests=(_HEX_A,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_digest_mismatch") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 13-17. Window eligibility
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"status": PaperDeterministicTimeWindowEvidenceStatus.REJECTED}, "session_window_not_ready"),
        ({"ready": False}, "session_window_not_ready"),
        ({"reason_codes": ("x",)}, "session_window_not_ready"),
        ({"sample_eligible": False}, "session_window_not_sample_eligible"),
        ({"source_event_digest_count": 0}, "session_window_source_events_missing"),
        ({"schema_version": "paper-deterministic-time-window-evidence.v0"}, "session_window_schema_invalid"),
    ],
)
def test_window_eligibility_failures_reject(changes: dict, reason: str) -> None:
    window = _reseal_window(_window(), **changes)
    evidence = _build((window,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc(reason) in evidence.reason_codes


def test_zero_duration_window_rejects() -> None:
    window = _reseal_window(_window(), stopped_at_ns=_DAY_START, window_duration_ns=0)
    evidence = _build((window,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_timestamps_invalid") in evidence.reason_codes


def test_incoherent_duration_window_rejects() -> None:
    window = _reseal_window(_window(), window_duration_ns=999)
    evidence = _build((window,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_timestamps_invalid") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 18. Unsafe flags
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"timestamp_origin_proven": True},
        {"real_wall_clock_used": True},
        {"live_ready": True},
        {"real_orders_enabled": True},
        {"real_capital_reserved": True},
        {"operational_readiness": True},
        {"thirty_day_gate_satisfied": True},
        {"paper_only": False},
        {"injected_deterministic_time_window": False},
    ],
)
def test_window_unsafe_flags_reject(changes: dict) -> None:
    window = _reseal_window(_window(), **changes)
    evidence = _build((window,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    assert _rc("session_window_unsafe_flags") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 19-20. Raise matrix
# --------------------------------------------------------------------------------------------------


def test_empty_windows_raises() -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="windows_malformed"):
        build_paper_attested_operational_day_evidence(
            (),
            expected_session_window_digests=(),
            attested_utc_day_index=_DAY_INDEX,
            attestor_id="operator-1",
            attestation_id="attestation-1",
            operational_day_evidence_id="operational-day-1",
            correlation_id=_CORRELATION,
        )


def test_non_tuple_windows_raises() -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="windows_malformed"):
        _build([_window()])  # type: ignore[arg-type]


def test_wrong_window_type_raises() -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="windows_malformed"):
        _build(("not-a-window",), expected_session_window_digests=(_HEX_A,))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_index", [0, -1, True, 1.5, "1", None])
def test_invalid_day_index_raises(bad_index: object) -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="attested_utc_day_index_invalid"):
        _build(attested_utc_day_index=bad_index)


@pytest.mark.parametrize("bad_anchor", ["", "xyz", "A" * 64, "a" * 63, _LiarStr("a" * 64)])
def test_invalid_expected_anchor_raises(bad_anchor: object) -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="expected_session_window_digest_invalid"):
        _build(expected_session_window_digests=(bad_anchor,))


@pytest.mark.parametrize(
    ("field_name", "reason"),
    [
        ("attestor_id", "attestor_id_invalid"),
        ("attestation_id", "attestation_id_invalid"),
        ("operational_day_evidence_id", "operational_day_evidence_id_invalid"),
        ("correlation_id", "correlation_id_invalid"),
    ],
)
@pytest.mark.parametrize("bad_value", ["", "  padded  ", "with\x00control", _LiarStr("id")])
def test_malformed_ids_raise(field_name: str, reason: str, bad_value: object) -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match=reason):
        _build(**{field_name: bad_value})


@pytest.mark.parametrize("metadata", [{1: "x"}, {"k": 2}, {"k": "v\x00"}, {" k": "v"}, "not-a-mapping"])
def test_malformed_metadata_raises(metadata: object) -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="metadata_malformed"):
        _build(metadata=metadata)


@pytest.mark.parametrize("token_id", ["deribit-op", "order-flow-x", "scheduler-run", "real_money_test", "bist-op"])
def test_forbidden_scope_token_raises(token_id: str) -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="scope_violation"):
        _build(attestor_id=token_id)


def test_clock_token_raises() -> None:
    with pytest.raises(PaperAttestedOperationalDayEvidenceError, match="clock_token_forbidden"):
        _build(attestation_id="wall_clock-1")


# --------------------------------------------------------------------------------------------------
# 21. Determinism / serializer
# --------------------------------------------------------------------------------------------------


def test_deterministic_same_inputs_same_digest() -> None:
    assert _build() == _build()
    assert _build().attested_operational_day_evidence_digest == _build().attested_operational_day_evidence_digest


def test_self_digest_reproves() -> None:
    evidence = _build()
    assert _is_hex64(evidence.attested_operational_day_evidence_digest)
    assert paper_attested_operational_day_evidence_digest(evidence) == evidence.attested_operational_day_evidence_digest


def test_to_dict_covers_every_field_and_digest_excludes_only_self() -> None:
    evidence = _build()
    payload = paper_attested_operational_day_evidence_to_dict(evidence)
    field_names = {field.name for field in fields(evidence)}
    assert set(payload.keys()) == field_names
    without_self = {k: v for k, v in payload.items() if k != "attested_operational_day_evidence_digest"}
    assert _canonical(without_self) == evidence.attested_operational_day_evidence_digest
    assert payload["status"] == "READY"
    assert payload["metadata"] == [["purpose", "attested operational day"]]


def test_metadata_normalized_sorted() -> None:
    evidence = _build(metadata={"zeta": "2", "alpha": "1"})
    assert evidence.metadata == (("alpha", "1"), ("zeta", "2"))


def test_tampered_digest_detectable() -> None:
    evidence = _build()
    tampered = replace(evidence, operational_readiness=True)
    assert paper_attested_operational_day_evidence_digest(tampered) != evidence.attested_operational_day_evidence_digest


# --------------------------------------------------------------------------------------------------
# 22-23. Field invariants
# --------------------------------------------------------------------------------------------------

_FALSE_FIELDS = (
    "operational_day_machine_proven",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "real_wall_clock_used",
    "real_time_paper_operation_proven",
    "operational_readiness",
    "prdv4_stage4_complete",
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
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


def test_false_fields_on_ready_path() -> None:
    evidence = _build()
    assert evidence.ready is True
    for field_name in _FALSE_FIELDS:
        assert getattr(evidence, field_name) is False, field_name
    assert evidence.paper_only is True
    assert evidence.session_windows_consumed is True
    assert evidence.operator_attested_operational_day is True


def test_false_fields_on_rejected_path() -> None:
    evidence = _build(expected_session_window_digests=(_HEX_B,))
    assert evidence.status is PaperAttestedOperationalDayEvidenceStatus.REJECTED
    for field_name in _FALSE_FIELDS:
        assert getattr(evidence, field_name) is False, field_name
    assert evidence.operator_attested_operational_day is False


def test_machine_proof_default_is_false() -> None:
    field_map = {field.name: field for field in fields(PaperAttestedOperationalDayEvidence)}
    assert field_map["machine_time_origin_proven"].default is False
    assert field_map["prdv4_stage4_complete"].default is False


# --------------------------------------------------------------------------------------------------
# 24. AST / source forbidden surface
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(operational_module.__file__).read_text(encoding="utf-8")


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
    for forbidden in ("open", "Path", "time_ns", "now", "utcnow", "time", "monotonic", "perf_counter"):
        assert forbidden not in call_names, forbidden


def test_no_completion_or_machine_true_assignment_in_source() -> None:
    source = _module_source()
    assert "machine_time_origin_proven: bool = False" in source
    assert re.search(r"prdv4_stage4_complete\s*=\s*True", source) is None
    assert '"prdv4_stage4_complete": True' not in source


def test_no_false_field_assigned_true_in_source() -> None:
    source = _module_source()
    for field_name in _FALSE_FIELDS:
        assert re.search(rf"{field_name}\s*=\s*True", source) is None, field_name
        assert re.search(rf'"{field_name}":\s*True', source) is None, field_name
