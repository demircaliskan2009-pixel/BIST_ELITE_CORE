"""Roughtime draft-19 bounded REQUEST-IN-SIGNED-RESPONSE composition (internal MT-4 aggregate K4+SREP).

This module composes two ALREADY MERGED proof layers and adds no cryptographic primitive of its own. K4
(:mod:`crypto_core.validation.roughtime_v19_request_inclusion`) proves that an exact complete request packet
folds through an exact response's canonical ``PATH``/``INDX`` to the ``ROOT`` that response declares inside its
``SREP``; the merged SREP verifier
(:mod:`crypto_core.validation.roughtime_v19_signed_response_verification`) proves that the outer response
``SIG`` validates under the delegated key certified by a ``CERT`` delegation signature, itself validated under
an exact caller-supplied long-term key. Neither layer alone connects the request to the signature: K4 never
proves the ``ROOT`` is signed, and SREP never proves any particular request is inside that ``ROOT``. This
module answers exactly one further closed question: are those two proofs about the SAME exact response bytes
and the SAME exact signed root?

Bounded profile (honest scope): ONE governance-selected, versioned profile, identified by
:data:`ROUGHTIME_V19_REQUEST_IN_SIGNED_RESPONSE_PROFILE_ID`
(``"roughtime-v19-request-in-signed-response-bounded-k4-srep.v1"``). It inherits the K1 structural bounds, the
K2/K3 semantic bounds, the K4 Merkle bounds and the K5/SREP signature bounds unchanged, and adds no new
byte-size ceiling, no new hash and no new public-key operation.

A successful artifact proves EXACTLY this one sentence and nothing further:

    The exact complete request packet is proven by K4 to fold through the exact response ``PATH``/``INDX`` to
    the same ``ROOT`` carried by that response's signed ``SREP``, whose outer signature and ``CERT`` delegation
    chain validate relative only to the exact caller-supplied long-term public key.

"Relative only to the caller-supplied long-term public key" is load-bearing. That key is accepted, never
admitted: supplying an unauthenticated key and obtaining an artifact proves internal self-consistency of the
chain, never that the key belongs to anyone.

It proves NOTHING about: provider identity; provider ownership of the long-term key; key provenance, admission
or revocation; ``NONC`` correlation between the request and the response (the outer ``NONC`` lies outside the
signed ``SREP`` bytes, so comparing it would be an unsigned correlation masquerading as a binding, and this
module deliberately never compares it); selected- or deployed-protocol version compatibility (an unoffered
selected version never rejects a mathematically valid composition); truthful, authenticated or UTC time;
machine-time provenance; quorum or sandwich completion; readiness; connector safety; reachability; operational
approval; or any private/live/order/capital capability.

Composition trust boundary. The public verifier consumes two artifacts it did not build and trusts neither.
Both inputs must be the EXACT merged public types (``type(x) is C``, never ``isinstance``), checked BEFORE any
attribute of either input is read, so a hostile ``__getattribute__``/``__post_init__``/``__new__`` override can
never execute. The K4 input is then re-proven by invoking the exact base ``__post_init__`` on it and rebuilding
a fresh exact K4 from its complete snapshotted state, which catches a mutated carried field that a raw-only
reparse would miss. The SREP input is re-proven by reading all ten public properties — each of which re-runs
SREP's own complete revalidation, transitively re-proving the ``CERT`` chain under the caller key — and
rebuilding a fresh exact SREP. Only the FRESH artifacts are compared.

Error normalization is deliberately NARROW. Only the five closed prerequisite domain error classes are
normalized, each at the exact stage that owns it. This module never catches ``Exception``, ``RuntimeError``,
``AssertionError``, ``AttributeError``, ``TypeError``, ``ValueError``, any other built-in base, or
``BaseException``. A programmer defect, a broken invariant or an unrelated internal failure propagates
unchanged rather than being laundered into a caller-controlled inconsistency reason.

Output representation: a SEALED NON-CONTAINER object inheriting directly from ``object`` with
``__slots__ = ("__weakref__",)``. It stores EXACTLY THREE anchors — ``request_raw``, ``response_raw`` and
``long_term_public_key`` — in a closure-local, non-module-global registry bound to one exact object identity
and guarded by a weak reference. Those three anchors are the complete source of the proof: the remaining ten
public values are deterministic derivatives, so storing them would create redundant consistency state that
could drift from the anchors. They are instead re-derived from scratch on EVERY public consumption, after the
complete composition has been re-proven. No verdict is cached and no proof-bearing slot exists.

Because ``object.__new__`` can still fabricate a hollow exact-type instance, EVERY public surface — each of the
thirteen properties, ``repr``, ``hash``, ``==``, ``!=``, ``bool``/truthiness and
``copy``/``deepcopy``/pickle reconstruction — re-proves exact type, identity-bound registry membership,
weak-reference liveness and the COMPLETE composition before it returns anything.

SUPPORTED TRUST BOUNDARY (public/supported operations): hostile public inputs; wrong exact types and
subclasses; hostile public attribute access; ordinary ``setattr``/``delattr``; explicit
``object.__setattr__``/``object.__delattr__`` against the artifact instance; ``object.__new__`` hollow
exact-type instances; explicit unbound built-in base calls; public/class/instance introspection through
``type``, MRO, ``dir``, ``vars`` and descriptor inspection; hash/equality/dict/set consumption; boolean
truthiness; ``copy.copy``; ``copy.deepcopy``; pickle serialization and reconstruction; malformed rebuild
arguments; and stale-id or weakref lifecycle accidents while private implementation state is unmodified.

EXCLUDED PRIVATE-STATE BOUNDARY: direct reading of private function ``__closure__`` cells; direct mutation of
private closure-cell contents; direct acquisition or mutation of the closure-local registry through those
cells; monkeypatching private implementation functions or constants; arbitrary mutation of module-private
Python objects; debugger/instrumentation compromise; interpreter-memory modification; native memory
corruption; and arbitrary same-process code execution that intentionally rewrites private implementation
state. No claim is made that closure contents are secret or resist code admitted to this excluded boundary;
pure Python cannot provide that guarantee.

Versioned specification: https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19
"""

from __future__ import annotations

import weakref
from enum import Enum
from weakref import ReferenceType

from crypto_core.validation.roughtime_v19_certificate_verification import (
    RoughtimeV19CertificateVerificationError,
    verify_roughtime_v19_certificate,
)
from crypto_core.validation.roughtime_v19_request_inclusion import (
    RoughtimeV19RequestInclusion,
    RoughtimeV19RequestInclusionError,
    verify_roughtime_v19_request_inclusion,
)
from crypto_core.validation.roughtime_v19_request_semantics import (
    RoughtimeV19RequestSemanticError,
    parse_roughtime_v19_request,
)
from crypto_core.validation.roughtime_v19_response_semantics import (
    RoughtimeV19ResponseSemanticError,
    parse_roughtime_v19_response,
)
from crypto_core.validation.roughtime_v19_signed_response_verification import (
    RoughtimeV19SignedResponseVerification,
    RoughtimeV19SignedResponseVerificationError,
    verify_roughtime_v19_signed_response,
)

# --- Composition profile (governance-selected, versioned; inherits K1/K2/K3/K4/K5/SREP bounds unchanged) ----
ROUGHTIME_V19_REQUEST_IN_SIGNED_RESPONSE_PROFILE_ID = "roughtime-v19-request-in-signed-response-bounded-k4-srep.v1"

# Sentinel for safe attribute reads: distinguishes "attribute absent" from any legitimate value, including None.
_MISSING = object()

# The COMPLETE declared field inventory of the merged K4 input artifact, in its exact declaration order.
_INCLUSION_FIELD_NAMES = (
    "request_raw",
    "response_raw",
    "leaf",
    "computed_root",
    "declared_root",
    "path_length",
    "index",
)

# The COMPLETE public property inventory of the merged SREP input artifact, in its exact declaration order.
_SIGNED_RESPONSE_FIELD_NAMES = (
    "response_raw",
    "long_term_public_key",
    "delegated_public_key",
    "signed_response_raw",
    "response_signature",
    "signed_root",
    "signed_midpoint",
    "signed_radius",
    "signed_version",
    "signed_versions",
)

# The EXACT registered state of this module's output artifact: three source anchors and nothing else. Every
# other public value is a deterministic derivative of these three, so storing one would create redundant
# consistency state capable of drifting from its own source.
_ANCHOR_FIELD_NAMES = (
    "request_raw",
    "response_raw",
    "long_term_public_key",
)

# The COMPLETE and EXCLUSIVE public property inventory, in exact declaration order. Index i of the validated
# view returned by proven_state is public property i. The first three are the stored anchors; the remaining
# ten are freshly re-derived on every consumption and are never stored.
_PUBLIC_FIELD_NAMES = (
    "request_raw",
    "response_raw",
    "long_term_public_key",
    "delegated_public_key",
    "signed_response_raw",
    "signed_root",
    "signed_midpoint",
    "signed_radius",
    "signed_version",
    "signed_versions",
    "request_leaf",
    "request_index",
    "request_path_length",
)

_ERROR_REASON_TYPE_MESSAGE = (
    "RoughtimeV19RequestInSignedResponseError requires a RoughtimeV19RequestInSignedResponseReason member"
)
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19RequestInSignedResponseError is immutable after construction"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})
_SEALED_ARTIFACT_MESSAGE = "RoughtimeV19RequestInSignedResponse is a sealed artifact type and cannot be subclassed"


class RoughtimeV19RequestInSignedResponseReason(str, Enum):
    """Closed composition-failure inventory: exactly five members, evaluated in the pinned precedence below.

    Deliberately coarse. Every prerequisite hardening detail — which K2/K3 semantic rule fired, which Merkle
    step failed, whether a key was non-canonical or small-order, whether the ``CERT`` or the outer ``SIG``
    refused — is already normalized inside K4 and SREP and is NOT re-exposed here, so this layer leaks no new
    oracle. There is deliberately no nonce reason, no version reason, and no provider/readiness reason.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    INPUT_ARTIFACT_INCONSISTENT = "input_artifact_inconsistent"
    SIGNED_ROOT_BINDING_MISMATCH = "signed_root_binding_mismatch"
    RESPONSE_BINDING_MISMATCH = "response_binding_mismatch"
    ARTIFACT_AGGREGATE_INCONSISTENT = "artifact_aggregate_inconsistent"


# The single reason every artifact-state defect normalizes to, on construction and on every consumption
# surface. Bound once so no surface can drift onto a different (more informative, oracle-leaking) reason.
_ARTIFACT_INCONSISTENT = RoughtimeV19RequestInSignedResponseReason.ARTIFACT_AGGREGATE_INCONSISTENT


class RoughtimeV19RequestInSignedResponseError(RuntimeError):
    """Raised for every composition failure, carrying exactly one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19RequestInSignedResponseReason` member. Any other
    argument raises a plain built-in ``TypeError`` before any attribute of that argument (in particular
    ``.value``) is read, so a hostile ``.value`` property can never run. ``str(error)`` is always exactly
    ``reason.value`` and no caller message is ever accepted.

    Scope of the immutability guarantee: ORDINARY attribute assignment and deletion through this class's
    public surface are blocked. This is not a claim of immunity to explicit ``object.__setattr__`` /
    ``object.__delattr__``, which bypass this class's hooks by design; the error object is a diagnostic
    carrier, not a proof artifact.
    """

    def __init__(self, reason: RoughtimeV19RequestInSignedResponseReason) -> None:
        if type(reason) is not RoughtimeV19RequestInSignedResponseReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19RequestInSignedResponseReason:
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
    reason: RoughtimeV19RequestInSignedResponseReason,
) -> RoughtimeV19RequestInSignedResponseError:
    return RoughtimeV19RequestInSignedResponseError(reason)


# --- Complete composition re-proof from the three source anchors -------------------------------------------


def _derived_state(
    request_raw: bytes,
    response_raw: bytes,
    long_term_public_key: bytes,
    reason: RoughtimeV19RequestInSignedResponseReason,
) -> tuple[bytes, bytes, bytes, int, int, int, tuple[int, ...], bytes, int, int]:
    """Re-run the COMPLETE composition from the three anchors and return the ten derived public values.

    Nothing here trusts a stored derivative, a caller-carried nested field or a prior verdict: both packets are
    re-parsed through the merged public K3/K2 parsers and the merged public K4, K5 and SREP verifiers are
    re-invoked on those fresh canonical artifacts on EVERY call, including during artifact self-validation.
    Only the five closed prerequisite domain errors are normalized; every other exception propagates unchanged.
    """
    for anchor in (request_raw, response_raw, long_term_public_key):
        # Exact built-in bytes only. This rejects a bytes SUBCLASS whose value compares equal but whose
        # behaviour (hash, equality, repr) is caller-controlled, which would otherwise reach stored state.
        if type(anchor) is not bytes:
            raise _err(reason)
    try:
        canonical_request = parse_roughtime_v19_request(request_raw)
    except RoughtimeV19RequestSemanticError:
        raise _err(reason) from None
    try:
        canonical_response = parse_roughtime_v19_response(response_raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(reason) from None
    try:
        inclusion = verify_roughtime_v19_request_inclusion(canonical_request, canonical_response)
    except RoughtimeV19RequestInclusionError:
        raise _err(reason) from None
    try:
        certificate = verify_roughtime_v19_certificate(canonical_response, long_term_public_key)
    except RoughtimeV19CertificateVerificationError:
        raise _err(reason) from None
    try:
        signed_response = verify_roughtime_v19_signed_response(certificate)
    except RoughtimeV19SignedResponseVerificationError:
        raise _err(reason) from None
    # K4 already establishes computed_root == declared_root before it returns, so this is a defence-in-depth
    # cross-contract drift guard rather than an independently reachable branch: it exists so a future K4
    # change that relaxed that equality could not silently widen this composition's claim.
    if inclusion.computed_root != inclusion.declared_root:
        raise _err(reason)
    if inclusion.declared_root != signed_response.signed_root:
        raise _err(reason)
    if inclusion.response_raw != signed_response.response_raw:
        raise _err(reason)
    return (
        signed_response.delegated_public_key,
        signed_response.signed_response_raw,
        signed_response.signed_root,
        signed_response.signed_midpoint,
        signed_response.signed_radius,
        signed_response.signed_version,
        signed_response.signed_versions,
        inclusion.leaf,
        inclusion.index,
        inclusion.path_length,
    )


def _validate_anchor_tuple(
    state: object,
    reason: RoughtimeV19RequestInSignedResponseReason,
) -> None:
    """Prove a candidate three-anchor state is exactly shaped, exactly typed and completely re-provable.

    Operates on a plain built-in ``tuple`` and never on the artifact object, so it cannot recurse through any
    public artifact surface. The three anchors are the only values trusted as *inputs*; everything else is
    re-derived by re-running the COMPLETE composition and nothing is cached.
    """
    if type(state) is not tuple:
        raise _err(reason)
    if len(state) != len(_ANCHOR_FIELD_NAMES):
        raise _err(reason)
    request_raw, response_raw, long_term_public_key = state
    _derived_state(request_raw, response_raw, long_term_public_key, reason)


# --- Sealed non-container public artifact with a closure-local identity registry ----------------------------


def _build_request_in_signed_response_class() -> type:
    """Create the public artifact class over a closure-local, non-module-global registry.

    The three verified anchors must live somewhere a caller can neither read through the object nor reach as
    ordinary module state, so the registry is bound in this closure and no production registry hook is
    exported. Inheriting straight from :class:`object` and keeping no proof in the instance means there is no
    storage for an explicit unbound built-in base call to read, so that escape is structurally absent rather
    than blacklisted method by method.
    """
    # id(artifact) -> (weakref.ref(artifact, on_death), three-anchor state tuple).
    # Keyed by identity, never by artifact equality or hash, so registry lookup can never invoke the
    # artifact's own __hash__/__eq__ (which would recurse into validation, which needs the registry).
    registry: dict[int, tuple[ReferenceType, tuple]] = {}

    def register(artifact: object, state: tuple) -> None:
        """Bind verified anchors to one exact live object identity. Called only after full verification."""
        key = id(artifact)

        def forget(dead: ReferenceType, key: int = key) -> None:
            # Remove ONLY the entry this reference owns. CPython may reuse an id() after collection, so a
            # blind `del registry[key]` could delete a newer artifact's entry.
            current = registry.get(key)
            if current is not None and current[0] is dead:
                del registry[key]

        registry[key] = (weakref.ref(artifact, forget), state)

    def proven_state(artifact: object) -> tuple:
        """Return the complete thirteen-value validated view, re-proving everything, or raise the closed reason.

        Five independent gates, in this order: exact public type; an identity-keyed registry entry exists; that
        entry's weak reference is still alive AND is exactly this object (so a stale or reused id can never
        authenticate a later object); the stored state is an exact three-value tuple; and the COMPLETE
        composition re-derives successfully from those three anchors. The returned view is the three stored
        anchors followed by the ten values freshly derived on THIS call.
        """
        if type(artifact) is not RoughtimeV19RequestInSignedResponse:
            raise _err(_ARTIFACT_INCONSISTENT)
        entry = registry.get(id(artifact))
        if entry is None:
            raise _err(_ARTIFACT_INCONSISTENT)
        reference, state = entry
        if reference() is not artifact:
            raise _err(_ARTIFACT_INCONSISTENT)
        if type(state) is not tuple or len(state) != len(_ANCHOR_FIELD_NAMES):
            raise _err(_ARTIFACT_INCONSISTENT)
        request_raw, response_raw, long_term_public_key = state
        derived = _derived_state(request_raw, response_raw, long_term_public_key, _ARTIFACT_INCONSISTENT)
        return (request_raw, response_raw, long_term_public_key, *derived)

    class RoughtimeV19RequestInSignedResponse:
        """Proof that one exact request is included in the signed root of one exact signed response.

        Stores EXACTLY THREE anchors — the complete ``request_raw`` packet bytes, the complete ``response_raw``
        packet bytes, and the exact 32-byte ``long_term_public_key`` the ``CERT`` chain was proven under. The
        other ten public values (``delegated_public_key``, ``signed_response_raw``, ``signed_root``,
        ``signed_midpoint``, ``signed_radius``, ``signed_version``, ``signed_versions``, ``request_leaf``,
        ``request_index``, ``request_path_length``) are deterministic derivatives of those anchors and are
        deliberately NOT stored: they are re-derived from scratch on every public consumption, so no stored
        derivative can ever drift from the source it claims to summarize.

        NOT A CONTAINER. It inherits directly from :class:`object` and stores NOTHING on the instance: there is
        no ``__dict__`` and the only slot is ``__weakref__`` (itself a read-only descriptor). Consequently
        ``setattr``, ``delattr``, ``object.__setattr__``, ``object.__delattr__`` and ``__dict__`` assignment all
        fail, no attribute can be added, and explicit unbound base calls such as ``tuple.__getitem__`` are
        simply inapplicable to this type and raise an ordinary ``TypeError`` without exposing anything.

        Construction re-runs the COMPLETE composition BEFORE the object is registered, so a failed construction
        leaves no registry entry and no consumable object. Every public surface — each of the thirteen
        properties, ``repr``, ``hash``, ``==``, ``!=``, ``bool``/truthiness and
        ``copy``/``deepcopy``/pickle reconstruction — re-proves identity, registry binding and the full
        composition before returning anything. A hollow
        ``object.__new__(RoughtimeV19RequestInSignedResponse)`` has no registry entry and fails closed on every
        one of them with exactly ``artifact_aggregate_inconsistent``; no ``KeyError``, ``LookupError``,
        ``ReferenceError``, ``AttributeError``, ``IndexError``, ``TypeError``, ``ValueError`` or prerequisite
        exception escapes. No verdict is cached.

        Deliberately NO sequence or container protocol: ``len``, iteration, indexing, membership, ``count``,
        ``index``, ordering, concatenation and repetition are all inapplicable. Truthiness is provided by an
        explicit validating ``__bool__`` and never by ``__len__``, so ``len`` stays inapplicable. Equality is
        strictly type-bound and compares only the three stored anchors, so a bare ``tuple``/``list``/``dict``
        carrying the same values is never equal to a proof in either direction.

        SEALED TYPE: closed to subclassing. Any attempt to derive from it raises a fixed repository-owned
        built-in ``TypeError`` at CLASS-DEFINITION time, before a subclass instance can exist.

        NON-CLAIM: existence of this artifact carries the composition claim above and nothing else. The signed
        values are SIGNED, not TRUE: ``signed_midpoint``/``signed_radius`` are not a truthful-time claim and
        ``signed_version``/``signed_versions`` are not a deployed-version claim. It does NOT assert provider
        identity, key ownership, provenance, admission or revocation, ``NONC`` correlation, version
        compatibility, machine-time provenance, quorum, sandwich completion, readiness, or connector safety.
        There is deliberately no ``verified``, ``authentic``, ``provider``, ``time_valid``, ``ready``,
        ``quorum``, ``correlated`` or ``admitted`` field: the type itself is the claim, and its scope is
        exactly this docstring.
        """

        # Only __weakref__ — required for the registry's lifecycle binding, and not writable, so it cannot be
        # repurposed as proof storage. No __dict__ and no data slot exist.
        __slots__ = ("__weakref__",)

        def __new__(
            cls,
            *,
            request_raw: bytes,
            response_raw: bytes,
            long_term_public_key: bytes,
        ) -> RoughtimeV19RequestInSignedResponse:
            state = (request_raw, response_raw, long_term_public_key)
            # Verify FIRST, then create and register: a rejected state must leave no object and no entry.
            _validate_anchor_tuple(state, _ARTIFACT_INCONSISTENT)
            artifact = object.__new__(cls)
            register(artifact, state)
            return artifact

        def __init_subclass__(cls, **kwargs: object) -> None:
            # Fires when a subclass is DEFINED, before it can be instantiated and therefore before any
            # overriding lifecycle method of that subclass can execute. Deterministic, no caller text.
            raise TypeError(_SEALED_ARTIFACT_MESSAGE)

        @property
        def request_raw(self) -> bytes:
            return proven_state(self)[0]

        @property
        def response_raw(self) -> bytes:
            return proven_state(self)[1]

        @property
        def long_term_public_key(self) -> bytes:
            return proven_state(self)[2]

        @property
        def delegated_public_key(self) -> bytes:
            return proven_state(self)[3]

        @property
        def signed_response_raw(self) -> bytes:
            return proven_state(self)[4]

        @property
        def signed_root(self) -> bytes:
            return proven_state(self)[5]

        @property
        def signed_midpoint(self) -> int:
            return proven_state(self)[6]

        @property
        def signed_radius(self) -> int:
            return proven_state(self)[7]

        @property
        def signed_version(self) -> int:
            return proven_state(self)[8]

        @property
        def signed_versions(self) -> tuple[int, ...]:
            return proven_state(self)[9]

        @property
        def request_leaf(self) -> bytes:
            return proven_state(self)[10]

        @property
        def request_index(self) -> int:
            return proven_state(self)[11]

        @property
        def request_path_length(self) -> int:
            return proven_state(self)[12]

        def __repr__(self) -> str:
            view = proven_state(self)
            rendered = ", ".join(f"{name}={view[index]!r}" for index, name in enumerate(_PUBLIC_FIELD_NAMES))
            return f"RoughtimeV19RequestInSignedResponse({rendered})"

        def __bool__(self) -> bool:
            """Truthiness is a proof-consumption surface, so ``if composition:`` must revalidate.

            Without an explicit implementation, ``object``'s default truthiness would report a hollow
            ``object.__new__`` instance as ``True`` without touching the registry or re-proving the
            composition. Returns exactly the built-in ``True`` for a genuine artifact and raises the closed
            artifact reason otherwise; it never returns ``False``, because a proof that cannot be re-proven is
            a fail-closed error and not a falsey value. Implemented through ``__bool__`` and deliberately NOT
            through ``__len__``, so this type still exposes no container protocol.
            """
            proven_state(self)
            return True

        def __hash__(self) -> int:
            # Hashes ONLY the three stored anchors, after the complete composition has been re-proven.
            return hash(proven_state(self)[: len(_ANCHOR_FIELD_NAMES)])

        def __eq__(self, other: object) -> bool:
            state = proven_state(self)[: len(_ANCHOR_FIELD_NAMES)]
            if type(other) is not RoughtimeV19RequestInSignedResponse:
                # Deliberately False rather than NotImplemented: a bare tuple/list/dict carrying the same
                # anchors must not compare equal to a verified proof through a reflected operation. The right
                # operand is never read, so a hostile object cannot execute anything here.
                return False
            return state == proven_state(other)[: len(_ANCHOR_FIELD_NAMES)]

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __reduce__(self) -> tuple:
            """Route ``copy``/``deepcopy``/pickle through the validating three-anchor constructor.

            Returns only the three plain anchors, never a derived value and never anything from the registry,
            and reconstruction runs the complete composition again — so a hand-crafted pickle cannot install
            proof state directly.
            """
            return (
                _rebuild_request_in_signed_response,
                (proven_state(self)[: len(_ANCHOR_FIELD_NAMES)],),
            )

    RoughtimeV19RequestInSignedResponse.__qualname__ = "RoughtimeV19RequestInSignedResponse"
    RoughtimeV19RequestInSignedResponse.__module__ = __name__
    return RoughtimeV19RequestInSignedResponse


RoughtimeV19RequestInSignedResponse = _build_request_in_signed_response_class()


def _rebuild_request_in_signed_response(state: object) -> RoughtimeV19RequestInSignedResponse:
    """Reconstruct an artifact from copy/deepcopy/pickle state by re-running the COMPLETE composition.

    Every argument shape defect and every value defect normalizes to the artifact reason; the validating
    keyword constructor is the only construction path, so no registry entry can exist before success.
    """
    if type(state) is not tuple or len(state) != len(_ANCHOR_FIELD_NAMES):
        raise _err(_ARTIFACT_INCONSISTENT)
    return RoughtimeV19RequestInSignedResponse(
        request_raw=state[0],
        response_raw=state[1],
        long_term_public_key=state[2],
    )


def verify_roughtime_v19_request_in_signed_response(
    request_inclusion: RoughtimeV19RequestInclusion,
    signed_response_verification: RoughtimeV19SignedResponseVerification,
) -> RoughtimeV19RequestInSignedResponse:
    """Bind an exact K4 request-inclusion proof to an exact SREP signed-response proof of the same response.

    Accepts the EXACT merged K4 and SREP artifact types only; both exact-type gates run BEFORE any attribute of
    either input is read, so no hostile override can execute. Each input is then completely re-proven across
    the trust boundary — the K4 input through its own exact base validator plus a fresh rebuild from its
    complete snapshotted state, the SREP input through its ten revalidating public properties plus a fresh
    rebuild, which transitively re-proves the ``CERT`` chain under the caller-supplied long-term key. ONLY the
    fresh artifacts are compared: the signed root first, then the exact response bytes.

    Verifies no new signature and computes no new hash. Performs no nonce correlation, no version relation, no
    provider or key-provenance binding, no root-key admission, no clock read, no quorum evaluation, and causes
    no readiness or connector transition.
    """
    if type(request_inclusion) is not RoughtimeV19RequestInclusion:
        raise _err(RoughtimeV19RequestInSignedResponseReason.WRONG_INPUT_TYPE)
    if type(signed_response_verification) is not RoughtimeV19SignedResponseVerification:
        raise _err(RoughtimeV19RequestInSignedResponseReason.WRONG_INPUT_TYPE)
    inconsistent = RoughtimeV19RequestInSignedResponseReason.INPUT_ARTIFACT_INCONSISTENT
    # K4 stage. Re-invoke the exact base validator on the caller's object first: it proves the COMPLETE
    # instance namespace, which a raw-only reparse could not, because a mutated carried field that the Merkle
    # computation never reads would otherwise survive.
    try:
        RoughtimeV19RequestInclusion.__post_init__(request_inclusion)
    except RoughtimeV19RequestInclusionError:
        raise _err(inconsistent) from None
    inclusion_state: dict[str, object] = {}
    for name in _INCLUSION_FIELD_NAMES:
        # Sentinel reads, never a caught AttributeError: an absent field is a closed inconsistency, not an
        # exception to be laundered.
        value = getattr(request_inclusion, name, _MISSING)
        if value is _MISSING:
            raise _err(inconsistent)
        inclusion_state[name] = value
    try:
        fresh_inclusion = RoughtimeV19RequestInclusion(**inclusion_state)  # type: ignore[arg-type]
    except RoughtimeV19RequestInclusionError:
        raise _err(inconsistent) from None
    # SREP stage. Reading each public property re-runs SREP's own complete revalidation, which freshly
    # re-parses K2, rebinds the delegated key, re-proves the CERT signature under the caller-supplied
    # long-term key and re-verifies the outer SIG, so K5 is transitively re-proven here.
    signed_response_state: dict[str, object] = {}
    try:
        for name in _SIGNED_RESPONSE_FIELD_NAMES:
            signed_response_state[name] = getattr(signed_response_verification, name)
        fresh_signed_response = RoughtimeV19SignedResponseVerification(**signed_response_state)  # type: ignore[arg-type]
    except RoughtimeV19SignedResponseVerificationError:
        raise _err(inconsistent) from None
    # Cross-artifact bindings, in pinned precedence: signed root first, then exact response bytes.
    if fresh_inclusion.declared_root != fresh_signed_response.signed_root:
        raise _err(RoughtimeV19RequestInSignedResponseReason.SIGNED_ROOT_BINDING_MISMATCH)
    if fresh_inclusion.response_raw != fresh_signed_response.response_raw:
        raise _err(RoughtimeV19RequestInSignedResponseReason.RESPONSE_BINDING_MISMATCH)
    return RoughtimeV19RequestInSignedResponse(
        request_raw=fresh_inclusion.request_raw,
        response_raw=fresh_inclusion.response_raw,
        long_term_public_key=fresh_signed_response.long_term_public_key,
    )


__all__ = [
    "ROUGHTIME_V19_REQUEST_IN_SIGNED_RESPONSE_PROFILE_ID",
    "RoughtimeV19RequestInSignedResponse",
    "RoughtimeV19RequestInSignedResponseError",
    "RoughtimeV19RequestInSignedResponseReason",
    "verify_roughtime_v19_request_in_signed_response",
]
