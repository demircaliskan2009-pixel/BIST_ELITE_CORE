"""Explicit paper sleeve funding evidence contract (PAPER_SLEEVE_FUNDING_EVIDENCE_V1).

A ``PaperSleeveFundingEvidence`` is the digest-bound statement of every paper funding settlement that applies to one
sleeve's position on one market inside one UTC-day-aligned window. The accepted repository has no paper funding
accrual producer. This artifact is therefore the CONTRACT a future producer must emit; it computes no funding itself.
It invents no venue funding rate and no funding amount, and it never turns missing funding into an implicit zero:
without this artifact, a funding-requiring sleeve valuation is blocked.

Each ``PaperSleeveFundingEvent`` carries:

* ``event_id``: a unique identifier;
* ``settlement_at_ns``: a unique instant inside the window, start-inclusive and end-exclusive;
* ``position_state_digest``: the exact digest of the paper position state the settlement applies to. The sleeve
  valuation re-binds it to the reconstructed position chain, so a settlement can never be applied to another sleeve's
  or a stale position;
* ``funding_amount``: a signed canonical scale-18 paper amount, positive when the bound position receives it and
  negative when it pays.

The evidence asserts completeness for its whole window; an empty event tuple is an explicit, digest-bound statement
that no settlement applied, never an absence.

Non-overclaim: amounts, settlement instants and their completeness are caller-supplied evidence whose external origin
is NOT proven (``funding_amount_origin_proven`` and ``settlement_time_origin_proven`` are structurally False). This is
never venue truth, real money, capital, a balance or margin.

Malformed input raises ``PaperSleeveFundingEvidenceError``. One assembly path serves the builder and the verifier
reassembly, and ``verify_paper_sleeve_funding_evidence`` is total. Exact ``Fraction`` arithmetic, no float, no
``decimal`` context, and no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, replace
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

_SCHEMA_VERSION = "paper-sleeve-funding-evidence.v1"
_REASON_PREFIX = "paper_sleeve_funding_evidence"
_SELF_DIGEST_FIELD = "funding_evidence_digest"
_IDENTIFIER_EXTRA_CHARS = frozenset("-_./:")

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_sleeve_funding_evidence_rules.v1",
    "amount_rule_id": "signed_paper_amount_positive_received_negative_paid_by_the_bound_position.v1",
    "origin_rule_id": "caller_supplied_digest_bound_origin_not_proven_never_venue_truth.v1",
    "coverage_rule_id": "evidence_asserts_every_settlement_for_the_sleeve_market_inside_the_window.v1",
    "position_binding_rule_id": "each_event_binds_the_exact_position_state_digest_it_applies_to.v1",
    "time_rule_id": "settlement_inside_window_start_inclusive_end_exclusive_unique_instant.v1",
    "window_rule_id": "utc_day_aligned_window_of_positive_whole_days.v1",
    "decimal_scale": 18,
    "decimal_max_text_length": 60,
    "utc_day_ns": 86_400_000_000_000,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_identifier_length": 128,
    "max_market_symbol_length": 64,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_SCALE_FACTOR = 10**_SCALE
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_max_text_length"]  # type: ignore[assignment]
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_IDENTIFIER: int = _RULE_SET_V1["max_identifier_length"]  # type: ignore[assignment]
_MAX_MARKET_SYMBOL: int = _RULE_SET_V1["max_market_symbol_length"]  # type: ignore[assignment]


def paper_sleeve_funding_evidence_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


PAPER_SLEEVE_FUNDING_EVIDENCE_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("funding_amount_origin_proven", False),
    ("settlement_time_origin_proven", False),
    ("venue_funding_rate_consumed", False),
    ("current_venue_facts_consumed", False),
    ("funding_computed_here", False),
    ("account_equity_represented", False),
    ("capital_represented", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
)
_FLAG_NAMES = frozenset(name for name, _ in PAPER_SLEEVE_FUNDING_EVIDENCE_NON_CLAIM_FLAGS)


class PaperSleeveFundingEvidenceError(EdgeArtifactError):
    """Raised on malformed funding evidence input or a forbidden scope token."""


@dataclass(frozen=True)
class PaperSleeveFundingEvent:
    """One paper funding settlement applied to one exact position state. Origin not proven."""

    event_id: str
    settlement_at_ns: int
    position_state_digest: str
    funding_amount: str


@dataclass(frozen=True)
class PaperSleeveFundingEvidence:
    """Immutable, digest-bound funding evidence of one sleeve, market and UTC-day window. Never venue truth."""

    schema_version: str
    evidence_id: str
    sleeve_id: str
    market_symbol: str
    window_start_ns: int
    window_end_ns: int
    events: tuple[PaperSleeveFundingEvent, ...]
    event_count: int
    funding_total: str
    rule_set_id: str
    rule_set_digest: str
    funding_evidence_digest: str
    paper_only: bool = True
    funding_amount_origin_proven: bool = False
    settlement_time_origin_proven: bool = False
    venue_funding_rate_consumed: bool = False
    current_venue_facts_consumed: bool = False
    funding_computed_here: bool = False
    account_equity_represented: bool = False
    capital_represented: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False


_RECORD_TYPES = frozenset({PaperSleeveFundingEvent})


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperSleeveFundingEvidenceError:
    return PaperSleeveFundingEvidenceError(_reason(code))


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _decimal_is_canonical(value: object) -> bool:
    """Canonical ASCII fixed-scale decimal text within the rule set's representation-safety length."""

    if type(value) is not str or len(value) > _MAX_DECIMAL_TEXT or not value.isascii():
        return False
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if dot != "." or len(fraction) != _SCALE:
        return False
    if not _ascii_digits(integer) or not _ascii_digits(fraction):
        return False
    if integer != "0" and integer.startswith("0"):
        return False
    if negative and integer == "0" and fraction.strip("0") == "":
        return False
    return True


def _render_scale(value: Fraction) -> str | None:
    """Exact fixed scale-18 text of a value already on the scale-18 grid; ``None`` when off-grid or too long."""

    scaled = value * _SCALE_FACTOR
    if scaled.denominator != 1:
        return None
    units = abs(scaled.numerator)
    if units >= 10**_MAX_DECIMAL_TEXT:
        return None
    digits = str(units).rjust(_SCALE + 1, "0")
    rendered = f"{digits[:-_SCALE]}.{digits[-_SCALE:]}"
    if scaled.numerator < 0:
        rendered = f"-{rendered}"
    return rendered if len(rendered) <= _MAX_DECIMAL_TEXT else None


def _wire_int_is_valid(value: object, *, minimum: int) -> bool:
    return type(value) is int and minimum <= value <= _MAX_WIRE_INT


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_identifier(value: object, field_name: str, *, max_length: int) -> str:
    if type(value) is not str or value == "" or len(value) > max_length or not value.isascii():
        raise _fail(f"{field_name}_invalid")
    if not value[0].isalnum() or any(not (char.isalnum() or char in _IDENTIFIER_EXTRA_CHARS) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if not _wire_int_is_valid(value, minimum=minimum):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


# --- events ---------------------------------------------------------------------------------------------------------


def _canonical_events(
    values: object, *, window_start_ns: int, window_end_ns: int
) -> tuple[tuple[PaperSleeveFundingEvent, ...], Fraction]:
    if type(values) not in (tuple, list):
        raise _fail("events_malformed")
    by_instant: dict[int, PaperSleeveFundingEvent] = {}
    identifiers: set[str] = set()
    folded: set[str] = set()
    total = Fraction(0)
    for item in tuple(values):  # type: ignore[arg-type]
        if type(item) is not PaperSleeveFundingEvent:
            raise _fail("event_malformed")
        event_id = _require_identifier(getattr(item, "event_id", None), "event_id", max_length=_MAX_IDENTIFIER)
        instant = _require_int(getattr(item, "settlement_at_ns", None), "settlement_at_ns", minimum=0)
        position_digest = getattr(item, "position_state_digest", None)
        if not edge_is_hex64(position_digest):
            raise _fail("position_state_digest_invalid")
        amount = getattr(item, "funding_amount", None)
        if not _decimal_is_canonical(amount):
            raise _fail("funding_amount_invalid")
        if instant < window_start_ns or instant >= window_end_ns:
            raise _fail("settlement_outside_window")
        if event_id in identifiers:
            raise _fail("event_id_duplicate")
        if event_id.lower() in folded:
            raise _fail("event_id_case_ambiguous")
        if instant in by_instant:
            raise _fail("settlement_instant_duplicate")
        identifiers.add(event_id)
        folded.add(event_id.lower())
        total += Fraction(amount)  # type: ignore[arg-type]
        by_instant[instant] = PaperSleeveFundingEvent(
            event_id=event_id,
            settlement_at_ns=instant,
            position_state_digest=position_digest,  # type: ignore[arg-type]
            funding_amount=amount,  # type: ignore[arg-type]
        )
    return tuple(by_instant[instant] for instant in sorted(by_instant)), total


# --- serialization --------------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in value]
    if type(value) is int:
        if value < 0 or value > _MAX_WIRE_INT:
            raise _fail("payload_integer_out_of_range")
        return value
    if type(value) in (str, bool):
        return value
    raise _fail("payload_value_not_canonical")


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize exactly: every value must be an exact builtin, tuple or record."""

    names = [field.name for field in fields(artifact)]  # type: ignore[arg-type]
    return {name: _serialize(getattr(artifact, name)) for name in names}


# --- assembly -------------------------------------------------------------------------------------------------------


def _assemble_evidence(
    *,
    evidence_id: object,
    sleeve_id: object,
    market_symbol: object,
    window_start_ns: object,
    window_end_ns: object,
    events: object,
) -> PaperSleeveFundingEvidence:
    """The one funding-evidence assembly path, shared by the builder and verifier reassembly."""

    evidence_id = _require_text(evidence_id, "evidence_id")
    sleeve_id = _require_identifier(sleeve_id, "sleeve_id", max_length=_MAX_IDENTIFIER)
    market_symbol = _require_identifier(market_symbol, "market_symbol", max_length=_MAX_MARKET_SYMBOL)
    start = _require_int(window_start_ns, "window_start_ns", minimum=0)
    end = _require_int(window_end_ns, "window_end_ns", minimum=0)
    if start % _DAY_NS != 0 or end % _DAY_NS != 0 or end <= start:
        raise _fail("window_not_utc_day_aligned")
    ordered, total = _canonical_events(events, window_start_ns=start, window_end_ns=end)
    total_text = _render_scale(total)
    if total_text is None:
        raise _fail("funding_total_not_representable")
    seed = PaperSleeveFundingEvidence(
        schema_version=_SCHEMA_VERSION,
        evidence_id=evidence_id,
        sleeve_id=sleeve_id,
        market_symbol=market_symbol,
        window_start_ns=start,
        window_end_ns=end,
        events=ordered,
        event_count=len(ordered),
        funding_total=total_text,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST,
        funding_evidence_digest="",
    )
    return replace(seed, funding_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_paper_sleeve_funding_evidence(
    *,
    evidence_id: str,
    sleeve_id: str,
    market_symbol: str,
    window_start_ns: int,
    window_end_ns: int,
    events: tuple[PaperSleeveFundingEvent, ...] | list[PaperSleeveFundingEvent],
) -> PaperSleeveFundingEvidence:
    """Seal caller-supplied funding settlements for one sleeve, market and window; malformed input raises."""

    return _assemble_evidence(
        evidence_id=evidence_id,
        sleeve_id=sleeve_id,
        market_symbol=market_symbol,
        window_start_ns=window_start_ns,
        window_end_ns=window_end_ns,
        events=events,
    )


def paper_sleeve_funding_evidence_to_dict(evidence: PaperSleeveFundingEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def paper_sleeve_funding_evidence_digest(evidence: PaperSleeveFundingEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``funding_evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


# --- strict parsing -------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if not _wire_int_is_valid(value, minimum=0):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_decimal(value: object) -> str:
    if not _decimal_is_canonical(value):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_events(value: object) -> tuple[PaperSleeveFundingEvent, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    events = [_parse_exact(PaperSleeveFundingEvent, entry, _EVENT_CONVERTERS) for entry in value]
    return tuple(events)  # type: ignore[arg-type]


_EVENT_CONVERTERS: dict[str, Callable[[object], object]] = {
    "settlement_at_ns": _as_int,
    "funding_amount": _as_decimal,
}
_EVIDENCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "window_start_ns": _as_int,
    "window_end_ns": _as_int,
    "events": _as_events,
    "event_count": _as_int,
    "funding_total": _as_decimal,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def paper_sleeve_funding_evidence_from_payload(payload: object) -> PaperSleeveFundingEvidence:
    """Strictly reconstruct funding evidence from its serialized payload (exact fields, types and domains)."""

    return _parse_exact(PaperSleeveFundingEvidence, payload, _EVIDENCE_CONVERTERS)  # type: ignore[return-value]


def paper_sleeve_funding_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a funding-evidence snapshot."""

    try:
        paper_sleeve_funding_evidence_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_evidence(evidence: object) -> PaperSleeveFundingEvidence:
    return _assemble_evidence(
        evidence_id=evidence.evidence_id,  # type: ignore[attr-defined]
        sleeve_id=evidence.sleeve_id,  # type: ignore[attr-defined]
        market_symbol=evidence.market_symbol,  # type: ignore[attr-defined]
        window_start_ns=evidence.window_start_ns,  # type: ignore[attr-defined]
        window_end_ns=evidence.window_end_ns,  # type: ignore[attr-defined]
        events=evidence.events,  # type: ignore[attr-defined]
    )


def verify_paper_sleeve_funding_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove funding evidence by strict parse, self-digest recomputation and reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        evidence,
        cls=PaperSleeveFundingEvidence,
        to_payload=_to_payload,
        parse_payload=paper_sleeve_funding_evidence_from_payload,
        reassemble=_reassemble_evidence,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "PAPER_SLEEVE_FUNDING_EVIDENCE_NON_CLAIM_FLAGS",
    "PAPER_SLEEVE_FUNDING_EVIDENCE_RULE_SET_DIGEST",
    "PaperSleeveFundingEvent",
    "PaperSleeveFundingEvidence",
    "PaperSleeveFundingEvidenceError",
    "build_paper_sleeve_funding_evidence",
    "paper_sleeve_funding_evidence_digest",
    "paper_sleeve_funding_evidence_from_payload",
    "paper_sleeve_funding_evidence_payload_is_well_formed",
    "paper_sleeve_funding_evidence_rule_set",
    "paper_sleeve_funding_evidence_to_dict",
    "verify_paper_sleeve_funding_evidence",
]
