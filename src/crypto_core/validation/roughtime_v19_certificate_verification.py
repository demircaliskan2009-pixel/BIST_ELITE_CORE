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

Output representation: the artifact this module returns is a SEALED, TUPLE-BACKED value object with
``__slots__ = ()``, so it has no instance ``__dict__`` and no writable slot at all. A frozen dataclass only
intercepts ``__setattr__`` while still carrying a writable instance namespace, which lets a caller replace a
cryptographically derived field AFTER verification succeeded and thereby invalidate the type-as-proof
contract, equality, hashing and dict/set membership. Storing the eight values in the immutable tuple base
removes that surface by construction rather than by interception: there is nothing to write through
``setattr``, through ``object.__setattr__`` or through ``__dict__``. Because ``tuple.__new__`` can still
fabricate an exact-type instance that bypasses the public keyword constructor, EVERY consumption surface
(each named field, ``repr``, ``hash``, equality, iteration, indexing, copy, deepcopy and pickle) re-proves the
complete state before it returns anything, using only base ``tuple`` operations so validation cannot recurse.

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

from enum import Enum

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
# order. This tuple IS the storage layout: index i of the artifact's tuple base holds field i below, and a
# valid artifact holds exactly this many elements and nothing else.
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
    ``.value``) is read, so a hostile ``.value`` property can never run. Once constructed the error is
    immutable and ``str(error)`` is always exactly ``reason.value``. No caller message is ever accepted.
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
    except (TypeError, RuntimeError):
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


def _validate_verification_state(
    obj: object,
    reason: RoughtimeV19CertificateVerificationReason,
) -> None:
    """Prove an exact-type artifact's COMPLETE stored state equals an independent re-derivation.

    This is the ONLY gate every consumption surface passes through, so it must hold for a hollow instance
    fabricated by ``tuple.__new__`` exactly as it holds for one built by the public keyword constructor. The
    exact-type gate rejects a foreign object handed to this function directly. The tuple length is then proven
    to be exactly the declared field count, which — combined with ``__slots__ = ()`` and the immutable tuple
    base — makes extra artifact state IMPOSSIBLE rather than merely detectable: there is no instance
    namespace to smuggle an overclaim, a private cache or a foreign key into. Only afterwards is every element
    read, exact-typed and re-derived by re-running the FULL verification from ``response_raw`` and
    ``long_term_public_key`` alone.

    Every read here goes through the ``tuple`` base (``tuple.__len__``/``tuple.__getitem__``) and never
    through the artifact's own named properties, ``__len__`` or ``__getitem__``, so validation can never
    recurse into itself.
    """
    if type(obj) is not RoughtimeV19CertificateVerification:
        raise _err(reason)
    if tuple.__len__(obj) != len(_VERIFICATION_FIELD_NAMES):
        raise _err(reason)
    values = [tuple.__getitem__(obj, index) for index in range(len(_VERIFICATION_FIELD_NAMES))]
    (
        response_raw,
        long_term_public_key,
        certificate_raw,
        certificate_signature,
        delegation_raw,
        delegated_public_key,
        min_time,
        max_time,
    ) = values
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


# --- Immutable, self-validating public artifact ------------------------------------------------------------


class RoughtimeV19CertificateVerification(tuple):
    """Proof that one exact ``CERT`` signature validates over one exact ``DELE`` under one supplied key.

    Carries the exact complete ``response_raw`` packet bytes, the exact 32-byte ``long_term_public_key`` the
    caller supplied, the exact preserved ``certificate_raw`` and 64-byte ``certificate_signature``, the exact
    signed ``delegation_raw``, and the ``delegated_public_key``/``min_time``/``max_time`` that K2 decoded from
    those signed bytes.

    GENUINELY IMMUTABLE, not merely write-intercepted. The eight values live in the immutable ``tuple`` base
    and are exposed only through read-only properties; ``__slots__ = ()`` means there is no instance
    ``__dict__`` and no writable slot. Consequently ``setattr``, ``delattr``, ``object.__setattr__``,
    ``object.__delattr__`` and ``__dict__`` assignment cannot alter a verified field, no attribute can be added
    dynamically, and ``hash``/equality are permanently fixed at construction. A frozen dataclass would keep a
    writable instance namespace and so permit exactly that post-verification mutation.

    Construction through the public keyword constructor re-parses ``response_raw`` and re-runs the COMPLETE
    verification — key policy, signature-encoding policy and the backend group equation — then requires every
    stored element to equal the re-derivation, so no invalid instance is ever returned. Because
    ``tuple.__new__`` can fabricate an exact-type instance that bypasses that constructor, EVERY surface that
    exposes a stored element re-proves the complete state first: each of the eight named properties, ``repr``,
    ``hash``, ``==``, ``!=``, membership, ``count``, ``index``, iteration, indexing, ``__getnewargs__`` and
    ``copy``/``deepcopy``/pickle reconstruction. Any mismatch, wrong length, non-exact element type, malformed
    raw, or hollow object raises ``artifact_certificate_verification_inconsistent`` — never a leaked
    ``IndexError``, ``AttributeError``, ``TypeError``, ``ValueError`` or backend exception. No verdict is
    cached: nothing mutable is stored. ``len()`` is deliberately the base implementation because it reveals a
    element count and never a proof value.

    Inherited sequence behaviour that would read stored elements WITHOUT re-proving them, or would decant a
    proof into a bare sequence, is refused rather than inherited: ``<``/``<=``/``>``/``>=`` and
    ``+``/``*`` return ``NotImplemented`` (so Python raises its ordinary ``TypeError``), and ``!=`` is defined
    explicitly because ``tuple`` supplies one that would otherwise bypass the validating ``__eq__``.

    Equality is strictly type-bound. A bare ``tuple`` carrying the same eight values is NOT equal to this
    proof in either direction, so a plain sequence can never impersonate a verified artifact in a container.

    SEALED TYPE: closed to subclassing. Any attempt to derive from it raises a fixed repository-owned built-in
    ``TypeError`` at CLASS-DEFINITION time, before any subclass instance can exist and therefore before any
    overriding lifecycle method can run.

    NON-CLAIM: existence of this artifact carries the signature claim above and nothing else. It does NOT
    assert provider identity, ownership or provenance of the supplied key, revocation status, deployed
    protocol version, ``SREP`` validity, request inclusion, truthful time, machine-time provenance, quorum,
    readiness, or connector safety. There is deliberately no ``verified``, ``authentic``, ``provider``,
    ``time_valid`` or ``ready`` field: the type itself is the claim, and its scope is exactly this docstring.
    """

    __slots__ = ()

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
        instance = tuple.__new__(
            cls,
            (
                response_raw,
                long_term_public_key,
                certificate_raw,
                certificate_signature,
                delegation_raw,
                delegated_public_key,
                min_time,
                max_time,
            ),
        )
        _validate_verification_state(instance, _ARTIFACT_INCONSISTENT)
        return instance

    def __init_subclass__(cls, **kwargs: object) -> None:
        # Fires when a subclass is DEFINED, before it can be instantiated and therefore before any overriding
        # lifecycle method of that subclass can execute. Deterministic, no caller-supplied text.
        raise TypeError(_SEALED_ARTIFACT_MESSAGE)

    def _proven_element(self, index: int) -> object:
        """Re-prove the complete state, then return one stored element through the ``tuple`` base."""
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return tuple.__getitem__(self, index)

    @property
    def response_raw(self) -> bytes:
        return self._proven_element(0)

    @property
    def long_term_public_key(self) -> bytes:
        return self._proven_element(1)

    @property
    def certificate_raw(self) -> bytes:
        return self._proven_element(2)

    @property
    def certificate_signature(self) -> bytes:
        return self._proven_element(3)

    @property
    def delegation_raw(self) -> bytes:
        return self._proven_element(4)

    @property
    def delegated_public_key(self) -> bytes:
        return self._proven_element(5)

    @property
    def min_time(self) -> int:
        return self._proven_element(6)

    @property
    def max_time(self) -> int:
        return self._proven_element(7)

    def __repr__(self) -> str:
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        rendered = ", ".join(
            f"{name}={tuple.__getitem__(self, index)!r}" for index, name in enumerate(_VERIFICATION_FIELD_NAMES)
        )
        return f"RoughtimeV19CertificateVerification({rendered})"

    def __hash__(self) -> int:
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return tuple.__hash__(self)

    def __eq__(self, other: object) -> bool:
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        if type(other) is not RoughtimeV19CertificateVerification:
            # Deliberately False rather than NotImplemented: a bare tuple of the same eight values must not
            # compare equal to a verified proof through the reflected operation either.
            return False
        _validate_verification_state(other, _ARTIFACT_INCONSISTENT)
        return tuple.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        # MUST be explicit: `tuple` supplies its own __ne__, which would otherwise compare raw stored elements
        # and let `forged != genuine` answer from UNVALIDATED state, bypassing __eq__ entirely.
        return not self.__eq__(other)

    def __lt__(self, other: object) -> object:
        # Ordering a cryptographic proof is meaningless, and tuple's inherited ordering would read stored
        # elements without re-proving them. NotImplemented restores the plain `TypeError` an unordered value
        # object raises, without raising from inside the comparison itself.
        return NotImplemented

    def __le__(self, other: object) -> object:
        return NotImplemented

    def __gt__(self, other: object) -> object:
        return NotImplemented

    def __ge__(self, other: object) -> object:
        return NotImplemented

    def __add__(self, other: object) -> object:
        # Concatenating or repeating a proof would extract its elements into a bare sequence; refuse instead.
        return NotImplemented

    def __radd__(self, other: object) -> object:
        return NotImplemented

    def __mul__(self, other: object) -> object:
        return NotImplemented

    def __rmul__(self, other: object) -> object:
        return NotImplemented

    def __contains__(self, value: object) -> bool:
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return tuple.__contains__(self, value)

    def count(self, value: object) -> int:
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return tuple.count(self, value)

    def index(self, value: object, *args: object) -> int:
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return tuple.index(self, value, *args)

    def __getnewargs__(self):
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return (tuple(tuple.__getitem__(self, index) for index in range(len(_VERIFICATION_FIELD_NAMES))),)

    def __iter__(self):
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return tuple.__iter__(self)

    def __getitem__(self, index):
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return tuple.__getitem__(self, index)

    def __reduce__(self):
        """Route ``copy``/``deepcopy``/pickle through the validating public constructor.

        The default tuple-subclass reduction would call ``cls.__new__(cls, values)`` positionally and bypass
        the keyword constructor, so reconstruction is pinned to a rebuild that re-runs the full verification.
        """
        _validate_verification_state(self, _ARTIFACT_INCONSISTENT)
        return (
            _rebuild_certificate_verification,
            (tuple(tuple.__getitem__(self, index) for index in range(len(_VERIFICATION_FIELD_NAMES))),),
        )


def _rebuild_certificate_verification(state: object) -> RoughtimeV19CertificateVerification:
    """Reconstruct an artifact from copy/deepcopy/pickle state by re-running the COMPLETE verification."""
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
