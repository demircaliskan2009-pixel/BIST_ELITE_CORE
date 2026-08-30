"""MT4-S3C P0 raw observation parser.  Qualification infrastructure only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 20.3, 20.5, 20.7, 27.2.
BUNDLE ENTRY 6 of the exact 16-entry qualification source bundle (V9 SECTION 8).

WHAT THIS MODULE IS.  It decodes the raw observation record (artifact class A3) produced by the
trusted observer, enforces the governed record bounds, and NORMALISES every per-case observation
into a typed structure.  It decodes the ordered syscall and phase event trace, and it decodes the
eight-byte response frame under the exact V5 layout.

WHAT IT NEVER DOES.  It reaches no verdict.  Adjudication -- expected class, expected code, expected
exit status, the ordering rules, the equivalence legs, the digest recomputation -- belongs to bundle
entry 5, which consumes this module's OUTPUT as data.  Keeping decoding and adjudication in separate
units is what lets the adjudicator be written against a typed structure rather than against raw
bytes, and it is why neither unit needs to import the other: there is no cross-script import
anywhere in the qualification source, so V9 SECTION 28 rules R2 and R5 hold by construction.

THE TWO-GATE ORDERING IS STRUCTURAL HERE (V9 20.7).  The process and transport outcome -- exit
status, terminating signal, deadline -- is resolved from fields that are decoded BEFORE the response
bytes are examined, and the decoded response is marked NOT_INTERPRETABLE whenever the process gate
did not pass.  A process or transport failure therefore cannot become a crypto verdict, and the
separation is a property of the data flow rather than a convention.
"""

from __future__ import annotations

import argparse
import json
import sys

# =================================================================================================
# FROZEN IDENTITIES AND GOVERNED BOUNDS (V9 27.2)
# =================================================================================================

RAW_SCHEMA = "mt4-s3c-raw-observation-record.v1"
NORMALISED_SCHEMA = "mt4-s3c-normalised-observation-record.v1"
PLATFORM_ID = "LINUX_X86_64"

MAX_SYSCALL_EVENTS_PER_CASE = 256
MAX_EVENT_RECORD_BYTES = 256
MAX_CASE_FIXED_FIELD_BYTES = 1024
MAX_RECORD_ENVELOPE_BYTES = 32768
MAX_FILTER_INSTRUCTIONS = 512
EXACT_CASE_COUNT = 25

# =================================================================================================
# WIRE_RESPONSE_LAYOUT (V9 20.3).  Fixed eight bytes; exact offsets.
# =================================================================================================

RESPONSE_FRAME_BYTES = 8
RESPONSE_MAGIC = b"MT4R"
RESPONSE_VERSION = 0x01

RESULT_CLASS_VERIFIER_STATUS = 0x01
RESULT_CLASS_REQUEST_PROTOCOL_ERROR = 0x02
LEGAL_RESULT_CLASSES = (RESULT_CLASS_VERIFIER_STATUS, RESULT_CLASS_REQUEST_PROTOCOL_ERROR)

# VERIFIER_STATUS_TAXONOMY (V9 20.4).  The GOVERNED bounded taxonomy: every one of 0..11 is a LEGAL
# WIRE STATUS.  Codes 12..255 are ILLEGAL.  Codes 1 and 2 are legal-but-structurally-unreachable and
# are classified as an internal contract break, NEVER as malformed protocol framing (PT-421).
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
VERIFIER_STATUS_CODES = tuple(code for code, _name in VERIFIER_STATUS_TAXONOMY)
# Statuses 4 (PK_NON_CANONICAL) and 8 (SIG_NON_CANONICAL) remain LEGAL vocabulary but are
# STRUCTURALLY UNREACHABLE from the pinned worker: pinned blst rejects an X coordinate >= the
# field modulus inside blst_p2_uncompress / blst_p1_uncompress, so the worker returns
# PK_BAD_ENCODING / SIG_BAD_ENCODING before it can ever reach its recompress comparison.
# Derived from pinned blst src/e1.c and src/e2.c, not from observed runtime behaviour.
VERIFIER_STATUS_REACHABLE = (0, 3, 5, 6, 7, 9, 10, 11)
VERIFIER_STATUS_UNREACHABLE = (1, 2, 4, 8)

# REQUEST_PROTOCOL_ERROR taxonomy (V9 20.5), CLOSED AT SIX.  0 and 7..255 are ILLEGAL.
REQUEST_PROTOCOL_ERROR_TAXONOMY = (
    (1, "WRONG_MAGIC"),
    (2, "WRONG_VERSION"),
    (3, "WRONG_OPCODE"),
    (4, "RESERVED_NONZERO"),
    (5, "SHORT_FRAME_EOF"),
    (6, "TRAILING_INPUT"),
)
REQUEST_PROTOCOL_ERROR_CODES = tuple(code for code, _name in REQUEST_PROTOCOL_ERROR_TAXONOMY)

# RESERVED CHILD EXIT CODES, PHASE-SCOPED (V9 20.5).  The candidate set and the launcher set are
# DISJOINT BY CONSTRUCTION: a candidate exiting 70 is WORKER_CRASHED, never LAUNCH_FAILED.
CANDIDATE_EXIT_CODES = (0, 64, 65)
LAUNCHER_EXIT_CODES = (70,)

# Response decode outcomes.
RESPONSE_OK = "RESPONSE_WELL_FORMED"
RESPONSE_NOT_INTERPRETABLE = "RESPONSE_NOT_INTERPRETABLE"
RESPONSE_VIOLATION = "WORKER_RESPONSE_PROTOCOL_VIOLATION"

# Process outcomes (V9 20.7), parent-derived only, NEVER on the wire.
PROCESS_CLEAN_EXIT = "PROCESS_CLEAN_EXIT"
PROCESS_WORKER_EXEC_FAILED = "WORKER_EXEC_FAILED"
PROCESS_WORKER_BOOTSTRAP_FAILED = "WORKER_BOOTSTRAP_FAILED"
PROCESS_WORKER_SANDBOX_FAILED = "WORKER_SANDBOX_FAILED"
PROCESS_WORKER_CRASHED = "WORKER_CRASHED"
PROCESS_WORKER_TIMEOUT = "WORKER_TIMEOUT"
PROCESS_INFRASTRUCTURE_FAILURE = "QUALIFICATION_INFRASTRUCTURE_FAILURE"


class ObservationParseError(RuntimeError):
    """Any failure to decode a required observation field.  There is no partial success."""


def _fail(marker, detail=""):
    raise ObservationParseError(marker if not detail else marker + ": " + detail)


def _require_dict(value, marker):
    if not isinstance(value, dict):
        _fail(marker, "value must be a JSON object")
    return value


def _require_list(value, marker):
    if not isinstance(value, list):
        _fail(marker, "value must be a JSON array")
    return value


def _require_str(value, marker):
    if not isinstance(value, str):
        _fail(marker, "value must be a JSON string")
    return value


def _require_bool(value, marker):
    if not isinstance(value, bool):
        _fail(marker, "value must be a JSON boolean")
    return value


def _require_int(value, marker, low=None, high=None):
    # A bool is NOT accepted as an int, and a float such as 2.0 is MALFORMED, not coerced.
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(marker, "value must be a JSON integer")
    if low is not None and value < low:
        _fail(marker, "value below the governed bound")
    if high is not None and value > high:
        _fail(marker, "value above the governed bound")
    return value


def _require_hex(value, marker, max_bytes):
    text = _require_str(value, marker)
    if len(text) % 2 != 0:
        _fail(marker, "hex length must be even")
    if len(text) // 2 > max_bytes:
        _fail(marker, "hex payload exceeds the governed bound")
    if any(character not in "0123456789abcdef" for character in text):
        _fail(marker, "hex must be lowercase [0-9a-f]")
    return bytes.fromhex(text)


def _is_hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


# =================================================================================================
# RESPONSE FRAME DECODING (V9 20.3, 21.6, 21.8)
# =================================================================================================


def decode_response(response_bytes, extra_byte_before_eof):
    """Decode the eight-byte response frame under the exact V5 layout.

    RESULT_CLASS 0x00 IS ILLEGAL AND RESERVED-INVALID ON PURPOSE: an all-zero or partially written
    eight-byte buffer must NOT be interpretable as "VERIFIER_STATUS / OK".  It fails as a response
    protocol violation instead of reading as success.
    """
    if extra_byte_before_eof:
        # Any additional byte, even one, before EOF is a violation (V9 21.8).
        return {"outcome": RESPONSE_VIOLATION, "marker": "EXTRA_BYTE_BEFORE_EOF"}
    if len(response_bytes) != RESPONSE_FRAME_BYTES:
        return {"outcome": RESPONSE_VIOLATION, "marker": "FRAME_LENGTH:" + str(len(response_bytes))}
    if response_bytes[0:4] != RESPONSE_MAGIC:
        return {"outcome": RESPONSE_VIOLATION, "marker": "MAGIC"}
    if response_bytes[4] != RESPONSE_VERSION:
        return {"outcome": RESPONSE_VIOLATION, "marker": "VERSION"}
    result_class = response_bytes[5]
    result_code = response_bytes[6]
    if response_bytes[7] != 0x00:
        return {"outcome": RESPONSE_VIOLATION, "marker": "RESERVED_NONZERO"}
    if result_class not in LEGAL_RESULT_CLASSES:
        return {"outcome": RESPONSE_VIOLATION, "marker": "RESULT_CLASS:" + str(result_class)}
    if result_class == RESULT_CLASS_VERIFIER_STATUS:
        if result_code not in VERIFIER_STATUS_CODES:
            # 12..255 are outside the frozen domain and are therefore malformed protocol.
            return {"outcome": RESPONSE_VIOLATION, "marker": "VERIFIER_STATUS_DOMAIN:" + str(result_code)}
        if result_code in VERIFIER_STATUS_UNREACHABLE:
            # 1 and 2 are LEGAL WIRE STATUSES that this protocol cannot produce.  Their appearance
            # is an INTERNAL CONTRACT BREAK, adjudicated as a response protocol violation -- never
            # as "malformed protocol framing" and never as a crypto result (V9 20.4, PT-421).
            return {
                "outcome": RESPONSE_VIOLATION,
                "marker": "VERIFIER_STATUS_LEGAL_BUT_UNREACHABLE:" + str(result_code),
                "result_class": result_class,
                "result_code": result_code,
            }
    elif result_code not in REQUEST_PROTOCOL_ERROR_CODES:
        # 0 and 7..255 are outside the closed six-member domain.
        return {"outcome": RESPONSE_VIOLATION, "marker": "REQUEST_ERROR_DOMAIN:" + str(result_code)}
    return {"outcome": RESPONSE_OK, "result_class": result_class, "result_code": result_code}


def status_name(result_class, result_code):
    if result_class == RESULT_CLASS_VERIFIER_STATUS:
        for code, name in VERIFIER_STATUS_TAXONOMY:
            if code == result_code:
                return name
    if result_class == RESULT_CLASS_REQUEST_PROTOCOL_ERROR:
        for code, name in REQUEST_PROTOCOL_ERROR_TAXONOMY:
            if code == result_code:
                return name
    return "UNKNOWN"


# =================================================================================================
# PROCESS GATE (V9 20.7).  Resolved WITHOUT touching response bytes.
# =================================================================================================


def resolve_process_outcome(case):
    """Gate one: the process and transport outcome, resolved before any response byte is read."""
    if case["infrastructure_reason"] != "NONE":
        reason = case["infrastructure_reason"]
        if reason == "WORKER_TIMEOUT":
            return PROCESS_WORKER_TIMEOUT
        if reason in ("LAUNCH_FAILED", "WORKER_EXEC_FAILED"):
            return PROCESS_WORKER_EXEC_FAILED
        if reason == "WORKER_SANDBOX_FAILED":
            return PROCESS_WORKER_SANDBOX_FAILED
        if reason == "WORKER_BOOTSTRAP_FAILED":
            return PROCESS_WORKER_BOOTSTRAP_FAILED
        if reason == "WORKER_CRASHED":
            return PROCESS_WORKER_CRASHED
        return PROCESS_INFRASTRUCTURE_FAILURE

    if not case["exec_transition_observed"]:
        # The process never became the candidate.  No verifier interpretation of any byte is
        # permitted and no bytes from the response pipe may be recorded as a result (V9 19.3).
        return PROCESS_WORKER_EXEC_FAILED

    if case["wait_signalled"]:
        return PROCESS_WORKER_CRASHED
    if not case["wait_exited"]:
        return PROCESS_WORKER_CRASHED

    status = case["wait_exit_status"]
    if status == 0:
        return PROCESS_CLEAN_EXIT
    if status == 64:
        return PROCESS_WORKER_BOOTSTRAP_FAILED
    if status == 65:
        return PROCESS_WORKER_SANDBOX_FAILED
    # PHASE-SCOPED: after a proven exec transition, EVERY other status -- including 70 -- is a
    # CANDIDATE behaviour and is WORKER_CRASHED, never LAUNCH_FAILED (V9 19.3 discriminator).
    return PROCESS_WORKER_CRASHED


# =================================================================================================
# RAW RECORD PARSING
# =================================================================================================


def _parse_event(payload, index):
    event = _require_dict(payload, "OBSERVATION_EVENT_MALFORMED")
    serialised = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(serialised) > MAX_EVENT_RECORD_BYTES:
        _fail("OBSERVATION_EVENT_BUDGET_EXCEEDED", "event record bytes")
    sequence = _require_int(event.get("sequence"), "OBSERVATION_EVENT_MALFORMED", 0, MAX_SYSCALL_EVENTS_PER_CASE)
    if sequence != index:
        _fail("OBSERVATION_EVENT_ORDER_MISMATCH", str(sequence))
    stop = _require_str(event.get("stop"), "OBSERVATION_EVENT_MALFORMED")
    if stop not in ("ENTRY", "EXIT"):
        _fail("OBSERVATION_EVENT_MALFORMED", "stop")
    arguments = _require_list(event.get("args"), "OBSERVATION_EVENT_MALFORMED")
    if len(arguments) != 6:
        _fail("OBSERVATION_EVENT_MALFORMED", "args")
    return {
        "sequence": sequence,
        "phase": _require_str(event.get("phase"), "OBSERVATION_EVENT_MALFORMED"),
        "stop": stop,
        "nr": _require_int(event.get("nr"), "OBSERVATION_EVENT_MALFORMED", -2, 2**32 - 1),
        "args": [_require_int(item, "OBSERVATION_EVENT_MALFORMED", 0, 2**64 - 1) for item in arguments],
        "ret": _require_int(event.get("ret"), "OBSERVATION_EVENT_MALFORMED", -(2**63), 2**63 - 1),
    }


def _parse_capture(payload, marker):
    capture = _require_dict(payload, marker)
    return {
        "valid": _require_bool(capture.get("valid"), marker),
        "length": _require_int(capture.get("length"), marker, 0, MAX_FILTER_INSTRUCTIONS),
        "fprog_va_u64": _require_int(capture.get("fprog_va_u64"), marker, 0, 2**64 - 1),
        "filter_va_u64": _require_int(capture.get("filter_va_u64"), marker, 0, 2**64 - 1),
        "install_return_i32": _require_int(capture.get("install_return_i32"), marker, -(2**31), 2**31 - 1),
        "program_bytes": _require_hex(capture.get("program_bytes_hex"), marker, MAX_FILTER_INSTRUCTIONS * 8),
    }


def _parse_case(payload, index):
    case = _require_dict(payload, "OBSERVATION_CASE_MALFORMED")
    case_index = _require_int(case.get("case_index"), "OBSERVATION_CASE_MALFORMED", 1, EXACT_CASE_COUNT)
    if case_index != index + 1:
        _fail("OBSERVATION_CASE_ORDER_MISMATCH", str(case_index))

    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        # An integer case identifier, or any non-string, is a TYPE failure and not a coercion
        # opportunity (V9 21.3).
        _fail("OBSERVATION_CASE_ID_TYPE_INVALID", repr(case_id))

    baseline = _require_dict(case.get("seccomp_baseline"), "SECCOMP_BASELINE_FIELD_MISSING")
    baseline_fields = {}
    for field in (
        "supervisor_seccomp",
        "supervisor_filters",
        "child_seccomp",
        "child_filters",
        "outer_post_seccomp",
        "outer_post_filters",
        "internal_post_seccomp",
        "internal_post_filters",
        "revalidated_filters",
        "trace_successful_seccomp_calls",
    ):
        if field not in baseline:
            _fail("SECCOMP_BASELINE_FIELD_MISSING", field)
        baseline_fields[field] = _require_int(baseline[field], "SECCOMP_BASELINE_FIELD_MALFORMED", 0, 4096)

    equivalence = _require_dict(case.get("internal_filter_equivalence"), "OBSERVATION_CASE_MALFORMED")
    equivalence_valid = _require_bool(equivalence.get("valid"), "OBSERVATION_CASE_MALFORMED")
    equivalence_digest = _require_str(equivalence.get("digest_sha256"), "OBSERVATION_CASE_MALFORMED")
    captured_cbpf_sha256 = _require_str(equivalence.get("captured_internal_cbpf_sha256"), "OBSERVATION_CASE_MALFORMED")
    if equivalence_valid and not _is_hex64(equivalence_digest):
        _fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_INVALID", equivalence_digest)
    if not equivalence_valid and equivalence_digest != "":
        _fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_INVALID", "digest present while the record is invalid")

    dump = _require_dict(case.get("dump_leg"), "OBSERVATION_CASE_MALFORMED")
    availability = _require_str(dump.get("availability"), "OBSERVATION_CASE_MALFORMED")
    if availability not in ("AVAILABLE", "UNAVAILABLE_IN_PINNED_ENVIRONMENT"):
        _fail("OBSERVATION_CASE_MALFORMED", "dump availability")

    events_payload = _require_list(case.get("syscall_events"), "OBSERVATION_CASE_MALFORMED")
    if len(events_payload) > MAX_SYSCALL_EVENTS_PER_CASE:
        _fail("OBSERVATION_EVENT_BUDGET_EXCEEDED", str(len(events_payload)))
    events = [_parse_event(item, position) for position, item in enumerate(events_payload)]
    if _require_int(
        case.get("syscall_event_count"), "OBSERVATION_CASE_MALFORMED", 0, MAX_SYSCALL_EVENTS_PER_CASE
    ) != len(events):
        _fail("OBSERVATION_CASE_MALFORMED", "syscall_event_count")
    if _require_bool(case.get("syscall_event_budget_exceeded"), "OBSERVATION_CASE_MALFORMED"):
        _fail("OBSERVATION_EVENT_BUDGET_EXCEEDED", case_id)

    response_bytes = _require_hex(case.get("response_bytes_hex"), "OBSERVATION_CASE_MALFORMED", RESPONSE_FRAME_BYTES)
    if _require_int(case.get("response_byte_count"), "OBSERVATION_CASE_MALFORMED", 0, RESPONSE_FRAME_BYTES) != len(
        response_bytes
    ):
        _fail("OBSERVATION_CASE_MALFORMED", "response_byte_count")

    normalised = {
        "case_index": case_index,
        "case_id": case_id,
        "stimulus_kind": _require_int(case.get("stimulus_kind"), "OBSERVATION_CASE_MALFORMED", 0, 2),
        "expected_result_class": _require_int(case.get("expected_result_class"), "OBSERVATION_CASE_MALFORMED", 0, 2),
        "expected_result_code": _require_int(case.get("expected_result_code"), "OBSERVATION_CASE_MALFORMED", -1, 255),
        "expected_exit_status": _require_int(case.get("expected_exit_status"), "OBSERVATION_CASE_MALFORMED", -1, 255),
        "observation_basis": _require_str(case.get("observation_basis"), "OBSERVATION_CASE_MALFORMED"),
        "infrastructure_reason": _require_str(case.get("infrastructure_reason"), "OBSERVATION_CASE_MALFORMED"),
        "infrastructure_marker": _require_str(case.get("infrastructure_marker"), "OBSERVATION_CASE_MALFORMED"),
        "exec_transition_observed": _require_bool(case.get("exec_transition_observed"), "OBSERVATION_CASE_MALFORMED"),
        "wait_exited": _require_bool(case.get("wait_exited"), "OBSERVATION_CASE_MALFORMED"),
        "wait_exit_status": _require_int(case.get("wait_exit_status"), "OBSERVATION_CASE_MALFORMED", -1, 255),
        "wait_signalled": _require_bool(case.get("wait_signalled"), "OBSERVATION_CASE_MALFORMED"),
        "wait_signal": _require_int(case.get("wait_signal"), "OBSERVATION_CASE_MALFORMED", 0, 64),
        "deadline_expired": _require_bool(case.get("deadline_expired"), "OBSERVATION_CASE_MALFORMED"),
        "response_bytes": response_bytes,
        "response_extra_byte_before_eof": _require_bool(
            case.get("response_extra_byte_before_eof"), "OBSERVATION_CASE_MALFORMED"
        ),
        "seccomp_baseline": baseline_fields,
        "outer_capture": _parse_capture(case.get("outer_capture"), "OBSERVATION_CASE_MALFORMED"),
        "internal_capture": _parse_capture(case.get("internal_capture"), "OBSERVATION_CASE_MALFORMED"),
        "dump_leg": {
            "availability": availability,
            "terminates_at_index": _require_int(
                dump.get("terminates_at_index"), "OBSERVATION_CASE_MALFORMED", -1, MAX_FILTER_INSTRUCTIONS
            ),
            "index0_bytes": _require_hex(
                dump.get("index0_bytes_hex"), "OBSERVATION_CASE_MALFORMED", MAX_FILTER_INSTRUCTIONS * 8
            ),
            "index1_bytes": _require_hex(
                dump.get("index1_bytes_hex"), "OBSERVATION_CASE_MALFORMED", MAX_FILTER_INSTRUCTIONS * 8
            ),
        },
        "internal_filter_equivalence": {
            "valid": equivalence_valid,
            "digest_sha256": equivalence_digest,
            "captured_internal_cbpf_sha256": captured_cbpf_sha256,
        },
        "syscall_events": events,
        "trace_execve_count": _require_int(
            case.get("trace_execve_count"), "OBSERVATION_CASE_MALFORMED", 0, MAX_SYSCALL_EVENTS_PER_CASE
        ),
    }

    if normalised["observation_basis"] != "EXECUTED_CANDIDATE_UNDER_OUTER_CONTAINMENT":
        _fail("OBSERVATION_BASIS_INVALID", normalised["observation_basis"])

    # GATE ONE, resolved from process and transport fields only.
    process_outcome = resolve_process_outcome(normalised)
    normalised["process_outcome"] = process_outcome

    # GATE TWO, reached only on a clean exit within the deadline.
    if process_outcome == PROCESS_CLEAN_EXIT:
        normalised["response"] = decode_response(response_bytes, normalised["response_extra_byte_before_eof"])
    else:
        normalised["response"] = {"outcome": RESPONSE_NOT_INTERPRETABLE, "marker": process_outcome}

    fixed_field_bytes = len(
        json.dumps(
            {key: value for key, value in normalised.items() if key != "syscall_events"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=lambda item: item.hex() if isinstance(item, bytes) else str(item),
        ).encode("utf-8")
    )
    if fixed_field_bytes > MAX_CASE_FIXED_FIELD_BYTES + (MAX_FILTER_INSTRUCTIONS * 8 * 4):
        _fail("OBSERVATION_CASE_BUDGET_EXCEEDED", str(fixed_field_bytes))
    return normalised


def parse_observation_record(payload):
    """Parse and normalise the whole raw observation record."""
    record = _require_dict(payload, "OBSERVATION_RECORD_MALFORMED")
    if _require_str(record.get("schema"), "OBSERVATION_RECORD_MALFORMED") != RAW_SCHEMA:
        _fail("OBSERVATION_RECORD_SCHEMA_INVALID")
    if _require_str(record.get("platform_id"), "OBSERVATION_RECORD_MALFORMED") != PLATFORM_ID:
        _fail("OBSERVATION_RECORD_PLATFORM_INVALID")
    for field in ("candidate_binary_sha256", "case_plan_sha256", "fixture_sha256"):
        if not _is_hex64(record.get(field)):
            _fail("OBSERVATION_RECORD_MALFORMED", field)

    cases_payload = _require_list(record.get("cases"), "OBSERVATION_RECORD_MALFORMED")
    declared = _require_int(record.get("case_count"), "OBSERVATION_CASE_COUNT_MISMATCH", 0, 4096)
    if declared != len(cases_payload):
        _fail("OBSERVATION_CASE_COUNT_MISMATCH", str(declared))
    if declared != EXACT_CASE_COUNT:
        _fail("OBSERVATION_CASE_COUNT_MISMATCH", str(declared))

    cases = [_parse_case(item, index) for index, item in enumerate(cases_payload)]
    identifiers = [case["case_id"] for case in cases]
    duplicates = {identifier for identifier in identifiers if identifiers.count(identifier) > 1}
    if duplicates:
        _fail("OBSERVATION_CASE_DUPLICATE", ",".join(sorted(duplicates)))

    return {
        "schema": NORMALISED_SCHEMA,
        "platform_id": PLATFORM_ID,
        "candidate_binary_sha256": record["candidate_binary_sha256"],
        "candidate_binary_bytes": _require_int(
            record.get("candidate_binary_bytes"), "OBSERVATION_RECORD_MALFORMED", 1, 8 * 1024 * 1024
        ),
        "case_plan_sha256": record["case_plan_sha256"],
        "fixture_sha256": record["fixture_sha256"],
        "case_count": declared,
        "cases": cases,
    }


def to_serialisable(normalised):
    """Render the normalised record with byte fields as lowercase hex, for a JSON hand-off."""

    def convert(value):
        if isinstance(value, bytes):
            return value.hex()
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    return convert(normalised)


def main(argv=None):
    parser = argparse.ArgumentParser(description="MT4-S3C raw observation parser")
    parser.add_argument("--observation", required=True, help="absolute path to the raw observation record")
    parser.add_argument("--out", required=True, help="absolute path of the normalised record to write")
    args = parser.parse_args(argv)

    with open(args.observation, "rb") as handle:
        payload = json.loads(handle.read().decode("utf-8"))
    normalised = parse_observation_record(payload)
    body = json.dumps(
        to_serialisable(normalised), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    with open(args.out, "wb") as handle:
        handle.write(body)
    sys.stdout.write("MT4_S3C_OBSERVATION_CASES=" + str(normalised["case_count"]) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
