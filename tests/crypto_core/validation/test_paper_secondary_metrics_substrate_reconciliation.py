"""Tests for the paper secondary-metrics substrate reconciliation artifact (denominator completeness)."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_secondary_metrics_substrate_reconciliation as recon_module
from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunResult,
    PaperEpisodeRunStatus,
    paper_episode_run_result_digest,
)
from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlEvent,
    PaperRealizedPnlStatus,
    paper_realized_pnl_event_digest,
)
from crypto_core.validation.paper_secondary_metrics_evidence import build_paper_secondary_metrics_evidence
from crypto_core.validation.paper_secondary_metrics_substrate_reconciliation import (
    PaperSecondaryMetricsSubstrateReconciliationError,
    PaperSecondaryMetricsSubstrateReconciliationStatus,
    PaperSecondaryMetricsSubstrateRecordInput,
    build_paper_secondary_metrics_substrate_reconciliation,
    paper_secondary_metrics_substrate_reconciliation_digest,
    paper_secondary_metrics_substrate_reconciliation_to_dict,
)
from crypto_core.validation.paper_session_sequence import (
    PaperSessionSequenceResult,
    PaperSessionSequenceStatus,
    paper_session_sequence_result_digest,
)
from crypto_core.validation.secondary_metrics_policy import build_secondary_metrics_policy
from crypto_core.validation.trade_record_evidence import build_trade_record_evidence, trade_record_evidence_digest

_REASON_PREFIX = "paper_secondary_metrics_substrate_reconciliation:"
_MARKET = "BTC-USD"

_STRUCTURAL_FALSE_FLAGS = (
    "live_ready",
    "shadow_ready",
    "connector_ready",
    "orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "stage4_complete",
    "sm5_enabled",
    "sm6_enabled",
)

_counter = [0]


def _hex() -> str:
    _counter[0] += 1
    return format(_counter[0], "064x")


def _rc(code: str) -> str:
    return f"{_REASON_PREFIX}{code}"


def _reseal(obj, field: str, fn):
    return replace(obj, **{field: fn(obj)})


def _fill(status: PaperFillSimulationStatus, filled: str, unfilled: str, price: str, *, correlation_id: str = "corr-1"):
    result = PaperFillSimulationResult(
        schema_version="paper-fill-simulation-result.v1",
        status=status,
        fill_simulation_id=f"fs-{_hex()[:6]}",
        intent_digest=_hex(),
        market_snapshot_digest=_hex(),
        fill_policy_digest=_hex(),
        market_symbol=_MARKET,
        side="BUY",
        intent_type="MARKET",
        fill_price=price,
        filled_units=filled,
        unfilled_units=unfilled,
        gross_notional="1",
        fee_amount="0",
        reason_codes=(),
        correlation_id=correlation_id,
        metadata=(),
        result_digest="0" * 64,
    )
    return _reseal(result, "result_digest", paper_fill_simulation_result_digest)


def _episode(episode_id: str, fill_result, realized_pnl_computed: bool, transition: str, *, correlation_id="corr-1"):
    result = PaperEpisodeRunResult(
        schema_version="paper-episode-run-result.v1",
        episode_run_id=episode_id,
        status=PaperEpisodeRunStatus.COMPUTED,
        market_symbol=_MARKET,
        order_intent_digest=_hex(),
        prior_position_state_digest=_hex(),
        fill_market_snapshot_digest=_hex(),
        fill_policy_digest=_hex(),
        fill_simulation_result_digest=fill_result.result_digest,
        fill_status="X",
        position_transition_digest=transition,
        transition_status="X",
        new_position_state_digest=_hex(),
        mark_snapshot_digest=_hex(),
        pnl_report_digest=_hex(),
        reason_codes=(),
        correlation_id=correlation_id,
        metadata=(),
        episode_run_digest="0" * 64,
        realized_pnl_computed=realized_pnl_computed,
    )
    return _reseal(result, "episode_run_digest", paper_episode_run_result_digest)


def _event(fill_result, transition: str, realized_pnl: str, *, correlation_id="corr-1"):
    event = PaperRealizedPnlEvent(
        schema_version="paper-realized-pnl-event.v1",
        realized_pnl_event_id=f"rp-{_hex()[:6]}",
        status=PaperRealizedPnlStatus.COMPUTED,
        market_symbol=_MARKET,
        prior_position_state_digest=_hex(),
        fill_simulation_result_digest=fill_result.result_digest,
        position_transition_digest=transition,
        new_position_state_digest=_hex(),
        prior_side="LONG",
        fill_side="SELL",
        prior_signed_units="1",
        filled_units="1",
        closed_units="1",
        residual_open_units="0",
        average_entry_price="95",
        fill_price="100",
        realized_pnl=realized_pnl,
        reason_codes=(),
        correlation_id=correlation_id,
        metadata=(),
        realized_pnl_event_digest="0" * 64,
    )
    return _reseal(event, "realized_pnl_event_digest", paper_realized_pnl_event_digest)


def _record(
    episode_id: str,
    record_id: str,
    *,
    filled: str,
    intended: str,
    realized_price: str | None,
    realized_pnl: str,
    policy_id: str = "policy-1",
    correlation_id: str = "corr-1",
    decided: bool = True,
):
    return build_trade_record_evidence(
        record_id=record_id,
        correlation_id=correlation_id,
        sleeve_id="sleeve-1",
        policy_id=policy_id,
        episode_id=episode_id,
        strategy_id="strategy-1",
        decision_id=f"decision-{record_id}",
        intended_quantity=intended,
        filled_quantity=filled,
        expected_fill_price="100.000000000000000000",
        realized_fill_price=realized_price,
        realized_pnl=realized_pnl,
        decided_episode=decided,
    )


def _policy(**overrides):
    payload = {
        "policy_id": "policy-1",
        "correlation_id": "corr-1",
        "expected_fill_model_parameters_digest": "a" * 64,
        "approved_hit_rate_floor": "0.500000000000000000",
        "approved_fill_rate_floor": "0.900000000000000000",
        "approved_slippage_ceiling_bps": "25.000000000000000000",
        "approved_min_decided_episode_count": 1,
        "approval_reference": "gov-sm2-1",
        "approval_digest": "b" * 64,
        "thresholds_approved": True,
    }
    payload.update(overrides)
    return build_secondary_metrics_policy(**payload)  # type: ignore[arg-type]


def _session(episode_digests: tuple[str, ...], *, correlation_id="corr-1", market=_MARKET):
    result = PaperSessionSequenceResult(
        schema_version="paper-session-sequence-result.v1",
        paper_session_id="ps-1",
        status=PaperSessionSequenceStatus.COMPUTED,
        market_symbol=market,
        episode_count=len(episode_digests),
        episode_run_digests=episode_digests,
        first_episode_run_digest=episode_digests[0],
        last_episode_run_digest=episode_digests[-1],
        computed_episode_count=len(episode_digests),
        fill_rejected_episode_count=0,
        rejected_episode_count=0,
        final_position_state_digest=_hex(),
        final_pnl_report_digest=_hex(),
        reason_codes=(),
        correlation_id=correlation_id,
        metadata=(),
        paper_session_sequence_digest="0" * 64,
    )
    return _reseal(result, "paper_session_sequence_digest", paper_session_sequence_result_digest)


class _Scenario:
    """A coherent win/loss/rejected 3-episode reconciliation fixture, mutable per test."""

    def __init__(self) -> None:
        self.policy = _policy()
        pt1, pt2, pt3 = _hex(), _hex(), _hex()
        fr1 = _fill(PaperFillSimulationStatus.FILLED, "1", "0", "100.1")
        fr2 = _fill(PaperFillSimulationStatus.FILLED, "1", "0", "99")
        fr3 = _fill(PaperFillSimulationStatus.REJECTED, "0", "1", "0")
        er1 = _episode("ep-0", fr1, True, pt1)
        er2 = _episode("ep-1", fr2, True, pt2)
        er3 = _episode("ep-2", fr3, False, pt3)
        ev1 = _event(fr1, pt1, "5")
        ev2 = _event(fr2, pt2, "-3")
        rec1 = _record(
            "ep-0",
            "rec-0",
            filled="1.000000000000000000",
            intended="1.000000000000000000",
            realized_price="100.100000000000000000",
            realized_pnl="5.000000000000000000",
        )
        rec2 = _record(
            "ep-1",
            "rec-1",
            filled="1.000000000000000000",
            intended="1.000000000000000000",
            realized_price="99.000000000000000000",
            realized_pnl="-3.000000000000000000",
        )
        rec3 = _record(
            "ep-2",
            "rec-2",
            filled="0.000000000000000000",
            intended="1.000000000000000000",
            realized_price=None,
            realized_pnl="0.000000000000000000",
        )
        self.records = [rec1, rec2, rec3]
        self.inputs = [
            PaperSecondaryMetricsSubstrateRecordInput(rec1, er1, fr1, ev1),
            PaperSecondaryMetricsSubstrateRecordInput(rec2, er2, fr2, ev2),
            PaperSecondaryMetricsSubstrateRecordInput(rec3, er3, fr3, None),
        ]
        self.session = _session((er1.episode_run_digest, er2.episode_run_digest, er3.episode_run_digest))
        self._rebuild_metrics()

    def _rebuild_metrics(self) -> None:
        self.metrics = build_paper_secondary_metrics_evidence(
            self.policy, self.records, evidence_id="sm4-1", correlation_id="corr-1"
        )

    def rebuild_metrics_from_inputs(self) -> None:
        self.records = [item.record for item in self.inputs]
        self._rebuild_metrics()

    def rebuild_session_from_inputs(self) -> None:
        digests = tuple(paper_episode_run_result_digest(item.episode_run) for item in self.inputs)
        self.session = _session(digests)

    def build(self, **overrides):
        payload = {
            "reconciliation_id": "recon-1",
            "correlation_id": "corr-1",
            "expected_policy_digest": self.policy.policy_digest,
            "expected_metrics_evidence_digest": self.metrics.evidence_digest,
            "expected_session_sequence_digest": self.session.paper_session_sequence_digest,
        }
        payload.update(overrides)
        return build_paper_secondary_metrics_substrate_reconciliation(
            self.policy, self.metrics, self.inputs, self.session, **payload
        )


# --- 1. Public API / happy path -----------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(recon_module.__all__) == {
        "PaperSecondaryMetricsSubstrateReconciliation",
        "PaperSecondaryMetricsSubstrateReconciliationError",
        "PaperSecondaryMetricsSubstrateReconciliationStatus",
        "PaperSecondaryMetricsSubstrateRecordInput",
        "build_paper_secondary_metrics_substrate_reconciliation",
        "paper_secondary_metrics_substrate_reconciliation_digest",
        "paper_secondary_metrics_substrate_reconciliation_to_dict",
    }


def test_happy_win_loss_rejected_reconciled() -> None:
    reconciliation = _Scenario().build()
    payload = paper_secondary_metrics_substrate_reconciliation_to_dict(reconciliation)

    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.RECONCILED
    assert reconciliation.ready is True
    assert reconciliation.reason_codes == ()
    assert reconciliation.episode_count == 3
    assert reconciliation.filled_episode_count == 2
    assert reconciliation.rejected_or_unfilled_episode_count == 1
    assert reconciliation.positive_pnl_episode_count == 1
    assert reconciliation.negative_pnl_episode_count == 1
    assert reconciliation.zero_pnl_episode_count == 0
    assert len(reconciliation.reconciled_record_digests) == 3
    assert payload["reconciliation_digest"] == paper_secondary_metrics_substrate_reconciliation_digest(reconciliation)


def test_output_is_frozen() -> None:
    reconciliation = _Scenario().build()
    with pytest.raises(FrozenInstanceError):
        reconciliation.ready = False  # type: ignore[misc]


def test_serializer_matches_dataclass_fields() -> None:
    reconciliation = _Scenario().build()
    payload = paper_secondary_metrics_substrate_reconciliation_to_dict(reconciliation)
    assert set(payload) == {field.name for field in fields(reconciliation)}
    assert payload["status"] == reconciliation.status.value


def test_deterministic_and_metadata_order_independent() -> None:
    scenario = _Scenario()
    first = scenario.build(metadata={"b": "2", "a": "1"})
    second = scenario.build(metadata={"a": "1", "b": "2"})
    assert first.reconciliation_digest == second.reconciliation_digest
    resealed = replace(first, reconciliation_digest="0" * 64)
    assert paper_secondary_metrics_substrate_reconciliation_digest(resealed) == first.reconciliation_digest


def test_structural_false_non_claim_flags() -> None:
    reconciliation = _Scenario().build()
    payload = paper_secondary_metrics_substrate_reconciliation_to_dict(reconciliation)
    assert payload["paper_only"] is True
    assert payload["validation_only"] is True
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert payload[flag] is False


# --- 2. Completeness / bijection (dropped, extra, duplicate) -------------------------------------------------


def test_dropped_losing_record_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs = [scenario.inputs[0], scenario.inputs[2]]  # drop the loss; session still has all 3
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_count_mismatch") in reconciliation.reason_codes


def test_dropped_rejected_unfilled_record_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs = [scenario.inputs[0], scenario.inputs[1]]  # drop the rejected episode
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_count_mismatch") in reconciliation.reason_codes


def test_extra_record_without_episode_rejected() -> None:
    scenario = _Scenario()
    pt = _hex()
    extra_fill = _fill(PaperFillSimulationStatus.FILLED, "1", "0", "100")
    extra_ep = _episode("ep-extra", extra_fill, True, pt)
    extra_ev = _event(extra_fill, pt, "1")
    extra_rec = _record(
        "ep-extra",
        "rec-extra",
        filled="1.000000000000000000",
        intended="1.000000000000000000",
        realized_price="100.000000000000000000",
        realized_pnl="1.000000000000000000",
    )
    scenario.inputs = [
        *scenario.inputs,
        PaperSecondaryMetricsSubstrateRecordInput(extra_rec, extra_ep, extra_fill, extra_ev),
    ]
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_count_mismatch") in reconciliation.reason_codes


def test_duplicate_record_episode_id_rejected() -> None:
    scenario = _Scenario()
    # A distinct substrate episode (different digest) re-using episode id "ep-0" of the win episode, with a
    # record whose episode_id matches its own run id — so the collision is a genuine duplicate episode id,
    # not a record<->run mismatch.
    pt = _hex()
    dup_fill = _fill(PaperFillSimulationStatus.REJECTED, "0", "1", "0")
    dup_episode = _episode("ep-0", dup_fill, False, pt)
    dup_record = _record(
        "ep-0",
        "rec-dup",
        filled="0.000000000000000000",
        intended="1.000000000000000000",
        realized_price=None,
        realized_pnl="0.000000000000000000",
    )
    scenario.inputs[2] = PaperSecondaryMetricsSubstrateRecordInput(dup_record, dup_episode, dup_fill, None)
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("duplicate_record_episode_id") in reconciliation.reason_codes


def test_duplicate_substrate_episode_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[2] = scenario.inputs[0]  # same episode_run (same digest) twice
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("duplicate_substrate_episode") in reconciliation.reason_codes


def test_episode_order_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs = [scenario.inputs[1], scenario.inputs[0], scenario.inputs[2]]  # swap first two
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("episode_order_mismatch") in reconciliation.reason_codes


# --- 3. Provenance / stale digests --------------------------------------------------------------------------


def test_stale_policy_digest_rejected() -> None:
    reconciliation = _Scenario().build(expected_policy_digest="c" * 64)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("policy_digest_mismatch") in reconciliation.reason_codes


def test_stale_metrics_evidence_digest_rejected() -> None:
    reconciliation = _Scenario().build(expected_metrics_evidence_digest="c" * 64)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("metrics_evidence_digest_mismatch") in reconciliation.reason_codes


def test_stale_session_sequence_digest_rejected() -> None:
    reconciliation = _Scenario().build(expected_session_sequence_digest="c" * 64)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("session_sequence_digest_mismatch") in reconciliation.reason_codes


def test_stale_fill_result_digest_rejected() -> None:
    scenario = _Scenario()
    win = scenario.inputs[0]
    tampered_fill = _reseal(
        replace(win.fill_result, gross_notional="999"), "result_digest", paper_fill_simulation_result_digest
    )
    scenario.inputs[0] = replace(win, fill_result=tampered_fill)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("fill_result_digest_mismatch") in reconciliation.reason_codes


def test_stale_realized_event_digest_rejected() -> None:
    scenario = _Scenario()
    win = scenario.inputs[0]
    tampered_event = replace(
        win.realized_pnl_event, realized_pnl_event_digest="0" * 64
    )  # carried digest not recomputed
    scenario.inputs[0] = replace(win, realized_pnl_event=tampered_event)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_digest_mismatch") in reconciliation.reason_codes


# --- 4. Record <-> substrate value binding ------------------------------------------------------------------


def _reseal_record(record, **overrides):
    tampered = replace(record, **overrides)
    return replace(tampered, record_digest=trade_record_evidence_digest(tampered))


def test_resealed_record_quantity_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, filled_quantity="0.500000000000000000")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("filled_quantity_mismatch") in reconciliation.reason_codes


def test_resealed_record_realized_pnl_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, realized_pnl="9.000000000000000000")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_pnl_mismatch") in reconciliation.reason_codes


def test_filled_episode_missing_required_realized_event_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(scenario.inputs[0], realized_pnl_event=None)  # episode says realized_pnl_computed True
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("realized_event_required") in reconciliation.reason_codes


def test_rejected_fill_carrying_realized_event_rejected() -> None:
    scenario = _Scenario()
    rejected = scenario.inputs[2]
    stray_event = _event(rejected.fill_result, rejected.episode_run.position_transition_digest, "0")
    scenario.inputs[2] = replace(rejected, realized_pnl_event=stray_event)
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("unexpected_realized_event") in reconciliation.reason_codes


def test_rejected_fill_record_claiming_fill_rejected() -> None:
    scenario = _Scenario()
    tampered = _reseal_record(
        scenario.inputs[2].record,
        filled_quantity="1.000000000000000000",
        realized_fill_price="100.000000000000000000",
    )
    scenario.inputs[2] = replace(scenario.inputs[2], record=tampered)
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("rejected_fill_record_mismatch") in reconciliation.reason_codes


def test_record_policy_id_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, policy_id="other-policy")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("record_policy_id_mismatch") in reconciliation.reason_codes


def test_record_episode_id_mismatch_rejected() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = replace(
        scenario.inputs[0], record=_reseal_record(scenario.inputs[0].record, episode_id="not-the-episode")
    )
    scenario.rebuild_metrics_from_inputs()
    reconciliation = scenario.build()
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("record_episode_id_mismatch") in reconciliation.reason_codes


def test_records_not_in_metrics_evidence_rejected() -> None:
    scenario = _Scenario()
    # Metrics evidence built over only the first two records; substrate supplies all three.
    scenario.metrics = build_paper_secondary_metrics_evidence(
        scenario.policy, scenario.records[:2], evidence_id="sm4-1", correlation_id="corr-1"
    )
    reconciliation = scenario.build(expected_metrics_evidence_digest=scenario.metrics.evidence_digest)
    assert reconciliation.status is PaperSecondaryMetricsSubstrateReconciliationStatus.REJECTED
    assert _rc("records_not_metrics_evidence") in reconciliation.reason_codes


# --- 5. Malformed input (raise) / scope ---------------------------------------------------------------------


def test_policy_wrong_type_raises() -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        build_paper_secondary_metrics_substrate_reconciliation(
            "policy",
            scenario.metrics,
            scenario.inputs,
            scenario.session,  # type: ignore[arg-type]
            reconciliation_id="r",
            correlation_id="corr-1",
            expected_policy_digest="a" * 64,
            expected_metrics_evidence_digest="a" * 64,
            expected_session_sequence_digest="a" * 64,
        )


def test_empty_inputs_raises() -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        build_paper_secondary_metrics_substrate_reconciliation(
            scenario.policy,
            scenario.metrics,
            [],
            scenario.session,
            reconciliation_id="r",
            correlation_id="corr-1",
            expected_policy_digest=scenario.policy.policy_digest,
            expected_metrics_evidence_digest=scenario.metrics.evidence_digest,
            expected_session_sequence_digest=scenario.session.paper_session_sequence_digest,
        )


def test_wrong_input_element_type_raises() -> None:
    scenario = _Scenario()
    scenario.inputs[0] = "not-an-input"  # type: ignore[assignment]
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        scenario.build()


@pytest.mark.parametrize("token", ["live-ready", "order_router", "deribit", "BIST-desk", "datetime.utcnow"])
def test_forbidden_metadata_token_raises(token: str) -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        scenario.build(metadata={"source": token})


@pytest.mark.parametrize("bad", ["  ", "recon\t1"])
def test_malformed_reconciliation_id_raises(bad: str) -> None:
    scenario = _Scenario()
    with pytest.raises(PaperSecondaryMetricsSubstrateReconciliationError):
        scenario.build(reconciliation_id=bad)


# --- 6. Module purity ---------------------------------------------------------------------------------------


def test_source_has_no_forbidden_imports_or_calls() -> None:
    source = Path(recon_module.__file__).read_text(encoding="utf-8")
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
    forbidden_call_names = {
        "open",
        "float",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
        "compare_stage4",
    }
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
