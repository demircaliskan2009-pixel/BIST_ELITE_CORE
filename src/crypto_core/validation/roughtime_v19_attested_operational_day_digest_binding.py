"""Bind a governed attested-operational-day self-digest to an authenticated Roughtime draft-19 request NONC.

This module adds exactly ONE structural provenance edge to two ALREADY MERGED layers and implements no
cryptographic primitive of its own. The governed subject is an exact
:class:`~crypto_core.validation.paper_attested_operational_day_evidence.PaperAttestedOperationalDayEvidence`;
the authentication carrier is an exact
:class:`~crypto_core.validation.roughtime_v19_request_in_signed_response.RoughtimeV19RequestInSignedResponse`
(the merged K4 + SREP aggregate). The edge is:

    current valid governed-day CONTENT -> freshly recomputed canonical day self-digest -> exact request
    ``NONC`` -> existing K4 request-inclusion proof -> existing K5/SREP authentication chain.

Bounded profile: ONE governance-selected, versioned profile identified by
:data:`ROUGHTIME_V19_ATTESTED_OPERATIONAL_DAY_DIGEST_BINDING_PROFILE_ID`. It inherits the K1 structural
bounds, the K2/K3 semantic bounds, the K4 Merkle bounds and the K5/SREP signature bounds unchanged, and adds
no new byte-size ceiling, no new hash and no new public-key operation.

A successful artifact proves EXACTLY this one sentence and nothing further:

    The freshly recomputed canonical self-digest of the exact supplied READY governed operational-day evidence
    is byte-for-byte the ``NONC`` of the exact request that the merged aggregate proves folds through that
    response's ``PATH``/``INDX`` to the same ``ROOT`` carried by its signed ``SREP``, whose outer signature and
    ``CERT`` chain validate relative only to the exact caller-supplied long-term public key.

"READY" is proven by re-validating the artifact's CURRENT CONTENT, never by trusting its construction history.
The day revalidation is LOAD-BEARING, not defence-in-depth: without it any REJECTED or unsafe-flagged day
could be bound simply by choosing a request ``NONC`` equal to that day's digest. Conversely, for a FIXED signed
response the ``NONC`` is fixed, so a resealed day can only pass if its canonical content digests to exactly
those 32 bytes -- a SHA-256 second preimage. The signature therefore pins the day's canonical CONTENT, and says
nothing whatever about origin or time.

THE INPUT DAY REMAINS OPERATOR-ATTESTED, NOT MACHINE-PROVEN. This module proves NOTHING about: the truthfulness
of the operator attestation; correspondence to a real calendar day; whether any supplied session occurred in
real time; the existence of the original time windows (they are not carried by the day artifact and cannot be
recomputed here); which builder invocation produced the day (content-equivalent reconstruction is
indistinguishable and is intentionally accepted as CURRENT CONTENT, never as historical origin); wall-clock
origin; truthful or authenticated UTC time; whether the digest existed before or after the response; responder
request-receipt ordering; not-before; not-after; timestamp origin; machine-time origin; ``NONC``
unpredictability; provider identity; provider ownership of the long-term key; key provenance, admission or
revocation; deployed Roughtime version compatibility; endpoint reachability; source admission; source role;
``proof_verified``; quorum eligibility; quorum satisfaction; interval or sandwich completion; operational-day
machine proof; >=30-day machine-proven spacing; PRDV4 Stage-4 completion; readiness; connector safety;
live/orders/capital; or profitability or edge. The binding is STRUCTURAL, never TEMPORAL. Exposing the governed
day object re-exposes its injected-deterministic ns fields, which keep their upstream
``injected_deterministic_ns.v1`` / ``operator_attested_not_machine_proven.v1`` semantics unchanged and are
neither wall-clock nor machine-proven.

Input trust boundary. The public verifier consumes two artifacts it did not build and trusts neither. Both
inputs must be the EXACT merged public types (``type(x) is C``, never ``isinstance``), checked BEFORE any
attribute, dataclass field, aggregate property or lifecycle method of either input is touched, so a hostile
``__getattribute__`` / ``__post_init__`` / ``__new__`` override can never execute. The governed day is then
re-validated field by field against its complete pinned inventory and its canonical self-digest is recomputed
through the merged public digest function; the aggregate is re-proven by snapshotting its three validating
public anchors and rebuilding a FRESH exact aggregate from exactly those snapshots, which transitively
re-proves K4, the ``CERT`` chain and the outer ``SREP`` signature.

Anchor dataflow (pinned). The caller aggregate is the VALIDATED SOURCE of the three stored snapshots; after the
snapshot completes, no further caller aggregate value is consumed -- in particular its ``signed_root`` is never
read, because that would cost one extra complete aggregate derivation for a value that must come from the fresh
artifact anyway. The three returned anchors ARE those exact validated snapshots, which the fresh constructor
independently re-proves. Only ``signed_root`` is sourced from the freshly reconstructed aggregate.

Error normalization is deliberately NARROW. Only the two closed prerequisite domain error classes are
normalized, each at the exact stage that owns it. This module never catches ``Exception``, ``RuntimeError``,
``AssertionError``, ``AttributeError``, ``TypeError``, ``ValueError``, any other built-in base, or
``BaseException``. The governed-day stage catches NOTHING: JSON-safety and exact shape are proven BEFORE the
public digest function is called, so that call cannot raise.

Output representation: a SEALED NON-CONTAINER object inheriting directly from ``object`` with
``__slots__ = ("__weakref__",)``. It stores EXACTLY FOUR values -- the exact original day reference and the
three exact byte anchors -- in a closure-local, non-module-global registry bound to one exact object identity
and guarded by a weak reference. The day self-digest and ``signed_root`` are deterministic derivatives and are
deliberately NOT stored; they are re-derived from scratch on EVERY public consumption, so no stored derivative
can drift from its source. No verdict is cached.

Mutable-reference policy. ``operational_day`` returns the EXACT registered reference; returning a copy or a
reconstruction is forbidden. That reference is NOT immutable: the upstream dataclass is frozen, but
``object.__setattr__`` defeats frozen. The caller already owns the reference, so exposing it grants no new
capability. Mutating it INVALIDATES FUTURE PROOF CONSUMPTION -- the recomputed digest changes, so it no longer
equals the signed ``NONC`` and every supported surface raises the closed artifact reason. That is fail-closed,
never a silently changed verdict, and never forgeable. Restoring the original content may make the artifact
valid again: only CURRENT CONTENT is proven. No mutable day field participates in hash, equality or the
rendered representation.

The artifact is EXPLICITLY UNHASHABLE (``__hash__ = None``) and its equality is validating IDENTITY-ONLY, so no
mutable day content can ever change a container placement or a comparison result.

SUPPORTED TRUST BOUNDARY (public/supported operations): hostile public inputs; wrong exact types and
subclasses; hostile public attribute access; ordinary ``setattr`` / ``delattr``; explicit
``object.__setattr__`` / ``object.__delattr__`` against the artifact instance; ``object.__new__`` hollow
exact-type instances; explicit unbound built-in base calls; public/class/instance introspection; equality and
truthiness consumption; ``copy.copy``; ``copy.deepcopy``; pickle serialization and reconstruction; malformed
rebuild arguments; and stale-id or weakref lifecycle accidents while private implementation state is
unmodified.

EXCLUDED PRIVATE-STATE BOUNDARY: direct reading of private function ``__closure__`` cells; direct mutation of
private closure-cell contents; monkeypatching private implementation functions or constants; debugger or
instrumentation compromise; interpreter-memory modification; and arbitrary same-process code execution that
intentionally rewrites private implementation state. No claim is made that closure contents are secret or
resist code admitted to this excluded boundary; pure Python cannot provide that guarantee.

Versioned specification: https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19
"""

from __future__ import annotations

import weakref
from dataclasses import fields
from enum import Enum
from weakref import ReferenceType

from crypto_core.validation.paper_attested_operational_day_evidence import (
    PaperAttestedOperationalDayEvidence,
    PaperAttestedOperationalDayEvidenceStatus,
    paper_attested_operational_day_evidence_digest,
)
from crypto_core.validation.roughtime_v19_request_in_signed_response import (
    RoughtimeV19RequestInSignedResponse,
    RoughtimeV19RequestInSignedResponseError,
)
from crypto_core.validation.roughtime_v19_request_semantics import (
    RoughtimeV19RequestSemanticError,
    parse_roughtime_v19_request,
)

# --- Binding profile (governance-selected, versioned; inherits every prerequisite bound unchanged) ----------
ROUGHTIME_V19_ATTESTED_OPERATIONAL_DAY_DIGEST_BINDING_PROFILE_ID = (
    "roughtime-v19-attested-operational-day-digest-request-nonce-binding.v1"
)

# Sentinel for safe attribute reads: distinguishes "attribute absent" from any legitimate value, including None.
_MISSING = object()

# D02. The COMPLETE declared field inventory of the governed day artifact, in its exact declaration order. It is
# consulted only AFTER the exact-type gate passes. Upstream schema drift fails CLOSED here instead of being
# silently digested but unvalidated.
_DAY_FIELD_NAMES = (
    "schema_version",
    "evidence_version",
    "status",
    "ready",
    "operational_day_evidence_id",
    "correlation_id",
    "market_symbol",
    "attested_utc_day_index",
    "day_start_ns",
    "day_end_ns",
    "day_duration_ns",
    "utc_day_policy",
    "session_count",
    "minimum_sessions_per_day",
    "expected_session_window_digests",
    "verified_session_window_digests",
    "session_window_ids",
    "session_run_ids",
    "session_aggregate_ids",
    "session_started_at_ns_list",
    "session_stopped_at_ns_list",
    "session_window_duration_ns_list",
    "session_metrics_summary_digests",
    "source_event_digest_counts",
    "attestor_id",
    "attestation_id",
    "attestation_source",
    "attestation_scope",
    "attestation_version",
    "operational_origin",
    "reason_codes",
    "metadata",
    "attested_operational_day_evidence_digest",
    "paper_only",
    "session_windows_consumed",
    "operator_attested_operational_day",
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

# D04 exact-shape partitions. Every declared field belongs to exactly one partition, so JSON safety and exact
# element typing are proven for the COMPLETE inventory before the public digest function is ever called.
_DAY_STR_FIELDS = (
    "schema_version",
    "evidence_version",
    "operational_day_evidence_id",
    "correlation_id",
    "market_symbol",
    "utc_day_policy",
    "attestor_id",
    "attestation_id",
    "attestation_source",
    "attestation_scope",
    "attestation_version",
    "operational_origin",
    "attested_operational_day_evidence_digest",
)
_DAY_INT_FIELDS = (
    "attested_utc_day_index",
    "day_start_ns",
    "day_end_ns",
    "day_duration_ns",
    "session_count",
    "minimum_sessions_per_day",
)
_DAY_STR_TUPLE_FIELDS = (
    "expected_session_window_digests",
    "verified_session_window_digests",
    "session_window_ids",
    "session_run_ids",
    "session_aggregate_ids",
    "session_metrics_summary_digests",
    "reason_codes",
)
_DAY_INT_TUPLE_FIELDS = (
    "session_started_at_ns_list",
    "session_stopped_at_ns_list",
    "session_window_duration_ns_list",
    "source_event_digest_counts",
)

# D09 / D10. ``operator_attested_operational_day`` is a member of the true-flag inventory; it is not a separate
# predicate family. ``ready`` is validated by D07 and is deliberately not repeated here.
_DAY_TRUE_FLAGS = (
    "paper_only",
    "session_windows_consumed",
    "operator_attested_operational_day",
)
_DAY_FALSE_FLAGS = (
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
_DAY_BOOL_FIELDS = ("ready", *_DAY_TRUE_FLAGS, *_DAY_FALSE_FLAGS)

# D11. Plain, non-empty, stripped, control-free identity strings. ``market_symbol`` is validated here and is not
# a separate predicate family.
_DAY_IDENTITY_FIELDS = (
    "operational_day_evidence_id",
    "correlation_id",
    "market_symbol",
    "attestor_id",
    "attestation_id",
)

# D14. Every session-indexed tuple must have length exactly ``session_count``.
_DAY_SESSION_LIST_FIELDS = (
    "expected_session_window_digests",
    "verified_session_window_digests",
    "session_window_ids",
    "session_run_ids",
    "session_aggregate_ids",
    "session_started_at_ns_list",
    "session_stopped_at_ns_list",
    "session_window_duration_ns_list",
    "session_metrics_summary_digests",
    "source_event_digest_counts",
)

# D05 / D06 pinned governed-day constants, re-pinned here so upstream drift fails closed.
_DAY_SCHEMA_VERSION = "paper-attested-operational-day-evidence.v1"
_DAY_EVIDENCE_VERSION = "paper-attested-operational-day-evidence.v1"
_DAY_ATTESTATION_SOURCE = "operator_attested_not_machine_proven.v1"
_DAY_ATTESTATION_SCOPE = "single_utc_day_digest_bound_paper_windows.v1"
_DAY_ATTESTATION_VERSION = "paper-attested-operational-day-attestation.v1"
_DAY_OPERATIONAL_ORIGIN = "operator_attested_not_machine_proven.v1"
_DAY_UTC_DAY_POLICY = "utc_epoch_day_index.v1"
_NANOSECONDS_PER_DAY = 86_400_000_000_000

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# The EXACT registered state of the output artifact: the irreducible governed subject plus the three proven
# minimal aggregate anchors, and nothing else.
_ANCHOR_FIELD_NAMES = (
    "operational_day",
    "request_raw",
    "response_raw",
    "long_term_public_key",
)
_BYTES_ANCHOR_FIELD_NAMES = (
    "request_raw",
    "response_raw",
    "long_term_public_key",
)

# The COMPLETE and EXCLUSIVE public property inventory, in exact declaration order. Index i of the validated
# view returned by proven_state is public property i.
_PUBLIC_FIELD_NAMES = (
    "operational_day",
    "attested_operational_day_evidence_digest",
    "request_raw",
    "response_raw",
    "long_term_public_key",
    "signed_root",
)

_DAY_TYPE_NAME = "PaperAttestedOperationalDayEvidence"

_ERROR_REASON_TYPE_MESSAGE = (
    "RoughtimeV19AttestedOperationalDayDigestBindingError requires a "
    "RoughtimeV19AttestedOperationalDayDigestBindingReason member"
)
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19AttestedOperationalDayDigestBindingError is immutable after construction"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})
_SEALED_ARTIFACT_MESSAGE = (
    "RoughtimeV19AttestedOperationalDayDigestBinding is a sealed artifact type and cannot be subclassed"
)


class RoughtimeV19AttestedOperationalDayDigestBindingReason(str, Enum):
    """Closed binding-failure inventory: exactly five members, evaluated in the pinned precedence below.

    Deliberately coarse. Reason 2 never says WHICH governed-day predicate failed. Reason 3 never re-exposes
    which K2/K3 rule, Merkle step, ``CERT`` or ``SIG`` check refused. Reason 4 leaks exactly one bit and cannot
    leak the ``NONC``, a matching-byte count or any prefix, because the comparison is a single whole-value
    equality. There is deliberately no digest-encoding reason (unreachable after a canonical hexdigest
    recomputation), no representation reason, and no temporal, provider, source, quorum or readiness reason.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    GOVERNED_DAY_ARTIFACT_INCONSISTENT = "governed_day_artifact_inconsistent"
    REQUEST_IN_SIGNED_RESPONSE_INCONSISTENT = "request_in_signed_response_inconsistent"
    DAY_DIGEST_REQUEST_NONCE_MISMATCH = "day_digest_request_nonce_mismatch"
    BINDING_ARTIFACT_INCONSISTENT = "binding_artifact_inconsistent"


# The single reason every artifact-state defect normalizes to, on construction and on every consumption
# surface. Bound once so no surface can drift onto a different (more informative, oracle-leaking) reason.
_ARTIFACT_INCONSISTENT = RoughtimeV19AttestedOperationalDayDigestBindingReason.BINDING_ARTIFACT_INCONSISTENT


class RoughtimeV19AttestedOperationalDayDigestBindingError(RuntimeError):
    """Raised for every binding failure, carrying exactly one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19AttestedOperationalDayDigestBindingReason`
    member. Any other argument raises a plain built-in ``TypeError`` before any attribute of that argument (in
    particular ``.value``) is read, so a hostile ``.value`` property can never run. ``str(error)`` is always
    exactly ``reason.value`` and no caller message is ever accepted.

    Scope of the immutability guarantee: ORDINARY attribute assignment and deletion through this class's public
    surface are blocked. This is not a claim of immunity to explicit ``object.__setattr__`` /
    ``object.__delattr__``, which bypass this class's hooks by design; the error object is a diagnostic carrier,
    not a proof artifact.
    """

    def __init__(self, reason: RoughtimeV19AttestedOperationalDayDigestBindingReason) -> None:
        if type(reason) is not RoughtimeV19AttestedOperationalDayDigestBindingReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19AttestedOperationalDayDigestBindingReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__delattr__(name)


def _err(
    reason: RoughtimeV19AttestedOperationalDayDigestBindingReason,
) -> RoughtimeV19AttestedOperationalDayDigestBindingError:
    return RoughtimeV19AttestedOperationalDayDigestBindingError(reason)


# --- Governed-day current-content revalidation (D01-D19) ---------------------------------------------------


def _is_plain_text(value: str) -> bool:
    """Plain, non-empty, stripped text free of ASCII control characters and DEL."""

    return (
        value.strip() != "" and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_control_free(value: str) -> bool:
    return not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _is_hex64(value: str) -> bool:
    return len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _validated_day_digest(
    operational_day: object,
    reason: RoughtimeV19AttestedOperationalDayDigestBindingReason,
) -> str:
    """Re-prove the COMPLETE supported governed-day contract on CURRENT CONTENT and return the fresh digest.

    Never trusts construction history, a carried derivative or a prior verdict. The carried self-digest is a
    consistency GATE only (D19); the returned value is always the fresh recomputation. Every JSON-safety and
    exact-shape gate (D04) completes BEFORE the merged public digest function is called, so that call cannot
    raise and no exception wrapper is needed around it.
    """
    # D01 exact type. Never isinstance: a subclass can exist because the upstream dataclass is not sealed.
    if type(operational_day) is not PaperAttestedOperationalDayEvidence:
        raise _err(reason)
    # D02 complete pinned field inventory in exact declaration order, consulted only after D01.
    if tuple(field.name for field in fields(operational_day)) != _DAY_FIELD_NAMES:
        raise _err(reason)
    # D03 completeness through a module-private sentinel: a hollow object.__new__ instance normalizes to the
    # owned coarse reason instead of raising a raw AttributeError.
    values: dict[str, object] = {}
    for name in _DAY_FIELD_NAMES:
        value = getattr(operational_day, name, _MISSING)
        if value is _MISSING:
            raise _err(reason)
        values[name] = value
    # D04 JSON safety and exact shape of every field.
    if type(values["status"]) is not PaperAttestedOperationalDayEvidenceStatus:
        raise _err(reason)
    for name in _DAY_BOOL_FIELDS:
        if type(values[name]) is not bool:
            raise _err(reason)
    for name in _DAY_INT_FIELDS:
        # ``type(x) is int`` also excludes bool, which is an int subclass.
        if type(values[name]) is not int:
            raise _err(reason)
    for name in _DAY_STR_FIELDS:
        # Exact str only: a str SUBCLASS compares equal but has caller-controlled behaviour.
        if type(values[name]) is not str:
            raise _err(reason)
    for name in _DAY_STR_TUPLE_FIELDS:
        entries = values[name]
        if type(entries) is not tuple:
            raise _err(reason)
        for entry in entries:
            if type(entry) is not str:
                raise _err(reason)
    for name in _DAY_INT_TUPLE_FIELDS:
        counts = values[name]
        if type(counts) is not tuple:
            raise _err(reason)
        for count in counts:
            if type(count) is not int:
                raise _err(reason)
    metadata = values["metadata"]
    if type(metadata) is not tuple:
        raise _err(reason)
    metadata_keys: list[str] = []
    for pair in metadata:
        if type(pair) is not tuple or len(pair) != 2:
            raise _err(reason)
        key, item = pair
        if type(key) is not str or type(item) is not str:
            raise _err(reason)
        if not _is_plain_text(key) or item != item.strip() or not _is_control_free(item):
            raise _err(reason)
        metadata_keys.append(key)
    if list(metadata) != sorted(metadata):
        raise _err(reason)
    if len(set(metadata_keys)) != len(metadata_keys):
        raise _err(reason)
    # D05 schema / evidence version.
    if values["schema_version"] != _DAY_SCHEMA_VERSION or values["evidence_version"] != _DAY_EVIDENCE_VERSION:
        raise _err(reason)
    # D06 provenance constants.
    if values["attestation_source"] != _DAY_ATTESTATION_SOURCE:
        raise _err(reason)
    if values["operational_origin"] != _DAY_OPERATIONAL_ORIGIN:
        raise _err(reason)
    if values["attestation_scope"] != _DAY_ATTESTATION_SCOPE:
        raise _err(reason)
    if values["attestation_version"] != _DAY_ATTESTATION_VERSION:
        raise _err(reason)
    if values["utc_day_policy"] != _DAY_UTC_DAY_POLICY:
        raise _err(reason)
    # D07 status / ready / reason-code coherence.
    if values["status"] is not PaperAttestedOperationalDayEvidenceStatus.READY:
        raise _err(reason)
    if values["ready"] is not True:
        raise _err(reason)
    if values["reason_codes"] != ():
        raise _err(reason)
    # D08 (trace) + D09 true flags.
    for name in _DAY_TRUE_FLAGS:
        if values[name] is not True:
            raise _err(reason)
    # D10 false flags.
    for name in _DAY_FALSE_FLAGS:
        if values[name] is not False:
            raise _err(reason)
    # D11 identity strings, carrying the D18 market_symbol trace.
    for name in _DAY_IDENTITY_FIELDS:
        if not _is_plain_text(values[name]):  # type: ignore[arg-type]
            raise _err(reason)
    # D12 day arithmetic.
    day_index = values["attested_utc_day_index"]
    if day_index <= 0:  # type: ignore[operator]
        raise _err(reason)
    if values["day_duration_ns"] != _NANOSECONDS_PER_DAY:
        raise _err(reason)
    if values["day_start_ns"] != day_index * _NANOSECONDS_PER_DAY:  # type: ignore[operator]
        raise _err(reason)
    if values["day_end_ns"] != (day_index + 1) * _NANOSECONDS_PER_DAY:  # type: ignore[operator]
        raise _err(reason)
    # D13 session counts.
    session_count = values["session_count"]
    minimum_sessions = values["minimum_sessions_per_day"]
    if session_count <= 0 or minimum_sessions <= 0:  # type: ignore[operator]
        raise _err(reason)
    if session_count < minimum_sessions:  # type: ignore[operator]
        raise _err(reason)
    # D14 session-indexed tuple lengths.
    for name in _DAY_SESSION_LIST_FIELDS:
        if len(values[name]) != session_count:  # type: ignore[arg-type]
            raise _err(reason)
    # D15 per-session content, ordering and non-overlap.
    day_start = values["day_start_ns"]
    day_end = values["day_end_ns"]
    started_list = values["session_started_at_ns_list"]
    stopped_list = values["session_stopped_at_ns_list"]
    duration_list = values["session_window_duration_ns_list"]
    verified_digests = values["verified_session_window_digests"]
    summary_digests = values["session_metrics_summary_digests"]
    event_counts = values["source_event_digest_counts"]
    previous_stopped = 0
    for index in range(session_count):  # type: ignore[arg-type]
        started = started_list[index]  # type: ignore[index]
        stopped = stopped_list[index]  # type: ignore[index]
        duration = duration_list[index]  # type: ignore[index]
        if started <= 0 or stopped <= 0 or duration <= 0:
            raise _err(reason)
        if stopped <= started:
            raise _err(reason)
        if duration != stopped - started:
            raise _err(reason)
        if started < day_start or stopped > day_end:  # type: ignore[operator]
            raise _err(reason)
        if started < previous_stopped:
            raise _err(reason)
        previous_stopped = stopped
        if not _is_hex64(verified_digests[index]):  # type: ignore[index]
            raise _err(reason)
        if not _is_hex64(summary_digests[index]):  # type: ignore[index]
            raise _err(reason)
        if event_counts[index] <= 0:  # type: ignore[index]
            raise _err(reason)
        for name in ("session_run_ids", "session_window_ids", "session_aggregate_ids"):
            if not _is_plain_text(values[name][index]):  # type: ignore[index]
                raise _err(reason)
    # D16 expected == verified element-wise, every expected entry exact lowercase hex64.
    expected_digests = values["expected_session_window_digests"]
    for index in range(session_count):  # type: ignore[arg-type]
        if not _is_hex64(expected_digests[index]):  # type: ignore[index]
            raise _err(reason)
        if expected_digests[index] != verified_digests[index]:  # type: ignore[index]
            raise _err(reason)
    # D17 within-day distinctness.
    if len(set(expected_digests)) != session_count:  # type: ignore[arg-type]
        raise _err(reason)
    if len(set(verified_digests)) != session_count:  # type: ignore[arg-type]
        raise _err(reason)
    if len(set(values["session_run_ids"])) != session_count:  # type: ignore[arg-type]
        raise _err(reason)
    # D19 carried self-digest shape, then equality against the FRESH recomputation. The carried value is a
    # consistency gate only and is never the trusted binding source.
    carried_digest = values["attested_operational_day_evidence_digest"]
    if not _is_hex64(carried_digest):  # type: ignore[arg-type]
        raise _err(reason)
    recomputed_digest = paper_attested_operational_day_evidence_digest(operational_day)
    if carried_digest != recomputed_digest:
        raise _err(reason)
    return recomputed_digest


# --- Complete binding re-proof from the four stored values -------------------------------------------------


def _derived_state(
    operational_day: object,
    request_raw: object,
    response_raw: object,
    long_term_public_key: object,
    reason: RoughtimeV19AttestedOperationalDayDigestBindingReason,
) -> tuple[str, bytes]:
    """Re-run the COMPLETE binding from the four stored values and return ``(day_digest, signed_root)``.

    Nothing here trusts a stored derivative or a prior verdict: the governed day is fully re-validated and its
    canonical self-digest is recomputed, the request is re-parsed through the merged public K3 parser, a FRESH
    exact aggregate is rebuilt from the three exact byte anchors, its ``signed_root`` is read through the
    validating public property, and the whole-value binding equality is re-checked -- on EVERY call, including
    during artifact self-validation. Only the two closed prerequisite domain errors are normalized; every other
    exception propagates unchanged.
    """
    day_digest = _validated_day_digest(operational_day, reason)
    for anchor in (request_raw, response_raw, long_term_public_key):
        # Exact built-in bytes only. This rejects a bytes SUBCLASS whose value compares equal but whose
        # behaviour (hash, equality, repr) is caller-controlled, which would otherwise reach stored state.
        if type(anchor) is not bytes:
            raise _err(reason)
    # The standalone K3 parse precedes the aggregate rebuild so this catch stays behaviourally reachable when
    # planted four-value state is reconstructed.
    try:
        canonical_request = parse_roughtime_v19_request(request_raw)  # type: ignore[arg-type]
    except RoughtimeV19RequestSemanticError:
        raise _err(reason) from None
    try:
        fresh_aggregate = RoughtimeV19RequestInSignedResponse(
            request_raw=request_raw,  # type: ignore[arg-type]
            response_raw=response_raw,  # type: ignore[arg-type]
            long_term_public_key=long_term_public_key,  # type: ignore[arg-type]
        )
        signed_root = fresh_aggregate.signed_root
    except RoughtimeV19RequestInSignedResponseError:
        raise _err(reason) from None
    # The ONE load-bearing equality: a single whole-value comparison over all 32 bytes of the freshly
    # recomputed day digest against the NONC the merged K3 parser located inside the re-proven request.
    if bytes.fromhex(day_digest) != canonical_request.nonce:
        raise _err(reason)
    return (day_digest, signed_root)


def _validate_binding_tuple(
    state: object,
    reason: RoughtimeV19AttestedOperationalDayDigestBindingReason,
) -> None:
    """Prove a candidate four-value state is exactly shaped and completely re-provable.

    Operates on a plain built-in ``tuple`` and never on the artifact object, so it cannot recurse through any
    public artifact surface.
    """
    if type(state) is not tuple:
        raise _err(reason)
    if len(state) != len(_ANCHOR_FIELD_NAMES):
        raise _err(reason)
    operational_day, request_raw, response_raw, long_term_public_key = state
    _derived_state(operational_day, request_raw, response_raw, long_term_public_key, reason)


# --- Sealed non-container public artifact with a closure-local identity registry ----------------------------


def _build_attested_operational_day_digest_binding_class() -> type:
    """Create the public artifact class over a closure-local, non-module-global registry.

    The four verified values must live somewhere a caller can neither read through the object nor reach as
    ordinary module state, so the registry is bound in this closure and no production registry hook is
    exported. Inheriting straight from :class:`object` and keeping no proof in the instance means there is no
    storage for an explicit unbound built-in base call to read, so that escape is structurally absent rather
    than blacklisted method by method.
    """
    # id(artifact) -> (weakref.ref(artifact, on_death), four-value state tuple).
    # Keyed by identity, never by artifact equality or hash, so registry lookup can never invoke the artifact's
    # own __eq__ (which would recurse into validation, which needs the registry). The artifact is explicitly
    # unhashable, so an id-keyed registry is also the only workable binding.
    registry: dict[int, tuple[ReferenceType, tuple]] = {}

    def register(artifact: object, state: tuple) -> None:
        """Bind verified values to one exact live object identity. Called only after full verification."""
        key = id(artifact)

        def forget(dead: ReferenceType, key: int = key) -> None:
            # Remove ONLY the entry this reference owns. CPython may reuse an id() after collection, so a
            # blind `del registry[key]` could delete a newer artifact's entry.
            current = registry.get(key)
            if current is not None and current[0] is dead:
                del registry[key]

        registry[key] = (weakref.ref(artifact, forget), state)

    def proven_state(artifact: object) -> tuple:
        """Return the complete six-value validated view, re-proving everything, or raise the closed reason.

        Five independent gates, in this order: exact public type; an identity-keyed registry entry exists; that
        entry's weak reference is still alive AND is exactly this object (so a stale or reused id can never
        authenticate a later object); the stored state is an exact four-value tuple; and the COMPLETE binding
        re-derives successfully from those four values. The returned view is the six public values in their
        exact declared order: the exact registered day reference, the freshly recomputed day digest, the three
        exact stored byte anchors, and the ``signed_root`` freshly read from the rebuilt aggregate.
        """
        if type(artifact) is not RoughtimeV19AttestedOperationalDayDigestBinding:
            raise _err(_ARTIFACT_INCONSISTENT)
        entry = registry.get(id(artifact))
        if entry is None:
            raise _err(_ARTIFACT_INCONSISTENT)
        reference, state = entry
        if reference() is not artifact:
            raise _err(_ARTIFACT_INCONSISTENT)
        if type(state) is not tuple or len(state) != len(_ANCHOR_FIELD_NAMES):
            raise _err(_ARTIFACT_INCONSISTENT)
        operational_day, request_raw, response_raw, long_term_public_key = state
        day_digest, signed_root = _derived_state(
            operational_day,
            request_raw,
            response_raw,
            long_term_public_key,
            _ARTIFACT_INCONSISTENT,
        )
        return (operational_day, day_digest, request_raw, response_raw, long_term_public_key, signed_root)

    class RoughtimeV19AttestedOperationalDayDigestBinding:
        """Proof that one exact governed day's current canonical content is the NONC of one signed request.

        Stores EXACTLY FOUR values -- the EXACT original governed-day reference and the three exact byte
        anchors ``request_raw``, ``response_raw`` and ``long_term_public_key``. The day self-digest and
        ``signed_root`` are deterministic derivatives of those four and are deliberately NOT stored: they are
        re-derived from scratch on every public consumption, so no stored derivative can ever drift from the
        source it claims to summarize.

        NOT A CONTAINER. It inherits directly from :class:`object` and stores NOTHING on the instance: there is
        no ``__dict__`` and the only slot is ``__weakref__`` (itself a read-only descriptor). Consequently
        ``setattr``, ``delattr``, ``object.__setattr__``, ``object.__delattr__`` and ``__dict__`` assignment all
        fail, no attribute can be added, and explicit unbound base calls are simply inapplicable to this type.

        Construction re-runs the COMPLETE binding BEFORE the object is registered, so a failed construction
        leaves no registry entry and no consumable object. Every public surface -- each of the six properties,
        ``repr``, ``str``, ``==``, ``!=``, ``bool``/truthiness and ``copy``/``deepcopy``/pickle reconstruction
        -- re-proves exact type, identity-bound registry membership, weak-reference liveness and the FULL
        binding before returning anything. A hollow
        ``object.__new__(RoughtimeV19AttestedOperationalDayDigestBinding)`` has no registry entry and fails
        closed on every one of them with exactly ``binding_artifact_inconsistent``; no ``KeyError``,
        ``LookupError``, ``ReferenceError``, ``AttributeError``, ``IndexError``, ``TypeError``, ``ValueError``
        or prerequisite exception escapes. No verdict and no derived value is cached.

        EXPLICITLY UNHASHABLE (``__hash__ = None``). The stored day is externally mutable through
        ``object.__setattr__``, so any value hash would be unstable across a container's lifetime; hashing is
        therefore removed rather than faked. Equality is validating IDENTITY-ONLY, so no mutable day content
        participates in a comparison result either: two distinct bindings over byte-identical content are valid
        but UNEQUAL, and a distinct binding can never become equal through content mutation.

        Deliberately NO sequence or container protocol: ``len``, iteration, indexing, membership, ``count``,
        ``index``, ordering, concatenation and repetition are all inapplicable. Truthiness is provided by an
        explicit validating ``__bool__`` and never by ``__len__``.

        MUTABLE-REFERENCE POLICY: ``operational_day`` returns the EXACT registered reference and never a copy
        or a reconstruction. The caller already owns it. Mutating it makes every supported surface raise the
        closed artifact reason (fail-closed, never forgeable); restoring the original content may revalidate.
        Only CURRENT CONTENT is proven -- nothing is frozen, copied or preserved.

        SEALED TYPE: closed to subclassing. Any attempt to derive from it raises a fixed repository-owned
        built-in ``TypeError`` at CLASS-DEFINITION time, before a subclass instance can exist.

        NON-CLAIM: existence of this artifact carries the structural binding claim in the module docstring and
        nothing else. THE INPUT DAY REMAINS OPERATOR-ATTESTED, NOT MACHINE-PROVEN. It does NOT assert the
        truthfulness of that attestation, a real calendar day, real session occurrence, original window
        existence, historical constructor origin, wall-clock truth, temporal ordering, not-before, not-after,
        timestamp origin, machine-time origin, ``NONC`` unpredictability, provider identity, key ownership,
        provenance, admission or revocation, deployed protocol compatibility, endpoint reachability, source
        admission or role, ``proof_verified``, quorum, sandwich completion, operational-day machine proof,
        >=30-day machine-proven spacing, PRDV4 Stage-4 completion, readiness, connector safety, live/orders/
        capital, or profitability or edge. There is deliberately no ``verified``, ``authentic``, ``provider``,
        ``time_valid``, ``ready``, ``quorum``, ``proof_verified`` or ``admitted`` field: the type itself is the
        claim, and its scope is exactly this docstring.
        """

        # Only __weakref__ -- required for the registry's lifecycle binding, and not writable, so it cannot be
        # repurposed as proof storage. No __dict__ and no data slot exist.
        __slots__ = ("__weakref__",)

        # Explicitly unsupported: a mutable stored day makes any value hash unstable, and fail-closed
        # revalidation is NOT hash stability. hash(), set insertion and dict-key insertion all raise the exact
        # built-in TypeError, identically before, during and after any day mutation.
        __hash__ = None

        def __new__(
            cls,
            *,
            operational_day: PaperAttestedOperationalDayEvidence,
            request_raw: bytes,
            response_raw: bytes,
            long_term_public_key: bytes,
        ) -> RoughtimeV19AttestedOperationalDayDigestBinding:
            state = (operational_day, request_raw, response_raw, long_term_public_key)
            # Verify FIRST, then create and register: a rejected state must leave no object and no entry.
            _validate_binding_tuple(state, _ARTIFACT_INCONSISTENT)
            artifact = object.__new__(cls)
            register(artifact, state)
            return artifact

        def __init_subclass__(cls, **kwargs: object) -> None:
            # Fires when a subclass is DEFINED, before it can be instantiated and therefore before any
            # overriding lifecycle method of that subclass can execute. Deterministic, no caller text.
            raise TypeError(_SEALED_ARTIFACT_MESSAGE)

        @property
        def operational_day(self) -> PaperAttestedOperationalDayEvidence:
            return proven_state(self)[0]

        @property
        def attested_operational_day_evidence_digest(self) -> str:
            return proven_state(self)[1]

        @property
        def request_raw(self) -> bytes:
            return proven_state(self)[2]

        @property
        def response_raw(self) -> bytes:
            return proven_state(self)[3]

        @property
        def long_term_public_key(self) -> bytes:
            return proven_state(self)[4]

        @property
        def signed_root(self) -> bytes:
            return proven_state(self)[5]

        def __repr__(self) -> str:
            """Deterministic, bounded, ASCII-only, fully redacted one-line representation.

            Performs EXACTLY ONE complete binding reproof and renders only that single proven view; the six
            public properties are never consumed one by one. The governed-day slot is a STATIC literal, so no
            caller-controlled string and no large integer can enter the output; the three byte anchors are
            reduced to their decimal lengths. No raw request, response or key bytes and no hex, base64 or other
            encoding of them is ever rendered, and no fingerprint is computed for redaction.
            """
            view = proven_state(self)
            operational_day, day_digest, request_raw, response_raw, long_term_public_key, signed_root = view
            return (
                "RoughtimeV19AttestedOperationalDayDigestBinding("
                f"operational_day=<{_DAY_TYPE_NAME} READY fields={len(_DAY_FIELD_NAMES)}>, "
                f"attested_operational_day_evidence_digest=<hex64:{day_digest}>, "
                f"request_raw=<bytes len={len(request_raw)} redacted>, "
                f"response_raw=<bytes len={len(response_raw)} redacted>, "
                f"long_term_public_key=<bytes len={len(long_term_public_key)} redacted>, "
                f"signed_root=<bytes len={len(signed_root)} hex={signed_root.hex()}>"
                ")"
            )

        def __str__(self) -> str:
            """Exactly the ``repr`` contract, with its own independent single reproof and no cached rendering."""
            view = proven_state(self)
            operational_day, day_digest, request_raw, response_raw, long_term_public_key, signed_root = view
            return (
                "RoughtimeV19AttestedOperationalDayDigestBinding("
                f"operational_day=<{_DAY_TYPE_NAME} READY fields={len(_DAY_FIELD_NAMES)}>, "
                f"attested_operational_day_evidence_digest=<hex64:{day_digest}>, "
                f"request_raw=<bytes len={len(request_raw)} redacted>, "
                f"response_raw=<bytes len={len(response_raw)} redacted>, "
                f"long_term_public_key=<bytes len={len(long_term_public_key)} redacted>, "
                f"signed_root=<bytes len={len(signed_root)} hex={signed_root.hex()}>"
                ")"
            )

        def __bool__(self) -> bool:
            """Truthiness is a proof-consumption surface, so ``if binding:`` must revalidate.

            Without an explicit implementation, ``object``'s default truthiness would report a hollow
            ``object.__new__`` instance as ``True`` without touching the registry or re-proving the binding.
            Returns exactly the built-in ``True`` for a genuine artifact and raises the closed artifact reason
            otherwise; it never returns ``False``, because a proof that cannot be re-proven is a fail-closed
            error and not a falsey value. Implemented through ``__bool__`` and deliberately NOT through
            ``__len__``, so this type still exposes no container protocol.
            """
            proven_state(self)
            return True

        def __eq__(self, other: object) -> bool:
            """Validating IDENTITY-ONLY equality.

            Self is completely re-proven first. A non-exact ``other`` returns the exact built-in ``False``
            without being read at all, so a hostile object can never execute anything here. A distinct exact
            binding is also completely re-proven and still returns ``False``: two bindings over byte-identical
            content are deliberately UNEQUAL, because the stored day is externally mutable and no mutable
            content may participate in a comparison result.
            """
            proven_state(self)
            if type(other) is not RoughtimeV19AttestedOperationalDayDigestBinding:
                return False
            if self is other:
                return True
            proven_state(other)
            return False

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __reduce__(self) -> tuple:
            """Route ``copy``/``deepcopy``/pickle through the validating four-value constructor.

            Returns only the four plain stored values, never a derived value and never anything from the
            registry, and reconstruction runs the complete binding again -- so a hand-crafted pickle cannot
            install proof state directly. Shallow ``copy.copy`` therefore keeps the EXACT same day reference,
            while ``deepcopy`` and pickle carry a distinct exact-type content-equivalent day; every rebuilt
            binding is a new identity, unequal to its source, and equally unhashable.
            """
            return (
                _rebuild_attested_operational_day_digest_binding,
                (proven_state(self)[:1] + proven_state(self)[2:5],),
            )

    RoughtimeV19AttestedOperationalDayDigestBinding.__qualname__ = "RoughtimeV19AttestedOperationalDayDigestBinding"
    RoughtimeV19AttestedOperationalDayDigestBinding.__module__ = __name__
    return RoughtimeV19AttestedOperationalDayDigestBinding


RoughtimeV19AttestedOperationalDayDigestBinding = _build_attested_operational_day_digest_binding_class()


def _rebuild_attested_operational_day_digest_binding(
    state: object,
) -> RoughtimeV19AttestedOperationalDayDigestBinding:
    """Reconstruct an artifact from copy/deepcopy/pickle state by re-running the COMPLETE binding.

    Every argument shape defect and every value defect normalizes to the artifact reason; the validating
    keyword constructor is the only construction path, so no registry entry can exist before success.
    """
    if type(state) is not tuple or len(state) != len(_ANCHOR_FIELD_NAMES):
        raise _err(_ARTIFACT_INCONSISTENT)
    return RoughtimeV19AttestedOperationalDayDigestBinding(
        operational_day=state[0],
        request_raw=state[1],
        response_raw=state[2],
        long_term_public_key=state[3],
    )


def verify_roughtime_v19_attested_operational_day_digest_binding(
    operational_day: PaperAttestedOperationalDayEvidence,
    request_in_signed_response: RoughtimeV19RequestInSignedResponse,
) -> RoughtimeV19AttestedOperationalDayDigestBinding:
    """Bind an exact governed operational-day artifact to an exact authenticated request-in-signed-response.

    Accepts the EXACT merged public types only; both exact-type gates run BEFORE any attribute, dataclass field
    or aggregate surface of either input is touched, so no hostile override can execute. The governed day is
    then completely re-validated on its CURRENT CONTENT and its canonical self-digest is recomputed through the
    merged public digest function; the aggregate is re-proven by snapshotting exactly three validating public
    anchors and rebuilding a FRESH exact aggregate from those snapshots, which transitively re-proves K4, the
    ``CERT`` chain and the outer ``SREP`` signature. The caller's ``signed_root`` is never read.

    Verifies no new signature and computes no new hash. Performs no version relation, no provider or
    key-provenance binding, no root-key admission, no clock read, no quorum evaluation, and causes no readiness
    or connector transition.
    """
    # P1/P2 exact-type gates, both complete before anything of either input is touched.
    if type(operational_day) is not PaperAttestedOperationalDayEvidence:
        raise _err(RoughtimeV19AttestedOperationalDayDigestBindingReason.WRONG_INPUT_TYPE)
    if type(request_in_signed_response) is not RoughtimeV19RequestInSignedResponse:
        raise _err(RoughtimeV19AttestedOperationalDayDigestBindingReason.WRONG_INPUT_TYPE)
    # P3 governed-day stage. Catches nothing: D04 proves the public digest call cannot raise.
    day_digest = _validated_day_digest(
        operational_day,
        RoughtimeV19AttestedOperationalDayDigestBindingReason.GOVERNED_DAY_ARTIFACT_INCONSISTENT,
    )
    aggregate_inconsistent = (
        RoughtimeV19AttestedOperationalDayDigestBindingReason.REQUEST_IN_SIGNED_RESPONSE_INCONSISTENT
    )
    # P4 caller snapshot: exactly three validating public property reads, each of which re-runs the aggregate's
    # own complete derivation. The caller's signed_root is deliberately NOT read.
    try:
        snapshot_request_raw = request_in_signed_response.request_raw
        snapshot_response_raw = request_in_signed_response.response_raw
        snapshot_long_term_public_key = request_in_signed_response.long_term_public_key
    except RoughtimeV19RequestInSignedResponseError:
        raise _err(aggregate_inconsistent) from None
    # P5 exact-bytes gates on the three snapshots, the standalone K3 parse, then the fresh reconstruction.
    for anchor in (snapshot_request_raw, snapshot_response_raw, snapshot_long_term_public_key):
        if type(anchor) is not bytes:
            raise _err(aggregate_inconsistent)
    try:
        canonical_request = parse_roughtime_v19_request(snapshot_request_raw)
    except RoughtimeV19RequestSemanticError:
        raise _err(aggregate_inconsistent) from None
    try:
        fresh_aggregate = RoughtimeV19RequestInSignedResponse(
            request_raw=snapshot_request_raw,
            response_raw=snapshot_response_raw,
            long_term_public_key=snapshot_long_term_public_key,
        )
        fresh_signed_root = fresh_aggregate.signed_root
    except RoughtimeV19RequestInSignedResponseError:
        raise _err(aggregate_inconsistent) from None
    if type(fresh_signed_root) is not bytes:
        raise _err(aggregate_inconsistent)
    # P6 the one load-bearing whole-value equality over all 32 bytes.
    if bytes.fromhex(day_digest) != canonical_request.nonce:
        raise _err(RoughtimeV19AttestedOperationalDayDigestBindingReason.DAY_DIGEST_REQUEST_NONCE_MISMATCH)
    return RoughtimeV19AttestedOperationalDayDigestBinding(
        operational_day=operational_day,
        request_raw=snapshot_request_raw,
        response_raw=snapshot_response_raw,
        long_term_public_key=snapshot_long_term_public_key,
    )


__all__ = [
    "ROUGHTIME_V19_ATTESTED_OPERATIONAL_DAY_DIGEST_BINDING_PROFILE_ID",
    "RoughtimeV19AttestedOperationalDayDigestBinding",
    "RoughtimeV19AttestedOperationalDayDigestBindingError",
    "RoughtimeV19AttestedOperationalDayDigestBindingReason",
    "verify_roughtime_v19_attested_operational_day_digest_binding",
]
