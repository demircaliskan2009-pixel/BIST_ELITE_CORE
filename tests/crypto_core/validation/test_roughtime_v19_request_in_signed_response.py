"""Deterministic contract tests for the Roughtime draft-19 request-in-signed-response composition (K4+SREP).

Fixture provenance: this layer composes two merged proof layers and performs no cryptography of its own, so a
valid fixture needs a response whose signed ``SREP`` carries the ROOT that the request actually folds to. No
accepted packet vector can supply that, because the packet's signed ``SREP`` bytes fix a ROOT that no
reachable request preimages. The fixtures therefore build a response whose ``SREP`` carries an
oracle-computed root and sign it with TEST-ONLY deterministic keys derived from fixed, disclosed seeds. This
is the same test-only signing precedent already accepted for the merged SREP suite: production never signs and
never generates a key, which is asserted below by source inspection.

Every Merkle value is produced by an independent test-side oracle that never imports a production helper, and
every encoder is test-only and never calls a production encoder.
"""

from __future__ import annotations

import ast
import copy
import gc
import hashlib
import operator
import pickle
import weakref
from pathlib import Path

import pytest
from nacl.encoding import RawEncoder
from nacl.signing import SigningKey

from crypto_core.validation.roughtime_v19_certificate_verification import (
    verify_roughtime_v19_certificate,
)
from crypto_core.validation.roughtime_v19_request_in_signed_response import (
    ROUGHTIME_V19_REQUEST_IN_SIGNED_RESPONSE_PROFILE_ID,
    RoughtimeV19RequestInSignedResponse,
    RoughtimeV19RequestInSignedResponseError,
    RoughtimeV19RequestInSignedResponseReason,
    verify_roughtime_v19_request_in_signed_response,
)
from crypto_core.validation.roughtime_v19_request_inclusion import (
    RoughtimeV19RequestInclusion,
    verify_roughtime_v19_request_inclusion,
)
from crypto_core.validation.roughtime_v19_request_semantics import (
    parse_roughtime_v19_request,
)
from crypto_core.validation.roughtime_v19_response_semantics import (
    parse_roughtime_v19_response,
)
from crypto_core.validation.roughtime_v19_signed_response_verification import (
    RoughtimeV19SignedResponseVerification,
    verify_roughtime_v19_signed_response,
)

R = RoughtimeV19RequestInSignedResponseReason

# --- Independently pinned identity constants --------------------------------------------------------------
_EXPECTED_PROFILE_ID = "roughtime-v19-request-in-signed-response-bounded-k4-srep.v1"
_EXPECTED_SEAL_MESSAGE = "RoughtimeV19RequestInSignedResponse is a sealed artifact type and cannot be subclassed"
_EXPECTED_REASON_TYPE_MESSAGE = (
    "RoughtimeV19RequestInSignedResponseError requires a RoughtimeV19RequestInSignedResponseReason member"
)
_EXPECTED_REASON_VALUES = (
    "wrong_input_type",
    "input_artifact_inconsistent",
    "signed_root_binding_mismatch",
    "response_binding_mismatch",
    "artifact_aggregate_inconsistent",
)
_EXPECTED_ANCHOR_FIELDS = (
    "request_raw",
    "response_raw",
    "long_term_public_key",
)
_EXPECTED_PUBLIC_FIELDS = (
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
_DERIVED_PUBLIC_FIELDS = _EXPECTED_PUBLIC_FIELDS[len(_EXPECTED_ANCHOR_FIELDS) :]
_FORBIDDEN_FIELD_TOKENS = (
    "verified",
    "authentic",
    "provider",
    "ready",
    "backend",
    "provenance",
    "valid",
    "truthful",
    "quorum",
    "correlated",
    "admitted",
)
_FORBIDDEN_PUBLIC_ATTRIBUTES = (
    "provider",
    "provider_id",
    "provider_verified",
    "root_key_admitted",
    "request_correlated",
    "truthful_time",
    "authenticated_time",
    "ready",
    "readiness_promoted",
    "countable",
    "quorum",
    "sandwich_complete",
    "machine_time_origin_proven",
    "verified",
    "authentic",
    "deployed_version",
)

# --- Normative transcript constants (needed only to BUILD fixtures, never to verify) ----------------------
_MAGIC = b"ROUGHTIM"
_CERT_CONTEXT = b"RoughTime v1 delegation signature\x00"
_SREP_CONTEXT = b"RoughTime v1 response signature\x00"
_DIGEST_BYTES = 32

_TAG_SIG = b"SIG\x00"
_TAG_NONC = b"NONC"
_TAG_TYPE = b"TYPE"
_TAG_PATH = b"PATH"
_TAG_SREP = b"SREP"
_TAG_CERT = b"CERT"
_TAG_INDX = b"INDX"
_TAG_VER = b"VER\x00"
_TAG_RADI = b"RADI"
_TAG_MIDP = b"MIDP"
_TAG_VERS = b"VERS"
_TAG_ROOT = b"ROOT"
_TAG_DELE = b"DELE"
_TAG_PUBK = b"PUBK"
_TAG_MINT = b"MINT"
_TAG_MAXT = b"MAXT"
_TAG_SRV = b"SRV\x00"

# TEST-ONLY deterministic keys from fixed disclosed seeds. Production never signs and never generates a key.
_LONG_TERM_SIGNING_KEY = SigningKey(bytes(range(32)), encoder=RawEncoder)
_DELEGATED_SIGNING_KEY = SigningKey(bytes(range(100, 132)), encoder=RawEncoder)
_OTHER_LONG_TERM_SIGNING_KEY = SigningKey(bytes(range(50, 82)), encoder=RawEncoder)
_LONG_TERM_PUBLIC_KEY = bytes(_LONG_TERM_SIGNING_KEY.verify_key)
_DELEGATED_PUBLIC_KEY = bytes(_DELEGATED_SIGNING_KEY.verify_key)
_OTHER_LONG_TERM_PUBLIC_KEY = bytes(_OTHER_LONG_TERM_SIGNING_KEY.verify_key)

_REQUEST_NONCE = bytes(range(32))
_RESPONSE_NONCE = bytes(range(32))
_OTHER_RESPONSE_NONCE = bytes(range(100, 132))
_SIBLING_A = bytes(range(200, 232))
_SIBLING_B = bytes(range(60, 92))

_MIDPOINT = 150
_RADIUS = 3
_MIN_TIME = 100
_MAX_TIME = 200
_SELECTED_VERSION = 1
_SIGNED_VERSIONS = (1, 0x40000001)


# --- Test-only encoders (independent of every production encoder) -----------------------------------------
def _le(tag: bytes) -> int:
    return int.from_bytes(tag, "little")


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "little")


def _u64(value: int) -> bytes:
    return int(value).to_bytes(8, "little")


def _encode_message(pairs: list[tuple[bytes, bytes]]) -> bytes:
    ordered = sorted(pairs, key=lambda pair: _le(pair[0]))
    out = _u32(len(ordered))
    cumulative = 0
    for index in range(len(ordered) - 1):
        cumulative += len(ordered[index][1])
        out += _u32(cumulative)
    for tag, _ in ordered:
        out += tag
    for _, value in ordered:
        out += value
    return out


def _encode_packet(message: bytes) -> bytes:
    return _MAGIC + _u32(len(message)) + message


# --- Test-only Merkle oracle (explicit direction tokens; never imports K4) --------------------------------
LEFT = "LEFT"
RIGHT = "RIGHT"


def _oracle_leaf(request_packet: bytes) -> bytes:
    return hashlib.sha512(b"\x00" + request_packet).digest()[:_DIGEST_BYTES]


def _oracle_root(leaf: bytes, steps: tuple[tuple[str, bytes], ...]) -> bytes:
    current = leaf
    for direction, sibling in steps:
        if direction == LEFT:
            current = hashlib.sha512(b"\x01" + current + sibling).digest()[:_DIGEST_BYTES]
        elif direction == RIGHT:
            current = hashlib.sha512(b"\x01" + sibling + current).digest()[:_DIGEST_BYTES]
        else:
            raise ValueError("direction must be LEFT or RIGHT")
    return current


def _oracle_index(directions: tuple[str, ...]) -> int:
    index = 0
    for depth, direction in enumerate(directions):
        if direction == RIGHT:
            index |= 1 << depth
    return index


# --- Test-only packet builders ----------------------------------------------------------------------------
def _request_packet(
    *, nonce: bytes = _REQUEST_NONCE, versions: tuple[int, ...] = (1,), srv: bytes | None = None
) -> bytes:
    pairs: list[tuple[bytes, bytes]] = [
        (_TAG_VER, b"".join(_u32(version) for version in versions)),
        (_TAG_NONC, nonce),
        (_TAG_TYPE, _u32(0)),
    ]
    if srv is not None:
        pairs.append((_TAG_SRV, srv))
    return _encode_packet(_encode_message(pairs))


def _dele_raw(*, delegated_public_key: bytes = _DELEGATED_PUBLIC_KEY) -> bytes:
    return _encode_message(
        [
            (_TAG_PUBK, delegated_public_key),
            (_TAG_MINT, _u64(_MIN_TIME)),
            (_TAG_MAXT, _u64(_MAX_TIME)),
        ]
    )


def _cert_raw(
    *, signing_key: SigningKey = _LONG_TERM_SIGNING_KEY, delegated_public_key: bytes = _DELEGATED_PUBLIC_KEY
) -> bytes:
    delegation = _dele_raw(delegated_public_key=delegated_public_key)
    signature = signing_key.sign(_CERT_CONTEXT + delegation).signature
    return _encode_message([(_TAG_SIG, signature), (_TAG_DELE, delegation)])


def _srep_raw(
    root: bytes,
    *,
    midpoint: int = _MIDPOINT,
    radius: int = _RADIUS,
    selected_version: int = _SELECTED_VERSION,
    versions: tuple[int, ...] = _SIGNED_VERSIONS,
) -> bytes:
    return _encode_message(
        [
            (_TAG_VER, _u32(selected_version)),
            (_TAG_RADI, _u32(radius)),
            (_TAG_MIDP, _u64(midpoint)),
            (_TAG_VERS, b"".join(_u32(version) for version in versions)),
            (_TAG_ROOT, root),
        ]
    )


def _response_packet(
    *,
    root: bytes,
    path: tuple[bytes, ...] = (),
    index: int = 0,
    nonce: bytes = _RESPONSE_NONCE,
    selected_version: int = _SELECTED_VERSION,
    versions: tuple[int, ...] = _SIGNED_VERSIONS,
    long_term_signing_key: SigningKey = _LONG_TERM_SIGNING_KEY,
) -> bytes:
    """Build a fully signed response: the outer SIG covers the exact SREP bytes under the delegated key."""
    signed_response = _srep_raw(root, selected_version=selected_version, versions=versions)
    outer_signature = _DELEGATED_SIGNING_KEY.sign(_SREP_CONTEXT + signed_response).signature
    return _encode_packet(
        _encode_message(
            [
                (_TAG_SIG, outer_signature),
                (_TAG_NONC, nonce),
                (_TAG_TYPE, _u32(1)),
                (_TAG_PATH, b"".join(path)),
                (_TAG_SREP, signed_response),
                (_TAG_CERT, _cert_raw(signing_key=long_term_signing_key)),
                (_TAG_INDX, _u32(index)),
            ]
        )
    )


def _packets(
    *,
    request_nonce: bytes = _REQUEST_NONCE,
    request_versions: tuple[int, ...] = (1,),
    path: tuple[bytes, ...] = (_SIBLING_A,),
    directions: tuple[str, ...] | None = None,
    response_nonce: bytes = _RESPONSE_NONCE,
    selected_version: int = _SELECTED_VERSION,
    versions: tuple[int, ...] = _SIGNED_VERSIONS,
    root: bytes | None = None,
    long_term_signing_key: SigningKey = _LONG_TERM_SIGNING_KEY,
) -> tuple[bytes, bytes]:
    """Return a matching (request_packet, response_packet) pair, root derived only by the oracle."""
    request = _request_packet(nonce=request_nonce, versions=request_versions)
    if directions is None:
        directions = tuple(LEFT for _ in path)
    index = _oracle_index(directions)
    derived_root = _oracle_root(_oracle_leaf(request), tuple(zip(directions, path))) if root is None else root
    response = _response_packet(
        root=derived_root,
        path=path,
        index=index,
        nonce=response_nonce,
        selected_version=selected_version,
        versions=versions,
        long_term_signing_key=long_term_signing_key,
    )
    return request, response


def _inclusion(request: bytes, response: bytes) -> RoughtimeV19RequestInclusion:
    return verify_roughtime_v19_request_inclusion(
        parse_roughtime_v19_request(request), parse_roughtime_v19_response(response)
    )


def _signed(
    response: bytes, *, long_term_public_key: bytes = _LONG_TERM_PUBLIC_KEY
) -> RoughtimeV19SignedResponseVerification:
    certificate = verify_roughtime_v19_certificate(parse_roughtime_v19_response(response), long_term_public_key)
    return verify_roughtime_v19_signed_response(certificate)


def _pair(**kwargs) -> tuple[RoughtimeV19RequestInclusion, RoughtimeV19SignedResponseVerification]:
    long_term_public_key = kwargs.pop("long_term_public_key", _LONG_TERM_PUBLIC_KEY)
    request, response = _packets(**kwargs)
    return _inclusion(request, response), _signed(response, long_term_public_key=long_term_public_key)


def _artifact(**kwargs) -> RoughtimeV19RequestInSignedResponse:
    inclusion, signed_response = _pair(**kwargs)
    return verify_roughtime_v19_request_in_signed_response(inclusion, signed_response)


def _anchors(**kwargs) -> dict:
    request, response = _packets(**kwargs)
    return {
        "request_raw": request,
        "response_raw": response,
        "long_term_public_key": _LONG_TERM_PUBLIC_KEY,
    }


def _hollow(cls, **fields):
    obj = object.__new__(cls)
    for name, value in fields.items():
        object.__setattr__(obj, name, value)
    return obj


def _registered_state(artifact: RoughtimeV19RequestInSignedResponse) -> tuple:
    """The three verified anchors, obtained through the public validating reducer (never the registry)."""
    reducer, arguments = artifact.__reduce__()
    assert reducer.__name__ == "_rebuild_request_in_signed_response"
    state = arguments[0]
    assert type(state) is tuple
    return state


_PRODUCTION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "crypto_core"
    / "validation"
    / "roughtime_v19_request_in_signed_response.py"
)


def _production_tree() -> ast.Module:
    return ast.parse(_PRODUCTION_PATH.read_text(encoding="utf-8"))


def _production_function(name: str) -> ast.FunctionDef:
    matches = [node for node in ast.walk(_production_tree()) if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(matches) == 1, name
    return matches[0]


def _production_function_source(name: str) -> str:
    return ast.get_source_segment(_PRODUCTION_PATH.read_text(encoding="utf-8"), _production_function(name)) or ""


def _closure_registry() -> dict:
    """Locate the closure-local registry for lifecycle assertions. Test-only implementation inspection.

    Explicitly OUTSIDE the supported trust boundary - this path exists only to prove lifecycle cleanup and
    identity binding, and is deliberately not a documented or public API. It makes no claim that closure
    contents are secret.
    """
    seen: list[dict] = []
    for cell in RoughtimeV19RequestInSignedResponse.__hash__.__closure__ or ():
        try:
            content = cell.cell_contents
        except ValueError:  # pragma: no cover - empty cell
            continue
        if type(content) is dict:
            seen.append(content)
        if callable(content):
            for inner in getattr(content, "__closure__", None) or ():
                try:
                    nested = inner.cell_contents
                except ValueError:  # pragma: no cover - empty cell
                    continue
                if type(nested) is dict:
                    seen.append(nested)
    assert seen, "closure-local registry not reachable for lifecycle assertions"
    return seen[0]


# ============================================================================================================
# Profile, API, reason and error contracts
# ============================================================================================================
def test_profile_id_is_exact() -> None:
    assert ROUGHTIME_V19_REQUEST_IN_SIGNED_RESPONSE_PROFILE_ID == _EXPECTED_PROFILE_ID


def test_production_exports_exactly_five_public_symbols() -> None:
    exports: list[str] = []
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    exports = [element.value for element in node.value.elts]
    assert exports == [
        "ROUGHTIME_V19_REQUEST_IN_SIGNED_RESPONSE_PROFILE_ID",
        "RoughtimeV19RequestInSignedResponse",
        "RoughtimeV19RequestInSignedResponseError",
        "RoughtimeV19RequestInSignedResponseReason",
        "verify_roughtime_v19_request_in_signed_response",
    ]


def test_reason_enum_is_exactly_five_members_in_order() -> None:
    assert tuple(member.value for member in R) == _EXPECTED_REASON_VALUES
    assert len(R) == 5


def test_error_str_is_reason_value_and_reason_is_exact() -> None:
    for member in R:
        error = RoughtimeV19RequestInSignedResponseError(member)
        assert str(error) == member.value
        assert error.reason is member


@pytest.mark.parametrize("bad", ["response_binding_mismatch", 0, None, object()])
def test_error_rejects_non_member_reason(bad) -> None:
    with pytest.raises(TypeError) as excinfo:
        RoughtimeV19RequestInSignedResponseError(bad)
    assert str(excinfo.value) == _EXPECTED_REASON_TYPE_MESSAGE


def test_error_rejects_hostile_value_property_before_reading_it() -> None:
    reads: list[str] = []

    class _HostileReason:
        @property
        def value(self) -> str:
            reads.append("value")
            return "response_binding_mismatch"

    with pytest.raises(TypeError):
        RoughtimeV19RequestInSignedResponseError(_HostileReason())
    assert reads == []


@pytest.mark.parametrize("locked", ["reason", "_reason", "args"])
def test_error_locked_attributes_block_ordinary_mutation(locked) -> None:
    error = RoughtimeV19RequestInSignedResponseError(R.WRONG_INPUT_TYPE)
    with pytest.raises(AttributeError):
        setattr(error, locked, "tampered")
    with pytest.raises(AttributeError):
        delattr(error, locked)


# ============================================================================================================
# Positive composition
# ============================================================================================================
def test_valid_composition_succeeds() -> None:
    request, response = _packets()
    artifact = verify_roughtime_v19_request_in_signed_response(_inclusion(request, response), _signed(response))
    assert artifact.request_raw == request
    assert artifact.response_raw == response
    assert artifact.long_term_public_key == _LONG_TERM_PUBLIC_KEY


def test_direct_three_anchor_construction_succeeds() -> None:
    anchors = _anchors()
    artifact = RoughtimeV19RequestInSignedResponse(**anchors)
    assert artifact.request_raw == anchors["request_raw"]
    assert artifact.response_raw == anchors["response_raw"]
    assert artifact.long_term_public_key == anchors["long_term_public_key"]
    assert artifact.delegated_public_key == _DELEGATED_PUBLIC_KEY
    assert artifact.request_path_length == 1


def test_composition_matches_every_prerequisite_derived_value() -> None:
    request, response = _packets()
    inclusion = _inclusion(request, response)
    signed_response = _signed(response)
    artifact = verify_roughtime_v19_request_in_signed_response(inclusion, signed_response)
    assert artifact.delegated_public_key == signed_response.delegated_public_key
    assert artifact.signed_response_raw == signed_response.signed_response_raw
    assert artifact.signed_root == signed_response.signed_root
    assert artifact.signed_midpoint == signed_response.signed_midpoint == _MIDPOINT
    assert artifact.signed_radius == signed_response.signed_radius == _RADIUS
    assert artifact.signed_version == signed_response.signed_version == _SELECTED_VERSION
    assert artifact.signed_versions == signed_response.signed_versions == _SIGNED_VERSIONS
    assert artifact.request_leaf == inclusion.leaf
    assert artifact.request_index == inclusion.index
    assert artifact.request_path_length == inclusion.path_length


def test_empty_path_composition_succeeds_and_root_equals_leaf() -> None:
    """An empty PATH folds zero times, so the signed root must equal the request leaf exactly."""
    artifact = _artifact(path=())
    assert artifact.request_path_length == 0
    assert artifact.request_index == 0
    assert artifact.signed_root == artifact.request_leaf


@pytest.mark.parametrize(
    ("path", "directions"),
    [
        ((_SIBLING_A,), (LEFT,)),
        ((_SIBLING_A,), (RIGHT,)),
        ((_SIBLING_A, _SIBLING_B), (LEFT, RIGHT)),
        ((_SIBLING_A, _SIBLING_B), (RIGHT, RIGHT)),
    ],
)
def test_multi_depth_and_right_direction_paths_compose(path, directions) -> None:
    artifact = _artifact(path=path, directions=directions)
    assert artifact.request_path_length == len(path)
    assert artifact.request_index == _oracle_index(directions)
    assert artifact.signed_root == _oracle_root(_oracle_leaf(artifact.request_raw), tuple(zip(directions, path)))


def test_independent_oracle_agrees_with_the_composed_leaf_and_root() -> None:
    artifact = _artifact()
    assert artifact.request_leaf == _oracle_leaf(artifact.request_raw)
    assert artifact.signed_root == _oracle_root(artifact.request_leaf, ((LEFT, _SIBLING_A),))


# ============================================================================================================
# Exact-type input gates
# ============================================================================================================
@pytest.mark.parametrize("bad", [object(), None, b"", 0, "inclusion", (), _LONG_TERM_PUBLIC_KEY])
def test_wrong_inclusion_input_type_rejected(bad) -> None:
    _, signed_response = _pair()
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(bad, signed_response)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


@pytest.mark.parametrize("bad", [object(), None, b"", 0, "signed", (), _LONG_TERM_PUBLIC_KEY])
def test_wrong_signed_response_input_type_rejected(bad) -> None:
    inclusion, _ = _pair()
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(inclusion, bad)
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_prerequisite_artifacts_are_not_interchangeable() -> None:
    """A K5 certificate, a raw K2 response and a swapped argument order are all wrong_input_type."""
    request, response = _packets()
    inclusion = _inclusion(request, response)
    signed_response = _signed(response)
    certificate = verify_roughtime_v19_certificate(parse_roughtime_v19_response(response), _LONG_TERM_PUBLIC_KEY)
    for first, second in (
        (signed_response, inclusion),
        (certificate, signed_response),
        (inclusion, certificate),
        (parse_roughtime_v19_response(response), signed_response),
    ):
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            verify_roughtime_v19_request_in_signed_response(first, second)
        assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_no_attribute_is_read_before_both_exact_type_gates_pass() -> None:
    """A hostile non-exact object must be rejected before any attribute of it is touched."""
    reads: list[str] = []

    class _Recording:
        def __getattribute__(self, name: str) -> object:
            reads.append(name)
            return object.__getattribute__(self, name)

    inclusion, signed_response = _pair()
    for first, second in ((_Recording(), signed_response), (inclusion, _Recording())):
        reads.clear()
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            verify_roughtime_v19_request_in_signed_response(first, second)
        assert excinfo.value.reason is R.WRONG_INPUT_TYPE
        assert reads == []


def test_inclusion_type_gate_precedes_signed_response_type_gate() -> None:
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(object(), object())
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_prerequisite_types_are_sealed_so_no_hostile_override_can_run() -> None:
    """Both prerequisites are sealed at class-definition time - the strongest possible form."""
    for base, message in (
        (
            RoughtimeV19RequestInclusion,
            "RoughtimeV19RequestInclusion is a sealed artifact type and cannot be subclassed",
        ),
        (
            RoughtimeV19SignedResponseVerification,
            "RoughtimeV19SignedResponseVerification is a sealed artifact type and cannot be subclassed",
        ),
    ):
        with pytest.raises(TypeError) as excinfo:
            type("_Hostile", (base,), {"__getattribute__": object.__getattribute__})
        assert str(excinfo.value) == message


# ============================================================================================================
# Hollow and inconsistent prerequisite inputs
# ============================================================================================================
def test_hollow_inclusion_artifact_normalizes_to_input_artifact_inconsistent() -> None:
    _, signed_response = _pair()
    hollow = object.__new__(RoughtimeV19RequestInclusion)
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(hollow, signed_response)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_hollow_signed_response_artifact_normalizes_to_input_artifact_inconsistent() -> None:
    inclusion, _ = _pair()
    hollow = object.__new__(RoughtimeV19SignedResponseVerification)
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(inclusion, hollow)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


@pytest.mark.parametrize(
    "field",
    ["request_raw", "response_raw", "leaf", "computed_root", "declared_root", "path_length", "index"],
)
def test_mutated_inclusion_carried_field_normalizes(field) -> None:
    """A caller-carried K4 field the Merkle recomputation never reads must still be rejected."""
    request, response = _packets()
    genuine = _inclusion(request, response)
    signed_response = _signed(response)
    state = {
        "request_raw": genuine.request_raw,
        "response_raw": genuine.response_raw,
        "leaf": genuine.leaf,
        "computed_root": genuine.computed_root,
        "declared_root": genuine.declared_root,
        "path_length": genuine.path_length,
        "index": genuine.index,
    }
    state[field] = bytes(32) if type(state[field]) is bytes else state[field] + 1
    forged = _hollow(RoughtimeV19RequestInclusion, **state)
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(forged, signed_response)
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_inclusion_with_extra_smuggled_state_normalizes() -> None:
    """An overclaiming extra attribute on the K4 input must be rejected by its exact namespace gate."""
    request, response = _packets()
    genuine = _inclusion(request, response)
    forged = _hollow(
        RoughtimeV19RequestInclusion,
        request_raw=genuine.request_raw,
        response_raw=genuine.response_raw,
        leaf=genuine.leaf,
        computed_root=genuine.computed_root,
        declared_root=genuine.declared_root,
        path_length=genuine.path_length,
        index=genuine.index,
        root_authentic=True,
    )
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(forged, _signed(response))
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


def test_incomplete_inclusion_state_normalizes_without_leaking_attribute_error() -> None:
    request, response = _packets()
    genuine = _inclusion(request, response)
    forged = _hollow(RoughtimeV19RequestInclusion, request_raw=genuine.request_raw)
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(forged, _signed(response))
    assert excinfo.value.reason is R.INPUT_ARTIFACT_INCONSISTENT


# ============================================================================================================
# Cross-artifact bindings
# ============================================================================================================
def test_signed_root_binding_mismatch_between_independently_valid_proofs() -> None:
    """Two independently valid compositions cannot be crossed: different requests fold to different roots."""
    first_request, first_response = _packets(request_nonce=_REQUEST_NONCE)
    second_request, second_response = _packets(request_nonce=_OTHER_RESPONSE_NONCE)
    assert first_request != second_request
    inclusion = _inclusion(first_request, first_response)
    signed_response = _signed(second_response)
    assert inclusion.declared_root != signed_response.signed_root
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(inclusion, signed_response)
    assert excinfo.value.reason is R.SIGNED_ROOT_BINDING_MISMATCH


def test_response_binding_mismatch_when_signed_root_matches_but_response_differs() -> None:
    """Same signed SREP bytes, different unsigned outer NONC: root binds, exact response bytes do not."""
    request, response = _packets(response_nonce=_RESPONSE_NONCE)
    _, other_response = _packets(response_nonce=_OTHER_RESPONSE_NONCE)
    assert response != other_response
    inclusion = _inclusion(request, response)
    signed_response = _signed(other_response)
    assert inclusion.declared_root == signed_response.signed_root
    assert inclusion.response_raw != signed_response.response_raw
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(inclusion, signed_response)
    assert excinfo.value.reason is R.RESPONSE_BINDING_MISMATCH


def test_signed_root_binding_precedes_response_binding() -> None:
    """When both bindings would fail, the pinned precedence reports the signed-root mismatch."""
    first_request, first_response = _packets(request_nonce=_REQUEST_NONCE)
    _, second_response = _packets(request_nonce=_OTHER_RESPONSE_NONCE, response_nonce=_OTHER_RESPONSE_NONCE)
    inclusion = _inclusion(first_request, first_response)
    signed_response = _signed(second_response)
    assert inclusion.declared_root != signed_response.signed_root
    assert inclusion.response_raw != signed_response.response_raw
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        verify_roughtime_v19_request_in_signed_response(inclusion, signed_response)
    assert excinfo.value.reason is R.SIGNED_ROOT_BINDING_MISMATCH


@pytest.mark.parametrize("nonce", [bytes(range(32)), bytes(range(1, 33)), bytes(32)])
def test_distinct_valid_response_matrix_never_cross_composes(nonce) -> None:
    request, response = _packets(request_nonce=nonce)
    _, foreign_response = _packets(request_nonce=bytes(range(70, 102)))
    with pytest.raises(RoughtimeV19RequestInSignedResponseError):
        verify_roughtime_v19_request_in_signed_response(_inclusion(request, response), _signed(foreign_response))
    # The matching pair still composes, so the rejection is specific rather than blanket.
    verify_roughtime_v19_request_in_signed_response(_inclusion(request, response), _signed(response))


def test_inclusion_proof_is_mandatory() -> None:
    """A response whose declared ROOT does not match the request cannot even produce the K4 prerequisite."""
    request, response = _packets(root=bytes(32))
    with pytest.raises(Exception) as excinfo:
        _inclusion(request, response)
    assert type(excinfo.value) is not RoughtimeV19RequestInSignedResponseError


def test_certificate_and_signed_response_proofs_are_mandatory() -> None:
    """A wrong long-term key breaks the CERT chain, so no SREP prerequisite can exist."""
    _, response = _packets()
    with pytest.raises(Exception) as excinfo:
        _signed(response, long_term_public_key=_OTHER_LONG_TERM_PUBLIC_KEY)
    assert type(excinfo.value) is not RoughtimeV19RequestInSignedResponseError


def test_three_anchor_construction_requires_the_exact_long_term_key() -> None:
    anchors = _anchors()
    anchors["long_term_public_key"] = _OTHER_LONG_TERM_PUBLIC_KEY
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        RoughtimeV19RequestInSignedResponse(**anchors)
    assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT


# ============================================================================================================
# Deliberate non-claims
# ============================================================================================================
def test_differing_nonces_never_reject_a_valid_composition() -> None:
    """NONC lies outside the signed SREP, so comparing it would be an unsigned correlation."""
    request = _request_packet(nonce=bytes(range(32)))
    root = _oracle_root(_oracle_leaf(request), ((LEFT, _SIBLING_A),))
    response = _response_packet(root=root, path=(_SIBLING_A,), index=0, nonce=bytes(range(200, 232)))
    inclusion = _inclusion(request, response)
    artifact = verify_roughtime_v19_request_in_signed_response(inclusion, _signed(response))
    assert artifact.request_raw == request
    assert parse_roughtime_v19_request(request).nonce != parse_roughtime_v19_response(response).nonce


def test_selected_version_not_offered_by_the_request_never_rejects() -> None:
    """No version relation is asserted: an unoffered selected version is not a rejection cause."""
    artifact = _artifact(request_versions=(1,), selected_version=0x40000001, versions=(1, 0x40000001))
    assert artifact.signed_version == 0x40000001
    assert parse_roughtime_v19_request(artifact.request_raw).versions == (1,)


def test_production_declares_no_nonce_or_version_comparison() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    tree = _production_tree()
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    identifiers = {token.lower() for token in attributes | names}
    for forbidden in ("nonce", "nonc", "versions_offered", "server_key_id", "srv", "quorum", "readiness_promoted"):
        assert forbidden not in identifiers
    assert "connector_ready_dialects" not in source


@pytest.mark.parametrize("name", _FORBIDDEN_PUBLIC_ATTRIBUTES)
def test_artifact_exposes_no_overclaiming_attribute(name) -> None:
    artifact = _artifact()
    assert not hasattr(RoughtimeV19RequestInSignedResponse, name), name
    assert not hasattr(artifact, name), name


def test_public_attribute_surface_is_exactly_the_declared_fields() -> None:
    artifact = _artifact()
    public = {
        name for name in dir(artifact) if not name.startswith("_") and not callable(getattr(type(artifact), name, None))
    }
    assert public == set(_EXPECTED_PUBLIC_FIELDS)


def test_artifact_field_names_avoid_forbidden_tokens() -> None:
    for name in _EXPECTED_PUBLIC_FIELDS:
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name


def test_signed_values_are_named_signed_not_true() -> None:
    for name in ("signed_root", "signed_midpoint", "signed_radius", "signed_version", "signed_versions"):
        assert name.startswith("signed_")
    for forbidden in ("true_", "actual_", "trusted_", "current_", "wall_", "utc_"):
        for name in _EXPECTED_PUBLIC_FIELDS:
            assert not name.startswith(forbidden)


# ============================================================================================================
# Exact three-anchor state and thirteen-property public view
# ============================================================================================================
def test_registered_state_is_exactly_the_three_anchors() -> None:
    from crypto_core.validation.roughtime_v19_request_in_signed_response import _ANCHOR_FIELD_NAMES

    assert _ANCHOR_FIELD_NAMES == _EXPECTED_ANCHOR_FIELDS
    assert len(_ANCHOR_FIELD_NAMES) == 3
    artifact = _artifact()
    registry = _closure_registry()
    _, state = registry[id(artifact)]
    assert type(state) is tuple
    assert len(state) == 3
    assert state == (artifact.request_raw, artifact.response_raw, artifact.long_term_public_key)
    assert tuple(type(value) for value in state) == (bytes, bytes, bytes)


def test_reduce_state_is_exactly_the_three_anchors() -> None:
    artifact = _artifact()
    state = _registered_state(artifact)
    assert len(state) == 3
    assert state == (artifact.request_raw, artifact.response_raw, artifact.long_term_public_key)


def test_constructor_accepts_exactly_the_three_anchor_keywords() -> None:
    anchors = _anchors()
    RoughtimeV19RequestInSignedResponse(**anchors)
    for extra in ("signed_root", "request_leaf", "delegated_public_key", "request_index"):
        with pytest.raises(TypeError):
            RoughtimeV19RequestInSignedResponse(**anchors, **{extra: b""})
    for missing in _EXPECTED_ANCHOR_FIELDS:
        reduced = {name: value for name, value in anchors.items() if name != missing}
        with pytest.raises(TypeError):
            RoughtimeV19RequestInSignedResponse(**reduced)


def test_artifact_declares_exactly_thirteen_public_properties_in_order() -> None:
    from crypto_core.validation.roughtime_v19_request_in_signed_response import _PUBLIC_FIELD_NAMES

    assert _PUBLIC_FIELD_NAMES == _EXPECTED_PUBLIC_FIELDS
    assert len(_PUBLIC_FIELD_NAMES) == 13
    for name in _EXPECTED_PUBLIC_FIELDS:
        assert type(getattr(RoughtimeV19RequestInSignedResponse, name)) is property


def test_public_view_order_matches_declared_property_order() -> None:
    """Every declared property is rendered, and in exactly the declared order."""
    artifact = _artifact()
    rendered = repr(artifact)
    for name in _EXPECTED_PUBLIC_FIELDS:
        assert repr(getattr(artifact, name)) in rendered, name
    positions = [rendered.index(f"{name}=") for name in _EXPECTED_PUBLIC_FIELDS]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(_EXPECTED_PUBLIC_FIELDS)


def test_ten_derived_values_are_not_stored_and_are_rederived_each_time() -> None:
    """Only three anchors are stored; every derived read recomputes from them through the public verifiers."""
    artifact = _artifact()
    stored = _registered_state(artifact)
    assert len(stored) == 3
    assert len(_DERIVED_PUBLIC_FIELDS) == 10
    for name in _DERIVED_PUBLIC_FIELDS:
        assert getattr(artifact, name) not in stored, name
    first = tuple(getattr(artifact, name) for name in _DERIVED_PUBLIC_FIELDS)
    second = tuple(getattr(artifact, name) for name in _DERIVED_PUBLIC_FIELDS)
    assert first == second
    # Re-derivation is genuine: mutating the stored anchors changes every derived value on the next read.
    assert first != tuple(
        getattr(_artifact(request_nonce=bytes(range(70, 102))), name) for name in _DERIVED_PUBLIC_FIELDS
    )


def test_derived_values_are_exact_builtin_types() -> None:
    artifact = _artifact()
    for name in ("delegated_public_key", "signed_response_raw", "signed_root", "request_leaf"):
        assert type(getattr(artifact, name)) is bytes, name
    for name in ("signed_midpoint", "signed_radius", "signed_version", "request_index", "request_path_length"):
        value = getattr(artifact, name)
        assert type(value) is int, name
        assert type(value) is not bool, name
    assert type(artifact.signed_versions) is tuple
    for version in artifact.signed_versions:
        assert type(version) is int


# ============================================================================================================
# Exact state type gates
# ============================================================================================================
@pytest.mark.parametrize("anchor", _EXPECTED_ANCHOR_FIELDS)
def test_bytes_subclass_anchor_rejected_even_when_value_preserving(anchor) -> None:
    """A bytes SUBCLASS compares equal but carries caller-controlled behaviour, so it must not reach state."""

    class _Bytes(bytes):
        pass

    anchors = _anchors()
    assert _Bytes(anchors[anchor]) == anchors[anchor]
    anchors[anchor] = _Bytes(anchors[anchor])
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        RoughtimeV19RequestInSignedResponse(**anchors)
    assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT


def test_exact_bytes_anchor_gate_fires_before_any_parser_is_reached() -> None:
    """The exact-bytes gate must reject a non-exact anchor BEFORE any prerequisite parser sees it.

    The merged K3/K2 parsers happen to reject a bytes subclass too, so a value-preserving subclass alone
    cannot distinguish our gate from theirs. What IS distinguishable, and what the gate exists for, is the
    ORDERING: a non-exact anchor must never reach a prerequisite and must never reach stored state. Tripwire
    parsers make that ordering observable - if the gate were weakened to ``isinstance``, a subclass would slip
    through and trip them.
    """
    import crypto_core.validation.roughtime_v19_request_in_signed_response as module

    class _Bytes(bytes):
        pass

    calls: list[str] = []

    def _tripwire(*args: object, **kwargs: object) -> object:
        calls.append("prerequisite reached")
        raise AssertionError("a non-exact-bytes anchor must never reach a prerequisite parser")

    anchors = _anchors()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, "parse_roughtime_v19_request", _tripwire)
        patch.setattr(module, "parse_roughtime_v19_response", _tripwire)
        for anchor in _EXPECTED_ANCHOR_FIELDS:
            mutated = dict(anchors)
            mutated[anchor] = _Bytes(mutated[anchor])
            assert mutated[anchor] == anchors[anchor]
            with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
                RoughtimeV19RequestInSignedResponse(**mutated)
            assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT, anchor
    assert calls == []


@pytest.mark.parametrize("anchor", _EXPECTED_ANCHOR_FIELDS)
@pytest.mark.parametrize("factory", [bytearray, memoryview])
def test_non_exact_bytes_anchor_rejected(anchor, factory) -> None:
    anchors = _anchors()
    anchors[anchor] = factory(anchors[anchor])
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        RoughtimeV19RequestInSignedResponse(**anchors)
    assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT


@pytest.mark.parametrize("value", [None, 0, True, "raw", (), [], object()])
def test_wrong_anchor_type_rejected(value) -> None:
    for anchor in _EXPECTED_ANCHOR_FIELDS:
        anchors = _anchors()
        anchors[anchor] = value
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            RoughtimeV19RequestInSignedResponse(**anchors)
        assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT


def test_altered_anchor_value_rejected() -> None:
    for anchor, replacement in (
        ("request_raw", _request_packet(nonce=bytes(range(70, 102)))),
        ("response_raw", _packets(request_nonce=bytes(range(70, 102)))[1]),
        ("long_term_public_key", _OTHER_LONG_TERM_PUBLIC_KEY),
    ):
        anchors = _anchors()
        anchors[anchor] = replacement
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            RoughtimeV19RequestInSignedResponse(**anchors)
        assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT


# ============================================================================================================
# Public consumption surfaces
# ============================================================================================================
_CONSUMPTION_SURFACES = (
    *((name, operator.attrgetter(name)) for name in _EXPECTED_PUBLIC_FIELDS),
    ("repr", repr),
    ("str", str),
    ("hash", hash),
    ("bool", bool),
    ("truth", operator.truth),
    ("reduce", lambda obj: obj.__reduce__()),
    ("reduce_ex", lambda obj: obj.__reduce_ex__(2)),
    ("copy", copy.copy),
    ("deepcopy", copy.deepcopy),
    ("pickle", pickle.dumps),
)


@pytest.mark.parametrize(
    "surface,consume", _CONSUMPTION_SURFACES, ids=lambda value: value if isinstance(value, str) else ""
)
def test_hollow_instance_fails_closed_on_every_public_surface(surface, consume) -> None:
    hollow = object.__new__(RoughtimeV19RequestInSignedResponse)
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        consume(hollow)
    assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT, surface


def test_truthiness_returns_exact_true_for_a_genuine_proof() -> None:
    artifact = _artifact()
    assert bool(artifact) is True
    assert artifact.__bool__() is True
    assert operator.truth(artifact) is True
    assert "__bool__" in vars(RoughtimeV19RequestInSignedResponse)
    assert "__len__" not in vars(RoughtimeV19RequestInSignedResponse)
    assert not hasattr(RoughtimeV19RequestInSignedResponse, "__len__")


def test_hollow_truthiness_fails_closed_rather_than_returning_false() -> None:
    hollow = object.__new__(RoughtimeV19RequestInSignedResponse)
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        RoughtimeV19RequestInSignedResponse.__bool__(hollow)
    assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT
    with pytest.raises(RoughtimeV19RequestInSignedResponseError):
        _ = "truthy" if hollow else "falsey"


def test_repr_renders_all_thirteen_public_properties_in_order() -> None:
    artifact = _artifact()
    rendered = repr(artifact)
    assert rendered.startswith("RoughtimeV19RequestInSignedResponse(request_raw=")
    positions = [rendered.index(f"{name}=") for name in _EXPECTED_PUBLIC_FIELDS]
    assert positions == sorted(positions)
    assert rendered.endswith(")")


def test_equality_and_hashing_are_deterministic_and_anchor_bound() -> None:
    first = _artifact()
    second = _artifact()
    assert operator.eq(first, second) is True
    assert operator.ne(first, second) is False
    assert hash(first) == hash(second)
    assert len({first, second}) == 1
    assert hash(first) == hash(_registered_state(first))


def test_equality_is_strictly_type_bound() -> None:
    artifact = _artifact()
    state = _registered_state(artifact)
    for impostor in (state, list(state), dict(zip(_EXPECTED_ANCHOR_FIELDS, state)), object()):
        assert operator.eq(artifact, impostor) is False
        assert operator.ne(artifact, impostor) is True
        assert operator.eq(impostor, artifact) is False


def test_inequality_and_hash_are_defined_explicitly_on_the_artifact() -> None:
    namespace = vars(RoughtimeV19RequestInSignedResponse)
    assert "__eq__" in namespace
    assert "__ne__" in namespace
    assert "__hash__" in namespace
    assert RoughtimeV19RequestInSignedResponse.__hash__ is not None


def test_dictionary_key_and_set_membership_stay_stable() -> None:
    first = _artifact()
    second = _artifact()
    mapping = {first: "proof"}
    members = {first}
    assert mapping[second] == "proof"
    assert second in members
    with pytest.raises(AttributeError):
        object.__setattr__(second, "long_term_public_key", bytes(32))
    assert mapping[second] == "proof"
    assert len({first, second}) == 1


def test_distinct_compositions_are_not_equal() -> None:
    first = _artifact(request_nonce=_REQUEST_NONCE)
    second = _artifact(request_nonce=bytes(range(70, 102)))
    assert operator.eq(first, second) is False
    assert len({first, second}) == 2


def test_hollow_instance_never_equals_or_collides_with_a_genuine_proof() -> None:
    genuine = _artifact()
    hollow = object.__new__(RoughtimeV19RequestInSignedResponse)
    mapping = {genuine: "proof"}
    for consume in (
        lambda: operator.eq(genuine, hollow),
        lambda: operator.eq(hollow, genuine),
        lambda: operator.ne(genuine, hollow),
        lambda: operator.ne(hollow, genuine),
        lambda: hollow in {genuine},
        lambda: mapping[hollow],
    ):
        with pytest.raises(RoughtimeV19RequestInSignedResponseError):
            consume()


# ============================================================================================================
# copy / deepcopy / pickle
# ============================================================================================================
def test_copy_deepcopy_and_pickle_stay_valid_and_immutable() -> None:
    artifact = _artifact()
    clones = (
        copy.copy(artifact),
        copy.deepcopy(artifact),
        pickle.loads(pickle.dumps(artifact)),  # noqa: S301 - round-trips this module's own artifact only
    )
    for clone in clones:
        assert type(clone) is RoughtimeV19RequestInSignedResponse
        assert clone is not artifact
        assert operator.eq(clone, artifact) is True
        assert hash(clone) == hash(artifact)
        assert not hasattr(clone, "__dict__")
        assert clone.signed_root == artifact.signed_root
        assert clone.request_leaf == artifact.request_leaf
        with pytest.raises(AttributeError):
            object.__setattr__(clone, "signed_root", bytes(32))


def test_pickle_payload_carries_no_registry_or_derived_state() -> None:
    artifact = _artifact()
    payload = pickle.dumps(artifact)
    assert b"_rebuild_request_in_signed_response" in payload
    assert b"registry" not in payload
    assert b"proven_state" not in payload
    for name in _DERIVED_PUBLIC_FIELDS:
        assert name.encode() not in payload, name
    restored = pickle.loads(payload)  # noqa: S301 - round-trips this module's own artifact only
    assert operator.eq(restored, artifact) is True


def test_rebuild_helper_rejects_malformed_state() -> None:
    from crypto_core.validation.roughtime_v19_request_in_signed_response import (
        _rebuild_request_in_signed_response,
    )

    state = _registered_state(_artifact())
    other_request, other_response = _packets(request_nonce=bytes(range(70, 102)))
    malformed = (
        None,
        (),
        state[:2],
        (*state, b"extra"),
        list(state),
        (b"forged", *state[1:]),
        (other_request, *state[1:]),
        (state[0], other_response, state[2]),
        (*state[:2], _OTHER_LONG_TERM_PUBLIC_KEY),
        (bytearray(state[0]), *state[1:]),
        (state[0], state[1], bytearray(state[2])),
    )
    for bad in malformed:
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            _rebuild_request_in_signed_response(bad)
        assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT
    assert _rebuild_request_in_signed_response(state).signed_root == _artifact().signed_root


def test_state_validator_rejects_foreign_and_malformed_state() -> None:
    from crypto_core.validation.roughtime_v19_request_in_signed_response import (
        _ARTIFACT_INCONSISTENT,
        _validate_anchor_tuple,
    )

    genuine = _registered_state(_artifact())
    for bad in (None, (), [*genuine], genuine[:2], (*genuine, b"extra"), object()):
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            _validate_anchor_tuple(bad, _ARTIFACT_INCONSISTENT)
        assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT
    _validate_anchor_tuple(genuine, _ARTIFACT_INCONSISTENT)


# ============================================================================================================
# Registry identity, weakref binding and lifecycle
# ============================================================================================================
def test_registry_is_not_reachable_through_the_module_namespace() -> None:
    import crypto_core.validation.roughtime_v19_request_in_signed_response as module

    for name in dir(module):
        if name.startswith("__"):
            continue
        assert type(getattr(module, name)) is not dict, name
    for hook in ("registry", "_registry", "get_registry", "_get_registry"):
        assert not hasattr(module, hook)


def test_registry_binds_exactly_one_entry_per_live_artifact() -> None:
    registry = _closure_registry()
    baseline = len(registry)
    first = _artifact()
    second = _artifact(request_nonce=bytes(range(70, 102)))
    assert len(registry) == baseline + 2
    for artifact in (first, second):
        reference, state = registry[id(artifact)]
        assert type(reference) is weakref.ReferenceType
        assert reference() is artifact
        assert reference.__callback__ is not None
        assert type(state) is tuple
        assert len(state) == 3
        assert tuple(type(value) for value in state) == (bytes, bytes, bytes)


def test_registry_entry_is_removed_when_the_artifact_dies() -> None:
    gc.collect()
    registry = _closure_registry()
    baseline = len(registry)
    artifact = _artifact()
    key = id(artifact)
    assert key in registry
    del artifact
    gc.collect()
    assert key not in registry
    assert len(registry) == baseline


def test_failed_construction_leaves_no_registry_entry() -> None:
    gc.collect()
    registry = _closure_registry()
    baseline = len(registry)
    anchors = _anchors()
    anchors["long_term_public_key"] = _OTHER_LONG_TERM_PUBLIC_KEY
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        RoughtimeV19RequestInSignedResponse(**anchors)
    assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT
    assert len(registry) == baseline


def test_hollow_instance_has_no_registry_entry() -> None:
    registry = _closure_registry()
    hollow = object.__new__(RoughtimeV19RequestInSignedResponse)
    assert id(hollow) not in registry


def test_a_stale_or_mismatched_weakref_never_authenticates_another_object() -> None:
    registry = _closure_registry()
    genuine = _artifact()
    state = _registered_state(genuine)
    impostor = object.__new__(RoughtimeV19RequestInSignedResponse)
    key = id(impostor)
    assert key not in registry
    registry[key] = (weakref.ref(genuine), state)
    try:
        for consume in (operator.attrgetter("signed_root"), bool, repr, hash, lambda obj: obj.__reduce__()):
            with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
                consume(impostor)
            assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT
    finally:
        registry.pop(key, None)
    assert genuine.signed_root == _artifact().signed_root


def test_a_dead_weakref_entry_never_authenticates() -> None:
    registry = _closure_registry()
    state = _registered_state(_artifact())
    doomed = _artifact()
    reference = weakref.ref(doomed)
    del doomed
    gc.collect()
    assert reference() is None
    impostor = object.__new__(RoughtimeV19RequestInSignedResponse)
    key = id(impostor)
    assert key not in registry
    registry[key] = (reference, state)
    try:
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            bool(impostor)
        assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT
    finally:
        registry.pop(key, None)


def test_registry_revalidation_rejects_planted_but_well_shaped_wrong_state() -> None:
    """Proves per-consumption revalidation is load-bearing, not merely a shape check, and is never cached.

    The artifact is consumed BEFORE the state is planted, so a verdict cached against the artifact identity
    would still be available afterwards. Every consumption after the plant must nevertheless fail closed,
    which proves the derivation genuinely re-runs on each call.
    """
    registry = _closure_registry()
    victim = _artifact()
    assert bool(victim) is True
    assert victim.signed_root == _artifact().signed_root
    key = id(victim)
    original = registry[key]
    other_request, _ = _packets(request_nonce=bytes(range(70, 102)))
    forged = (other_request, original[1][1], original[1][2])
    registry[key] = (weakref.ref(victim), forged)
    try:
        for consume in (operator.attrgetter("signed_root"), bool, repr, hash):
            with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
                consume(victim)
            assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT
    finally:
        registry[key] = original
    assert bool(victim) is True


def test_registry_lookup_never_invokes_artifact_equality_or_hash() -> None:
    registry = _closure_registry()
    _artifact()
    for key in registry:
        assert type(key) is int


def test_stale_weakref_callback_does_not_delete_replacement_owner_entry() -> None:
    """A stale callback must delete ONLY the entry its own exact weakref owns.

    CPython may reuse an integer identity after a collection, so an obsolete callback firing late could
    otherwise evict a NEWER artifact's entry. The replacement entry is installed under the original key
    deterministically rather than by waiting for a probabilistic id() reuse, and the callback invoked here is
    the exact one production attached to the stored weakref.

    White-box lifecycle invariant only: this is an EXCLUDED private-state operation that does not widen the
    public attacker model and claims no resistance to arbitrary private closure mutation.
    """
    gc.collect()
    registry = _closure_registry()
    baseline = len(registry)
    owner = _artifact()
    replacement = _artifact(request_nonce=bytes(range(70, 102)))
    owner_key = id(owner)
    replacement_key = id(replacement)
    assert owner_key != replacement_key
    assert len(registry) == baseline + 2

    owner_reference, owner_state = registry[owner_key]
    replacement_entry = registry[replacement_key]
    replacement_reference, replacement_state = replacement_entry
    assert replacement_reference is not owner_reference

    stale_callback = owner_reference.__callback__
    assert stale_callback is not None

    registry[owner_key] = replacement_entry
    try:
        stale_callback(owner_reference)
        assert owner_key in registry
        surviving_reference, surviving_state = registry[owner_key]
        assert surviving_reference is replacement_reference
        assert surviving_state is replacement_state
        assert surviving_reference() is replacement
    finally:
        registry[owner_key] = (owner_reference, owner_state)

    assert bool(owner) is True
    assert bool(replacement) is True
    assert len(registry) == baseline + 2
    del owner
    del replacement
    gc.collect()
    assert owner_key not in registry
    assert replacement_key not in registry
    assert len(registry) == baseline


# ============================================================================================================
# Immutability and absent container protocol
# ============================================================================================================
def test_artifact_inherits_no_builtin_container_or_scalar_base() -> None:
    assert RoughtimeV19RequestInSignedResponse.__mro__ == (RoughtimeV19RequestInSignedResponse, object)
    assert RoughtimeV19RequestInSignedResponse.__bases__ == (object,)
    for forbidden in (tuple, list, dict, set, frozenset, bytes, bytearray, str, int, float):
        assert not issubclass(RoughtimeV19RequestInSignedResponse, forbidden), forbidden
    assert RoughtimeV19RequestInSignedResponse.__name__ == "RoughtimeV19RequestInSignedResponse"
    assert RoughtimeV19RequestInSignedResponse.__qualname__ == "RoughtimeV19RequestInSignedResponse"
    assert (
        RoughtimeV19RequestInSignedResponse.__module__
        == "crypto_core.validation.roughtime_v19_request_in_signed_response"
    )


def test_artifact_has_no_instance_dict_and_only_a_weakref_slot() -> None:
    artifact = _artifact()
    assert RoughtimeV19RequestInSignedResponse.__slots__ == ("__weakref__",)
    assert not hasattr(artifact, "__dict__")
    assert type(artifact).__dictoffset__ == 0
    assert "__dict__" not in dir(artifact)
    with pytest.raises(TypeError):
        vars(artifact)


@pytest.mark.parametrize("field", _EXPECTED_PUBLIC_FIELDS)
def test_setattr_and_delattr_rejected_for_every_public_field(field) -> None:
    artifact = _artifact()
    before = getattr(artifact, field)
    for mutate in (
        lambda: setattr(artifact, field, bytes(32)),
        lambda: delattr(artifact, field),
        lambda: object.__setattr__(artifact, field, bytes(32)),
        lambda: object.__delattr__(artifact, field),
    ):
        with pytest.raises(AttributeError):
            mutate()
    assert getattr(artifact, field) == before


@pytest.mark.parametrize("name", ["provider_id", "ready", "_cache", "_verified", "__dict__"])
def test_arbitrary_state_cannot_be_added(name) -> None:
    artifact = _artifact()
    for mutate in (
        lambda: setattr(artifact, name, True),
        lambda: object.__setattr__(artifact, name, True),
    ):
        with pytest.raises(AttributeError):
            mutate()


def test_no_public_property_is_a_writable_descriptor() -> None:
    for name in _EXPECTED_PUBLIC_FIELDS:
        descriptor = getattr(RoughtimeV19RequestInSignedResponse, name)
        assert type(descriptor) is property
        assert descriptor.fset is None, name
        assert descriptor.fdel is None, name


_SEQUENCE_PROTOCOL_NAMES = (
    "__getitem__",
    "__setitem__",
    "__delitem__",
    "__iter__",
    "__next__",
    "__len__",
    "__contains__",
    "__reversed__",
    "__add__",
    "__mul__",
    "__rmul__",
    "__getnewargs__",
    "count",
    "index",
)


@pytest.mark.parametrize("name", _SEQUENCE_PROTOCOL_NAMES)
def test_sequence_protocol_is_absent_from_the_artifact(name) -> None:
    artifact = _artifact()
    assert not hasattr(RoughtimeV19RequestInSignedResponse, name), name
    assert not hasattr(artifact, name), name


def test_sequence_operations_fail_without_exposing_proof_state() -> None:
    artifact = _artifact()
    secret = artifact.signed_root.hex()
    for label, operation in (("len", len), ("iter", iter), ("reversed", reversed)):
        with pytest.raises(TypeError) as excinfo:
            operation(artifact)
        assert secret not in str(excinfo.value), label
    for label, operation in (
        ("index", lambda obj: obj[0]),
        ("membership", lambda obj: b"x" in obj),
        ("unpack", lambda obj: [*obj]),
        ("concat", lambda obj: obj + ()),
        ("repeat", lambda obj: obj * 2),
    ):
        with pytest.raises(TypeError) as excinfo:
            operation(artifact)
        assert secret not in str(excinfo.value), label


@pytest.mark.parametrize("operation", ["lt", "le", "gt", "ge"])
def test_ordering_is_inapplicable(operation) -> None:
    with pytest.raises(TypeError):
        getattr(operator, operation)(_artifact(), _artifact())


@pytest.mark.parametrize("base", [tuple, list, dict, bytes, bytearray, str, set, frozenset])
def test_unbound_builtin_base_calls_are_inapplicable(base) -> None:
    artifact = _artifact()
    hollow = object.__new__(RoughtimeV19RequestInSignedResponse)
    for subject in (artifact, hollow):
        with pytest.raises(TypeError) as excinfo:
            base.__repr__(subject)
        assert artifact.signed_root.hex() not in str(excinfo.value)


def test_every_subclass_form_is_sealed() -> None:
    ledger: list[str] = []

    def _ordinary() -> type:
        class _Ordinary(RoughtimeV19RequestInSignedResponse):
            pass

        return _Ordinary

    def _new_override() -> type:
        class _NoValidation(RoughtimeV19RequestInSignedResponse):
            def __new__(cls, **fields: object) -> object:
                ledger.append("__new__")
                return object.__new__(cls)

        return _NoValidation

    for definer in (_ordinary, _new_override):
        with pytest.raises(TypeError) as excinfo:
            definer()
        assert type(excinfo.value) is TypeError
        assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    with pytest.raises(TypeError) as excinfo:
        type("_Dynamic", (RoughtimeV19RequestInSignedResponse,), {"__getattribute__": object.__getattribute__})
    assert str(excinfo.value) == _EXPECTED_SEAL_MESSAGE
    assert ledger == []


# ============================================================================================================
# Narrow exception normalization
# ============================================================================================================
def _enclosing_function_names(tree: ast.Module) -> dict[ast.ExceptHandler, str]:
    owner: dict[ast.ExceptHandler, str] = {}
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        current = parents.get(node)
        while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            current = parents.get(current)
        owner[node] = current.name if current is not None else "<module>"
    return owner


_ALLOWED_CAUGHT_EXCEPTIONS = {
    "RoughtimeV19RequestSemanticError",
    "RoughtimeV19ResponseSemanticError",
    "RoughtimeV19RequestInclusionError",
    "RoughtimeV19CertificateVerificationError",
    "RoughtimeV19SignedResponseVerificationError",
}


def test_production_catches_only_the_five_prerequisite_domain_errors() -> None:
    """No broad catch of any kind: only the closed prerequisite domain error classes may be normalized."""
    tree = _production_tree()
    caught: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        assert node.type is not None, "a bare except is forbidden"
        caught.update(child.id for child in ast.walk(node.type) if isinstance(child, ast.Name))
    assert caught == _ALLOWED_CAUGHT_EXCEPTIONS
    forbidden = {
        "Exception",
        "BaseException",
        "RuntimeError",
        "AssertionError",
        "AttributeError",
        "TypeError",
        "ValueError",
        "LookupError",
        "KeyError",
        "IndexError",
        "ArithmeticError",
        "OSError",
        "KeyboardInterrupt",
        "SystemExit",
        "GeneratorExit",
    }
    assert caught & forbidden == set()


def test_production_source_contains_no_broad_except_clause() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    for forbidden in ("except Exception", "except BaseException", "except:", "except (Exception"):
        assert forbidden not in source, forbidden


def test_assertion_error_from_a_prerequisite_propagates_unchanged(monkeypatch) -> None:
    """A programmer defect must never be laundered into a caller-controlled inconsistency reason."""
    import crypto_core.validation.roughtime_v19_request_in_signed_response as module

    def _boom(*args, **kwargs):
        raise AssertionError("invariant broken")

    monkeypatch.setattr(module, "verify_roughtime_v19_request_inclusion", _boom)
    with pytest.raises(AssertionError) as excinfo:
        RoughtimeV19RequestInSignedResponse(**_anchors())
    assert str(excinfo.value) == "invariant broken"


class _ProgrammerDefect(Exception):
    """An exception class the production module cannot possibly have enumerated."""


@pytest.mark.parametrize(
    "target",
    [
        "parse_roughtime_v19_request",
        "parse_roughtime_v19_response",
        "verify_roughtime_v19_request_inclusion",
        "verify_roughtime_v19_certificate",
        "verify_roughtime_v19_signed_response",
    ],
)
def test_custom_programmer_exception_propagates_unchanged(target, monkeypatch) -> None:
    import crypto_core.validation.roughtime_v19_request_in_signed_response as module

    def _boom(*args, **kwargs):
        raise _ProgrammerDefect("unrelated internal failure")

    monkeypatch.setattr(module, target, _boom)
    with pytest.raises(_ProgrammerDefect):
        RoughtimeV19RequestInSignedResponse(**_anchors())


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_base_exception_is_never_swallowed(interrupt, monkeypatch) -> None:
    import crypto_core.validation.roughtime_v19_request_in_signed_response as module

    def _boom(*args, **kwargs):
        raise interrupt()

    monkeypatch.setattr(module, "verify_roughtime_v19_signed_response", _boom)
    with pytest.raises(interrupt):
        RoughtimeV19RequestInSignedResponse(**_anchors())


def test_no_raw_prerequisite_exception_leaks_from_the_public_surfaces() -> None:
    """Every caller-reachable defect closes as this module's own reason, never a prerequisite class."""
    inclusion, signed_response = _pair()
    _, foreign = _packets(request_nonce=bytes(range(70, 102)))
    for first, second in (
        (inclusion, _signed(foreign)),
        (object.__new__(RoughtimeV19RequestInclusion), signed_response),
    ):
        with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
            verify_roughtime_v19_request_in_signed_response(first, second)
        assert type(excinfo.value) is RoughtimeV19RequestInSignedResponseError
    anchors = _anchors()
    anchors["response_raw"] = b"ROUGHTIM"
    with pytest.raises(RoughtimeV19RequestInSignedResponseError) as excinfo:
        RoughtimeV19RequestInSignedResponse(**anchors)
    assert excinfo.value.reason is R.ARTIFACT_AGGREGATE_INCONSISTENT


# ============================================================================================================
# Import policy, absence of new cryptography, and protected invariants
# ============================================================================================================
def test_verifier_rebuilds_both_prerequisites_instead_of_trusting_the_caller_objects() -> None:
    """Structural pin for a mandated step whose behaviour is redundant by construction.

    Both inputs are exact-typed and sealed, and the K4 input is fully re-proven by its own base
    ``__post_init__`` before anything is read, so trusting the caller object instead of a fresh rebuild
    produces the same observable behaviour today. The rebuild is nonetheless required by the accepted
    contract, so it is pinned here: removing either reconstruction, or the base revalidation call, fails this
    named test.
    """
    node = _production_function("verify_roughtime_v19_request_in_signed_response")
    constructed = {
        child.func.id for child in ast.walk(node) if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    assert "RoughtimeV19RequestInclusion" in constructed
    assert "RoughtimeV19SignedResponseVerification" in constructed
    attributes = {child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)}
    assert "__post_init__" in attributes
    source = _production_function_source("verify_roughtime_v19_request_in_signed_response")
    assert "fresh_inclusion = RoughtimeV19RequestInclusion(**inclusion_state)" in source
    assert "fresh_signed_response = RoughtimeV19SignedResponseVerification(**signed_response_state)" in source


def test_three_anchor_reconstruction_retains_every_cross_contract_drift_guard() -> None:
    """Structural pin for three comparisons that are unreachable inside the reconstruction path.

    ``_derived_state`` starts from ONE response, so K4's declared root, SREP's signed root and both
    ``response_raw`` values are all derived from that same source and cannot disagree today. The guards are
    retained as cross-contract drift protection for a future prerequisite change, and are pinned structurally
    because an unreachable branch cannot honestly be proven behaviourally. The equivalent comparisons in the
    public verifier, where two INDEPENDENT artifacts meet, are separately proven by the binding tests above.
    """
    source = _production_function_source("_derived_state")
    for guard in (
        "if inclusion.computed_root != inclusion.declared_root:",
        "if inclusion.declared_root != signed_response.signed_root:",
        "if inclusion.response_raw != signed_response.response_raw:",
    ):
        assert guard in source, guard


def test_production_imports_only_public_prerequisite_symbols() -> None:
    imported: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
            for alias in node.names:
                imported.add(alias.name)
    assert modules == {
        "__future__",
        "enum",
        "weakref",
        "crypto_core.validation.roughtime_v19_certificate_verification",
        "crypto_core.validation.roughtime_v19_request_inclusion",
        "crypto_core.validation.roughtime_v19_request_semantics",
        "crypto_core.validation.roughtime_v19_response_semantics",
        "crypto_core.validation.roughtime_v19_signed_response_verification",
    }
    for name in imported:
        if name in ("annotations", "Enum", "ReferenceType"):
            continue
        assert not name.startswith("_"), f"private prerequisite import: {name}"


def test_production_performs_no_new_cryptographic_operation() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    tree = _production_tree()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    for forbidden in ("hashlib", "hmac", "nacl", "cryptography", "ssl"):
        assert forbidden not in modules, forbidden
    for forbidden in (
        "sha512",
        "sha256",
        "SigningKey",
        "VerifyKey",
        "RawEncoder",
        "digest(",
        "crypto_sign",
        "\\x00",
        "\\x01",
    ):
        assert forbidden not in source, forbidden


def test_production_reads_no_clock_randomness_or_external_resource() -> None:
    modules: set[str] = set()
    for node in ast.walk(_production_tree()):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    for forbidden in (
        "time",
        "datetime",
        "random",
        "secrets",
        "os",
        "socket",
        "requests",
        "pathlib",
        "subprocess",
        "threading",
        "asyncio",
    ):
        assert forbidden not in modules, forbidden


def test_production_uses_no_isinstance() -> None:
    calls = {
        node.func.id
        for node in ast.walk(_production_tree())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "isinstance" not in calls


def test_production_contains_no_bist_reference() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("bist", "kap", "ideal", "matriks", "borsa"):
        assert forbidden not in source, forbidden


_PROTECTED_DIGESTS = {
    "roughtime_v19_kernel.py": "3ef6d6ec400bc395580606980c4ee0afecec2fa7488070718e4e87ab9706da11",
    "roughtime_v19_response_semantics.py": "1cd222147413ddd25c3249c93900a3fa9da90090e789a0b0dfe3488c671eded1",
    "roughtime_v19_request_semantics.py": "7fe884baab27728746c91cc796ec91b70cf1db62b7e0eec7317241a3e9cfea8b",
    "roughtime_v19_request_inclusion.py": "451d16de6dc565071858ae1c7506b19144b6f9db75139de328fc9f5c9e7a0d53",
    "roughtime_v19_certificate_verification.py": "19f365695a3d8e70063dcdac685c7047ea5e1e4120373a35fc64d67a073578cf",
    "roughtime_v19_signed_response_verification.py": "64b3a4f56905685ca8daff8d67f3500b0bfd0712bb9c2980161b107827e016a5",
}


@pytest.mark.parametrize(("filename", "digest"), sorted(_PROTECTED_DIGESTS.items()))
def test_protected_prerequisite_files_are_unchanged(filename, digest) -> None:
    """This slice composes its prerequisites and must never modify one of them."""
    path = _PRODUCTION_PATH.parent / filename
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, filename


def test_composition_causes_no_readiness_or_connector_transition() -> None:
    from crypto_core.venue.public_feed_dialects import connector_ready_dialects

    before = tuple(spec.dialect_id for spec in connector_ready_dialects())
    _artifact()
    after = tuple(spec.dialect_id for spec in connector_ready_dialects())
    assert before == after == ("deribit:l2_orderbook:book_instrument_interval",)


def test_production_declares_no_readiness_or_connector_symbol() -> None:
    source = _PRODUCTION_PATH.read_text(encoding="utf-8")
    tree = _production_tree()
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    identifiers = {token.lower() for token in attributes | names}
    for forbidden in (
        "mt4_verifier_profile_selected",
        "readiness_promoted",
        "connector_promoted",
        "operational_readiness",
        "live_ready",
        "shadow_ready",
        "deribit_ready",
    ):
        assert forbidden not in identifiers, forbidden
        assert forbidden not in source, forbidden
