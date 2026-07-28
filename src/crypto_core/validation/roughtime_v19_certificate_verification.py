"""Roughtime draft-19 bounded CERTIFICATE/DELEGATION signature verifier (internal MT-4 prerequisite K5).

This module layers ONE cryptographic signature check over the merged K2 response-semantic decoder
(:mod:`crypto_core.validation.roughtime_v19_response_semantics`). K2 proves wire semantics and performs no
cryptography; K5 answers exactly one closed question: does the exact ``CERT`` signature validate, under an
exact caller-supplied 32-byte long-term Ed25519 public key, over the exact ``DELE`` value bytes that K2
preserved?

Bounded profile (honest scope): ONE governance-selected, versioned profile, identified by
:data:`ROUGHTIME_V19_CERTIFICATE_VERIFICATION_PROFILE_ID`
(``"roughtime-v19-certificate-verification-bounded-k5.v1"``). It inherits the K1 structural bounds and the K2
semantic bounds unchanged and adds no new byte-size ceiling of its own.

Normative transcript (the only message this module ever verifies)::

    CERT_CONTEXT = b"RoughTime v1 delegation signature\\x00"   # 34 bytes, trailing NUL is part of the input
    transcript   = CERT_CONTEXT + certificate.delegation.raw   # exact preserved DELE value bytes

The DELE bytes are taken verbatim from a freshly re-parsed K2 artifact and are NEVER reconstructed,
re-encoded or normalized from decoded fields. Algorithm is Ed25519 / PureEdDSA (RFC 8032): no Ed25519ctx, no
Ed25519ph, no prehash, and no hashing of the transcript before verification.

Defence in depth before the backend is called. The final group-equation check is delegated to the pinned
PyNaCl backend, but this module independently enforces repository policy first, so a weak input can never
reach the backend at all: exact built-in ``bytes`` types; public key exactly 32 bytes and signature exactly
64; canonical encoding of the public key ``A`` and of the signature point ``R`` (clear the sign bit, require
the encoded y-coordinate < 2**255 - 19); the signature scalar ``S`` read little-endian and required to be
strictly below the group order ``L``; and rejection of the complete documented small-order encoding inventory
for BOTH ``A`` and ``R``. These private checks are additional fail-closed policy, never a replacement
verifier.

Trust boundary: K5 consumes an artifact it did not build. It requires the EXACT merged public type
(``type(x) is C``, never ``isinstance``), which alone rejects every subclass and so prevents a hostile
``__getattribute__``/``__new__`` override from executing; it then re-parses ``response.raw``
through the merged K2 public parser and performs ALL cryptographic work on that fresh canonical artifact, so
a caller-carried nested field can never influence the result. Every K2 failure, every state defect and every
backend exception is normalized to exactly one closed member of
:class:`RoughtimeV19CertificateVerificationReason`; no raw PyNaCl exception, ``AttributeError``,
``TypeError`` or ``ValueError`` escapes, and no ``BaseException`` is caught.

Output representation: the artifact this module returns is a SEALED NON-CONTAINER object that inherits
directly from ``object``, stores no proof state on the instance at all, and holds its eight verified values in
a closure-local, non-module-global registry bound to one exact object identity and guarded by a weak reference.

Two earlier representations were rejected for concrete reasons. A frozen dataclass only intercepts
``__setattr__`` while still carrying a writable instance ``__dict__``, so a caller could replace a
cryptographically derived field AFTER verification succeeded. Moving the values into a ``tuple`` base closed
that hole but opened a worse one: subclass overrides cannot intercept an EXPLICIT unbound base call, so
``tuple.__getitem__(artifact, 0)``, ``tuple.__iter__``, ``tuple.__repr__``, ``tuple.__getnewargs__``,
``tuple.__add__``, ``tuple.count`` and ``tuple.index`` read the base storage directly and returned
unvalidated — including deliberately forged — proof state. Keeping no proof in the instance removes the
storage those calls read, so the escape is structurally absent rather than blacklisted method by method, and
every built-in container base call is simply inapplicable to this type.

Because ``object.__new__`` can still fabricate a hollow exact-type instance that bypasses the public keyword
constructor, EVERY public surface (each of the eight named properties, ``repr``, ``hash``, ``==``, ``!=`` and
``copy``/``deepcopy``/pickle reconstruction) re-proves exact type, identity-bound registry membership, weak
reference liveness and the COMPLETE cryptographic derivation before it returns anything.

SUPPORTED TRUST BOUNDARY (public/supported operations): hostile public inputs; wrong exact types and
subclasses; hostile public attribute access; ordinary ``setattr``/``delattr``; explicit
``object.__setattr__``/``object.__delattr__`` against the artifact instance; ``object.__new__`` hollow
exact-type instances; explicit unbound built-in base calls; public/class/instance introspection through
``type``, MRO, ``dir``, ``vars`` and descriptor inspection; hash/equality/dict/set consumption; ``copy.copy``;
``copy.deepcopy``; pickle serialization and reconstruction; malformed rebuild arguments; ordinary backend
``Exception`` instances; and stale-id or weakref lifecycle accidents while private implementation state is
unmodified.

EXCLUDED PRIVATE-STATE BOUNDARY: direct reading of private function ``__closure__`` cells; direct mutation of
private closure-cell contents; direct acquisition or mutation of the closure-local registry through those
cells; monkeypatching private implementation functions or constants; arbitrary mutation of module-private
Python objects; debugger/instrumentation compromise; interpreter-memory modification; native memory
corruption; and arbitrary same-process code execution that intentionally rewrites private implementation
state. No claim is made that closure contents are secret or resist code admitted to this excluded boundary;
pure Python cannot provide that guarantee.

A successful artifact proves EXACTLY:

* the exact ``CERT`` signature validates under the supplied long-term public key;
* the signature covers the exact preserved ``DELE`` raw bytes;
* the delegated public key and ``MINT``/``MAXT`` are the exact K2-decoded values carried by that signed
  ``DELE``;
* K2 has already established ``MINT <= MAXT`` and ``MINT <= MIDP <= MAXT`` structurally.

It proves NOTHING about: provider identity; provider ownership of the supplied long-term key; key provenance;
root-key admission; key revocation; deployed protocol version; the ``SREP`` signature; K4 request inclusion;
truthful or authenticated time; machine-time provenance; quorum; readiness; connector safety; reachability;
operational approval; or any private/live/order/capital capability. Supplying an unauthenticated key and
getting a successful artifact proves self-consistency only, never identity.

Versioned specification: https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19
"""

from __future__ import annotations

import weakref
from enum import Enum
from weakref import ReferenceType

from nacl.encoding import RawEncoder
from nacl.exceptions import BadSignatureError
from nacl.exceptions import ValueError as NaclValueError
from nacl.signing import VerifyKey

from crypto_core.validation.roughtime_v19_response_semantics import (
    RoughtimeV19ResponseSemanticError,
    RoughtimeV19ResponseSemantics,
    parse_roughtime_v19_response,
)

# --- Verification profile (governance-selected, versioned; inherits K1/K2 bounds unchanged) ----------------
ROUGHTIME_V19_CERTIFICATE_VERIFICATION_PROFILE_ID = "roughtime-v19-certificate-verification-bounded-k5.v1"

# --- Normative transcript constants -----------------------------------------------------------------------
# The trailing NUL is part of the signed input. Omitting it changes the transcript and MUST fail.
_CERT_CONTEXT = b"RoughTime v1 delegation signature\x00"

# --- Ed25519 hardening constants (RFC 8032) ---------------------------------------------------------------
_PUBLIC_KEY_BYTES = 32
_SIGNATURE_BYTES = 64
_FIELD_PRIME = (1 << 255) - 19  # p; a canonical encoded y-coordinate must be strictly below this
_GROUP_ORDER = (1 << 252) + 27742317777372353535851937790883648493  # L; S must be strictly below this
_SIGN_BIT_MASK = 0x7F  # byte 31 carries the x sign bit, which is not part of the y-coordinate

# Complete small-order encoding inventory, transcribed byte-for-byte from the immutable vendored libsodium
# source shipped with the pinned backend:
#   pyca/pynacl tag 1.6.2
#   src/libsodium/src/libsodium/crypto_core/ed25519/ref10/ed25519_ref10.c
#   function ge25519_has_small_order, static table `blacklist[][32]`
# The source asserts its own length with COMPILER_ASSERT(7 == sizeof blacklist / sizeof blacklist[0]), so the
# inventory is exactly seven entries. Comments record each entry's documented order. libsodium compares bytes
# 0..30 exactly and byte 31 masked with 0x7f; _is_small_order mirrors that rule exactly.
_SMALL_ORDER_ENCODINGS = (
    bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000"),  # 0 (order 4)
    bytes.fromhex("0100000000000000000000000000000000000000000000000000000000000000"),  # 1 (order 1)
    bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"),  # order 8
    bytes.fromhex("c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"),  # order 8
    bytes.fromhex("ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"),  # p-1 (order 2)
    bytes.fromhex("edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"),  # p (=0, order 4)
    bytes.fromhex("eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"),  # p+1 (=1, order 1)
)

# Sentinel for safe attribute reads: distinguishes "attribute absent" from any legitimate value.
_MISSING = object()

# The COMPLETE and EXCLUSIVE public field inventory of this module's output artifact, in exact declaration
# order. It also fixes the registered state layout: index i of the registered state tuple is public field i
# below, and a valid state holds exactly this many values and nothing else.
_VERIFICATION_FIELD_NAMES = (
    "response_raw",
    "long_term_public_key",
    "certificate_raw",
    "certificate_signature",
    "delegation_raw",
    "delegated_public_key",
    "min_time",
    "max_time",
)

_ERROR_REASON_TYPE_MESSAGE = (
    "RoughtimeV19CertificateVerificationError requires a RoughtimeV19CertificateVerificationReason member"
)
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19CertificateVerificationError is immutable after construction"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})
_SEALED_ARTIFACT_MESSAGE = "RoughtimeV19CertificateVerification is a sealed artifact type and cannot be subclassed"


class RoughtimeV19CertificateVerificationReason(str, Enum):
    """Closed failure inventory: exactly six members, evaluated in the pinned precedence below.

    Deliberately coarse: whether a rejection came from canonicality, small-order membership, the scalar bound,
    a signature mismatch or a backend refusal is NOT distinguishable through the public reason, so the
    verifier leaks no oracle about which hardening step fired.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    INPUT_ARTIFACT_INCONSISTENT = "input_artifact_inconsistent"
    LONG_TERM_PUBLIC_KEY_INVALID = "long_term_public_key_invalid"
    CERT_SIGNATURE_INVALID = "cert_signature_invalid"
    CRYPTO_BACKEND_FAILURE = "crypto_backend_failure"
    ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT = "artifact_certificate_verification_inconsistent"


# The single reason every artifact-state defect normalizes to, on construction and on every consumption
# surface. Bound once so no surface can drift onto a different (more informative, oracle-leaking) reason.
_ARTIFACT_INCONSISTENT = RoughtimeV19CertificateVerificationReason.ARTIFACT_CERTIFICATE_VERIFICATION_INCONSISTENT


class RoughtimeV19CertificateVerificationError(RuntimeError):
    """Raised for every certificate-verification failure, carrying exactly one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19CertificateVerificationReason` member. Any other
    argument raises a plain built-in ``TypeError`` before any attribute of that argument (in particular
    ``.value``) is read, so a hostile ``.value`` property can never run. ``str(error)`` is always exactly
    ``reason.value`` and no caller message is ever accepted.

    Scope of the immutability guarantee: ORDINARY attribute assignment and deletion through this class's
    public surface (``error.reason = x``, ``del error.reason``, and likewise for ``_reason``/``args``) are
    blocked. This is not a claim of immunity to explicit ``object.__setattr__``/``object.__delattr__``, which
    bypass this class's hooks by design; the error object is a diagnostic carrier, not a proof artifact.
    """

    def __init__(self, reason: RoughtimeV19CertificateVerificationReason) -> None:
        if type(reason) is not RoughtimeV19CertificateVerificationReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19CertificateVerificationReason:
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
    reason: RoughtimeV19CertificateVerificationReason,
) -> RoughtimeV19CertificateVerificationError:
    return RoughtimeV19CertificateVerificationError(reason)


# --- Private Ed25519 encoding hardening (policy only; never the group-equation verifier) -------------------


def _is_canonical_point(encoding: bytes) -> bool:
    """Return whether a 32-byte point encoding carries a canonical y-coordinate (y < p, sign bit ignored)."""
    masked = bytearray(encoding)
    masked[31] &= _SIGN_BIT_MASK
    return int.from_bytes(bytes(masked), "little") < _FIELD_PRIME


def _is_small_order(encoding: bytes) -> bool:
    """Return whether a 32-byte point encoding is in the documented small-order inventory.

    Mirrors libsodium's ge25519_has_small_order exactly: bytes 0..30 compared verbatim and byte 31 compared
    with the sign bit masked off.
    """
    head = encoding[:31]
    tail = encoding[31] & _SIGN_BIT_MASK
    for candidate in _SMALL_ORDER_ENCODINGS:
        if head == candidate[:31] and tail == (candidate[31] & _SIGN_BIT_MASK):
            return True
    return False


def _public_key_rejected(public_key: bytes) -> bool:
    """Return whether a caller-supplied long-term public key fails repository policy before the backend."""
    if len(public_key) != _PUBLIC_KEY_BYTES:
        return True
    if not _is_canonical_point(public_key):
        return True
    return _is_small_order(public_key)


def _signature_rejected(signature: bytes) -> bool:
    """Return whether a signature fails encoding policy: R canonical and non-small-order, and S < L."""
    if len(signature) != _SIGNATURE_BYTES:
        return True
    point_r = signature[:32]
    if not _is_canonical_point(point_r):
        return True
    if _is_small_order(point_r):
        return True
    return int.from_bytes(signature[32:], "little") >= _GROUP_ORDER


def _verify_detached(transcript: bytes, public_key: bytes, signature: bytes) -> None:
    """Delegate the final Ed25519 group-equation check to the pinned backend, normalizing every failure.

    Argument order is fixed: ``VerifyKey(public_key, encoder=RawEncoder).verify(message, signature)``. All
    lengths and encodings were already proven above, so a backend refusal here means the signature does not
    validate; anything else is reported as a backend failure rather than silently swallowed.
    """
    try:
        VerifyKey(public_key, encoder=RawEncoder).verify(transcript, signature)
    except BadSignatureError:
        raise _err(RoughtimeV19CertificateVerificationReason.CERT_SIGNATURE_INVALID) from None
    except NaclValueError:
        raise _err(RoughtimeV19CertificateVerificationReason.CERT_SIGNATURE_INVALID) from None
    except Exception:
        # The ONLY broad catch in this module, deliberately scoped to the two external backend calls above and
        # placed AFTER the two signature-invalid classes so it can never mask a real verification verdict. An
        # enumerated handler list is not sufficient here: the backend is third-party native code, so any
        # unexpected class it raises (AttributeError, IndexError, builtins.ValueError, OSError, a custom
        # exception, ...) must still normalize instead of escaping raw through a cryptographic boundary.
        # BaseException is NOT caught, so KeyboardInterrupt and SystemExit still propagate. K2 parsing,
        # transcript construction and all registry/artifact logic live outside this block.
        raise _err(RoughtimeV19CertificateVerificationReason.CRYPTO_BACKEND_FAILURE) from None


# --- Shared verification core (used by the entry point and by artifact self-validation) --------------------


def _verified_state(
    response_raw: bytes,
    long_term_public_key: bytes,
    inconsistent: RoughtimeV19CertificateVerificationReason,
) -> tuple[bytes, bytes, bytes, bytes, int, int]:
    """Re-parse the response, re-run every check, and return the six derived artifact values.

    Nothing here trusts a caller-carried field: the canonical K2 artifact is produced fresh from
    ``response_raw`` on every call, including during artifact self-validation, so no stored verdict is ever
    believed.
    """
    try:
        canonical = parse_roughtime_v19_response(response_raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(inconsistent) from None
    if _public_key_rejected(long_term_public_key):
        raise _err(RoughtimeV19CertificateVerificationReason.LONG_TERM_PUBLIC_KEY_INVALID)
    certificate = canonical.certificate
    delegation = certificate.delegation
    signature = certificate.signature
    if _signature_rejected(signature):
        raise _err(RoughtimeV19CertificateVerificationReason.CERT_SIGNATURE_INVALID)
    _verify_detached(_CERT_CONTEXT + delegation.raw, long_term_public_key, signature)
    return (
        certificate.raw,
        signature,
        delegation.raw,
        delegation.pubk,
        delegation.min_time,
        delegation.max_time,
    )


def _validate_state_tuple(
    state: object,
    reason: RoughtimeV19CertificateVerificationReason,
) -> None:
    """Prove a candidate eight-value state is exactly shaped, exactly typed and cryptographically re-derivable.

    Operates on a plain built-in ``tuple`` and never on the artifact object, so it cannot recurse through any
    public artifact surface. The first two values (``response_raw`` and ``long_term_public_key``) are the only
    inputs trusted as *inputs*; the remaining six are re-derived from them by re-running the COMPLETE
    verification — fresh K2 parse, key policy, signature-encoding policy and the backend group equation — and
    must match exactly. No stored verdict is ever believed and nothing is cached.
    """
    if type(state) is not tuple:
        raise _err(reason)
    if len(state) != len(_VERIFICATION_FIELD_NAMES):
        raise _err(reason)
    (
        response_raw,
        long_term_public_key,
        certificate_raw,
        certificate_signature,
        delegation_raw,
        delegated_public_key,
        min_time,
        max_time,
    ) = state
    for candidate in (
        response_raw,
        long_term_public_key,
        certificate_raw,
        certificate_signature,
        delegation_raw,
        delegated_public_key,
    ):
        if type(candidate) is not bytes:
            raise _err(reason)
    if type(min_time) is not int or type(max_time) is not int:
        raise _err(reason)
    try:
        expected = _verified_state(response_raw, long_term_public_key, reason)
    except RoughtimeV19CertificateVerificationError:
        raise _err(reason) from None
    if (
        certificate_raw,
        certificate_signature,
        delegation_raw,
        delegated_public_key,
        min_time,
        max_time,
    ) != expected:
        raise _err(reason)


# --- Sealed non-container public artifact with a closure-local identity registry ----------------------------


def _build_certificate_verification_class() -> type:
    """Create the public artifact class over a closure-local, non-module-global registry.

    Why a factory rather than a module-level class plus a module-level dict: the eight verified values must be
    absent from both the artifact instance and the module namespace. A module-global mapping would be exposed
    as ordinary module state, so the registry is bound in this closure and no production registry hook is
    exported. Direct inspection or mutation of private ``__closure__`` cells is explicitly outside the
    supported trust boundary; closure locality is containment, not a secrecy claim.

    Why not a container base class: the previous representation subclassed ``tuple``, which stores the values
    in the base object itself. Subclass overrides cannot intercept an EXPLICIT unbound base call, so
    ``tuple.__getitem__(artifact, 0)``, ``tuple.__iter__``, ``tuple.__repr__``, ``tuple.__getnewargs__``,
    ``tuple.__add__`` and friends read that storage directly and returned unvalidated — including forged —
    proof state. Inheriting straight from :class:`object` and keeping no proof in the instance removes the
    storage those calls read, so the escape is structurally absent rather than blacklisted method by method.
    """
    # id(artifact) -> (weakref.ref(artifact, on_death), eight-value state tuple).
    # Keyed by identity, never by artifact equality or hash, so registry lookup can never invoke the
    # artifact's own __hash__/__eq__ (which would recurse into validation, which needs the registry).
    registry: dict[int, tuple[ReferenceType, tuple]] = {}

    def register(artifact: object, state: tuple) -> None:
        """Bind verified state to one exact live object identity. Called only after full verification."""
        key = id(artifact)

        def forget(dead: ReferenceType, key: int = key) -> None:
            # Remove ONLY the entry this reference owns. CPython may reuse an id() after collection, so a
            # blind `del registry[key]` could delete a newer artifact's entry.
            current = registry.get(key)
            if current is not None and current[0] is dead:
                del registry[key]

        registry[key] = (weakref.ref(artifact, forget), state)

    def proven_state(artifact: object) -> tuple:
        """Return the verified state for ``artifact``, re-proving everything, or raise the closed reason.

        Four independent gates, in this order: exact public type; an identity-keyed registry entry exists;
        that entry's weak reference is still alive AND is exactly this object (so a stale or reused id can
        never authenticate a later object); and the complete state re-validates cryptographically.
        """
        if type(artifact) is not RoughtimeV19CertificateVerification:
            raise _err(_ARTIFACT_INCONSISTENT)
        entry = registry.get(id(artifact))
        if entry is None:
            raise _err(_ARTIFACT_INCONSISTENT)
        reference, state = entry
        if reference() is not artifact:
            raise _err(_ARTIFACT_INCONSISTENT)
        _validate_state_tuple(state, _ARTIFACT_INCONSISTENT)
        return state

    class RoughtimeV19CertificateVerification:
        """Proof that one exact ``CERT`` signature validates over one exact ``DELE`` under one supplied key.

        Carries the exact complete ``response_raw`` packet bytes, the exact 32-byte ``long_term_public_key``
        the caller supplied, the exact preserved ``certificate_raw`` and 64-byte ``certificate_signature``,
        the exact signed ``delegation_raw``, and the ``delegated_public_key``/``min_time``/``max_time`` that
        K2 decoded from those signed bytes.

        NOT A CONTAINER. It inherits directly from :class:`object` and stores NOTHING on the instance: there
        is no ``__dict__`` and the only slot is ``__weakref__`` (itself a read-only descriptor). The eight
        verified values live in a closure-local, non-module-global registry, bound to one exact object identity
        and guarded by a weak reference. Consequently there is no instance storage for an explicit
        unbound base call to read: ``tuple.__getitem__``, ``tuple.__iter__``, ``tuple.__repr__``,
        ``tuple.__getnewargs__``, ``tuple.__add__``, ``tuple.count``, ``tuple.index`` and the rest are simply
        inapplicable to this type and raise an ordinary ``TypeError`` without exposing anything. ``setattr``,
        ``delattr``, ``object.__setattr__``, ``object.__delattr__`` and ``__dict__`` assignment all fail, so a
        verified field cannot be replaced after the fact, and ``hash``/equality are fixed at construction.

        Construction through the public keyword constructor re-parses ``response_raw`` and re-runs the
        COMPLETE verification BEFORE the object is registered, so a failed construction leaves no registry
        entry and no consumable object. Every public surface — each of the eight named properties, ``repr``,
        ``hash``, ``==``, ``!=`` and ``copy``/``deepcopy``/pickle reconstruction — re-proves identity,
        registry binding and the full cryptographic derivation before it returns anything. A hollow
        ``object.__new__(RoughtimeV19CertificateVerification)`` has no registry entry and therefore fails
        closed on every one of them with exactly ``artifact_certificate_verification_inconsistent``; no
        ``KeyError``, ``LookupError``, ``ReferenceError``, ``AttributeError``, ``IndexError``, ``TypeError``,
        ``ValueError`` or backend exception escapes. No verdict is cached.

        Deliberately NO sequence or container protocol: ``len``, iteration, indexing, membership, ``count``,
        ``index``, ordering, concatenation and repetition are all inapplicable. Equality is strictly
        type-bound, so a bare ``tuple``/``list``/``dict`` carrying the same eight values is never equal to a
        proof in either direction and cannot impersonate one inside a container.

        SUPPORTED TRUST BOUNDARY (public/supported operations): hostile public inputs; wrong exact types and
        subclasses; hostile public attribute access; ordinary ``setattr``/``delattr``; explicit
        ``object.__setattr__``/``object.__delattr__`` against the artifact instance; ``object.__new__`` hollow
        exact-type instances; explicit unbound built-in base calls; public/class/instance introspection through
        ``type``, MRO, ``dir``, ``vars`` and descriptor inspection; hash/equality/dict/set consumption;
        ``copy.copy``; ``copy.deepcopy``; pickle serialization and reconstruction; malformed rebuild
        arguments; ordinary backend ``Exception`` instances; and stale-id or weakref lifecycle accidents while
        private implementation state is unmodified.

        EXCLUDED PRIVATE-STATE BOUNDARY: direct reading of private function ``__closure__`` cells; direct
        mutation of private closure-cell contents; direct acquisition or mutation of the closure-local
        registry through those cells; monkeypatching private implementation functions or constants; arbitrary
        mutation of module-private Python objects; debugger/instrumentation compromise; interpreter-memory
        modification; native memory corruption; and arbitrary same-process code execution that intentionally
        rewrites private implementation state. No claim is made that closure contents are secret or resist
        code admitted to this excluded boundary; pure Python cannot provide that guarantee.

        SEALED TYPE: closed to subclassing. Any attempt to derive from it raises a fixed repository-owned
        built-in ``TypeError`` at CLASS-DEFINITION time, before a subclass instance can exist and therefore
        before any overriding lifecycle method can run.

        NON-CLAIM: existence of this artifact carries the signature claim above and nothing else. It does NOT
        assert provider identity, ownership or provenance of the supplied key, revocation status, deployed
        protocol version, ``SREP`` validity, request inclusion, truthful time, machine-time provenance,
        quorum, readiness, or connector safety. There is deliberately no ``verified``, ``authentic``,
        ``provider``, ``time_valid`` or ``ready`` field: the type itself is the claim, and its scope is
        exactly this docstring.
        """

        # Only __weakref__ — required for the registry's lifecycle binding, and not writable, so it cannot be
        # repurposed as proof storage. No __dict__ and no data slot exist.
        __slots__ = ("__weakref__",)

        def __new__(
            cls,
            *,
            response_raw: bytes,
            long_term_public_key: bytes,
            certificate_raw: bytes,
            certificate_signature: bytes,
            delegation_raw: bytes,
            delegated_public_key: bytes,
            min_time: int,
            max_time: int,
        ) -> RoughtimeV19CertificateVerification:
            state = (
                response_raw,
                long_term_public_key,
                certificate_raw,
                certificate_signature,
                delegation_raw,
                delegated_public_key,
                min_time,
                max_time,
            )
            # Verify FIRST, then create and register: a rejected state must leave no object and no entry.
            _validate_state_tuple(state, _ARTIFACT_INCONSISTENT)
            artifact = object.__new__(cls)
            register(artifact, state)
            return artifact

        def __init_subclass__(cls, **kwargs: object) -> None:
            # Fires when a subclass is DEFINED, before it can be instantiated and therefore before any
            # overriding lifecycle method of that subclass can execute. Deterministic, no caller text.
            raise TypeError(_SEALED_ARTIFACT_MESSAGE)

        @property
        def response_raw(self) -> bytes:
            return proven_state(self)[0]

        @property
        def long_term_public_key(self) -> bytes:
            return proven_state(self)[1]

        @property
        def certificate_raw(self) -> bytes:
            return proven_state(self)[2]

        @property
        def certificate_signature(self) -> bytes:
            return proven_state(self)[3]

        @property
        def delegation_raw(self) -> bytes:
            return proven_state(self)[4]

        @property
        def delegated_public_key(self) -> bytes:
            return proven_state(self)[5]

        @property
        def min_time(self) -> int:
            return proven_state(self)[6]

        @property
        def max_time(self) -> int:
            return proven_state(self)[7]

        def __repr__(self) -> str:
            state = proven_state(self)
            rendered = ", ".join(f"{name}={state[index]!r}" for index, name in enumerate(_VERIFICATION_FIELD_NAMES))
            return f"RoughtimeV19CertificateVerification({rendered})"

        def __hash__(self) -> int:
            return hash(proven_state(self))

        def __eq__(self, other: object) -> bool:
            state = proven_state(self)
            if type(other) is not RoughtimeV19CertificateVerification:
                # Deliberately False rather than NotImplemented: a bare tuple/list/dict carrying the same
                # eight values must not compare equal to a verified proof through a reflected operation.
                return False
            return state == proven_state(other)

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __reduce__(self) -> tuple:
            """Route ``copy``/``deepcopy``/pickle through the validating public constructor.

            Returns only the eight plain values, never anything from the registry, and reconstruction runs the
            complete verification again — so a hand-crafted pickle cannot install proof state directly.
            """
            return (_rebuild_certificate_verification, (proven_state(self),))

    RoughtimeV19CertificateVerification.__qualname__ = "RoughtimeV19CertificateVerification"
    RoughtimeV19CertificateVerification.__module__ = __name__
    return RoughtimeV19CertificateVerification


RoughtimeV19CertificateVerification = _build_certificate_verification_class()


def _rebuild_certificate_verification(state: object) -> RoughtimeV19CertificateVerification:
    """Reconstruct an artifact from copy/deepcopy/pickle state by re-running the COMPLETE verification.

    Every argument shape defect and every value defect normalizes to the artifact reason; the validating
    keyword constructor is the only construction path, so no registry entry can exist before success.
    """
    if type(state) is not tuple or len(state) != len(_VERIFICATION_FIELD_NAMES):
        raise _err(_ARTIFACT_INCONSISTENT)
    return RoughtimeV19CertificateVerification(
        response_raw=state[0],
        long_term_public_key=state[1],
        certificate_raw=state[2],
        certificate_signature=state[3],
        delegation_raw=state[4],
        delegated_public_key=state[5],
        min_time=state[6],
        max_time=state[7],
    )


def verify_roughtime_v19_certificate(
    response: RoughtimeV19ResponseSemantics,
    long_term_public_key: bytes,
) -> RoughtimeV19CertificateVerification:
    """Verify the ``CERT`` delegation signature of ``response`` under an exact long-term Ed25519 public key.

    Accepts the EXACT merged K2 artifact type and exact built-in ``bytes`` only; a subclass is rejected by
    ``wrong_input_type`` before any attribute is read, so no hostile override can execute. ``response.raw`` is
    then re-parsed through the merged K2 public parser and ALL cryptographic work is performed on that fresh
    canonical artifact, never on caller-carried nested fields. The transcript is the fixed 34-byte context
    followed by the exact preserved ``DELE`` bytes; it is never reconstructed.

    Verifies only the certificate. Performs no ``SREP`` verification, no request-inclusion aggregation, no
    ``SRV`` hashing, no provider or key-provenance binding, no clock read, and causes no readiness or connector
    transition.
    """
    if type(response) is not RoughtimeV19ResponseSemantics:
        raise _err(RoughtimeV19CertificateVerificationReason.WRONG_INPUT_TYPE)
    if type(long_term_public_key) is not bytes:
        raise _err(RoughtimeV19CertificateVerificationReason.WRONG_INPUT_TYPE)
    inconsistent = RoughtimeV19CertificateVerificationReason.INPUT_ARTIFACT_INCONSISTENT
    response_raw = getattr(response, "raw", _MISSING)
    if response_raw is _MISSING or type(response_raw) is not bytes:
        raise _err(inconsistent)
    (
        certificate_raw,
        certificate_signature,
        delegation_raw,
        delegated_public_key,
        min_time,
        max_time,
    ) = _verified_state(response_raw, long_term_public_key, inconsistent)
    return RoughtimeV19CertificateVerification(
        response_raw=response_raw,
        long_term_public_key=long_term_public_key,
        certificate_raw=certificate_raw,
        certificate_signature=certificate_signature,
        delegation_raw=delegation_raw,
        delegated_public_key=delegated_public_key,
        min_time=min_time,
        max_time=max_time,
    )


__all__ = [
    "ROUGHTIME_V19_CERTIFICATE_VERIFICATION_PROFILE_ID",
    "RoughtimeV19CertificateVerification",
    "RoughtimeV19CertificateVerificationError",
    "RoughtimeV19CertificateVerificationReason",
    "verify_roughtime_v19_certificate",
]
