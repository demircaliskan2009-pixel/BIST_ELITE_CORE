"""Governed paper integrated risk and system safety tests (S1_INTEGRATED_RISK_AND_SYSTEM_SAFETY_CLOSURE_V1).

SYNTHETIC TEST VALUES ONLY. Every policy, approval, bar, book, price path, latency and instant here is a synthetic fixture
that exercises structure. None is a calibrated threshold, a venue fact, a qualified source, a real market observation or
a real human decision. The structural interpretations CL2-7, CL2-9, CL2-10 and CL2-11 of
S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1 r2 were approved for construction only; that approval is not production
permission. The TEST-ONLY regime approval table is installed exactly as the regime closure's tests install it, and the
PRODUCTION entry gate stays in force throughout (no rule table is replaced).

It proves:

* A. the position-management policy v2: every v1 identity (builder, rule set, policy and engine results) equals accepted
  main; v2 is code-defined, digest-bound and reverifies totally; a v2 rule never hides behind a v1 payload; its method
  authorities keep DEC-9 unapproved and never extend the v1 table;
* B. the one engine under a policy v2: the nearer of the 1.5% initial stop and the ATR stop binds, at the exact boundary
  of each; a mark between the two stops triggers only the v2 stop; the DEC-9 reading tightens the ATR distance alone; a
  LONG open whose ATR stop is not positive is refused under v1 and protected by the initial stop under v2;
* C. the §1.29 proven lower bound: the doctrine values; every signal reading; the entry thresholds at their exact
  boundaries; the overrides; soundness and tightness against an exhaustive oracle; HALT and SS-0 never proven; the
  obligations; malformed inputs; the evidence; purity;
* D. rule set v7 in the gate: every v1-v6 identity unchanged; SYSTEM-STATE, HZ-STOP, HZ-LIMITS and SCALE-1 at their
  boundaries; the readings are the observation's own; no admission change; malformed facts refused;
* E. world G's integrated lineage (seal v8, evidence v8) under the TEST-ONLY regime table: it changes only its version,
  its rule set and the bound system-state evidence; a policy v2 authority passes HZ-STOP and admits nothing; lineage
  switches, relabelled versions and forged digests never verify; an audit replay on two UTC days reproduces every
  sealed reading, and no reading is revised by a later seal;
* F. legacy byte identity: world G's regime lineage (seal v7, evidence v7) equals its accepted-main pins.
"""

from __future__ import annotations

import ast
import functools
import inspect
import itertools
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.governed_paper_entry_safety as entry_safety
import crypto_core.validation.governed_paper_regime_state as regime
import crypto_core.validation.governed_paper_system_state as system_state
import crypto_core.validation.historical_position_management_policy as policy_module
from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_sha256_text
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    governed_paper_day_seal_to_dict,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_ID,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_entry_sequences,
    governed_paper_entry_safety_evidence_to_dict,
    governed_paper_entry_safety_rule_set,
    governed_paper_entry_safety_rule_set_digest,
    governed_paper_entry_safety_system_state_reading,
)
from crypto_core.validation.governed_paper_execution_authority import build_governed_paper_cycle_authority
from crypto_core.validation.governed_paper_protective_authority import build_governed_paper_protective_authority
from crypto_core.validation.governed_paper_system_state import (
    GOVERNED_PAPER_SYSTEM_STATE_NON_CLAIM_FLAGS,
    GOVERNED_PAPER_SYSTEM_STATE_RULE,
    GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST,
    GOVERNED_PAPER_SYSTEM_STATE_RULE_ID,
    GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS,
    GovernedPaperSystemStateError,
    GovernedPaperSystemStateMeasurement,
    GovernedPaperSystemStateObligationStatus,
    build_governed_paper_system_state_evidence,
    derive_governed_paper_system_state_reading,
    governed_paper_system_state_evidence_digest,
    governed_paper_system_state_id,
    governed_paper_system_state_reading_digest,
    governed_paper_system_state_rule,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionFillOutcome,
    HistoricalExecutionProtectiveTriggerKind,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_render_amount
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    build_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_position_management_policy import (
    INITIAL_STOP_FRACTION,
    INITIAL_STOP_HORIZON,
    INITIAL_STOP_RULE_V1,
    POSITION_MANAGEMENT_METHOD_AUTHORITY,
    POSITION_MANAGEMENT_RULE_SET_DIGEST,
    POSITION_MANAGEMENT_V2_METHOD_AUTHORITY,
    POSITION_MANAGEMENT_V2_RULE_SET,
    POSITION_MANAGEMENT_V2_RULE_SET_DIGEST,
    POSITION_MANAGEMENT_V2_RULE_SET_ID,
    STOP_BINDING_RULE_V1,
    TIGHTENING_DEC9_READING_V1,
    TIGHTENING_NOT_APPLIED_PENDING_DEC9,
    PositionManagementMethodAuthority,
    build_historical_position_management_policy,
    build_historical_position_management_policy_v2,
    historical_position_management_initial_stop_fraction,
    historical_position_management_methods_requiring_human_approval,
    historical_position_management_policy_digest,
    historical_position_management_policy_from_payload,
    historical_position_management_policy_payload_is_well_formed,
    historical_position_management_policy_to_dict,
    verify_historical_position_management_policy,
)

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_authority as prot
    import test_governed_paper_protective_lineage as lineage
    import test_governed_paper_regime_state as rst
    import test_historical_execution_protective_lifecycle as lifet
    import test_historical_pit_dataset as pit
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_authority as prot
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet
    from tests.crypto_core.validation import test_historical_pit_dataset as pit

SECOND = 1_000_000_000
MS = 1_000_000
HOUR = 3_600 * SECOND
UNIT = Fraction(1, 10**18)  # one scale-18 unit
S = GovernedPaperEntrySafetyStatus
BLOCKED = S.BLOCKED_ON_MISSING_INPUT
UNREPRESENTABLE = S.BLOCKED_PROTECTION_UNREPRESENTABLE
M = GovernedPaperSystemStateMeasurement
OB = GovernedPaperSystemStateObligationStatus
STOP = HistoricalExecutionProtectiveTriggerKind.STOP
MAX_HOLD = HistoricalExecutionProtectiveTriggerKind.MAX_HOLD
PRODUCTION_CHECKS = entry_safety._CHECKS  # noqa: SLF001 - captured at import, before any fixture could patch it
V2_FIELDS = ("initial_stop_rule_id", "initial_stop_horizon", "initial_stop_fraction", "stop_binding_rule_id")
V7_ADDED = ("HZ-STOP", "HZ-LIMITS", "SCALE-1")
V7, V8 = "governed-paper-day-seal.v7", "governed-paper-day-seal.v8"
render = historical_execution_render_amount

# The accepted-main identities this contract never changes, pinned on main 61d3611d before it (PR #430's merge): the
# position-management v1 rule set and policy, three v1 protective lifecycle economics, rule set v6 and world G's regime
# lineage (seal v7, evidence v7) under the TEST-ONLY regime table.
ACCEPTED_MAIN_PM_RULE_SET_V1_DIGEST = "3c507cc35d05df234d48d3dc7e9c57ea14d5a2276444cef65de224971f68a69d"
ACCEPTED_MAIN_PM_POLICY_V1_DIGEST = "054a3bdec9961972491e2e4f6090803814f280a0239e6b1112f5bf845199c7e7"
ACCEPTED_MAIN_LIFECYCLE_V1_RESULTS = {
    "hold": "d106c6899663fc63d31158cedd65b9387b64c8c5189d5ae91025f0df159e47dc",
    "dec9": "22045e854ba9ece157d9fe359da83562e4cdffd32ef226b98542e87d0732a75d",
    "pending": "5a6c96a89c810d5b6229c74bee8f8866c7d74278ed31fba84646500add28d7d7",
}
ACCEPTED_MAIN_RULE_SET_V6_DIGEST = "b9ab91894290ee6e104e9dccc1a421f284b970fda657b2d1795a9a091b9510dc"
ACCEPTED_MAIN_V7_SEALS = (
    "070ccd8c95115709e4af687ddecf70d9cdf6c65dd3d7811c07ae251961a11640",
    "7309882237b4edbbbd1883256a44961d167e8b5606292b356a732b3d1f645798",
    "18e33e8c19321072149b36cfd1addbb081a0facbd0c42178119add2c00204c82",
    "27590aad45dea57664f3d0012354682b2207795f6062f6dec11af050c50b566b",
)
ACCEPTED_MAIN_V7_ENTRY_EVIDENCE = (
    "8f170888dcca650ca99c8e27724240e31f11cba6d4a3520398e82f2c9cd5ca06",
    "d44c9ce2f34cd3b9d40beb4c1a375607fb8965775c2117d1b81870c345f3b9c5",
    "89aa23f38a052b984adf04ccf7eb648ac392c8fbab491dcf01984dfd218dcabe",
    "aa2ef14468603f7aca9fbc8f77bd906972e7d36a0212913b8c7a6a199ec9decf",
)
ACCEPTED_MAIN_V7_REGIME_EVIDENCE = (
    "cab3632835af9bd273948f81f8e88b5dc80e006298708e9f8f074b2922a2d13b",
    "abf2384c9ef30e50fe6b66acc6c91748dc45ae79699d46e87589133387532f27",
    "fda0e4166d95358f8df3251f9817753f1043eb5a9390a0e658db94ca1fb7cf68",
    "615e6cfd1fed22a430ecf15dabaa78f0ace2abb46882f56717044318f2fc4b83",
)
ACCEPTED_MAIN_V7_REGIME_PREFIX_CLOSE = (
    "74fb2a07f60e96c347d4861df1281fc38c48b6c29db278ad3ba13c4631c15901",
    "8f78bbf2deb94109b19d73741448fa969ea82e71f3a4d3f3f6b0fb33df97bb72",
    "f13e21f9131308a40d4d4f933571a6fc766c8b0a7ab249c03918f90e55724270",
    "e5607e5bd57c0b6f7137d272e659e2b93eef9b2da8337e1074e29ab184420667",
)
ACCEPTED_MAIN_V7_LINEAGE_EVIDENCE = "e98ed7be3896a2f28118e6f5fd7a1f251cf9710cb2fda38e53ced141ee6bec15"


@pytest.fixture(autouse=True, scope="module")
def _production_tables_with_exact_memos():
    """The exact upstream memos and identity memos of pure re-proofs; the PRODUCTION rule and approval tables stay."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        archives = gpe.SameObjects(regime.verify_historical_ohlc_bar_archive)
        patch.setattr(regime, "verify_historical_ohlc_bar_archive", archives)
        patch.setattr(gpe.execution, "verify_historical_ohlc_bar_archive", archives)
        patch.setattr(
            regime, "verify_historical_pit_dataset", gpe._EXACT[(gpe.execution, "verify_historical_pit_dataset")]
        )  # noqa: SLF001
        assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
        assert regime._APPROVAL_TABLE is rst.PRODUCTION_TABLE  # noqa: SLF001
        yield


# --- A. the position-management policy v2 --------------------------------------------------------------------------------


def policy_of(builder: object, tightening: str = TIGHTENING_NOT_APPLIED_PENDING_DEC9, **changes: object):  # noqa: ANN201
    arguments: dict[str, object] = {
        "policy_id": "pm-policy-1",
        "policy_version": "synthetic-v1",
        "instrument": lifet.INS,
        "atr_bar_price_semantics": HistoricalOhlcPriceSemantics.MARK_PRICE,
        "atr_max_bar_age_ns": 8 * HOUR,
        "stop_tightening_method_id": tightening,
    }
    arguments.update(changes)
    return builder(**arguments)  # type: ignore[operator]


@functools.cache
def pm_v2(tightening: str = TIGHTENING_NOT_APPLIED_PENDING_DEC9):  # noqa: ANN201
    """SYNTHETIC policy v2 with exactly the governed inputs of the lifecycle tests' v1 ``pm_policy``."""

    return policy_of(build_historical_position_management_policy_v2, tightening)


def resealed(policy: object, **changes: object):  # noqa: ANN201
    changed = replace(policy, **changes)  # type: ignore[type-var]
    return replace(changed, policy_digest=historical_position_management_policy_digest(changed))


def test_every_v1_position_management_identity_and_v1_engine_result_equals_accepted_main() -> None:
    assert POSITION_MANAGEMENT_RULE_SET_DIGEST == ACCEPTED_MAIN_PM_RULE_SET_V1_DIGEST
    v1 = lifet.pm_policy()
    assert (v1.schema_version, v1.policy_digest) == (
        "historical-position-management-policy.v1",
        ACCEPTED_MAIN_PM_POLICY_V1_DIGEST,
    )
    assert all(getattr(v1, name) == "" for name in V2_FIELDS)
    assert not set(V2_FIELDS) & set(historical_position_management_policy_to_dict(v1))
    assert historical_position_management_initial_stop_fraction(v1) is None
    results = {
        "hold": lifet.hold_result(),
        "dec9": lifet.tightened(TIGHTENING_DEC9_READING_V1),
        "pending": lifet.tightened(TIGHTENING_NOT_APPLIED_PENDING_DEC9),
    }
    assert {name: item.result_digest for name, item in results.items()} == ACCEPTED_MAIN_LIFECYCLE_V1_RESULTS
    # the v1 builder keeps exactly its six governed inputs and no default: the v2 opt-in is a separate builder
    parameters = inspect.signature(build_historical_position_management_policy).parameters
    assert len(parameters) == 6 and all(item.default is inspect.Parameter.empty for item in parameters.values())


def test_policy_v2_is_code_defined_digest_bound_and_reverifies_totally() -> None:
    v1, v2 = lifet.pm_policy(), pm_v2()
    assert (v2.schema_version, v2.rule_set_id, v2.rule_set_digest) == (
        "historical-position-management-policy.v2",
        POSITION_MANAGEMENT_V2_RULE_SET_ID,
        POSITION_MANAGEMENT_V2_RULE_SET_DIGEST,
    )
    assert POSITION_MANAGEMENT_V2_RULE_SET_ID == "historical-position-management.v2"
    assert POSITION_MANAGEMENT_V2_RULE_SET_DIGEST == edge_sha256_text(
        edge_canonical_json(POSITION_MANAGEMENT_V2_RULE_SET)
    )
    assert (v2.initial_stop_rule_id, v2.initial_stop_horizon, v2.initial_stop_fraction, v2.stop_binding_rule_id) == (
        INITIAL_STOP_RULE_V1,
        "INTRADAY",
        "0.015000000000000000",
        STOP_BINDING_RULE_V1,
    )
    assert (INITIAL_STOP_FRACTION, INITIAL_STOP_HORIZON) == (Fraction(3, 200), "INTRADAY")
    assert historical_position_management_initial_stop_fraction(v2) == Fraction(3, 200)
    one, two = historical_position_management_policy_to_dict(v1), historical_position_management_policy_to_dict(v2)
    assert set(two) - set(one) == set(V2_FIELDS)
    identity = ("schema_version", "rule_set_id", "rule_set_digest", "policy_digest")
    assert {key: value for key, value in two.items() if key in one and key not in identity} == {
        key: value for key, value in one.items() if key not in identity
    }
    # the v2 rule set is the v1 rule set with only the initial stop and its binding added
    v1_rules, v2_rules = policy_module.POSITION_MANAGEMENT_RULE_SET, POSITION_MANAGEMENT_V2_RULE_SET
    changed = ("rule_set_id", "contract_id", "authorities", "method_authority")
    assert {key: value for key, value in v2_rules.items() if key in v1_rules and key not in changed} == {
        key: value for key, value in v1_rules.items() if key not in changed
    }
    assert set(v2_rules) - set(v1_rules) == {
        "initial_stop_rule_id",
        "initial_stop_horizon",
        "initial_stop_fraction",
        "initial_stop_basis",
        "stop_binding_rule_id",
        "stop_binding",
        "stop_binding_tightening",
    }
    verification = verify_historical_position_management_policy(v2)
    assert (verification.intact, verification.recomputed_digest) == (True, v2.policy_digest)
    assert v2.policy_digest == historical_position_management_policy_digest(v2) != v1.policy_digest
    assert historical_position_management_policy_payload_is_well_formed(two)
    assert historical_position_management_policy_from_payload(json.loads(edge_canonical_json(two))) == v2
    parameters = inspect.signature(build_historical_position_management_policy_v2).parameters
    assert set(parameters) == set(inspect.signature(build_historical_position_management_policy).parameters)
    assert all(item.default is inspect.Parameter.empty for item in parameters.values())
    # every governed input still changes the digest under v2
    assert policy_of(build_historical_position_management_policy_v2, atr_max_bar_age_ns=9 * HOUR).policy_digest != (
        v2.policy_digest
    )


@pytest.mark.parametrize(
    "forge",
    [
        lambda: replace(lifet.pm_policy(), initial_stop_fraction="0.015000000000000000"),  # behind a v1 payload
        lambda: resealed(pm_v2(), initial_stop_fraction="0.020000000000000000"),
        lambda: resealed(pm_v2(), initial_stop_horizon="SWING"),
        lambda: resealed(pm_v2(), stop_binding_rule_id="THE_FARTHER_STOP_BINDS_V1"),
        lambda: resealed(pm_v2(), initial_stop_rule_id=""),
        lambda: resealed(pm_v2(), rule_set_digest=POSITION_MANAGEMENT_RULE_SET_DIGEST),
        lambda: replace(pm_v2(), schema_version="historical-position-management-policy.v1"),
        lambda: resealed(lifet.pm_policy(), schema_version="historical-position-management-policy.v2"),
    ],
)
def test_a_v2_rule_never_hides_behind_a_v1_payload_and_a_resealed_v2_value_never_verifies(forge: object) -> None:
    assert verify_historical_position_management_policy(forge()).intact is False  # type: ignore[operator]


def test_the_strict_parser_reads_exactly_the_fields_of_each_schema() -> None:
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:initial_stop_fraction$"):
        historical_position_management_policy_to_dict(
            replace(lifet.pm_policy(), initial_stop_fraction="0.015000000000000000")
        )
    one = historical_position_management_policy_to_dict(lifet.pm_policy())
    two = historical_position_management_policy_to_dict(pm_v2())
    assert historical_position_management_policy_payload_is_well_formed(one)
    for payload in (
        {**one, "initial_stop_fraction": ""},  # a v1 payload never carries a v2 field, not even an empty one
        {key: value for key, value in two.items() if key != "stop_binding_rule_id"},
        {**two, "initial_stop_basis": "executed_price_of_the_opening_fill"},
    ):
        assert not historical_position_management_policy_payload_is_well_formed(payload)


def test_the_v2_authorities_keep_dec9_unapproved_and_never_extend_the_v1_table() -> None:
    authority = POSITION_MANAGEMENT_V2_METHOD_AUTHORITY
    assert authority[INITIAL_STOP_RULE_V1] is PositionManagementMethodAuthority.PRDV4_DOCTRINE
    assert authority[STOP_BINDING_RULE_V1] is PositionManagementMethodAuthority.HUMAN_AUTHORIZED  # CL2-10
    assert {key: value for key, value in authority.items() if key in POSITION_MANAGEMENT_METHOD_AUTHORITY} == (
        POSITION_MANAGEMENT_METHOD_AUTHORITY
    )
    assert not {INITIAL_STOP_RULE_V1, STOP_BINDING_RULE_V1} & set(POSITION_MANAGEMENT_METHOD_AUTHORITY)
    assert POSITION_MANAGEMENT_V2_RULE_SET["method_authority"][STOP_BINDING_RULE_V1] == "HUMAN_AUTHORIZED"  # type: ignore[index]
    assert historical_position_management_methods_requiring_human_approval(pm_v2()) == ()
    assert historical_position_management_methods_requiring_human_approval(pm_v2(TIGHTENING_DEC9_READING_V1)) == (
        TIGHTENING_DEC9_READING_V1,
    )


# --- B. the one engine under a policy v2 -------------------------------------------------------------------------------------

END_2D = lifet.ANCHOR + 2 * lifet.DAY
BETWEEN = lifet.Path(rates=(lifet.POSITIVE,) * 6, mark=lifet.jump(48, 102))  # strictly between the v2 and v1 stops
LONG = lifet.Path(rates=(lifet.NEGATIVE,) * 6)  # LONG from D_0, flat marks


@functools.cache
def archive_of(true_range: Fraction) -> HistoricalOhlcBarArchive:
    """Flat SYNTHETIC 4 h bars -24..24 whose every true range is exactly ``true_range``: so is the Wilder ATR."""

    bars = tuple(lifet.bar(k, true_range=true_range) for k in range(-24, 25))
    name = f"{true_range.numerator}-{true_range.denominator}"
    return build_historical_ohlc_bar_archive(
        archive_id=f"ohlc-protective-tr-{name}", source=lifet.ohlc_source(), bars=bars
    )


@functools.cache
def run_under(
    path: object,
    end: int,
    version: str,
    true_range: Fraction = Fraction(2),
    tightening: str = TIGHTENING_NOT_APPLIED_PENDING_DEC9,
):  # noqa: ANN201
    """The one engine over ``path`` under the v1 or v2 policy and a flat archive of ``true_range``."""

    policy = lifet.pm_policy(tightening) if version == "v1" else pm_v2(tightening)
    archive = lifet.ohlc_archive() if true_range == 2 else archive_of(true_range)
    return lifet.computed(lifet.managed(lifet.world(path, end=end), policy=policy, archive=archive))


def levels(protection: object) -> list[tuple[int, str, str]]:
    return [(item.milestone, item.stop_distance, item.stop_price) for item in protection.stop_levels]  # type: ignore[attr-defined]


def test_under_a_policy_v2_the_nearer_1_5pct_initial_stop_binds_over_a_wider_atr_stop() -> None:
    v1, v2 = lifet.hold_result(), run_under(lifet.HOLD, lifet.HOLD_END, "v2")
    one, two = v1.excursion_protections[0], v2.excursion_protections[0]
    basis = Fraction(two.basis_price)
    assert basis == lifet.basis() and two.direction == "SHORT"
    assert (
        (two.atr_value, two.stop_atr_multiple) == (one.atr_value, one.stop_atr_multiple) == (lifet.d(2), lifet.d("1.5"))
    )
    assert levels(one) == [(0, lifet.d(3), render(basis + 3))]
    initial = basis * INITIAL_STOP_FRACTION
    assert initial < 3
    assert levels(two) == [(0, render(initial), render(basis + initial))]
    assert v2.position_management_policy_digest == pm_v2().policy_digest != v1.position_management_policy_digest
    # the flat path reaches neither stop: only the 24 h deadline closes the excursion, and every fill is the v1 fill
    triggers = [[item.trigger_kind for item in obligation.triggers] for obligation in v2.protective_obligations]
    assert triggers == [[item.trigger_kind for item in obligation.triggers] for obligation in v1.protective_obligations]
    assert [(item.execution_time_ns, item.fill_price, item.outcome) for item in v2.fills] == [
        (item.execution_time_ns, item.fill_price, item.outcome) for item in v1.fills
    ]


def test_a_mark_between_the_two_stops_triggers_only_the_policy_v2_stop() -> None:
    v1, v2 = run_under(BETWEEN, END_2D, "v1"), run_under(BETWEEN, END_2D, "v2")
    basis = lifet.basis()
    assert basis * Fraction(203, 200) < 102 < basis + 3
    assert [item.trigger_kind for item in v1.protective_obligations[0].triggers] == [MAX_HOLD]
    (trigger,) = v2.protective_obligations[0].triggers
    assert (trigger.trigger_kind, trigger.trigger_time_ns, trigger.mark_price) == (
        STOP,
        lifet.slot(48) + lifet.VISIBLE,
        lifet.d(102),
    )
    assert Fraction(trigger.stop_price) == basis * Fraction(203, 200)  # type: ignore[arg-type]
    close = lifet.protective_fills(v2)[0]
    assert close.execution_time_ns == lifet.book_visible(48)  # the close-only fill at the next eligible book


@pytest.mark.parametrize(("offset", "stopped"), [(Fraction(0), True), (-UNIT, False)])
def test_the_exact_v2_stop_boundary_triggers_and_one_unit_inside_does_not(offset: Fraction, stopped: bool) -> None:
    level = lifet.basis() * Fraction(203, 200) + offset
    result = run_under(lifet.Path(rates=(lifet.POSITIVE,) * 6, mark=lifet.jump(48, level)), END_2D, "v2")
    kinds = [item.trigger_kind for item in result.protective_obligations[0].triggers]
    assert kinds == ([STOP] if stopped else [MAX_HOLD])


@pytest.mark.parametrize("case", ["atr_nearer", "equally_near"])
def test_when_the_atr_stop_is_not_farther_the_policy_v2_levels_are_the_v1_levels(case: str) -> None:
    basis = lifet.basis()
    true_range = Fraction(1, 2) if case == "atr_nearer" else basis / 100  # 1.5 x basis / 100 = 1.5% of the basis
    v1 = run_under(lifet.HOLD, lifet.HOLD_END, "v1", true_range)
    v2 = run_under(lifet.HOLD, lifet.HOLD_END, "v2", true_range)
    one, two = v1.excursion_protections[0], v2.excursion_protections[0]
    assert Fraction(two.basis_price) == basis and Fraction(two.atr_value) == true_range
    atr_distance = Fraction(3, 2) * true_range
    assert (atr_distance < basis * INITIAL_STOP_FRACTION) is (case == "atr_nearer")
    assert atr_distance <= basis * INITIAL_STOP_FRACTION
    assert levels(two) == levels(one) == [(0, render(atr_distance), render(basis + atr_distance))]


def test_the_dec9_reading_tightens_the_atr_distance_alone_and_the_initial_distance_never_moves() -> None:
    true_range = Fraction(6, 5)
    result = run_under(lifet.HOLD, lifet.HOLD_END, "v2", true_range, TIGHTENING_DEC9_READING_V1)
    protection = result.excursion_protections[0]
    basis = Fraction(protection.basis_price)
    atr, initial = Fraction(3, 2) * true_range, basis * INITIAL_STOP_FRACTION
    expected = [min(atr * Fraction(4, 5) ** milestone, initial) for milestone in range(3)]
    # the initial stop binds first; the tightened ATR stop is nearer from the first complete 8 h period on
    assert expected == [initial, atr * Fraction(4, 5), atr * Fraction(16, 25)]
    assert levels(protection) == [
        (milestone, render(value), render(basis + value)) for milestone, value in enumerate(expected)
    ]
    assert all(later <= earlier for earlier, later in itertools.pairwise(expected))  # it never loosens


def test_a_long_open_whose_atr_stop_is_not_positive_is_refused_under_v1_and_protected_under_v2() -> None:
    true_range = Fraction(80)  # 1.5 x ATR = 120: the §1.9 stop alone would lie below zero
    v1 = run_under(LONG, END_2D, "v1", true_range)
    refused = [item for item in v1.fills if item.outcome is HistoricalExecutionFillOutcome.REJECTED]
    assert refused and {item.reason for item in refused} == {"position_management_stop_price_not_positive"}
    assert lifet.executed(v1) == [] and v1.excursion_protections == ()
    v2 = run_under(LONG, END_2D, "v2", true_range)
    first = v2.excursion_protections[0]
    basis = Fraction(first.basis_price)
    assert first.direction == "LONG" and Fraction(3, 2) * true_range > basis
    assert levels(first) == [(0, render(basis * INITIAL_STOP_FRACTION), render(basis * Fraction(197, 200)))]


# --- C. the §1.29 proven lower bound ----------------------------------------------------------------------------------------

DATA_IDS = tuple(f"NT-D0{index}" for index in range(1, 6))
EXECUTION_IDS = tuple(f"NT-X0{index}" for index in range(1, 5))
WEIGHTS = {
    "S1": Fraction(20, 100),
    "S2": Fraction(15, 100),
    "S3": Fraction(15, 100),
    "S4": Fraction(10, 100),
    "S5": Fraction(10, 100),
    "S6": Fraction(8, 100),
    "S7": Fraction(7, 100),
    "S8": Fraction(5, 100),
    "S9": Fraction(5, 100),
    "S10": Fraction(5, 100),
}


def data(failing: int) -> tuple[tuple[str, str], ...]:
    """NT-D01..NT-D05: the first ``failing`` proven active, the rest measured inactive."""

    return tuple((name, "FAIL" if index < failing else "PASS") for index, name in enumerate(DATA_IDS))


def execution(failing: int) -> tuple[tuple[str, str], ...]:
    """NT-X01..NT-X04: the first ``failing`` proven active; otherwise NT-X01 passes and the rest are BLOCKED."""

    return tuple(
        (name, "FAIL" if index < failing else ("PASS" if index == 0 else "BLOCKED_ON_MISSING_INPUT"))
        for index, name in enumerate(EXECUTION_IDS)
    )


def reading(**changes: object):  # noqa: ANN201
    values: dict[str, object] = {
        "decision_sequence": 7,
        "decision_time_ns": est.T,
        "kill_switch_level": 0,
        "drawdown_beyond_10pct_proven": False,
        "drawdown_beyond_15pct_proven": False,
        "data_statuses": data(0),
        "execution_statuses": execution(0),
        "latency_ns": 50 * MS,
        "latency_budget_ns": 100 * MS,
        "single_instrument_portfolio": True,
    }
    values.update(changes)
    return derive_governed_paper_system_state_reading(**values)  # type: ignore[arg-type]


def lower(item: object, signal_id: str) -> Fraction:
    return Fraction(next(signal.lower_bound for signal in item.signals if signal.signal_id == signal_id))  # type: ignore[attr-defined]


def measurement(item: object, signal_id: str) -> GovernedPaperSystemStateMeasurement:
    return next(signal.measurement for signal in item.signals if signal.signal_id == signal_id)  # type: ignore[attr-defined]


def test_the_rule_carries_exactly_the_prdv4_1_29_doctrine_values() -> None:
    rule = GOVERNED_PAPER_SYSTEM_STATE_RULE
    weights = {name: Fraction(value) for name, value in rule["weights"].items()}  # type: ignore[union-attr]
    assert weights == WEIGHTS and sum(weights.values()) == 1
    assert tuple(weights) == GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS == tuple(f"S{index}" for index in range(1, 11))
    assert {name: Fraction(value) for name, value in rule["state_entry_shs_at_or_below"].items()} == {  # type: ignore[union-attr]
        "SS-4": Fraction(15, 100),
        "SS-3": Fraction(35, 100),
        "SS-2": Fraction(60, 100),
        "SS-1": Fraction(80, 100),
    }
    assert rule["states"] == ["SS-0:NORMAL", "SS-1:DEGRADED", "SS-2:DEFENSIVE", "SS-3:CRISIS", "SS-4:HALT"]
    assert rule["unmeasured"] == ["S3", "S6", "S7", "S9"]
    assert (rule["rule_id"], GOVERNED_PAPER_SYSTEM_STATE_RULE_ID) == (
        "governed-paper-system-state-proven-lower-bound.v1",
    ) * 2
    assert (
        GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST
        == edge_sha256_text(edge_canonical_json(rule))
        == edge_sha256_text(edge_canonical_json(governed_paper_system_state_rule()))
    )


def test_each_signal_reads_only_its_proven_lower_bound() -> None:
    base = reading()
    assert [item.signal_id for item in base.signals] == list(GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS)
    assert {item.signal_id: item.measurement for item in base.signals} == {
        **dict.fromkeys(("S1", "S2", "S4", "S5", "S10"), M.LOWER_BOUND),
        **dict.fromkeys(("S3", "S6", "S7", "S9"), M.UNMEASURED),
        "S8": M.PROVEN_NOT_APPLICABLE,
    }
    assert {item.signal_id: Fraction(item.lower_bound) for item in base.signals} == {
        **{name: Fraction(0) for name in GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS},
        "S10": Fraction(1, 10),  # 50 ms over five times the 100 ms T1 budget
    }
    assert (Fraction(base.stress_lower_bound), Fraction(base.shs_upper_bound)) == (
        Fraction(5, 1000),
        Fraction(995, 1000),
    )
    assert (base.state_lower_bound, base.state_reason, base.obligations) == (0, "no_state_above_ss0_proven", ())
    assert base.unmeasured_signal_ids == ("S3", "S6", "S7", "S9") and governed_paper_system_state_id(base) == "SS-0"
    assert {item.signal_id: item.weight for item in base.signals} == {
        name: render(value) for name, value in WEIGHTS.items()
    }
    for level in range(4):
        assert lower(reading(kill_switch_level=level), "S1") == Fraction(level, 4)
    # 2/3 is not exact at scale 18: a lower bound renders DOWN, so its rendering never claims more than is proven
    assert lower(reading(drawdown_beyond_10pct_proven=True), "S2") == Fraction(666_666_666_666_666_666, 10**18)
    assert lower(reading(drawdown_beyond_10pct_proven=True), "S2") < Fraction(2, 3)
    assert lower(reading(drawdown_beyond_10pct_proven=True, drawdown_beyond_15pct_proven=True), "S2") == 1
    for failing in range(6):
        assert lower(reading(data_statuses=data(failing)), "S4") == Fraction(failing, 5)
    # a BLOCKED condition is unknown: never inactive and never active
    unknown = tuple((name, "BLOCKED_ON_MISSING_INPUT") for name in DATA_IDS)
    assert lower(reading(data_statuses=unknown), "S4") == 0 and measurement(reading(data_statuses=unknown), "S4") is (
        M.LOWER_BOUND
    )
    for failing in range(5):
        assert lower(reading(execution_statuses=execution(failing)), "S5") == Fraction(failing, 4)
    for latency, expected in ((0, 0), (250 * MS, Fraction(1, 2)), (500 * MS, 1), (2 * SECOND, 1)):
        assert lower(reading(latency_ns=latency), "S10") == expected
    budgetless = reading(latency_budget_ns=None)
    assert (measurement(budgetless, "S10"), lower(budgetless, "S10")) == (M.UNMEASURED, 0)
    assert budgetless.unmeasured_signal_ids == ("S3", "S6", "S7", "S9", "S10")
    multi = reading(single_instrument_portfolio=False)
    assert measurement(multi, "S8") is M.UNMEASURED and multi.unmeasured_signal_ids == ("S3", "S6", "S7", "S8", "S9")


TWO_DATA_AT_100MS = {"kill_switch_level": 3, "data_statuses": data(2), "latency_ns": 100 * MS}  # stress exactly 0.20
DEFENSIVE_AT_200MS = {
    "kill_switch_level": 3,
    "drawdown_beyond_10pct_proven": True,
    "data_statuses": data(4),
    "execution_statuses": execution(2),
    "latency_ns": 200 * MS,
}  # stress 0.15 + 0.10 + 0.08 + 0.05 + 0.02 = exactly 0.40


@pytest.mark.parametrize(
    ("changes", "state", "reason"),
    [
        (TWO_DATA_AT_100MS, 1, "shs_upper_bound_at_or_below_the_degraded_entry"),
        ({**TWO_DATA_AT_100MS, "latency_ns": 100 * MS - 1}, 0, "no_state_above_ss0_proven"),
        (DEFENSIVE_AT_200MS, 2, "shs_upper_bound_at_or_below_the_defensive_entry"),
        ({**DEFENSIVE_AT_200MS, "latency_ns": 200 * MS - 1}, 1, "shs_upper_bound_at_or_below_the_degraded_entry"),
        ({"latency_ns": 500 * MS}, 3, "critical_override_s10_severity_1"),
        ({"latency_ns": 500 * MS - 1}, 0, "no_state_above_ss0_proven"),
        (
            {"drawdown_beyond_10pct_proven": True, "drawdown_beyond_15pct_proven": True},
            3,
            "critical_override_s2_severity_1",
        ),
        ({"execution_statuses": execution(4)}, 3, "critical_override_s5_severity_1"),
        ({"data_statuses": data(5)}, 2, "critical_override_s4_severity_1"),  # the DEFENSIVE minimum, never CRISIS
        ({**DEFENSIVE_AT_200MS, "latency_ns": 500 * MS}, 3, "critical_override_s10_severity_1"),
    ],
)
def test_the_bound_meets_each_entry_threshold_and_override_exactly(
    changes: dict[str, object], state: int, reason: str
) -> None:
    item = reading(**changes)
    assert (item.state_lower_bound, item.state_reason) == (state, reason)
    assert Fraction(item.shs_upper_bound) == 1 - Fraction(item.stress_lower_bound)
    assert item.reading_digest == governed_paper_system_state_reading_digest(item)


def oracle(severities: dict[str, Fraction], *, s4_specific: bool) -> int:
    """An independent PRDV4 §1.29 state of exact severities: the SHS entry thresholds, then the critical overrides. With
    ``s4_specific`` the complete-data-loss rule is read as the DEFENSIVE minimum, otherwise as any severity of 1."""

    shs = 1 - sum(WEIGHTS[name] * value for name, value in severities.items())
    state = next(
        (level for level, bound in ((4, "0.15"), (3, "0.35"), (2, "0.60"), (1, "0.80")) if shs <= Fraction(bound)), 0
    )
    for name, value in severities.items():
        if value == 1:
            state = max(state, 2 if name == "S4" and s4_specific else 3)
    return state


def test_the_bound_is_sound_and_tight_under_every_completion_and_never_reaches_halt() -> None:
    latencies = (0, 100 * MS, 200 * MS, 499 * MS, 500 * MS)
    drawdowns = ((False, False), (True, False), (True, True))
    for level, (ten, fifteen), failing_data, failing_execution, latency in itertools.product(
        range(4), drawdowns, range(6), range(5), latencies
    ):
        item = reading(
            kill_switch_level=level,
            drawdown_beyond_10pct_proven=ten,
            drawdown_beyond_15pct_proven=fifteen,
            data_statuses=data(failing_data),
            execution_statuses=execution(failing_execution),
            latency_ns=latency,
        )
        assert item.state_lower_bound < 4 and item.unmeasured_signal_ids == ("S3", "S6", "S7", "S9")
        # the exact proven severities, derived independently of the module from the inputs alone
        measured = {
            **{name: Fraction(0) for name in GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS},
            "S1": Fraction(level, 4),
            "S2": Fraction(1) if fifteen else Fraction(2, 3) if ten else Fraction(0),
            "S4": Fraction(failing_data, 5),
            "S5": Fraction(failing_execution, 4),
            "S10": min(Fraction(1), Fraction(latency, 500 * MS)),
        }
        # each rendering keeps its direction: a severity and the stress never above, the SHS bound never below, exact
        assert all(Fraction(signal.lower_bound) <= measured[signal.signal_id] for signal in item.signals)
        stress = sum(WEIGHTS[name] * value for name, value in measured.items())
        assert Fraction(item.stress_lower_bound) <= stress and Fraction(item.shs_upper_bound) >= 1 - stress
        # tight: the bound IS the state of the minimal completion under the weaker reading of the S4 override
        assert item.state_lower_bound == oracle(measured, s4_specific=True)
        # sound: the extreme completions of the unmeasured signals and higher measured severities, under both readings
        # (the state is monotone in every severity, so the extremes bound every completion between them)
        for completion in itertools.product((Fraction(0), Fraction(1)), repeat=4):
            completed = {**measured, **dict(zip(("S3", "S6", "S7", "S9"), completion, strict=True))}
            raised = {name: max(value, Fraction(1, 2)) for name, value in completed.items()}
            for severities, specific in itertools.product((completed, raised), (True, False)):
                assert oracle(severities, s4_specific=specific) >= item.state_lower_bound


def test_the_obligations_are_the_per_state_rules_of_the_bound_and_none_is_executed() -> None:
    expected = {
        1: [
            ("t0_and_t1_edges_suspended", OB.ENFORCED_BY_ENTRY_REFUSAL),
            ("remaining_allocation_reduced_by_30pct", OB.FAIL_CLOSED_BY_SCALE_1),
        ],
        2: [
            ("no_new_entries_across_all_horizons", OB.ENFORCED_BY_ENTRY_REFUSAL),
            ("trailing_stops_tightened_to_50pct_of_normal_width", OB.BLOCKED_UNREPRESENTABLE),
            ("micro_and_intraday_positions_reduced_by_twap", OB.BLOCKED_UNREPRESENTABLE),
        ],
        3: [
            ("no_new_entries", OB.ENFORCED_BY_ENTRY_REFUSAL),
            ("intraday_positions_exited_by_15min_twap", OB.BLOCKED_UNREPRESENTABLE),
            ("all_pending_orders_cancelled", OB.BLOCKED_UNREPRESENTABLE),
        ],
    }
    for changes, state in ((TWO_DATA_AT_100MS, 1), ({"data_statuses": data(5)}, 2), ({"latency_ns": 500 * MS}, 3)):
        item = reading(**changes)
        assert [(obligation.rule, obligation.status) for obligation in item.obligations] == expected[state]
        assert {obligation.state_id for obligation in item.obligations} == {f"SS-{state}"}
        assert all(obligation.reason for obligation in item.obligations)
    assert reading().obligations == ()
    halt = system_state._OBLIGATIONS[4]  # noqa: SLF001 - never reachable: KS-4 and SHS <= 0.15 are never proven
    assert [rule for rule, status, _ in halt if status is OB.BLOCKED_UNREPRESENTABLE] == [
        "all_positions_flattened_by_market_orders",
        "all_orders_cancelled",
        "all_engines_disabled_until_a_manual_restart",
    ]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"kill_switch_level": 4}, "inputs_malformed:kill_switch_level"),
        ({"kill_switch_level": True}, "inputs_malformed:kill_switch_level"),
        ({"kill_switch_level": -1}, "inputs_malformed:kill_switch_level"),
        ({"drawdown_beyond_15pct_proven": True}, "inputs_malformed:drawdown_beyond_15pct_without_beyond_10pct"),
        ({"drawdown_beyond_10pct_proven": 1}, "inputs_malformed:drawdown_beyond_10pct_proven"),
        ({"data_statuses": data(0)[:4]}, "inputs_malformed:data_statuses"),
        ({"data_statuses": data(0)[::-1]}, "inputs_malformed:data_statuses"),
        ({"data_statuses": (("NT-D01", "ACTIVE"), *data(0)[1:])}, "inputs_malformed:data_statuses"),
        ({"execution_statuses": list(execution(0))}, "inputs_malformed:execution_statuses"),
        ({"latency_ns": -1}, "inputs_malformed:latency_ns"),
        ({"latency_budget_ns": 0}, "inputs_malformed:latency_budget_ns"),
        ({"single_instrument_portfolio": 1}, "inputs_malformed:single_instrument_portfolio"),
        ({"decision_time_ns": -1}, "inputs_malformed:decision_time_ns"),
    ],
)
def test_malformed_system_state_inputs_are_refused(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(GovernedPaperSystemStateError, match=f"^governed_paper_system_state:{reason}$"):
        reading(**changes)


def test_the_evidence_binds_every_reading_in_decision_order() -> None:
    first, second = reading(), reading(decision_sequence=9, decision_time_ns=est.T + HOUR, kill_switch_level=1)
    evidence = build_governed_paper_system_state_evidence(instrument=lifet.INS, readings=(first, second))
    assert evidence.evidence_digest == governed_paper_system_state_evidence_digest(evidence)
    assert (evidence.rule_id, evidence.rule_digest, evidence.readings) == (
        GOVERNED_PAPER_SYSTEM_STATE_RULE_ID,
        GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST,
        (first, second),
    )
    assert {name: getattr(evidence, name) for name, _ in GOVERNED_PAPER_SYSTEM_STATE_NON_CLAIM_FLAGS} == dict(
        GOVERNED_PAPER_SYSTEM_STATE_NON_CLAIM_FLAGS
    )
    for readings in ((second, first), (first, first), (replace(first, state_lower_bound=1),), (object(),)):
        with pytest.raises(GovernedPaperSystemStateError):
            build_governed_paper_system_state_evidence(instrument=lifet.INS, readings=readings)  # type: ignore[arg-type]
    with pytest.raises(GovernedPaperSystemStateError, match="instrument_malformed$"):
        build_governed_paper_system_state_evidence(instrument="", readings=())


def test_the_module_is_pure_exact_and_offline_and_reads_no_nav_wallet_or_margin() -> None:
    source_text = Path(system_state.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source_text)):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in pit.FORBIDDEN_MODULES for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] not in pit.FORBIDDEN_MODULES and node.module != "decimal"
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in pit.FORBIDDEN_CALLS, name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
    # S9 has no reading: the derivation takes no NAV, equity, wallet or margin input at all (B1: no NAV for a wallet)
    parameters = inspect.signature(derive_governed_paper_system_state_reading).parameters
    assert not any(token in name for name in parameters for token in ("nav", "equity", "wallet", "margin"))


# --- D. rule set v7 in the gate -------------------------------------------------------------------------------------------


def v7(states: dict[str, object] | None = None, kill_switch: object = None, **observation: object):  # noqa: ANN201
    """A SYNTHETIC rule set v7 observation on top of the rule set v6 facts (decision 7, SHORT at ``est.T``)."""

    return est.measured(
        kill_switch=kst.ks() if kill_switch is None else kill_switch,
        regime=rst.regime_facts(states),  # type: ignore[arg-type]
        system_safety=True,
        **observation,
    )


def decided(**changes: object):  # noqa: ANN201
    return evaluate_governed_paper_entry_safety(v7(**changes))


def outcome(decision: object, name: str) -> tuple[GovernedPaperEntrySafetyStatus, str, str]:
    check = est.check_of(decision, name)
    return check.status, check.observed, check.reason


def lost_data(**changes: object):  # noqa: ANN201
    """Every NT-D condition proven active at ``est.T``: a 61 s trade gap, an 11 s old book that also diverges 10 s from
    the latest trade, an index 25% below the trade and a zero 5-minute volume."""

    return v7(
        market_data=est.market_facts(trade_gap_ns=61 * SECOND, index_price=est.d(30), volume_target=est.d(0)),
        book_update_event_time_ns=est.T - 11 * SECOND,
        **changes,
    )


def test_rule_set_v7_adds_only_its_rule_and_three_checks_and_v1_to_v6_keep_their_identities() -> None:
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST,
    ) == (
        est.ACCEPTED_MAIN_RULE_SET_V1_DIGEST,
        est.ACCEPTED_MAIN_RULE_SET_V2_DIGEST,
        est.RULE_SET_V3_DIGEST,
        est.RULE_SET_V4_DIGEST,
        rst.ACCEPTED_MAIN_RULE_SET_V5_DIGEST,
        ACCEPTED_MAIN_RULE_SET_V6_DIGEST,
    )
    v7_rules, v6_rules = GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET, GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET
    added = ("rule_set_id", "contract_id", "checks", "system_safety_rule")
    assert {key: value for key, value in v7_rules.items() if key not in added} == {
        key: value for key, value in v6_rules.items() if key not in added
    }
    assert v7_rules["checks"][: len(v6_rules["checks"])] == v6_rules["checks"]  # type: ignore[index, arg-type]
    assert [item["check_id"] for item in v7_rules["checks"][len(v6_rules["checks"]) :]] == list(V7_ADDED)  # type: ignore[index, arg-type]
    assert (v7_rules["rule_set_id"], v7_rules["contract_id"]) == (
        GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_ID,
        "S1_INTEGRATED_RISK_AND_SYSTEM_SAFETY_CLOSURE_V1",
    )
    rule = v7_rules["system_safety_rule"]
    assert (rule["implemented_items"], rule["unread_items"], rule["excluded_items"]) == (  # type: ignore[index]
        ["CL2-7", "CL2-9", "CL2-10", "CL2-11"],
        ["CL2-8"],
        ["CL1-14", "CL2-12", "CL2-13"],
    )
    assert (rule["system_state_rule_id"], rule["system_state_rule_digest"]) == (  # type: ignore[index]
        GOVERNED_PAPER_SYSTEM_STATE_RULE_ID,
        GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST,
    )
    assert {name: rule[name] for name in ("single_position_cap", "total_exposure_cap", "initial_stop_fraction")} == {  # type: ignore[index]
        "single_position_cap": est.d("0.08"),
        "total_exposure_cap": est.d("0.4"),
        "initial_stop_fraction": est.d("0.015"),
    }
    assert (rule["concurrent_positions_cap"], rule["turnover_trades_per_day_cap"]) == (8, 20)  # type: ignore[index]
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST
        == edge_sha256_text(edge_canonical_json(v7_rules))
        == governed_paper_entry_safety_rule_set_digest(
            protective=True, portfolio=True, market_data=True, kill_switch=True, regime=True, system_safety=True
        )
    )
    with pytest.raises(GovernedPaperEntrySafetyError, match="system_safety_rule_set_needs_the_regime_rule_set$"):
        governed_paper_entry_safety_rule_set(
            protective=True, portfolio=True, market_data=True, kill_switch=True, system_safety=True
        )


def test_without_the_flag_every_check_keeps_its_rule_set_v6_outcome_and_the_first_refusal_never_moves() -> None:
    current = decided()
    legacy = evaluate_governed_paper_entry_safety(replace(v7(), system_safety=False))
    assert (len(legacy.checks), len(current.checks)) == (36, 39)
    assert [item.check_id for item in current.checks][-3:] == list(V7_ADDED)
    assert [item for item in current.checks if item.check_id not in ("SYSTEM-STATE", *V7_ADDED)] == [
        item for item in legacy.checks if item.check_id != "SYSTEM-STATE"
    ]
    # under rule set v6 SYSTEM-STATE stays exactly its regime reading
    assert outcome(legacy, "SYSTEM-STATE") == (BLOCKED, "seen-system-state", est.code("SYSTEM-STATE:why_system-state"))
    # no admission change: after the measured Data PASS the first refusal is still NT-R01
    assert (current.entry_permitted, current.first_failure_check_id) == (False, "NT-R01")
    cases = (
        v7(initial_stop_represented=True),
        v7(latency_ns=500 * MS),
        v7(kill_switch=kst.ks(1)),
        v7(candidate_position_quantity=est.d(-20), candidate_nav=est.d(Fraction(10_000) - UNIT)),
        lost_data(),
    )
    for observation in cases:
        new = evaluate_governed_paper_entry_safety(observation)
        old = evaluate_governed_paper_entry_safety(replace(observation, system_safety=False))
        assert (new.entry_permitted, new.first_failure_check_id, new.first_failure_reason) == (
            old.entry_permitted,
            old.first_failure_check_id,
            old.first_failure_reason,
        )
        assert new.entry_permitted is False
        assert all(est.check_of(new, name).status is not S.PASS for name in ("SYSTEM-STATE", "HZ-LIMITS", "SCALE-1"))


def test_system_state_fails_on_a_proven_state_above_ss0_and_is_otherwise_blocked() -> None:
    decision = decided()
    derived = governed_paper_entry_safety_system_state_reading(v7())
    assert outcome(decision, "SYSTEM-STATE") == (
        BLOCKED,
        "lower_bound=SS-0;shs_upper_bound=0.995000000000000000",
        est.code("SYSTEM-STATE:ss0_unprovable_signals_s3_s6_s7_s9_have_no_reading_and_no_signal_has_an_upper_bound"),
    )
    assert est.check_of(decision, "SYSTEM-STATE").evidence_record_digests == (derived.reading_digest,)
    assert derived == reading()  # the gate's derivation reads exactly the observation's own facts
    # exactly five times the T1 budget: NT-X01 passes (strictly above only), S10 reaches 1 and overrides to CRISIS
    crisis = decided(latency_ns=500 * MS)
    assert est.check_of(crisis, "NT-X01").status is S.PASS
    assert outcome(crisis, "SYSTEM-STATE") == (
        S.FAIL,
        "lower_bound=SS-3;shs_upper_bound=0.950000000000000000",
        est.code(
            "SYSTEM-STATE:system_state_at_least_ss-3_proven_by_critical_override_s10_severity_1_family_b_t1_needs_ss0"
        ),
    )
    # a proven drawdown beyond 15% (with its trigger 2) at an absorbed KS-3
    proven = tuple(name for name in kst.ALL_UNPROVEN if name not in ("T2", "T11"))
    deep = decided(kill_switch=kst.ks(3, proving_trigger_ids=("T11",), unproven_trigger_ids=proven))
    assert outcome(deep, "SYSTEM-STATE")[0::2] == (
        S.FAIL,
        est.code(
            "SYSTEM-STATE:system_state_at_least_ss-3_proven_by_critical_override_s2_severity_1_family_b_t1_needs_ss0"
        ),
    )
    # complete data loss: the DEFENSIVE minimum
    lost = evaluate_governed_paper_entry_safety(lost_data())
    assert [est.check_of(lost, name).status for name in DATA_IDS] == [S.FAIL] * 5
    assert outcome(lost, "SYSTEM-STATE")[0:2] == (S.FAIL, "lower_bound=SS-2;shs_upper_bound=0.895000000000000000")
    other = decided(family_b_applicable=False)
    assert outcome(other, "SYSTEM-STATE") == (
        BLOCKED,
        "",
        est.code("SYSTEM-STATE:family_b_applicability_undetermined"),
    )


def test_hz_stop_passes_only_when_a_policy_v2_represents_the_initial_stop() -> None:
    assert outcome(decided(), "HZ-STOP") == (
        UNREPRESENTABLE,
        "",
        est.code("HZ-STOP:intraday_initial_stop_not_represented_by_the_position_management_policy"),
    )
    represented = decided(initial_stop_represented=True)
    assert outcome(represented, "HZ-STOP") == (
        S.PASS,
        "0.015000000000000000",
        est.code("HZ-STOP:nearer_of_the_1_5pct_initial_stop_and_the_atr_4h_stop_enforced_by_the_engine"),
    )
    assert est.check_of(represented, "HZ-STOP").evidence_record_digests == (est.AUTHORITY, est.ATR_WINDOW)
    uncovered = decided(initial_stop_represented=True, protective_window_covers=False)
    assert outcome(uncovered, "HZ-STOP") == (
        UNREPRESENTABLE,
        "",
        est.code("HZ-STOP:protective_authority_does_not_cover_the_holding_horizon"),
    )
    no_atr = decided(
        initial_stop_represented=True,
        atr_available=False,
        atr_value=None,
        atr_window_digest=None,
        atr_reason="atr_bar_stale",
    )
    assert outcome(no_atr, "HZ-STOP") == (BLOCKED, "", est.code("HZ-STOP:atr_4h_unavailable:atr_bar_stale"))
    assert (represented.entry_permitted, represented.first_failure_check_id) == (False, "NT-R01")


def held(quantity: int, **changes: object):  # noqa: ANN201
    """``v7`` holding ``quantity`` units at the fresh mark 40, a decision that is no entry (no candidate NAV)."""

    return v7(
        position_quantity=est.d(quantity),
        candidate_position_quantity=est.d(quantity),
        candidate_nav=None,
        **changes,
    )


def test_hz_limits_fails_strictly_above_the_intraday_8pct_and_never_passes() -> None:
    assert outcome(decided(), "HZ-LIMITS") == (
        BLOCKED,
        render(Fraction(40) / Fraction("9999.98")),
        est.code("HZ-LIMITS:intraday_turnover_of_20_trades_per_day_has_no_defined_reading"),
    )
    exact = decided(candidate_position_quantity=est.d(-20), candidate_nav=est.d(10_000))  # 20 x 40 / 10000 = 8%
    assert outcome(exact, "HZ-LIMITS")[0:2] == (BLOCKED, est.d("0.08"))
    beyond = decided(candidate_position_quantity=est.d(-20), candidate_nav=est.d(Fraction(10_000) - UNIT))
    assert outcome(beyond, "HZ-LIMITS")[0::2] == (
        S.FAIL,
        est.code("HZ-LIMITS:candidate_position_above_the_intraday_8pct_of_nav"),
    )
    assert est.check_of(beyond, "NT-R04").status is S.PASS  # the stricter INTRADAY limit binds before NT-R04's 25%
    position = evaluate_governed_paper_entry_safety(held(-21))  # 21 x 40 / 10000 = 8.4%
    assert outcome(position, "HZ-LIMITS") == (
        S.FAIL,
        est.d("0.084"),
        est.code("HZ-LIMITS:single_position_above_the_intraday_8pct_of_nav"),
    )
    assert est.check_of(position, "NT-R04").status is S.PASS
    assert outcome(evaluate_governed_paper_entry_safety(held(-20)), "HZ-LIMITS")[0:2] == (BLOCKED, est.d("0.08"))
    # the turnover reading is undefined, so no size ever passes
    for quantity in range(0, 26):
        candidate = {"candidate_nav": None} if quantity == 0 else {"candidate_nav": est.d(10_000)}
        status = outcome(decided(candidate_position_quantity=est.d(-quantity), **candidate), "HZ-LIMITS")[0]
        assert status in (BLOCKED, S.FAIL)


def test_scale_1_fails_on_a_proven_reduced_allocation_and_never_passes() -> None:
    derived = governed_paper_entry_safety_system_state_reading(v7())
    base = decided()
    assert outcome(base, "SCALE-1") == (
        BLOCKED,
        "",
        est.code(
            "SCALE-1:allocation_multipliers_unproven_edge_health_meta_layer_crowding_capacity_regime_dimensions_"
            "margin_and_kelly"
        ),
    )
    assert est.check_of(base, "SCALE-1").evidence_record_digests == (kst.LADDER, derived.reading_digest)
    assert outcome(decided(kill_switch=kst.ks(1)), "SCALE-1") == (
        S.FAIL,
        "1",
        est.code("SCALE-1:kill_switch_lower_bound_ks_1_allocation_multiplier_below_1"),
    )
    assert outcome(decided(latency_ns=200 * MS), "SCALE-1")[0] is BLOCKED  # exactly twice the budget halves nothing
    assert outcome(decided(latency_ns=200 * MS + 1), "SCALE-1") == (
        S.FAIL,
        str(200 * MS + 1),
        est.code("SCALE-1:latency_above_2x_the_tier_budget_halves_the_position_size"),
    )
    # KS-0 and an unhalved latency, yet a proven DEFENSIVE state: complete data loss
    assert outcome(evaluate_governed_paper_entry_safety(lost_data()), "SCALE-1") == (
        S.FAIL,
        "SS-2",
        est.code("SCALE-1:system_state_at_least_ss-2_reduces_the_allocation"),
    )


@pytest.mark.parametrize(
    ("build", "name"),
    [
        (lambda: est.measured(kill_switch=kst.ks(), system_safety=True), "system_safety_without_the_regime_facts"),
        (lambda: replace(v7(), system_safety=1), "system_safety"),
        (lambda: v7(initial_stop_represented=1), "initial_stop_represented"),
        (lambda: est.observation(initial_stop_represented=True), "protective_facts_without_a_protective_context"),
        (
            lambda: v7(
                kill_switch=kst.ks(
                    1,
                    proving_trigger_ids=("T11",),
                    unproven_trigger_ids=tuple(x for x in kst.ALL_UNPROVEN if x != "T11"),
                )
            ),
            "kill_switch_drawdown_proofs_inconsistent",
        ),
    ],
)
def test_malformed_system_safety_facts_are_refused(build: object, name: str) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{est.code(f'observation_malformed:{name}')}$"):
        evaluate_governed_paper_entry_safety(build())  # type: ignore[operator]


def test_a_legacy_evidence_never_carries_a_system_state_evidence() -> None:
    legacy = rst.regime_day_3_gate()  # rule set v6, rebuilt through the public builders
    assert "system_state_evidence" not in governed_paper_entry_safety_evidence_to_dict(legacy)
    stray = build_governed_paper_system_state_evidence(instrument=legacy.instrument, readings=())
    with pytest.raises(ValueError, match="legacy_rule_set_carries_a_system_state_evidence$"):
        governed_paper_entry_safety_evidence_to_dict(replace(legacy, system_state_evidence=stray))


# --- E. world G's integrated lineage (seal v8, evidence v8) -----------------------------------------------------------------


@functools.cache
def pm_v2_g():  # noqa: ANN201
    """SYNTHETIC policy v2 with exactly the governed inputs of world G's v1 protective policy."""

    return build_historical_position_management_policy_v2(
        policy_id="pm-policy-g",
        policy_version="synthetic-v1",
        instrument=gpe.INS,
        atr_bar_price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        atr_max_bar_age_ns=8 * HOUR,
        stop_tightening_method_id=TIGHTENING_NOT_APPLIED_PENDING_DEC9,
    )


@functools.cache
def v2_authority():  # noqa: ANN201
    """World G's protective authority (DEC-1) over the policy v2, approved exactly as the v1 one."""

    inputs = prot.authority_inputs(gpe.scenario("G"), position_management_policy=pm_v2_g())
    return inputs, build_governed_paper_protective_authority(inputs)


def safety_day(days: tuple, context: object, policy: str = "v1"):  # noqa: ANN201
    """Open, run and seal the day after ``days`` of world G on the integrated lineage with the regime ``context``."""

    world = gpe.scenario("G")
    day = len(days)
    prior = days[-1].seal if days else None
    cycle_inputs = gpe.cycle_inputs_for(day, prior, world=world)
    cycle = build_governed_paper_cycle_authority(cycle_inputs)
    protection = replace(
        lineage.protection_for(
            day,
            days,
            authority=None if policy == "v1" else v2_authority(),
            portfolio_no_trade=True,
            market_data_integrity=True,
            kill_switch_escalation=True,
        ),
        regime=context,
        system_safety=True,
    )
    seal_inputs = gpe.seal_inputs_for(
        day, cycle_inputs, cycle, prior, gpe.pending_of(days), world=world, protection=protection
    )
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def safety_days(count: int, policy: str = "v1") -> tuple:
    """World G's first ``count`` days of the integrated lineage (seal v8) under the TEST-ONLY regime table."""

    if count == 0:
        return ()
    days = safety_days(count - 1, policy)
    return (*days, safety_day(days, rst.regime_context(len(days)), policy))


@functools.cache
def public_gate(day: int):  # noqa: ANN201
    """Day ``day``'s decision run and rule set v7 evaluation, rebuilt independently through the public builders."""

    item = safety_days(5)[day]
    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        evidence = build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(economics, item.seal.schedule),  # type: ignore[attr-defined]
            market_data=True,
            kill_switch=True,
            regime=rst.regime_context(day),
            system_safety=True,
        )
    return run, evidence


# World G's sealed day-3 entry under rule set v7: its NT-D readings are BLOCKED (no trade or index series in its genesis
# data contract), so no data condition is proven active; its kill-switch bound is KS-0 and its latency unhalved; its v1
# policy does not represent the initial stop.
WORLD_G_DAY_3 = {
    "SYSTEM-STATE": (
        BLOCKED,
        est.code("SYSTEM-STATE:ss0_unprovable_signals_s3_s6_s7_s9_have_no_reading_and_no_signal_has_an_upper_bound"),
    ),
    "HZ-STOP": (
        UNREPRESENTABLE,
        est.code("HZ-STOP:intraday_initial_stop_not_represented_by_the_position_management_policy"),
    ),
    "HZ-LIMITS": (BLOCKED, est.code("HZ-LIMITS:intraday_turnover_of_20_trades_per_day_has_no_defined_reading")),
    "SCALE-1": (
        BLOCKED,
        est.code(
            "SCALE-1:allocation_multipliers_unproven_edge_health_meta_layer_crowding_capacity_regime_dimensions_"
            "margin_and_kelly"
        ),
    ),
}
UNCHANGED = (
    "schedule",
    "economics_result_digest",
    "governed_outcome_digest",
    "episodes",
    "funding_events",
    "sealed_history_digest",
    "prefix_digest_open",
    "prefix_digest_close",
    "kill_switch_ladder_digest",
    "kill_switch_prefix_digest_open",
    "kill_switch_prefix_digest_close",
    *rst.V7_FIELDS,
)


def test_world_g_integrated_lineage_changes_only_its_version_rule_set_and_bound_system_state() -> None:
    days, legacy = safety_days(4), rst.regime_days(4)
    for item, old in zip(days, legacy, strict=True):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V8, GovernedPaperDaySealStatus.SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST
        for name in UNCHANGED:
            assert getattr(seal, name) == getattr(old.seal, name), name
        assert len(seal.system_state_evidence_digest) == 64
        verification = rst.verify(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    (entry,) = days[3].seal.entry_safety_decisions
    (old_entry,) = legacy[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")  # unchanged: no new admission
    assert [check for check in entry.checks if check.check_id not in ("SYSTEM-STATE", *V7_ADDED)] == [
        check for check in old_entry.checks if check.check_id != "SYSTEM-STATE"
    ]
    statuses = {check.check_id: (check.status, check.reason) for check in entry.checks}
    assert {name: statuses[name] for name in ("SYSTEM-STATE", *V7_ADDED)} == WORLD_G_DAY_3
    lineage_evidence = rst.regime_lineage_evidence(days)
    assert (lineage_evidence.schema_version, lineage_evidence.status) == (
        "governed-paper-execution-evidence.v8",
        GovernedPaperExecutionStatus.READY,
    )
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        verification = verify_governed_paper_execution_evidence(lineage_evidence, gpe.evidence_inputs(days))
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert "system_state_evidence_digest" in governed_paper_day_seal_to_dict(days[3].seal)


def test_an_audit_replay_reproduces_every_sealed_system_state_and_no_later_seal_revises_a_reading() -> None:
    days = safety_days(5)
    readings: list[dict[int, object]] = []
    for day in (3, 4):  # two UTC days of the lineage: day 4's evaluation re-derives day 3's entry
        item = days[day]
        run, evidence = public_gate(day)
        assert (evidence.rule_set_id, evidence.evidence_digest) == (
            GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_ID,
            item.seal.entry_safety_evidence_digest,
        )
        system = evidence.system_state_evidence
        assert system is not None and system.evidence_digest == item.seal.system_state_evidence_digest
        assert {reading_.decision_sequence for reading_ in system.readings} == set(
            governed_paper_entry_safety_entry_sequences(run)
        )  # entries only: an exit or a protective close-only action is never read
        for decision in evidence.decisions:
            derived = next(r for r in system.readings if r.decision_sequence == decision.decision_sequence)
            assert est.check_of(decision, "SYSTEM-STATE").evidence_record_digests == (derived.reading_digest,)
        readings.append({reading_.decision_sequence: reading_ for reading_ in system.readings})
    earlier, later = readings
    assert earlier and all(later[sequence] == item for sequence, item in earlier.items())


def test_an_integrated_lineage_is_one_from_day_0_or_never_and_only_on_a_regime_lineage() -> None:
    days, legacy = safety_days(2), rst.regime_days(2)
    for item, changes, reason in (
        (days[1], {"system_safety": False}, "system_safety_gate_lineage_switched"),
        (legacy[1], {"system_safety": True}, "system_safety_gate_lineage_switched"),
        (days[0], {"regime": None}, "system_safety_gate_needs_the_regime_lineage"),
        (days[1], {"system_safety": 1}, "protection_inputs_malformed:system_safety"),
    ):
        with rst.approval_table(rst.TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    # a relabelled version never verifies: a v8 seal cannot hide behind a v7 payload, a v7 seal labelled v8 never rebuilds
    assert rst.verify(replace(days[1].seal, schema_version=V7), days[1].seal_inputs).intact is False
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:system_state_evidence_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V7)
    for forged in (replace(legacy[1].seal, schema_version=V8), gpe.reseal_seal(legacy[1].seal, schema_version=V8)):
        assert rst.verify(forged, legacy[1].seal_inputs).intact is False
    forged_digest = gpe.reseal_seal(days[1].seal, system_state_evidence_digest="0" * 64)
    assert rst.verify(forged_digest, days[1].seal_inputs).intact is False


def test_a_policy_v2_lineage_passes_hz_stop_and_admits_nothing() -> None:
    days, v1_days = safety_days(4, "v2"), safety_days(4)
    authority = v2_authority()[1]
    assert authority.position_management_policy_digest == pm_v2_g().policy_digest
    for item, old in zip(days, v1_days, strict=True):
        seal, schedule = item.seal, item.seal.schedule
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V8, GovernedPaperDaySealStatus.SEALED, ())
        # the same refusals and no fill at all: only the authority (so the run-derived identities) differ
        assert schedule.entry_refused_decision_sequences == old.seal.schedule.entry_refused_decision_sequences
        assert [(window.window_start_ns, window.window_end_ns) for window in schedule.protective_windows] == [
            (window.window_start_ns, window.window_end_ns) for window in old.seal.schedule.protective_windows
        ]
        for name in (
            "episodes",
            "funding_events",
            "sealed_history_digest",
            "kill_switch_prefix_digest_close",
            "regime_evidence_digest",
        ):
            assert getattr(seal, name) == getattr(old.seal, name), name
        assert seal.protective_authority_digest == authority.authority_digest != old.seal.protective_authority_digest
        verification = rst.verify(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    (entry,) = days[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    assert (est.check_of(entry, "HZ-STOP").status, est.check_of(entry, "HZ-STOP").reason) == (
        S.PASS,
        est.code("HZ-STOP:nearer_of_the_1_5pct_initial_stop_and_the_atr_4h_stop_enforced_by_the_engine"),
    )
    (old_entry,) = v1_days[3].seal.entry_safety_decisions

    def summary(decision: object) -> list[tuple[str, GovernedPaperEntrySafetyStatus, str, str]]:
        return [(item.check_id, item.status, item.observed, item.reason) for item in decision.checks]  # type: ignore[attr-defined]

    assert [row for row in summary(entry) if row[0] != "HZ-STOP"] == [
        row for row in summary(old_entry) if row[0] != "HZ-STOP"
    ]


# --- F. legacy byte identity -----------------------------------------------------------------------------------------------


def test_world_g_regime_lineage_is_byte_identical_to_accepted_main() -> None:
    days = rst.regime_days(4)
    assert GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V6_DIGEST
    assert tuple(item.seal.schema_version for item in days) == (V7,) * 4
    assert tuple(item.seal.seal_digest for item in days) == ACCEPTED_MAIN_V7_SEALS
    assert tuple(item.seal.entry_safety_evidence_digest for item in days) == ACCEPTED_MAIN_V7_ENTRY_EVIDENCE
    assert tuple(item.seal.regime_evidence_digest for item in days) == ACCEPTED_MAIN_V7_REGIME_EVIDENCE
    assert tuple(item.seal.regime_prefix_digest_close for item in days) == ACCEPTED_MAIN_V7_REGIME_PREFIX_CLOSE
    assert all(item.seal.system_state_evidence_digest == "" for item in days)
    assert "system_state_evidence_digest" not in governed_paper_day_seal_to_dict(days[3].seal)
    assert rst.regime_lineage_evidence(days).evidence_digest == ACCEPTED_MAIN_V7_LINEAGE_EVIDENCE
