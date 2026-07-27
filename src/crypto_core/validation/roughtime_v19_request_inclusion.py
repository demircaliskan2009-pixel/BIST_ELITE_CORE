"""Roughtime draft-19 bounded REQUEST-INCLUSION Merkle verifier (internal MT-4 prerequisite K4) — provider-independent.

This module layers a pure, deterministic CRYPTOGRAPHIC-HASH view over the merged K2 response-semantic decoder
(:mod:`crypto_core.validation.roughtime_v19_response_semantics`) and the merged K3 request-semantic decoder
(:mod:`crypto_core.validation.roughtime_v19_request_semantics`). K2 and K3 prove wire semantics and perform no
cryptography; K4 answers exactly one closed question: does the exact complete request packet hash, through the
canonical ``PATH``/``INDX`` supplied by the exact complete response packet, to the exact ``ROOT`` declared inside
that response's ``SREP``?

Bounded profile (honest scope): this verifier implements ONE governance-selected, versioned profile, identified by
:data:`ROUGHTIME_V19_REQUEST_INCLUSION_PROFILE_ID`
(``"roughtime-v19-request-inclusion-bounded-k4.v1"``). It inherits the K1 structural bounds and the K2/K3 semantic
bounds unchanged and adds NO new byte-size ceiling of its own.

Normative construction (the only hashing this module performs)::

    H(x)  = sha512(x).digest()[:32]           # SHA-512 truncated to its FIRST 32 bytes, at every level
    leaf  = H(b"\\x00" + request_packet)      # over the COMPLETE packet, including the ROUGHTIM header
    node  = H(b"\\x01" + left + right)        # domain-separated internal node

``INDX`` bits are consumed LEAST-SIGNIFICANT-FIRST, one bit per ``PATH`` depth in tuple order. At depth ``d`` with
``bit = (index >> d) & 1``: bit ``0`` means the running accumulator is the LEFT child and the sibling is the right;
bit ``1`` means the sibling is the LEFT child and the accumulator is the right. Every ``INDX`` bit at or above the
path length is unused and MUST be zero, checked BEFORE the root comparison so an over-wide index can never be
reported as a mere root mismatch. An empty ``PATH`` is valid: the fold runs zero times, the root equals the leaf,
and the index must therefore be exactly zero.

Trust boundary: K4 consumes artifacts it did not build. It never trusts dataclass identity, frozen status, or the
claim that a constructor ever ran. :func:`verify_roughtime_v19_request_inclusion` first requires both inputs to be
the EXACT merged public types (``type(x) is C``, never ``isinstance``), which alone rejects every subclass and so
prevents any hostile ``__getattribute__``, ``__post_init__`` or ``__new__`` override from executing. It then reads
the complete declared state of each input through ``getattr`` with a private sentinel, re-invokes the exact base
K3 and K2 constructors on that complete state so the merged validators re-prove it recursively (including nested
``SREP``, ``CERT`` and ``DELE``), and finally re-parses both ``raw`` byte strings through the merged public
parsers. ONLY those freshly parsed canonical artifacts feed the Merkle computation, so a caller-declared field can
never influence the result even if it somehow survived revalidation. Every K2/K3 failure and every state defect is
normalized to exactly one closed member of :class:`RoughtimeV19RequestInclusionReason`, so no raw
``RoughtimeV19ResponseSemanticError``/``RoughtimeV19RequestSemanticError``/``AttributeError``/``TypeError`` is ever
leaked and no ``BaseException`` is caught.

Scope boundary — what a successful artifact does NOT and never will claim:

* it makes NO request/response correlation claim: nonces are never compared, no nonce field or nonce reason
  exists, and a differing outer ``NONC`` never rejects a mathematically valid inclusion. Outer ``NONC`` lies
  outside the signed ``SREP`` bytes, so comparing it would be an unsigned correlation masquerading as a binding;
* it makes NO version-compatibility claim: the response's selected version is never related to the request's
  offered versions, no version field or version reason exists, and an unoffered selected version never rejects a
  mathematically valid inclusion;
* it does NOT prove the ``ROOT`` is authentic — authenticity lives entirely in the ``SREP`` signature, which this
  module does not verify;
* it verifies NO ``CERT`` and NO ``SREP`` signature, hashes no ``SRV`` identifier, and performs no Ed25519 or any
  other public-key operation;
* it binds NO provider, endpoint, long-term key or delegated key, and infers NO deployed-protocol provenance;
* it proves NO time: no clock is read, and ``MIDP``/``MINT``/``MAXT``/``RADI`` are never touched;
* it asserts NO nonce entropy, NO quorum, and builds NO ``MachineTimeAnchorEvidence``, no aggregate verification
  result and no machine-time provenance claim;
* it has NO readiness or connector effect and triggers NO readiness or connector transition;
* it performs NO network, filesystem, environment, randomness, subprocess or threading access, and makes no
  order, capital, edge or profitability claim of any kind.

A successful :class:`RoughtimeV19RequestInclusion` therefore proves exactly this and nothing further: the exact
complete request packet hashes through the canonical path and index to the exact root declared by the exact
complete response packet.

Versioned specification: https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha512

from crypto_core.validation.roughtime_v19_request_semantics import (
    RoughtimeV19RequestSemanticError,
    RoughtimeV19RequestSemantics,
    parse_roughtime_v19_request,
)
from crypto_core.validation.roughtime_v19_response_semantics import (
    RoughtimeV19ResponseSemanticError,
    RoughtimeV19ResponseSemantics,
    parse_roughtime_v19_response,
)

# --- Inclusion profile (governance-selected, versioned; inherits K1/K2/K3 bounds unchanged) ----------------
ROUGHTIME_V19_REQUEST_INCLUSION_PROFILE_ID = "roughtime-v19-request-inclusion-bounded-k4.v1"

# --- Normative constants ----------------------------------------------------------------------------------
_LEAF_PREFIX = b"\x00"  # domain separation for a leaf; never reused for an internal node
_INTERNAL_PREFIX = b"\x01"  # domain separation for an internal node; never reused for a leaf
_DIGEST_BYTES = 32  # SHA-512 truncated to its FIRST 32 bytes at every level

# Sentinel for safe attribute reads: distinguishes "attribute absent" from any legitimate value, including None.
_MISSING = object()

# Complete declared field inventories of the merged input artifacts, in their exact declaration order.
_REQUEST_FIELD_NAMES = (
    "versions",
    "nonce",
    "message_type",
    "server_key_id",
    "padding",
    "extensions",
    "raw",
)
_RESPONSE_FIELD_NAMES = (
    "signature",
    "nonce",
    "message_type",
    "path",
    "index",
    "signed_response",
    "certificate",
    "extensions",
    "raw",
)

# The COMPLETE and EXCLUSIVE instance-namespace inventory of this module's own output artifact, in exact
# declaration order. A valid artifact's __dict__ must contain exactly these keys and nothing else — see
# _validate_inclusion_state. Private on purpose: it is an internal enforcement inventory, never public API.
_INCLUSION_FIELD_NAMES = (
    "request_raw",
    "response_raw",
    "leaf",
    "computed_root",
    "declared_root",
    "path_length",
    "index",
)

_ERROR_REASON_TYPE_MESSAGE = "RoughtimeV19RequestInclusionError requires a RoughtimeV19RequestInclusionReason member"
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19RequestInclusionError is immutable after construction"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})
_SEALED_ARTIFACT_MESSAGE = "RoughtimeV19RequestInclusion is a sealed artifact type and cannot be subclassed"


class RoughtimeV19RequestInclusionReason(str, Enum):
    """Closed inclusion-failure inventory: exactly five members, evaluated in the pinned precedence below.

    The first four are public verifier outcomes; the fifth is reserved for direct output-artifact construction.
    There is deliberately NO nonce reason, NO version reason, NO ``PATH_INVALID`` reason (K2 already proves path
    shape structurally and K4 adds no second, contradictory rule) and NO provider/readiness reason.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    INPUT_ARTIFACT_INCONSISTENT = "input_artifact_inconsistent"
    INDEX_UNUSED_BITS_SET = "index_unused_bits_set"
    ROOT_MISMATCH = "root_mismatch"
    ARTIFACT_INCLUSION_INCONSISTENT = "artifact_inclusion_inconsistent"


class RoughtimeV19RequestInclusionError(RuntimeError):
    """Raised for every inclusion failure, carrying exactly one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19RequestInclusionReason` member. Any other argument
    raises a plain built-in ``TypeError`` before any attribute of that argument (in particular ``.value``) is
    read, so a hostile ``.value`` property or Enum-like substitute can never run. Once constructed the error is
    immutable: ``reason`` is read-only, its backing storage cannot be substituted, ``args`` cannot be replaced,
    and ``str(error)`` is always exactly ``reason.value``. No caller-provided message is ever accepted.
    """

    def __init__(self, reason: RoughtimeV19RequestInclusionReason) -> None:
        if type(reason) is not RoughtimeV19RequestInclusionReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19RequestInclusionReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ERROR_LOCKED_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        super().__delattr__(name)


def _err(reason: RoughtimeV19RequestInclusionReason) -> RoughtimeV19RequestInclusionError:
    return RoughtimeV19RequestInclusionError(reason)


# --- Normative Merkle primitives (the only hashing in this module) ----------------------------------------


def _digest(payload: bytes) -> bytes:
    """Return ``sha512(payload)`` truncated to its FIRST 32 bytes. Never the last 32, never folded, never XORed."""
    return sha512(payload).digest()[:_DIGEST_BYTES]


def _leaf_digest(request_packet: bytes) -> bytes:
    """Return the Merkle leaf over the COMPLETE request packet, including the ``ROUGHTIM`` header."""
    return _digest(_LEAF_PREFIX + request_packet)


def _fold_root(leaf: bytes, path: tuple[bytes, ...], index: int) -> bytes:
    """Fold ``leaf`` up through ``path`` in tuple order, consuming ``index`` bits LEAST-SIGNIFICANT-FIRST.

    At depth ``d`` a zero bit places the running accumulator on the LEFT and the sibling on the right; a one bit
    places the sibling on the LEFT and the accumulator on the right. An empty ``path`` folds zero times, so the
    returned root is the leaf itself. Unused high bits are NOT inspected here — the caller checks them first so
    the precedence between ``INDEX_UNUSED_BITS_SET`` and ``ROOT_MISMATCH`` is pinned.
    """
    current = leaf
    for depth, sibling in enumerate(path):
        if (index >> depth) & 1 == 0:
            current = _digest(_INTERNAL_PREFIX + current + sibling)
        else:
            current = _digest(_INTERNAL_PREFIX + sibling + current)
    return current


# --- Safe cross-boundary state reads ----------------------------------------------------------------------


def _declared_state(
    obj: object,
    field_names: tuple[str, ...],
    reason: RoughtimeV19RequestInclusionReason,
) -> dict[str, object]:
    """Read every named field of an EXACT-type input through ``getattr`` + sentinel, never trusting presence.

    An object built through ``object.__new__`` without its initializer is missing some or all of its declared
    fields; returning ``reason`` for a missing field means such an object is rejected with a closed reason rather
    than leaking ``AttributeError``. Reaching here already proves the exact base type, so attribute lookup cannot
    dispatch a caller-defined ``__getattribute__``.
    """
    state: dict[str, object] = {}
    for name in field_names:
        value = getattr(obj, name, _MISSING)
        if value is _MISSING:
            raise _err(reason)
        state[name] = value
    return state


def _validate_inclusion_state(obj: object, reason: RoughtimeV19RequestInclusionReason) -> None:
    """Prove an exact-type inclusion artifact's COMPLETE declared state equals an independent recomputation.

    Defence in depth: the exact-type gate rejects a foreign object handed to an unbound
    ``RoughtimeV19RequestInclusion.__post_init__`` call. The exact INSTANCE NAMESPACE is then proven to hold
    exactly the seven declared field names and nothing else, so an artifact can never smuggle extra state — an
    overclaim such as ``root_authentic = True``, a private cache, or a foreign key — past validation while
    remaining equal to and hash-identical with a clean proof. Only afterwards is every field read safely,
    exact-typed (which rejects ``bytes``/``int`` subclasses and ``bool``), length-checked, and re-derived from
    the carried ``request_raw``/``response_raw`` alone. Every defect normalizes to ``reason``.

    Namespace gate ordering is load-bearing and each step makes the next one safe. ``__dict__`` accepts a dict
    SUBCLASS through ``object.__setattr__``, so the exact-``dict`` check must come first or a subclass could lie
    about its length, iteration or equality. A key whose ``__eq__`` is hostile survives insertion, so every key
    must be proven an exact built-in ``str`` BEFORE any set or equality comparison can invoke it. Only then is
    the key inventory compared.
    """
    if type(obj) is not RoughtimeV19RequestInclusion:
        raise _err(reason)
    namespace = getattr(obj, "__dict__", _MISSING)
    if namespace is _MISSING or type(namespace) is not dict:
        raise _err(reason)
    if len(namespace) != len(_INCLUSION_FIELD_NAMES):
        raise _err(reason)
    for key in namespace:
        if type(key) is not str:
            raise _err(reason)
    if set(namespace) != set(_INCLUSION_FIELD_NAMES):
        raise _err(reason)
    request_raw = getattr(obj, "request_raw", _MISSING)
    response_raw = getattr(obj, "response_raw", _MISSING)
    leaf = getattr(obj, "leaf", _MISSING)
    computed_root = getattr(obj, "computed_root", _MISSING)
    declared_root = getattr(obj, "declared_root", _MISSING)
    path_length = getattr(obj, "path_length", _MISSING)
    index = getattr(obj, "index", _MISSING)
    for value in (request_raw, response_raw, leaf, computed_root, declared_root, path_length, index):
        if value is _MISSING:
            raise _err(reason)
    for value in (request_raw, response_raw, leaf, computed_root, declared_root):
        if type(value) is not bytes:
            raise _err(reason)
    if type(path_length) is not int or type(index) is not int:
        raise _err(reason)
    for value in (leaf, computed_root, declared_root):
        if len(value) != _DIGEST_BYTES:
            raise _err(reason)
    try:
        canonical_request = parse_roughtime_v19_request(request_raw)
    except RoughtimeV19RequestSemanticError:
        raise _err(reason) from None
    try:
        canonical_response = parse_roughtime_v19_response(response_raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(reason) from None
    expected_path = canonical_response.path
    expected_index = canonical_response.index
    expected_declared_root = canonical_response.signed_response.root
    if path_length != len(expected_path) or index != expected_index:
        raise _err(reason)
    if declared_root != expected_declared_root:
        raise _err(reason)
    expected_leaf = _leaf_digest(canonical_request.raw)
    if leaf != expected_leaf:
        raise _err(reason)
    if index >> len(expected_path) != 0:
        raise _err(reason)
    if computed_root != _fold_root(expected_leaf, expected_path, expected_index):
        raise _err(reason)
    if computed_root != declared_root:
        raise _err(reason)


# --- Immutable, self-validating public artifact -----------------------------------------------------------


@dataclass(frozen=True)
class RoughtimeV19RequestInclusion:
    """Proof that one exact request packet hashes to one exact response-declared ``ROOT``. Nothing more.

    Carries the exact complete ``request_raw`` and ``response_raw`` packet bytes, the exact 32-byte ``leaf``, the
    exact 32-byte ``computed_root`` and the exact 32-byte ``declared_root`` (equal by construction), the
    ``path_length`` actually folded and the exact ``index`` whose low ``path_length`` bits were consumed. Frozen
    and hashable.

    Direct construction re-parses ``request_raw`` and ``response_raw`` and independently recomputes every field;
    any mismatch, missing or incomplete state, non-exact type (including a ``bytes``/``int`` subclass or ``bool``),
    wrong digest length, unused index bit, root mismatch, malformed raw, or object built without its initializer
    raises ``artifact_inclusion_inconsistent`` — never a leaked ``AttributeError`` and never an underlying K2/K3
    semantic error.

    EXACT STATE: the instance namespace must contain exactly these seven keys and nothing else. Extra state of
    any form — an overclaim such as ``root_authentic = True``, an innocuous extra public attribute, a private
    cache, or a foreign non-string key — raises ``artifact_inclusion_inconsistent``. This boundary is enforced
    because a frozen dataclass compares and hashes only its declared fields, so without it an artifact carrying
    smuggled state would validate, and would remain equal to and hash-identical with a clean proof, while a
    downstream reader could still observe the smuggled attribute.

    SEALED TYPE: closed to subclassing. Any attempt to derive from it — an ordinary subclass, one overriding
    ``__post_init__``/``__getattribute__``/``__new__``, or a dynamically created ``type(...)`` subclass — raises a
    fixed repository-owned built-in ``TypeError`` at CLASS-DEFINITION time, before any subclass instance can exist
    and therefore before any overriding method body can run. Definition-time sealing is required because an
    exact-type check inside ``__post_init__`` alone is bypassable: a subclass that overrides ``__post_init__``
    simply never invokes it. The seal raises a plain built-in ``TypeError`` rather than a semantic reason, because
    a subclass definition is a programming error, not a wire-semantic outcome; the closed five-member reason
    inventory is unchanged.

    NON-CLAIM: existence of this artifact proves inclusion only. It does NOT prove that this response answers this
    request (no nonce is compared), that the versions are compatible (no version is related), that the ``ROOT`` is
    authentic, that any signature or certificate is valid, that any provider or key is identified, that any time
    is truthful, or that any readiness, connector, quorum, machine-time-provenance, order, capital or edge
    condition holds.
    """

    request_raw: bytes
    response_raw: bytes
    leaf: bytes
    computed_root: bytes
    declared_root: bytes
    path_length: int
    index: int

    def __init_subclass__(cls, **kwargs: object) -> None:
        # Fires when a subclass is DEFINED, before it can be instantiated and before any overridden lifecycle
        # method of that subclass can execute. Deterministic, no caller-supplied text.
        raise TypeError(_SEALED_ARTIFACT_MESSAGE)

    def __post_init__(self) -> None:
        _validate_inclusion_state(self, RoughtimeV19RequestInclusionReason.ARTIFACT_INCLUSION_INCONSISTENT)


def verify_roughtime_v19_request_inclusion(
    request: RoughtimeV19RequestSemantics,
    response: RoughtimeV19ResponseSemantics,
) -> RoughtimeV19RequestInclusion:
    """Prove that ``request``'s exact complete packet hashes to the exact ``ROOT`` declared by ``response``.

    Accepts the EXACT merged K3 and K2 artifact types only; a subclass is rejected by ``wrong_input_type`` before
    any attribute is read, so no hostile override can execute. Both inputs are then completely revalidated across
    the trust boundary — full declared state re-proven by the exact base constructors, then both ``raw`` packets
    re-parsed through the merged public parsers — and ONLY the freshly parsed canonical artifacts feed the Merkle
    computation. Unused ``INDX`` bits are rejected before the root comparison.

    Performs no nonce comparison, no version relation, no signature or certificate verification, no ``SRV``
    hashing, no provider or key binding, no clock read, and causes no readiness or connector transition. Returns
    an immutable :class:`RoughtimeV19RequestInclusion` whose existence carries the inclusion claim and no other.
    """
    if type(request) is not RoughtimeV19RequestSemantics:
        raise _err(RoughtimeV19RequestInclusionReason.WRONG_INPUT_TYPE)
    if type(response) is not RoughtimeV19ResponseSemantics:
        raise _err(RoughtimeV19RequestInclusionReason.WRONG_INPUT_TYPE)
    inconsistent = RoughtimeV19RequestInclusionReason.INPUT_ARTIFACT_INCONSISTENT
    request_state = _declared_state(request, _REQUEST_FIELD_NAMES, inconsistent)
    response_state = _declared_state(response, _RESPONSE_FIELD_NAMES, inconsistent)
    request_raw = request_state["raw"]
    response_raw = response_state["raw"]
    if type(request_raw) is not bytes or type(response_raw) is not bytes:
        raise _err(inconsistent)
    # Re-invoke the exact base constructors on the caller's COMPLETE declared state so the merged K3 and K2
    # validators re-prove it recursively (K2 binds SREP, CERT and DELE). This catches a mutated field the Merkle
    # computation never reads, which the canonical re-parse below could not detect on its own.
    try:
        RoughtimeV19RequestSemantics(**request_state)  # type: ignore[arg-type]
    except RoughtimeV19RequestSemanticError:
        raise _err(inconsistent) from None
    try:
        RoughtimeV19ResponseSemantics(**response_state)  # type: ignore[arg-type]
    except RoughtimeV19ResponseSemanticError:
        raise _err(inconsistent) from None
    # Canonical re-parse. Everything below uses ONLY these artifacts, never the caller's declared fields.
    try:
        canonical_request = parse_roughtime_v19_request(request_raw)
    except RoughtimeV19RequestSemanticError:
        raise _err(inconsistent) from None
    try:
        canonical_response = parse_roughtime_v19_response(response_raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(inconsistent) from None
    path = canonical_response.path
    index = canonical_response.index
    if index >> len(path) != 0:
        raise _err(RoughtimeV19RequestInclusionReason.INDEX_UNUSED_BITS_SET)
    leaf = _leaf_digest(canonical_request.raw)
    computed_root = _fold_root(leaf, path, index)
    declared_root = canonical_response.signed_response.root
    if computed_root != declared_root:
        raise _err(RoughtimeV19RequestInclusionReason.ROOT_MISMATCH)
    return RoughtimeV19RequestInclusion(
        request_raw=canonical_request.raw,
        response_raw=canonical_response.raw,
        leaf=leaf,
        computed_root=computed_root,
        declared_root=declared_root,
        path_length=len(path),
        index=index,
    )


__all__ = [
    "ROUGHTIME_V19_REQUEST_INCLUSION_PROFILE_ID",
    "RoughtimeV19RequestInclusion",
    "RoughtimeV19RequestInclusionError",
    "RoughtimeV19RequestInclusionReason",
    "verify_roughtime_v19_request_inclusion",
]
