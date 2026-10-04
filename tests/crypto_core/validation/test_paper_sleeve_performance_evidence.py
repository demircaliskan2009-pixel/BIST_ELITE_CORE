"""RG-3 per-sleeve paper performance evidence tests (RG3_SLEEVE_PERFORMANCE_PROVENANCE_V1).

SYNTHETIC TEST VALUES ONLY. The sleeve world, the RG-2 envelope and every approval are the synthetic fixtures of their
own test modules; none is a production threshold, none is venue truth, and none is production-approved. The generic
series world (methodology, deterministic time window, daily-return series, paper Sharpe) is built here ONLY through
the accepted public builders, over the exact buckets the sleeve valuation emits.
"""

from __future__ import annotations

import ast
import functools
import json
import re
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.paper_sleeve_performance_evidence as performance_module
from crypto_core.validation.edge_artifact_core import edge_canonical_json
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnSeriesEvidence,
    PaperDailyReturnSeriesEvidenceStatus,
    build_paper_daily_return_series_evidence,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    build_paper_deterministic_time_window_evidence,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PaperPortfolioRiskEnvelope,
    paper_portfolio_risk_envelope_rule_set,
)
from crypto_core.validation.paper_return_series_methodology import (
    PaperReturnSeriesMethodology,
    build_paper_return_series_methodology,
)
from crypto_core.validation.paper_sharpe_evidence import (
    PaperSharpeEvidence,
    PaperSharpeEvidenceStatus,
    build_paper_sharpe_evidence,
)
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDailyValuationEvidence,
    build_paper_sleeve_daily_valuation_evidence,
    paper_sleeve_daily_return_buckets,
)
from crypto_core.validation.paper_sleeve_equity_basis_policy import (
    PaperSleeveEquityBasisPolicy,
    PaperSleeveFundingTreatment,
    paper_sleeve_equity_basis_methodology_policy_ids,
)
from crypto_core.validation.paper_sleeve_funding_evidence import build_paper_sleeve_funding_evidence
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PAPER_SLEEVE_PERFORMANCE_MEASURE_ID,
    PAPER_SLEEVE_PERFORMANCE_NON_CLAIM_FLAGS,
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceEvidenceError,
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    build_paper_sleeve_performance_evidence,
    paper_sleeve_performance_evidence_digest,
    paper_sleeve_performance_evidence_to_dict,
    verify_paper_sleeve_performance_evidence,
)

try:  # the module objects pytest collects (basename import), so the authentic worlds and their caches are built once
    import test_paper_portfolio_risk_envelope as rg2
    import test_paper_sleeve_daily_valuation_evidence as world
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as world

_PREFIX = "paper_sleeve_performance_evidence"
_READY = PaperSleevePerformanceStatus.READY
_NOT_COMPUTABLE = PaperSleevePerformanceStatus.NOT_COMPUTABLE
_NEEDS_GOVERNANCE = PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
METHODOLOGY_ID = "sleeve-method-1"
RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"
SERIES_INPUT_NAMES = ("methodology", "time_window", "daily_return_series", "sharpe_evidence")
NO_SERIES: dict[str, object] = dict.fromkeys(SERIES_INPUT_NAMES)


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _valuation_code(code: str) -> str:
    return f"paper_sleeve_daily_valuation_evidence:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperSleevePerformanceEvidenceError, match=f"^{re.escape(_code(code))}$")


# --- the generic series world over the sleeve buckets ---------------------------------------------------------------


def methodology_for(policy: PaperSleeveEquityBasisPolicy, **overrides: object) -> PaperReturnSeriesMethodology:
    values: dict[str, object] = {
        "methodology_id": METHODOLOGY_ID,
        "correlation_id": world.VALUATION_CORRELATION,
        "risk_free_policy_id": RISK_FREE_POLICY_ID,
        **paper_sleeve_equity_basis_methodology_policy_ids(policy),
    }
    values.update(overrides)
    return build_paper_return_series_methodology(**values)  # type: ignore[arg-type]


def time_window_for(start_ns: int, end_ns: int) -> PaperDeterministicTimeWindowEvidence:
    summary = world.window_support._summary()  # noqa: SLF001 - the accepted metrics-summary fixture of the window chain
    return build_paper_deterministic_time_window_evidence(
        summary,
        expected_metrics_summary_digest=summary.summary_digest,
        started_at_ns=start_ns,
        stopped_at_ns=end_ns,
        window_id="window-sleeve",
        methodology_id=METHODOLOGY_ID,
        run_id=world.window_support._RUN,  # noqa: SLF001
        aggregate_id=world.window_support._AGG_ID,  # noqa: SLF001
        correlation_id=world.VALUATION_CORRELATION,
        sample_observation_count=(end_ns - start_ns) // world.DAY_NS,
    )


def series_for(
    valuation: PaperSleeveDailyValuationEvidence,
    methodology: PaperReturnSeriesMethodology,
    time_window: PaperDeterministicTimeWindowEvidence,
    *,
    correlation_id: str = world.VALUATION_CORRELATION,
) -> PaperDailyReturnSeriesEvidence:
    return build_paper_daily_return_series_evidence(
        methodology,
        time_window,
        expected_methodology_digest=methodology.methodology_digest,
        expected_time_window_digest=time_window.time_window_digest,
        series_id="sleeve-series-1",
        correlation_id=correlation_id,
        daily_buckets=paper_sleeve_daily_return_buckets(valuation),
    )


def sharpe_for(series: PaperDailyReturnSeriesEvidence) -> PaperSharpeEvidence:
    return build_paper_sharpe_evidence(
        series,
        expected_daily_return_series_digest=series.series_digest,
        risk_free_policy_id=RISK_FREE_POLICY_ID,
        sharpe_evidence_id="sleeve-sharpe-1",
        paper_id="sleeve-paper-1",
        correlation_id=world.VALUATION_CORRELATION,
    )


@dataclass(frozen=True)
class SeriesWorld:
    methodology: PaperReturnSeriesMethodology
    time_window: PaperDeterministicTimeWindowEvidence
    series: PaperDailyReturnSeriesEvidence
    sharpe: PaperSharpeEvidence

    def inputs(self) -> dict[str, object]:
        return {
            "methodology": self.methodology,
            "time_window": self.time_window,
            "daily_return_series": self.series,
            "sharpe_evidence": self.sharpe,
        }


def series_world(
    valuation: PaperSleeveDailyValuationEvidence, policy: PaperSleeveEquityBasisPolicy, start_ns: int, end_ns: int
) -> SeriesWorld:
    methodology = methodology_for(policy)
    time_window = time_window_for(start_ns, end_ns)
    series = series_for(valuation, methodology, time_window)
    return SeriesWorld(methodology, time_window, series, sharpe_for(series))


@functools.lru_cache(maxsize=None)
def world_series() -> SeriesWorld:
    return series_world(world.world_valuation(), world.basis_policy(), world.WINDOW_START, world.WINDOW_END)


@functools.lru_cache(maxsize=None)
def world_envelope() -> PaperPortfolioRiskEnvelope:
    return rg2.governed()


def performance_inputs(**overrides: object) -> PaperSleevePerformanceInputs:
    values: dict[str, object] = {
        "performance_evidence_id": "rg3-sleeve-alpha-1",
        "correlation_id": world.VALUATION_CORRELATION,
        "portfolio_risk_envelope": world_envelope(),
        "valuation_inputs": world.valuation_inputs(),
        "valuation": world.world_valuation(),
        **world_series().inputs(),
    }
    values.update(overrides)
    return PaperSleevePerformanceInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> PaperSleevePerformanceEvidence:
    return build_paper_sleeve_performance_evidence(inputs)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def world_performance() -> PaperSleevePerformanceEvidence:
    return build(performance_inputs())


def blocked_valuation_inputs(**overrides: object) -> dict[str, object]:
    """RG-3 inputs over a valuation built from ``overrides``, with no series inputs."""

    valuation_inputs = world.valuation_inputs(**overrides)
    return {
        "valuation_inputs": valuation_inputs,
        "valuation": build_paper_sleeve_daily_valuation_evidence(valuation_inputs),
        **NO_SERIES,
    }


def _reseal(evidence: PaperSleevePerformanceEvidence, **changes: object) -> PaperSleevePerformanceEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, performance_evidence_digest=paper_sleeve_performance_evidence_digest(changed))


SHORT_WINDOW_DAYS = 10


@functools.lru_cache(maxsize=None)
def short_window_inputs() -> dict[str, object]:
    """A genuine 10-day sleeve world: the accepted Sharpe needs more observations than it has."""

    end = world.WINDOW_START + SHORT_WINDOW_DAYS * world.DAY_NS
    episodes = world.world_episodes()[:2]
    funding = build_paper_sleeve_funding_evidence(
        evidence_id="funding-evidence-short",
        sleeve_id=world.SLEEVE,
        market_symbol=world.MARKET,
        window_start_ns=world.WINDOW_START,
        window_end_ns=end,
        events=tuple(event for event in world.funding_events(episodes) if event.settlement_at_ns < end),
    )
    valuation_inputs = world.valuation_inputs(
        episodes=episodes,
        day_closes=tuple(world.build_day_close(day, episodes) for day in range(SHORT_WINDOW_DAYS)),
        window_end_ns=end,
        funding_evidence=funding,
    )
    valuation = build_paper_sleeve_daily_valuation_evidence(valuation_inputs)
    series = series_world(valuation, world.basis_policy(), world.WINDOW_START, end)
    return {"valuation_inputs": valuation_inputs, "valuation": valuation, **series.inputs()}


# --- the READY snapshot ---------------------------------------------------------------------------------------------


def test_world_snapshot_is_ready() -> None:
    snapshot = world_performance()
    assert snapshot.status is _READY, snapshot.reason_codes
    assert snapshot.ready is True
    assert snapshot.reason_codes == ()
    assert (snapshot.sleeve_id, snapshot.market_symbol) == (world.SLEEVE, world.MARKET)
    assert (snapshot.window_start_ns, snapshot.window_end_ns, snapshot.day_count) == (
        world.WINDOW_START,
        world.WINDOW_END,
        world.WINDOW_DAYS,
    )
    assert (snapshot.valuation_status, snapshot.daily_return_series_status, snapshot.sharpe_status) == (
        "COMPUTED",
        "READY",
        "READY",
    )
    assert snapshot.sharpe_computed is True
    assert snapshot.performance_measure_id == PAPER_SLEEVE_PERFORMANCE_MEASURE_ID
    assert snapshot.paper_sharpe_annualized == "1.809314530709372854"


def test_the_snapshot_binds_every_reproven_digest() -> None:
    snapshot = world_performance()
    envelope = world_envelope()
    valuation = world.world_valuation()
    series = world_series()
    assert (snapshot.envelope_digest, snapshot.envelope_policy_digest, snapshot.envelope_advances) == (
        envelope.envelope_digest,
        envelope.policy_digest,
        True,
    )
    assert (snapshot.equity_basis_policy_digest, snapshot.equity_basis_digest) == (
        valuation.equity_basis_policy_digest,
        valuation.equity_basis_digest,
    )
    assert snapshot.equity_basis_policy_advances is True
    assert snapshot.valuation_digest == valuation.valuation_digest
    assert snapshot.methodology_digest == series.methodology.methodology_digest
    assert snapshot.time_window_digest == series.time_window.time_window_digest
    assert snapshot.daily_return_series_digest == series.series.series_digest
    assert snapshot.sharpe_evidence_digest == series.sharpe.sharpe_evidence_digest
    assert (snapshot.performance_evidence_id, snapshot.correlation_id) == (
        "rg3-sleeve-alpha-1",
        world.VALUATION_CORRELATION,
    )


def test_the_accepted_generic_substrate_accepts_the_sleeve_buckets() -> None:
    series = world_series()
    valuation = world.world_valuation()
    assert series.methodology.mtm_policy_id == f"sleeve-basis-{world.basis_policy().policy_digest}-mtm"
    assert series.series.status is PaperDailyReturnSeriesEvidenceStatus.READY, series.series.reason_codes
    assert series.series.daily_returns == tuple(day.daily_return for day in valuation.days)
    assert series.sharpe.status is PaperSharpeEvidenceStatus.READY, series.sharpe.reason_codes
    assert series.sharpe.sharpe_computed is True


def test_the_snapshot_values_are_the_rebuilt_series_and_sharpe_values() -> None:
    snapshot = world_performance()
    series = world_series()
    assert snapshot.daily_returns == series.series.daily_returns
    assert len(snapshot.daily_returns) == world.WINDOW_DAYS
    assert (snapshot.paper_sharpe_daily, snapshot.paper_sharpe_annualized) == (
        series.sharpe.paper_sharpe_daily,
        series.sharpe.paper_sharpe_annualized,
    )


def test_the_measure_is_the_one_the_rg2_envelope_commits() -> None:
    assert paper_portfolio_risk_envelope_rule_set()["performance_measure_id"] == PAPER_SLEEVE_PERFORMANCE_MEASURE_ID


def test_the_build_is_deterministic() -> None:
    assert build(performance_inputs()) == world_performance()


# --- governance precedence ------------------------------------------------------------------------------------------


def test_an_ungoverned_envelope_needs_governance_approval_and_carries_no_value() -> None:
    snapshot = build(performance_inputs(portfolio_risk_envelope=rg2.build()))
    assert snapshot.status is _NEEDS_GOVERNANCE
    assert snapshot.ready is False
    assert snapshot.reason_codes == (_code("portfolio_risk_envelope_not_governed"),)
    assert snapshot.sharpe_computed is True
    assert (snapshot.daily_returns, snapshot.paper_sharpe_daily, snapshot.paper_sharpe_annualized) == ((), "", "")
    assert snapshot.sharpe_evidence_digest == world_series().sharpe.sharpe_evidence_digest


def test_an_ungoverned_basis_policy_needs_governance_approval() -> None:
    snapshot = build(
        performance_inputs(**blocked_valuation_inputs(equity_basis_policy=world.basis_policy(governed=False)))
    )
    assert snapshot.status is _NEEDS_GOVERNANCE
    assert snapshot.reason_codes == tuple(
        sorted(
            {
                _code("equity_basis_policy_not_governed"),
                _code("valuation_not_computed"),
                _valuation_code("equity_basis_policy_not_governed"),
            }
        )
    )
    assert snapshot.equity_basis_policy_advances is False
    assert snapshot.valuation_status == "NOT_COMPUTABLE"


def test_governance_dominates_every_other_blocking_reason() -> None:
    snapshot = build(
        performance_inputs(
            portfolio_risk_envelope=rg2.build(),
            **blocked_valuation_inputs(equity_basis_policy=world.basis_policy(governed=False), funding_evidence=None),
        )
    )
    assert snapshot.status is _NEEDS_GOVERNANCE
    assert {
        _code("portfolio_risk_envelope_not_governed"),
        _code("equity_basis_policy_not_governed"),
        _valuation_code("funding_evidence_missing"),
    } <= set(snapshot.reason_codes)


# --- represented NOT_COMPUTABLE states ------------------------------------------------------------------------------


def test_missing_funding_is_not_computable() -> None:
    snapshot = build(performance_inputs(**blocked_valuation_inputs(funding_evidence=None)))
    assert snapshot.status is _NOT_COMPUTABLE
    assert snapshot.reason_codes == (_valuation_code("funding_evidence_missing"), _code("valuation_not_computed"))
    assert (snapshot.daily_returns, snapshot.paper_sharpe_annualized, snapshot.sharpe_computed) == ((), "", False)
    assert snapshot.methodology_digest == snapshot.daily_return_series_digest == ""


def test_a_computed_valuation_without_series_inputs_is_not_computable() -> None:
    snapshot = build(performance_inputs(**NO_SERIES))
    assert snapshot.status is _NOT_COMPUTABLE
    assert snapshot.reason_codes == (_code("daily_return_series_not_supplied"),)
    assert (snapshot.sharpe_status, snapshot.sharpe_computed, snapshot.paper_sharpe_annualized) == ("", False, "")


def test_an_insufficient_sample_is_not_computable_and_never_a_fake_sharpe() -> None:
    snapshot = build(performance_inputs(**short_window_inputs()))
    assert snapshot.status is _NOT_COMPUTABLE
    assert snapshot.day_count == SHORT_WINDOW_DAYS
    assert snapshot.daily_return_series_status == "READY"
    assert snapshot.sharpe_status == "REJECTED"
    assert snapshot.reason_codes == (
        "paper_sharpe_evidence:insufficient_bucket_count",
        "paper_sharpe_evidence:insufficient_daily_return_count",
        _code("sharpe_not_computed"),
    )
    assert (snapshot.daily_returns, snapshot.paper_sharpe_daily, snapshot.paper_sharpe_annualized) == ((), "", "")


def test_a_series_over_another_window_is_rejected_by_the_accepted_series() -> None:
    shifted = series_world(
        world.world_valuation(),
        world.basis_policy(),
        world.WINDOW_START + world.DAY_NS,
        world.WINDOW_END + world.DAY_NS,
    )
    snapshot = build(performance_inputs(**shifted.inputs()))
    assert snapshot.status is _NOT_COMPUTABLE
    assert snapshot.daily_return_series_status == "REJECTED"
    assert {
        "paper_daily_return_series_evidence:bucket_window_start_mismatch",
        "paper_daily_return_series_evidence:bucket_window_end_mismatch",
        _code("daily_return_series_not_ready"),
        _code("sharpe_not_computed"),
    } <= set(snapshot.reason_codes)
    assert snapshot.daily_returns == ()


# --- provenance and binding defects raise ---------------------------------------------------------------------------


def test_a_tampered_envelope_is_rejected() -> None:
    with _raises("portfolio_risk_envelope_not_intact"):
        build(performance_inputs(portfolio_risk_envelope=replace(world_envelope(), envelope_id="rg2-other")))


@pytest.mark.parametrize(
    ("envelope_overrides", "code"),
    [
        ({"sleeve_caps": [rg2.sleeve("sleeve-beta", "250")]}, "sleeve_not_declared_in_envelope"),
        ({"market_caps": [rg2.market("ETH-PERPETUAL", "500")]}, "market_not_declared_in_envelope"),
    ],
    ids=["sleeve", "market"],
)
def test_the_sleeve_and_market_must_be_declared_in_the_envelope(
    envelope_overrides: dict[str, object], code: str
) -> None:
    with _raises(code):
        build(performance_inputs(portfolio_risk_envelope=rg2.governed(**envelope_overrides)))


def test_a_resealed_valuation_forgery_is_rejected() -> None:
    valuation = world.world_valuation()
    days = (replace(valuation.days[0], equity_basis="1000", daily_return="0", normalized_index_end="1"),)
    forged = world._reseal(valuation, days=days + valuation.days[1:])  # noqa: SLF001
    with _raises("valuation_not_reconstructed"):
        build(performance_inputs(valuation=forged))


def test_a_valuation_of_other_inputs_is_rejected() -> None:
    other = build_paper_sleeve_daily_valuation_evidence(world.valuation_inputs(valuation_id="sleeve-valuation-2"))
    with _raises("valuation_not_reconstructed"):
        build(performance_inputs(valuation=other))


def test_unprovable_valuation_inputs_raise() -> None:
    donor = world.world_episodes()[1]
    forged_inputs = world.valuation_inputs(episodes=world._with_first_episode(fill_result=donor.fill_result))  # noqa: SLF001
    with _raises("valuation_reconstruction_failed"):
        build(performance_inputs(valuation_inputs=forged_inputs))


def test_the_valuation_correlation_must_be_the_snapshot_correlation() -> None:
    with _raises("valuation_correlation_mismatch"):
        build(performance_inputs(correlation_id="corr-other"))


@pytest.mark.parametrize("missing", SERIES_INPUT_NAMES)
def test_series_inputs_are_all_or_nothing(missing: str) -> None:
    with _raises("series_inputs_incomplete"):
        build(performance_inputs(**{missing: None}))


def test_series_inputs_for_an_uncomputed_valuation_are_rejected() -> None:
    blocked = blocked_valuation_inputs(funding_evidence=None)
    with _raises("series_inputs_supplied_for_uncomputed_valuation"):
        build(performance_inputs(valuation_inputs=blocked["valuation_inputs"], valuation=blocked["valuation"]))


@pytest.mark.parametrize("name", SERIES_INPUT_NAMES)
def test_series_inputs_of_another_type_are_rejected(name: str) -> None:
    with _raises(f"{name}_malformed"):
        build(performance_inputs(**{name: "not-an-artifact"}))


@pytest.mark.parametrize(
    "methodology_factory",
    [
        lambda: methodology_for(world.basis_policy(), mtm_policy_id="mtm-policy-other"),
        lambda: methodology_for(world.basis_policy(reference_notional="2000")),
    ],
    ids=["foreign-policy-id", "other-basis-policy"],
)
def test_a_methodology_not_bound_to_the_basis_policy_is_rejected(
    methodology_factory: Callable[[], PaperReturnSeriesMethodology],
) -> None:
    with _raises("methodology_not_bound_to_equity_basis_policy"):
        build(performance_inputs(methodology=methodology_factory()))


def test_a_genuine_series_over_other_buckets_is_rejected() -> None:
    policy = world.basis_policy(funding_treatment=PaperSleeveFundingTreatment.GOVERNED_NOT_APPLICABLE)
    other_valuation = build_paper_sleeve_daily_valuation_evidence(
        world.valuation_inputs(equity_basis_policy=policy, funding_evidence=None)
    )
    series = world_series()
    other_series = series_for(other_valuation, series.methodology, series.time_window)
    with _raises("daily_return_series_not_reconstructed"):
        build(performance_inputs(daily_return_series=other_series, sharpe_evidence=sharpe_for(other_series)))


def test_a_tampered_series_is_rejected() -> None:
    forged = replace(world_series().series, daily_returns=("0",) * world.WINDOW_DAYS)
    with _raises("daily_return_series_not_reconstructed"):
        build(performance_inputs(daily_return_series=forged))


def test_a_tampered_sharpe_is_rejected() -> None:
    forged = replace(world_series().sharpe, paper_sharpe_annualized="9.000000000000000000")
    with _raises("sharpe_evidence_not_reconstructed"):
        build(performance_inputs(sharpe_evidence=forged))


def test_a_series_of_another_correlation_is_rejected() -> None:
    series = world_series()
    other = series_for(world.world_valuation(), series.methodology, series.time_window, correlation_id="corr-other")
    with _raises("daily_return_series_correlation_mismatch"):
        build(performance_inputs(daily_return_series=other, sharpe_evidence=sharpe_for(other)))


MALFORMED_INPUTS: tuple[tuple[dict[str, object], str], ...] = (
    ({"performance_evidence_id": ""}, "performance_evidence_id_invalid"),
    ({"performance_evidence_id": "x" * 257}, "performance_evidence_id_invalid"),
    ({"performance_evidence_id": "bist-rg3"}, "bist_scope_leakage:performance_evidence_id"),
    ({"correlation_id": " padded"}, "correlation_id_invalid"),
    ({"correlation_id": "auto_loop"}, "forbidden_scope_token:correlation_id"),
    ({"portfolio_risk_envelope": None}, "portfolio_risk_envelope_malformed"),
    ({"valuation_inputs": None}, "valuation_inputs_malformed"),
    ({"valuation": None}, "valuation_malformed"),
)


@pytest.mark.parametrize(("changes", "code"), MALFORMED_INPUTS)
def test_malformed_inputs_raise(changes: dict[str, object], code: str) -> None:
    with _raises(code):
        build(performance_inputs(**changes))


def test_inputs_of_another_type_raise() -> None:
    with _raises("inputs_malformed"):
        build(world.valuation_inputs())


# --- serialization and verification ---------------------------------------------------------------------------------


def test_to_dict_and_digest_are_canonical() -> None:
    snapshot = world_performance()
    payload = paper_sleeve_performance_evidence_to_dict(snapshot)
    assert list(payload) == [field.name for field in fields(PaperSleevePerformanceEvidence)]
    assert payload["status"] == "READY"
    assert paper_sleeve_performance_evidence_digest(snapshot) == snapshot.performance_evidence_digest
    assert json.loads(edge_canonical_json(payload)) == payload


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"status": "READY"}, "payload_enum_field_not_exact_member"),
        ({"day_count": -1}, "payload_integer_out_of_range"),
        ({"daily_returns": []}, "payload_value_not_canonical"),
        ({"paper_sharpe_daily": 1.5}, "payload_value_not_canonical"),
    ],
)
def test_the_serializer_accepts_only_exact_values(changes: dict[str, object], code: str) -> None:
    with _raises(code):
        paper_sleeve_performance_evidence_digest(replace(world_performance(), **changes))


def test_the_verifier_accepts_the_genuine_snapshot() -> None:
    snapshot = world_performance()
    verification = verify_paper_sleeve_performance_evidence(snapshot, performance_inputs())
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == snapshot.performance_evidence_digest
    assert verification.canonical_json == edge_canonical_json(paper_sleeve_performance_evidence_to_dict(snapshot))


@pytest.mark.parametrize(
    "changes",
    [
        {"promotion_demotion_decided": True},
        {"portfolio_allocation_approved": True},
        {"portfolio_stop_evaluated": True},
        {"governance_threshold_selected": True},
        {"series_session_context_sleeve_proven": True},
        {"current_lifecycle_head_proven": True},
        {"sleeve_id": "sleeve-beta"},
        {"paper_sharpe_annualized": "9.000000000000000000"},
        {"envelope_advances": False},
    ],
    ids=lambda changes: next(iter(changes)),
)
def test_the_verifier_detects_a_resealed_forgery(changes: dict[str, object]) -> None:
    verification = verify_paper_sleeve_performance_evidence(
        _reseal(world_performance(), **changes), performance_inputs()
    )
    assert verification.intact is False
    assert set(verification.reason_codes) == {
        _code(f"field_mismatch:{next(iter(changes))}"),
        _code("field_mismatch:performance_evidence_digest"),
    }


def test_the_verifier_detects_an_unsealed_tamper() -> None:
    forged = replace(world_performance(), status=_NOT_COMPUTABLE)
    verification = verify_paper_sleeve_performance_evidence(forged, performance_inputs())
    assert set(verification.reason_codes) == {_code("self_digest_mismatch"), _code("field_mismatch:status")}


def test_the_verifier_binds_the_exact_inputs() -> None:
    verification = verify_paper_sleeve_performance_evidence(
        world_performance(), performance_inputs(performance_evidence_id="rg3-sleeve-alpha-2")
    )
    assert set(verification.reason_codes) == {
        _code("field_mismatch:performance_evidence_id"),
        _code("field_mismatch:performance_evidence_digest"),
    }


@pytest.mark.parametrize("evidence", [None, 0, "snapshot", object()], ids=["none", "int", "str", "object"])
def test_the_verifier_is_total_for_any_object(evidence: object) -> None:
    verification = verify_paper_sleeve_performance_evidence(evidence, performance_inputs())
    assert (verification.intact, verification.reason_codes) == (False, (_code("evidence_type_invalid"),))


def test_the_verifier_is_total_for_non_canonical_evidence_and_malformed_inputs() -> None:
    snapshot = world_performance()
    serialization = verify_paper_sleeve_performance_evidence(replace(snapshot, status="READY"), performance_inputs())
    assert serialization.reason_codes == (_code("evidence_serialization_failed"),)
    reconstruction = verify_paper_sleeve_performance_evidence(snapshot, None)  # type: ignore[arg-type]
    assert (reconstruction.intact, reconstruction.reason_codes) == (False, (_code("evidence_reconstruction_failed"),))


def test_the_snapshot_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        world_performance().ready = False  # type: ignore[misc]


# --- safety ---------------------------------------------------------------------------------------------------------


def test_non_claim_flags_are_structural_and_never_inputs() -> None:
    flags = dict(PAPER_SLEEVE_PERFORMANCE_NON_CLAIM_FLAGS)
    assert [name for name, value in flags.items() if value] == ["paper_only"]
    assert {
        "promotion_demotion_decided",
        "portfolio_allocation_approved",
        "portfolio_stop_evaluated",
        "capital_allocated",
        "governance_threshold_selected",
        "statistical_significance_proven",
        "account_equity_represented",
        "series_session_context_sleeve_proven",
        "episode_set_completeness_proven",
        "current_lifecycle_head_proven",
        "regime_evidence_available",
    } <= set(flags)
    defaults = {field.name: field.default for field in fields(PaperSleevePerformanceEvidence) if field.name in flags}
    assert defaults == flags
    snapshot = world_performance()
    assert {name: getattr(snapshot, name) for name in flags} == flags
    assert not set(flags) & {field.name for field in fields(PaperSleevePerformanceInputs)}


def test_inputs_carry_no_sleeve_label_threshold_or_decision() -> None:
    assert [field.name for field in fields(PaperSleevePerformanceInputs)] == [
        "performance_evidence_id",
        "correlation_id",
        "portfolio_risk_envelope",
        "valuation_inputs",
        "valuation",
        "methodology",
        "time_window",
        "daily_return_series",
        "sharpe_evidence",
    ]


def test_the_rg2_risk_budget_is_never_read() -> None:
    """RG-3 reads only the envelope's identity, governance and declarations; never a budget, cap or stop value."""

    tree = ast.parse(Path(performance_module.__file__).read_text(encoding="utf-8"))
    envelope_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "envelope"
    }
    cap_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "cap"
    }
    assert envelope_attributes == {"advances", "envelope_digest", "market_caps", "policy_digest", "sleeve_caps"}
    assert cap_attributes == {"market_symbol", "sleeve_id"}


def test_the_module_is_pure_and_consumes_only_the_accepted_substrate() -> None:
    world.pit.assert_module_is_pure(
        performance_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.paper_daily_return_series_evidence",
            "crypto_core.validation.paper_deterministic_time_window_adapter",
            "crypto_core.validation.paper_portfolio_risk_envelope",
            "crypto_core.validation.paper_return_series_methodology",
            "crypto_core.validation.paper_sharpe_evidence",
            "crypto_core.validation.paper_sleeve_daily_valuation_evidence",
            "crypto_core.validation.paper_sleeve_equity_basis_policy",
        },
    )


def test_one_construction_site_serves_the_builder_and_the_verifier() -> None:
    world.assert_single_construction_site(
        performance_module,
        "PaperSleevePerformanceEvidence",
        "build_paper_sleeve_performance_evidence",
        "verify_paper_sleeve_performance_evidence",
    )


def test_the_module_embeds_no_production_number() -> None:
    integers, decimals = world.module_literals(performance_module)
    # 0 is the wire minimum, and 32 and 127 bound control characters; the wire bounds come from the committed rule set.
    assert integers <= {0, 32, 127}
    assert decimals == set()


def test_the_public_api_is_exact() -> None:
    assert set(performance_module.__all__) == {
        "PAPER_SLEEVE_PERFORMANCE_MEASURE_ID",
        "PAPER_SLEEVE_PERFORMANCE_NON_CLAIM_FLAGS",
        "PaperSleevePerformanceEvidence",
        "PaperSleevePerformanceEvidenceError",
        "PaperSleevePerformanceInputs",
        "PaperSleevePerformanceStatus",
        "build_paper_sleeve_performance_evidence",
        "paper_sleeve_performance_evidence_digest",
        "paper_sleeve_performance_evidence_to_dict",
        "verify_paper_sleeve_performance_evidence",
    }
