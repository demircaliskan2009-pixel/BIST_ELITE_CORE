"""Tests for deterministic paper daily return-series evidence."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnBucket,
    PaperDailyReturnSeriesEvidenceError,
    PaperDailyReturnSeriesEvidenceStatus,
    build_paper_daily_return_series_evidence,
    paper_daily_return_series_evidence_digest,
    paper_daily_return_series_evidence_to_dict,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.paper_return_series_methodology import (
    PaperReturnSeriesMethodology,
    build_paper_return_series_methodology,
    paper_return_series_methodology_digest,
)

_DAY_NS = 86_400_000_000_000
_HEX_A = "a" * 64


class _LiarStr(str):
    """A string subclass that defeats equality but not exact type checks."""

    def __eq__(self, other: object) -> bool:  # noqa: D401 - test double
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


class _IntSub(int):
    """An int subclass rejected by exact integer checks."""


@dataclass(frozen=True)
class _MethodologySub(PaperReturnSeriesMethodology):
    """Subclass test double; exact type is required."""


@dataclass(frozen=True)
class _WindowSub(PaperDeterministicTimeWindowEvidence):
    """Subclass test double; exact type is required."""


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _methodology(**overrides: object) -> PaperReturnSeriesMethodology:
    payload: dict[str, object] = {
        "methodology_id": "method-1",
        "correlation_id": "corr-1",
        "mtm_policy_id": "mtm-policy-1",
        "fee_policy_id": "fee-policy-1",
        "funding_policy_id": "funding-policy-1",
        "mark_policy_id": "mark-policy-1",
        "exposure_policy_id": "exposure-policy-1",
        "liquidation_policy_id": "liquidation-policy-1",
        "risk_free_policy_id": "risk-free-policy-1",
    }
    payload.update(overrides)
    return build_paper_return_series_methodology(**payload)  # type: ignore[arg-type]


def _reseal_methodology(methodology: PaperReturnSeriesMethodology) -> PaperReturnSeriesMethodology:
    return replace(methodology, methodology_digest=paper_return_series_methodology_digest(methodology))


def _window(*, days: int = 2, **overrides: object) -> PaperDeterministicTimeWindowEvidence:
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
    fields_payload.update(overrides)
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **fields_payload)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _bucket_at(bucket_id: str, start_ns: object, end_ns: object, start: str, end: str) -> PaperDailyReturnBucket:
    seed = PaperDailyReturnBucket(
        bucket_id=bucket_id,
        bucket_start_ns=start_ns,  # type: ignore[arg-type]
        bucket_end_ns=end_ns,  # type: ignore[arg-type]
        normalized_index_start=start,
        normalized_index_end=end,
        bucket_digest="",
    )
    return replace(seed, bucket_digest=series_module._bucket_digest(seed))  # noqa: SLF001


def _bucket(day: int, start: str, end: str) -> PaperDailyReturnBucket:
    return _bucket_at(f"bucket-{day + 1}", day * _DAY_NS, (day + 1) * _DAY_NS, start, end)


def _buckets() -> tuple[PaperDailyReturnBucket, ...]:
    return (_bucket(0, "1", "1.01"), _bucket(1, "1.01", "1.0201"))


def _build(**overrides: object):
    methodology = overrides.pop("methodology", _methodology())
    window = overrides.pop("time_window", _window())
    payload: dict[str, object] = {
        "expected_methodology_digest": methodology.methodology_digest,
        "expected_time_window_digest": window.time_window_digest,
        "series_id": "series-1",
        "correlation_id": "corr-1",
        "daily_buckets": _buckets(),
        "metadata": {"purpose": "daily return series"},
    }
    payload.update(overrides)
    return build_paper_daily_return_series_evidence(methodology, window, **payload)  # type: ignore[arg-type]


def test_happy_path_computes_daily_return_series() -> None:
    result = _build()
    payload = paper_daily_return_series_evidence_to_dict(result)

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.READY
    assert result.ready is True
    assert result.bucket_count == 2
    assert result.return_count == 2
    assert result.daily_returns == ("0.01", "0.01")
    assert result.normalized_index_start == "1"
    assert result.normalized_index_end == "1.0201"
    assert result.calendar == "UTC"
    assert result.bucket_frequency == "1d_utc"
    assert result.bucket_duration_ns == _DAY_NS
    assert result.required_consecutive_bucket_count == 30
    assert result.return_basis == "normalized_paper_equity_index"
    assert result.methodology_digest == result.expected_methodology_digest
    assert result.time_window_digest == result.expected_time_window_digest
    assert result.metrics_summary_digest == _HEX_A
    assert result.sample_eligible is True
    assert result.reason_codes == ()
    assert _is_hex64(result.series_digest)
    assert payload["status"] == "READY"
    assert payload["daily_returns"] == ["0.01", "0.01"]
    assert payload["buckets"][0]["bucket_id"] == "bucket-1"  # type: ignore[index]`n    assert _is_hex64(payload["buckets"][0]["bucket_digest"])  # type: ignore[index]`n    assert payload["buckets"][0]["bucket_start_ns"] == 0  # type: ignore[index]
    assert payload["series_digest"] == paper_daily_return_series_evidence_digest(result)


def test_non_overclaim_flags_and_return_series_flag() -> None:
    payload = paper_daily_return_series_evidence_to_dict(_build())

    assert payload["return_series_computed"] is True
    assert payload["daily_returns_computed"] is True
    assert payload["daily_return_series_evidence"] is True
    assert payload["paper_only"] is True
    for flag in (
        "sharpe_computed",
        "paper_sharpe_computed",
        "thirty_day_gate_satisfied",
        "thirty_day_gate_decided",
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
        "timestamp_origin_proven",
        "real_account_equity_used",
        "real_capital_used",
    ):
        assert payload[flag] is False
    for forbidden_key in ("paper_sharpe", "sharpe", "thirty_day_gate_decision", "Stage4PaperSummary"):
        assert forbidden_key not in payload


def test_thirty_daily_buckets_still_do_not_satisfy_gate() -> None:
    buckets = tuple(_bucket(day, "1", "1") for day in range(30))
    result = _build(time_window=_window(days=30), daily_buckets=buckets)

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.READY
    assert result.bucket_count == 30
    assert result.daily_returns == tuple("0" for _ in range(30))
    assert result.thirty_day_gate_satisfied is False
    assert result.thirty_day_gate_decided is False
    assert result.comparison_ready is False
    assert result.stage4_comparator_invoked is False


def test_high_scale_leading_zero_return_is_exact() -> None:
    result = _build(
        time_window=_window(days=1),
        daily_buckets=(
            _bucket(
                0,
                "1",
                "1.000000000000000000000000000001",
            ),
        ),
    )

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.READY
    assert result.daily_returns == ("0.000000000000000000000000000001",)


def test_non_terminating_return_fails_closed() -> None:
    result = _build(
        time_window=_window(days=2),
        daily_buckets=(
            _bucket(0, "1", "3"),
            _bucket(1, "3", "4"),
        ),
    )

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:return_non_terminating" in result.reason_codes

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:return_non_terminating" in result.reason_codes


def test_digest_is_deterministic_and_excludes_self_digest() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    assert first.series_digest == second.series_digest
    assert paper_daily_return_series_evidence_digest(first) == first.series_digest

    resealed = replace(first, series_digest="0" * 64)
    assert paper_daily_return_series_evidence_digest(resealed) == first.series_digest


@pytest.mark.parametrize(
    "override",
    [
        {"series_id": "series-2"},
        {"daily_buckets": (_bucket(0, "1", "1.02"), _bucket(1, "1.02", "1.0404"))},
        {"metadata": {"purpose": "daily return series", "review": "one"}},
    ],
)
def test_digest_changes_when_critical_fields_change(override: dict[str, object]) -> None:
    base = _build()
    other = _build(**override)
    assert base.series_digest != other.series_digest


def test_exact_methodology_type_required() -> None:
    methodology = _methodology()
    values = {field.name: getattr(methodology, field.name) for field in fields(methodology)}
    sub = _MethodologySub(**values)

    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="methodology_malformed"):
        _build(methodology=sub)


def test_exact_time_window_type_required() -> None:
    window = _window()
    values = {field.name: getattr(window, field.name) for field in fields(window)}
    sub = _WindowSub(**values)

    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="time_window_malformed"):
        _build(time_window=sub)


def test_methodology_digest_mismatch_rejects() -> None:
    result = _build(expected_methodology_digest="b" * 64)
    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:methodology_digest_mismatch" in result.reason_codes


def test_methodology_unsafe_or_mtm_tamper_rejects() -> None:
    forged = _reseal_methodology(replace(_methodology(), mark_to_market_required=False, return_series_computed=True))
    result = _build(methodology=forged, expected_methodology_digest=forged.methodology_digest)

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:methodology_mtm_policy_mismatch" in result.reason_codes
    assert "paper_daily_return_series_evidence:methodology_unsafe_flags" in result.reason_codes


def test_time_window_digest_mismatch_rejects() -> None:
    result = _build(expected_time_window_digest="b" * 64)
    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:time_window_digest_mismatch" in result.reason_codes


def test_time_window_sample_or_flag_tamper_rejects() -> None:
    forged = replace(_window(), sample_eligible=False, reason_codes=("window_not_sample_eligible",))
    forged = replace(forged, time_window_digest=paper_deterministic_time_window_evidence_digest(forged))
    result = _build(time_window=forged, expected_time_window_digest=forged.time_window_digest)

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:time_window_not_sample_eligible" in result.reason_codes

    unsafe = replace(_window(), return_series_computed=True)
    unsafe = replace(unsafe, time_window_digest=paper_deterministic_time_window_evidence_digest(unsafe))
    unsafe_result = _build(time_window=unsafe, expected_time_window_digest=unsafe.time_window_digest)
    assert unsafe_result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:time_window_unsafe_flags" in unsafe_result.reason_codes


def test_methodology_id_and_correlation_mismatch_reject() -> None:
    methodology = _methodology(methodology_id="method-2")
    result = _build(methodology=methodology, expected_methodology_digest=methodology.methodology_digest)
    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:methodology_id_mismatch" in result.reason_codes

    corr_result = _build(correlation_id="corr-2")
    assert corr_result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:correlation_id_mismatch" in corr_result.reason_codes


def test_empty_buckets_reject() -> None:
    result = _build(time_window=_window(days=0, stopped_at_ns=0, window_duration_ns=0), daily_buckets=())
    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert result.return_series_computed is False
    assert result.daily_returns_computed is False
    assert "paper_daily_return_series_evidence:buckets_empty" in result.reason_codes


@pytest.mark.parametrize(
    ("buckets", "reason"),
    [
        (
            (_bucket_at("bucket-short", 0, _DAY_NS - 1, "1", "1.01"),),
            "paper_daily_return_series_evidence:bucket_duration_invalid",
        ),
        (
            (_bucket(0, "1", "1.01"), _bucket_at("bucket-gap", 2 * _DAY_NS, 3 * _DAY_NS, "1.01", "1.02")),
            "paper_daily_return_series_evidence:bucket_sequence_non_contiguous",
        ),
        (
            (_bucket(0, "1", "1.01"), _bucket(1, "1.02", "1.03")),
            "paper_daily_return_series_evidence:normalized_index_chain_mismatch",
        ),
        (
            (_bucket(0, "1.0", "1.01"), _bucket(1, "1.01", "1.0201")),
            "paper_daily_return_series_evidence:bucket_index_noncanonical",
        ),
        (
            (_bucket(0, "0", "1.01"), _bucket(1, "1.01", "1.0201")),
            "paper_daily_return_series_evidence:bucket_index_nonpositive",
        ),
    ],
)
def test_bucket_invariants_reject(buckets: tuple[PaperDailyReturnBucket, ...], reason: str) -> None:
    result = _build(daily_buckets=buckets)
    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert reason in result.reason_codes


def test_bucket_window_coverage_rejects() -> None:
    result = _build(time_window=_window(days=3), daily_buckets=_buckets())
    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:bucket_window_end_mismatch" in result.reason_codes
    assert "paper_daily_return_series_evidence:bucket_window_duration_mismatch" in result.reason_codes


def test_shifted_utc_day_aligned_buckets_reject() -> None:
    shifted_window = _window(
        started_at_ns=1,
        stopped_at_ns=(2 * _DAY_NS) + 1,
        window_duration_ns=2 * _DAY_NS,
    )
    result = _build(
        time_window=shifted_window,
        daily_buckets=(
            _bucket_at("bucket-1", 1, _DAY_NS + 1, "1", "1.01"),
            _bucket_at("bucket-2", _DAY_NS + 1, (2 * _DAY_NS) + 1, "1.01", "1.0201"),
        ),
    )

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:time_window_utc_day_alignment_invalid" in result.reason_codes
    assert "paper_daily_return_series_evidence:bucket_utc_day_alignment_invalid" in result.reason_codes


def test_first_bucket_must_match_methodology_normalized_start() -> None:
    result = _build(
        daily_buckets=(
            _bucket_at("bucket-1", 0, _DAY_NS, "2", "2.02"),
            _bucket_at("bucket-2", _DAY_NS, 2 * _DAY_NS, "2.02", "2.0402"),
        )
    )

    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:normalized_index_start_mismatch" in result.reason_codes


def test_bucket_id_and_digest_invariants_reject() -> None:
    digest_mismatch = replace(_bucket(0, "1", "1.01"), normalized_index_end="1.02")
    result = _build(daily_buckets=(digest_mismatch, _bucket(1, "1.01", "1.0201")))
    assert result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:bucket_digest_mismatch" in result.reason_codes

    malformed_digest = replace(_bucket(0, "1", "1.01"), bucket_digest="bad")
    malformed_result = _build(daily_buckets=(malformed_digest, _bucket(1, "1.01", "1.0201")))
    assert malformed_result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:bucket_digest_invalid" in malformed_result.reason_codes

    duplicate_id = (
        _bucket_at("duplicate-bucket", 0, _DAY_NS, "1", "1.01"),
        _bucket_at("duplicate-bucket", _DAY_NS, 2 * _DAY_NS, "1.01", "1.0201"),
    )
    duplicate_id_result = _build(daily_buckets=duplicate_id)
    assert duplicate_id_result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:duplicate_bucket_id" in duplicate_id_result.reason_codes

    duplicate_digest_result = _build(daily_buckets=(_bucket(0, "1", "1.01"), _bucket(0, "1", "1.01")))
    assert duplicate_digest_result.status is PaperDailyReturnSeriesEvidenceStatus.REJECTED
    assert "paper_daily_return_series_evidence:duplicate_bucket_digest" in duplicate_digest_result.reason_codes

    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="bucket_id_invalid"):
        _build(daily_buckets=(_bucket_at(" bucket-1 ", 0, _DAY_NS, "1", "1.01"),))


def test_malformed_bucket_or_id_inputs_raise() -> None:
    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="bucket_malformed"):
        _build(daily_buckets=({"not": "a-bucket"},))
    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="bucket_timestamp_invalid"):
        _build(daily_buckets=(_bucket_at("bucket-bad-timestamp", _IntSub(0), _DAY_NS, "1", "1.01"),))
    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="series_id_invalid"):
        _build(series_id=_LiarStr("series-1"))
    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="expected_methodology_digest_invalid"):
        _build(expected_methodology_digest="not-a-digest")


@pytest.mark.parametrize(
    ("field_name", "field_value", "reason"),
    [
        ("series_id", "series-1\x07", "series_id_invalid"),
        ("series_id", "series\n1", "series_id_invalid"),
        ("series_id", "series\t1", "series_id_invalid"),
        ("correlation_id", "corr-1\x07", "correlation_id_invalid"),
        ("correlation_id", "corr\n1", "correlation_id_invalid"),
        ("correlation_id", "corr\t1", "correlation_id_invalid"),
    ],
)
def test_control_character_series_and_correlation_ids_reject(field_name: str, field_value: str, reason: str) -> None:
    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match=reason):
        _build(**{field_name: field_value})


@pytest.mark.parametrize("bucket_id", ["bucket-1\x07", "bucket\n1", "bucket\t1"])
def test_control_character_bucket_ids_reject_even_with_matching_digest(
    bucket_id: str,
) -> None:
    forged = _bucket_at(bucket_id, 0, _DAY_NS, "1", "1.01")

    with pytest.raises(PaperDailyReturnSeriesEvidenceError, match="bucket_id_invalid"):
        _build(
            daily_buckets=(
                forged,
                _bucket_at("bucket-2", _DAY_NS, 2 * _DAY_NS, "1.01", "1.0201"),
            )
        )


@pytest.mark.parametrize(
    "override",
    [
        {"series_id": "live-series"},
        {"correlation_id": "shadow-corr"},
        {"metadata": {"path": "crypto_core.execution.paper_adapter"}},
        {"metadata": {"venue": "BIST"}},
        {"metadata": {"source": "time.time_ns"}},
        {"metadata": {"source": "datetime.now"}},
    ],
)
def test_forbidden_scope_and_clock_tokens_raise(override: dict[str, object]) -> None:
    with pytest.raises(PaperDailyReturnSeriesEvidenceError):
        _build(**override)


def test_inputs_not_mutated_and_output_frozen() -> None:
    buckets = list(_buckets())
    metadata = {"b": "2", "a": "1"}
    result = _build(daily_buckets=buckets, metadata=metadata)

    assert buckets == list(_buckets())
    assert metadata == {"b": "2", "a": "1"}
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


def test_serializer_is_json_ready_and_matches_dataclass_fields() -> None:
    result = _build()
    payload = paper_daily_return_series_evidence_to_dict(result)
    dataclass_field_names = {field.name for field in fields(result)}

    assert set(payload) == dataclass_field_names
    assert payload["status"] == result.status.value
    assert payload["metadata"] == [["purpose", "daily return series"]]


def test_public_api_exact() -> None:
    assert set(series_module.__all__) == {
        "PaperDailyReturnBucket",
        "PaperDailyReturnSeriesEvidence",
        "PaperDailyReturnSeriesEvidenceError",
        "PaperDailyReturnSeriesEvidenceStatus",
        "build_paper_daily_return_series_evidence",
        "paper_daily_return_series_evidence_digest",
        "paper_daily_return_series_evidence_to_dict",
    }


def test_source_has_no_forbidden_runtime_or_stage4_execution_surfaces() -> None:
    source = Path(series_module.__file__).read_text(encoding="utf-8")
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
