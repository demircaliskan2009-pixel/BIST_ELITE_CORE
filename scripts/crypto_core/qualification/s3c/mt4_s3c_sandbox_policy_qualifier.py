"""MT4-S3C P0 canonical sandbox policy qualifier.  Qualification infrastructure only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 12, 13, 14, 15, 16.
BUNDLE ENTRY 12 of the exact 16-entry qualification source bundle (V9 SECTION 8).

WHAT THIS MODULE IS.  It is the INDEPENDENT derivation of both canonical seccomp programs.  It
holds the frozen semantic policy table and the frozen instruction layout, derives the canonical
classic-BPF program from them, and requires the bytes the canonical probe (bundle entry 11) reports
for the COMPILED canonical source (bundle entry 10) to equal that derivation byte for byte.  Two
derivations, one from C macros and one from this table, must agree; a disagreement is
OUTER_FILTER_EQUIVALENCE_FAILED or INTERNAL_FILTER_EQUIVALENCE_FAILED and is never resolved in
favour of either side.

WHAT THIS MODULE IS NOT.  It confers no authority.  It executes no candidate byte, opens no
network connection, reads no clock, and admits nothing.  Every value it emits is DATA.

NO PLATFORM NUMERIC VALUE IS ASSERTED FROM MEMORY (V9 13.1).  Every audit architecture value, x32
marker, syscall number, prctl option, seccomp operation, seccomp return action, seccomp_data field
offset and classic-BPF opcode arrives from the probe, which read them from the pinned UAPI headers.
This module asserts only its OWN governed constants and its OWN frozen layout.

SELF-CONTAINED.  This module imports no repository module and contains no dynamic import
machinery, so V9 SECTION 28 rules R2, R5 and leg B hold by construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

# =================================================================================================
# FROZEN IDENTITIES (V9 12.1, 13.2, 16.2)
# =================================================================================================

PROBE_SCHEMA = "mt4-s3c-canonical-policy-probe.v1"

OUTER_POLICY_SCHEMA = "mt4-s3c-outer-containment-policy.v1"
OUTER_POLICY_DIGEST_DOMAIN = b"mt4-s3c-outer-containment-policy.v1\x00"
OUTER_POLICY_DOMAIN = "MT4_S3C_OUTER_CONTAINMENT_P0_LINUX_X86_64"

# V9-4 (P2) closure: the internal semantic policy identity and digest are GOVERNED here rather than
# left undefined or self-asserted.  They carry their own schema id and their own digest domain, so
# an internal policy record can never be mistaken for an outer one.
INTERNAL_POLICY_SCHEMA = "mt4-s3c-internal-containment-policy.v1"
INTERNAL_POLICY_DIGEST_DOMAIN = b"mt4-s3c-internal-containment-policy.v1\x00"
INTERNAL_POLICY_DOMAIN = "MT4_S3C_INTERNAL_CONTAINMENT_P0_LINUX_X86_64"

PROGRAM_REPRESENTATION_VERSION = "mt4-s3c-cbpf-canonical.v1"
CBPF_DIGEST_DOMAIN_PREFIX = b"mt4-s3c-cbpf-canonical.v1\x00"

INTERNAL_EQUIVALENCE_SCHEMA = "mt4-s3c-internal-filter-equivalence.v1"
INTERNAL_EQUIVALENCE_DIGEST_DOMAIN = b"mt4-s3c-internal-filter-equivalence.v1\x00"
INTERNAL_EQUIVALENCE_CONTRACT_ID = "MT4_S3C_INTERNAL_FILTER_EQUIVALENCE_V1"

SANDBOX_POLICY_SCHEMA = "mt4-s3c-sandbox-policy.v1"
SANDBOX_POLICY_DIGEST_DOMAIN = b"mt4-s3c-sandbox-policy.v1\x00"

PLATFORM_ID = "LINUX_X86_64"
AUDIT_ARCHITECTURE_NAME = "AUDIT_ARCH_X86_64"
ALTERNATE_ABI_POLICY = "REJECT_ALL_NON_MATCHING_AUDIT_ARCH_KILL_PROCESS"
X32_POLICY = "REJECT_X32_MARKER_UNMASKED_UNSTRIPPED_KILL_PROCESS"
DEFAULT_ACTION = "SECCOMP_RET_KILL_PROCESS"
SECCOMP_OPERATION = "SECCOMP_SET_MODE_FILTER"
UNUSED_ARGUMENT_POLICY = "UNUSED_ARGUMENT_WORDS_MUST_BE_ZERO"

# =================================================================================================
# GOVERNED PROJECT CONSTANTS.  These are this architecture's own values, not platform values.
# =================================================================================================

FD_REQUEST = 3
FD_RESPONSE = 4
REQUEST_FRAME_BYTES = 184
RESPONSE_FRAME_BYTES = 8
CLOSE_RANGE_FIRST_FD = 5
CLOSE_RANGE_MAX_FD = 4294967295
CLOSE_LEGAL_FDS = (0, 1, 2)
MAX_FILTER_INSTRUCTIONS = 512
ARG_WORDS = 6
SECCOMP_DATA_BYTES = 64

REASON_CLASSES = (
    "CANDIDATE_BOOTSTRAP",
    "CANDIDATE_RESPONSE",
    "CANDIDATE_VERIFY",
    "LAUNCH_TRANSITION",
    "PROCESS_EXIT",
)

# =================================================================================================
# FROZEN INSTRUCTION LAYOUT.  Mirrors bundle entry 10 exactly.
# =================================================================================================

LEN_PROLOGUE = 6
LEN_NR_MATCH = 3
LEN_ARG_EXACT = 6
LEN_ARG_RANGE = 8
LEN_ARG_POINTER = 0
LEN_ARG_UNCONSTRAINED_SCALAR = 0
LEN_ALLOW = 1
LEN_KILL = 1

FROZEN_OUTER_PROGRAM_LEN = 400
FROZEN_INTERNAL_PROGRAM_LEN = 113

# =================================================================================================
# ARGUMENT RULE MODEL (V9 14.2, extended by the V9-3 audit repair)
#
# V9 14.2 requires every rule to classify all six seccomp_data argument words into exactly one
# category and explicitly forbids a rule that leaves an index unclassified.  Its two literal shapes
# name three categories (exact, range, unconstrained pointer) plus zero-required.  V9 14.4 also
# requires exit_group argument 0 to be UNCONSTRAINED by the filter, which none of those four
# categories expresses.  The closure therefore adds exactly ONE further category,
# UNCONSTRAINED_SCALAR, so that the classification is total and exit_group's intentionally
# unconstrained status word is not incorrectly forced to zero.  No other category exists and no
# other category may be added without a new architecture revision.
#
# The V9-3 repair also requires ORDERED ALTERNATIVE TUPLES rather than a shape that cannot represent
# permitted alternatives.  A syscall therefore carries an ORDERED LIST of complete rules; close
# carries three (one per legal descriptor) and prctl carries two (one per permitted option).  An
# implicit option set is not representable.
# =================================================================================================

CAT_EXACT = "EXACT"
CAT_RANGE = "RANGE"
CAT_POINTER = "UNCONSTRAINED_POINTER"
CAT_SCALAR = "UNCONSTRAINED_SCALAR"
CAT_ZERO = "ZERO_REQUIRED"

ARGUMENT_CATEGORIES = (CAT_EXACT, CAT_RANGE, CAT_POINTER, CAT_SCALAR, CAT_ZERO)

_CATEGORY_INSTRUCTION_LENGTH = {
    CAT_EXACT: LEN_ARG_EXACT,
    CAT_RANGE: LEN_ARG_RANGE,
    CAT_POINTER: LEN_ARG_POINTER,
    CAT_SCALAR: LEN_ARG_UNCONSTRAINED_SCALAR,
    CAT_ZERO: LEN_ARG_EXACT,
}


class SandboxPolicyError(RuntimeError):
    """Any failure to prove a required policy property.  There is no partial success."""


def _fail(marker, detail=""):
    raise SandboxPolicyError(marker if not detail else marker + ": " + detail)


class ArgumentRule:
    """One complete alternative: an exact category for every one of the six argument words."""

    __slots__ = ("categories", "values", "minimums", "maximums")

    def __init__(self, spec):
        if len(spec) != ARG_WORDS:
            _fail("POLICY_RULE_INCOMPLETE", "a rule must classify exactly six argument words")
        categories = []
        values = []
        minimums = []
        maximums = []
        for category, low, high in spec:
            if category not in ARGUMENT_CATEGORIES:
                _fail("POLICY_RULE_CATEGORY_UNKNOWN", str(category))
            categories.append(category)
            values.append(low)
            minimums.append(low)
            maximums.append(high)
        self.categories = tuple(categories)
        self.values = tuple(values)
        self.minimums = tuple(minimums)
        self.maximums = tuple(maximums)

    def instruction_length(self):
        return sum(_CATEGORY_INSTRUCTION_LENGTH[category] for category in self.categories)

    def to_canonical(self):
        """Canonical JSON form.  Every index appears in exactly one classification list."""
        exact = {}
        pointers = []
        scalars = []
        zeros = []
        ranges = {}
        for index in range(ARG_WORDS):
            category = self.categories[index]
            if category == CAT_EXACT:
                exact[str(index)] = int(self.values[index])
            elif category == CAT_RANGE:
                ranges[str(index)] = {
                    "min_u64": int(self.minimums[index]),
                    "max_u64": int(self.maximums[index]),
                }
            elif category == CAT_POINTER:
                pointers.append(index)
            elif category == CAT_SCALAR:
                scalars.append(index)
            else:
                zeros.append(index)
        if ranges:
            kind = "ARG_EXACT_AND_ARG_RANGE_WITH_ZERO_TAIL"
        else:
            kind = "ARGS_EXACT_WITH_ZERO_TAIL"
        return {
            "kind": kind,
            "exact_u64": exact,
            "range_u64": ranges,
            "unconstrained_pointer_indices": pointers,
            "unconstrained_scalar_indices": scalars,
            "zero_indices": zeros,
        }


def _zero_tail(*classified):
    """Build a six-word specification, defaulting every unnamed index to ZERO_REQUIRED."""
    spec = [(CAT_ZERO, 0, 0)] * ARG_WORDS
    for index, category, low, high in classified:
        spec[index] = (category, low, high)
    return tuple(spec)


def _exact(index, value):
    return (index, CAT_EXACT, int(value), 0)


def _pointer(index):
    return (index, CAT_POINTER, 0, 0)


def _scalar(index):
    return (index, CAT_SCALAR, 0, 0)


def _range(index, low, high):
    return (index, CAT_RANGE, int(low), int(high))


def _read_rules(constants):
    del constants
    return (ArgumentRule(_zero_tail(_exact(0, FD_REQUEST), _pointer(1), _range(2, 1, REQUEST_FRAME_BYTES))),)


def _write_rules(constants):
    del constants
    return (ArgumentRule(_zero_tail(_exact(0, FD_RESPONSE), _pointer(1), _range(2, 1, RESPONSE_FRAME_BYTES))),)


def _close_rules(constants):
    del constants
    return tuple(ArgumentRule(_zero_tail(_exact(0, fd))) for fd in CLOSE_LEGAL_FDS)


def _execve_rules(constants):
    del constants
    return (ArgumentRule(_zero_tail(_pointer(0), _pointer(1), _pointer(2))),)


def _prctl_rules(constants):
    return (
        ArgumentRule(_zero_tail(_exact(0, constants["pr_set_dumpable_u32"]), _exact(1, 0))),
        ArgumentRule(_zero_tail(_exact(0, constants["pr_set_no_new_privs_u32"]), _exact(1, 1))),
    )


def _exit_group_rules(constants):
    del constants
    return (ArgumentRule(_zero_tail(_scalar(0))),)


def _seccomp_rules(constants):
    return (
        ArgumentRule(
            _zero_tail(
                _exact(0, constants["seccomp_set_mode_filter_u32"]),
                _exact(1, 0),
                _pointer(2),
            )
        ),
    )


def _close_range_rules(constants):
    del constants
    return (
        ArgumentRule(
            _zero_tail(
                _exact(0, CLOSE_RANGE_FIRST_FD),
                _exact(1, CLOSE_RANGE_MAX_FD),
                _exact(2, 0),
            )
        ),
    )


# The frozen dispatch order, which V9 13.1 STEP 3 requires to be ascending by syscall number.  The
# ascending property is PROVEN against the probe-reported numbers, never assumed from this order.
_OUTER_INVENTORY = (
    ("read", "CANDIDATE_VERIFY", _read_rules),
    ("write", "CANDIDATE_RESPONSE", _write_rules),
    ("close", "CANDIDATE_BOOTSTRAP", _close_rules),
    ("execve", "LAUNCH_TRANSITION", _execve_rules),
    ("prctl", "CANDIDATE_BOOTSTRAP", _prctl_rules),
    ("exit_group", "PROCESS_EXIT", _exit_group_rules),
    ("seccomp", "CANDIDATE_BOOTSTRAP", _seccomp_rules),
    ("close_range", "CANDIDATE_BOOTSTRAP", _close_range_rules),
)

_INTERNAL_INVENTORY = (
    ("read", "CANDIDATE_VERIFY", _read_rules),
    ("write", "CANDIDATE_RESPONSE", _write_rules),
    ("exit_group", "PROCESS_EXIT", _exit_group_rules),
)

OUTER_SYSCALL_NAMES = tuple(name for name, _reason, _rules in _OUTER_INVENTORY)
INTERNAL_SYSCALL_NAMES = tuple(name for name, _reason, _rules in _INTERNAL_INVENTORY)

# =================================================================================================
# PROBE INPUT VALIDATION.  Strict, typed, fail-closed.  A bool is never accepted as an int.
# =================================================================================================

_REQUIRED_UAPI_SCALARS = (
    "audit_architecture_value_u32",
    "x32_syscall_bit_u32",
    "seccomp_set_mode_filter_u32",
    "seccomp_ret_allow_u32",
    "seccomp_ret_kill_process_u32",
    "pr_set_dumpable_u32",
    "pr_set_no_new_privs_u32",
    "seccomp_data_offset_nr_u32",
    "seccomp_data_offset_arch_u32",
)

_REQUIRED_BPF_OPCODES = ("ld_w_abs", "jmp_jeq_k", "jmp_jge_k", "jmp_jgt_k", "jmp_ja", "ret_k")


def _require_int(value, marker, low=0, high=2**32 - 1):
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(marker, "value must be a JSON integer")
    if value < low or value > high:
        _fail(marker, "value out of range")
    return value


def _require_str(value, marker):
    if not isinstance(value, str):
        _fail(marker, "value must be a JSON string")
    return value


def validate_probe_constants(payload):
    """Validate the probe's UAPI block and return it as a flat, typed mapping."""
    if not isinstance(payload, dict):
        _fail("PROBE_PAYLOAD_MALFORMED")
    if _require_str(payload.get("schema"), "PROBE_SCHEMA_INVALID") != PROBE_SCHEMA:
        _fail("PROBE_SCHEMA_INVALID")
    if _require_str(payload.get("platform_id"), "PROBE_PLATFORM_INVALID") != PLATFORM_ID:
        _fail("PROBE_PLATFORM_INVALID")
    uapi = payload.get("uapi")
    if not isinstance(uapi, dict):
        _fail("PROBE_UAPI_MALFORMED")
    if _require_str(uapi.get("audit_architecture_name"), "PROBE_UAPI_MALFORMED") != AUDIT_ARCHITECTURE_NAME:
        _fail("PROBE_UAPI_MALFORMED", "audit architecture name")

    constants = {}
    for key in _REQUIRED_UAPI_SCALARS:
        if key not in uapi:
            _fail("PROBE_UAPI_FIELD_MISSING", key)
        constants[key] = _require_int(uapi[key], "PROBE_UAPI_FIELD_MALFORMED")

    for key in ("seccomp_data_offset_arg_lo_u32", "seccomp_data_offset_arg_hi_u32"):
        offsets = uapi.get(key)
        if not isinstance(offsets, list) or len(offsets) != ARG_WORDS:
            _fail("PROBE_UAPI_FIELD_MALFORMED", key)
        constants[key] = tuple(_require_int(item, "PROBE_UAPI_FIELD_MALFORMED") for item in offsets)

    numbers = uapi.get("syscall_nr_u32")
    if not isinstance(numbers, dict):
        _fail("PROBE_UAPI_FIELD_MALFORMED", "syscall_nr_u32")
    if sorted(numbers) != sorted(OUTER_SYSCALL_NAMES):
        _fail("PROBE_SYSCALL_INVENTORY_MISMATCH")
    constants["syscall_nr_u32"] = {
        name: _require_int(numbers[name], "PROBE_UAPI_FIELD_MALFORMED") for name in OUTER_SYSCALL_NAMES
    }

    opcodes = uapi.get("bpf_opcode_u16")
    if not isinstance(opcodes, dict):
        _fail("PROBE_UAPI_FIELD_MALFORMED", "bpf_opcode_u16")
    if sorted(opcodes) != sorted(_REQUIRED_BPF_OPCODES):
        _fail("PROBE_UAPI_FIELD_MALFORMED", "bpf_opcode_u16 inventory")
    constants["bpf_opcode_u16"] = {
        name: _require_int(opcodes[name], "PROBE_UAPI_FIELD_MALFORMED", 0, 2**16 - 1) for name in _REQUIRED_BPF_OPCODES
    }

    _validate_constant_relations(constants)
    return constants


def _validate_constant_relations(constants):
    """Prove the relations the canonical structure depends on, without asserting any value."""
    if constants["x32_syscall_bit_u32"] == 0:
        _fail("PROBE_X32_BIT_INVALID")
    if constants["seccomp_ret_allow_u32"] == constants["seccomp_ret_kill_process_u32"]:
        _fail("PROBE_SECCOMP_ACTIONS_NOT_DISJOINT")
    if constants["pr_set_dumpable_u32"] == constants["pr_set_no_new_privs_u32"]:
        _fail("PROBE_PRCTL_OPTIONS_NOT_DISJOINT")

    numbers = constants["syscall_nr_u32"]
    ordered = [numbers[name] for name in OUTER_SYSCALL_NAMES]
    if any(ordered[index] >= ordered[index + 1] for index in range(len(ordered) - 1)):
        _fail("PROBE_DISPATCH_ORDER_NOT_ASCENDING")
    if len(set(ordered)) != len(ordered):
        _fail("PROBE_SYSCALL_NUMBERS_NOT_UNIQUE")
    if any(number >= constants["x32_syscall_bit_u32"] for number in ordered):
        _fail("PROBE_SYSCALL_NUMBER_CARRIES_X32_MARKER")

    lo = constants["seccomp_data_offset_arg_lo_u32"]
    hi = constants["seccomp_data_offset_arg_hi_u32"]
    for index in range(ARG_WORDS):
        if hi[index] != lo[index] + 4:
            _fail("PROBE_ARG_WORD_OFFSETS_INVALID")
        if index and lo[index] != lo[index - 1] + 8:
            _fail("PROBE_ARG_WORD_OFFSETS_INVALID")
        if lo[index] + 8 > SECCOMP_DATA_BYTES:
            _fail("PROBE_ARG_WORD_OFFSETS_INVALID")
    if constants["seccomp_data_offset_nr_u32"] + 4 > SECCOMP_DATA_BYTES:
        _fail("PROBE_ARG_WORD_OFFSETS_INVALID")
    if constants["seccomp_data_offset_arch_u32"] + 4 > SECCOMP_DATA_BYTES:
        _fail("PROBE_ARG_WORD_OFFSETS_INVALID")

    opcodes = constants["bpf_opcode_u16"]
    if len(set(opcodes.values())) != len(_REQUIRED_BPF_OPCODES):
        _fail("PROBE_BPF_OPCODES_NOT_DISJOINT")


# =================================================================================================
# THE CANONICAL EMITTER.  A pure function of the semantic table plus the probe constants.
# =================================================================================================


class Instruction:
    """One classic-BPF instruction: u16 code, u8 jt, u8 jf, u32 k."""

    __slots__ = ("code", "jt", "jf", "k")

    def __init__(self, code, k=0, jt=0, jf=0):
        self.code = code & 0xFFFF
        self.k = k & 0xFFFFFFFF
        self.jt = jt & 0xFF
        self.jf = jf & 0xFF

    def pack(self):
        return self.code.to_bytes(2, "little") + bytes((self.jt, self.jf)) + self.k.to_bytes(4, "little")

    def as_dict(self):
        return {"code_u16": self.code, "jt_u8": self.jt, "jf_u8": self.jf, "k_u32": self.k}


def _emit_argument_check(out, constants, target, index, category, low, high):
    """Emit one argument-word check.  The high word is ALWAYS compared before the low word."""
    opcodes = constants["bpf_opcode_u16"]
    if category in (CAT_POINTER, CAT_SCALAR):
        return
    lo_offset = constants["seccomp_data_offset_arg_lo_u32"][index]
    hi_offset = constants["seccomp_data_offset_arg_hi_u32"][index]
    out.append(Instruction(opcodes["ld_w_abs"], hi_offset))
    out.append(Instruction(opcodes["jmp_jeq_k"], 0, 1, 0))
    out.append(("JA", target))
    out.append(Instruction(opcodes["ld_w_abs"], lo_offset))
    if category == CAT_RANGE:
        out.append(Instruction(opcodes["jmp_jge_k"], low, 1, 0))
        out.append(("JA", target))
        out.append(Instruction(opcodes["jmp_jgt_k"], high, 0, 1))
        out.append(("JA", target))
    else:
        value = 0 if category == CAT_ZERO else low
        out.append(Instruction(opcodes["jmp_jeq_k"], value, 1, 0))
        out.append(("JA", target))


def _emit_rule(out, constants, target, rule):
    for index in range(ARG_WORDS):
        _emit_argument_check(
            out,
            constants,
            target,
            index,
            rule.categories[index],
            rule.minimums[index],
            rule.maximums[index],
        )


def derive_program(constants, inventory):
    """Derive the canonical classic-BPF program for one inventory.

    Placeholders of the form ("JA", <symbolic target>) are resolved after the full layout is known,
    so no jump offset is ever guessed and no distance can overflow an 8-bit conditional field.
    """
    opcodes = constants["bpf_opcode_u16"]
    numbers = constants["syscall_nr_u32"]

    rules_by_name = {}
    for name, _reason, factory in inventory:
        rules = factory(constants)
        if not rules:
            _fail("POLICY_RULE_MISSING", name)
        rules_by_name[name] = rules

    out = []
    # STEP 1 arch check first, before any syscall-number policy evaluation.
    out.append(Instruction(opcodes["ld_w_abs"], constants["seccomp_data_offset_arch_u32"]))
    out.append(Instruction(opcodes["jmp_jeq_k"], constants["audit_architecture_value_u32"], 1, 0))
    out.append(("JA", "KILL"))
    # STEP 2 x32 rejection with the marker intact: not stripped, not masked, not normalised.
    out.append(Instruction(opcodes["ld_w_abs"], constants["seccomp_data_offset_nr_u32"]))
    out.append(Instruction(opcodes["jmp_jge_k"], constants["x32_syscall_bit_u32"], 0, 1))
    out.append(("JA", "KILL"))
    if len(out) != LEN_PROLOGUE:
        _fail("POLICY_LAYOUT_DRIFT", "prologue")

    # STEP 3 syscall dispatch in the frozen ascending order.
    #
    # A syscall-number MISMATCH falls through to the NEXT dispatch entry, never to the kill block:
    # only one entry can ever match a given nr, so the chain terminates at the STEP 4 default.  An
    # ARGUMENT-rule failure inside a matched entry jumps to the next ALTERNATIVE TUPLE of that same
    # entry when one exists, and to the kill block when none does.
    for position_of_entry, (name, _reason, _factory) in enumerate(inventory):
        rules = rules_by_name[name]
        last_entry = position_of_entry + 1 == len(inventory)
        next_entry = "KILL" if last_entry else (inventory[position_of_entry + 1][0], "ENTRY")
        out.append((name, "ENTRY"))
        out.append(Instruction(opcodes["ld_w_abs"], constants["seccomp_data_offset_nr_u32"]))
        out.append(Instruction(opcodes["jmp_jeq_k"], numbers[name], 1, 0))
        out.append(("JA", next_entry))
        for position, rule in enumerate(rules):
            last = position + 1 == len(rules)
            target = "KILL" if last else (name, position + 1)
            out.append((name, position))
            _emit_rule(out, constants, target, rule)
            out.append(Instruction(opcodes["ret_k"], constants["seccomp_ret_allow_u32"]))

    # STEP 4 default action.  This single instruction is also the shared kill block.
    out.append("KILL")
    out.append(Instruction(opcodes["ret_k"], constants["seccomp_ret_kill_process_u32"]))

    return _resolve_labels(out, opcodes["jmp_ja"])


def _resolve_labels(items, ja_code):
    """Assign absolute indices to labels, then materialise every unconditional jump."""
    labels = {}
    index = 0
    for item in items:
        if isinstance(item, Instruction):
            index += 1
        elif isinstance(item, tuple) and item and item[0] == "JA":
            index += 1
        else:
            if item in labels:
                _fail("POLICY_LAYOUT_DRIFT", "duplicate label")
            labels[item] = index
    total = index

    program = []
    index = 0
    for item in items:
        if isinstance(item, Instruction):
            program.append(item)
            index += 1
        elif isinstance(item, tuple) and item and item[0] == "JA":
            target = item[1]
            if target not in labels:
                _fail("POLICY_LAYOUT_DRIFT", "unresolved jump target")
            distance = labels[target] - index - 1
            if distance < 0:
                _fail("POLICY_LAYOUT_DRIFT", "backward jump is not representable")
            program.append(Instruction(ja_code, distance))
            index += 1
    if len(program) != total:
        _fail("POLICY_LAYOUT_DRIFT", "instruction count mismatch")
    return program


def program_bytes(program):
    return b"".join(instruction.pack() for instruction in program)


def cbpf_digest(program):
    """CBPF_DIGEST over the canonical representation (V9 13.2)."""
    count = len(program)
    if count < 1 or count > MAX_FILTER_INSTRUCTIONS:
        _fail("POLICY_PROGRAM_LENGTH_INVALID", str(count))
    preimage = CBPF_DIGEST_DOMAIN_PREFIX + count.to_bytes(4, "little") + program_bytes(program)
    return hashlib.sha256(preimage).hexdigest()


# =================================================================================================
# A PURE CLASSIC-BPF INTERPRETER.
#
# The canonical probe proves the compiled source has the intended BYTES.  This interpreter proves
# the derived program has the intended SEMANTICS, offline, with no kernel and no native build, so
# every argument-tuple mutant in the permanent test matrix is a real causal test rather than a
# claim.  It implements only the instruction forms this architecture emits; anything else is a
# hard failure rather than a silently tolerated no-op.
# =================================================================================================


def build_seccomp_data(constants, arch, nr, args):
    if len(args) != ARG_WORDS:
        _fail("SECCOMP_DATA_ARGS_INVALID")
    buffer = bytearray(SECCOMP_DATA_BYTES)
    offset_nr = constants["seccomp_data_offset_nr_u32"]
    offset_arch = constants["seccomp_data_offset_arch_u32"]
    buffer[offset_nr : offset_nr + 4] = (nr & 0xFFFFFFFF).to_bytes(4, "little")
    buffer[offset_arch : offset_arch + 4] = (arch & 0xFFFFFFFF).to_bytes(4, "little")
    for index in range(ARG_WORDS):
        low = constants["seccomp_data_offset_arg_lo_u32"][index]
        buffer[low : low + 8] = (args[index] & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")
    return bytes(buffer)


def evaluate(constants, program, data):
    """Run the program over one seccomp_data image and return the resulting action word."""
    opcodes = constants["bpf_opcode_u16"]
    accumulator = 0
    index = 0
    steps = 0
    limit = 4 * MAX_FILTER_INSTRUCTIONS
    while True:
        steps += 1
        if steps > limit:
            _fail("POLICY_PROGRAM_DID_NOT_TERMINATE")
        if index < 0 or index >= len(program):
            _fail("POLICY_PROGRAM_JUMPED_OUT_OF_RANGE")
        instruction = program[index]
        code = instruction.code
        if code == opcodes["ret_k"]:
            return instruction.k
        if code == opcodes["ld_w_abs"]:
            offset = instruction.k
            if offset + 4 > len(data):
                _fail("POLICY_PROGRAM_READ_OUT_OF_RANGE")
            accumulator = int.from_bytes(data[offset : offset + 4], "little")
            index += 1
            continue
        if code == opcodes["jmp_ja"]:
            index += 1 + instruction.k
            continue
        if code == opcodes["jmp_jeq_k"]:
            taken = accumulator == instruction.k
        elif code == opcodes["jmp_jge_k"]:
            taken = accumulator >= instruction.k
        elif code == opcodes["jmp_jgt_k"]:
            taken = accumulator > instruction.k
        else:
            _fail("POLICY_PROGRAM_OPCODE_UNSUPPORTED", str(code))
        index += 1 + (instruction.jt if taken else instruction.jf)


# =================================================================================================
# CANONICAL POLICY PREIMAGES AND DIGESTS (V9 12.1, 12.2, 12.4)
# =================================================================================================


def _inventory_preimage(constants, inventory):
    numbers = constants["syscall_nr_u32"]
    entries = []
    for name, reason, factory in inventory:
        if reason not in REASON_CLASSES:
            _fail("POLICY_REASON_CLASS_UNKNOWN", reason)
        rules = factory(constants)
        entries.append(
            {
                "name": name,
                "nr_u32": numbers[name],
                "reason_class": reason,
                "argument_rule_count": len(rules),
                "argument_rules": [rule.to_canonical() for rule in rules],
            }
        )
    entries.sort(key=lambda entry: entry["nr_u32"])
    return entries


def _semantic_preimage(constants, inventory, schema, policy_domain):
    entries = _inventory_preimage(constants, inventory)
    reason_classes = sorted({entry["reason_class"] for entry in entries})
    return {
        "schema": schema,
        "policy_domain": policy_domain,
        "audit_architecture_name": AUDIT_ARCHITECTURE_NAME,
        "audit_architecture_value_u32": constants["audit_architecture_value_u32"],
        "alternate_abi_policy": ALTERNATE_ABI_POLICY,
        "x32_policy": X32_POLICY,
        "x32_syscall_bit_u32": constants["x32_syscall_bit_u32"],
        "default_action": DEFAULT_ACTION,
        "seccomp_operation": SECCOMP_OPERATION,
        "seccomp_flags_u32": 0,
        "seccomp_flags_names": [],
        "unused_argument_policy": UNUSED_ARGUMENT_POLICY,
        "reason_classes": reason_classes,
        "syscall_inventory_count": len(entries),
        "syscall_inventory": entries,
        "program_representation_version": PROGRAM_REPRESENTATION_VERSION,
    }


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


def domain_digest(domain, payload):
    return hashlib.sha256(domain + canonical_json(payload)).hexdigest()


def build_policy_record(constants, inventory, schema, digest_domain, policy_domain, program):
    """Build the semantic and governed digests for one policy (V9 12.4 separation)."""
    semantic = _semantic_preimage(constants, inventory, schema, policy_domain)
    semantic_digest = domain_digest(digest_domain, semantic)

    count = len(program)
    if count < 1 or count > MAX_FILTER_INSTRUCTIONS:
        _fail("POLICY_PROGRAM_LENGTH_INVALID", str(count))
    governed = dict(semantic)
    governed["emitted_cbpf_instruction_count"] = count
    governed["emitted_cbpf_sha256"] = cbpf_digest(program)
    governed_digest = domain_digest(digest_domain, governed)

    if semantic_digest == governed_digest:
        _fail("POLICY_DIGEST_SEPARATION_LOST")
    return {
        "schema": schema,
        "policy_domain": policy_domain,
        "semantic_preimage": semantic,
        "semantic_digest_sha256": semantic_digest,
        "governed_preimage": governed,
        "governed_digest_sha256": governed_digest,
        "emitted_cbpf_instruction_count": count,
        "emitted_cbpf_sha256": governed["emitted_cbpf_sha256"],
    }


# =================================================================================================
# INTERNAL FILTER EQUIVALENCE DIGEST (V9 SECTION 16, the V9-4 repair)
#
# ONE governed schema, ONE domain, ONE ordering, ONE encoding.  The adjudicator (bundle entry 5) and
# the trusted Stage-C gate recompute this digest from the SAME frozen field set using the SAME
# canonical encoding; a permanent test proves all three implementations agree byte for byte on the
# same record.  Independent recomputation at the trust boundary is the point: receipt equality alone
# is explicitly insufficient (V9 16.4).
# =================================================================================================

INTERNAL_EQUIVALENCE_FIELDS = (
    "schema",
    "canonical_internal_policy_id",
    "canonical_internal_policy_sha256",
    "program_representation_version",
    "canonical_internal_cbpf_instruction_count",
    "canonical_internal_cbpf_sha256",
    "captured_internal_cbpf_sha256",
    "captured_internal_uargs_va_u64",
    "captured_internal_len_u32",
    "install_exit_return_i32",
    "baseline_supervisor_seccomp",
    "baseline_supervisor_filters",
    "baseline_child_seccomp",
    "baseline_child_filters",
    "pre_install_filters",
    "post_install_filters",
    "post_install_seccomp_mode",
    "revalidated_filters",
    "dump_leg_availability",
    "dump_leg_index0_sha256",
    "dump_leg_index1_sha256",
    "dump_leg_terminates_at_index",
    "case_id",
    "source_run_id",
    "source_run_attempt",
    "source_head_sha",
    "candidate_binary_sha256",
)

_EQUIVALENCE_HEX_FIELDS = (
    "canonical_internal_policy_sha256",
    "canonical_internal_cbpf_sha256",
    "captured_internal_cbpf_sha256",
    "candidate_binary_sha256",
)

_EQUIVALENCE_REQUIRED_VALUES = {
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

DUMP_AVAILABLE = "AVAILABLE"
DUMP_UNAVAILABLE = "UNAVAILABLE_IN_PINNED_ENVIRONMENT"


def _is_hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_internal_equivalence_record(record):
    """Validate BEFORE digesting.  A record that violates a constraint is never digested."""
    if not isinstance(record, dict):
        _fail("INTERNAL_FILTER_EQUIVALENCE_RECORD_MALFORMED")
    if sorted(record) != sorted(INTERNAL_EQUIVALENCE_FIELDS):
        _fail("INTERNAL_FILTER_EQUIVALENCE_FIELD_SET_INVALID")
    if record["schema"] != INTERNAL_EQUIVALENCE_SCHEMA:
        _fail("INTERNAL_FILTER_EQUIVALENCE_SCHEMA_INVALID")
    if record["program_representation_version"] != PROGRAM_REPRESENTATION_VERSION:
        _fail("INTERNAL_FILTER_EQUIVALENCE_REPRESENTATION_INVALID")
    for field in _EQUIVALENCE_HEX_FIELDS:
        if not _is_hex64(record[field]):
            _fail("INTERNAL_FILTER_EQUIVALENCE_HEX_INVALID", field)
    for field, expected in _EQUIVALENCE_REQUIRED_VALUES.items():
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            _fail("INTERNAL_FILTER_EQUIVALENCE_CONSTRAINT_VIOLATED", field)
    count = record["canonical_internal_cbpf_instruction_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > MAX_FILTER_INSTRUCTIONS:
        _fail("INTERNAL_FILTER_EQUIVALENCE_COUNT_INVALID")
    for field in ("captured_internal_len_u32", "source_run_id", "source_run_attempt"):
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail("INTERNAL_FILTER_EQUIVALENCE_INT_INVALID", field)
    va = record["captured_internal_uargs_va_u64"]
    if isinstance(va, bool) or not isinstance(va, int) or va < 0 or va >= 2**64:
        _fail("INTERNAL_FILTER_EQUIVALENCE_INT_INVALID", "captured_internal_uargs_va_u64")
    for field in ("canonical_internal_policy_id", "case_id", "source_head_sha"):
        if not isinstance(record[field], str) or not record[field]:
            _fail("INTERNAL_FILTER_EQUIVALENCE_STR_INVALID", field)

    availability = record["dump_leg_availability"]
    if availability == DUMP_AVAILABLE:
        if not _is_hex64(record["dump_leg_index0_sha256"]) or not _is_hex64(record["dump_leg_index1_sha256"]):
            _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "claims AVAILABLE with empty dump fields")
        if record["dump_leg_terminates_at_index"] != 2:
            _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "terminating index")
    elif availability == DUMP_UNAVAILABLE:
        if record["dump_leg_index0_sha256"] != "" or record["dump_leg_index1_sha256"] != "":
            _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "unavailable dump carries digests")
        if record["dump_leg_terminates_at_index"] != -1:
            _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "terminating index")
    else:
        _fail("INTERNAL_FILTER_EQUIVALENCE_DUMP_INVALID", "availability enum")

    # Equivalence itself: the captured program must equal the canonical reference.
    if record["captured_internal_cbpf_sha256"] != record["canonical_internal_cbpf_sha256"]:
        _fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured program differs from canonical")
    if record["captured_internal_len_u32"] != record["canonical_internal_cbpf_instruction_count"]:
        _fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured length differs from canonical")
    return record


def internal_equivalence_digest(record):
    """MT4_S3C_INTERNAL_FILTER_EQUIVALENCE_V1 digest.  Validation always runs first."""
    validate_internal_equivalence_record(record)
    return domain_digest(INTERNAL_EQUIVALENCE_DIGEST_DOMAIN, record)


# =================================================================================================
# QUALIFICATION ENTRY POINT
# =================================================================================================


def _require_program(payload, key, expected_length):
    programs = payload.get("programs")
    if not isinstance(programs, dict):
        _fail("PROBE_PROGRAMS_MALFORMED")
    block = programs.get(key)
    if not isinstance(block, dict):
        _fail("PROBE_PROGRAMS_MALFORMED", key)
    count = _require_int(block.get("instruction_count"), "PROBE_PROGRAM_COUNT_INVALID", 1, MAX_FILTER_INSTRUCTIONS)
    raw = _require_str(block.get("instruction_bytes_hex"), "PROBE_PROGRAM_BYTES_INVALID")
    if len(raw) != count * 16 or any(character not in "0123456789abcdef" for character in raw):
        _fail("PROBE_PROGRAM_BYTES_INVALID", key)
    if count != expected_length:
        _fail("PROBE_PROGRAM_LENGTH_UNEXPECTED", key)
    return bytes.fromhex(raw)


def qualify(payload):
    """Qualify the compiled canonical policy source against the independent derivation."""
    constants = validate_probe_constants(payload)

    outer_program = derive_program(constants, _OUTER_INVENTORY)
    internal_program = derive_program(constants, _INTERNAL_INVENTORY)
    if len(outer_program) != FROZEN_OUTER_PROGRAM_LEN:
        _fail("POLICY_LAYOUT_DRIFT", "outer program length")
    if len(internal_program) != FROZEN_INTERNAL_PROGRAM_LEN:
        _fail("POLICY_LAYOUT_DRIFT", "internal program length")

    compiled_outer = _require_program(payload, "outer", FROZEN_OUTER_PROGRAM_LEN)
    compiled_internal = _require_program(payload, "internal", FROZEN_INTERNAL_PROGRAM_LEN)
    if program_bytes(outer_program) != compiled_outer:
        _fail("OUTER_FILTER_EQUIVALENCE_FAILED", "compiled source differs from the canonical derivation")
    if program_bytes(internal_program) != compiled_internal:
        _fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "compiled source differs from the canonical derivation")

    outer_record = build_policy_record(
        constants,
        _OUTER_INVENTORY,
        OUTER_POLICY_SCHEMA,
        OUTER_POLICY_DIGEST_DOMAIN,
        OUTER_POLICY_DOMAIN,
        outer_program,
    )
    internal_record = build_policy_record(
        constants,
        _INTERNAL_INVENTORY,
        INTERNAL_POLICY_SCHEMA,
        INTERNAL_POLICY_DIGEST_DOMAIN,
        INTERNAL_POLICY_DOMAIN,
        internal_program,
    )

    mutants = run_mutant_matrix(constants, outer_program, internal_program)

    record = {
        "schema": SANDBOX_POLICY_SCHEMA,
        "platform_id": PLATFORM_ID,
        "internal_filter_equivalence_contract_id": INTERNAL_EQUIVALENCE_CONTRACT_ID,
        "canonical_internal_policy_id": INTERNAL_POLICY_DOMAIN,
        "canonical_internal_policy_sha256": internal_record["semantic_digest_sha256"],
        "canonical_internal_cbpf_instruction_count": internal_record["emitted_cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": internal_record["emitted_cbpf_sha256"],
        "outer_policy": outer_record,
        "internal_policy": internal_record,
        "mutant_matrix": mutants,
    }
    record["sandbox_policy_digest_sha256"] = domain_digest(SANDBOX_POLICY_DIGEST_DOMAIN, record)
    return record


# =================================================================================================
# MUTANT MATRIX.  Each entry is a causal test with a named V9 permanent-test identifier.
# =================================================================================================


def _allow(constants):
    return constants["seccomp_ret_allow_u32"]


def _kill(constants):
    return constants["seccomp_ret_kill_process_u32"]


def _mutant_vectors(constants):
    arch = constants["audit_architecture_value_u32"]
    numbers = constants["syscall_nr_u32"]
    x32 = constants["x32_syscall_bit_u32"]
    dumpable = constants["pr_set_dumpable_u32"]
    nnp = constants["pr_set_no_new_privs_u32"]
    set_mode = constants["seccomp_set_mode_filter_u32"]
    pointer = 0x7FFF0000ABCD1234

    vectors = [
        ("PT-111", "non x86_64 audit architecture", arch ^ 0x1, numbers["read"], (3, pointer, 184, 0, 0, 0), False),
        ("PT-112", "x32 calling convention", arch, numbers["read"] | x32, (3, pointer, 184, 0, 0, 0), False),
        ("PT-121", "prctl(PR_SET_DUMPABLE, 1)", arch, numbers["prctl"], (dumpable, 1, 0, 0, 0, 0), False),
        ("PT-122", "prctl(PR_SET_NO_NEW_PRIVS, 0)", arch, numbers["prctl"], (nnp, 0, 0, 0, 0, 0), False),
        ("PT-123", "prctl dumpable nonzero arg2", arch, numbers["prctl"], (dumpable, 0, 1, 0, 0, 0), False),
        ("PT-123b", "prctl dumpable nonzero arg3", arch, numbers["prctl"], (dumpable, 0, 0, 1, 0, 0), False),
        ("PT-123c", "prctl dumpable nonzero arg4", arch, numbers["prctl"], (dumpable, 0, 0, 0, 1, 0), False),
        ("PT-123d", "prctl dumpable nonzero arg5", arch, numbers["prctl"], (dumpable, 0, 0, 0, 0, 1), False),
        ("PT-123e", "prctl no_new_privs nonzero arg2", arch, numbers["prctl"], (nnp, 1, 1, 0, 0, 0), False),
        ("PT-125", "unlisted prctl option", arch, numbers["prctl"], (dumpable ^ nnp ^ 0x5A5A, 0, 0, 0, 0, 0), False),
        ("PT-131", "execve nonzero zero_index", arch, numbers["execve"], (pointer, pointer, pointer, 1, 0, 0), False),
        ("PT-132", "close nonzero zero_index", arch, numbers["close"], (1, 0, 0, 0, 1, 0), False),
        (
            "PT-133",
            "close_range nonzero zero_index",
            arch,
            numbers["close_range"],
            (5, CLOSE_RANGE_MAX_FD, 0, 0, 0, 7),
            False,
        ),
        ("PT-134", "seccomp nonzero zero_index", arch, numbers["seccomp"], (set_mode, 0, pointer, 0, 3, 0), False),
        ("PT-135", "read nonzero zero_index", arch, numbers["read"], (3, pointer, 184, 0, 0, 9), False),
        ("PT-136", "write nonzero zero_index", arch, numbers["write"], (4, pointer, 8, 2, 0, 0), False),
        ("PT-137", "exit_group nonzero zero_index", arch, numbers["exit_group"], (0, 4, 0, 0, 0, 0), False),
        ("PT-504", "clone-like syscall outside the allowlist", arch, _unlisted_nr(numbers, x32), (0,) * 6, False),
        (
            "PT-120a",
            "read on a descriptor outside the fixed table",
            arch,
            numbers["read"],
            (5, pointer, 8, 0, 0, 0),
            False,
        ),
        ("PT-120b", "read length above the request frame", arch, numbers["read"], (3, pointer, 185, 0, 0, 0), False),
        ("PT-120c", "read length of zero", arch, numbers["read"], (3, pointer, 0, 0, 0, 0), False),
        ("PT-120d", "write length above the response frame", arch, numbers["write"], (4, pointer, 9, 0, 0, 0), False),
        (
            "PT-126",
            "argument high word set while the low word matches",
            arch,
            numbers["read"],
            (3 + (1 << 32), pointer, 184, 0, 0, 0),
            False,
        ),
        ("PT-509", "close on a descriptor outside the legal set", arch, numbers["close"], (3, 0, 0, 0, 0, 0), False),
        ("POS-read", "the exact permitted read", arch, numbers["read"], (3, pointer, 184, 0, 0, 0), True),
        ("POS-read-min", "the bounded trailing probe", arch, numbers["read"], (3, pointer, 1, 0, 0, 0), True),
        ("POS-write", "the exact permitted response write", arch, numbers["write"], (4, pointer, 8, 0, 0, 0), True),
        ("POS-close0", "close(0)", arch, numbers["close"], (0, 0, 0, 0, 0, 0), True),
        ("POS-close1", "close(1)", arch, numbers["close"], (1, 0, 0, 0, 0, 0), True),
        ("POS-close2", "close(2)", arch, numbers["close"], (2, 0, 0, 0, 0, 0), True),
        (
            "POS-close-range",
            "close_range(5, UINT32_MAX, 0)",
            arch,
            numbers["close_range"],
            (5, CLOSE_RANGE_MAX_FD, 0, 0, 0, 0),
            True,
        ),
        (
            "POS-execve",
            "the single trusted launch transition",
            arch,
            numbers["execve"],
            (pointer, pointer, pointer, 0, 0, 0),
            True,
        ),
        ("POS-prctl-dumpable", "prctl(PR_SET_DUMPABLE, 0)", arch, numbers["prctl"], (dumpable, 0, 0, 0, 0, 0), True),
        ("POS-prctl-nnp", "prctl(PR_SET_NO_NEW_PRIVS, 1)", arch, numbers["prctl"], (nnp, 1, 0, 0, 0, 0), True),
        (
            "POS-seccomp",
            "the single internal filter install",
            arch,
            numbers["seccomp"],
            (set_mode, 0, pointer, 0, 0, 0),
            True,
        ),
        ("POS-exit-0", "exit_group(0)", arch, numbers["exit_group"], (0, 0, 0, 0, 0, 0), True),
        ("POS-exit-64", "exit_group(64)", arch, numbers["exit_group"], (64, 0, 0, 0, 0, 0), True),
        ("POS-exit-65", "exit_group(65)", arch, numbers["exit_group"], (65, 0, 0, 0, 0, 0), True),
    ]
    return vectors


def _unlisted_nr(numbers, x32_bit):
    """Pick a syscall number that is not in the allowlist and carries no x32 marker."""
    taken = set(numbers.values())
    for candidate in range(0, min(x32_bit, 4096)):
        if candidate not in taken:
            return candidate
    _fail("POLICY_MUTANT_VECTOR_UNAVAILABLE")
    return 0


# The internal filter allows strictly fewer syscalls, so these outer-permitted calls must die there.
_INTERNAL_ONLY_KILLS = (
    "POS-close0",
    "POS-close1",
    "POS-close2",
    "POS-close-range",
    "POS-execve",
    "POS-prctl-dumpable",
    "POS-prctl-nnp",
    "POS-seccomp",
)


def run_mutant_matrix(constants, outer_program, internal_program):
    """Evaluate every governed vector against both programs.  Any disagreement fails closed."""
    allow = _allow(constants)
    kill = _kill(constants)
    results = []
    for test_id, description, arch, nr, args, expect_allow in _mutant_vectors(constants):
        data = build_seccomp_data(constants, arch, nr, args)
        outer = evaluate(constants, outer_program, data)
        internal = evaluate(constants, internal_program, data)
        if outer not in (allow, kill) or internal not in (allow, kill):
            _fail("POLICY_PROGRAM_ACTION_UNKNOWN", test_id)
        expected_outer = allow if expect_allow else kill
        if outer != expected_outer:
            _fail("POLICY_MUTANT_NOT_KILLED" if not expect_allow else "POLICY_POSITIVE_NOT_ALLOWED", test_id)
        expected_internal = allow if (expect_allow and test_id not in _INTERNAL_ONLY_KILLS) else kill
        if internal != expected_internal:
            _fail("POLICY_INTERNAL_INTERSECTION_VIOLATED", test_id)
        results.append(
            {
                "test_id": test_id,
                "description": description,
                "outer_action": "ALLOW" if outer == allow else "KILL_PROCESS",
                "internal_action": "ALLOW" if internal == allow else "KILL_PROCESS",
            }
        )
    results.sort(key=lambda item: item["test_id"])
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="MT4-S3C canonical sandbox policy qualifier")
    parser.add_argument("--probe-json", required=True, help="absolute path to the canonical probe output")
    parser.add_argument("--out", required=True, help="absolute path of the policy record to write")
    parser.add_argument(
        "--emit-env",
        help="append the governed policy values as NAME=value lines, so the workflow needs no "
        "command substitution to move them between steps (V9 SECTION 28.3 leg A)",
    )
    args = parser.parse_args(argv)

    with open(args.probe_json, "rb") as handle:
        payload = json.loads(handle.read().decode("utf-8"))
    record = qualify(payload)
    with open(args.out, "wb") as handle:
        handle.write(canonical_json(record))
    sys.stdout.write("MT4_S3C_SANDBOX_POLICY_DIGEST=" + record["sandbox_policy_digest_sha256"] + "\n")
    sys.stdout.write("MT4_S3C_OUTER_POLICY_DIGEST=" + record["outer_policy"]["governed_digest_sha256"] + "\n")
    sys.stdout.write("MT4_S3C_INTERNAL_POLICY_DIGEST=" + record["internal_policy"]["governed_digest_sha256"] + "\n")
    if args.emit_env:
        with open(args.emit_env, "a", encoding="ascii") as handle:
            handle.write("S3C_POLICY_INTERNAL_ID=" + record["canonical_internal_policy_id"] + "\n")
            handle.write("S3C_POLICY_INTERNAL_SHA256=" + record["canonical_internal_policy_sha256"] + "\n")
            handle.write("S3C_POLICY_INTERNAL_COUNT=" + str(record["canonical_internal_cbpf_instruction_count"]) + "\n")
            handle.write("S3C_POLICY_INTERNAL_CBPF=" + record["canonical_internal_cbpf_sha256"] + "\n")
            handle.write("S3C_POLICY_OUTER_DIGEST=" + record["outer_policy"]["governed_digest_sha256"] + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
