"""MT4-S3C P0 observation adjudicator.  Qualification infrastructure only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 15.6, 16, 20, 21, 32.
BUNDLE ENTRY 5 of the exact 16-entry qualification source bundle (V9 SECTION 8).

WHAT THIS MODULE IS.  It owns the governed OBSERVATION CASE INVENTORY and every adjudication rule
applied to it: the rejection rules that run BEFORE any per-case result is interpreted, the
per-case expected RESULT_CLASS and RESULT_CODE comparison, the phase-scoped exit-status taxonomy,
the syscall ordering and count rules O1..O5, the seccomp baseline and count transitions, and the
INDEPENDENT recomputation of every per-case internal filter equivalence digest.

WHY THE INVENTORY IS DERIVED AND NOT MERELY LISTED.  V9 SECTION 21.2 states derivation rules so an
auditor can CHECK the derivation rather than trust the list.  This module implements those rules as
executable code, derives the inventory from them, and requires the derivation to equal the frozen
table exactly.  A list that no rule produces, or a rule that produces something not in the list,
fails here.

WHY THE COUNT IS 25 AND NOT 16.  V8 froze sixteen cases derived from a wire contract that did not
exist: its "no response frame, exit 64" result type is impossible under V5, and its two-value crypto
result type cannot express a twelve-value taxonomy.  The inventory is RE-DERIVED from the restored
contract, and the restored taxonomy requires one governed case per REACHABLE verifier status.  The
25 decompose as exactly 12 verifier cases, 11 request cases and 2 process cases.

WHAT THIS MODULE IS NOT.  It is unprivileged, reviewed source running in an ordinary job (trust tier
T-B).  Its output is DATA and EVIDENCE, never authority.  It gains credibility only because the
trusted Stage-C gate independently proves the source run, the workflow digest, the source-bundle
digest, the run attempt, the artifact identities and every digest binding.

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

CASE_SET_SCHEMA = "mt4-s3c-observation-case-set.v2"
CASE_SET_DIGEST_DOMAIN = b"mt4-s3c-observation-case-set.v2\x00"
ADJUDICATION_SCHEMA = "mt4-s3c-observation-adjudication.v1"
ADJUDICATION_DIGEST_DOMAIN = b"mt4-s3c-observation-adjudication.v1\x00"
INTERNAL_EQUIVALENCE_SCHEMA = "mt4-s3c-internal-filter-equivalence.v1"
INTERNAL_EQUIVALENCE_DIGEST_DOMAIN = b"mt4-s3c-internal-filter-equivalence.v1\x00"
PROGRAM_REPRESENTATION_VERSION = "mt4-s3c-cbpf-canonical.v1"
PLATFORM_ID = "LINUX_X86_64"

EXACT_CASE_COUNT = 25

RESULT_CLASS_VERIFIER_STATUS = 1
RESULT_CLASS_REQUEST_PROTOCOL_ERROR = 2
RESULT_CLASS_NONE = 0

VERIFIER_STATUS_CODES = tuple(range(12))
# Statuses 4 (PK_NON_CANONICAL) and 8 (SIG_NON_CANONICAL) remain LEGAL vocabulary but are
# STRUCTURALLY UNREACHABLE from the pinned worker: pinned blst rejects an X coordinate >= the
# field modulus inside blst_p2_uncompress / blst_p1_uncompress, so the worker returns
# PK_BAD_ENCODING / SIG_BAD_ENCODING before it can ever reach its recompress comparison.
# Derived from pinned blst src/e1.c and src/e2.c, not from observed runtime behaviour.
VERIFIER_STATUS_REACHABLE = (0, 3, 5, 6, 7, 9, 10, 11)
VERIFIER_STATUS_UNREACHABLE = (1, 2, 4, 8)
REQUEST_PROTOCOL_ERROR_CODES = (1, 2, 3, 4, 5, 6)

CANDIDATE_EXIT_CODES = (0, 64, 65)
LAUNCHER_EXIT_CODES = (70,)

STIMULUS_CLASSES = (
    "CRYPTO_POSITIVE",
    "CRYPTO_NEGATIVE_PUBLIC_KEY",
    "CRYPTO_NEGATIVE_SIGNATURE",
    "CRYPTO_NEGATIVE_VERIFY",
    "REQUEST_PROTOCOL_STIMULUS",
    "PROCESS_STIMULUS",
)

RESULT_TYPES = (
    "RT_VERIFIER_STATUS_FRAME",
    "RT_REQUEST_PROTOCOL_ERROR_FRAME",
    "RT_PROCESS_TERMINATED_BY_SIGNAL",
    "RT_DEADLINE_EXPIRED",
)

CASE_ORIGIN_V5 = "V5_INHERITED"
CASE_ORIGIN_V9 = "V9_STRENGTHENING_CASE"

STIMULUS_WRITE_ALL_THEN_CLOSE = 0
STIMULUS_WRITE_PREFIX_THEN_SIGKILL = 1
STIMULUS_WRITE_PREFIX_THEN_HOLD = 2


class AdjudicationError(RuntimeError):
    """Any failure to prove a required adjudication property.  There is no partial success."""


def _fail(marker, detail=""):
    raise AdjudicationError(marker if not detail else marker + ": " + detail)


# =================================================================================================
# THE DERIVATION RULES (V9 21.2 DR1..DR8, with the DR1b orthogonality rule the audit required).
#
# Each rule below is executable.  derive_case_inventory() applies them in order and the result is
# required to equal FROZEN_CASE_INVENTORY exactly, so the derivation is CHECKED rather than trusted.
#
#   DR1  Every REACHABLE VERIFIER_STATUS code owns at least one governed case.  The structurally
#        unreachable codes -- 1 NULL_INPUT, 2 BAD_LENGTH, 4 PK_NON_CANONICAL and 8
#        SIG_NON_CANONICAL -- get NO case and instead get a rejection rule plus a permanent test.
#        4 and 8 are unreachable because pinned blst refuses an X coordinate >= the field modulus
#        during uncompress, so the worker answers BAD_ENCODING before its recompress check runs.
#   DR1b CONSUMPTION ORTHOGONALITY.  Where one verifier status is reachable through two INDEPENDENT
#        input-consumption paths, EACH path gets its own governed case, because a single code cannot
#        prove both.  VERIFY_FAILED (11) is reachable by altering the MESSAGE DIGEST while keeping a
#        valid signature and public key, and by altering the PUBLIC KEY while keeping a valid
#        signature and digest.  Without both, a worker that ignored the public key entirely would
#        still pass the positive case and every signature case.  This is the rule that makes the
#        formal derivation produce 25 rather than 24.
#   DR2  One governed case per REQUEST_PROTOCOL_ERROR code (1..6), PLUS one case per genuinely
#        distinct BOUNDARY stimulus that the V4/V5 fail-closed enumeration names separately.
#        Distinctness of STIMULUS is what makes a case, not distinctness of code.
#   DR3  Response-side conditions are NOT cases.  A malformed response, an illegal class, an illegal
#        code, a nonzero reserved byte or an extra byte before EOF is an OUTCOME, and is therefore an
#        adjudication rule applied to EVERY case.  Making them cases would double-count.
#   DR4  The determinism requirement is exactly ONE exact repeat of the positive case.
#   DR5  Each PROCESS normalisation outcome requiring a distinct EXTERNAL stimulus is a case: crash
#        and timeout.  Exec failure, bootstrap failure and sandbox failure are NOT cases of the real
#        candidate; they are mutant-worker permanent tests.
#   DR6  Filter installation, ordering, equivalence and the seccomp baseline are NOT cases.  They are
#        adjudication rules applied to EVERY case.
#   DR7  Adversarial mutant WORKERS are PERMANENT TESTS, not members of the governed case set for the
#        real candidate.  Conflating the two is what makes case counts drift.
#   DR8  Two V9_STRENGTHENING_CASEs exercise the frozen field-validation ORDER.  They add no wire
#        code, no offset, no length and no taxonomy member; each one's expected response is a value
#        V5 already requires for its winning condition.
# =================================================================================================

_POSITIVE_CASE_ID = "C01_POSITIVE_EXACT_FIXTURE"
_POSITIVE_CASE_STIMULUS = "CRYPTO_POSITIVE"

# DR1/DR1b crypto-negative cases in FROZEN ORDER: (case_id, expected_status, stimulus_class).
#
# The list is keyed by CASE, not by status, because a status may be reachable through more than one
# INDEPENDENT construction and each construction earns its own case (DR1b).  Three statuses are
# doubled here:
#
#   3  PK_BAD_ENCODING  -- a malformed G2 compression flag (C03), and a G2 X coordinate that is
#                          >= the field modulus (C04).
#   7  SIG_BAD_ENCODING -- the same two constructions on G1 (C07, C08).
#   11 VERIFY_FAILED    -- a wrong message digest (C11), and a wrong public key (C12).
#
# Statuses 4 and 8 appear NOWHERE in this list.  They are legal vocabulary but structurally
# unreachable from the pinned worker, so giving them a case would assert a behaviour the pinned
# implementation cannot produce.  See VERIFIER_STATUS_UNREACHABLE above.
_CRYPTO_NEGATIVE_CASES = (
    ("C03_PK_BAD_ENCODING", 3, "CRYPTO_NEGATIVE_PUBLIC_KEY"),
    ("C04_PK_FIELD_MODULUS_BAD_ENCODING", 3, "CRYPTO_NEGATIVE_PUBLIC_KEY"),
    ("C05_PK_INFINITY", 5, "CRYPTO_NEGATIVE_PUBLIC_KEY"),
    ("C06_PK_NOT_IN_GROUP", 6, "CRYPTO_NEGATIVE_PUBLIC_KEY"),
    ("C07_SIG_BAD_ENCODING", 7, "CRYPTO_NEGATIVE_SIGNATURE"),
    ("C08_SIG_FIELD_MODULUS_BAD_ENCODING", 7, "CRYPTO_NEGATIVE_SIGNATURE"),
    ("C09_SIG_INFINITY", 9, "CRYPTO_NEGATIVE_SIGNATURE"),
    ("C10_SIG_NOT_IN_GROUP", 10, "CRYPTO_NEGATIVE_SIGNATURE"),
    ("C11_VERIFY_FAILED_WRONG_DIGEST", 11, "CRYPTO_NEGATIVE_VERIFY"),
    ("C12_VERIFY_FAILED_WRONG_PUBLIC_KEY", 11, "CRYPTO_NEGATIVE_PUBLIC_KEY"),
)

# DR2 boundary stimuli: (case_id, request-error code).  Codes 5 and 6 each carry the distinct
# boundary stimuli that the fail-closed enumeration names separately.
_REQUEST_CASE_STIMULI = (
    ("C13_WRONG_MAGIC", 1),
    ("C14_WRONG_VERSION", 2),
    ("C15_WRONG_OPCODE", 3),
    ("C16_RESERVED_NONZERO", 4),
    ("C17_SHORT_FRAME_EOF_EMPTY", 5),
    ("C18_SHORT_FRAME_EOF_PARTIAL_HEADER", 5),
    ("C19_SHORT_FRAME_EOF_ONE_SHORT", 5),
    ("C20_TRAILING_INPUT_ONE_BYTE", 6),
    ("C21_TRAILING_INPUT_SECOND_FRAME", 6),
)

# DR8 ordering cases: each pins which of two simultaneously true conditions wins.
_ORDERING_CASE_STIMULI = (
    ("C22_ORDER_TRAILING_BEFORE_MAGIC", 6),
    ("C23_ORDER_SHORT_BEFORE_MAGIC", 5),
)

# DR5 process cases.
_PROCESS_CASE_STIMULI = (
    ("C24_CRASH_MID_REQUEST", "RT_PROCESS_TERMINATED_BY_SIGNAL", STIMULUS_WRITE_PREFIX_THEN_SIGKILL),
    ("C25_TIMEOUT_WRITER_WITHHOLDS", "RT_DEADLINE_EXPIRED", STIMULUS_WRITE_PREFIX_THEN_HOLD),
)


def _case(index, case_id, stimulus_class, result_type, result_class, result_code, exit_status, origin, stimulus_kind):
    return {
        "case_index": index,
        "case_id": case_id,
        "stimulus_class": stimulus_class,
        "expected_result_type": result_type,
        "expected_result_class": result_class,
        "expected_result_code": result_code,
        "expected_exit_status": exit_status,
        "case_origin": origin,
        "stimulus_kind": stimulus_kind,
    }


def derive_case_inventory():
    """Apply DR1, DR1b, DR2, DR4, DR5 and DR8 in order and return the derived inventory."""
    derived = []
    index = 1

    # DR1: the positive case comes first because DR4's repeat is defined relative to it.
    derived.append(
        _case(
            index,
            _POSITIVE_CASE_ID,
            _POSITIVE_CASE_STIMULUS,
            "RT_VERIFIER_STATUS_FRAME",
            RESULT_CLASS_VERIFIER_STATUS,
            0,
            0,
            CASE_ORIGIN_V5,
            STIMULUS_WRITE_ALL_THEN_CLOSE,
        )
    )
    index += 1

    # DR4: exactly ONE exact repeat of the positive case.
    derived.append(
        _case(
            index,
            "C02_DETERMINISM_EXACT_REPEAT",
            "CRYPTO_POSITIVE",
            "RT_VERIFIER_STATUS_FRAME",
            RESULT_CLASS_VERIFIER_STATUS,
            0,
            0,
            CASE_ORIGIN_V5,
            STIMULUS_WRITE_ALL_THEN_CLOSE,
        )
    )
    index += 1

    # DR1 continued, with DR1b folded in: the frozen crypto-negative case order.  Iterating the CASE
    # list rather than the status list is what lets one status carry two independent constructions.
    for case_id, code, stimulus_class in _CRYPTO_NEGATIVE_CASES:
        derived.append(
            _case(
                index,
                case_id,
                stimulus_class,
                "RT_VERIFIER_STATUS_FRAME",
                RESULT_CLASS_VERIFIER_STATUS,
                code,
                0,
                CASE_ORIGIN_V5,
                STIMULUS_WRITE_ALL_THEN_CLOSE,
            )
        )
        index += 1

    # DR2: one case per request-error code plus each distinct boundary stimulus.
    for case_id, code in _REQUEST_CASE_STIMULI:
        derived.append(
            _case(
                index,
                case_id,
                "REQUEST_PROTOCOL_STIMULUS",
                "RT_REQUEST_PROTOCOL_ERROR_FRAME",
                RESULT_CLASS_REQUEST_PROTOCOL_ERROR,
                code,
                0,
                CASE_ORIGIN_V5,
                STIMULUS_WRITE_ALL_THEN_CLOSE,
            )
        )
        index += 1

    # DR8: the two frozen-validation-order cases.
    for case_id, code in _ORDERING_CASE_STIMULI:
        derived.append(
            _case(
                index,
                case_id,
                "REQUEST_PROTOCOL_STIMULUS",
                "RT_REQUEST_PROTOCOL_ERROR_FRAME",
                RESULT_CLASS_REQUEST_PROTOCOL_ERROR,
                code,
                0,
                CASE_ORIGIN_V9,
                STIMULUS_WRITE_ALL_THEN_CLOSE,
            )
        )
        index += 1

    # DR5: the two process cases.
    for case_id, result_type, stimulus_kind in _PROCESS_CASE_STIMULI:
        derived.append(
            _case(
                index,
                case_id,
                "PROCESS_STIMULUS",
                result_type,
                RESULT_CLASS_NONE,
                -1,
                -1,
                CASE_ORIGIN_V5,
                stimulus_kind,
            )
        )
        index += 1

    if len(derived) != EXACT_CASE_COUNT:
        _fail("OBSERVATION_CASE_COUNT_MISMATCH", str(len(derived)))
    return tuple(derived)


FROZEN_CASE_INVENTORY = derive_case_inventory()
FROZEN_CASE_IDS = tuple(case["case_id"] for case in FROZEN_CASE_INVENTORY)

# Composition proof, stated as an executable assertion rather than a comment.
VERIFIER_CASE_COUNT = sum(1 for case in FROZEN_CASE_INVENTORY if case["expected_result_class"] == 1)
REQUEST_CASE_COUNT = sum(1 for case in FROZEN_CASE_INVENTORY if case["expected_result_class"] == 2)
PROCESS_CASE_COUNT = sum(1 for case in FROZEN_CASE_INVENTORY if case["expected_result_class"] == 0)


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


def domain_digest(domain, payload):
    return hashlib.sha256(domain + canonical_json(payload)).hexdigest()


def case_set_preimage():
    """CASE_SET_SCHEMA v2 (V9 21.3).  v2 because v1's result-type enum cannot express class+code."""
    return {
        "schema": CASE_SET_SCHEMA,
        "case_count": EXACT_CASE_COUNT,
        "cases": [
            {
                "case_index": case["case_index"],
                "case_id": case["case_id"],
                "stimulus_class": case["stimulus_class"],
                "expected_result_type": case["expected_result_type"],
                "expected_result_class": case["expected_result_class"],
                "expected_result_code": case["expected_result_code"],
                "expected_exit_status": case["expected_exit_status"],
                "case_origin": case["case_origin"],
            }
            for case in FROZEN_CASE_INVENTORY
        ],
        "case_id_order": list(FROZEN_CASE_IDS),
    }


def observation_case_set_digest():
    return domain_digest(CASE_SET_DIGEST_DOMAIN, case_set_preimage())


# =================================================================================================
# REJECTION RULES BEFORE ADJUDICATION (V9 21.7).  Each carries a distinct marker and fails closed.
# No partially valid case set is ever adjudicated.
# =================================================================================================


def reject_invalid_case_set(cases):
    observed_ids = [case["case_id"] for case in cases]
    if len(cases) != EXACT_CASE_COUNT:
        _fail("OBSERVATION_CASE_COUNT_MISMATCH", str(len(cases)))
    for identifier in observed_ids:
        if not isinstance(identifier, str):
            _fail("OBSERVATION_CASE_ID_TYPE_INVALID", repr(identifier))
    for identifier in FROZEN_CASE_IDS:
        occurrences = observed_ids.count(identifier)
        if occurrences == 0:
            _fail("OBSERVATION_CASE_MISSING", identifier)
        if occurrences > 1:
            _fail("OBSERVATION_CASE_DUPLICATE", identifier)
    for identifier in observed_ids:
        if identifier not in FROZEN_CASE_IDS:
            _fail("OBSERVATION_CASE_UNKNOWN", identifier)
    if tuple(observed_ids) != FROZEN_CASE_IDS:
        _fail("OBSERVATION_CASE_ORDER_MISMATCH")

    for expected, observed in zip(FROZEN_CASE_INVENTORY, cases):
        if observed["expected_result_class"] != expected["expected_result_class"]:
            _fail("OBSERVATION_CASE_RESULT_CLASS_MISMATCH", expected["case_id"])
        if observed["expected_result_code"] != expected["expected_result_code"]:
            _fail("OBSERVATION_CASE_RESULT_CODE_MISMATCH", expected["case_id"])
        if observed["expected_exit_status"] != expected["expected_exit_status"]:
            _fail("OBSERVATION_CASE_EXIT_STATUS_MISMATCH", expected["case_id"])
        if observed["stimulus_kind"] != expected["stimulus_kind"]:
            _fail("OBSERVATION_CASE_STIMULUS_MISMATCH", expected["case_id"])
        expected_class = expected["expected_result_class"]
        expected_code = expected["expected_result_code"]
        if expected_class == RESULT_CLASS_VERIFIER_STATUS and expected_code not in VERIFIER_STATUS_REACHABLE:
            _fail("OBSERVATION_CASE_STATUS_DOMAIN_INVALID", expected["case_id"])
        if expected_class == RESULT_CLASS_REQUEST_PROTOCOL_ERROR and expected_code not in REQUEST_PROTOCOL_ERROR_CODES:
            _fail("OBSERVATION_CASE_STATUS_DOMAIN_INVALID", expected["case_id"])


# =================================================================================================
# ADJUDICATION RULES APPLIED TO EVERY CASE (V9 21.8)
# =================================================================================================


def _check_syscall_ordering(case, policy, findings):
    """Rules O1..O5 of V9 15.6, adjudicated over the ordered trace.

    The syscall NUMBERS come from the canonical policy record, which derived them from the pinned
    UAPI headers through the canonical probe.  No number is asserted from memory here.
    """
    numbers = policy["syscall_numbers"]
    candidate_entries = [
        event for event in case["syscall_events"] if event["phase"] == "CANDIDATE" and event["stop"] == "ENTRY"
    ]

    seccomp_positions = [
        position for position, event in enumerate(candidate_entries) if event["nr"] == numbers["seccomp"]
    ]
    read_positions = [
        position
        for position, event in enumerate(candidate_entries)
        if event["nr"] == numbers["read"] and event["args"][0] == 3
    ]

    # O2: EXACTLY ONE seccomp call in the candidate trace.  A second is a failure even if its
    # program were canonical, because installed authority would then be ambiguous.
    if case["exec_transition_observed"] and len(seccomp_positions) != 1:
        findings.append("SANDBOX_INSTALL_COUNT_VIOLATION:" + str(len(seccomp_positions)))

    # O1: the candidate's seccomp call must PRECEDE the first read on the request descriptor.
    if seccomp_positions and read_positions and seccomp_positions[0] > read_positions[0]:
        findings.append("SANDBOX_ORDERING_VIOLATION")
    if read_positions and not seccomp_positions:
        findings.append("SANDBOX_ORDERING_VIOLATION")

    # O3: exactly ONE execve in the trace -- the trusted transition itself.
    if case["exec_transition_observed"] and case["trace_execve_count"] != 1:
        findings.append("EXEC_COUNT_VIOLATION:" + str(case["trace_execve_count"]))

    # O4: after the internal install, no syscall outside the intersection set {read, write,
    # exit_group} may appear with a successful return.
    if seccomp_positions:
        allowed = (numbers["read"], numbers["write"], numbers["exit_group"], numbers["seccomp"])
        for event in candidate_entries[seccomp_positions[0] + 1 :]:
            if event["nr"] >= 0 and event["nr"] not in allowed:
                findings.append("SANDBOX_INTERSECTION_VIOLATION:" + str(event["nr"]))
                break

    # O5: the trace-derived filter count must AGREE with the /proc-derived count.
    baseline = case["seccomp_baseline"]
    derived = baseline["supervisor_filters"] + baseline["trace_successful_seccomp_calls"]
    if baseline["revalidated_filters"] != 0 and derived != baseline["revalidated_filters"]:
        findings.append("SECCOMP_COUNT_DISAGREEMENT")


def _check_seccomp_baseline(case, findings):
    """SECCOMP_STACK_BASELINE_V1 measurements M-1..M-5 (V9 SECTION 11)."""
    baseline = case["seccomp_baseline"]
    if baseline["supervisor_seccomp"] != 0 or baseline["supervisor_filters"] != 0:
        findings.append("SECCOMP_BASELINE_NONZERO:M-1")
    if baseline["child_seccomp"] != 0 or baseline["child_filters"] != 0:
        findings.append("SECCOMP_BASELINE_NONZERO:M-2")
    if case["exec_transition_observed"]:
        if baseline["outer_post_seccomp"] != 2 or baseline["outer_post_filters"] != 1:
            findings.append("SECCOMP_COUNT_TRANSITION_INVALID:M-3")
        if baseline["internal_post_seccomp"] != 2 or baseline["internal_post_filters"] != 2:
            findings.append("SECCOMP_COUNT_TRANSITION_INVALID:M-4")
        if baseline["revalidated_filters"] != 2:
            findings.append("SECCOMP_COUNT_TRANSITION_INVALID:M-5")


def _check_filter_equivalence(case, policy, findings):
    """Legs L1 and L2 plus the ELF-derived link-time address expectation of leg L1."""
    internal = case["internal_capture"]
    outer = case["outer_capture"]

    if not outer["valid"]:
        findings.append("OUTER_FILTER_EQUIVALENCE_FAILED:not_captured")
    elif cbpf_digest(outer["program_bytes"]) != policy["outer_emitted_cbpf_sha256"]:
        findings.append("OUTER_FILTER_EQUIVALENCE_FAILED:captured_differs")

    if not internal["valid"]:
        findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:not_captured")
        return
    if internal["length"] != policy["internal_cbpf_instruction_count"]:
        findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:length")
    if cbpf_digest(internal["program_bytes"]) != policy["internal_emitted_cbpf_sha256"]:
        findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:captured_differs")
    if internal["install_return_i32"] != 0:
        findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:install_return")
    # LEG L1: uargs must equal the exact link-time virtual address of the canonical sock_fprog
    # object in the qualified candidate image, as determined by the B0 static ELF analysis of the
    # SAME digest-proven bytes.  A pointer into the stack, heap or anywhere else fails immediately.
    if policy.get("internal_fprog_va_u64") is not None and internal["fprog_va_u64"] != policy["internal_fprog_va_u64"]:
        findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:uargs_not_link_time_address")
    if (
        policy.get("internal_program_va_u64") is not None
        and internal["filter_va_u64"] != policy["internal_program_va_u64"]
    ):
        findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:filter_not_link_time_address")

    # LEG L3, corroboration only.  Unavailability is recorded, never a failure; a mismatch when it IS
    # available is a hard failure and is never a substitute for L0, L1 or L2.
    dump = case["dump_leg"]
    if dump["availability"] == "AVAILABLE":
        if dump["terminates_at_index"] != 2:
            findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:dump_terminating_index")
        if cbpf_digest(dump["index0_bytes"]) != policy["internal_emitted_cbpf_sha256"]:
            findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:dump_index0")
        if cbpf_digest(dump["index1_bytes"]) != policy["outer_emitted_cbpf_sha256"]:
            findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:dump_index1")


def cbpf_digest(program_bytes):
    """CBPF_DIGEST over the canonical representation (V9 13.2)."""
    if len(program_bytes) % 8 != 0:
        _fail("CBPF_REPRESENTATION_INVALID", str(len(program_bytes)))
    count = len(program_bytes) // 8
    preimage = PROGRAM_REPRESENTATION_VERSION.encode("ascii") + b"\x00" + count.to_bytes(4, "little") + program_bytes
    return hashlib.sha256(preimage).hexdigest()


# =================================================================================================
# INTERNAL FILTER EQUIVALENCE DIGEST RECOMPUTATION (V9 16.4)
#
# This is the SECOND of three independent computations of the same value.  The trusted observer
# computed it into A3 from the live observation; this adjudicator recomputes it here from the raw
# observation FIELDS using the canonical reference it derives itself; and the trusted Stage-C gate
# recomputes it a third time and requires A3 == A4 == STAGE_C_RECOMPUTED.  A receipt carrying a
# digest is a claim; the recomputation is the proof.
# =================================================================================================

INTERNAL_EQUIVALENCE_REQUIRED_VALUES = {
    "install_exit_return_i32": 0,
    "baseline_supervisor_seccomp": 0,
    "baseline_supervisor_filters": 0,
    "baseline_child_seccomp": 0,
    "baseline_child_filters": 0,
    "pre_install_filters": 1,
    "post_install_filters": 2,
    "post_install_seccomp_mode": 2,
    "revalidated_filters": 2,
}


def build_equivalence_record(case, policy, identity):
    dump = case["dump_leg"]
    available = dump["availability"] == "AVAILABLE"
    return {
        "schema": INTERNAL_EQUIVALENCE_SCHEMA,
        "canonical_internal_policy_id": policy["internal_policy_id"],
        "canonical_internal_policy_sha256": policy["internal_policy_sha256"],
        "program_representation_version": PROGRAM_REPRESENTATION_VERSION,
        "canonical_internal_cbpf_instruction_count": policy["internal_cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": policy["internal_emitted_cbpf_sha256"],
        "captured_internal_cbpf_sha256": cbpf_digest(case["internal_capture"]["program_bytes"]),
        "captured_internal_uargs_va_u64": case["internal_capture"]["fprog_va_u64"],
        "captured_internal_len_u32": case["internal_capture"]["length"],
        "install_exit_return_i32": case["internal_capture"]["install_return_i32"],
        "baseline_supervisor_seccomp": case["seccomp_baseline"]["supervisor_seccomp"],
        "baseline_supervisor_filters": case["seccomp_baseline"]["supervisor_filters"],
        "baseline_child_seccomp": case["seccomp_baseline"]["child_seccomp"],
        "baseline_child_filters": case["seccomp_baseline"]["child_filters"],
        "pre_install_filters": case["seccomp_baseline"]["outer_post_filters"],
        "post_install_filters": case["seccomp_baseline"]["internal_post_filters"],
        "post_install_seccomp_mode": case["seccomp_baseline"]["internal_post_seccomp"],
        "revalidated_filters": case["seccomp_baseline"]["revalidated_filters"],
        "dump_leg_availability": dump["availability"],
        "dump_leg_index0_sha256": cbpf_digest(dump["index0_bytes"]) if available else "",
        "dump_leg_index1_sha256": cbpf_digest(dump["index1_bytes"]) if available else "",
        "dump_leg_terminates_at_index": dump["terminates_at_index"] if available else -1,
        "case_id": case["case_id"],
        "source_run_id": identity["source_run_id"],
        "source_run_attempt": identity["source_run_attempt"],
        "source_head_sha": identity["source_head_sha"],
        "candidate_binary_sha256": identity["candidate_binary_sha256"],
    }


def validate_equivalence_record(record):
    """Validate BEFORE digesting.  A violating record is never digested (V9 16.3)."""
    for field, expected in INTERNAL_EQUIVALENCE_REQUIRED_VALUES.items():
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            _fail("INTERNAL_FILTER_EQUIVALENCE_CONSTRAINT_VIOLATED", field)
    if record["captured_internal_cbpf_sha256"] != record["canonical_internal_cbpf_sha256"]:
        _fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured program differs from canonical")
    if record["captured_internal_len_u32"] != record["canonical_internal_cbpf_instruction_count"]:
        _fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured length differs from canonical")
    if record["dump_leg_availability"] == "AVAILABLE":
        if not record["dump_leg_index0_sha256"] or not record["dump_leg_index1_sha256"]:
            _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "AVAILABLE with empty dump fields")
        if record["dump_leg_terminates_at_index"] != 2:
            _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "terminating index")
    elif record["dump_leg_index0_sha256"] or record["dump_leg_index1_sha256"]:
        _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "unavailable dump carries digests")
    return record


def recompute_equivalence_digest(case, policy, identity):
    record = validate_equivalence_record(build_equivalence_record(case, policy, identity))
    return domain_digest(INTERNAL_EQUIVALENCE_DIGEST_DOMAIN, record)


# =================================================================================================
# PER-CASE ADJUDICATION
# =================================================================================================


def adjudicate_case(expected, case, policy, identity):
    findings = []

    _check_seccomp_baseline(case, findings)
    _check_syscall_ordering(case, policy, findings)
    # Repair 4: the containment legs run for EVERY case, before the result-type split below.  They
    # describe what the candidate INSTALLED during bootstrap, which is complete before any stimulus
    # is consumed and is therefore independent of how the case ended.
    _check_filter_equivalence(case, policy, findings)

    process_outcome = case["process_outcome"]
    response = case["response"]
    result_type = expected["expected_result_type"]

    if result_type == "RT_PROCESS_TERMINATED_BY_SIGNAL":
        # No response frame is read or interpreted (V9 21.6).
        if process_outcome != "WORKER_CRASHED":
            findings.append("PROCESS_OUTCOME_MISMATCH:" + process_outcome)
        if response["outcome"] != "RESPONSE_NOT_INTERPRETABLE":
            findings.append("RESPONSE_INTERPRETED_ON_PROCESS_FAILURE")
    elif result_type == "RT_DEADLINE_EXPIRED":
        if process_outcome != "WORKER_TIMEOUT":
            findings.append("PROCESS_OUTCOME_MISMATCH:" + process_outcome)
        if response["outcome"] != "RESPONSE_NOT_INTERPRETABLE":
            findings.append("RESPONSE_INTERPRETED_ON_PROCESS_FAILURE")
    else:
        # BOTH frame result types require exit status EXACTLY 0.  That is the V5 rule V8 broke, and
        # it is restated at the point of use so it cannot be lost again.
        if process_outcome != "PROCESS_CLEAN_EXIT":
            findings.append("PROCESS_OUTCOME_MISMATCH:" + process_outcome)
        elif case["wait_exit_status"] != 0:
            findings.append("EXIT_STATUS_MISMATCH:" + str(case["wait_exit_status"]))
        if response["outcome"] != "RESPONSE_WELL_FORMED":
            findings.append("WORKER_RESPONSE_PROTOCOL_VIOLATION:" + str(response.get("marker", "")))
        else:
            if response["result_class"] != expected["expected_result_class"]:
                findings.append("OBSERVATION_CASE_RESULT_CLASS_MISMATCH")
            elif response["result_code"] != expected["expected_result_code"]:
                findings.append("OBSERVATION_CASE_RESULT_CODE_MISMATCH:" + str(response["result_code"]))

    # The phase-scoped exit-status taxonomy (V9 20.5).  Candidate {0,64,65}; launcher {70}.  After a
    # proven exec transition a status of 70 is a CANDIDATE behaviour and is WORKER_CRASHED.
    if case["exec_transition_observed"] and case["wait_exited"]:
        if case["wait_exit_status"] not in CANDIDATE_EXIT_CODES:
            findings.append("CANDIDATE_EXIT_STATUS_OUT_OF_TAXONOMY:" + str(case["wait_exit_status"]))

    # Repair 4.  EVERY case is required to carry a recomputed equivalence digest.  The old
    # PROCESS_CLEAN_EXIT precondition made the two process cases exempt, which is exactly the
    # unbound path this closes: an absent internal capture is now a CASE FAILURE for every case,
    # never a silently empty digest that downstream code has to interpret.
    equivalence_digest = ""
    equivalence_recomputed = False
    if case["internal_capture"]["valid"]:
        try:
            equivalence_digest = recompute_equivalence_digest(case, policy, identity)
            equivalence_recomputed = True
        except AdjudicationError as error:
            findings.append(str(error))
        if equivalence_recomputed and case["internal_filter_equivalence"]["digest_sha256"] != equivalence_digest:
            # A3 must equal the adjudicator's INDEPENDENT recomputation.
            findings.append("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH")
    else:
        findings.append("INTERNAL_FILTER_EQUIVALENCE_FAILED:absent")

    return {
        "case_index": expected["case_index"],
        "case_id": expected["case_id"],
        "stimulus_class": expected["stimulus_class"],
        "expected_result_type": result_type,
        "expected_result_class": expected["expected_result_class"],
        "expected_result_code": expected["expected_result_code"],
        "observed_process_outcome": process_outcome,
        "observed_response_outcome": response["outcome"],
        "observed_result_class": response.get("result_class", -1),
        "observed_result_code": response.get("result_code", -1),
        "internal_filter_equivalence_digest_sha256": equivalence_digest,
        "case_verdict": "CASE_CONFORMS" if not findings else "CASE_FAILED",
        "findings": sorted(findings),
    }


def adjudicate(normalised, policy, identity):
    reject_invalid_case_set(normalised["cases"])

    if normalised["candidate_binary_sha256"] != identity["candidate_binary_sha256"]:
        _fail("CANDIDATE_IDENTITY_MISMATCH")

    verdicts = [
        adjudicate_case(expected, case, policy, identity)
        for expected, case in zip(FROZEN_CASE_INVENTORY, normalised["cases"])
    ]

    # C02 must be byte-identical to C01: the determinism requirement (V9 21.4, PT-424).
    first = normalised["cases"][0]
    repeat = normalised["cases"][1]
    if first["response_bytes"] != repeat["response_bytes"]:
        verdicts[1]["findings"].append("DETERMINISM_VIOLATION")
        verdicts[1]["case_verdict"] = "CASE_FAILED"

    record = {
        "schema": ADJUDICATION_SCHEMA,
        "platform_id": PLATFORM_ID,
        "observation_case_set_digest_sha256": observation_case_set_digest(),
        "case_set_schema": CASE_SET_SCHEMA,
        "case_count": EXACT_CASE_COUNT,
        "verifier_case_count": VERIFIER_CASE_COUNT,
        "request_case_count": REQUEST_CASE_COUNT,
        "process_case_count": PROCESS_CASE_COUNT,
        "candidate_binary_sha256": identity["candidate_binary_sha256"],
        "source_run_id": identity["source_run_id"],
        "source_run_attempt": identity["source_run_attempt"],
        "source_head_sha": identity["source_head_sha"],
        "case_plan_sha256": normalised["case_plan_sha256"],
        "fixture_sha256": normalised["fixture_sha256"],
        "outer_containment_policy_digest_sha256": policy["outer_governed_digest_sha256"],
        "canonical_internal_policy_id": policy["internal_policy_id"],
        "canonical_internal_policy_sha256": policy["internal_policy_sha256"],
        "case_verdicts": verdicts,
        "all_cases_conform": all(verdict["case_verdict"] == "CASE_CONFORMS" for verdict in verdicts),
        "evidence_status": "ADMISSION_EVIDENCE_ONLY",
        "authority_non_transition": {
            "readiness_transition": "NONE",
            "connector_transition": "NONE",
            "product_native_execution": "NO",
            "machine_time_authority": "NONE",
            "mt5_mt6_authority": "NONE",
            "stage4_authority": "NONE",
        },
    }
    record["adjudication_digest_sha256"] = domain_digest(ADJUDICATION_DIGEST_DOMAIN, record)
    return record


# =================================================================================================
# INPUT LOADING
# =================================================================================================


def _load_json(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _rehydrate(normalised):
    """Convert the parser's hex fields back into bytes for adjudication."""

    def unhex(value):
        return bytes.fromhex(value)

    for case in normalised["cases"]:
        case["response_bytes"] = unhex(case["response_bytes"])
        for key in ("outer_capture", "internal_capture"):
            case[key]["program_bytes"] = unhex(case[key]["program_bytes"])
        case["dump_leg"]["index0_bytes"] = unhex(case["dump_leg"]["index0_bytes"])
        case["dump_leg"]["index1_bytes"] = unhex(case["dump_leg"]["index1_bytes"])
    return normalised


def policy_reference(policy_record, elf_record):
    """Assemble the canonical reference the adjudicator derives for itself, never from a receipt."""
    reference = {
        "internal_policy_id": policy_record["canonical_internal_policy_id"],
        "internal_policy_sha256": policy_record["canonical_internal_policy_sha256"],
        "internal_cbpf_instruction_count": policy_record["canonical_internal_cbpf_instruction_count"],
        "internal_emitted_cbpf_sha256": policy_record["canonical_internal_cbpf_sha256"],
        "outer_emitted_cbpf_sha256": policy_record["outer_policy"]["emitted_cbpf_sha256"],
        "outer_governed_digest_sha256": policy_record["outer_policy"]["governed_digest_sha256"],
        "internal_fprog_va_u64": None,
        "internal_program_va_u64": None,
        "syscall_numbers": {
            entry["name"]: entry["nr_u32"]
            for entry in policy_record["outer_policy"]["semantic_preimage"]["syscall_inventory"]
        },
    }
    if elf_record is not None:
        objects = elf_record["canonical_internal_filter_object"]
        reference["internal_fprog_va_u64"] = objects["fprog_va_u64"]
        reference["internal_program_va_u64"] = objects["program_va_u64"]
    return reference


def main(argv=None):
    parser = argparse.ArgumentParser(description="MT4-S3C observation adjudicator")
    parser.add_argument("--normalised-observation")
    parser.add_argument("--policy-record")
    parser.add_argument("--elf-record")
    parser.add_argument("--source-run-id", type=int)
    parser.add_argument("--source-run-attempt", type=int)
    parser.add_argument("--source-head-sha")
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--out")
    parser.add_argument(
        "--emit-case-set-digest",
        help="append S3C_CASE_SET_DIGEST=<digest> and exit; no observation is read",
    )
    args = parser.parse_args(argv)

    # The trusted observer must record the case-set digest into A3, and the workflow obtains it
    # through this bounded emit-only mode rather than through a shell command substitution.
    if args.emit_case_set_digest:
        with open(args.emit_case_set_digest, "a", encoding="ascii") as handle:
            handle.write("S3C_CASE_SET_DIGEST=" + observation_case_set_digest() + "\n")
        return 0
    for name in (
        "normalised_observation",
        "policy_record",
        "elf_record",
        "source_run_id",
        "source_run_attempt",
        "source_head_sha",
        "candidate_sha256",
        "out",
    ):
        if getattr(args, name) is None:
            _fail("ADJUDICATOR_ARGUMENT_MISSING", name)

    normalised = _rehydrate(_load_json(args.normalised_observation))
    policy_record = _load_json(args.policy_record)
    elf_record = _load_json(args.elf_record)
    identity = {
        "source_run_id": args.source_run_id,
        "source_run_attempt": args.source_run_attempt,
        "source_head_sha": args.source_head_sha,
        "candidate_binary_sha256": args.candidate_sha256,
    }
    if elf_record["candidate_binary_sha256"] != args.candidate_sha256:
        _fail("CANDIDATE_IDENTITY_MISMATCH", "elf record")

    record = adjudicate(normalised, policy_reference(policy_record, elf_record), identity)
    with open(args.out, "wb") as handle:
        handle.write(canonical_json(record))
    sys.stdout.write("MT4_S3C_OBSERVATION_CASE_SET_DIGEST=" + record["observation_case_set_digest_sha256"] + "\n")
    sys.stdout.write("MT4_S3C_ALL_CASES_CONFORM=" + str(record["all_cases_conform"]) + "\n")
    return 0 if record["all_cases_conform"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
