"""Tests for the MT4-RT19 attested-operational-day digest to authenticated request-NONC binding.

Permanent contract: 103 named tests (T01-T103), 19 validating consumption surfaces, and a 4 x 19 = 76 case
invalid-artifact-state matrix. Every fixture is deterministic and built from fixed disclosed seeds; production
never signs and never generates a key.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import json
import operator
import pickle
import re
import weakref
from dataclasses import fields, replace
from pathlib import Path

import pytest
from nacl.encoding import RawEncoder
from nacl.signing import SigningKey

from crypto_core.validation import roughtime_v19_attested_operational_day_digest_binding as binding_module
from crypto_core.validation.paper_attested_operational_day_evidence import (
    PaperAttestedOperationalDayEvidence,
    PaperAttestedOperationalDayEvidenceStatus,
    build_paper_attested_operational_day_evidence,
    paper_attested_operational_day_evidence_digest,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.roughtime_v19_attested_operational_day_digest_binding import (
    ROUGHTIME_V19_ATTESTED_OPERATIONAL_DAY_DIGEST_BINDING_PROFILE_ID,
    RoughtimeV19AttestedOperationalDayDigestBinding,
    RoughtimeV19AttestedOperationalDayDigestBindingError,
    RoughtimeV19AttestedOperationalDayDigestBindingReason,
    verify_roughtime_v19_attested_operational_day_digest_binding,
)
from crypto_core.validation.roughtime_v19_certificate_verification import verify_roughtime_v19_certificate
from crypto_core.validation.roughtime_v19_request_in_signed_response import (
    RoughtimeV19RequestInSignedResponse,
    verify_roughtime_v19_request_in_signed_response,
)
from crypto_core.validation.roughtime_v19_request_inclusion import (
    RoughtimeV19RequestInclusion,
    verify_roughtime_v19_request_inclusion,
)
from crypto_core.validation.roughtime_v19_request_semantics import parse_roughtime_v19_request
from crypto_core.validation.roughtime_v19_response_semantics import parse_roughtime_v19_response
from crypto_core.validation.roughtime_v19_signed_response_verification import (
    RoughtimeV19SignedResponseVerification,
    verify_roughtime_v19_signed_response,
)

R = RoughtimeV19AttestedOperationalDayDigestBindingReason
_ERROR = RoughtimeV19AttestedOperationalDayDigestBindingError
_BINDING = RoughtimeV19AttestedOperationalDayDigestBinding

_PROFILE_ID = "roughtime-v19-attested-operational-day-digest-request-nonce-binding.v1"

_PRODUCTION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "crypto_core"
    / "validation"
    / "roughtime_v19_attested_operational_day_digest_binding.py"
)
_PRODUCTION_SOURCE = _PRODUCTION_PATH.read_text(encoding="utf-8")
_PRODUCTION_TREE = ast.parse(_PRODUCTION_SOURCE)

# --- Governed-day fixture constants -----------------------------------------------------------------------
_DAY_NS = 86_400_000_000_000
_BASE_INDEX = 19_700
_MARKET = "BTC-PERPETUAL"
_CORRELATION = "corr-1"
_HEX_A = "a" * 64

# --- Roughtime transcript constants (needed only to BUILD fixtures, never to verify) -----------------------
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
_TAG_ZZZZ = b"ZZZZ"

# TEST-ONLY deterministic keys from fixed disclosed seeds. Production never signs and never generates a key.
_LONG_TERM_SIGNING_KEY = SigningKey(bytes(range(32)), encoder=RawEncoder)
_DELEGATED_SIGNING_KEY = SigningKey(bytes(range(100, 132)), encoder=RawEncoder)
_LONG_TERM_PUBLIC_KEY = bytes(_LONG_TERM_SIGNING_KEY.verify_key)
_DELEGATED_PUBLIC_KEY = bytes(_DELEGATED_SIGNING_KEY.verify_key)

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

LEFT = "LEFT"
RIGHT = "RIGHT"

_MAX_PACKET_BYTES = 4096
_PACKET_FRAME_BYTES = 12
_MAX_MESSAGE_BYTES = _MAX_PACKET_BYTES - _PACKET_FRAME_BYTES

_FIXED_TEMPLATE_LENGTH = 445
_HARD_REPR_CAP = 512
_PROVEN_MAXIMUM_RENDERED_LENGTH = 455


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


class _LiarInt(int):
    """An ``int`` subclass rejected by exact ``type(x) is int`` checks."""


class _LiarBytes(bytes):
    """A ``bytes`` subclass rejected by exact ``type(x) is bytes`` checks."""


class _DaySubclass(PaperAttestedOperationalDayEvidence):
    """A governed-day SUBCLASS: value-equal but rejected by the exact-type gate."""


class _ProbeError(Exception):
    """An unrelated programmer exception used to prove nothing broad is caught."""


# --- Test-only encoders (independent of every production encoder) ------------------------------------------
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


# --- Test-only Merkle oracle (explicit direction tokens; never imports K4) ---------------------------------
def _oracle_leaf(request_packet: bytes) -> bytes:
    return hashlib.sha512(b"\x00" + request_packet).digest()[:_DIGEST_BYTES]


def _oracle_root(leaf: bytes, steps: tuple[tuple[str, bytes], ...]) -> bytes:
    current = leaf
    for direction, sibling in steps:
        if direction == LEFT:
            current = hashlib.sha512(b"\x01" + current + sibling).digest()[:_DIGEST_BYTES]
        elif direction == RIGHT:
            current = hashlib.sha512(b"\x01" + sibling + current).digest()[:_DIGEST_BYTES]
        else:  # pragma: no cover - defensive
            raise ValueError("direction must be LEFT or RIGHT")
    return current


def _oracle_index(directions: tuple[str, ...]) -> int:
    index = 0
    for depth, direction in enumerate(directions):
        if direction == RIGHT:
            index |= 1 << depth
    return index


# --- Independent test-side canonical day digest (never the production digest function) ---------------------
def _independent_day_digest(day: PaperAttestedOperationalDayEvidence) -> str:
    payload: dict[str, object] = {}
    for field in fields(day):
        if field.name == "attested_operational_day_evidence_digest":
            continue
        value = getattr(day, field.name)
        if field.name == "status":
            payload[field.name] = day.status.value
        elif field.name == "metadata":
            payload[field.name] = [[key, item] for key, item in day.metadata]
        elif type(value) is tuple:
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Governed-day fixtures ---------------------------------------------------------------------------------
def _window(index: int, *, suffix: str = "0", market_symbol: str = _MARKET) -> PaperDeterministicTimeWindowEvidence:
    started_at_ns = index * _DAY_NS + (int(suffix) if suffix.isdigit() else 0) * 7_200_000_000_000
    duration_ns = 3_600_000_000_000
    payload: dict[str, object] = {
        "schema_version": "paper-deterministic-time-window-evidence.v1",
        "time_window_version": "paper-deterministic-time-window.v1",
        "status": PaperDeterministicTimeWindowEvidenceStatus.READY,
        "ready": True,
        "window_id": f"window-{index}-{suffix}",
        "methodology_id": "method-1",
        "timestamp_policy": "injected_deterministic_ns.v1",
        "run_id": f"run-{index}-{suffix}",
        "aggregate_id": f"agg-{index}-{suffix}",
        "correlation_id": _CORRELATION,
        "market_symbol": market_symbol,
        "expected_metrics_summary_digest": _HEX_A,
        "metrics_summary_digest": _HEX_A,
        "summary_ready": True,
        "summary_readiness_verdict": "PAPER_STAGE4_CANDIDATE",
        "started_at_ns": started_at_ns,
        "stopped_at_ns": started_at_ns + duration_ns,
        "window_duration_ns": duration_ns,
        "sample_observation_count": 5,
        "sample_eligible": True,
        "session_bridge_count": 1,
        "episode_count_total": 1,
        "event_count": 1,
        "computed_event_count": 1,
        "no_realized_event_count": 0,
        "source_event_digest_count": 1,
        "closed_units_total": "1",
        "realized_pnl_total": "1",
        "abs_realized_pnl_total": "1",
        "reason_codes": (),
        "metadata": (),
    }
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **payload)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _day(
    index: int = _BASE_INDEX,
    *,
    sessions: int = 1,
    correlation_id: str = _CORRELATION,
    market_symbol: str = _MARKET,
    attestor_id: str = "operator-1",
    metadata: dict[str, str] | None = None,
) -> PaperAttestedOperationalDayEvidence:
    windows = tuple(_window(index, suffix=str(offset), market_symbol=market_symbol) for offset in range(sessions))
    return build_paper_attested_operational_day_evidence(
        windows,
        expected_session_window_digests=tuple(window.time_window_digest for window in windows),
        attested_utc_day_index=index,
        attestor_id=attestor_id,
        attestation_id=f"attestation-{index}",
        operational_day_evidence_id=f"operational-day-{index}",
        correlation_id=correlation_id,
        metadata={"purpose": "attested operational day"} if metadata is None else metadata,
    )


def _reseal_day(day: PaperAttestedOperationalDayEvidence, **changes: object) -> PaperAttestedOperationalDayEvidence:
    seed = replace(day, **changes)  # type: ignore[arg-type]
    return replace(seed, attested_operational_day_evidence_digest=paper_attested_operational_day_evidence_digest(seed))


def _mutated_day(day: PaperAttestedOperationalDayEvidence, **changes: object) -> PaperAttestedOperationalDayEvidence:
    """Change a carried field WITHOUT resealing, so the carried digest goes stale (D19)."""
    return replace(day, **changes)  # type: ignore[arg-type]


# --- Roughtime packet fixtures -----------------------------------------------------------------------------
def _request_packet(
    *,
    nonce: bytes,
    versions: tuple[int, ...] = (1,),
    srv: bytes | None = None,
    padding: bytes | None = None,
) -> bytes:
    pairs: list[tuple[bytes, bytes]] = [
        (_TAG_VER, b"".join(_u32(version) for version in versions)),
        (_TAG_NONC, nonce),
        (_TAG_TYPE, _u32(0)),
    ]
    if srv is not None:
        pairs.append((_TAG_SRV, srv))
    if padding is not None:
        pairs.append((_TAG_ZZZZ, padding))
    return _encode_packet(_encode_message(pairs))


def _dele_raw(*, delegated_public_key: bytes = _DELEGATED_PUBLIC_KEY) -> bytes:
    return _encode_message(
        [(_TAG_PUBK, delegated_public_key), (_TAG_MINT, _u64(_MIN_TIME)), (_TAG_MAXT, _u64(_MAX_TIME))]
    )


def _cert_raw(*, signing_key: SigningKey = _LONG_TERM_SIGNING_KEY) -> bytes:
    delegation = _dele_raw()
    signature = signing_key.sign(_CERT_CONTEXT + delegation).signature
    return _encode_message([(_TAG_SIG, signature), (_TAG_DELE, delegation)])


def _srep_raw(root: bytes) -> bytes:
    return _encode_message(
        [
            (_TAG_VER, _u32(_SELECTED_VERSION)),
            (_TAG_RADI, _u32(_RADIUS)),
            (_TAG_MIDP, _u64(_MIDPOINT)),
            (_TAG_VERS, b"".join(_u32(version) for version in _SIGNED_VERSIONS)),
            (_TAG_ROOT, root),
        ]
    )


def _response_packet(
    *,
    root: bytes,
    path: tuple[bytes, ...] = (_SIBLING_A,),
    index: int = 0,
    nonce: bytes = _RESPONSE_NONCE,
    long_term_signing_key: SigningKey = _LONG_TERM_SIGNING_KEY,
    padding: bytes | None = None,
) -> bytes:
    signed_response = _srep_raw(root)
    outer_signature = _DELEGATED_SIGNING_KEY.sign(_SREP_CONTEXT + signed_response).signature
    pairs: list[tuple[bytes, bytes]] = [
        (_TAG_SIG, outer_signature),
        (_TAG_NONC, nonce),
        (_TAG_TYPE, _u32(1)),
        (_TAG_PATH, b"".join(path)),
        (_TAG_SREP, signed_response),
        (_TAG_CERT, _cert_raw(signing_key=long_term_signing_key)),
        (_TAG_INDX, _u32(index)),
    ]
    if padding is not None:
        pairs.append((_TAG_ZZZZ, padding))
    return _encode_packet(_encode_message(pairs))


def _packets(
    *,
    nonce: bytes,
    path: tuple[bytes, ...] = (_SIBLING_A,),
    directions: tuple[str, ...] | None = None,
    response_nonce: bytes = _RESPONSE_NONCE,
    srv: bytes | None = None,
    request_padding: bytes | None = None,
    response_padding: bytes | None = None,
    long_term_signing_key: SigningKey = _LONG_TERM_SIGNING_KEY,
    root: bytes | None = None,
) -> tuple[bytes, bytes]:
    request = _request_packet(nonce=nonce, srv=srv, padding=request_padding)
    if directions is None:
        directions = tuple(LEFT for _ in path)
    derived_root = _oracle_root(_oracle_leaf(request), tuple(zip(directions, path))) if root is None else root
    response = _response_packet(
        root=derived_root,
        path=path,
        index=_oracle_index(directions),
        nonce=response_nonce,
        long_term_signing_key=long_term_signing_key,
        padding=response_padding,
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


def _aggregate(
    request: bytes, response: bytes, *, long_term_public_key: bytes = _LONG_TERM_PUBLIC_KEY
) -> RoughtimeV19RequestInSignedResponse:
    return verify_roughtime_v19_request_in_signed_response(
        _inclusion(request, response), _signed(response, long_term_public_key=long_term_public_key)
    )


def _aggregate_for(day: PaperAttestedOperationalDayEvidence, **kwargs) -> RoughtimeV19RequestInSignedResponse:
    request, response = _packets(nonce=bytes.fromhex(day.attested_operational_day_evidence_digest), **kwargs)
    return _aggregate(request, response)


def _bound(day: PaperAttestedOperationalDayEvidence | None = None, **kwargs) -> _BINDING:
    day = _day() if day is None else day
    return verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate_for(day, **kwargs))


def _max_boundary_parts() -> tuple[PaperAttestedOperationalDayEvidence, bytes, bytes]:
    """A GENUINE 4096/4096/32 fixture accepted by the real public prerequisite contracts.

    Request: four pairs VER/NONC/TYPE/ZZZZ with 4012 all-zero padding bytes (K3 requires every ZZZZ byte to be
    zero); message 4084, packet 4096. Response: the seven mandatory outer pairs plus ONE all-zero ZZZZ tag,
    which sorts last (0x5a5a5a5a > INDX 0x58444e49) and is preserved as an unknown outer extension; the signed
    SREP and CERT bytes are untouched, so no signature is affected. The padding length is COMPUTED, then the
    exact 4096/4096 lengths are asserted by the caller.
    """
    day = _day(_BASE_INDEX + 1)
    nonce = bytes.fromhex(day.attested_operational_day_evidence_digest)
    request = _request_packet(nonce=nonce, padding=b"\x00" * 4012)
    root = _oracle_root(_oracle_leaf(request), ((LEFT, _SIBLING_A),))
    unpadded = _response_packet(root=root)
    # One extra pair costs 4 offset bytes + 4 tag bytes on top of its value.
    padding_length = _MAX_MESSAGE_BYTES - (len(unpadded) - _PACKET_FRAME_BYTES) - 8
    response = _response_packet(root=root, padding=b"\x00" * padding_length)
    return day, request, response


def _max_boundary_binding() -> tuple[_BINDING, PaperAttestedOperationalDayEvidence, bytes, bytes]:
    day, request, response = _max_boundary_parts()
    binding = verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response))
    return binding, day, request, response


# --- Lifecycle helpers -------------------------------------------------------------------------------------
def _hollow(cls, **attributes):
    obj = object.__new__(cls)
    for name, value in attributes.items():
        object.__setattr__(obj, name, value)
    return obj


def _closure_registry() -> dict:
    """Locate the closure-local registry for lifecycle assertions. Test-only implementation inspection.

    Explicitly OUTSIDE the supported trust boundary - this path exists only to prove lifecycle cleanup and
    identity binding, and is deliberately not a documented or public API. It makes no claim that closure
    contents are secret.
    """
    seen: list[dict] = []
    for cell in _BINDING.__bool__.__closure__ or ():
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


def _registered_state(binding: _BINDING) -> tuple:
    """The four verified values, obtained through the public validating reducer (never the registry)."""
    reducer, arguments = binding.__reduce__()
    assert reducer.__name__ == "_rebuild_attested_operational_day_digest_binding"
    state = arguments[0]
    assert type(state) is tuple
    return state


def _expected_repr(
    day_digest: str, request_raw: bytes, response_raw: bytes, long_term_public_key: bytes, signed_root: bytes
) -> str:
    """Assemble the expected representation INDEPENDENTLY from named already-proven values."""
    return (
        "RoughtimeV19AttestedOperationalDayDigestBinding("
        "operational_day=<PaperAttestedOperationalDayEvidence READY fields=66>, "
        f"attested_operational_day_evidence_digest=<hex64:{day_digest}>, "
        f"request_raw=<bytes len={len(request_raw)} redacted>, "
        f"response_raw=<bytes len={len(response_raw)} redacted>, "
        f"long_term_public_key=<bytes len={len(long_term_public_key)} redacted>, "
        f"signed_root=<bytes len=32 hex={signed_root.hex()}>"
        ")"
    )


_REPR_PATTERN = re.compile(
    r"\A"
    + re.escape("RoughtimeV19AttestedOperationalDayDigestBinding(operational_day=<")
    + r"PaperAttestedOperationalDayEvidence READY fields=66"
    + re.escape(">, attested_operational_day_evidence_digest=<hex64:")
    + r"(?P<digest>[0-9a-f]{64})"
    + re.escape(">, request_raw=<bytes len=")
    + r"(?P<request_len>[1-9][0-9]{0,3})"
    + re.escape(" redacted>, response_raw=<bytes len=")
    + r"(?P<response_len>[1-9][0-9]{0,3})"
    + re.escape(" redacted>, long_term_public_key=<bytes len=")
    + r"(?P<key_len>32)"
    + re.escape(" redacted>, signed_root=<bytes len=32 hex=")
    + r"(?P<root_hex>[0-9a-f]{64})"
    + re.escape(">)")
    + r"\Z"
)


# --- AST helpers -------------------------------------------------------------------------------------------
def _production_function(name: str) -> ast.AST:
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def _production_function_source(name: str) -> str:
    return ast.get_source_segment(_PRODUCTION_SOURCE, _production_function(name)) or ""


_EXPECTED_EXPORTS = (
    "ROUGHTIME_V19_ATTESTED_OPERATIONAL_DAY_DIGEST_BINDING_PROFILE_ID",
    "RoughtimeV19AttestedOperationalDayDigestBinding",
    "RoughtimeV19AttestedOperationalDayDigestBindingError",
    "RoughtimeV19AttestedOperationalDayDigestBindingReason",
    "verify_roughtime_v19_attested_operational_day_digest_binding",
)
_EXPECTED_PUBLIC_FIELDS = (
    "operational_day",
    "attested_operational_day_evidence_digest",
    "request_raw",
    "response_raw",
    "long_term_public_key",
    "signed_root",
)
_EXPECTED_ANCHOR_FIELDS = (
    "operational_day",
    "request_raw",
    "response_raw",
    "long_term_public_key",
)
_EXPECTED_REASONS = (
    ("WRONG_INPUT_TYPE", "wrong_input_type"),
    ("GOVERNED_DAY_ARTIFACT_INCONSISTENT", "governed_day_artifact_inconsistent"),
    ("REQUEST_IN_SIGNED_RESPONSE_INCONSISTENT", "request_in_signed_response_inconsistent"),
    ("DAY_DIGEST_REQUEST_NONCE_MISMATCH", "day_digest_request_nonce_mismatch"),
    ("BINDING_ARTIFACT_INCONSISTENT", "binding_artifact_inconsistent"),
)


# ==========================================================================================================
# A. IDENTITY / API / ERROR (T01-T06)
# ==========================================================================================================
def test_t01_profile_id_is_the_exact_pinned_string() -> None:
    assert ROUGHTIME_V19_ATTESTED_OPERATIONAL_DAY_DIGEST_BINDING_PROFILE_ID == _PROFILE_ID
    assert type(ROUGHTIME_V19_ATTESTED_OPERATIONAL_DAY_DIGEST_BINDING_PROFILE_ID) is str


def test_t02_public_exports_and_verifier_signature_are_exact() -> None:
    """Kills any reintroduced caller digest / expected-digest / policy parameter."""
    assert tuple(binding_module.__all__) == _EXPECTED_EXPORTS
    node = _production_function("verify_roughtime_v19_attested_operational_day_digest_binding")
    assert isinstance(node, ast.FunctionDef)
    args = node.args
    assert args.posonlyargs == []
    assert args.kwonlyargs == []
    assert args.vararg is None and args.kwarg is None
    assert [arg.arg for arg in args.args] == ["operational_day", "request_in_signed_response"]
    assert [ast.unparse(arg.annotation) for arg in args.args] == [
        "PaperAttestedOperationalDayEvidence",
        "RoughtimeV19RequestInSignedResponse",
    ]
    assert ast.unparse(node.returns) == "RoughtimeV19AttestedOperationalDayDigestBinding"


def test_t03_reason_enum_has_exactly_five_members_in_pinned_order() -> None:
    assert tuple((member.name, member.value) for member in R) == _EXPECTED_REASONS


@pytest.mark.parametrize("member", list(R))
def test_t04_error_carries_the_exact_reason_and_renders_its_value(member) -> None:
    error = _ERROR(member)
    assert error.reason is member
    assert str(error) == member.value


def test_t05_error_rejects_a_non_member_reason_without_reading_it() -> None:
    class _HostileValue:
        @property
        def value(self):  # pragma: no cover - must never run
            raise AssertionError("hostile .value was read")

    with pytest.raises(TypeError) as excinfo:
        _ERROR(_HostileValue())  # type: ignore[arg-type]
    assert type(excinfo.value) is TypeError
    assert "Reason member" in str(excinfo.value) or "Reason" in str(excinfo.value)


@pytest.mark.parametrize("name", ["reason", "_reason", "args"])
def test_t06_error_locked_attributes_reject_setattr_and_delattr(name) -> None:
    error = _ERROR(R.WRONG_INPUT_TYPE)
    with pytest.raises(AttributeError):
        setattr(error, name, "x")
    with pytest.raises(AttributeError):
        delattr(error, name)


# ==========================================================================================================
# B. POSITIVE BINDING (T07-T11)
# ==========================================================================================================
def test_t07_binding_holds_and_operational_day_is_the_exact_original_reference() -> None:
    """Exact-reference identity plus the complete mutable-reference policy."""
    day = _day()
    binding = _bound(day)
    assert binding.operational_day is day
    assert binding.operational_day is binding.operational_day
    original = day.attestor_id
    object.__setattr__(day, "attestor_id", "operator-2")
    try:
        for consume in (repr, str, bool, lambda b: b.operational_day, lambda b: b.signed_root):
            with pytest.raises(_ERROR) as excinfo:
                consume(binding)
            assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT
        with pytest.raises(TypeError):
            hash(binding)
        with pytest.raises(_ERROR):
            binding.__eq__(binding)
    finally:
        object.__setattr__(day, "attestor_id", original)
    assert binding.operational_day is day
    assert bool(binding) is True
    # Parity with the governed builder: an EMPTY metadata key is admitted upstream, so a day carrying one must
    # still bind here rather than being rejected by an incompatible non-empty constraint.
    empty_key_day = _day(_BASE_INDEX + 11, metadata={"": "x"})
    assert empty_key_day.metadata == (("", "x"),)
    assert _bound(empty_key_day).operational_day is empty_key_day


def test_t08_exposed_digest_equals_an_independent_canonical_recomputation() -> None:
    day = _day()
    binding = _bound(day)
    assert binding.attested_operational_day_evidence_digest == _independent_day_digest(day)


def test_t09_bound_digest_decodes_to_the_exact_request_nonce() -> None:
    day = _day()
    binding = _bound(day)
    decoded = bytes.fromhex(binding.attested_operational_day_evidence_digest)
    assert len(decoded) == 32
    assert decoded == parse_roughtime_v19_request(binding.request_raw).nonce


def test_t10_signed_root_matches_the_independent_oracle_and_comes_from_a_fresh_aggregate() -> None:
    day = _day()
    request, response = _packets(nonce=bytes.fromhex(day.attested_operational_day_evidence_digest))
    binding = verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response))
    expected_root = _oracle_root(_oracle_leaf(request), ((LEFT, _SIBLING_A),))
    assert binding.signed_root == expected_root


@pytest.mark.parametrize(
    ("path", "directions"),
    [
        ((), ()),
        ((_SIBLING_A,), (LEFT,)),
        ((_SIBLING_A, _SIBLING_B), (LEFT, RIGHT)),
        ((_SIBLING_A, _SIBLING_B), (RIGHT, RIGHT)),
    ],
)
def test_t11_binding_holds_for_multi_session_days_and_every_merkle_path_shape(path, directions) -> None:
    day = _day(sessions=2)
    binding = _bound(day, path=path, directions=directions)
    assert binding.operational_day is day
    assert day.session_count == 2


# ==========================================================================================================
# C. TYPE GATES (T12-T16)
# ==========================================================================================================
def _subclass_day() -> object:
    day = _day()
    values = {field.name: getattr(day, field.name) for field in fields(day)}
    return _DaySubclass(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kind",
    ["none", "bytes", "object", "dict", "int", "str", "aggregate", "subclass"],
)
def test_t12_wrong_first_input_type_is_rejected(kind) -> None:
    day = _day()
    aggregate = _aggregate_for(day)
    candidates = {
        "none": None,
        "bytes": b"raw",
        "object": object(),
        "dict": {"day": 1},
        "int": 123,
        "str": "day",
        "aggregate": aggregate,
        "subclass": _subclass_day(),
    }
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(candidates[kind], aggregate)  # type: ignore[arg-type]
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


@pytest.mark.parametrize("kind", ["day", "inclusion", "signed", "bytes", "none", "object", "tuple", "int"])
def test_t13_wrong_second_input_type_is_rejected(kind) -> None:
    day = _day()
    request, response = _packets(nonce=bytes.fromhex(day.attested_operational_day_evidence_digest))
    candidates = {
        "day": day,
        "inclusion": _inclusion(request, response),
        "signed": _signed(response),
        "bytes": response,
        "none": None,
        "object": object(),
        "tuple": (request, response, _LONG_TERM_PUBLIC_KEY),
        "int": 7,
    }
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(day, candidates[kind])  # type: ignore[arg-type]
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE


def test_t14_no_attribute_of_either_input_is_read_before_both_type_gates_pass() -> None:
    reads: list[str] = []

    class _RecordingDay:
        def __getattribute__(self, name):  # pragma: no cover - must never run
            reads.append(f"day.{name}")
            raise AttributeError(name)

    class _RecordingAggregate:
        def __getattribute__(self, name):  # pragma: no cover - must never run
            reads.append(f"aggregate.{name}")
            raise AttributeError(name)

    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(
            _RecordingDay(),  # type: ignore[arg-type]
            _RecordingAggregate(),  # type: ignore[arg-type]
        )
    assert excinfo.value.reason is R.WRONG_INPUT_TYPE
    assert reads == []


def test_t15_the_day_type_gate_precedes_the_aggregate_type_gate() -> None:
    node = _production_function("verify_roughtime_v19_attested_operational_day_digest_binding")
    source = ast.get_source_segment(_PRODUCTION_SOURCE, node) or ""
    day_gate = source.index("type(operational_day) is not PaperAttestedOperationalDayEvidence")
    aggregate_gate = source.index("type(request_in_signed_response) is not RoughtimeV19RequestInSignedResponse")
    assert day_gate < aggregate_gate
    first_read = source.index("request_in_signed_response.request_raw")
    assert aggregate_gate < first_read


def test_t16_both_gates_complete_before_any_day_field_or_aggregate_surface_is_touched(monkeypatch) -> None:
    tripped: list[str] = []
    original = binding_module.paper_attested_operational_day_evidence_digest

    def _tripwire(day):
        tripped.append("digest")
        return original(day)

    monkeypatch.setattr(binding_module, "paper_attested_operational_day_evidence_digest", _tripwire)
    day = _day()
    aggregate = _aggregate_for(day)
    for first, second in ((None, aggregate), (day, None), (object(), object())):
        with pytest.raises(_ERROR) as excinfo:
            verify_roughtime_v19_attested_operational_day_digest_binding(first, second)  # type: ignore[arg-type]
        assert excinfo.value.reason is R.WRONG_INPUT_TYPE
    assert tripped == []
    # Live-tripwire control: the same tripwire fires for a genuine call, proving it is armed.
    verify_roughtime_v19_attested_operational_day_digest_binding(day, aggregate)
    assert tripped


# ==========================================================================================================
# D. GOVERNED-DAY REVALIDATION (T17-T36)
# ==========================================================================================================
def _expect_day_rejection(day: object) -> None:
    genuine = _day()
    aggregate = _aggregate_for(genuine)
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(day, aggregate)  # type: ignore[arg-type]
    assert excinfo.value.reason is R.GOVERNED_DAY_ARTIFACT_INCONSISTENT


def test_t17_hollow_day_normalizes_without_a_raw_attribute_error() -> None:
    _expect_day_rejection(object.__new__(PaperAttestedOperationalDayEvidence))


def test_t18_pinned_field_inventory_matches_the_live_dataclass_exactly() -> None:
    live = tuple(field.name for field in fields(PaperAttestedOperationalDayEvidence))
    assert binding_module._DAY_FIELD_NAMES == live
    assert len(binding_module._DAY_FIELD_NAMES) == 66


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("status", "READY"),
        ("ready", 1),
        ("session_count", True),
        ("market_symbol", _LiarStr("BTC-PERPETUAL")),
        ("attested_utc_day_index", _LiarInt(_BASE_INDEX)),
        ("reason_codes", []),
        ("metadata", (("purpose", 1),)),
        ("session_run_ids", ("a", 2)),
        ("session_run_ids", (2,)),
        ("source_event_digest_counts", ("1",)),
    ],
)
def test_t19_non_json_safe_fields_are_rejected_before_the_digest_is_called(monkeypatch, field_name, value) -> None:
    calls: list[str] = []
    original = binding_module.paper_attested_operational_day_evidence_digest

    def _tripwire(day):
        calls.append("digest")
        return original(day)

    monkeypatch.setattr(binding_module, "paper_attested_operational_day_evidence_digest", _tripwire)
    day = _day()
    hostile = replace(day, **{field_name: value})  # type: ignore[arg-type]
    _expect_day_rejection(hostile)
    assert calls == []


@pytest.mark.parametrize("field_name", ["schema_version", "evidence_version"])
def test_t20_schema_or_evidence_version_mismatch_is_rejected(field_name) -> None:
    _expect_day_rejection(_reseal_day(_day(), **{field_name: "paper-attested-operational-day-evidence.v2"}))


@pytest.mark.parametrize(
    "field_name",
    ["attestation_source", "attestation_scope", "attestation_version", "operational_origin", "utc_day_policy"],
)
def test_t21_altered_provenance_constants_are_rejected(field_name) -> None:
    _expect_day_rejection(_reseal_day(_day(), **{field_name: "tampered.v1"}))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("status", PaperAttestedOperationalDayEvidenceStatus.REJECTED),
        ("ready", False),
        ("reason_codes", ("paper_attested_operational_day_evidence:something",)),
    ],
)
def test_t22_status_ready_and_reason_code_incoherence_is_rejected(field_name, value) -> None:
    _expect_day_rejection(_reseal_day(_day(), **{field_name: value}))


def test_t23_operator_attested_operational_day_false_is_rejected() -> None:
    """T23 OWNS the operator-attested true flag (D08 is a trace alias of D09)."""
    _expect_day_rejection(_reseal_day(_day(), operator_attested_operational_day=False))


@pytest.mark.parametrize("field_name", ["paper_only", "session_windows_consumed"])
def test_t24_remaining_true_flags_flipped_false_are_rejected(field_name) -> None:
    _expect_day_rejection(_reseal_day(_day(), **{field_name: False}))


@pytest.mark.parametrize("field_name", list(binding_module._DAY_FALSE_FLAGS))
def test_t25_every_false_flag_flipped_true_is_rejected(field_name) -> None:
    _expect_day_rejection(_reseal_day(_day(), **{field_name: True}))


@pytest.mark.parametrize(
    "field_name",
    [
        "operational_day_evidence_id",
        "correlation_id",
        "market_symbol",
        "attestor_id",
        "attestation_id",
        "metadata",
    ],
)
@pytest.mark.parametrize(
    "bad",
    [
        "",
        "  ",
        " padded",
        "with\nnewline",
        # Scope / clock admission parity with the governed builder: a RESEALED day carrying a syntactically
        # plain but forbidden token must never authenticate here either.
        "scheduler-run",
        "live_order-1",
        "capital-1",
        "wall_clock-1",
        "system_time-1",
        "bist-thing",
    ],
)
def test_t26_blank_or_non_canonical_identity_strings_are_rejected(field_name, bad) -> None:
    """D11, carrying the D18 market_symbol trace and the builder's own scope/clock admission rule."""
    if field_name == "metadata":
        if bad == "":
            # An EMPTY metadata KEY is admitted upstream; only a forbidden or non-canonical text is refused.
            return
        _expect_day_rejection(_reseal_day(_day(), metadata=(("purpose", bad),)))
        _expect_day_rejection(_reseal_day(_day(), metadata=((bad, "value"),)))
        return
    _expect_day_rejection(_reseal_day(_day(), **{field_name: bad}))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("attested_utc_day_index", 0),
        ("attested_utc_day_index", -1),
        ("day_start_ns", 1),
        ("day_end_ns", 1),
        ("day_duration_ns", 1),
    ],
)
def test_t27_day_arithmetic_incoherence_is_rejected(field_name, value) -> None:
    _expect_day_rejection(_reseal_day(_day(), **{field_name: value}))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("session_count", 0), ("session_count", -1), ("minimum_sessions_per_day", 0), ("minimum_sessions_per_day", 5)],
)
def test_t28_session_count_incoherence_is_rejected(field_name, value) -> None:
    _expect_day_rejection(_reseal_day(_day(), **{field_name: value}))


@pytest.mark.parametrize("field_name", list(binding_module._DAY_SESSION_LIST_FIELDS))
def test_t29_every_session_indexed_tuple_with_a_wrong_length_is_rejected(field_name) -> None:
    day = _day()
    current = getattr(day, field_name)
    _expect_day_rejection(_reseal_day(day, **{field_name: current + current}))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("session_started_at_ns_list", (0,)),
        ("session_stopped_at_ns_list", (0,)),
        ("session_window_duration_ns_list", (0,)),
        ("session_window_duration_ns_list", (5,)),
        ("session_started_at_ns_list", (1,)),
        ("session_stopped_at_ns_list", (_BASE_INDEX + 5) * _DAY_NS),
        ("session_metrics_summary_digests", ("z" * 64,)),
        ("session_metrics_summary_digests", ("ab",)),
        ("source_event_digest_counts", (0,)),
        ("session_run_ids", ("",)),
        ("session_window_ids", (" bad",)),
        ("session_aggregate_ids", ("bad\t",)),
    ],
)
def test_t30_invalid_per_session_content_is_rejected(field_name, value) -> None:
    day = _day()
    payload = value if type(value) is tuple else (value,)
    _expect_day_rejection(_reseal_day(day, **{field_name: payload}))


def test_t31_expected_and_verified_session_digests_must_match_element_wise() -> None:
    day = _day()
    _expect_day_rejection(_reseal_day(day, expected_session_window_digests=(_HEX_A,)))


@pytest.mark.parametrize(
    "field_name",
    ["expected_session_window_digests", "verified_session_window_digests", "session_run_ids"],
)
def test_t32_within_day_duplicates_are_rejected(field_name) -> None:
    day = _day(sessions=2)
    current = getattr(day, field_name)
    _expect_day_rejection(_reseal_day(day, **{field_name: (current[0], current[0])}))


@pytest.mark.parametrize("bad", ["", "abc", "z" * 64, "A" * 64, "a" * 63])
def test_t33_carried_self_digest_must_be_exact_lowercase_hex64(monkeypatch, bad) -> None:
    """The D19 SHAPE gate fires BEFORE the recomputation, so a malformed carried digest never reaches it."""
    calls: list[str] = []
    original = binding_module.paper_attested_operational_day_evidence_digest

    def _tripwire(day):
        calls.append("digest")
        return original(day)

    monkeypatch.setattr(binding_module, "paper_attested_operational_day_evidence_digest", _tripwire)
    _expect_day_rejection(replace(_day(), attested_operational_day_evidence_digest=bad))
    assert calls == []


def test_t34_a_stale_or_foreign_carried_self_digest_is_rejected() -> None:
    day = _day()
    _expect_day_rejection(_mutated_day(day, attestor_id="operator-9"))
    _expect_day_rejection(replace(day, attested_operational_day_evidence_digest=_HEX_A))


def test_t35_a_resealed_day_no_longer_matches_the_signed_nonce() -> None:
    day = _day()
    aggregate = _aggregate_for(day)
    resealed = _reseal_day(day, attestor_id="operator-2")
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(resealed, aggregate)
    assert excinfo.value.reason is R.DAY_DIGEST_REQUEST_NONCE_MISMATCH


def test_t36_a_rejected_day_whose_own_digest_is_the_nonce_is_still_refused() -> None:
    """The day revalidation is LOAD-BEARING, not defence-in-depth."""
    unsafe = _reseal_day(_day(), status=PaperAttestedOperationalDayEvidenceStatus.REJECTED, ready=False)
    aggregate = _aggregate_for(unsafe)
    assert (
        bytes.fromhex(unsafe.attested_operational_day_evidence_digest)
        == parse_roughtime_v19_request(aggregate.request_raw).nonce
    )
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(unsafe, aggregate)
    assert excinfo.value.reason is R.GOVERNED_DAY_ARTIFACT_INCONSISTENT


# ==========================================================================================================
# E. DIGEST DATAFLOW (T37-T40)
# ==========================================================================================================
def test_t37_bound_digest_is_sourced_from_the_fresh_recomputation() -> None:
    """STRUCTURAL DATAFLOW EVIDENCE only - not a behavioural claim."""
    source = _production_function_source("_validated_day_digest")
    assert "recomputed_digest = paper_attested_operational_day_evidence_digest(operational_day)" in source
    assert "return recomputed_digest" in source
    assert "return carried_digest" not in source


def test_t38_the_public_day_digest_is_called_exactly_once_per_derivation(monkeypatch) -> None:
    calls: list[str] = []
    original = binding_module.paper_attested_operational_day_evidence_digest

    def _counting(day):
        calls.append("digest")
        return original(day)

    day = _day()
    binding = _bound(day)
    monkeypatch.setattr(binding_module, "paper_attested_operational_day_evidence_digest", _counting)
    binding.signed_root
    assert len(calls) == 1
    assert _PRODUCTION_SOURCE.count("paper_attested_operational_day_evidence_digest(") == 1


def test_t39_no_truncation_and_no_prefix_acceptance() -> None:
    day = _day()
    genuine = day.attested_operational_day_evidence_digest
    tampered_tail = genuine[:-1] + ("0" if genuine[-1] != "0" else "1")
    tampered_head = ("0" if genuine[0] != "0" else "1") + genuine[1:]
    for candidate in (tampered_tail, tampered_head):
        request, response = _packets(nonce=bytes.fromhex(candidate))
        with pytest.raises(_ERROR) as excinfo:
            verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response))
        assert excinfo.value.reason is R.DAY_DIGEST_REQUEST_NONCE_MISMATCH


def test_t40_the_binding_comparison_is_a_single_whole_value_equality() -> None:
    for name in ("_derived_state", "verify_roughtime_v19_attested_operational_day_digest_binding"):
        source = _production_function_source(name)
        assert "bytes.fromhex(" in source
        for forbidden in ("startswith", "endswith", "[:", ":32]", "for byte", "hmac", "compare_digest"):
            assert forbidden not in source, (name, forbidden)
    node = _production_function("_derived_state")
    comparisons = [child for child in ast.walk(node) if isinstance(child, ast.Compare)]
    nonce_comparisons = [child for child in comparisons if "canonical_request.nonce" in ast.unparse(child)]
    assert len(nonce_comparisons) == 1
    assert [type(op) for op in nonce_comparisons[0].ops] == [ast.NotEq]


# ==========================================================================================================
# F. AGGREGATE REVALIDATION (T41-T46)
# ==========================================================================================================
def test_t41_a_hollow_aggregate_is_rejected() -> None:
    day = _day()
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(
            day, object.__new__(RoughtimeV19RequestInSignedResponse)
        )
    assert excinfo.value.reason is R.REQUEST_IN_SIGNED_RESPONSE_INCONSISTENT


def test_t42_an_aggregate_with_unprovable_planted_state_is_rejected() -> None:
    day = _day()
    genuine = _aggregate_for(day)
    hollow = object.__new__(RoughtimeV19RequestInSignedResponse)
    aggregate_registry = None
    for cell in RoughtimeV19RequestInSignedResponse.__hash__.__closure__ or ():
        content = cell.cell_contents
        if callable(content):
            for inner in getattr(content, "__closure__", None) or ():
                nested = inner.cell_contents
                if type(nested) is dict:
                    aggregate_registry = nested
        if type(content) is dict:
            aggregate_registry = content
    assert aggregate_registry is not None
    aggregate_registry[id(hollow)] = (weakref.ref(hollow), (b"bad", b"bad", b"bad"))
    try:
        with pytest.raises(_ERROR) as excinfo:
            verify_roughtime_v19_attested_operational_day_digest_binding(day, hollow)
        assert excinfo.value.reason is R.REQUEST_IN_SIGNED_RESPONSE_INCONSISTENT
    finally:
        aggregate_registry.pop(id(hollow), None)
    assert genuine is not None


def test_t43_an_aggregate_with_a_mismatched_owner_entry_is_rejected() -> None:
    day = _day()
    genuine = _aggregate_for(day)
    impostor = object.__new__(RoughtimeV19RequestInSignedResponse)
    aggregate_registry = None
    for cell in RoughtimeV19RequestInSignedResponse.__hash__.__closure__ or ():
        content = cell.cell_contents
        if callable(content):
            for inner in getattr(content, "__closure__", None) or ():
                nested = inner.cell_contents
                if type(nested) is dict:
                    aggregate_registry = nested
        if type(content) is dict:
            aggregate_registry = content
    assert aggregate_registry is not None
    aggregate_registry[id(impostor)] = (weakref.ref(genuine), (b"a", b"b", b"c"))
    try:
        with pytest.raises(_ERROR) as excinfo:
            verify_roughtime_v19_attested_operational_day_digest_binding(day, impostor)
        assert excinfo.value.reason is R.REQUEST_IN_SIGNED_RESPONSE_INCONSISTENT
    finally:
        aggregate_registry.pop(id(impostor), None)


def test_t44_exact_caller_snapshot_and_fresh_signed_root_dataflow() -> None:
    """Bounded instrumentation at the NEW MODULE boundary only; no prerequisite internals are counted."""
    day = _day()
    request, response = _packets(nonce=bytes.fromhex(day.attested_operational_day_evidence_digest))
    caller = _aggregate(request, response)
    caller_reads: list[str] = []
    fresh_reads: list[str] = []
    constructions: list[dict] = []
    real_class = binding_module.RoughtimeV19RequestInSignedResponse

    class _Recorder:
        """Wraps the caller aggregate and records every validating public property read."""

        def __init__(self, inner):
            object.__setattr__(self, "_inner", inner)

        def __getattr__(self, name):
            caller_reads.append(name)
            return getattr(object.__getattribute__(self, "_inner"), name)

    recorder = _Recorder(caller)
    # The exact-type gate must still see the real type, so the recorder is only used to count reads through a
    # patched module-level name resolution rather than by passing a foreign object to the verifier.
    original_getattr = type(caller).request_raw.fget
    seen: list[str] = []

    def _patched(prop_name):
        original = getattr(real_class, prop_name).fget

        def _wrapper(self):
            if self is caller:
                caller_reads.append(prop_name)
            else:
                fresh_reads.append(prop_name)
            return original(self)

        return _wrapper

    monkey = pytest.MonkeyPatch()
    try:
        for prop_name in ("request_raw", "response_raw", "long_term_public_key", "signed_root"):
            monkey.setattr(real_class, prop_name, property(_patched(prop_name)), raising=True)

        original_new = real_class.__new__

        def _counting_new(cls, **kwargs):
            constructions.append(dict(kwargs))
            return original_new(cls, **kwargs)

        monkey.setattr(real_class, "__new__", _counting_new, raising=True)
        binding = verify_roughtime_v19_attested_operational_day_digest_binding(day, caller)
    finally:
        monkey.undo()
    assert caller_reads == ["request_raw", "response_raw", "long_term_public_key"]
    assert "signed_root" not in caller_reads
    assert fresh_reads.count("signed_root") >= 1
    assert len(constructions) >= 1
    first = constructions[0]
    assert first["request_raw"] == request
    assert first["response_raw"] == response
    assert first["long_term_public_key"] == _LONG_TERM_PUBLIC_KEY
    assert binding.request_raw == request
    assert binding.response_raw == response
    assert binding.long_term_public_key == _LONG_TERM_PUBLIC_KEY
    assert binding.signed_root == _oracle_root(_oracle_leaf(request), ((LEFT, _SIBLING_A),))
    assert seen == [] and original_getattr is not None and recorder is not None


def test_t45_the_nonce_is_located_by_the_k3_parser_and_never_by_a_fixed_offset() -> None:
    day = _day()
    binding = _bound(day, srv=b"\x11" * 32, request_padding=b"\x00" * 16)
    assert binding.operational_day is day
    assert len(binding.request_raw) > 76


def test_t46_no_raw_prerequisite_exception_leaks_from_a_public_surface() -> None:
    hollow = object.__new__(_BINDING)
    for consume in (repr, str, bool, lambda b: b.operational_day, lambda b: b.signed_root, copy.copy):
        with pytest.raises(_ERROR) as excinfo:
            consume(hollow)
        assert type(excinfo.value) is _ERROR


# ==========================================================================================================
# G. WRONG-CANDIDATE COMPARISONS (T47-T51)
# ==========================================================================================================
def _expect_nonce_mismatch(day: PaperAttestedOperationalDayEvidence, candidate: bytes) -> None:
    request, response = _packets(nonce=candidate)
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response))
    assert excinfo.value.reason is R.DAY_DIGEST_REQUEST_NONCE_MISMATCH


def test_t47_the_response_outer_nonce_is_never_accepted() -> None:
    day = _day()
    request, response = _packets(
        nonce=bytes.fromhex(day.attested_operational_day_evidence_digest), response_nonce=_OTHER_RESPONSE_NONCE
    )
    binding = verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response))
    assert binding.operational_day is day
    _expect_nonce_mismatch(day, _OTHER_RESPONSE_NONCE)


def test_t48_the_request_leaf_is_never_accepted() -> None:
    day = _day()
    request, response = _packets(nonce=bytes.fromhex(day.attested_operational_day_evidence_digest))
    leaf = _oracle_leaf(request)
    # Positive control: the genuine binding holds even though the digest is NOT the leaf, so any comparison
    # rewired to the leaf breaks here.
    assert leaf != bytes.fromhex(day.attested_operational_day_evidence_digest)
    assert (
        verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response)).operational_day
        is day
    )
    _expect_nonce_mismatch(day, leaf)


def test_t49_the_signed_root_is_never_accepted() -> None:
    day = _day()
    request, response = _packets(nonce=bytes.fromhex(day.attested_operational_day_evidence_digest))
    root = _oracle_root(_oracle_leaf(request), ((LEFT, _SIBLING_A),))
    # Positive control: the genuine binding holds even though the digest is NOT the signed root.
    assert root != bytes.fromhex(day.attested_operational_day_evidence_digest)
    assert (
        verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response)).operational_day
        is day
    )
    _expect_nonce_mismatch(day, root)


@pytest.mark.parametrize("key", [_LONG_TERM_PUBLIC_KEY, _DELEGATED_PUBLIC_KEY])
def test_t50_neither_public_key_is_ever_accepted(key) -> None:
    _expect_nonce_mismatch(_day(), key)


@pytest.mark.parametrize("field_name", ["attestation_id", "operational_day_evidence_id", "correlation_id"])
def test_t51_no_day_identifier_is_ever_accepted(field_name) -> None:
    day = _day()
    text = getattr(day, field_name)
    _expect_nonce_mismatch(day, hashlib.sha256(text.encode()).digest())


# ==========================================================================================================
# H. STATE MINIMALITY (T52-T57)
# ==========================================================================================================
def test_t52_registered_state_is_exactly_the_four_values() -> None:
    assert binding_module._ANCHOR_FIELD_NAMES == _EXPECTED_ANCHOR_FIELDS
    day = _day()
    binding = _bound(day)
    registry = _closure_registry()
    _, state = registry[id(binding)]
    assert type(state) is tuple
    assert len(state) == 4
    assert state[0] is day
    assert tuple(type(value) for value in state[1:]) == (bytes, bytes, bytes)


def test_t53_the_reduce_state_is_exactly_those_four_values() -> None:
    day = _day()
    binding = _bound(day)
    state = _registered_state(binding)
    assert len(state) == 4
    assert state[0] is day
    assert state[1] == binding.request_raw
    assert state[2] == binding.response_raw
    assert state[3] == binding.long_term_public_key


def test_t54_the_constructor_accepts_exactly_four_keywords() -> None:
    day = _day()
    binding = _bound(day)
    state = _registered_state(binding)
    with pytest.raises(TypeError):
        _BINDING(day, state[1], state[2], state[3])  # type: ignore[misc]
    with pytest.raises(TypeError):
        _BINDING(
            operational_day=day,
            request_raw=state[1],
            response_raw=state[2],
            long_term_public_key=state[3],
            extra=1,  # type: ignore[call-arg]
        )
    with pytest.raises(TypeError):
        _BINDING(operational_day=day, request_raw=state[1], response_raw=state[2])  # type: ignore[call-arg]


def test_t55_exactly_six_read_only_public_properties_in_declared_order() -> None:
    declared = [name for name, value in vars(_BINDING).items() if isinstance(value, property)]
    assert tuple(declared) == _EXPECTED_PUBLIC_FIELDS
    binding = _bound()
    for name in _EXPECTED_PUBLIC_FIELDS:
        assert getattr(_BINDING, name).fset is None
        assert getattr(_BINDING, name).fdel is None
        with pytest.raises(AttributeError):
            setattr(binding, name, "x")


def test_t56_derived_values_are_absent_from_state_and_re_derived_on_every_read() -> None:
    day = _day()
    binding = _bound(day)
    state = _registered_state(binding)
    assert binding.attested_operational_day_evidence_digest not in {value for value in state if type(value) is str}
    assert binding.signed_root not in set(state[1:])
    first = binding.attested_operational_day_evidence_digest
    second = binding.attested_operational_day_evidence_digest
    assert first == second


def test_t57_no_derivative_only_state_is_stored() -> None:
    day = _day()
    binding = _bound(day)
    registry = _closure_registry()
    _, state = registry[id(binding)]
    nonce = parse_roughtime_v19_request(binding.request_raw).nonce
    assert nonce not in state
    assert binding.signed_root not in state
    assert binding.attested_operational_day_evidence_digest not in state
    assert True not in state and False not in state
    assert _registered_state(binding) == state


# ==========================================================================================================
# I. EXACT STATE TYPE GATES (T58-T60)
# ==========================================================================================================
@pytest.mark.parametrize("position", [1, 2, 3])
@pytest.mark.parametrize("wrapper", [_LiarBytes, bytearray, memoryview])
def test_t58_non_exact_bytes_anchors_are_rejected(position, wrapper) -> None:
    day = _day()
    binding = _bound(day)
    state = list(_registered_state(binding))
    state[position] = wrapper(state[position])
    with pytest.raises(_ERROR) as excinfo:
        binding_module._rebuild_attested_operational_day_digest_binding(tuple(state))
    assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT


def test_t59_the_exact_bytes_gate_fires_before_the_parser_is_reached(monkeypatch) -> None:
    parsed: list[str] = []
    original = binding_module.parse_roughtime_v19_request

    def _tripwire(raw):
        parsed.append("parse")
        return original(raw)

    monkeypatch.setattr(binding_module, "parse_roughtime_v19_request", _tripwire)
    day = _day()
    binding = _bound(day)
    state = list(_registered_state(binding))
    state[1] = bytearray(state[1])
    parsed.clear()
    with pytest.raises(_ERROR):
        binding_module._rebuild_attested_operational_day_digest_binding(tuple(state))
    assert parsed == []


def test_t60_a_non_exact_type_day_in_stored_state_is_rejected() -> None:
    day = _day()
    binding = _bound(day)
    state = list(_registered_state(binding))
    state[0] = _subclass_day()
    with pytest.raises(_ERROR) as excinfo:
        binding_module._rebuild_attested_operational_day_digest_binding(tuple(state))
    assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT


# ==========================================================================================================
# J. CONSUMPTION-SURFACE MATRIX (T61-T65)
# ==========================================================================================================
def _consume_eq(binding):
    return operator.eq(binding, binding)


def _consume_ne(binding):
    return operator.ne(binding, binding)


def _consume_reduce(binding):
    return binding.__reduce__()


def _consume_reduce_ex(binding):
    return binding.__reduce_ex__(2)


def _consume_pickle_roundtrip(binding):
    return pickle.loads(pickle.dumps(binding))  # noqa: S301 - round-trips this module's own artifact only


_CONSUMPTION_SURFACES = (
    *((name, operator.attrgetter(name)) for name in _EXPECTED_PUBLIC_FIELDS),
    ("repr", repr),
    ("str", str),
    ("bool_dunder", _BINDING.__bool__),
    ("bool", bool),
    ("truth", operator.truth),
    ("eq", _consume_eq),
    ("ne", _consume_ne),
    ("reduce", _consume_reduce),
    ("reduce_ex", _consume_reduce_ex),
    ("copy", copy.copy),
    ("deepcopy", copy.deepcopy),
    ("pickle_dumps", pickle.dumps),
    ("pickle_roundtrip", _consume_pickle_roundtrip),
)
_CONSUMPTION_SURFACE_IDS = tuple(name for name, _ in _CONSUMPTION_SURFACES)
_REQUIRED_CONSUMPTION_SURFACES = (
    "operational_day",
    "attested_operational_day_evidence_digest",
    "request_raw",
    "response_raw",
    "long_term_public_key",
    "signed_root",
    "repr",
    "str",
    "bool_dunder",
    "bool",
    "truth",
    "eq",
    "ne",
    "reduce",
    "reduce_ex",
    "copy",
    "deepcopy",
    "pickle_dumps",
    "pickle_roundtrip",
)


@contextlib.contextmanager
def _hollow_state():
    """A fabricated exact-type instance with no registry entry at all."""
    yield object.__new__(_BINDING)


@contextlib.contextmanager
def _dead_owner_state():
    """A registry entry whose owning weak reference is already dead."""
    registry = _closure_registry()
    victim = _bound()
    key = id(victim)
    reference, state = registry[key]
    impostor = object.__new__(_BINDING)
    dead = weakref.ref(object.__new__(_BINDING))
    registry[id(impostor)] = (dead, state)
    try:
        yield impostor
    finally:
        registry.pop(id(impostor), None)
        assert reference is not None


@contextlib.contextmanager
def _mismatched_owner_state():
    """A registry entry whose live weak reference points at a DIFFERENT object."""
    registry = _closure_registry()
    owner = _bound()
    impostor = object.__new__(_BINDING)
    _, state = registry[id(owner)]
    registry[id(impostor)] = (weakref.ref(owner), state)
    try:
        yield impostor
    finally:
        registry.pop(id(impostor), None)


@contextlib.contextmanager
def _inconsistent_registered_state():
    """A live, correctly owned entry whose stored state can no longer be re-proven."""
    registry = _closure_registry()
    binding = _bound()
    key = id(binding)
    reference, state = registry[key]
    registry[key] = (reference, (state[0], b"broken", state[2], state[3]))
    try:
        yield binding
    finally:
        registry[key] = (reference, state)


_INVALID_ARTIFACT_STATES = (
    ("hollow", _hollow_state),
    ("dead_owner", _dead_owner_state),
    ("mismatched_owner", _mismatched_owner_state),
    ("inconsistent_registered_state", _inconsistent_registered_state),
)
_INVALID_ARTIFACT_STATE_IDS = tuple(name for name, _ in _INVALID_ARTIFACT_STATES)
_REQUIRED_INVALID_ARTIFACT_STATES = (
    "hollow",
    "dead_owner",
    "mismatched_owner",
    "inconsistent_registered_state",
)


def test_t61_the_validating_consumption_inventory_is_exact_and_complete() -> None:
    """19 validating surfaces. hash is DELIBERATELY excluded: it is unsupported and owned by T69."""
    assert _CONSUMPTION_SURFACE_IDS == _REQUIRED_CONSUMPTION_SURFACES
    assert len(_CONSUMPTION_SURFACES) == 19
    assert "hash" not in _CONSUMPTION_SURFACE_IDS


def test_t62_the_invalid_artifact_state_inventory_is_exact_and_complete() -> None:
    assert _INVALID_ARTIFACT_STATE_IDS == _REQUIRED_INVALID_ARTIFACT_STATES
    assert len(_INVALID_ARTIFACT_STATES) == 4


@pytest.mark.parametrize(("surface", "consume"), _CONSUMPTION_SURFACES, ids=_CONSUMPTION_SURFACE_IDS)
def test_t63_a_hollow_instance_fails_closed_on_every_validating_surface(surface, consume) -> None:
    hollow = object.__new__(_BINDING)
    with pytest.raises(_ERROR) as excinfo:
        consume(hollow)
    assert type(excinfo.value) is _ERROR, surface
    assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT, surface


@pytest.mark.parametrize(("surface", "consume"), _CONSUMPTION_SURFACES, ids=_CONSUMPTION_SURFACE_IDS)
def test_t64_every_validating_surface_succeeds_for_a_genuine_artifact(surface, consume) -> None:
    binding = _bound()
    consume(binding)


@pytest.mark.parametrize(("state", "factory"), _INVALID_ARTIFACT_STATES, ids=_INVALID_ARTIFACT_STATE_IDS)
@pytest.mark.parametrize(("surface", "consume"), _CONSUMPTION_SURFACES, ids=_CONSUMPTION_SURFACE_IDS)
def test_t65_every_invalid_state_fails_closed_on_every_validating_surface(surface, consume, state, factory) -> None:
    with factory() as invalid, pytest.raises(_ERROR) as excinfo:
        consume(invalid)
    assert type(excinfo.value) is _ERROR, (state, surface)
    assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT, (state, surface)


# ==========================================================================================================
# K. TRUTHINESS / UNHASHABILITY / EQUALITY / SERIALIZATION (T66-T71)
# ==========================================================================================================
def test_t66_truthiness_returns_exactly_true_without_a_length_protocol() -> None:
    binding = _bound()
    assert binding.__bool__() is True
    assert bool(binding) is True
    assert "__len__" not in vars(_BINDING)
    with pytest.raises(TypeError):
        len(binding)  # type: ignore[arg-type]


def test_t67_hollow_truthiness_fails_closed_rather_than_returning_false() -> None:
    hollow = object.__new__(_BINDING)
    with pytest.raises(_ERROR) as excinfo:
        bool(hollow)
    assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT


def test_t68_repr_and_str_are_bounded_redacted_and_exactly_templated() -> None:
    """Independent exact-template equality is the primary oracle; the max-boundary case renders exactly 455."""
    day = _day()
    request, response = _packets(nonce=bytes.fromhex(day.attested_operational_day_evidence_digest))
    binding = verify_roughtime_v19_attested_operational_day_digest_binding(day, _aggregate(request, response))
    expected_digest = _independent_day_digest(day)
    expected_root = _oracle_root(_oracle_leaf(request), ((LEFT, _SIBLING_A),))
    expected = _expected_repr(expected_digest, request, response, _LONG_TERM_PUBLIC_KEY, expected_root)

    derivations: list[str] = []
    original = binding_module.paper_attested_operational_day_evidence_digest
    monkey = pytest.MonkeyPatch()

    def _counting(value):
        derivations.append("derive")
        return original(value)

    monkey.setattr(binding_module, "paper_attested_operational_day_evidence_digest", _counting)
    try:
        derivations.clear()
        repr_result = repr(binding)
        assert len(derivations) == 1  # (1) exactly one reproof per repr call, never six
        derivations.clear()
        str_result = str(binding)
        assert len(derivations) == 1  # (2) exactly one reproof per str call
    finally:
        monkey.undo()

    assert type(repr_result) is str  # (4)
    assert type(str_result) is str  # (5)
    assert repr_result == expected  # (6)
    assert str_result == expected  # (7)
    assert str_result == repr_result  # (8)
    match = _REPR_PATTERN.fullmatch(repr_result)  # (9) anchored, escaped, exact named groups, no wildcard
    assert match is not None
    assert match.group("digest") == expected_digest
    assert match.group("request_len") == str(len(request))
    assert match.group("response_len") == str(len(response))
    assert match.group("key_len") == "32"
    assert match.group("root_hex") == expected_root.hex()
    assert repr_result.isascii() is True  # (10)
    assert "\n" not in repr_result  # (11)
    assert "\r" not in repr_result  # (12)
    assert len(repr_result) <= _HARD_REPR_CAP  # (13)
    assert len(repr_result) == _FIXED_TEMPLATE_LENGTH + len(str(len(request))) + len(str(len(response))) + len(
        "32"
    )  # (14)

    # (15) GENUINE maximum-boundary case: 4096 / 4096 / 32 renders exactly 455 characters.
    max_binding, max_day, max_request, max_response = _max_boundary_binding()
    assert len(max_request) == _MAX_PACKET_BYTES
    assert len(max_response) == _MAX_PACKET_BYTES
    assert len(max_binding.request_raw) == _MAX_PACKET_BYTES
    assert len(max_binding.response_raw) == _MAX_PACKET_BYTES
    assert len(max_binding.long_term_public_key) == 32
    max_expected = _expected_repr(
        _independent_day_digest(max_day),
        max_request,
        max_response,
        _LONG_TERM_PUBLIC_KEY,
        max_binding.signed_root,
    )
    max_result = repr(max_binding)
    assert max_result == max_expected
    assert str(max_binding) == max_result
    assert len(max_result) == _PROVEN_MAXIMUM_RENDERED_LENGTH
    assert len(max_result) <= _HARD_REPR_CAP
    assert max_result.isascii() is True
    assert "\n" not in max_result and "\r" not in max_result
    assert _REPR_PATTERN.fullmatch(max_result) is not None

    # (16) every invalid state raises from BOTH repr and str, with no partial output.
    for _, factory in _INVALID_ARTIFACT_STATES:
        with factory() as invalid:
            for consume in (repr, str):
                with pytest.raises(_ERROR) as excinfo:
                    consume(invalid)
                assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT
    # (17) a day mutation also fails closed rather than rendering a degraded string.
    original_id = max_day.attestor_id
    object.__setattr__(max_day, "attestor_id", "operator-x")
    try:
        for consume in (repr, str):
            with pytest.raises(_ERROR):
                consume(max_binding)
    finally:
        object.__setattr__(max_day, "attestor_id", original_id)


def test_t69_the_binding_is_explicitly_unhashable_before_during_and_after_mutation() -> None:
    day = _day()
    binding = _bound(day)
    assert _BINDING.__hash__ is None

    def _assert_unhashable():
        with pytest.raises(TypeError) as excinfo:
            hash(binding)
        assert type(excinfo.value) is TypeError
        with pytest.raises(TypeError):
            _members = {binding}
        with pytest.raises(TypeError):
            _mapping = {binding: 1}

    _assert_unhashable()
    original = day.attestor_id
    object.__setattr__(day, "attestor_id", "operator-z")
    try:
        _assert_unhashable()
    finally:
        object.__setattr__(day, "attestor_id", original)
    _assert_unhashable()
    # Mutation-after-first-successful-hash and mutation-after-container-insertion are UNREACHABLE because a
    # successful hash can never occur.


def test_t70_equality_is_validating_and_identity_only() -> None:
    day = _day()
    binding = _bound(day)

    touched: list[str] = []

    class _Hostile:
        def __getattribute__(self, name):  # pragma: no cover - must never run
            touched.append(name)
            raise AttributeError(name)

        def __eq__(self, other):  # pragma: no cover - must never run
            touched.append("__eq__")
            raise AttributeError("__eq__")

        __hash__ = None

    assert (binding == _Hostile()) is False
    assert (binding != _Hostile()) is True
    assert touched == []
    same = binding
    assert (binding == same) is True
    assert (binding != same) is False
    same_content = _bound(day)
    assert (binding == same_content) is False
    assert (binding != same_content) is True
    original = day.attestor_id
    object.__setattr__(day, "attestor_id", "operator-q")
    try:
        with pytest.raises(_ERROR):
            binding.__eq__(binding)
    finally:
        object.__setattr__(day, "attestor_id", original)
    assert (binding == same) is True


def test_t71_copy_deepcopy_and_pickle_rebuild_from_exactly_the_four_values() -> None:
    day = _day()
    binding = _bound(day)
    shallow = copy.copy(binding)
    assert shallow is not binding
    assert shallow.operational_day is day
    assert (shallow == binding) is False
    with pytest.raises(TypeError):
        hash(shallow)
    deep = copy.deepcopy(binding)
    assert deep.operational_day is not day
    assert type(deep.operational_day) is PaperAttestedOperationalDayEvidence
    assert deep.operational_day == day
    assert (deep == binding) is False
    roundtrip = pickle.loads(pickle.dumps(binding))  # noqa: S301 - round-trips this module's own artifact only
    assert type(roundtrip) is _BINDING
    assert roundtrip.operational_day is not day
    assert roundtrip.operational_day == day
    assert (roundtrip == binding) is False
    with pytest.raises(TypeError):
        hash(roundtrip)
    registry = _closure_registry()
    for rebuilt in (shallow, deep, roundtrip):
        _, state = registry[id(rebuilt)]
        assert len(state) == 4


# ==========================================================================================================
# L. REGISTRY LIFECYCLE (T72-T77)
# ==========================================================================================================
def test_t72_the_registry_is_not_reachable_through_the_module_namespace() -> None:
    for name in dir(binding_module):
        value = getattr(binding_module, name)
        assert not (type(value) is dict and value and all(type(key) is int for key in value)), name


def test_t73_one_id_keyed_entry_per_artifact_and_lookup_never_uses_hash_or_equality() -> None:
    binding = _bound()
    registry = _closure_registry()
    assert id(binding) in registry
    assert sum(1 for key in registry if key == id(binding)) == 1
    reference, _ = registry[id(binding)]
    assert reference() is binding
    assert _BINDING.__hash__ is None
    source = _production_function_source("_build_attested_operational_day_digest_binding_class")
    assert "registry.get(id(artifact))" in source
    assert "registry[key] = " in source


def test_t74_the_entry_is_removed_when_the_artifact_dies() -> None:
    registry = _closure_registry()
    binding = _bound()
    key = id(binding)
    assert key in registry
    del binding
    assert key not in registry


def test_t75_a_failed_construction_leaves_no_entry() -> None:
    registry = _closure_registry()
    before = dict(registry)
    with pytest.raises(_ERROR):
        _BINDING(
            operational_day=_day(),
            request_raw=b"bad",
            response_raw=b"bad",
            long_term_public_key=b"bad",
        )
    assert set(registry) == set(before)
    hollow = object.__new__(_BINDING)
    assert id(hollow) not in registry


def test_t76_a_stale_or_mismatched_reference_never_authenticates_another_object() -> None:
    registry = _closure_registry()
    owner = _bound()
    impostor = object.__new__(_BINDING)
    _, state = registry[id(owner)]
    registry[id(impostor)] = (weakref.ref(owner), state)
    try:
        with pytest.raises(_ERROR) as excinfo:
            impostor.signed_root
        assert excinfo.value.reason is R.BINDING_ARTIFACT_INCONSISTENT
    finally:
        registry.pop(id(impostor), None)


def test_t77_a_stale_weakref_callback_deletes_only_its_own_entry() -> None:
    """The death callback must delete ONLY the entry its own exact reference still owns."""
    registry = _closure_registry()
    binding = _bound()
    key = id(binding)
    original_reference, state = registry[key]
    # Re-bind the slot to a DIFFERENT reference. When the artifact dies, the original owner's callback fires,
    # finds it no longer owns this slot, and must leave the newer entry untouched.
    replacement = (weakref.ref(binding), state)
    registry[key] = replacement
    try:
        del binding
        assert registry.get(key) is replacement
        assert original_reference() is None
    finally:
        registry.pop(key, None)


# ==========================================================================================================
# M. IMMUTABILITY / ABSENT CONTAINER PROTOCOL (T78-T82)
# ==========================================================================================================
def test_t78_the_instance_has_no_dict_and_only_a_weakref_slot() -> None:
    binding = _bound()
    assert _BINDING.__slots__ == ("__weakref__",)
    assert not hasattr(binding, "__dict__")
    with pytest.raises(TypeError):
        vars(binding)


@pytest.mark.parametrize("name", list(_EXPECTED_PUBLIC_FIELDS) + ["anything"])
def test_t79_setattr_and_delattr_are_rejected_for_every_field(name) -> None:
    binding = _bound()
    with pytest.raises(AttributeError):
        setattr(binding, name, 1)
    with pytest.raises(AttributeError):
        delattr(binding, name)
    with pytest.raises(AttributeError):
        object.__setattr__(binding, name, 1)
    with pytest.raises(AttributeError):
        object.__delattr__(binding, name)


def test_t80_no_public_property_is_a_writable_descriptor() -> None:
    for name in _EXPECTED_PUBLIC_FIELDS:
        descriptor = getattr(_BINDING, name)
        assert isinstance(descriptor, property)
        assert descriptor.fset is None and descriptor.fdel is None


@pytest.mark.parametrize(
    "action",
    [
        len,
        iter,
        reversed,
        lambda b: b[0],
        lambda b: 1 in b,
        lambda b: b + b,
        lambda b: b * 2,
        lambda b: operator.lt(b, b),
    ],
)
def test_t81_the_sequence_protocol_is_absent(action) -> None:
    binding = _bound()
    with pytest.raises(TypeError):
        action(binding)


def test_t82_every_subclass_form_is_sealed() -> None:
    with pytest.raises(TypeError) as excinfo:

        class _Derived(_BINDING):  # type: ignore[misc]
            pass

    assert "sealed artifact type" in str(excinfo.value)
    with pytest.raises(TypeError):
        type("Dynamic", (_BINDING,), {})


# ==========================================================================================================
# N. EXCEPTION NARROWNESS (T83-T87)
# ==========================================================================================================
def test_t83_production_catches_exactly_the_two_prerequisite_domain_errors() -> None:
    handlers = [node for node in ast.walk(_PRODUCTION_TREE) if isinstance(node, ast.ExceptHandler)]
    assert handlers
    caught = set()
    for handler in handlers:
        assert handler.type is not None, "bare except is forbidden"
        caught.add(ast.unparse(handler.type))
    assert caught == {"RoughtimeV19RequestSemanticError", "RoughtimeV19RequestInSignedResponseError"}
    # NO catch surrounds the public day-digest call: the governed-day stage contains no try/except at all.
    digest_stage = _production_function("_validated_day_digest")
    assert not [node for node in ast.walk(digest_stage) if isinstance(node, (ast.Try, ast.ExceptHandler))]
    # Catch reachability: the standalone K3 parse must precede the aggregate rebuild in the derivation, so the
    # request-semantic catch stays behaviourally reachable on the reconstruction path.
    derived = _production_function_source("_derived_state")
    assert derived.index("parse_roughtime_v19_request(") < derived.index("RoughtimeV19RequestInSignedResponse(")


def test_t84_the_source_contains_no_broad_except_and_no_ble001_suppression() -> None:
    for forbidden in (
        "except Exception",
        "except BaseException",
        "except:",
        "except RuntimeError",
        "except AssertionError",
        "except AttributeError",
        "except TypeError",
        "except ValueError",
        "except LookupError",
        "except KeyError",
        "except IndexError",
        "except ArithmeticError",
        "except OSError",
        "except GeneratorExit",
        "BLE001",
        "noqa",
    ):
        assert forbidden not in _PRODUCTION_SOURCE, forbidden


def test_t85_an_assertion_error_from_a_prerequisite_propagates_unchanged(monkeypatch) -> None:
    day = _day()
    aggregate = _aggregate_for(day)

    def _boom(_value):
        raise AssertionError("prerequisite defect")

    monkeypatch.setattr(binding_module, "paper_attested_operational_day_evidence_digest", _boom)
    with pytest.raises(AssertionError):
        verify_roughtime_v19_attested_operational_day_digest_binding(day, aggregate)


@pytest.mark.parametrize("target", ["paper_attested_operational_day_evidence_digest", "parse_roughtime_v19_request"])
def test_t86_an_unrelated_programmer_exception_propagates_unchanged(monkeypatch, target) -> None:
    day = _day()
    aggregate = _aggregate_for(day)

    def _boom(*_args, **_kwargs):
        raise _ProbeError("unrelated")

    monkeypatch.setattr(binding_module, target, _boom)
    with pytest.raises(_ProbeError):
        verify_roughtime_v19_attested_operational_day_digest_binding(day, aggregate)


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_t87_keyboard_interrupt_and_system_exit_propagate_unchanged(monkeypatch, exception) -> None:
    day = _day()
    aggregate = _aggregate_for(day)

    def _boom(*_args, **_kwargs):
        raise exception()

    monkeypatch.setattr(binding_module, "parse_roughtime_v19_request", _boom)
    with pytest.raises(exception):
        verify_roughtime_v19_attested_operational_day_digest_binding(day, aggregate)


# ==========================================================================================================
# O. CRYPTO / IO / BOUNDARY (T88-T95)
# ==========================================================================================================
def test_t88_production_imports_only_public_prerequisite_symbols() -> None:
    imported: list[str] = []
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.append(alias.name)
                assert not alias.name.startswith("_"), alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
    assert set(imported) >= {
        "PaperAttestedOperationalDayEvidence",
        "PaperAttestedOperationalDayEvidenceStatus",
        "paper_attested_operational_day_evidence_digest",
        "RoughtimeV19RequestInSignedResponse",
        "RoughtimeV19RequestInSignedResponseError",
        "RoughtimeV19RequestSemanticError",
        "parse_roughtime_v19_request",
    }


def test_t89_no_new_cryptographic_operation_and_no_encoding_shortcut() -> None:
    modules: list[str] = []
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Import):
            modules.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module.split(".")[0])
    for forbidden in ("hashlib", "hmac", "base64", "nacl", "cryptography", "ssl", "binascii"):
        assert forbidden not in modules, forbidden
    for token in (
        "sha256(",
        "sha512(",
        "SigningKey",
        "VerifyKey",
        "RawEncoder",
        "b64encode",
        "b64decode",
        "crypto_sign",
        ".digest()",
        "hexdigest(",
    ):
        assert token not in _PRODUCTION_SOURCE, token
    assert _PRODUCTION_SOURCE.count("paper_attested_operational_day_evidence_digest(") == 1


def test_t90_production_reads_no_clock_randomness_filesystem_or_subprocess() -> None:
    modules: list[str] = []
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Import):
            modules.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module.split(".")[0])
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
        "urllib",
        "io",
    ):
        assert forbidden not in modules, forbidden


def test_t91_production_uses_no_isinstance() -> None:
    assert "isinstance(" not in _PRODUCTION_SOURCE
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "isinstance"


def test_t92_production_names_no_mt2_or_mt3_symbol() -> None:
    for forbidden in (
        "machine_time_policy",
        "machine_time_source_registry",
        "MachineTimePolicy",
        "MachineTimeSourceRegistry",
        "source_id",
        "source_class",
        "recommended_role",
        "verification_profile_id",
        "registry_digest",
        "policy_digest",
    ):
        assert forbidden not in _PRODUCTION_SOURCE, forbidden


@pytest.mark.parametrize(
    "attribute",
    [
        "machine_time_origin_proven",
        "timestamp_origin_proven",
        "operational_day_machine_proven",
        "real_wall_clock_used",
        "real_time_paper_operation_proven",
        "not_before",
        "not_after",
        "not_before_proven",
        "not_after_proven",
        "truthful_time",
        "authenticated_time",
        "real_day",
        "calendar_day",
        "proof_verified",
        "operational_use_approved",
        "quorum",
        "quorum_countable",
        "source_admitted",
        "verification_profile_id",
        "provider",
        "provider_id",
        "provider_verified",
        "key_admitted",
        "ready",
        "readiness_promoted",
        "operational_readiness",
        "verified",
        "authentic",
        "deployed_version",
    ],
)
def test_t93_the_artifact_exposes_no_overclaiming_attribute(attribute) -> None:
    binding = _bound()
    assert not hasattr(binding, attribute), attribute


def test_t94_the_public_attribute_surface_is_exactly_the_six_declared_fields() -> None:
    public = tuple(name for name in dir(_BINDING) if not name.startswith("_"))
    assert public == tuple(sorted(_EXPECTED_PUBLIC_FIELDS))


def test_t95_property_names_carry_no_temporal_or_provider_vocabulary() -> None:
    for name in _EXPECTED_PUBLIC_FIELDS:
        lowered = name.lower()
        for forbidden in ("time", "clock", "midpoint", "radius", "provider", "quorum", "ready", "proven"):
            assert forbidden not in lowered, (name, forbidden)


# ==========================================================================================================
# P. PROTECTED INVARIANTS AND NON-TRANSITION (T96-T99)
# ==========================================================================================================
_PROTECTED_DIGESTS = {
    "roughtime_v19_kernel.py": "3ef6d6ec400bc395580606980c4ee0afecec2fa7488070718e4e87ab9706da11",
    "roughtime_v19_response_semantics.py": "1cd222147413ddd25c3249c93900a3fa9da90090e789a0b0dfe3488c671eded1",
    "roughtime_v19_request_semantics.py": "7fe884baab27728746c91cc796ec91b70cf1db62b7e0eec7317241a3e9cfea8b",
    "roughtime_v19_request_inclusion.py": "451d16de6dc565071858ae1c7506b19144b6f9db75139de328fc9f5c9e7a0d53",
    "roughtime_v19_certificate_verification.py": "19f365695a3d8e70063dcdac685c7047ea5e1e4120373a35fc64d67a073578cf",
    "roughtime_v19_signed_response_verification.py": "64b3a4f56905685ca8daff8d67f3500b0bfd0712bb9c2980161b107827e016a5",
    "roughtime_v19_request_in_signed_response.py": "e716204c53d026b505c1e498fd763fe2b14b54f1e81644cc04a3863daa2ee105",
    "paper_attested_operational_day_evidence.py": "1550aa78636167e68ba75bce42edfae515c4f67e19d17ed36daccf74c161d5e2",
}


@pytest.mark.parametrize(("filename", "digest"), sorted(_PROTECTED_DIGESTS.items()))
def test_t96_protected_prerequisite_files_are_unchanged(filename, digest) -> None:
    path = _PRODUCTION_PATH.parent / filename
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, filename


def test_t97_building_a_binding_causes_no_readiness_or_connector_transition() -> None:
    from crypto_core.venue.public_feed_dialects import connector_ready_dialects

    before = tuple(spec.dialect_id for spec in connector_ready_dialects())
    binding = _bound()
    after = tuple(spec.dialect_id for spec in connector_ready_dialects())
    assert before == after == ("deribit:l2_orderbook:book_instrument_interval",)
    assert binding.operational_day.operational_readiness is False


def test_t98_production_declares_no_readiness_connector_or_profile_selection_symbol() -> None:
    for forbidden in (
        "readiness_promoted",
        "mt4_verifier_profile_selected",
        "connector_ready_dialects",
        "profile_selected",
        "promote",
    ):
        assert forbidden not in _PRODUCTION_SOURCE, forbidden
    # ``connector_invoked`` and ``operational_readiness`` appear ONLY as governed-day field/flag names the
    # module requires to be exactly False: once in the pinned 66-name inventory and once in the false-flag
    # inventory. They are never declared as a symbol of this module.
    assert _PRODUCTION_SOURCE.count('"connector_invoked"') == 2
    assert _PRODUCTION_SOURCE.count('"operational_readiness"') == 2
    declared: set[str] = set()
    for node in ast.walk(_PRODUCTION_TREE):
        if isinstance(node, ast.Assign):
            declared.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            declared.add(node.name)
    for name in declared:
        lowered = name.lower()
        for forbidden in ("readiness", "connector", "profile_selected", "quorum"):
            assert forbidden not in lowered, (name, forbidden)


def test_t99_production_contains_no_bist_reference() -> None:
    """Out-of-scope vocabulary may appear ONLY inside the re-pinned rejection pattern, nowhere else."""
    gate_lines = [line for line in _PRODUCTION_SOURCE.splitlines() if line.startswith("_SCOPE_EXCLUSION_PATTERN")]
    assert len(gate_lines) == 1
    remainder = _PRODUCTION_SOURCE.replace(gate_lines[0], "").lower()
    for forbidden in ("bist", "kap", "ideal", "matriks", "borsa"):
        assert forbidden not in remainder, forbidden


# ==========================================================================================================
# Q. DETERMINISM AND HONESTY (T100-T103)
# ==========================================================================================================
def test_t100_repeated_construction_yields_identical_values_but_distinct_unhashable_identities() -> None:
    day = _day()
    first = _bound(day)
    second = _bound(day)
    assert first is not second
    assert first.attested_operational_day_evidence_digest == second.attested_operational_day_evidence_digest
    assert first.signed_root == second.signed_root
    assert first.request_raw == second.request_raw
    assert (first == second) is False
    for artifact in (first, second):
        with pytest.raises(TypeError):
            hash(artifact)


@pytest.mark.parametrize("offset", [2, 3, 4, 5, 6])
def test_t101_one_signed_request_binds_exactly_one_day(offset) -> None:
    day = _day()
    aggregate = _aggregate_for(day)
    other = _day(_BASE_INDEX + offset)
    with pytest.raises(_ERROR) as excinfo:
        verify_roughtime_v19_attested_operational_day_digest_binding(other, aggregate)
    assert excinfo.value.reason is R.DAY_DIGEST_REQUEST_NONCE_MISMATCH


def test_t102_the_docstrings_carry_the_explicit_non_claim_inventory() -> None:
    """DOCUMENTARY public non-claim enforcement, not cryptographic proof."""
    module_doc = binding_module.__doc__ or ""
    class_doc = _BINDING.__doc__ or ""
    assert "OPERATOR-ATTESTED, NOT MACHINE-PROVEN" in module_doc
    assert "OPERATOR-ATTESTED, NOT MACHINE-PROVEN" in class_doc
    for phrase in ("not-before", "not-after", "quorum", "readiness", "provider identity"):
        assert phrase in module_doc, phrase
    assert "MUTABLE-REFERENCE POLICY" in class_doc
    assert "STRUCTURAL, never TEMPORAL" in module_doc


def test_t103_a_content_equivalent_day_is_accepted_without_a_historical_origin_claim() -> None:
    day = _day()
    values = {field.name: getattr(day, field.name) for field in fields(day)}
    rebuilt = PaperAttestedOperationalDayEvidence(**values)  # type: ignore[arg-type]
    assert rebuilt is not day
    assert rebuilt == day
    aggregate = _aggregate_for(day)
    first = verify_roughtime_v19_attested_operational_day_digest_binding(day, aggregate)
    second = verify_roughtime_v19_attested_operational_day_digest_binding(rebuilt, aggregate)
    assert second.operational_day is rebuilt
    assert (first == second) is False
    assert first.attested_operational_day_evidence_digest == second.attested_operational_day_evidence_digest
