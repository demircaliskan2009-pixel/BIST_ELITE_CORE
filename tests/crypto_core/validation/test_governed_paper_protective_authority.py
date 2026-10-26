"""Governed paper protective close-only authority tests (PROTECTIVE_POSITION_LIFECYCLE_V1, DEC-1).

SYNTHETIC TEST VALUES ONLY. Every bar, policy value, validity window and approval here is a synthetic fixture that
exercises structure. No ``HUMAN_GOVERNANCE`` record built here is a real human decision: they are synthetic PASS-branch
fixtures over world G's synthetic genesis, exactly like the genesis and cycle approvals of the lineage tests. Nothing
here grants C1-C9, approves DEC-9, qualifies a source or proves a venue fact.

The OHLC fixtures of world G: flat SYNTHETIC 4 h mark-price bars around 40 with a range of 0.4 (ATR_4h 0.4, stop
distance 0.6), from four days before the genesis instant G, each visible 1 s after its close.
"""

from __future__ import annotations

import functools
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_protective_authority as authority_module
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_sha256_text
from crypto_core.validation.governed_paper_execution_authority import GovernedPaperApprovalKind
from crypto_core.validation.governed_paper_protective_authority import (
    GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET,
    GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET_DIGEST,
    GovernedPaperProtectiveAuthority,
    GovernedPaperProtectiveAuthorityApproval,
    GovernedPaperProtectiveAuthorityError,
    GovernedPaperProtectiveAuthorityInputs,
    GovernedPaperProtectiveAuthorityStatus,
    build_governed_paper_protective_authority,
    build_governed_paper_protective_revocation,
    governed_paper_protective_authority_digest,
    governed_paper_protective_authority_to_dict,
    governed_paper_protective_context,
    governed_paper_protective_revocation_digest,
    governed_paper_protective_window,
    verify_governed_paper_protective_authority,
    verify_governed_paper_protective_revocation,
)
from crypto_core.validation.historical_execution_economics_policy import HistoricalExecutionApprovalKind
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    HistoricalOhlcSourceDeclaration,
    build_historical_ohlc_bar,
    build_historical_ohlc_bar_archive,
    historical_ohlc_source_declaration_digest,
)
from crypto_core.validation.historical_position_management_policy import (
    TIGHTENING_DEC9_READING_V1,
    TIGHTENING_NOT_APPLIED_PENDING_DEC9,
    HistoricalPositionManagementApproval,
    HistoricalPositionManagementPolicy,
    build_historical_position_management_policy,
)

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_historical_pit_dataset as pit
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "governed_paper_protective_authority"
HOUR = 3_600_000_000_000
H4 = 4 * HOUR
SECOND = 1_000_000_000
HUMAN = GovernedPaperApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC
VALID_UNTIL_DAY = 60  # SYNTHETIC protective validity: [G, E_60)


@pytest.fixture(autouse=True, scope="module")
def _exact_memos():
    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        yield


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


# --- the world G protective fixtures (shared with the lineage and gate tests) ---------------------------------------------


def ohlc_source(**changes: object) -> HistoricalOhlcSourceDeclaration:
    base = HistoricalOhlcSourceDeclaration(
        source_id="synthetic-ohlc-g",
        source_reference="archive:synthetic-ohlc-g",
        rights_status=SourcePacketRightsStatus.OWN_RESEARCH,
        rights_reference="license-1",
        instrument=gpe.INS,
        price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        bar_intervals_ns=(H4,),
    )
    return replace(base, **changes)


@functools.cache
def world_bar(k: int):  # noqa: ANN201
    """SYNTHETIC 4 h bar ``k`` of world G (bar 0 opens at G): open == close == 40, range 0.4, visible 1 s after."""

    opened = gpe.G + k * H4
    return build_historical_ohlc_bar(
        interval_ns=H4,
        open_time_ns=opened,
        open_price=gpe.d(40),
        high_price=gpe.d(Fraction("40.2")),
        low_price=gpe.d(Fraction("39.8")),
        close_price=gpe.d(40),
        available_at_ns=opened + H4 + SECOND,
        finalized_at_ns=opened + H4 + SECOND,
    )


FIRST_BAR = -24  # four days of bars before G


@functools.cache
def world_ohlc(day: int, *, source: HistoricalOhlcSourceDeclaration | None = None) -> HistoricalOhlcBarArchive:
    """World G's OHLC archive sealed at E_(day + 1): exactly the bars visible then."""

    end = gpe.instant(day + 1)
    bars = tuple(
        world_bar(k)
        for k in range(FIRST_BAR, 6 * (day + 1))
        if max(world_bar(k).available_at_ns, world_bar(k).finalized_at_ns) <= end
    )
    return build_historical_ohlc_bar_archive(
        archive_id=f"ohlc-g-{day}", source=ohlc_source() if source is None else source, bars=bars
    )


@functools.cache
def pm_policy(tightening: str = TIGHTENING_NOT_APPLIED_PENDING_DEC9, instrument: str = gpe.INS):  # noqa: ANN201
    return build_historical_position_management_policy(
        policy_id="pm-policy-g",
        policy_version="synthetic-v1",
        instrument=instrument,
        atr_bar_price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        atr_max_bar_age_ns=8 * HOUR,
        stop_tightening_method_id=tightening,
    )


def pm_approval(
    policy: HistoricalPositionManagementPolicy, genesis: object, **changes: object
) -> HistoricalPositionManagementApproval:
    """SYNTHETIC: the exact commitments a human reviews before adopting one position-management policy."""

    values: dict[str, object] = {
        "approval_reference": "synthetic-pm-adoption-1",
        "approval_digest": "f" * 64,
        "approval_kind": HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE,
        "approved_policy_digest": policy.policy_digest,
        "approved_rule_set_digest": policy.rule_set_digest,
        "approved_instrument": gpe.INS,
        "approved_strategy_spec_digest": genesis.strategy_spec_digest,  # type: ignore[attr-defined]
        "approved_ohlc_source_digest": historical_ohlc_source_declaration_digest(ohlc_source()),
    }
    values.update(changes)
    return HistoricalPositionManagementApproval(**values)  # type: ignore[arg-type]


def authority_approval_for(
    inputs: GovernedPaperProtectiveAuthorityInputs, *, kind: object = HUMAN, **changes: object
) -> GovernedPaperProtectiveAuthorityApproval:
    """SYNTHETIC: the exact commitments a human reviews before granting one protective authority (DEC-1)."""

    draft = build_governed_paper_protective_authority(replace(inputs, approval=None))
    values: dict[str, object] = {
        "approval_reference": "synthetic-protective-authority-1",
        "approval_digest": "a" * 64,
        "approval_kind": kind,
        "approved_authority_id": draft.authority_id,
        "approved_authority_policy_digest": draft.authority_policy_digest,
        "approved_rule_set_digest": draft.rule_set_digest,
    }
    values.update(changes)
    return GovernedPaperProtectiveAuthorityApproval(**values)  # type: ignore[arg-type]


def authority_inputs(world: object | None = None, **changes: object) -> GovernedPaperProtectiveAuthorityInputs:
    """The protective authority inputs of ``world`` (default world G), approved unless ``approval`` is given."""

    world = gpe.scenario("G") if world is None else world
    policy = changes.pop("position_management_policy", pm_policy())
    values: dict[str, object] = {
        "authority_id": f"gpe-protective-{world.name}",  # type: ignore[attr-defined]
        "correlation_id": "corr-gpe-protective",
        "genesis_inputs": world.genesis_inputs,  # type: ignore[attr-defined]
        "genesis": world.genesis,  # type: ignore[attr-defined]
        "position_management_policy": policy,
        "position_management_approval": pm_approval(policy, world.genesis),  # type: ignore[attr-defined]
        "ohlc_source": ohlc_source(),
        "valid_from_ns": gpe.G,
        "valid_until_ns": gpe.instant(VALID_UNTIL_DAY),
        "approval": None,
    }
    approve = "approval" not in changes
    values.update(changes)
    inputs = GovernedPaperProtectiveAuthorityInputs(**values)  # type: ignore[arg-type]
    return replace(inputs, approval=authority_approval_for(inputs)) if approve else inputs


@functools.cache
def world_authority(name: str = "G") -> tuple[GovernedPaperProtectiveAuthorityInputs, GovernedPaperProtectiveAuthority]:
    inputs = authority_inputs(gpe.scenario(name))
    return inputs, build_governed_paper_protective_authority(inputs)


def revocation(authority: GovernedPaperProtectiveAuthority, effective_at_ns: int, **changes: object):  # noqa: ANN201
    values: dict[str, object] = {
        "revocation_id": f"synthetic-revocation-{effective_at_ns}",
        "authority_digest": authority.authority_digest,
        "effective_at_ns": effective_at_ns,
        "approval_reference": "synthetic-protective-revocation-1",
        "approval_digest": "b" * 64,
        "approval_kind": HUMAN,
    }
    values.update(changes)
    return build_governed_paper_protective_revocation(**values)  # type: ignore[arg-type]


def reseal(authority: GovernedPaperProtectiveAuthority, **changes: object) -> GovernedPaperProtectiveAuthority:
    changed = replace(authority, **changes)
    return replace(changed, authority_digest=governed_paper_protective_authority_digest(changed))


# --- A. the authority ---------------------------------------------------------------------------------------------------


def test_an_exact_human_governed_authority_is_authorized_close_only_and_bound_to_its_genesis() -> None:
    inputs, authority = world_authority()
    _, genesis = gpe.world_genesis()
    assert (authority.status, authority.authorized, authority.reason_codes) == (
        GovernedPaperProtectiveAuthorityStatus.AUTHORIZED,
        True,
        (),
    )
    assert (authority.genesis_digest, authority.instrument, authority.strategy_spec_digest) == (
        genesis.genesis_digest,
        genesis.instrument,
        genesis.strategy_spec_digest,
    )
    assert authority.position_management_policy_digest == pm_policy().policy_digest
    assert authority.ohlc_source_digest == historical_ohlc_source_declaration_digest(ohlc_source())
    assert (authority.valid_from_ns, authority.valid_until_ns) == (gpe.G, gpe.instant(VALID_UNTIL_DAY))
    assert authority.stop_tightening_method_id == TIGHTENING_NOT_APPLIED_PENDING_DEC9
    assert (authority.close_only, authority.paper_only, authority.execution_authorized, authority.live_ready) == (
        True,
        True,
        False,
        False,
    )
    assert authority.synthetic_test_approval_used is False
    assert authority.authority_digest == governed_paper_protective_authority_digest(authority)
    verification = verify_governed_paper_protective_authority(authority, inputs)
    assert verification.intact and verification.recomputed_digest == authority.authority_digest


def test_the_rule_set_names_what_dec1_bypasses_what_it_never_does_and_what_it_keeps() -> None:
    rule_set = GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET
    assert GOVERNED_PAPER_PROTECTIVE_AUTHORITY_RULE_SET_DIGEST == edge_sha256_text(edge_canonical_json(rule_set))
    assert set(rule_set["bypasses"]) == {  # type: ignore[arg-type]
        "cycle_direction_ceiling",
        "cycle_window",
        "cycle_reservation_price_ceiling",
        "entry_safety_refusals",
        "lifecycle_invalidation_entry_ban",
    }
    assert {"open", "increase", "reverse", "real_order", "capital_mutation"} <= set(rule_set["never"])  # type: ignore[arg-type]
    assert {"engine_fill_model", "latency", "spread", "depth", "fees", "close_only_construction"} <= set(
        rule_set["kept"]  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"approval": None}, "authority_approval_missing"),
        ({"position_management_approval": None}, "position_management_approval_missing"),
    ],
)
def test_a_missing_approval_needs_governance(changes: dict[str, object], reason: str) -> None:
    authority = build_governed_paper_protective_authority(authority_inputs(**changes))
    assert authority.status is GovernedPaperProtectiveAuthorityStatus.NEEDS_GOVERNANCE_APPROVAL
    assert code(reason) in authority.reason_codes and authority.authorized is False


def test_a_synthetic_or_mismatched_approval_is_never_promoted_to_authority() -> None:
    inputs = authority_inputs()
    synthetic = build_governed_paper_protective_authority(
        replace(inputs, approval=authority_approval_for(inputs, kind=SYNTHETIC))
    )
    assert synthetic.status is GovernedPaperProtectiveAuthorityStatus.NEEDS_GOVERNANCE_APPROVAL
    assert synthetic.synthetic_test_approval_used is True
    assert code("authority_approval_not_human_governance") in synthetic.reason_codes
    for name in ("approved_authority_id", "approved_authority_policy_digest", "approved_rule_set_digest"):
        value = "other-authority" if name == "approved_authority_id" else "0" * 64
        changed = build_governed_paper_protective_authority(
            replace(inputs, approval=authority_approval_for(inputs, **{name: value}))
        )
        assert changed.reason_codes == (code(f"authority_approval_mismatch:{name}"),)
    _, genesis = gpe.world_genesis()
    pm_synthetic = build_governed_paper_protective_authority(
        authority_inputs(
            position_management_approval=pm_approval(
                pm_policy(), genesis, approval_kind=HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC
            )
        )
    )
    assert code("position_management_approval_not_human_governance") in pm_synthetic.reason_codes
    foreign = build_governed_paper_protective_authority(
        authority_inputs(
            position_management_approval=pm_approval(pm_policy(), genesis, approved_ohlc_source_digest="c" * 64)
        )
    )
    assert foreign.reason_codes == (code("position_management_approval_mismatch:approved_ohlc_source_digest"),)


def test_a_human_approved_dec9_reading_never_becomes_authorized() -> None:
    policy = pm_policy(TIGHTENING_DEC9_READING_V1)
    _, genesis = gpe.world_genesis()
    inputs = authority_inputs(position_management_policy=policy)
    assert inputs.position_management_approval.approved_policy_digest == policy.policy_digest  # type: ignore[union-attr]
    authority = build_governed_paper_protective_authority(inputs)
    assert authority.status is GovernedPaperProtectiveAuthorityStatus.NEEDS_GOVERNANCE_APPROVAL
    assert authority.reason_codes == (
        code(f"position_management_method_requires_human_approval:{TIGHTENING_DEC9_READING_V1}"),
    )
    assert genesis.strategy_spec_digest == authority.strategy_spec_digest
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("protective_authority_not_authorized")):
        governed_paper_protective_context(authority, inputs)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"ohlc_source": ohlc_source(instrument="ETH-USDT-PERP")}, "ohlc_source_instrument_mismatch"),
        ({"ohlc_source": ohlc_source(bar_intervals_ns=(HOUR,))}, "ohlc_source_lacks_the_atr_interval"),
        (
            {"ohlc_source": ohlc_source(price_semantics=HistoricalOhlcPriceSemantics.LAST_TRADE)},
            "ohlc_source_price_semantics_mismatch",
        ),
        ({"valid_from_ns": gpe.G - 1}, "protective_window_starts_before_the_genesis"),
        ({"valid_until_ns": gpe.G}, "protective_window_empty"),
    ],
)
def test_a_structural_shortfall_is_blocked(changes: dict[str, object], reason: str) -> None:
    authority = build_governed_paper_protective_authority(authority_inputs(**changes))
    assert authority.status is GovernedPaperProtectiveAuthorityStatus.BLOCKED
    assert code(reason) in authority.reason_codes
    assert governed_paper_protective_window(authority, revoked_from_ns=None) is None


def test_a_policy_of_another_instrument_is_blocked() -> None:
    policy = pm_policy(instrument="ETH-USDT-PERP")
    authority = build_governed_paper_protective_authority(authority_inputs(position_management_policy=policy))
    assert authority.status is GovernedPaperProtectiveAuthorityStatus.BLOCKED
    assert code("position_management_policy_instrument_mismatch") in authority.reason_codes


def test_malformed_or_tampered_inputs_are_never_represented() -> None:
    inputs = authority_inputs()
    forged_policy = replace(pm_policy(), atr_max_bar_age_ns=9 * HOUR)
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("position_management_policy_not_authentic")):
        build_governed_paper_protective_authority(replace(inputs, position_management_policy=forged_policy))
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("authority_inputs_malformed")):
        build_governed_paper_protective_authority(object())  # type: ignore[arg-type]
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("valid_until_ns_invalid")):
        build_governed_paper_protective_authority(replace(inputs, valid_until_ns=True))
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("authority_id_invalid")):
        build_governed_paper_protective_authority(replace(inputs, authority_id=" spaced"))
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("authority_approval_kind_malformed")):
        build_governed_paper_protective_authority(
            replace(inputs, approval=replace(inputs.approval, approval_kind="HUMAN_GOVERNANCE"))  # type: ignore[type-var]
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("status", GovernedPaperProtectiveAuthorityStatus.AUTHORIZED),
        ("valid_until_ns", 10**19),
        ("close_only", False),
        ("execution_authorized", True),
        ("stop_tightening_method_id", TIGHTENING_DEC9_READING_V1),
        ("synthetic_test_approval_used", True),
    ],
)
def test_a_resealed_substitution_never_verifies(name: str, value: object) -> None:
    inputs, authority = world_authority()
    if name == "status":  # promote a NEEDS_GOVERNANCE authority
        inputs = authority_inputs(approval=None)
        authority = build_governed_paper_protective_authority(inputs)
    forged = reseal(authority, **{name: value})
    assert not verify_governed_paper_protective_authority(forged, inputs).intact
    with pytest.raises(GovernedPaperProtectiveAuthorityError):
        governed_paper_protective_context(forged, inputs)


def test_the_verifier_is_total() -> None:
    inputs, authority = world_authority()
    for value in (None, "authority", object(), governed_paper_protective_authority_to_dict(authority)):
        assert not verify_governed_paper_protective_authority(value, inputs).intact
    assert not verify_governed_paper_protective_authority(authority, None).intact


def test_the_context_holds_canonical_reconstructions_of_an_authorized_authority() -> None:
    inputs, authority = world_authority()
    context = governed_paper_protective_context(authority, inputs)
    assert context.authority == authority
    assert context.position_management_policy == pm_policy()
    assert context.position_management_approval == inputs.position_management_approval
    assert context.ohlc_source == ohlc_source()


# --- B. the engine window and revocation ------------------------------------------------------------------------------


def test_the_window_ends_at_the_expiry_or_the_earliest_revocation() -> None:
    _, authority = world_authority()
    full = governed_paper_protective_window(authority, revoked_from_ns=None)
    assert (full.window_start_ns, full.window_end_ns, full.authority_digest) == (  # type: ignore[union-attr]
        gpe.G,
        gpe.instant(VALID_UNTIL_DAY),
        authority.authority_digest,
    )
    revoked = governed_paper_protective_window(authority, revoked_from_ns=gpe.instant(4))
    assert revoked.window_end_ns == gpe.instant(4)  # type: ignore[union-attr]
    later = governed_paper_protective_window(authority, revoked_from_ns=gpe.instant(VALID_UNTIL_DAY + 1))
    assert later == full  # a revocation after the expiry changes nothing
    assert governed_paper_protective_window(authority, revoked_from_ns=gpe.G) is None
    pending = build_governed_paper_protective_authority(authority_inputs(approval=None))
    assert governed_paper_protective_window(pending, revoked_from_ns=None) is None


def test_a_revocation_is_digest_bound_and_reverifies_totally() -> None:
    _, authority = world_authority()
    record = revocation(authority, gpe.instant(4) + 100)
    assert record.revocation_digest == governed_paper_protective_revocation_digest(record)
    assert verify_governed_paper_protective_revocation(record).intact
    forged = replace(record, effective_at_ns=gpe.instant(5))
    assert not verify_governed_paper_protective_revocation(forged).intact
    resealed = replace(forged, revocation_digest=governed_paper_protective_revocation_digest(forged))
    assert verify_governed_paper_protective_revocation(resealed).intact  # another revocation, never this one
    for value in (None, "revocation", object()):
        assert not verify_governed_paper_protective_revocation(value).intact
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("revocation_approval_kind_malformed")):
        revocation(authority, gpe.instant(4), approval_kind="HUMAN_GOVERNANCE")
    with pytest.raises(GovernedPaperProtectiveAuthorityError, match=code("revocation_effective_at_ns_invalid")):
        revocation(authority, -1)


def test_the_module_is_pure_and_offline() -> None:
    pit.assert_module_is_pure(
        authority_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.governed_paper_execution_authority",
            "crypto_core.validation.governed_paper_typed_identity",
            "crypto_core.validation.historical_execution_economics",
            "crypto_core.validation.historical_execution_economics_policy",
            "crypto_core.validation.historical_ohlc_bar_archive",
            "crypto_core.validation.historical_position_management_policy",
        },
    )
