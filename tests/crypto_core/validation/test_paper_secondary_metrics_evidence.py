"""Tests for the SM-4 paper secondary-metrics evidence artifact."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_secondary_metrics_evidence as evidence_module
from crypto_core.validation.paper_secondary_metrics_evidence import (
    PaperSecondaryMetricsEvidenceError,
    PaperSecondaryMetricsEvidenceStatus,
    build_paper_secondary_metrics_evidence,
    paper_secondary_metrics_evidence_digest,
    paper_secondary_metrics_evidence_to_dict,
)
from crypto_core.validation.secondary_metrics_policy import (
    build_secondary_metrics_policy,
    secondary_metrics_policy_digest,
)
from crypto_core.validation.trade_record_evidence import (
    build_trade_record_evidence,
    trade_record_evidence_digest,
)

_REASON_PREFIX = "paper_secondary_metrics_evidence:"

_STRUCTURAL_FALSE_FLAGS = (
    "comparator_invoked",
    "secondary_metrics_enforced",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "pnl_authoritative",
    "edge_proven",
    "profitability_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "production_execution",
)


def _rc(code: str) -> str:
    return f"{_REASON_PREFIX}{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _policy(**overrides: object):
    payload: dict[str, object] = {
        "policy_id": "policy-1",
        "correlation_id": "corr-1",
        "expected_fill_model_parameters_digest": "a" * 64,
        "approved_hit_rate_floor": "0.500000000000000000",
        "approved_fill_rate_floor": "0.900000000000000000",
        "approved_slippage_ceiling_bps": "25.000000000000000000",
        "approved_min_decided_episode_count": 2,
        "approval_reference": "gov-sm2-1",
        "approval_digest": "b" * 64,
        "thresholds_approved": True,
    }
    payload.update(overrides)
    return build_secondary_metrics_policy(**payload)  # type: ignore[arg-type]


def _record(
    idx: int = 0,
    *,
    decided: bool = True,
    pnl: str = "5.000000000000000000",
    intended: str = "1.000000000000000000",
    filled: str = "1.000000000000000000",
    expected: str = "100.000000000000000000",
    realized: str | None = "100.100000000000000000",
    policy_id: str = "policy-1",
    **overrides: object,
):
    payload: dict[str, object] = {
        "record_id": f"rec-{idx}",
        "correlation_id": "corr-1",
        "sleeve_id": "sleeve-1",
        "policy_id": policy_id,
        "episode_id": f"ep-{idx}",
        "strategy_id": "strategy-1",
        "decision_id": f"dec-{idx}",
        "intended_quantity": intended,
        "filled_quantity": filled,
        "expected_fill_price": expected,
        "realized_fill_price": realized,
        "realized_pnl": pnl,
        "decided_episode": decided,
    }
    payload.update(overrides)
    return build_trade_record_evidence(**payload)  # type: ignore[arg-type]


def _build(policy=None, records=None, **overrides: object):
    policy = policy if policy is not None else _policy()
    records = records if records is not None else [_record(0), _record(1)]
    payload: dict[str, object] = {"evidence_id": "sm4-1", "correlation_id": "corr-1"}
    payload.update(overrides)
    return build_paper_secondary_metrics_evidence(policy, records, **payload)  # type: ignore[arg-type]


def _reseal_policy(policy, **overrides):
    """Re-seal a policy with tampered fields and a freshly recomputed self-digest."""

    tampered = replace(policy, **overrides)
    return replace(tampered, policy_digest=secondary_metrics_policy_digest(tampered))


# --- 1. Public API / happy path -----------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(evidence_module.__all__) == {
        "PaperSecondaryMetricsEvidence",
        "PaperSecondaryMetricsEvidenceError",
        "PaperSecondaryMetricsEvidenceStatus",
        "build_paper_secondary_metrics_evidence",
        "paper_secondary_metrics_evidence_digest",
        "paper_secondary_metrics_evidence_to_dict",
    }


def test_happy_metrics_ready() -> None:
    evidence = _build()
    payload = paper_secondary_metrics_evidence_to_dict(evidence)

    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_READY
    assert evidence.ready is True
    assert evidence.thresholds_cleared is True
    assert evidence.decided_episode_count == 2
    assert evidence.positive_pnl_episode_count == 2
    assert evidence.filled_episode_count == 2
    assert evidence.hit_rate == "1.000000000000000000"
    assert evidence.fill_rate_by_quantity == "1.000000000000000000"
    assert evidence.fill_rate_by_episode == "1.000000000000000000"
    assert evidence.average_slippage_bps == "10.000000000000000000"
    assert evidence.hit_rate_satisfied is True
    assert evidence.fill_rate_satisfied is True
    assert evidence.slippage_satisfied is True
    assert evidence.reason_codes == ()
    assert _is_hex64(evidence.evidence_digest)
    assert payload["evidence_digest"] == paper_secondary_metrics_evidence_digest(evidence)


def test_output_is_frozen() -> None:
    evidence = _build()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]


# --- 2. Digest / serializer ---------------------------------------------------------------------------------


def test_repeated_build_deterministic() -> None:
    assert _build().evidence_digest == _build().evidence_digest


def test_serializer_excludes_self_digest_from_recompute() -> None:
    evidence = _build()
    resealed = replace(evidence, evidence_digest="0" * 64)
    assert paper_secondary_metrics_evidence_digest(evidence) == evidence.evidence_digest
    assert paper_secondary_metrics_evidence_digest(resealed) == evidence.evidence_digest


def test_serializer_matches_dataclass_fields() -> None:
    evidence = _build()
    payload = paper_secondary_metrics_evidence_to_dict(evidence)
    assert set(payload) == {field.name for field in fields(evidence)}
    assert payload["status"] == evidence.status.value


def test_record_digests_sorted_unique() -> None:
    evidence = _build()
    assert list(evidence.record_digests) == sorted(evidence.record_digests)
    assert len(set(evidence.record_digests)) == len(evidence.record_digests)


def test_digest_changes_on_tamper() -> None:
    evidence = _build()
    tampered = replace(evidence, prdv4_stage4_complete=True)
    assert paper_secondary_metrics_evidence_digest(tampered) != evidence.evidence_digest


# --- 3. Malformed caller input (raise) ----------------------------------------------------------------------


def test_policy_wrong_type_raises() -> None:
    with pytest.raises(PaperSecondaryMetricsEvidenceError):
        build_paper_secondary_metrics_evidence("policy", [_record(0)], evidence_id="e", correlation_id="c")  # type: ignore[arg-type]


def test_records_wrong_type_raises() -> None:
    with pytest.raises(PaperSecondaryMetricsEvidenceError):
        build_paper_secondary_metrics_evidence(_policy(), "records", evidence_id="e", correlation_id="c")  # type: ignore[arg-type]


def test_empty_records_raises() -> None:
    with pytest.raises(PaperSecondaryMetricsEvidenceError):
        build_paper_secondary_metrics_evidence(_policy(), [], evidence_id="e", correlation_id="c")


def test_record_wrong_element_type_raises() -> None:
    with pytest.raises(PaperSecondaryMetricsEvidenceError):
        build_paper_secondary_metrics_evidence(_policy(), [_record(0), "x"], evidence_id="e", correlation_id="c")  # type: ignore[list-item]


@pytest.mark.parametrize("override", [{"evidence_id": "  "}, {"correlation_id": ""}, {"metadata": {"k": 1}}])
def test_malformed_scope_raises(override: dict[str, object]) -> None:
    with pytest.raises(PaperSecondaryMetricsEvidenceError):
        _build(**override)


def test_forbidden_token_in_metadata_raises() -> None:
    with pytest.raises(PaperSecondaryMetricsEvidenceError):
        _build(metadata={"source": "order_router"})


# --- 4. Trust boundary (REJECTED) ---------------------------------------------------------------------------


def test_policy_digest_mismatch_rejects() -> None:
    resealed = replace(_policy(), policy_digest="0" * 64)
    evidence = _build(policy=resealed)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("policy_digest_mismatch") in evidence.reason_codes


def test_unapproved_thresholds_rejected() -> None:
    rejected_policy = _policy(thresholds_approved=False)
    evidence = _build(policy=rejected_policy)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("policy_not_ready") in evidence.reason_codes


def test_unsafe_policy_flags_rejects() -> None:
    tampered = replace(_policy(), prdv4_stage4_complete=True)
    tampered = replace(tampered, policy_digest=secondary_metrics_policy_digest(tampered))
    evidence = _build(policy=tampered)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("policy_unsafe_flags") in evidence.reason_codes


def test_resealed_policy_thresholds_not_approved_rejects() -> None:
    tampered = _reseal_policy(_policy(), thresholds_approved=False)

    evidence = _build(policy=tampered)

    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.ready is False
    assert evidence.status is not PaperSecondaryMetricsEvidenceStatus.METRICS_READY
    assert _rc("policy_approval_invalid") in evidence.reason_codes


def test_resealed_policy_missing_approval_metadata_rejects() -> None:
    tampered = _reseal_policy(_policy(), approval_reference=None, approval_digest=None)

    evidence = _build(policy=tampered)

    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.ready is False
    assert _rc("policy_approval_invalid") in evidence.reason_codes


@pytest.mark.parametrize(
    "override",
    [
        {"approved_hit_rate_floor": "0.5"},
        {"approved_fill_rate_floor": "0.9"},
        {"approved_slippage_ceiling_bps": "25"},
    ],
)
def test_resealed_policy_non_scale18_thresholds_reject(override: dict[str, object]) -> None:
    tampered = _reseal_policy(_policy(), **override)

    evidence = _build(policy=tampered)

    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.ready is False
    assert _rc("policy_threshold_invalid") in evidence.reason_codes


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"policy_version": "secondary-metrics-policy.v2"}, "policy_version_invalid"),
        ({"hit_rate_definition": "wins_over_decided_episodes.v1"}, "policy_definition_mismatch"),
        ({"fill_rate_definition": "filled_episodes_only.v1"}, "policy_definition_mismatch"),
        ({"slippage_definition": "unsigned_bps.v1"}, "policy_definition_mismatch"),
        (
            {"expected_fill_model_reference": "crypto_core.execution.fill_pricer.FillPricer.v2"},
            "policy_expected_fill_model_reference_invalid",
        ),
        ({"expected_fill_model_parameters_digest": "g" * 64}, "policy_expected_fill_model_parameters_digest_invalid"),
        (
            {"decimal_policy": "decimal_quantized_scale_9_round_half_even_fraction_intermediates.v1"},
            "policy_decimal_policy_mismatch",
        ),
        ({"decimal_scale": 9}, "policy_decimal_policy_mismatch"),
        ({"decimal_rounding": "ROUND_HALF_UP"}, "policy_decimal_policy_mismatch"),
        ({"fraction_intermediates_required": False}, "policy_decimal_policy_mismatch"),
        ({"approved_hit_rate_floor": "1.000000000000000001"}, "policy_threshold_invalid"),
        ({"approved_fill_rate_floor": "1.000000000000000001"}, "policy_threshold_invalid"),
        ({"approved_slippage_ceiling_bps": "-0.000000000000000001"}, "policy_threshold_invalid"),
        ({"approved_min_decided_episode_count": True}, "policy_min_decided_episode_count_invalid"),
    ],
)
def test_resealed_policy_decimal_or_definition_mismatch_rejects(override: dict[str, object], reason: str) -> None:
    tampered = _reseal_policy(_policy(), **override)

    evidence = _build(policy=tampered)

    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.ready is False
    assert _rc(reason) in evidence.reason_codes


def test_record_digest_mismatch_rejects() -> None:
    resealed = replace(_record(0), record_digest="0" * 64)
    evidence = _build(records=[resealed, _record(1)])
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("record_digest_mismatch") in evidence.reason_codes


def test_record_not_ready_rejects() -> None:
    rejected_record = _record(0, intended="1.000000000000000000", filled="2.000000000000000000")
    evidence = _build(records=[rejected_record, _record(1)])
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("record_not_ready") in evidence.reason_codes


def test_record_policy_id_mismatch_rejects() -> None:
    evidence = _build(records=[_record(0, policy_id="other"), _record(1)])
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("record_policy_id_mismatch") in evidence.reason_codes


def test_unsafe_record_flags_rejects() -> None:
    tampered = replace(_record(0), order_created=True)
    tampered = replace(tampered, record_digest=trade_record_evidence_digest(tampered))
    evidence = _build(records=[tampered, _record(1)])
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("record_unsafe_flags") in evidence.reason_codes


def test_duplicate_record_id_rejects() -> None:
    dup = _record(0, episode_id="ep-x")
    other = _record(0, episode_id="ep-y")  # same record_id rec-0, different digest
    evidence = _build(records=[dup, other])
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("duplicate_record_id") in evidence.reason_codes


def test_duplicate_record_digest_rejects() -> None:
    rec = _record(0)
    evidence = _build(records=[rec, rec])
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("duplicate_record_digest") in evidence.reason_codes


def _reseal(record, **overrides):
    """Re-seal a record with tampered fields and a freshly recomputed self-digest (digest stays valid)."""
    tampered = replace(record, **overrides)
    return replace(tampered, record_digest=trade_record_evidence_digest(tampered))


def test_metrics_recomputed_from_raw_not_carried_flags() -> None:
    # Codex P1: a digest-valid, READY record re-sealed with a LOSING raw pnl but a carried hit_flag=True must
    # not be counted as a hit. SM-4 must recompute the hit from raw realized_pnl, not trust hit_flag.
    incoherent_hits = [
        _reseal(_record(0), realized_pnl="-5.000000000000000000", hit_flag=True),
        _reseal(_record(1), realized_pnl="-5.000000000000000000", hit_flag=True),
    ]
    assert all(record.hit_flag is True for record in incoherent_hits)  # carried flag still lies
    evidence = _build(records=incoherent_hits)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.hit_rate == "0.000000000000000000"
    assert _rc("hit_rate_below_floor") in evidence.reason_codes


def test_slippage_recomputed_from_raw_not_carried_flag() -> None:
    # A record whose carried slippage_bps is a benign lie but whose raw prices imply a large breach must be
    # rejected on the recomputed slippage, not the carried value.
    breaching = [
        _reseal(_record(0), realized_fill_price="100.500000000000000000", slippage_bps="1.000000000000000000"),
        _reseal(_record(1), realized_fill_price="100.500000000000000000", slippage_bps="1.000000000000000000"),
    ]
    evidence = _build(records=breaching)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.average_slippage_bps == "50.000000000000000000"
    assert _rc("slippage_above_ceiling") in evidence.reason_codes


def test_incoherent_raw_record_rejected() -> None:
    # filled > intended is impossible from build_trade_record_evidence; a hand re-sealed READY record with
    # that raw incoherence must fail closed at the SM-4 boundary.
    incoherent = _reseal(_record(0), filled_quantity="2.000000000000000000")
    assert incoherent.status.value == "RECORD_READY"
    evidence = _build(records=[incoherent, _record(1)])
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert _rc("record_incoherent") in evidence.reason_codes


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"record_version": "trade-record-evidence.v2"}, "record_version_invalid"),
        ({"hit_rate_definition": "wins_over_decided_episodes.v1"}, "record_definition_mismatch"),
        ({"fill_rate_definition": "filled_quantity_only.v1"}, "record_definition_mismatch"),
        ({"slippage_definition": "unsigned_bps.v1"}, "record_definition_mismatch"),
        (
            {"decimal_policy": "decimal_quantized_scale_9_round_half_even_fraction_intermediates.v1"},
            "record_decimal_policy_mismatch",
        ),
        ({"decimal_scale": 9}, "record_decimal_policy_mismatch"),
        ({"decimal_rounding": "ROUND_HALF_UP"}, "record_decimal_policy_mismatch"),
        ({"decimal_internal_precision": 28}, "record_decimal_policy_mismatch"),
    ],
)
def test_resealed_record_definition_or_decimal_policy_mismatch_rejects(
    override: dict[str, object], reason: str
) -> None:
    tampered = _reseal(_record(0), **override)

    evidence = _build(records=[tampered, _record(1)])

    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.ready is False
    assert evidence.status is not PaperSecondaryMetricsEvidenceStatus.METRICS_READY
    assert _rc(reason) in evidence.reason_codes


def test_large_summed_quantities_do_not_raise() -> None:
    # Codex P2: summed quantities near the per-record cap exceed Python's default Decimal precision (28);
    # the formatter must quantize under the precision-80 context instead of raising InvalidOperation.
    big = "1000000000000000000.000000000000000000"
    records = [
        _record(0, intended=big, filled=big),
        _record(1, intended=big, filled=big),
    ]
    evidence = _build(records=records)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_READY
    assert evidence.intended_quantity_sum == "2000000000000000000.000000000000000000"
    assert evidence.filled_quantity_sum == "2000000000000000000.000000000000000000"


# --- 5. Sufficiency + threshold enforcement -----------------------------------------------------------------


def test_insufficient_decided_episodes() -> None:
    evidence = _build(policy=_policy(approved_min_decided_episode_count=5))
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert evidence.sufficient_evidence is False
    assert _rc("insufficient_decided_episodes") in evidence.reason_codes


def test_hit_rate_below_floor_blocks_secondary_metric_enforcement() -> None:
    records = [
        _record(0, pnl="5.000000000000000000"),
        _record(1, pnl="-5.000000000000000000"),
        _record(2, pnl="-5.000000000000000000"),
        _record(3, pnl="-5.000000000000000000"),
    ]
    evidence = _build(records=records)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.hit_rate == "0.250000000000000000"
    assert evidence.hit_rate_satisfied is False
    assert _rc("hit_rate_below_floor") in evidence.reason_codes


def test_fill_rate_below_floor_blocks_secondary_metric_enforcement() -> None:
    records = [
        _record(0, filled="0.500000000000000000"),
        _record(1, filled="0.500000000000000000"),
    ]
    evidence = _build(records=records)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.fill_rate_by_quantity == "0.500000000000000000"
    assert evidence.fill_rate_satisfied is False
    assert _rc("fill_rate_below_floor") in evidence.reason_codes


def test_slippage_above_ceiling_blocks_secondary_metric_enforcement() -> None:
    records = [
        _record(0, realized="100.500000000000000000"),
        _record(1, realized="100.500000000000000000"),
    ]
    evidence = _build(records=records)
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_REJECTED
    assert evidence.average_slippage_bps == "50.000000000000000000"
    assert evidence.slippage_satisfied is False
    assert _rc("slippage_above_ceiling") in evidence.reason_codes


def test_valid_thresholds_pass() -> None:
    evidence = _build()
    assert evidence.status is PaperSecondaryMetricsEvidenceStatus.METRICS_READY
    assert evidence.thresholds_cleared is True


# --- 6. Enforcement-boundary / purity (design §6 named regressions) -----------------------------------------


def test_secondary_metrics_thresholds_enforced_outside_current_comparator() -> None:
    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert "stage4_comparator" not in node.module
        if isinstance(node, ast.Import):
            assert all("stage4_comparator" not in alias.name for alias in node.names)
    # A READY verdict is produced by this module's own Fraction comparisons, not by a comparator.
    evidence = _build()
    assert evidence.thresholds_enforced_here_not_by_comparator is True
    assert evidence.comparator_invoked is False
    assert evidence.thresholds_cleared is True


def test_compare_stage4_echo_does_not_satisfy_secondary_metric_enforcement() -> None:
    # AST proof (not a raw string scan): the module never imports the comparator module nor calls
    # ``compare_stage4``. The comparator name appears only in the module docstring to explain the non-claim.
    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert "stage4_comparator" not in node.module
        if isinstance(node, ast.Import):
            assert all("stage4_comparator" not in alias.name for alias in node.names)
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id != "compare_stage4"
            if isinstance(function, ast.Attribute):
                assert function.attr != "compare_stage4"


def test_structural_false_non_claim_flags() -> None:
    evidence = _build()
    payload = paper_secondary_metrics_evidence_to_dict(evidence)
    assert payload["paper_only"] is True
    assert payload["evidence_only"] is True
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert payload[flag] is False


def test_source_has_no_forbidden_imports_or_calls() -> None:
    source = Path(evidence_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "time",
        "datetime",
        "random",
        "secrets",
        "socket",
        "requests",
        "urllib",
        "threading",
        "asyncio",
        "subprocess",
        "os",
        "pathlib",
        "sqlite3",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
    )
    forbidden_call_names = {"open", "float", "now", "utcnow", "time", "time_ns", "perf_counter", "monotonic"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == m or alias.name.startswith(f"{m}.") for m in forbidden_modules)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == m or node.module.startswith(f"{m}.") for m in forbidden_modules)
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names
