"""Roughtime draft-19 bounded SIGNED-RESPONSE (SREP) signature verifier (internal MT-4 prerequisite K5-SREP).

This module layers ONE additional cryptographic signature check on top of the merged K5 certificate verifier
(:mod:`crypto_core.validation.roughtime_v19_certificate_verification`). K5 proves that a ``CERT`` delegation
signature validates under a caller-supplied long-term key; this module answers exactly one further closed
question: does the OUTER response ``SIG`` validate, under the DELEGATED public key that the verified K5
artifact carries, over the exact ``SREP`` value bytes that a fresh K2 parse of the same response preserved?

Bounded profile (honest scope): ONE governance-selected, versioned profile, identified by
:data:`ROUGHTIME_V19_SIGNED_RESPONSE_VERIFICATION_PROFILE_ID`
(``"roughtime-v19-signed-response-verification-bounded-k5-srep.v1"``). It inherits the K1 structural bounds,
the K2 semantic bounds and the K5 certificate bounds unchanged and adds no new byte-size ceiling of its own.

Normative transcript (the only message this module ever verifies)::

    SREP_CONTEXT = b"RoughTime v1 response signature\\x00"   # 32 bytes, trailing NUL is part of the input
    transcript   = SREP_CONTEXT + signed_response.raw        # exact preserved SREP value bytes

The ``SREP`` bytes are taken verbatim from a freshly re-parsed K2 artifact and are NEVER reconstructed,
re-encoded or normalized from decoded fields, and the outer packet framing is never included. Algorithm is
Ed25519 / PureEdDSA (RFC 8032): no Ed25519ctx, no Ed25519ph, no prehash, and no hashing of the transcript
before verification.

KEY ROLE. The outer ``SIG`` is verified under the DELEGATED public key only — never under the long-term key.
The delegated key is not taken on trust from the caller: ``response_raw`` is re-parsed through the merged K2
public parser and the canonical ``DELE`` ``PUBK`` must equal the K5 artifact's ``delegated_public_key``, and
the canonical response raw must equal the K5 artifact's ``response_raw``, before any signature work happens.

Defence in depth before the backend is called, independently implemented here and NOT imported from K5: exact
built-in ``bytes`` types; delegated public key exactly 32 bytes and signature exactly 64; canonical encoding
of the public key ``A`` and of the signature point ``R`` (clear the sign bit, require the encoded
y-coordinate < 2**255 - 19); the signature scalar ``S`` read little-endian and required to be strictly below
the group order ``L``; and rejection of the complete documented small-order encoding inventory for BOTH ``A``
and ``R``, comparing bytes 0..30 verbatim and byte 31 masked with ``0x7f``. These private checks are
additional fail-closed policy, never a replacement verifier — the final group equation is delegated to the
pinned PyNaCl backend.

Trust boundary: this module consumes an artifact it did not build. It requires the EXACT merged K5 public type
(``type(x) is C``, never ``isinstance``), which alone rejects every subclass and so prevents a hostile
``__getattribute__``/``__new__`` override from executing. Reading the K5 artifact's public properties re-runs
K5's own complete revalidation, so a hollow or forged K5 instance fails closed before this module does any
work. No private K5 symbol — helper, constant, registry or rebuild hook — is imported.

Output representation: the returned artifact is a SEALED NON-CONTAINER object that inherits directly from
``object``, stores no proof state on the instance at all, and holds its verified values in a closure-local,
non-module-global registry bound to one exact object identity and guarded by a weak reference. A frozen
dataclass would keep a writable instance ``__dict__``; a ``tuple`` subclass would keep the values in a base
object that explicit unbound base calls (``tuple.__getitem__`` and friends) read without validation. Keeping
no proof in the instance removes both surfaces structurally rather than blacklisting methods. Because
``object.__new__`` can still fabricate a hollow exact-type instance, EVERY public surface — each named
property, ``repr``, ``hash``, ``==``, ``!=``, ``bool``/truthiness and ``copy``/``deepcopy``/pickle
reconstruction — re-proves exact type, identity-bound registry membership, weak-reference liveness and the
COMPLETE cryptographic derivation before it returns anything.

Supported trust boundary (Option A): public inputs and public API operations; ``object.__new__`` hollow
instances; ``object.__setattr__``/``object.__delattr__`` against the artifact; explicit built-in base calls;
public introspection; hash/equality/dict/set; copy/deepcopy/pickle; malformed rebuild arguments; ordinary
backend ``Exception`` instances; and stale-id or weakref lifecycle accidents while private implementation
state is unmodified. EXCLUDED and NOT claimed: direct private ``__closure__`` inspection or mutation; direct
acquisition or mutation of the closure-local registry through those cells; monkeypatching private
implementation functions or constants; arbitrary module-private mutation; debugger, interpreter or
native-memory compromise. No closure-secrecy claim is made.

A successful artifact proves EXACTLY:

* the outer response ``SIG`` validates under the delegated public key carried by the verified K5 artifact;
* that signature covers the exact preserved ``SREP`` raw bytes of the same response;
* the signed ``ROOT``/``MIDP``/``RADI``/``VER``/``VERS`` values are the exact K2-decoded values carried by
  those signed bytes;
* the delegated key and response bytes are consistent between the K5 artifact and a fresh K2 reparse;
* K5 has already established that the ``CERT`` delegation signature validates under its supplied long-term
  key, and that claim is re-proven here whenever the artifact is consumed, so every stored value stays
  cryptographically bound rather than merely carried.

It proves NOTHING about: provider identity; provider ownership of the supplied long-term key; key provenance;
root-key admission; key revocation; deployed protocol version; whether ``ROOT`` contains any particular
request; ``NONC`` correlation with a request; K4 request inclusion; truthful or authenticated time;
machine-time provenance; quorum; readiness; connector safety; reachability; operational approval; or any
private/live/order/capital capability. A successful artifact under an unauthenticated long-term key proves
self-consistency of the signature chain only, never identity and never truthful time.

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

from crypto_core.validation.roughtime_v19_certificate_verification import (
    RoughtimeV19CertificateVerification,
)
from crypto_core.validation.roughtime_v19_response_semantics import (
    RoughtimeV19ResponseSemanticError,
    parse_roughtime_v19_response,
)

# --- Verification profile (governance-selected, versioned; inherits K1/K2/K5 bounds unchanged) --------------
ROUGHTIME_V19_SIGNED_RESPONSE_VERIFICATION_PROFILE_ID = "roughtime-v19-signed-response-verification-bounded-k5-srep.v1"

# --- Normative transcript constants -----------------------------------------------------------------------
# The trailing NUL is part of the signed input. Omitting it changes the transcript and MUST fail.
# 32 bytes total: 31 ASCII characters plus the terminating NUL.
_SREP_CONTEXT = b"RoughTime v1 response signature\x00"

# The CERT context is public draft-19 protocol data, restated here (never imported from K5) so this module can
# independently RE-PROVE the certificate claim whenever it revalidates its own artifact. That re-proof exists
# only to keep the carried `long_term_public_key` field cryptographically bound; it introduces no new public
# claim and this module still verifies exactly one NEW signature layer, the outer response SIG.
_CERT_CONTEXT = b"RoughTime v1 delegation signature\x00"

# --- Ed25519 hardening constants (RFC 8032), implemented independently of K5 -------------------------------
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
# inventory is exactly seven entries. Pinned here independently of K5 so neither module proves the other's
# inventory. libsodium compares bytes 0..30 exactly and byte 31 masked with 0x7f; _is_small_order mirrors that.
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
#
# Justification, field by field (smallest set that lets a LATER aggregate re-prove this layer without
# reopening it, and without overclaiming):
#   response_raw          - the exact complete packet these claims are about; the sole response source, and
#                           the input every re-derivation starts from.
#   long_term_public_key  - the key the CERT layer was proven under; required so an aggregate can bind this
#                           SREP proof to the same certificate chain. Re-proven cryptographically on every
#                           consumption, never merely carried.
#   delegated_public_key  - the key the outer SIG was verified under; the load-bearing key of THIS layer.
#   signed_response_raw   - the exact preserved SREP value bytes the signature actually covers.
#   response_signature    - the exact 64-byte outer SIG that was verified.
#   signed_root           - ROOT inside the signed SREP; an aggregate needs it to later test request
#                           inclusion. Carrying it proves only that it is signed, never that it contains
#                           any particular request.
#   signed_midpoint       - MIDP inside the signed SREP. Signed, NOT truthful.
#   signed_radius         - RADI inside the signed SREP. Signed, NOT truthful.
#   signed_version        - the selected VER inside the signed SREP. Signed, NOT a deployed-version claim.
#   signed_versions       - the VERS inventory K2 decoded from the signed SREP. Signed, NOT a deployed-version
#                           or negotiation claim.
_VERIFICATION_FIELD_NAMES = (
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

_ERROR_REASON_TYPE_MESSAGE = (
    "RoughtimeV19SignedResponseVerificationError requires a RoughtimeV19SignedResponseVerificationReason member"
)
_ERROR_IMMUTABLE_MESSAGE = "RoughtimeV19SignedResponseVerificationError blocks ordinary attribute mutation"
_ERROR_LOCKED_ATTRS = frozenset({"reason", "_reason", "args"})
_SEALED_ARTIFACT_MESSAGE = "RoughtimeV19SignedResponseVerification is a sealed artifact type and cannot be subclassed"


class RoughtimeV19SignedResponseVerificationReason(str, Enum):
    """Closed failure inventory: exactly six members, evaluated in the pinned precedence below.

    Deliberately coarse: whether a rejection came from canonicality, small-order membership, the scalar bound,
    a wrong context, a missing NUL, a mutated transcript, a signature mismatch or a backend refusal is NOT
    distinguishable through the public reason, so the verifier leaks no oracle about which step fired.
    """

    WRONG_INPUT_TYPE = "wrong_input_type"
    INPUT_ARTIFACT_INCONSISTENT = "input_artifact_inconsistent"
    DELEGATED_PUBLIC_KEY_INVALID = "delegated_public_key_invalid"
    SREP_SIGNATURE_INVALID = "srep_signature_invalid"
    CRYPTO_BACKEND_FAILURE = "crypto_backend_failure"
    ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT = "artifact_signed_response_verification_inconsistent"


# The single reason every artifact-state defect normalizes to, on construction and on every consumption
# surface. Bound once so no surface can drift onto a different (more informative, oracle-leaking) reason.
_ARTIFACT_INCONSISTENT = RoughtimeV19SignedResponseVerificationReason.ARTIFACT_SIGNED_RESPONSE_VERIFICATION_INCONSISTENT


class RoughtimeV19SignedResponseVerificationError(RuntimeError):
    """Raised for every signed-response-verification failure, carrying exactly one closed reason.

    The constructor accepts ONLY an exact :class:`RoughtimeV19SignedResponseVerificationReason` member. Any
    other argument raises a plain built-in ``TypeError`` before any attribute of that argument (in particular
    ``.value``) is read, so a hostile ``.value`` property can never run. ``str(error)`` is always exactly
    ``reason.value`` and no caller message is ever accepted.

    Scope of the immutability guarantee: ORDINARY attribute assignment and deletion through this class's
    public surface are blocked. This is not a claim of immunity to explicit ``object.__setattr__`` /
    ``object.__delattr__``, which bypass this class's hooks by design; the error object is a diagnostic
    carrier, not a proof artifact.
    """

    def __init__(self, reason: RoughtimeV19SignedResponseVerificationReason) -> None:
        if type(reason) is not RoughtimeV19SignedResponseVerificationReason:
            raise TypeError(_ERROR_REASON_TYPE_MESSAGE)
        object.__setattr__(self, "_reason", reason)
        super().__init__(reason.value)

    @property
    def reason(self) -> RoughtimeV19SignedResponseVerificationReason:
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
    reason: RoughtimeV19SignedResponseVerificationReason,
) -> RoughtimeV19SignedResponseVerificationError:
    return RoughtimeV19SignedResponseVerificationError(reason)


# --- Private Ed25519 encoding hardening (policy only; never the group-equation verifier) -------------------


def _is_canonical_point(encoding: bytes) -> bool:
    """Return whether a 32-byte point encoding carries a canonical y-coordinate (y < p, sign bit ignored)."""
    masked = bytearray(encoding)
    masked[31] &= _SIGN_BIT_MASK
    return int.from_bytes(bytes(masked), "little") < _FIELD_PRIME


def _is_small_order(encoding: bytes) -> bool:
    """Return whether a 32-byte point encoding is in the documented small-order inventory.

    Mirrors libsodium's ge25519_has_small_order exactly: bytes 0..30 compared verbatim and byte 31 compared
    with the sign bit masked off, so toggling byte 31's high bit cannot smuggle a small-order point through.
    """
    head = encoding[:31]
    tail = encoding[31] & _SIGN_BIT_MASK
    for candidate in _SMALL_ORDER_ENCODINGS:
        if head == candidate[:31] and tail == (candidate[31] & _SIGN_BIT_MASK):
            return True
    return False


def _public_key_rejected(public_key: bytes) -> bool:
    """Return whether a public key fails repository policy before the backend is reached."""
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


def _verify_detached(
    transcript: bytes,
    public_key: bytes,
    signature: bytes,
    invalid: RoughtimeV19SignedResponseVerificationReason,
) -> None:
    """Delegate the final Ed25519 group-equation check to the pinned backend, normalizing every failure.

    Argument order is fixed: ``VerifyKey(public_key, encoder=RawEncoder).verify(message, signature)``. All
    lengths and encodings were already proven by policy above, so a backend refusal here means the signature
    does not validate; anything else is reported as a backend failure rather than leaking.
    """
    try:
        VerifyKey(public_key, encoder=RawEncoder).verify(transcript, signature)
    except BadSignatureError:
        raise _err(invalid) from None
    except NaclValueError:
        raise _err(invalid) from None
    except Exception:
        # The ONLY broad catch in this module, deliberately scoped to the two external backend calls above and
        # placed AFTER the two signature-invalid classes so it can never mask a real verification verdict. An
        # enumerated handler list is not sufficient here: the backend is third-party native code, so any
        # unexpected class it raises (AttributeError, IndexError, builtins.ValueError, OSError, a custom
        # exception, ...) must still normalize instead of escaping raw through a cryptographic boundary.
        # BaseException is NOT caught, so KeyboardInterrupt and SystemExit still propagate. K2 parsing,
        # transcript construction and all registry/artifact logic live outside this block.
        raise _err(RoughtimeV19SignedResponseVerificationReason.CRYPTO_BACKEND_FAILURE) from None


# --- Shared verification core (used by the entry point and by artifact self-validation) --------------------


def _verified_state(
    response_raw: bytes,
    long_term_public_key: bytes,
    delegated_public_key: bytes,
    inconsistent: RoughtimeV19SignedResponseVerificationReason,
) -> tuple[bytes, bytes, bytes, int, int, int, tuple[int, ...]]:
    """Re-parse the response, re-run every check, and return the seven derived artifact values.

    Nothing here trusts a caller-carried nested field: the canonical K2 artifact is produced fresh from
    ``response_raw`` on every call, including during artifact self-validation, so no stored verdict is ever
    believed. The delegated key is re-bound to the canonical ``DELE`` ``PUBK`` before any signature work, and
    the outer ``SIG`` is verified under that delegated key only — never under the long-term key.
    """
    try:
        canonical = parse_roughtime_v19_response(response_raw)
    except RoughtimeV19ResponseSemanticError:
        raise _err(inconsistent) from None
    if _public_key_rejected(delegated_public_key):
        raise _err(RoughtimeV19SignedResponseVerificationReason.DELEGATED_PUBLIC_KEY_INVALID)
    # No `canonical.raw != response_raw` guard: K2 sets `raw` to exactly the bytes it parsed, so that branch is
    # unreachable by construction. An unreachable guard in a cryptographic boundary cannot be causally proven
    # and would only create the appearance of a check, so the reparse itself IS the binding.
    certificate = canonical.certificate
    delegation = certificate.delegation
    if delegation.pubk != delegated_public_key:
        raise _err(inconsistent)
    # Re-prove the CERT layer so the carried long-term key stays cryptographically bound. This adds no public
    # claim; it is the binding step for a field this module stores but did not itself originate.
    if _public_key_rejected(long_term_public_key) or _signature_rejected(certificate.signature):
        raise _err(inconsistent)
    _verify_detached(
        _CERT_CONTEXT + delegation.raw,
        long_term_public_key,
        certificate.signature,
        inconsistent,
    )
    signed_response = canonical.signed_response
    response_signature = canonical.signature
    if _signature_rejected(response_signature):
        raise _err(RoughtimeV19SignedResponseVerificationReason.SREP_SIGNATURE_INVALID)
    _verify_detached(
        _SREP_CONTEXT + signed_response.raw,
        delegated_public_key,
        response_signature,
        RoughtimeV19SignedResponseVerificationReason.SREP_SIGNATURE_INVALID,
    )
    return (
        signed_response.raw,
        response_signature,
        signed_response.root,
        signed_response.midpoint_seconds,
        signed_response.radius_seconds,
        signed_response.version,
        signed_response.versions,
    )


def _validate_state_tuple(
    state: object,
    reason: RoughtimeV19SignedResponseVerificationReason,
) -> None:
    """Prove a candidate ten-value state is exactly shaped, exactly typed and cryptographically re-derivable.

    Operates on a plain built-in ``tuple`` and never on the artifact object, so it cannot recurse through any
    public artifact surface. The first three values (``response_raw``, ``long_term_public_key`` and
    ``delegated_public_key``) are the only values trusted as *inputs*; the remaining seven are re-derived from
    them by re-running the COMPLETE verification — fresh K2 parse, delegated-key rebinding, key and signature
    policy, the CERT re-proof and the SREP group equation — and must match exactly. Nothing is cached.
    """
    if type(state) is not tuple:
        raise _err(reason)
    if len(state) != len(_VERIFICATION_FIELD_NAMES):
        raise _err(reason)
    (
        response_raw,
        long_term_public_key,
        delegated_public_key,
        signed_response_raw,
        response_signature,
        signed_root,
        signed_midpoint,
        signed_radius,
        signed_version,
        signed_versions,
    ) = state
    for candidate in (
        response_raw,
        long_term_public_key,
        delegated_public_key,
        signed_response_raw,
        response_signature,
        signed_root,
    ):
        if type(candidate) is not bytes:
            raise _err(reason)
    for number in (signed_midpoint, signed_radius, signed_version):
        if type(number) is not int:
            raise _err(reason)
    if type(signed_versions) is not tuple:
        raise _err(reason)
    for version in signed_versions:
        if type(version) is not int:
            raise _err(reason)
    try:
        expected = _verified_state(response_raw, long_term_public_key, delegated_public_key, reason)
    except RoughtimeV19SignedResponseVerificationError:
        raise _err(reason) from None
    if (
        signed_response_raw,
        response_signature,
        signed_root,
        signed_midpoint,
        signed_radius,
        signed_version,
        signed_versions,
    ) != expected:
        raise _err(reason)


# --- Sealed non-container public artifact with a closure-local identity registry ---------------------------


def _build_signed_response_verification_class() -> type:
    """Create the public artifact class over a closure-local, non-module-global registry.

    The verified values must live somewhere a caller can neither read through the object nor reach as
    ordinary module state, so the registry is bound in this closure and no production registry hook is
    exported. Inheriting straight from :class:`object` and keeping no proof in the instance means there is no
    storage for an explicit unbound built-in base call to read, so that escape is structurally absent rather
    than blacklisted method by method.
    """
    # id(artifact) -> (weakref.ref(artifact, on_death), ten-value state tuple).
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
        if type(artifact) is not RoughtimeV19SignedResponseVerification:
            raise _err(_ARTIFACT_INCONSISTENT)
        entry = registry.get(id(artifact))
        if entry is None:
            raise _err(_ARTIFACT_INCONSISTENT)
        reference, state = entry
        if reference() is not artifact:
            raise _err(_ARTIFACT_INCONSISTENT)
        _validate_state_tuple(state, _ARTIFACT_INCONSISTENT)
        return state

    class RoughtimeV19SignedResponseVerification:
        """Proof that one exact outer response ``SIG`` validates over one exact ``SREP`` under one delegated key.

        Carries the exact complete ``response_raw`` packet bytes, the ``long_term_public_key`` the certificate
        layer was proven under, the ``delegated_public_key`` this layer verified the outer ``SIG`` under, the
        exact signed ``signed_response_raw`` bytes, the exact 64-byte ``response_signature``, and the
        ``signed_root``/``signed_midpoint``/``signed_radius``/``signed_version``/``signed_versions`` values
        that K2 decoded from those signed bytes.

        NOT A CONTAINER. It inherits directly from :class:`object` and stores NOTHING on the instance: there
        is no ``__dict__`` and the only slot is ``__weakref__`` (itself a read-only descriptor). The verified
        values live in a closure-local, non-module-global registry bound to one exact object identity and
        guarded by a weak reference. Consequently ``setattr``, ``delattr``, ``object.__setattr__``,
        ``object.__delattr__`` and ``__dict__`` assignment all fail, no attribute can be added, ``hash`` and
        equality are fixed at construction, and explicit unbound base calls such as ``tuple.__getitem__`` are
        simply inapplicable to this type and raise an ordinary ``TypeError`` without exposing anything.

        Construction re-runs the COMPLETE verification BEFORE the object is registered, so a failed
        construction leaves no registry entry and no consumable object. Every public surface — each named
        property, ``repr``, ``hash``, ``==``, ``!=``, ``bool``/truthiness and
        ``copy``/``deepcopy``/pickle reconstruction — re-proves identity, registry binding and the full
        cryptographic derivation before returning anything.
        A hollow ``object.__new__(RoughtimeV19SignedResponseVerification)`` has no registry entry and fails
        closed on every one of them with exactly ``artifact_signed_response_verification_inconsistent``; no
        ``KeyError``, ``LookupError``, ``ReferenceError``, ``AttributeError``, ``IndexError``, ``TypeError``,
        ``ValueError`` or backend exception escapes. No verdict is cached.

        Deliberately NO sequence or container protocol: ``len``, iteration, indexing, membership, ``count``,
        ``index``, ordering, concatenation and repetition are all inapplicable. Equality is strictly
        type-bound, so a bare ``tuple``/``list``/``dict`` carrying the same values is never equal to a proof.

        SEALED TYPE: closed to subclassing. Any attempt to derive from it raises a fixed repository-owned
        built-in ``TypeError`` at CLASS-DEFINITION time, before a subclass instance can exist.

        NON-CLAIM: the signed values are SIGNED, not TRUE. ``signed_midpoint``/``signed_radius`` are not a
        truthful-time claim, ``signed_version``/``signed_versions`` are not a deployed-version claim, and
        ``signed_root`` is not a request-inclusion claim. This artifact does NOT assert provider identity,
        key ownership or provenance, root-key admission, revocation, ``NONC`` correlation, K4 inclusion,
        quorum, machine-time provenance, readiness, or connector safety. There is deliberately no
        ``verified``, ``authentic``, ``provider``, ``time_valid``, ``ready`` or ``quorum`` field: the type
        itself is the claim, and its scope is exactly this docstring.
        """

        # Only __weakref__ — required for the registry's lifecycle binding, and not writable, so it cannot be
        # repurposed as proof storage. No __dict__ and no data slot exist.
        __slots__ = ("__weakref__",)

        def __new__(
            cls,
            *,
            response_raw: bytes,
            long_term_public_key: bytes,
            delegated_public_key: bytes,
            signed_response_raw: bytes,
            response_signature: bytes,
            signed_root: bytes,
            signed_midpoint: int,
            signed_radius: int,
            signed_version: int,
            signed_versions: tuple[int, ...],
        ) -> RoughtimeV19SignedResponseVerification:
            state = (
                response_raw,
                long_term_public_key,
                delegated_public_key,
                signed_response_raw,
                response_signature,
                signed_root,
                signed_midpoint,
                signed_radius,
                signed_version,
                signed_versions,
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
        def delegated_public_key(self) -> bytes:
            return proven_state(self)[2]

        @property
        def signed_response_raw(self) -> bytes:
            return proven_state(self)[3]

        @property
        def response_signature(self) -> bytes:
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

        def __bool__(self) -> bool:
            proven_state(self)
            return True

        def __repr__(self) -> str:
            state = proven_state(self)
            rendered = ", ".join(f"{name}={state[index]!r}" for index, name in enumerate(_VERIFICATION_FIELD_NAMES))
            return f"RoughtimeV19SignedResponseVerification({rendered})"

        def __hash__(self) -> int:
            return hash(proven_state(self))

        def __eq__(self, other: object) -> bool:
            state = proven_state(self)
            if type(other) is not RoughtimeV19SignedResponseVerification:
                # Deliberately False rather than NotImplemented: a bare tuple/list/dict carrying the same
                # values must not compare equal to a verified proof through a reflected operation.
                return False
            return state == proven_state(other)

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __reduce__(self) -> tuple:
            """Route ``copy``/``deepcopy``/pickle through the validating public constructor.

            Returns only the plain values, never anything from the registry, and reconstruction runs the
            complete verification again — so a hand-crafted pickle cannot install proof state directly.
            """
            return (_rebuild_signed_response_verification, (proven_state(self),))

    RoughtimeV19SignedResponseVerification.__qualname__ = "RoughtimeV19SignedResponseVerification"
    RoughtimeV19SignedResponseVerification.__module__ = __name__
    return RoughtimeV19SignedResponseVerification


RoughtimeV19SignedResponseVerification = _build_signed_response_verification_class()


def _rebuild_signed_response_verification(state: object) -> RoughtimeV19SignedResponseVerification:
    """Reconstruct an artifact from copy/deepcopy/pickle state by re-running the COMPLETE verification.

    Every argument shape defect and every value defect normalizes to the artifact reason; the validating
    keyword constructor is the only construction path, so no registry entry can exist before success.
    """
    if type(state) is not tuple or len(state) != len(_VERIFICATION_FIELD_NAMES):
        raise _err(_ARTIFACT_INCONSISTENT)
    return RoughtimeV19SignedResponseVerification(
        response_raw=state[0],
        long_term_public_key=state[1],
        delegated_public_key=state[2],
        signed_response_raw=state[3],
        response_signature=state[4],
        signed_root=state[5],
        signed_midpoint=state[6],
        signed_radius=state[7],
        signed_version=state[8],
        signed_versions=state[9],
    )


def verify_roughtime_v19_signed_response(
    certificate_verification: RoughtimeV19CertificateVerification,
) -> RoughtimeV19SignedResponseVerification:
    """Verify the outer response ``SIG`` over the exact ``SREP`` under the verified delegated public key.

    Accepts the EXACT merged K5 artifact type only; a subclass is rejected by ``wrong_input_type`` before any
    attribute is read, so no hostile override can execute. Reading the K5 artifact's public properties re-runs
    K5's own complete revalidation, so a hollow or forged K5 instance fails closed here. ``response_raw`` is
    then re-parsed through the merged K2 public parser and ALL cryptographic work is performed on that fresh
    canonical artifact, never on caller-carried nested fields. The transcript is the fixed 32-byte response
    context followed by the exact preserved ``SREP`` bytes; it is never reconstructed.

    Verifies only the outer response signature. Performs no request-inclusion aggregation, no ``SRV`` hashing,
    no provider or key-provenance binding, no root-key admission, no clock read, no quorum evaluation, and
    causes no readiness or connector transition.
    """
    if type(certificate_verification) is not RoughtimeV19CertificateVerification:
        raise _err(RoughtimeV19SignedResponseVerificationReason.WRONG_INPUT_TYPE)
    inconsistent = RoughtimeV19SignedResponseVerificationReason.INPUT_ARTIFACT_INCONSISTENT
    try:
        response_raw = getattr(certificate_verification, "response_raw", _MISSING)
        long_term_public_key = getattr(certificate_verification, "long_term_public_key", _MISSING)
        delegated_public_key = getattr(certificate_verification, "delegated_public_key", _MISSING)
    except Exception:
        # A hollow or inconsistent K5 artifact raises its OWN closed error on property access; normalize it to
        # this module's input-artifact reason rather than leaking another module's exception type.
        raise _err(inconsistent) from None
    for candidate in (response_raw, long_term_public_key, delegated_public_key):
        if candidate is _MISSING or type(candidate) is not bytes:
            raise _err(inconsistent)
    (
        signed_response_raw,
        response_signature,
        signed_root,
        signed_midpoint,
        signed_radius,
        signed_version,
        signed_versions,
    ) = _verified_state(response_raw, long_term_public_key, delegated_public_key, inconsistent)
    return RoughtimeV19SignedResponseVerification(
        response_raw=response_raw,
        long_term_public_key=long_term_public_key,
        delegated_public_key=delegated_public_key,
        signed_response_raw=signed_response_raw,
        response_signature=response_signature,
        signed_root=signed_root,
        signed_midpoint=signed_midpoint,
        signed_radius=signed_radius,
        signed_version=signed_version,
        signed_versions=signed_versions,
    )


__all__ = [
    "ROUGHTIME_V19_SIGNED_RESPONSE_VERIFICATION_PROFILE_ID",
    "RoughtimeV19SignedResponseVerification",
    "RoughtimeV19SignedResponseVerificationError",
    "RoughtimeV19SignedResponseVerificationReason",
    "verify_roughtime_v19_signed_response",
]
