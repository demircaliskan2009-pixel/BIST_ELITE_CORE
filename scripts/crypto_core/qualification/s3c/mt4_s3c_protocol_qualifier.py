"""MT4-S3C P0 protocol qualifier and deterministic case-plan builder.  Qualification only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 20, 21.
BUNDLE ENTRY 8 of the exact 16-entry qualification source bundle (V9 SECTION 8).

WHAT THIS MODULE OWNS.

  1. V5 TAXONOMY CONFORMANCE.  It proves the wire contract this slice implements is exactly the V5
     contract: the fixed 184-byte request layout, the fixed 8-byte response layout with a one-byte
     RESULT_CLASS at offset 5 and a one-byte RESULT_CODE at offset 6, the governed verifier status
     domain 0..11 in which EVERY member is a LEGAL WIRE STATUS, the request-protocol-error domain
     closed at six, the phase-scoped reserved exit codes, and the frozen field-validation ORDER.

  2. THE DETERMINISTIC CASE PLAN.  It converts the governed TEST-ONLY fixture (bundle entry 16) into
     the frozen binary plan the trusted observer drives.  The plan carries the fixture digest, and
     the observer records the plan digest into the raw observation record, so the plan is never a
     trust input: it is a derived artifact bound to a bundled source that the adjudicator and the
     trusted gate can both re-derive and compare.

WHY THE EXPECTED CODES ARE NOT GUESSED.  The exact status a pinned library returns for a given
malformed input is a property of THAT LIBRARY, not of this architecture.  The expected RESULT_CLASS
and RESULT_CODE for every case are frozen by the architecture (V9 21.4) and the fixture must carry
exactly those values; the OFFLINE one-time generator is what proves pinned blst agrees with them.
If pinned blst returns a different code for a frozen construction, the correct outcome is
UNRESOLVED_P2 returned to the controller -- never relabelling the case, never widening the expected
set, and never accepting "any non-zero code".

THE FIXTURE MATERIAL GATE IS FAIL-CLOSED AND HAS NO PERMISSIVE BRANCH.  The fixture carries an
explicit two-member state.  PENDING_OFFLINE_GENERATION is ALWAYS rejected before any case material
is read, so a fixture whose vectors have not yet been produced by the offline generator can never
yield a qualification result of any kind.  There is no mode in which a pending fixture is tolerated.

SELF-CONTAINED.  This module imports no repository module and contains no dynamic import machinery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

# =================================================================================================
# FROZEN IDENTITIES
# =================================================================================================

FIXTURE_SCHEMA = "mt4-s3c-test-only-vector.v1"
PROTOCOL_SCHEMA = "mt4-s3c-protocol-conformance.v1"
PROTOCOL_DIGEST_DOMAIN = b"mt4-s3c-protocol-conformance.v1\x00"
PLATFORM_ID = "LINUX_X86_64"

TEST_VECTOR_AUTHORITY = "PROJECT_GENERATED_DETERMINISTIC_TEST_VECTOR"
FIXTURE_STATE_GENERATED = "GENERATED_OFFLINE_ONE_TIME"
FIXTURE_STATE_PENDING = "PENDING_OFFLINE_GENERATION"
FIXTURE_STATES = (FIXTURE_STATE_GENERATED, FIXTURE_STATE_PENDING)

# =================================================================================================
# WIRE CONTRACT (V9 20.2, 20.3, 20.4, 20.5, 20.6)
# =================================================================================================

REQUEST_FRAME_BYTES = 184
RESPONSE_FRAME_BYTES = 8

REQUEST_MAGIC = b"MT4W"
RESPONSE_MAGIC = b"MT4R"
WIRE_VERSION = 0x01
OPCODE_VERIFY_QUICKNET_G1 = 0x01

REQUEST_LAYOUT = (
    ("magic", 0, 4),
    ("version", 4, 1),
    ("opcode", 5, 1),
    ("reserved", 6, 2),
    ("public_key", 8, 96),
    ("signature", 104, 48),
    ("message_digest", 152, 32),
)

RESPONSE_LAYOUT = (
    ("magic", 0, 4),
    ("version", 4, 1),
    ("result_class", 5, 1),
    ("result_code", 6, 1),
    ("reserved", 7, 1),
)

RESULT_CLASS_VERIFIER_STATUS = 0x01
RESULT_CLASS_REQUEST_PROTOCOL_ERROR = 0x02

VERIFIER_STATUS_TAXONOMY = (
    (0, "OK"),
    (1, "NULL_INPUT"),
    (2, "BAD_LENGTH"),
    (3, "PK_BAD_ENCODING"),
    (4, "PK_NON_CANONICAL"),
    (5, "PK_INFINITY"),
    (6, "PK_NOT_IN_GROUP"),
    (7, "SIG_BAD_ENCODING"),
    (8, "SIG_NON_CANONICAL"),
    (9, "SIG_INFINITY"),
    (10, "SIG_NOT_IN_GROUP"),
    (11, "VERIFY_FAILED"),
)
VERIFIER_STATUS_REACHABLE = (0, 3, 4, 5, 6, 7, 8, 9, 10, 11)
VERIFIER_STATUS_UNREACHABLE = (1, 2)

REQUEST_PROTOCOL_ERROR_TAXONOMY = (
    (1, "WRONG_MAGIC"),
    (2, "WRONG_VERSION"),
    (3, "WRONG_OPCODE"),
    (4, "RESERVED_NONZERO"),
    (5, "SHORT_FRAME_EOF"),
    (6, "TRAILING_INPUT"),
)

# The FROZEN field-validation order.  It is LOAD-BEARING and is why two dedicated cases exist.
FIELD_VALIDATION_ORDER = (
    "SHORT_FRAME_EOF",
    "TRAILING_INPUT",
    "WRONG_MAGIC",
    "WRONG_VERSION",
    "WRONG_OPCODE",
    "RESERVED_NONZERO",
    "VERIFY",
)

CANDIDATE_EXIT_CODES = (0, 64, 65)
LAUNCHER_EXIT_CODES = (70,)

# =================================================================================================
# THE GOVERNED CASE EXPECTATIONS (V9 21.4).
#
# Independently frozen here and in bundle entry 5.  A permanent test asserts the two tables are
# identical, which is what makes the duplication a cross-check rather than a drift risk: neither
# unit imports the other, so neither can silently adopt the other's mistake.
# =================================================================================================

STIMULUS_WRITE_ALL_THEN_CLOSE = 0
STIMULUS_WRITE_PREFIX_THEN_SIGKILL = 1
STIMULUS_WRITE_PREFIX_THEN_HOLD = 2

GOVERNED_CASES = (
    ("C01_POSITIVE_EXACT_FIXTURE", 1, 0, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C02_DETERMINISM_EXACT_REPEAT", 1, 0, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C03_PK_BAD_ENCODING", 1, 3, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C04_PK_NON_CANONICAL", 1, 4, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C05_PK_INFINITY", 1, 5, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C06_PK_NOT_IN_GROUP", 1, 6, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C07_SIG_BAD_ENCODING", 1, 7, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C08_SIG_NON_CANONICAL", 1, 8, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C09_SIG_INFINITY", 1, 9, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C10_SIG_NOT_IN_GROUP", 1, 10, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C11_VERIFY_FAILED_WRONG_DIGEST", 1, 11, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C12_VERIFY_FAILED_WRONG_PUBLIC_KEY", 1, 11, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C13_WRONG_MAGIC", 2, 1, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C14_WRONG_VERSION", 2, 2, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C15_WRONG_OPCODE", 2, 3, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C16_RESERVED_NONZERO", 2, 4, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C17_SHORT_FRAME_EOF_EMPTY", 2, 5, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C18_SHORT_FRAME_EOF_PARTIAL_HEADER", 2, 5, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C19_SHORT_FRAME_EOF_ONE_SHORT", 2, 5, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C20_TRAILING_INPUT_ONE_BYTE", 2, 6, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C21_TRAILING_INPUT_SECOND_FRAME", 2, 6, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C22_ORDER_TRAILING_BEFORE_MAGIC", 2, 6, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C23_ORDER_SHORT_BEFORE_MAGIC", 2, 5, 0, STIMULUS_WRITE_ALL_THEN_CLOSE),
    ("C24_CRASH_MID_REQUEST", 0, -1, -1, STIMULUS_WRITE_PREFIX_THEN_SIGKILL),
    ("C25_TIMEOUT_WRITER_WITHHOLDS", 0, -1, -1, STIMULUS_WRITE_PREFIX_THEN_HOLD),
)
EXACT_CASE_COUNT = 25

# The FROZEN construction intent for every case, so the offline generator has an unambiguous target
# and the construction is deterministic by design rather than by bit-flipping.  Single-bit mutation
# is explicitly NOT used for any crypto negative, because which status a flipped bit produces is not
# determinate from the architecture (V9 21.9).
CONSTRUCTION_INTENT = {
    "C01_POSITIVE_EXACT_FIXTURE": "GOVERNED_TEST_ONLY_POSITIVE_VECTOR",
    "C02_DETERMINISM_EXACT_REPEAT": "BYTE_IDENTICAL_REPEAT_OF_C01",
    "C03_PK_BAD_ENCODING": "G2_MALFORMED_COMPRESSION_FLAG_PATTERN",
    "C04_PK_NON_CANONICAL": "G2_X_COORDINATE_GREATER_OR_EQUAL_FIELD_MODULUS",
    "C05_PK_INFINITY": "G2_CANONICAL_INFINITY_ENCODING",
    "C06_PK_NOT_IN_GROUP": "G2_VALID_ENCODING_OUTSIDE_PRIME_ORDER_SUBGROUP",
    "C07_SIG_BAD_ENCODING": "G1_MALFORMED_COMPRESSION_FLAG_PATTERN",
    "C08_SIG_NON_CANONICAL": "G1_X_COORDINATE_GREATER_OR_EQUAL_FIELD_MODULUS",
    "C09_SIG_INFINITY": "G1_CANONICAL_INFINITY_ENCODING",
    "C10_SIG_NOT_IN_GROUP": "G1_VALID_ENCODING_OUTSIDE_PRIME_ORDER_SUBGROUP",
    "C11_VERIFY_FAILED_WRONG_DIGEST": "VALID_SIGNATURE_OVER_A_DIFFERENT_MESSAGE_DIGEST",
    "C12_VERIFY_FAILED_WRONG_PUBLIC_KEY": "VALID_IN_SUBGROUP_PUBLIC_KEY_THAT_IS_NOT_THE_SIGNER",
    "C13_WRONG_MAGIC": "FULL_FRAME_WITH_MAGIC_NOT_MT4W",
    "C14_WRONG_VERSION": "FULL_FRAME_WITH_VERSION_NOT_ONE",
    "C15_WRONG_OPCODE": "FULL_FRAME_WITH_OPCODE_NOT_ONE",
    "C16_RESERVED_NONZERO": "FULL_FRAME_WITH_NONZERO_REQUEST_RESERVED_FIELD",
    "C17_SHORT_FRAME_EOF_EMPTY": "ZERO_BYTES_THEN_EOF",
    "C18_SHORT_FRAME_EOF_PARTIAL_HEADER": "SEVEN_BYTES_THEN_EOF",
    "C19_SHORT_FRAME_EOF_ONE_SHORT": "ONE_HUNDRED_EIGHTY_THREE_BYTES_THEN_EOF",
    "C20_TRAILING_INPUT_ONE_BYTE": "ONE_HUNDRED_EIGHTY_FIVE_BYTES_THEN_EOF",
    "C21_TRAILING_INPUT_SECOND_FRAME": "TWO_COMPLETE_FRAMES_THEN_EOF",
    "C22_ORDER_TRAILING_BEFORE_MAGIC": "OVER_LONG_INPUT_WHOSE_FIRST_FRAME_CARRIES_A_WRONG_MAGIC",
    "C23_ORDER_SHORT_BEFORE_MAGIC": "SHORT_INPUT_THAT_ALSO_CARRIES_A_WRONG_MAGIC",
    "C24_CRASH_MID_REQUEST": "PARTIAL_INPUT_THEN_EXTERNAL_SIGKILL",
    "C25_TIMEOUT_WRITER_WITHHOLDS": "PARTIAL_INPUT_WITH_THE_WRITER_HELD_OPEN_PAST_THE_DEADLINE",
}

# =================================================================================================
# THE FROZEN BINARY CASE PLAN
# =================================================================================================

_CASE_ID_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")

PLAN_MAGIC = b"MT4CPLAN"
PLAN_VERSION = 1
PLAN_HEADER_BYTES = 64
PLAN_CASE_ID_BYTES = 48
MAX_CASE_INPUT_BYTES = 512


class ProtocolQualificationError(RuntimeError):
    """Any failure to prove a required protocol property.  There is no partial success."""


def _fail(marker, detail=""):
    raise ProtocolQualificationError(marker if not detail else marker + ": " + detail)


def _require_int(value, marker, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(marker, "value must be a JSON integer")
    if low is not None and value < low:
        _fail(marker, "value below the governed bound")
    if high is not None and value > high:
        _fail(marker, "value above the governed bound")
    return value


def _require_str(value, marker):
    if not isinstance(value, str):
        _fail(marker, "value must be a JSON string")
    return value


def _is_hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


# =================================================================================================
# V5 CONFORMANCE PROOFS
# =================================================================================================


def prove_wire_contract():
    """Prove the frozen layouts and taxonomies are internally consistent and closed."""
    offset = 0
    for name, field_offset, length in REQUEST_LAYOUT:
        if field_offset != offset:
            _fail("WIRE_LAYOUT_VIOLATION", "request field " + name)
        offset += length
    if offset != REQUEST_FRAME_BYTES:
        _fail("WIRE_LAYOUT_VIOLATION", "request frame length")

    offset = 0
    for name, field_offset, length in RESPONSE_LAYOUT:
        if field_offset != offset:
            _fail("WIRE_LAYOUT_VIOLATION", "response field " + name)
        offset += length
    if offset != RESPONSE_FRAME_BYTES:
        _fail("WIRE_LAYOUT_VIOLATION", "response frame length")

    # V8's layout had a two-byte reserved tail and no RESULT_CLASS at all.  Both are WITHDRAWN, and
    # the exact restored placement is asserted field by field so the defect cannot reappear.
    fields = {name: (start, length) for name, start, length in RESPONSE_LAYOUT}
    if fields["result_class"] != (5, 1):
        _fail("WIRE_LAYOUT_VIOLATION", "RESULT_CLASS must be one byte at offset 5")
    if fields["result_code"] != (6, 1):
        _fail("WIRE_LAYOUT_VIOLATION", "RESULT_CODE must be one byte at offset 6")
    if fields["reserved"] != (7, 1):
        _fail("WIRE_LAYOUT_VIOLATION", "the response reserved tail must be exactly one byte")

    codes = tuple(code for code, _name in VERIFIER_STATUS_TAXONOMY)
    if codes != tuple(range(12)):
        # The governing S3B profile fails closed unless the taxonomy is exactly tuple(range(12)).
        _fail("VERIFIER_CONTRACT_MISMATCH", str(codes))
    if tuple(sorted(VERIFIER_STATUS_REACHABLE + VERIFIER_STATUS_UNREACHABLE)) != codes:
        _fail("VERIFIER_CONTRACT_MISMATCH", "reachability partition")

    error_codes = tuple(code for code, _name in REQUEST_PROTOCOL_ERROR_TAXONOMY)
    if error_codes != (1, 2, 3, 4, 5, 6):
        _fail("REQUEST_PROTOCOL_TAXONOMY_NOT_CLOSED", str(error_codes))

    if set(CANDIDATE_EXIT_CODES) & set(LAUNCHER_EXIT_CODES):
        # The phase-scoped sets must be DISJOINT: a candidate exiting 70 is WORKER_CRASHED.
        _fail("EXIT_CODE_TAXONOMY_NOT_DISJOINT")
    if RESULT_CLASS_VERIFIER_STATUS == 0 or RESULT_CLASS_REQUEST_PROTOCOL_ERROR == 0:
        _fail("WIRE_LAYOUT_VIOLATION", "RESULT_CLASS 0x00 must remain illegal and reserved-invalid")
    if REQUEST_MAGIC == RESPONSE_MAGIC:
        _fail("WIRE_LAYOUT_VIOLATION", "an echoed request must never read as a response")
    if FIELD_VALIDATION_ORDER[0] != "SHORT_FRAME_EOF" or FIELD_VALIDATION_ORDER[1] != "TRAILING_INPUT":
        _fail("FIELD_VALIDATION_ORDER_VIOLATION")


# =================================================================================================
# FIXTURE VALIDATION
# =================================================================================================


def require_generated_fixture(fixture):
    """Fail closed unless the fixture material was produced by the offline one-time generator.

    This gate runs BEFORE any case material is read.  There is no permissive branch: a fixture in
    the PENDING state can never yield a qualification result, so an ungenerated fixture is
    structurally incapable of producing a crypto verdict.
    """
    state = _require_str(fixture.get("fixture_material_state"), "FIXTURE_STATE_INVALID")
    if state not in FIXTURE_STATES:
        _fail("FIXTURE_STATE_INVALID", state)
    if state != FIXTURE_STATE_GENERATED:
        _fail(
            "FIXTURE_MATERIAL_NOT_GENERATED",
            "the TEST-ONLY vector material must be produced offline and one-time by the governed "
            "generator against pinned blst before any case may be driven",
        )
    for field in ("generator_source_sha256", "generator_binary_sha256"):
        if not _is_hex64(fixture.get(field)):
            _fail("FIXTURE_PROVENANCE_INVALID", field)


def validate_fixture(fixture):
    """Strict structural validation of the governed TEST-ONLY fixture."""
    if not isinstance(fixture, dict):
        _fail("FIXTURE_MALFORMED")
    if _require_str(fixture.get("schema"), "FIXTURE_SCHEMA_INVALID") != FIXTURE_SCHEMA:
        _fail("FIXTURE_SCHEMA_INVALID")
    authority = _require_str(fixture.get("vector_authority"), "TEST_VECTOR_AUTHORITY_VIOLATION")
    if authority != TEST_VECTOR_AUTHORITY:
        # The vector must NEVER be labelled official, normative or Quicknet, and must never be
        # reinterpreted as FX-DRAND-QUICKNET.v1 authority (V9 SECTION 39).
        _fail("TEST_VECTOR_AUTHORITY_VIOLATION", authority)

    wire = fixture.get("wire")
    if not isinstance(wire, dict):
        _fail("FIXTURE_MALFORMED", "wire")
    if _require_int(wire.get("request_frame_bytes"), "FIXTURE_MALFORMED") != REQUEST_FRAME_BYTES:
        _fail("FIXTURE_WIRE_MISMATCH", "request_frame_bytes")
    if _require_int(wire.get("response_frame_bytes"), "FIXTURE_MALFORMED") != RESPONSE_FRAME_BYTES:
        _fail("FIXTURE_WIRE_MISMATCH", "response_frame_bytes")

    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != EXACT_CASE_COUNT:
        _fail("OBSERVATION_CASE_COUNT_MISMATCH", str(len(cases) if isinstance(cases, list) else -1))

    for index, (governed, entry) in enumerate(zip(GOVERNED_CASES, cases)):
        case_id, expected_class, expected_code, expected_exit, stimulus_kind = governed
        if not isinstance(entry, dict):
            _fail("FIXTURE_MALFORMED", "case " + str(index))
        if _require_str(entry.get("case_id"), "OBSERVATION_CASE_ID_TYPE_INVALID") != case_id:
            _fail("OBSERVATION_CASE_ORDER_MISMATCH", case_id)
        if (
            _require_str(entry.get("construction_intent"), "FIXTURE_CONSTRUCTION_VIOLATION")
            != CONSTRUCTION_INTENT[case_id]
        ):
            _fail("FIXTURE_CONSTRUCTION_VIOLATION", case_id)
        if _require_int(entry.get("expected_result_class"), "FIXTURE_MALFORMED", 0, 2) != expected_class:
            _fail("OBSERVATION_CASE_RESULT_CLASS_MISMATCH", case_id)
        if _require_int(entry.get("expected_result_code"), "FIXTURE_MALFORMED", -1, 255) != expected_code:
            _fail("OBSERVATION_CASE_RESULT_CODE_MISMATCH", case_id)
        if _require_int(entry.get("expected_exit_status"), "FIXTURE_MALFORMED", -1, 255) != expected_exit:
            _fail("OBSERVATION_CASE_EXIT_STATUS_MISMATCH", case_id)
        if _require_int(entry.get("stimulus_kind"), "FIXTURE_MALFORMED", 0, 2) != stimulus_kind:
            _fail("OBSERVATION_CASE_STIMULUS_MISMATCH", case_id)
    return cases


def _case_input_bytes(entry, case_id):
    text = _require_str(entry.get("input_hex"), "FIXTURE_MALFORMED")
    if len(text) % 2 != 0 or any(character not in "0123456789abcdef" for character in text):
        _fail("FIXTURE_MALFORMED", "input_hex for " + case_id)
    payload = bytes.fromhex(text)
    if len(payload) > MAX_CASE_INPUT_BYTES:
        _fail("FIXTURE_MALFORMED", "input too long for " + case_id)
    return payload


# =================================================================================================
# CASE PLAN CONSTRUCTION
# =================================================================================================


def build_case_plan(fixture_bytes, fixture):
    """Build the frozen binary plan.  Deterministic: identical inputs give identical bytes."""
    require_generated_fixture(fixture)
    cases = validate_fixture(fixture)

    header = bytearray()
    header += PLAN_MAGIC
    header += PLAN_VERSION.to_bytes(4, "little")
    header += EXACT_CASE_COUNT.to_bytes(4, "little")
    header += hashlib.sha256(fixture_bytes).digest()
    header += b"\x00" * 16
    if len(header) != PLAN_HEADER_BYTES:
        _fail("CASE_PLAN_MALFORMED", "header length")

    body = bytearray()
    for governed, entry in zip(GOVERNED_CASES, cases):
        case_id, expected_class, expected_code, expected_exit, stimulus_kind = governed
        identifier = case_id.encode("ascii")
        if len(identifier) > PLAN_CASE_ID_BYTES:
            _fail("CASE_PLAN_MALFORMED", "case identifier too long: " + case_id)
        if any(character not in _CASE_ID_ALPHABET for character in case_id):
            _fail("CASE_PLAN_MALFORMED", "case identifier alphabet: " + case_id)
        payload = _case_input_bytes(entry, case_id)
        body += identifier + b"\x00" * (PLAN_CASE_ID_BYTES - len(identifier))
        body += stimulus_kind.to_bytes(4, "little")
        body += len(payload).to_bytes(4, "little")
        body += expected_class.to_bytes(4, "little")
        body += (expected_code & 0xFFFFFFFF).to_bytes(4, "little")
        body += (expected_exit & 0xFFFFFFFF).to_bytes(4, "little")
        body += payload

    plan = bytes(header + body)
    return plan


# =================================================================================================
# PROTOCOL CONFORMANCE RECORD
# =================================================================================================


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


def build_protocol_record(fixture_bytes, fixture, plan):
    prove_wire_contract()
    record = {
        "schema": PROTOCOL_SCHEMA,
        "platform_id": PLATFORM_ID,
        "wire_protocol": "V5_WIRE_PROTOCOL",
        "request_frame_bytes": REQUEST_FRAME_BYTES,
        "response_frame_bytes": RESPONSE_FRAME_BYTES,
        "request_layout": [
            {"field": name, "offset": start, "length": length} for name, start, length in REQUEST_LAYOUT
        ],
        "response_layout": [
            {"field": name, "offset": start, "length": length} for name, start, length in RESPONSE_LAYOUT
        ],
        "verifier_status_taxonomy": [{"code": code, "name": name} for code, name in VERIFIER_STATUS_TAXONOMY],
        "verifier_status_reachable": list(VERIFIER_STATUS_REACHABLE),
        "verifier_status_legal_but_unreachable": list(VERIFIER_STATUS_UNREACHABLE),
        "request_protocol_error_taxonomy": [
            {"code": code, "name": name} for code, name in REQUEST_PROTOCOL_ERROR_TAXONOMY
        ],
        "field_validation_order": list(FIELD_VALIDATION_ORDER),
        "candidate_exit_codes": list(CANDIDATE_EXIT_CODES),
        "launcher_exit_codes": list(LAUNCHER_EXIT_CODES),
        "case_count": EXACT_CASE_COUNT,
        "case_id_order": [case_id for case_id, _c, _k, _e, _s in GOVERNED_CASES],
        "fixture_schema": FIXTURE_SCHEMA,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "fixture_material_state": fixture["fixture_material_state"],
        "generator_source_sha256": fixture["generator_source_sha256"],
        "generator_binary_sha256": fixture["generator_binary_sha256"],
        "test_vector_authority": TEST_VECTOR_AUTHORITY,
        "case_plan_sha256": hashlib.sha256(plan).hexdigest(),
        "evidence_status": "ADMISSION_EVIDENCE_ONLY",
        "authority_non_transition": {
            "fixture_corpus_admitted": False,
            "fixture_corpus_loaded": False,
            "fixture_corpus_verified": False,
            "proof_verified": False,
            "randomness_verified": False,
            "provider_operationally_approved": False,
            "readiness_promoted": False,
            "connector_promoted": False,
        },
    }
    record["protocol_conformance_digest_sha256"] = hashlib.sha256(
        PROTOCOL_DIGEST_DOMAIN + canonical_json(record)
    ).hexdigest()
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description="MT4-S3C protocol qualifier and case-plan builder")
    parser.add_argument("--fixture", required=True, help="absolute path to the governed TEST-ONLY fixture")
    parser.add_argument("--plan-out", required=True, help="absolute path of the binary case plan to write")
    parser.add_argument("--record-out", required=True, help="absolute path of the conformance record to write")
    args = parser.parse_args(argv)

    with open(args.fixture, "rb") as handle:
        fixture_bytes = handle.read()
    fixture = json.loads(fixture_bytes.decode("utf-8"))

    plan = build_case_plan(fixture_bytes, fixture)
    record = build_protocol_record(fixture_bytes, fixture, plan)

    with open(args.plan_out, "wb") as handle:
        handle.write(plan)
    with open(args.record_out, "wb") as handle:
        handle.write(canonical_json(record))
    sys.stdout.write("MT4_S3C_PROTOCOL_CONFORMANCE_DIGEST=" + record["protocol_conformance_digest_sha256"] + "\n")
    sys.stdout.write("MT4_S3C_CASE_PLAN_DIGEST=" + record["case_plan_sha256"] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
