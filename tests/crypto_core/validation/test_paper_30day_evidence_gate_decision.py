"""Tests for deterministic paper 30-day evidence gate decision."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_30day_evidence_gate_decision as gate_module
from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecisionError,
    PaperThirtyDayEvidenceGateDecisionStatus,
    build_paper_30day_evidence_gate_decision,
    paper_30day_evidence_gate_decision_digest,
    paper_30day_evidence_gate_decision_to_dict,
)
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnBucket,
    PaperDailyReturnSeriesEvidence,
    PaperDailyReturnSeriesEvidenceStatus,
    build_paper_daily_return_series_evidence,
    paper_daily_return_series_evidence_digest,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.paper_return_series_methodology import (
    build_paper_return_series_methodology,
)

_DAY_NS = 86_400_000_000_000
_HEX_A = "a" * 64


class _LiarStr(str):
    """A string subclass rejected by exact string checks."""


@dataclass(frozen=True)
class _SeriesSub(PaperDailyReturnSeriesEvidence):
    """Subclass test double; exact upstream type is required."""


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _methodology():
    return build_paper_return_series_methodology(
        methodology_id="method-1",
        correlation_id="corr-1",
        mtm_policy_id="mtm-policy-1",
        fee_policy_id="fee-policy-1",
        funding_policy_id="funding-policy-1",
        mark_policy_id="mark-policy-1",
        exposure_policy_id="exposure-policy-1",
        liquidation_policy_id="liquidation-policy-1",
        risk_free_policy_id="risk-free-policy-1",
    )


def _window(*, days: int = 30) -> PaperDeterministicTimeWindowEvidence:
    fields_payload: dict[str, object] = {
        "schema_version": "paper-deterministic-time-window-evidence.v1",
        "time_window_version": "paper-deterministic-time-window.v1",
        "status": PaperDeterministicTimeWindowEvidenceStatus.READY,
        "ready": True,
        "window_id": "window-1",
        "methodology_id": "method-1",
        "timestamp_policy": "injected_deterministic_ns.v1",
        "run_id": "run-1",
        "aggregate_id": "agg-1",
        "correlation_id": "corr-1",
        "market_symbol": "BTC-PERPETUAL",
        "expected_metrics_summary_digest": _HEX_A,
        "metrics_summary_digest": _HEX_A,
        "summary_ready": True,
        "summary_readiness_verdict": "PAPER_STAGE4_CANDIDATE",
        "started_at_ns": 0,
        "stopped_at_ns": days * _DAY_NS,
        "window_duration_ns": days * _DAY_NS,
        "sample_observation_count": days,
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
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **fields_payload)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _bucket(day: int, start: str = "1", end: str = "1") -> PaperDailyReturnBucket:
    seed = PaperDailyReturnBucket(
        bucket_id=f"bucket-{day + 1}",
        bucket_start_ns=day * _DAY_NS,
        bucket_end_ns=(day + 1) * _DAY_NS,
        normalized_index_start=start,
        normalized_index_end=end,
        bucket_digest="",
    )
    return replace(seed, bucket_digest=series_module._bucket_digest(seed))  # noqa: SLF001


def _buckets(days: int = 30) -> tuple[PaperDailyReturnBucket, ...]:
    return tuple(_bucket(day) for day in range(days))


def _series(*, days: int = 30, buckets: tuple[PaperDailyReturnBucket, ...] | None = None):
    methodology = _methodology()
    window = _window(days=days)
    return build_paper_daily_return_series_evidence(
        methodology,
        window,
        expected_methodology_digest=methodology.methodology_digest,
        expected_time_window_digest=window.time_window_digest,
        series_id="series-1",
        correlation_id="corr-1",
        daily_buckets=_buckets(days) if buckets is None else buckets,
        metadata={"purpose": "daily return series"},
    )


def _reseal_series(series: PaperDailyReturnSeriesEvidence) -> PaperDailyReturnSeriesEvidence:
    return replace(series, series_digest=paper_daily_return_series_evidence_digest(series))


def _build(series: PaperDailyReturnSeriesEvidence | None = None, **overrides: object):
    current = _series() if series is None else series
    payload: dict[str, object] = {
        "expected_series_digest": current.series_digest,
        "gate_id": "gate-1",
        "correlation_id": "corr-1",
        "metadata": {"purpose": "paper 30day gate"},
    }
    payload.update(overrides)
    return build_paper_30day_evidence_gate_decision(current, **payload)  # type: ignore[arg-type]


def test_happy_path_thirty_day_gate_satisfied() -> None:
    result = _build()
    payload = paper_30day_evidence_gate_decision_to_dict(result)

    assert result.status is PaperThirtyDayEvidenceGateDecisionStatus.READY
    assert result.ready is True
    assert result.thirty_day_gate_satisfied is True
    assert result.thirty_day_gate_decided is True
    assert result.thirty_day_evidence_gate_decision is True
    assert result.bucket_count == 30
    assert result.daily_return_count == 30
    assert result.gate_bucket_count_used == 30
    assert result.gate_daily_return_count_used == 30
    assert result.bucket_ids[0] == "bucket-1"
    assert result.bucket_ids[-1] == "bucket-30"
    assert result.first_bucket_start_ns == 0
    assert result.last_bucket_end_ns == 30 * _DAY_NS
    assert result.window_duration_ns == 30 * _DAY_NS
    assert result.reason_codes == ()
    assert _is_hex64(result.decision_digest)
    assert payload["status"] == "READY"
    assert payload["decision_digest"] == paper_30day_evidence_gate_decision_digest(result)


def test_non_overclaim_flags_are_false_and_digest_bound() -> None:
    result = _build()
    payload = paper_30day_evidence_gate_decision_to_dict(result)

    assert payload["paper_only"] is True
    assert payload["daily_return_series_evidence_consumed"] is True
    assert payload["thirty_day_evidence_gate_decision"] is True
    assert payload["thirty_day_gate_decided"] is True
    assert payload["thirty_day_gate_satisfied"] is True
    for flag in (
        "sharpe_computed",
        "paper_sharpe_computed",
        "comparison_ready",
        "stage4_comparator_invoked",
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "operational_readiness",
        "deribit_ready",
        "profitability_proven",
        "edge_proven",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "real_wall_clock_used",
        "real_account_equity_used",
        "real_capital_used",
    ):
        assert payload[flag] is False
    for forbidden_key in ("paper_sharpe", "sharpe_ratio", "comparator_result", "Stage4PaperSummary"):
        assert forbidden_key not in payload

    tampered = replace(result, profitability_proven=True)
    assert paper_30day_evidence_gate_decision_digest(tampered) != result.decision_digest


def test_exact_upstream_type_required() -> None:
    series = _series()
    values = {field.name: getattr(series, field.name) for field in fields(series)}
    sub = _SeriesSub(**values)

    with pytest.raises(PaperThirtyDayEvidenceGateDecisionError, match="series_malformed"):
        _build(series=sub)


def test_upstream_digest_recomputed_and_mismatch_rejects() -> None:
    result = _build(expected_series_digest="b" * 64)

    assert result.status is PaperThirtyDayEvidenceGateDecisionStatus.REJECTED
    assert result.thirty_day_gate_satisfied is False
    assert "paper_30day_evidence_gate_decision:series_digest_mismatch" in result.reason_codes


def test_unsafe_upstream_flag_rejects_even_when_resealed() -> None:
    unsafe = _reseal_series(replace(_series(), live_ready=True, sharpe_computed=True))
    result = _build(series=unsafe)

    assert result.status is PaperThirtyDayEvidenceGateDecisionStatus.REJECTED
    assert result.thirty_day_gate_satisfied is False
    assert "paper_30day_evidence_gate_decision:series_unsafe_flags" in result.reason_codes


def test_upstream_not_ready_rejects_even_when_digest_valid() -> None:
    rejected = _reseal_series(
        replace(
            _series(),
            status=PaperDailyReturnSeriesEvidenceStatus.REJECTED,
            ready=False,
            reason_codes=("paper_daily_return_series_evidence:test_rejection",),
            return_series_computed=False,
            daily_returns_computed=False,
        )
    )
    result = _build(series=rejected)

    assert result.status is PaperThirtyDayEvidenceGateDecisionStatus.REJECTED
    assert "paper_30day_evidence_gate_decision:series_not_ready" in result.reason_codes
    assert "paper_30day_evidence_gate_decision:series_unsafe_flags" in result.reason_codes


@pytest.mark.parametrize("days", [29, 31])
def test_exact_thirty_bucket_policy_rejects_non_thirty_series(days: int) -> None:
    result = _build(series=_series(days=days))

    assert result.status is PaperThirtyDayEvidenceGateDecisionStatus.REJECTED
    assert result.thirty_day_gate_satisfied is False
    assert "paper_30day_evidence_gate_decision:insufficient_bucket_count" in result.reason_codes
    assert "paper_30day_evidence_gate_decision:insufficient_daily_return_count" in result.reason_codes


def test_daily_return_count_mismatch_rejects_digest_valid_forgery() -> None:
    forged = _reseal_series(replace(_series(), return_count=29))
    result = _build(series=forged)

    assert result.status is PaperThirtyDayEvidenceGateDecisionStatus.REJECTED
    assert "paper_30day_evidence_gate_decision:insufficient_daily_return_count" in result.reason_codes
    assert "paper_30day_evidence_gate_decision:daily_return_count_mismatch" in result.reason_codes


def test_bucket_payload_forgery_rejects_even_when_series_resealed() -> None:
    series = _series()
    forged_bucket = replace(series.buckets[0], bucket_end_ns=_DAY_NS - 1)
    forged = _reseal_series(replace(series, buckets=(forged_bucket, *series.buckets[1:])))
    result = _build(series=forged)

    assert result.status is PaperThirtyDayEvidenceGateDecisionStatus.REJECTED
    assert "paper_30day_evidence_gate_decision:bucket_digest_mismatch" in result.reason_codes
    assert "paper_30day_evidence_gate_decision:bucket_duration_invalid" in result.reason_codes


def test_changed_upstream_digest_changes_gate_digest() -> None:
    base = _build()
    changed_series = _series(
        buckets=(
            _bucket(0, "1", "2"),
            _bucket(1, "2", "2"),
            *_buckets(28)[2:],
        )
    )
    changed = _build(series=changed_series)

    assert base.series_digest != changed.series_digest
    assert base.decision_digest != changed.decision_digest


def test_digest_is_deterministic_and_excludes_only_self_digest() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})

    assert first.decision_digest == second.decision_digest
    assert paper_30day_evidence_gate_decision_digest(first) == first.decision_digest
    resealed = replace(first, decision_digest="0" * 64)
    assert paper_30day_evidence_gate_decision_digest(resealed) == first.decision_digest
    changed = _build(metadata={"a": "1", "b": "3"})
    assert changed.decision_digest != first.decision_digest


def test_output_frozen_and_inputs_not_mutated() -> None:
    series = _series()
    metadata = {"b": "2", "a": "1"}
    before_digest = series.series_digest
    result = _build(series=series, metadata=metadata)

    assert series.series_digest == before_digest
    assert metadata == {"b": "2", "a": "1"}
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "override",
    [
        {"gate_id": "live-gate"},
        {"correlation_id": "shadow-corr"},
        {"metadata": {"path": "crypto_core.execution.paper_adapter"}},
        {"metadata": {"venue": "BIST"}},
        {"metadata": {"source": "time.time_ns"}},
        {"metadata": {"source": "datetime.now"}},
    ],
)
def test_forbidden_scope_and_clock_tokens_raise(override: dict[str, object]) -> None:
    with pytest.raises(PaperThirtyDayEvidenceGateDecisionError):
        _build(**override)


def test_malformed_public_inputs_raise() -> None:
    with pytest.raises(PaperThirtyDayEvidenceGateDecisionError, match="expected_series_digest_invalid"):
        _build(expected_series_digest="not-a-digest")
    with pytest.raises(PaperThirtyDayEvidenceGateDecisionError, match="gate_id_invalid"):
        _build(gate_id=_LiarStr("gate-1"))
    with pytest.raises(PaperThirtyDayEvidenceGateDecisionError, match="metadata_malformed"):
        _build(metadata={"ok": 1})


def test_serializer_is_json_ready_and_matches_dataclass_fields() -> None:
    result = _build()
    payload = paper_30day_evidence_gate_decision_to_dict(result)
    dataclass_field_names = {field.name for field in fields(result)}

    assert set(payload) == dataclass_field_names
    assert payload["status"] == result.status.value
    assert payload["metadata"] == [["purpose", "paper 30day gate"]]
    assert payload["bucket_ids"][0] == "bucket-1"
    assert payload["daily_returns"] == ["0"] * 30


def test_public_api_exact() -> None:
    assert set(gate_module.__all__) == {
        "PaperThirtyDayEvidenceGateDecision",
        "PaperThirtyDayEvidenceGateDecisionError",
        "PaperThirtyDayEvidenceGateDecisionStatus",
        "build_paper_30day_evidence_gate_decision",
        "paper_30day_evidence_gate_decision_digest",
        "paper_30day_evidence_gate_decision_to_dict",
    }


def test_source_has_no_forbidden_runtime_or_stage4_execution_surfaces() -> None:
    source = Path(gate_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "time",
        "datetime",
        "random",
        "secrets",
        "uuid",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "threading",
        "asyncio",
        "multiprocessing",
        "subprocess",
        "os",
        "pathlib",
        "shutil",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.session",
        "crypto_core.data",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
    )
    forbidden_call_names = {
        "open",
        "Path",
        "compare_stage4",
        "Stage4PaperSummary",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == module or alias.name.startswith(f"{module}.") for module in forbidden_modules
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                node.module == module or node.module.startswith(f"{module}.") for module in forbidden_modules
            )
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names
