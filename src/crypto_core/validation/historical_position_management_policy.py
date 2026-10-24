"""Versioned protective position-management policy (PROTECTIVE_POSITION_LIFECYCLE_V1).

PRDV4 §1.9 "Position Management for Funding Trades" as ONE versioned, digest-bound policy that the one economics
engine (``historical_execution_economics``) applies identically to the historical backtest and to governed paper:

* maximum holding period: a close-only protective obligation at exactly 24 h after the first FLAT -> non-zero executed
  fill of an excursion. Adding to or reducing the excursion never moves that anchor;
* mandatory stop: ``1.5 x ATR_4h`` from the excursion's opening fill price, with ATR_4h by the human-approved DEC-7
  method (``WILDER_ATR_14_CONTIGUOUS_COMPLETED_UTC_BARS_V1``) over an authenticated ``HistoricalOhlcBarArchive``, read
  at the decision instant of the opening intent. A PIT-visible mark at or beyond the stop (LONG: at or below, SHORT: at
  or above) triggers the close-only obligation; a trigger is never a fill;
* time-decay stop: PRDV4 asks for a 20% tightening every 8 h. Its exact reading is DEC-9 (see below).

Rule identities and PRDV4 doctrine values are code-defined and committed by ``POSITION_MANAGEMENT_RULE_SET_DIGEST``;
the builder copies them into every policy and the verifier refuses any other value. The governed caller inputs have
no default: the instrument, the OHLC price semantics the ATR reads, the maximum age of the latest ATR bar and the
stop-tightening method.

Method authority. Every method id this module implements carries its authority:

* ``PRDV4_DOCTRINE``: the published 24 h, 1.5 x ATR_4h, 20% and 8 h values;
* ``HUMAN_AUTHORIZED``: DEC-7, the Wilder ATR, approved by the human for this contract;
* ``CONTRACT_SPECIFIED``: the engineering of this contract under DEC-1 and its invariants, namely the PIT mark trigger
  and the close-only standing obligation executed by the unchanged fill model. A standing obligation waits for the
  first eligible book: ``max_execution_delay_ns`` bounds the staleness of a decision intent, and a close-only
  obligation never goes stale;
* ``HUMAN_APPROVAL_REQUIRED`` (DEC-9): the controller's proposed reading of the time-decay stop
  (``PRDV4_1_9_TIGHTEN_GEOMETRIC_0_8_PER_COMPLETE_8H_FROM_FIRST_OPEN_FILL_V1``: after k complete 8 h periods since the
  first opening fill the distance is ``d0 x 0.8^k``, it never loosens, and the 24 h maximum hold stays independent).
  The repository records interpretations of PRDV4 methods as human-authorized readings by method id
  (``edge_factory_design.md`` section 1a), and no human has authorized this one. It is executed only under a
  ``TEST_ONLY_SYNTHETIC`` approval, which is always surfaced as synthetic. A ``HUMAN_GOVERNANCE`` approval of a policy
  that applies it never advances;
* ``TIGHTENING_NOT_APPLIED_PENDING_DEC9``: the stop keeps its initial distance and no tightening is claimed.

A policy that does not apply the time-decay stop is never §1.9-complete. Under either choice the paper entry gate keeps
FB-STOP-TIGHTENING blocked (``governed_paper_entry_safety``).

``HistoricalPositionManagementApproval`` binds the exact policy digest, the rule-set digest, the instrument, the
authenticated StrategySpec digest and the adopted OHLC source declaration digest. Matching is decided by the consumer
(the economics result). Deterministic and pure: no IO, clock, randomness, network or environment. It proves no edge,
profitability, venue fact or readiness.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    verify_edge_artifact_total,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_ohlc_bar_archive import WILDER_ATR_METHOD_ID, HistoricalOhlcPriceSemantics

_SCHEMA_VERSION = "historical-position-management-policy.v1"
_PREFIX = "historical_position_management_policy"
_DIGEST_FIELD = "policy_digest"
_HOUR_NS = 3_600_000_000_000
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")

MAX_HOLD_RULE_V1 = "PRDV4_1_9_MAX_HOLD_24H_FROM_FIRST_OPEN_FILL_V1"
STOP_RULE_V1 = "PRDV4_1_9_STOP_1_5_ATR_4H_FROM_OPENING_FILL_PRICE_V1"
STOP_TRIGGER_RULE_V1 = "PIT_VISIBLE_MARK_AT_OR_BEYOND_THE_STOP_V1"
PROTECTIVE_EXECUTION_RULE_V1 = "CLOSE_ONLY_STANDING_OBLIGATION_ENGINE_FILL_MODEL_V1"
EVENT_PRIORITY_RULE_V1 = "funding_then_protective_then_decision_then_fill_then_valuation_v1"
RE_ENTRY_RULE_V1 = "fresh_entry_admission_after_a_protective_close_v1"
TIGHTENING_DEC9_READING_V1 = "PRDV4_1_9_TIGHTEN_GEOMETRIC_0_8_PER_COMPLETE_8H_FROM_FIRST_OPEN_FILL_V1"
TIGHTENING_NOT_APPLIED_PENDING_DEC9 = "TIGHTENING_NOT_APPLIED_PENDING_DEC9"

# PRDV4 §1.9 doctrine values: published, never governed parameters.
MAX_HOLD_NS = 24 * _HOUR_NS
STOP_ATR_MULTIPLE = Fraction(3, 2)
ATR_INTERVAL_NS = 4 * _HOUR_NS
ATR_PERIOD = 14
TIGHTENING_PERIOD_NS = 8 * _HOUR_NS
TIGHTENING_FACTOR = Fraction(4, 5)


class PositionManagementMethodAuthority(str, Enum):
    PRDV4_DOCTRINE = "PRDV4_DOCTRINE"
    HUMAN_AUTHORIZED = "HUMAN_AUTHORIZED"
    CONTRACT_SPECIFIED = "CONTRACT_SPECIFIED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    NOT_APPLIED = "NOT_APPLIED"


POSITION_MANAGEMENT_METHOD_AUTHORITY: dict[str, PositionManagementMethodAuthority] = {
    MAX_HOLD_RULE_V1: PositionManagementMethodAuthority.PRDV4_DOCTRINE,
    STOP_RULE_V1: PositionManagementMethodAuthority.PRDV4_DOCTRINE,
    WILDER_ATR_METHOD_ID: PositionManagementMethodAuthority.HUMAN_AUTHORIZED,
    STOP_TRIGGER_RULE_V1: PositionManagementMethodAuthority.CONTRACT_SPECIFIED,
    PROTECTIVE_EXECUTION_RULE_V1: PositionManagementMethodAuthority.CONTRACT_SPECIFIED,
    TIGHTENING_DEC9_READING_V1: PositionManagementMethodAuthority.HUMAN_APPROVAL_REQUIRED,
    TIGHTENING_NOT_APPLIED_PENDING_DEC9: PositionManagementMethodAuthority.NOT_APPLIED,
}
_TIGHTENING_METHODS = (TIGHTENING_DEC9_READING_V1, TIGHTENING_NOT_APPLIED_PENDING_DEC9)


def _render(value: Fraction) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None:  # pragma: no cover - code constants are representable
        raise ValueError("position management constant unrepresentable")
    return rendered


POSITION_MANAGEMENT_RULE_SET: dict[str, object] = {
    "rule_set_id": "historical-position-management.v1",
    "contract_id": "PROTECTIVE_POSITION_LIFECYCLE_V1",
    "authorities": ["PRDV4 §1.9", "DEC-1 protective close-only authority", "DEC-7 Wilder ATR(14)"],
    "max_hold_rule_id": MAX_HOLD_RULE_V1,
    "max_hold_ns": MAX_HOLD_NS,
    "max_hold_anchor": "first_flat_to_nonzero_executed_fill_of_the_excursion",
    "stop_rule_id": STOP_RULE_V1,
    "stop_atr_multiple": _render(STOP_ATR_MULTIPLE),
    "stop_basis": "executed_price_of_the_opening_fill",
    "stop_atr_instant": "decision_instant_of_the_opening_intent",
    "atr_method_id": WILDER_ATR_METHOD_ID,
    "atr_interval_ns": ATR_INTERVAL_NS,
    "atr_period": ATR_PERIOD,
    "stop_trigger_rule_id": STOP_TRIGGER_RULE_V1,
    "stop_trigger_observations": "every_mark_visibility_after_the_open_and_every_tightening_milestone",
    "tightening_methods": list(_TIGHTENING_METHODS),
    "tightening_period_ns": TIGHTENING_PERIOD_NS,
    "tightening_factor": _render(TIGHTENING_FACTOR),
    "protective_execution_rule_id": PROTECTIVE_EXECUTION_RULE_V1,
    "event_priority_rule_id": EVENT_PRIORITY_RULE_V1,
    "re_entry_rule_id": RE_ENTRY_RULE_V1,
    "method_authority": {key: value.value for key, value in sorted(POSITION_MANAGEMENT_METHOD_AUTHORITY.items())},
}
POSITION_MANAGEMENT_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(POSITION_MANAGEMENT_RULE_SET))
POSITION_MANAGEMENT_RULE_SET_ID = str(POSITION_MANAGEMENT_RULE_SET["rule_set_id"])


class HistoricalPositionManagementPolicyError(EdgeArtifactError):
    """Malformed input or a value outside the code-defined rule set: a policy is never represented over it."""


@dataclass(frozen=True)
class HistoricalPositionManagementPolicy:
    """One versioned protective position-management policy; ``policy_digest`` covers every other field."""

    schema_version: str
    policy_id: str
    policy_version: str
    instrument: str
    rule_set_id: str
    rule_set_digest: str
    max_hold_rule_id: str
    max_hold_ns: int
    stop_rule_id: str
    stop_atr_multiple: str
    atr_method_id: str
    atr_interval_ns: int
    atr_period: int
    atr_bar_price_semantics: HistoricalOhlcPriceSemantics
    atr_max_bar_age_ns: int
    stop_trigger_rule_id: str
    stop_tightening_method_id: str
    stop_tightening_period_ns: int
    stop_tightening_factor: str
    protective_execution_rule_id: str
    event_priority_rule_id: str
    re_entry_rule_id: str
    policy_digest: str


@dataclass(frozen=True)
class HistoricalPositionManagementApproval:
    """Governance approval of one exact policy for one strategy, instrument and adopted OHLC source."""

    approval_reference: str
    approval_digest: str
    approval_kind: HistoricalExecutionApprovalKind
    approved_policy_digest: str
    approved_rule_set_digest: str
    approved_instrument: str
    approved_strategy_spec_digest: str
    approved_ohlc_source_digest: str


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> HistoricalPositionManagementPolicyError:
    return HistoricalPositionManagementPolicyError(_reason(code))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_instrument(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 64 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


_CODE_DEFINED: dict[str, object] = {
    "schema_version": _SCHEMA_VERSION,
    "rule_set_id": POSITION_MANAGEMENT_RULE_SET_ID,
    "rule_set_digest": POSITION_MANAGEMENT_RULE_SET_DIGEST,
    "max_hold_rule_id": MAX_HOLD_RULE_V1,
    "max_hold_ns": MAX_HOLD_NS,
    "stop_rule_id": STOP_RULE_V1,
    "stop_atr_multiple": _render(STOP_ATR_MULTIPLE),
    "atr_method_id": WILDER_ATR_METHOD_ID,
    "atr_interval_ns": ATR_INTERVAL_NS,
    "atr_period": ATR_PERIOD,
    "stop_trigger_rule_id": STOP_TRIGGER_RULE_V1,
    "stop_tightening_period_ns": TIGHTENING_PERIOD_NS,
    "stop_tightening_factor": _render(TIGHTENING_FACTOR),
    "protective_execution_rule_id": PROTECTIVE_EXECUTION_RULE_V1,
    "event_priority_rule_id": EVENT_PRIORITY_RULE_V1,
    "re_entry_rule_id": RE_ENTRY_RULE_V1,
}


def _assemble_policy(
    *,
    policy_id: object,
    policy_version: object,
    instrument: object,
    atr_bar_price_semantics: object,
    atr_max_bar_age_ns: object,
    stop_tightening_method_id: object,
) -> HistoricalPositionManagementPolicy:
    """The one policy assembly path, shared by the builder and the verifier."""

    if type(atr_bar_price_semantics) is not HistoricalOhlcPriceSemantics:
        raise _fail("atr_bar_price_semantics_invalid")
    if not historical_execution_wire_int_is_valid(atr_max_bar_age_ns, minimum=1):
        raise _fail("atr_max_bar_age_ns_invalid")
    if type(stop_tightening_method_id) is not str or stop_tightening_method_id not in _TIGHTENING_METHODS:
        raise _fail("stop_tightening_method_unsupported")
    seed = HistoricalPositionManagementPolicy(
        policy_id=_require_text(policy_id, "policy_id"),
        policy_version=_require_text(policy_version, "policy_version"),
        instrument=_require_instrument(instrument, "instrument"),
        atr_bar_price_semantics=atr_bar_price_semantics,
        atr_max_bar_age_ns=atr_max_bar_age_ns,  # type: ignore[arg-type]
        stop_tightening_method_id=stop_tightening_method_id,
        policy_digest="",
        **_CODE_DEFINED,  # type: ignore[arg-type]
    )
    return replace(seed, policy_digest=edge_payload_digest(_to_payload(seed), _DIGEST_FIELD))


def build_historical_position_management_policy(
    *,
    policy_id: str,
    policy_version: str,
    instrument: str,
    atr_bar_price_semantics: HistoricalOhlcPriceSemantics,
    atr_max_bar_age_ns: int,
    stop_tightening_method_id: str,
) -> HistoricalPositionManagementPolicy:
    """Build one policy from its governed inputs; the rule identities and doctrine values are code-defined.

    Nothing is defaulted. A malformed or unsupported governed input raises ``HistoricalPositionManagementPolicyError``.
    """

    return _assemble_policy(
        policy_id=policy_id,
        policy_version=policy_version,
        instrument=instrument,
        atr_bar_price_semantics=atr_bar_price_semantics,
        atr_max_bar_age_ns=atr_max_bar_age_ns,
        stop_tightening_method_id=stop_tightening_method_id,
    )


def historical_position_management_policy_to_dict(policy: HistoricalPositionManagementPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a policy, including its self-digest."""

    return _to_payload(policy)


def historical_position_management_policy_digest(policy: HistoricalPositionManagementPolicy) -> str:
    """Recompute the canonical policy digest, excluding only ``policy_digest``."""

    return edge_payload_digest(_to_payload(policy), _DIGEST_FIELD)


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "max_hold_ns": _as_int,
    "atr_interval_ns": _as_int,
    "atr_period": _as_int,
    "atr_bar_price_semantics": _as_enum(HistoricalOhlcPriceSemantics),
    "atr_max_bar_age_ns": _as_int,
    "stop_tightening_period_ns": _as_int,
}


def historical_position_management_policy_from_payload(payload: object) -> HistoricalPositionManagementPolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields and types; no proof)."""

    return _parse_exact(HistoricalPositionManagementPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def historical_position_management_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a policy snapshot."""

    try:
        historical_position_management_policy_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_policy(policy: object) -> HistoricalPositionManagementPolicy:
    return _assemble_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        policy_version=policy.policy_version,  # type: ignore[attr-defined]
        instrument=policy.instrument,  # type: ignore[attr-defined]
        atr_bar_price_semantics=policy.atr_bar_price_semantics,  # type: ignore[attr-defined]
        atr_max_bar_age_ns=policy.atr_max_bar_age_ns,  # type: ignore[attr-defined]
        stop_tightening_method_id=policy.stop_tightening_method_id,  # type: ignore[attr-defined]
    )


def verify_historical_position_management_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a policy: strict parse, digest recomputation and reassembly from its governed inputs. Total."""

    return verify_edge_artifact_total(
        policy,
        cls=HistoricalPositionManagementPolicy,
        to_payload=_to_payload,
        parse_payload=historical_position_management_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_DIGEST_FIELD,
        reason=_reason,
    )


def historical_position_management_tightening_applied(policy: HistoricalPositionManagementPolicy) -> bool:
    """Whether the policy applies the DEC-9 time-decay reading (never §1.9-complete otherwise)."""

    return policy.stop_tightening_method_id == TIGHTENING_DEC9_READING_V1


def historical_position_management_methods_requiring_human_approval(
    policy: HistoricalPositionManagementPolicy,
) -> tuple[str, ...]:
    """The applied method ids no human has authorized yet (sorted); a HUMAN_GOVERNANCE approval never covers them."""

    applied = (
        policy.max_hold_rule_id,
        policy.stop_rule_id,
        policy.atr_method_id,
        policy.stop_trigger_rule_id,
        policy.stop_tightening_method_id,
        policy.protective_execution_rule_id,
    )
    return tuple(
        sorted(
            method
            for method in applied
            if POSITION_MANAGEMENT_METHOD_AUTHORITY.get(method)
            is PositionManagementMethodAuthority.HUMAN_APPROVAL_REQUIRED
        )
    )


# --- approval ----------------------------------------------------------------------------------------------------------


def canonical_historical_position_management_approval(
    approval: object,
) -> HistoricalPositionManagementApproval | None:
    """Structurally validate an approval (``None`` stays ``None``); raises on any malformed state."""

    if approval is None:
        return None
    if type(approval) is not HistoricalPositionManagementApproval:
        raise _fail("approval_malformed")
    if type(approval.approval_kind) is not HistoricalExecutionApprovalKind:
        raise _fail("approval_kind_invalid")
    return HistoricalPositionManagementApproval(
        approval_reference=_require_text(approval.approval_reference, "approval_reference"),
        approval_digest=_require_hex64(approval.approval_digest, "approval_digest"),
        approval_kind=approval.approval_kind,
        approved_policy_digest=_require_hex64(approval.approved_policy_digest, "approved_policy_digest"),
        approved_rule_set_digest=_require_hex64(approval.approved_rule_set_digest, "approved_rule_set_digest"),
        approved_instrument=_require_instrument(approval.approved_instrument, "approved_instrument"),
        approved_strategy_spec_digest=_require_hex64(
            approval.approved_strategy_spec_digest, "approved_strategy_spec_digest"
        ),
        approved_ohlc_source_digest=_require_hex64(approval.approved_ohlc_source_digest, "approved_ohlc_source_digest"),
    )


def historical_position_management_approval_mismatches(
    approval: HistoricalPositionManagementApproval,
    *,
    policy: HistoricalPositionManagementPolicy,
    strategy_spec_digest: str,
    instrument: str,
    ohlc_source_digest: str,
) -> tuple[str, ...]:
    """Names of approval fields that do not match the exact policy and authenticated context (sorted)."""

    expected = {
        "approved_policy_digest": policy.policy_digest,
        "approved_rule_set_digest": policy.rule_set_digest,
        "approved_instrument": instrument,
        "approved_strategy_spec_digest": strategy_spec_digest,
        "approved_ohlc_source_digest": ohlc_source_digest,
    }
    return tuple(sorted(name for name, value in expected.items() if getattr(approval, name) != value))


_APPROVAL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approval_kind": _as_enum(HistoricalExecutionApprovalKind),
}


def historical_position_management_approval_from_payload(payload: object) -> HistoricalPositionManagementApproval:
    """Strictly reconstruct an approval from its serialized payload (exact fields and types; no proof)."""

    return _parse_exact(HistoricalPositionManagementApproval, payload, _APPROVAL_CONVERTERS)  # type: ignore[return-value]


__all__ = [
    "ATR_INTERVAL_NS",
    "ATR_PERIOD",
    "EVENT_PRIORITY_RULE_V1",
    "MAX_HOLD_NS",
    "MAX_HOLD_RULE_V1",
    "POSITION_MANAGEMENT_METHOD_AUTHORITY",
    "POSITION_MANAGEMENT_RULE_SET",
    "POSITION_MANAGEMENT_RULE_SET_DIGEST",
    "POSITION_MANAGEMENT_RULE_SET_ID",
    "PROTECTIVE_EXECUTION_RULE_V1",
    "RE_ENTRY_RULE_V1",
    "STOP_ATR_MULTIPLE",
    "STOP_RULE_V1",
    "STOP_TRIGGER_RULE_V1",
    "TIGHTENING_DEC9_READING_V1",
    "TIGHTENING_FACTOR",
    "TIGHTENING_NOT_APPLIED_PENDING_DEC9",
    "TIGHTENING_PERIOD_NS",
    "HistoricalPositionManagementApproval",
    "HistoricalPositionManagementPolicy",
    "HistoricalPositionManagementPolicyError",
    "PositionManagementMethodAuthority",
    "build_historical_position_management_policy",
    "canonical_historical_position_management_approval",
    "historical_position_management_approval_from_payload",
    "historical_position_management_approval_mismatches",
    "historical_position_management_methods_requiring_human_approval",
    "historical_position_management_policy_digest",
    "historical_position_management_policy_from_payload",
    "historical_position_management_policy_payload_is_well_formed",
    "historical_position_management_policy_to_dict",
    "historical_position_management_tightening_applied",
    "verify_historical_position_management_policy",
]
