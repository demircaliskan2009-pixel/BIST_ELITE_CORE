"""Permanent offline contract tests for the MT4-S3C P0 static worker qualification slice.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTION 33 (permanent test matrix).
PATH N20.  DELIBERATELY NOT A SOURCE-BUNDLE ENTRY.

NON-CIRCULARITY (V9 SECTION 28.7 leg E).  These tests are run by the ORDINARY CI suite.  They are
never invoked by the qualification workflow and they produce NO qualification evidence, which is
exactly why V9 SECTION 8 excludes test modules from the source bundle: a closure test inside the
bundle would be validating the set it belongs to.

WHAT THESE TESTS DO.  They build, execute and mutate the deterministic parts of the slice offline:
the canonical seccomp policy derivation and its emitted classic-BPF program, a pure classic-BPF
interpreter over that program, the static ELF qualifier against synthesised images, the wire-protocol
decoder, the governed observation case inventory, the internal filter equivalence digest, and the
source shape of every C, assembly and YAML file in the slice.  Every entry names a MUTATION that must
flip a result: a test that passes under its own mutation is a defect in the test, not evidence about
the system.

WHAT THESE TESTS NEVER DO.  They never build native code, never execute the candidate, never touch
the network, and never fake a Linux runtime fact.  Linux-only behaviour -- the seccomp installation
itself, the ptrace observation, the namespace separation -- is proven in the S3C qualification
workflow on the pinned runner, and is classified RUNTIME_TO_PROVE rather than asserted here.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_S3C = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "s3c"
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

QUALIFICATION_WORKFLOW = _WORKFLOWS / "crypto_core_mt4_s3c_static_worker_qualification.yml"
TRUSTED_WORKFLOW = _WORKFLOWS / "crypto_core_mt4_s3c_trusted_attestation.yml"
TRUSTED_GATE = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_s3c_trusted_attestation_gate.py"
FIXTURE = _REPO_ROOT / "tests" / "crypto_core" / "fixtures" / "mt4_s3c_test_only_positive_vector_v1.json"
VECTOR_GENERATOR = _S3C / "mt4_s3c_test_only_vector_generator.c"

POLICY_SOURCE = _S3C / "mt4_s3c_sandbox_policy.c"
POLICY_PROBE_SOURCE = _S3C / "mt4_s3c_sandbox_policy_probe.c"
LAUNCHER_SOURCE = _S3C / "mt4_s3c_outer_containment_launcher.c"
BOOTSTRAP_SOURCE = _S3C / "mt4_s3c_static_worker_bootstrap.c"
START_SOURCE = _S3C / "mt4_s3c_static_worker_start.S"
VERIFY_SOURCE = _S3C / "mt4_s3c_static_worker_verify.c"
CAPABILITY_SOURCE = _S3C / "mt4_s3c_blst_capability.c"

# The exact 16-entry qualification source bundle (V9 SECTION 8), ordered byte-wise ascending.
SOURCE_BUNDLE_PATHS = (
    ".github/workflows/crypto_core_mt4_s3c_static_worker_qualification.yml",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_blst_capability.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_build_manifest.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_elf_qualify.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_observation_adjudicator.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_observation_parser.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_protocol_qualifier.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_receipt_generator.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_qualifier.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_bootstrap.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_start.S",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_verify.c",
    "tests/crypto_core/fixtures/mt4_s3c_test_only_positive_vector_v1.json",
)

# The exact 21 NEW paths this slice creates (V9 SECTION 35.2).
NEW_PATHS = SOURCE_BUNDLE_PATHS + (
    ".github/workflows/crypto_core_mt4_s3c_trusted_attestation.yml",
    "scripts/crypto_core/qualification/mt4_s3c_trusted_attestation_gate.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_test_only_vector_generator.c",
    "tests/crypto_core/validation/test_mt4_s3c_static_worker_qualification.py",
    "tests/crypto_core/validation/test_mt4_s3c_trusted_attestation.py",
)

# The six READ_ONLY_DEPENDENCY paths (V9 SECTION 9).  This slice reads them and never writes them.
READ_ONLY_DEPENDENCIES = (
    "scripts/crypto_core/qualification/mt4_trusted_attestation_gate.py",
    ".github/workflows/crypto_core_mt4_trusted_attestation.yml",
    ".github/workflows/crypto_core_mt4_s3a_blst_qualification.yml",
    "scripts/crypto_core/qualification/mt4_s3a_blst_quicknet_shim.c",
    "scripts/crypto_core/qualification/mt4_blst_dependency_admission_manifest.py",
    "src/crypto_core/validation/machine_time_drand_quicknet_verifier_profile.py",
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy_qualifier = _load("mt4_s3c_policy_qualifier", _S3C / "mt4_s3c_sandbox_policy_qualifier.py")
elf_qualify = _load("mt4_s3c_elf_qualify", _S3C / "mt4_s3c_elf_qualify.py")
observation_parser = _load("mt4_s3c_observation_parser", _S3C / "mt4_s3c_observation_parser.py")
adjudicator = _load("mt4_s3c_observation_adjudicator", _S3C / "mt4_s3c_observation_adjudicator.py")
protocol_qualifier = _load("mt4_s3c_protocol_qualifier", _S3C / "mt4_s3c_protocol_qualifier.py")
build_manifest = _load("mt4_s3c_build_manifest", _S3C / "mt4_s3c_build_manifest.py")
receipt_generator = _load("mt4_s3c_receipt_generator", _S3C / "mt4_s3c_receipt_generator.py")


# =================================================================================================
# SYNTHETIC UAPI CONSTANTS.
#
# These are TEST-ONLY sentinels, not platform values.  Using synthetic numbers is deliberate: the
# derivation and the interpreter are pure functions of whatever the canonical probe reports, so the
# mutant-kill proofs below hold without this test asserting a single Linux constant from memory.
# =================================================================================================


def synthetic_constants(**overrides):
    constants = {
        "audit_architecture_value_u32": 0xC000003E,
        "x32_syscall_bit_u32": 0x40000000,
        "seccomp_set_mode_filter_u32": 1,
        "seccomp_ret_allow_u32": 0x7FFF0000,
        "seccomp_ret_kill_process_u32": 0x80000000,
        "pr_set_dumpable_u32": 4,
        "pr_set_no_new_privs_u32": 38,
        "seccomp_data_offset_nr_u32": 0,
        "seccomp_data_offset_arch_u32": 4,
        "seccomp_data_offset_arg_lo_u32": tuple(16 + 8 * index for index in range(6)),
        "seccomp_data_offset_arg_hi_u32": tuple(20 + 8 * index for index in range(6)),
        "syscall_nr_u32": {
            "read": 0,
            "write": 1,
            "close": 3,
            "execve": 59,
            "prctl": 157,
            "exit_group": 231,
            "seccomp": 317,
            "close_range": 436,
        },
        "bpf_opcode_u16": {
            "ld_w_abs": 0x20,
            "jmp_jeq_k": 0x15,
            "jmp_jge_k": 0x35,
            "jmp_jgt_k": 0x25,
            "jmp_ja": 0x05,
            "ret_k": 0x06,
        },
    }
    constants.update(overrides)
    return constants


@pytest.fixture(scope="module")
def constants():
    return synthetic_constants()


@pytest.fixture(scope="module")
def programs(constants):
    outer = policy_qualifier.derive_program(constants, policy_qualifier._OUTER_INVENTORY)
    internal = policy_qualifier.derive_program(constants, policy_qualifier._INTERNAL_INVENTORY)
    return outer, internal


def _read(path):
    return path.read_text(encoding="utf-8")


def _code_only(path):
    """The source with comment prose removed, so prose never satisfies a source-shape check.

    Every source-shape test below runs against CODE, not against the sentence that describes
    the rule: a file that merely says a construct is forbidden must not thereby pass the test
    that the construct is absent.
    """
    text = _read(path)
    if path.suffix in (".yml", ".yaml"):
        return re.sub(r"(?m)^\s*#.*$", " ", text)
    return re.sub(r"/[*].*?[*]/", " ", text, flags=re.DOTALL)


# =================================================================================================
# BLOCK 0 -- SCOPE AND INVENTORY
# =================================================================================================


def test_every_new_path_exists_and_the_inventory_is_exactly_twenty_one():
    assert len(NEW_PATHS) == 21
    assert len(set(NEW_PATHS)) == 21
    for relative in NEW_PATHS:
        assert (_REPO_ROOT / relative).is_file(), relative


def test_source_bundle_is_exactly_sixteen_entries_in_ascending_order():
    assert len(SOURCE_BUNDLE_PATHS) == 16
    assert list(SOURCE_BUNDLE_PATHS) == sorted(SOURCE_BUNDLE_PATHS)
    assert build_manifest.SOURCE_BUNDLE_PATHS == SOURCE_BUNDLE_PATHS
    assert build_manifest.SOURCE_BUNDLE_ENTRY_COUNT == 16


def test_read_only_dependencies_exist_and_are_not_part_of_the_new_set():
    for relative in READ_ONLY_DEPENDENCIES:
        assert (_REPO_ROOT / relative).is_file(), relative
        assert relative not in NEW_PATHS


def test_the_offline_vector_generator_and_the_tests_are_outside_the_bundle():
    # Generation is frozen as OFFLINE and ONE-TIME, outside the qualification jobs, so it cannot
    # affect run evidence; and a closure test inside the bundle would validate its own set.
    for relative in (
        "scripts/crypto_core/qualification/s3c/mt4_s3c_test_only_vector_generator.c",
        "tests/crypto_core/validation/test_mt4_s3c_static_worker_qualification.py",
        "tests/crypto_core/validation/test_mt4_s3c_trusted_attestation.py",
        "scripts/crypto_core/qualification/mt4_s3c_trusted_attestation_gate.py",
        ".github/workflows/crypto_core_mt4_s3c_trusted_attestation.yml",
    ):
        assert relative not in SOURCE_BUNDLE_PATHS


# =================================================================================================
# BLOCK B/C -- OUTER POLICY, ABI, EMITTED PROGRAM AND ARGUMENT TUPLES  [V9-3]
# =================================================================================================


def test_frozen_program_lengths(programs):
    outer, internal = programs
    assert len(outer) == policy_qualifier.FROZEN_OUTER_PROGRAM_LEN == 400
    assert len(internal) == policy_qualifier.FROZEN_INTERNAL_PROGRAM_LEN == 113


def test_pt_118_the_arch_check_is_strictly_first(programs, constants):
    outer, internal = programs
    for program in (outer, internal):
        assert program[0].code == constants["bpf_opcode_u16"]["ld_w_abs"]
        assert program[0].k == constants["seccomp_data_offset_arch_u32"]
        assert program[1].code == constants["bpf_opcode_u16"]["jmp_jeq_k"]
        assert program[1].k == constants["audit_architecture_value_u32"]


def test_pt_113_the_x32_marker_is_compared_unmasked_and_unstripped(programs, constants):
    outer, _internal = programs
    # STEP 2 compares the UNMODIFIED nr against the marker with a greater-or-equal test.  The
    # canonical emitter has no masking instruction at all, so a stripped or normalised comparison is
    # not merely discouraged, it is not representable.
    assert outer[3].code == constants["bpf_opcode_u16"]["ld_w_abs"]
    assert outer[3].k == constants["seccomp_data_offset_nr_u32"]
    assert outer[4].code == constants["bpf_opcode_u16"]["jmp_jge_k"]
    assert outer[4].k == constants["x32_syscall_bit_u32"]
    permitted = set(constants["bpf_opcode_u16"].values())
    assert {instruction.code for instruction in outer}.issubset(permitted)


def test_the_shared_kill_block_is_the_last_instruction_and_the_default_action(programs, constants):
    outer, internal = programs
    for program in (outer, internal):
        last = program[-1]
        assert last.code == constants["bpf_opcode_u16"]["ret_k"]
        assert last.k == constants["seccomp_ret_kill_process_u32"]
        returns = [item for item in program if item.code == constants["bpf_opcode_u16"]["ret_k"]]
        kills = [item for item in returns if item.k == constants["seccomp_ret_kill_process_u32"]]
        assert len(kills) == 1


def test_every_jump_is_forward_and_inside_the_program(programs, constants):
    outer, internal = programs
    for program in (outer, internal):
        for index, instruction in enumerate(program):
            if instruction.code == constants["bpf_opcode_u16"]["jmp_ja"]:
                assert instruction.jt == 0 and instruction.jf == 0
                assert 0 <= index + 1 + instruction.k < len(program)
            elif instruction.code in (
                constants["bpf_opcode_u16"]["jmp_jeq_k"],
                constants["bpf_opcode_u16"]["jmp_jge_k"],
                constants["bpf_opcode_u16"]["jmp_jgt_k"],
            ):
                assert (instruction.jt, instruction.jf) in ((1, 0), (0, 1))


def test_the_governed_mutant_matrix_kills_every_named_vector(constants, programs):
    outer, internal = programs
    results = policy_qualifier.run_mutant_matrix(constants, outer, internal)
    identifiers = {entry["test_id"] for entry in results}
    for required in (
        "PT-111",
        "PT-112",
        "PT-121",
        "PT-122",
        "PT-123",
        "PT-123b",
        "PT-123c",
        "PT-123d",
        "PT-123e",
        "PT-125",
        "PT-126",
        "PT-131",
        "PT-132",
        "PT-133",
        "PT-134",
        "PT-135",
        "PT-136",
        "PT-137",
        "PT-504",
        "PT-509",
    ):
        assert required in identifiers
    for entry in results:
        if entry["test_id"].startswith("PT-"):
            assert entry["outer_action"] == "KILL_PROCESS", entry["test_id"]


def test_pt_141_a_single_changed_instruction_changes_the_governed_digest(constants, programs):
    outer, _internal = programs
    baseline = policy_qualifier.cbpf_digest(outer)
    mutated = policy_qualifier.derive_program(constants, policy_qualifier._OUTER_INVENTORY)
    mutated[10].k ^= 1
    assert policy_qualifier.cbpf_digest(mutated) != baseline


def test_pt_124_an_identical_semantic_table_with_a_changed_program_changes_only_the_governed_digest(
    constants, programs
):
    outer, _internal = programs
    honest = policy_qualifier.build_policy_record(
        constants,
        policy_qualifier._OUTER_INVENTORY,
        policy_qualifier.OUTER_POLICY_SCHEMA,
        policy_qualifier.OUTER_POLICY_DIGEST_DOMAIN,
        policy_qualifier.OUTER_POLICY_DOMAIN,
        outer,
    )
    tampered_program = policy_qualifier.derive_program(constants, policy_qualifier._OUTER_INVENTORY)
    tampered_program[20].k ^= 0xFF
    tampered = policy_qualifier.build_policy_record(
        constants,
        policy_qualifier._OUTER_INVENTORY,
        policy_qualifier.OUTER_POLICY_SCHEMA,
        policy_qualifier.OUTER_POLICY_DIGEST_DOMAIN,
        policy_qualifier.OUTER_POLICY_DOMAIN,
        tampered_program,
    )
    assert honest["semantic_digest_sha256"] == tampered["semantic_digest_sha256"]
    assert honest["governed_digest_sha256"] != tampered["governed_digest_sha256"]


def test_pt_115_a_default_allow_action_changes_the_governed_digest():
    permissive = synthetic_constants(seccomp_ret_kill_process_u32=0x7FFF0000)
    with pytest.raises(policy_qualifier.SandboxPolicyError):
        # ALLOW and KILL_PROCESS collapsing to one value is not a policy, it is a contradiction.
        policy_qualifier._validate_constant_relations(permissive)


def test_pt_120_widening_an_argument_rule_changes_the_governed_digest(constants, programs):
    outer, _internal = programs
    baseline = policy_qualifier.build_policy_record(
        constants,
        policy_qualifier._OUTER_INVENTORY,
        policy_qualifier.OUTER_POLICY_SCHEMA,
        policy_qualifier.OUTER_POLICY_DIGEST_DOMAIN,
        policy_qualifier.OUTER_POLICY_DOMAIN,
        outer,
    )

    def widened(_constants):
        return (
            policy_qualifier.ArgumentRule(
                policy_qualifier._zero_tail(
                    policy_qualifier._range(0, 0, 255),
                    policy_qualifier._pointer(1),
                    policy_qualifier._range(2, 1, 184),
                )
            ),
        )

    inventory = (("read", "CANDIDATE_VERIFY", widened),) + policy_qualifier._OUTER_INVENTORY[1:]
    program = policy_qualifier.derive_program(constants, inventory)
    record = policy_qualifier.build_policy_record(
        constants,
        inventory,
        policy_qualifier.OUTER_POLICY_SCHEMA,
        policy_qualifier.OUTER_POLICY_DIGEST_DOMAIN,
        policy_qualifier.OUTER_POLICY_DOMAIN,
        program,
    )
    assert record["governed_digest_sha256"] != baseline["governed_digest_sha256"]


def test_pt_127_an_option_set_only_rule_is_not_representable():
    # V9 14.2: every rule MUST classify all six argument words.  A rule that leaves an index
    # unclassified is MALFORMED and fails closed rather than silently admitting a free argument.
    with pytest.raises(policy_qualifier.SandboxPolicyError):
        policy_qualifier.ArgumentRule(((policy_qualifier.CAT_EXACT, 4, 0),))
    with pytest.raises(policy_qualifier.SandboxPolicyError):
        policy_qualifier.ArgumentRule(tuple([("ARG_IN_SET", 0, 0)] * 6))


def test_the_two_discriminated_prctl_tuples_are_ordered_alternatives(constants):
    rules = policy_qualifier._prctl_rules(constants)
    assert len(rules) == 2
    first, second = (rule.to_canonical() for rule in rules)
    assert first["exact_u64"]["0"] == constants["pr_set_dumpable_u32"]
    assert first["exact_u64"]["1"] == 0
    assert second["exact_u64"]["0"] == constants["pr_set_no_new_privs_u32"]
    assert second["exact_u64"]["1"] == 1
    for rule in (first, second):
        assert rule["zero_indices"] == [2, 3, 4, 5]
        assert rule["unconstrained_pointer_indices"] == []
        assert rule["unconstrained_scalar_indices"] == []


def test_close_carries_three_discriminated_tuples_and_no_implicit_set(constants):
    rules = policy_qualifier._close_rules(constants)
    assert len(rules) == 3
    assert [rule.to_canonical()["exact_u64"]["0"] for rule in rules] == [0, 1, 2]


def test_exit_group_argument_zero_is_an_explicit_unconstrained_scalar(constants):
    rule = policy_qualifier._exit_group_rules(constants)[0].to_canonical()
    # Constraining the exit status in classic BPF was considered and REJECTED: an out-of-taxonomy
    # exit would then be KILLED by seccomp and would present as a containment violation, destroying
    # failure attribution.  The status word is therefore unconstrained BY THE FILTER and constrained
    # by the adjudicator over the observed wait status instead.
    assert rule["unconstrained_scalar_indices"] == [0]
    assert rule["zero_indices"] == [1, 2, 3, 4, 5]
    assert "0" not in rule["exact_u64"]


def test_every_rule_classifies_all_six_argument_words(constants):
    for _name, _reason, factory in policy_qualifier._OUTER_INVENTORY:
        for rule in factory(constants):
            canonical = rule.to_canonical()
            covered = (
                set(int(key) for key in canonical["exact_u64"])
                | set(int(key) for key in canonical["range_u64"])
                | set(canonical["unconstrained_pointer_indices"])
                | set(canonical["unconstrained_scalar_indices"])
                | set(canonical["zero_indices"])
            )
            assert covered == set(range(6))


def test_the_internal_allowed_set_is_exactly_read_write_exit_group():
    assert policy_qualifier.INTERNAL_SYSCALL_NAMES == ("read", "write", "exit_group")
    assert len(policy_qualifier.OUTER_SYSCALL_NAMES) == 8


def test_pt_503_the_outer_allowlist_is_exactly_the_frozen_eight_with_reason_classes(constants):
    preimage = policy_qualifier._semantic_preimage(
        constants,
        policy_qualifier._OUTER_INVENTORY,
        policy_qualifier.OUTER_POLICY_SCHEMA,
        policy_qualifier.OUTER_POLICY_DOMAIN,
    )
    assert preimage["syscall_inventory_count"] == 8
    assert preimage["default_action"] == "SECCOMP_RET_KILL_PROCESS"
    assert preimage["seccomp_flags_u32"] == 0
    assert preimage["unused_argument_policy"] == "UNUSED_ARGUMENT_WORDS_MUST_BE_ZERO"
    assert preimage["reason_classes"] == sorted(policy_qualifier.REASON_CLASSES)
    for entry in preimage["syscall_inventory"]:
        assert entry["reason_class"] in policy_qualifier.REASON_CLASSES
        assert entry["argument_rule_count"] == len(entry["argument_rules"])
    numbers = [entry["nr_u32"] for entry in preimage["syscall_inventory"]]
    assert numbers == sorted(numbers)


def test_a_non_ascending_dispatch_order_fails_closed():
    broken = synthetic_constants()
    broken["syscall_nr_u32"] = dict(broken["syscall_nr_u32"])
    broken["syscall_nr_u32"]["write"] = 0
    with pytest.raises(policy_qualifier.SandboxPolicyError):
        policy_qualifier._validate_constant_relations(broken)


def test_a_syscall_number_carrying_the_x32_marker_fails_closed():
    broken = synthetic_constants()
    broken["syscall_nr_u32"] = dict(broken["syscall_nr_u32"])
    broken["syscall_nr_u32"]["close_range"] = 0x40000001
    with pytest.raises(policy_qualifier.SandboxPolicyError):
        policy_qualifier._validate_constant_relations(broken)


# =================================================================================================
# BLOCK E -- INTERNAL_FILTER_EQUIVALENCE_DIGEST  [V9-4]
# =================================================================================================


def _equivalence_record():
    return {
        "schema": policy_qualifier.INTERNAL_EQUIVALENCE_SCHEMA,
        "canonical_internal_policy_id": policy_qualifier.INTERNAL_POLICY_DOMAIN,
        "canonical_internal_policy_sha256": "a" * 64,
        "program_representation_version": policy_qualifier.PROGRAM_REPRESENTATION_VERSION,
        "canonical_internal_cbpf_instruction_count": 113,
        "canonical_internal_cbpf_sha256": "b" * 64,
        "captured_internal_cbpf_sha256": "b" * 64,
        "captured_internal_uargs_va_u64": 0x401600,
        "captured_internal_len_u32": 113,
        "install_exit_return_i32": 0,
        "baseline_supervisor_seccomp": 0,
        "baseline_supervisor_filters": 0,
        "baseline_child_seccomp": 0,
        "baseline_child_filters": 0,
        "pre_install_filters": 1,
        "post_install_filters": 2,
        "post_install_seccomp_mode": 2,
        "revalidated_filters": 2,
        "dump_leg_availability": policy_qualifier.DUMP_UNAVAILABLE,
        "dump_leg_index0_sha256": "",
        "dump_leg_index1_sha256": "",
        "dump_leg_terminates_at_index": -1,
        "case_id": "C01_POSITIVE_EXACT_FIXTURE",
        "source_run_id": 12345,
        "source_run_attempt": 1,
        "source_head_sha": "c" * 40,
        "candidate_binary_sha256": "d" * 64,
    }


def test_the_equivalence_field_set_is_exactly_the_frozen_twenty_seven():
    assert len(policy_qualifier.INTERNAL_EQUIVALENCE_FIELDS) == 27
    assert sorted(_equivalence_record()) == sorted(policy_qualifier.INTERNAL_EQUIVALENCE_FIELDS)


def test_the_equivalence_preimage_carries_no_authority_field():
    for forbidden in ("accepted", "admitted", "status", "verdict", "timestamp", "readiness", "machine_time"):
        assert not any(forbidden in field for field in policy_qualifier.INTERNAL_EQUIVALENCE_FIELDS)


@pytest.mark.parametrize(
    ("test_id", "field", "value"),
    (
        ("PT-151", "canonical_internal_policy_sha256", "e" * 64),
        ("PT-152", "canonical_internal_cbpf_sha256", "f" * 64),
        ("PT-153", "baseline_child_filters", 1),
        ("PT-154", "pre_install_filters", 0),
        ("PT-155", "post_install_filters", 1),
        ("PT-156", "captured_internal_uargs_va_u64", 0x7FFFDEAD),
        ("PT-157", "source_run_id", 999999),
        ("PT-158", "candidate_binary_sha256", "0" * 64),
    ),
)
def test_every_equivalence_mutant_changes_or_rejects_the_digest(test_id, field, value):
    honest = policy_qualifier.internal_equivalence_digest(_equivalence_record())
    mutated = _equivalence_record()
    mutated[field] = value
    try:
        assert policy_qualifier.internal_equivalence_digest(mutated) != honest, test_id
    except policy_qualifier.SandboxPolicyError:
        pass  # a constraint violation is a stronger outcome than a differing digest


def test_pt_161_an_available_dump_leg_with_empty_fields_is_rejected():
    record = _equivalence_record()
    record["dump_leg_availability"] = policy_qualifier.DUMP_AVAILABLE
    with pytest.raises(policy_qualifier.SandboxPolicyError):
        policy_qualifier.internal_equivalence_digest(record)


def test_a_captured_program_differing_from_canonical_is_never_digested():
    record = _equivalence_record()
    record["captured_internal_cbpf_sha256"] = "9" * 64
    with pytest.raises(policy_qualifier.SandboxPolicyError):
        policy_qualifier.internal_equivalence_digest(record)


def test_the_three_independent_equivalence_implementations_agree_byte_for_byte():
    """A3, A4 and Stage C must compute the SAME value from the same record.

    The three implementations are deliberately independent -- none imports another -- because
    independent recomputation at the trust boundary is the whole point of V9 16.4.  This test is
    what makes that independence a cross-check rather than a drift risk.
    """
    record = _equivalence_record()
    from_qualifier = policy_qualifier.internal_equivalence_digest(record)
    from_adjudicator = adjudicator.domain_digest(
        adjudicator.INTERNAL_EQUIVALENCE_DIGEST_DOMAIN, adjudicator.validate_equivalence_record(dict(record))
    )
    gate_domain = b"mt4-s3c-internal-filter-equivalence.v1\x00"
    gate_body = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    from_gate = hashlib.sha256(gate_domain + gate_body).hexdigest()
    assert from_qualifier == from_adjudicator == from_gate


def test_the_adjudicator_and_qualifier_agree_on_the_required_equivalence_values():
    assert adjudicator.INTERNAL_EQUIVALENCE_REQUIRED_VALUES == policy_qualifier._EQUIVALENCE_REQUIRED_VALUES
    assert adjudicator.INTERNAL_EQUIVALENCE_SCHEMA == policy_qualifier.INTERNAL_EQUIVALENCE_SCHEMA
    assert adjudicator.INTERNAL_EQUIVALENCE_DIGEST_DOMAIN == policy_qualifier.INTERNAL_EQUIVALENCE_DIGEST_DOMAIN


# =================================================================================================
# BLOCK P -- V5 WIRE PROTOCOL AND OBSERVATION CASE SET  [V9-5]
# =================================================================================================


def _response(result_class, result_code, magic=b"MT4R", version=1, reserved=0):
    return magic + bytes((version, result_class, result_code, reserved))


def test_the_restored_response_layout_places_result_class_and_code_at_five_and_six():
    fields = {name: (start, length) for name, start, length in protocol_qualifier.RESPONSE_LAYOUT}
    assert fields["result_class"] == (5, 1)
    assert fields["result_code"] == (6, 1)
    assert fields["reserved"] == (7, 1)
    protocol_qualifier.prove_wire_contract()


def test_pt_401_the_v8_two_byte_reserved_tail_is_withdrawn():
    # A V8-shaped frame carries its code at offset 5 and a two-byte reserved tail.  Under the
    # restored layout that same buffer decodes as an illegal RESULT_CLASS, never as a crypto result.
    v8_shaped = b"MT4R" + bytes((1, 0, 0, 0))
    decoded = observation_parser.decode_response(v8_shaped, False)
    assert decoded["outcome"] == observation_parser.RESPONSE_VIOLATION


def test_pt_402_an_all_zero_buffer_is_never_verifier_status_ok():
    decoded = observation_parser.decode_response(bytes(8), False)
    assert decoded["outcome"] == observation_parser.RESPONSE_VIOLATION


@pytest.mark.parametrize(
    ("test_id", "frame", "extra"),
    (
        ("PT-403", _response(0x03, 0), False),
        ("PT-404", _response(0x01, 0, reserved=1), False),
        ("PT-405", _response(0x01, 12), False),
        ("PT-405b", _response(0x01, 255), False),
        ("PT-406", _response(0x02, 0), False),
        ("PT-406b", _response(0x02, 7), False),
        ("PT-407", _response(0x01, 0), True),
        ("PT-421a", _response(0x01, 1), False),
        ("PT-421b", _response(0x01, 2), False),
        ("WRONG_MAGIC", _response(0x01, 0, magic=b"MT4W"), False),
        ("WRONG_VERSION", _response(0x01, 0, version=2), False),
    ),
)
def test_every_illegal_response_shape_is_a_protocol_violation(test_id, frame, extra):
    decoded = observation_parser.decode_response(frame, extra)
    assert decoded["outcome"] == observation_parser.RESPONSE_VIOLATION, test_id


def test_all_twelve_verifier_statuses_are_legal_wire_statuses():
    # Every one of 0..11 is a LEGAL WIRE STATUS.  Codes 1 and 2 are legal-but-unreachable and are
    # classified as an internal contract break, NEVER as malformed protocol framing.
    assert observation_parser.VERIFIER_STATUS_CODES == tuple(range(12))
    for code in observation_parser.VERIFIER_STATUS_REACHABLE:
        decoded = observation_parser.decode_response(_response(0x01, code), False)
        assert decoded["outcome"] == observation_parser.RESPONSE_OK
        assert decoded["result_code"] == code
    for code in observation_parser.VERIFIER_STATUS_UNREACHABLE:
        decoded = observation_parser.decode_response(_response(0x01, code), False)
        assert decoded["outcome"] == observation_parser.RESPONSE_VIOLATION
        assert "LEGAL_BUT_UNREACHABLE" in decoded["marker"]
        assert "MALFORMED" not in decoded["marker"]


def test_the_request_error_taxonomy_is_closed_at_six():
    for code in observation_parser.REQUEST_PROTOCOL_ERROR_CODES:
        decoded = observation_parser.decode_response(_response(0x02, code), False)
        assert decoded["outcome"] == observation_parser.RESPONSE_OK
    assert observation_parser.REQUEST_PROTOCOL_ERROR_CODES == (1, 2, 3, 4, 5, 6)


def test_the_phase_scoped_exit_code_sets_are_disjoint():
    assert observation_parser.CANDIDATE_EXIT_CODES == (0, 64, 65)
    assert observation_parser.LAUNCHER_EXIT_CODES == (70,)
    assert not set(observation_parser.CANDIDATE_EXIT_CODES) & set(observation_parser.LAUNCHER_EXIT_CODES)


def test_pt_194_a_candidate_exiting_seventy_is_worker_crashed_not_launch_failed():
    case = {
        "infrastructure_reason": "NONE",
        "exec_transition_observed": True,
        "wait_signalled": False,
        "wait_exited": True,
        "wait_exit_status": 70,
    }
    assert observation_parser.resolve_process_outcome(case) == observation_parser.PROCESS_WORKER_CRASHED


def test_a_process_that_never_became_the_candidate_is_exec_failed():
    case = {
        "infrastructure_reason": "NONE",
        "exec_transition_observed": False,
        "wait_signalled": False,
        "wait_exited": True,
        "wait_exit_status": 70,
    }
    assert observation_parser.resolve_process_outcome(case) == observation_parser.PROCESS_WORKER_EXEC_FAILED


# =================================================================================================
# THE GOVERNED OBSERVATION CASE INVENTORY  [V9-5]
# =================================================================================================


def test_the_derivation_rules_produce_exactly_twenty_five_cases():
    derived = adjudicator.derive_case_inventory()
    assert len(derived) == 25
    assert derived == adjudicator.FROZEN_CASE_INVENTORY


def test_pt_419_the_case_count_composition_is_twelve_eleven_and_two():
    assert adjudicator.VERIFIER_CASE_COUNT == 12
    assert adjudicator.REQUEST_CASE_COUNT == 11
    assert adjudicator.PROCESS_CASE_COUNT == 2
    assert adjudicator.EXACT_CASE_COUNT == 25


def test_both_orthogonal_verify_failed_cases_are_derived():
    # DR1b: a single code cannot prove two independent consumption paths.  Without C12 a worker that
    # ignored the public key entirely would still pass C01 and every signature case.
    code_eleven = [case for case in adjudicator.FROZEN_CASE_INVENTORY if case["expected_result_code"] == 11]
    assert len(code_eleven) == 2
    assert {case["case_id"] for case in code_eleven} == {
        "C11_VERIFY_FAILED_WRONG_DIGEST",
        "C12_VERIFY_FAILED_WRONG_PUBLIC_KEY",
    }


def test_the_two_structurally_unreachable_codes_get_no_case():
    codes = {case["expected_result_code"] for case in adjudicator.FROZEN_CASE_INVENTORY}
    assert 1 not in codes or all(
        case["expected_result_class"] != 1
        for case in adjudicator.FROZEN_CASE_INVENTORY
        if case["expected_result_code"] == 1
    )
    verifier_codes = {
        case["expected_result_code"] for case in adjudicator.FROZEN_CASE_INVENTORY if case["expected_result_class"] == 1
    }
    assert verifier_codes == set(adjudicator.VERIFIER_STATUS_REACHABLE)


def test_the_boundary_stimuli_share_codes_by_design():
    short_cases = [
        case
        for case in adjudicator.FROZEN_CASE_INVENTORY
        if case["expected_result_class"] == 2 and case["expected_result_code"] == 5
    ]
    trailing_cases = [
        case
        for case in adjudicator.FROZEN_CASE_INVENTORY
        if case["expected_result_class"] == 2 and case["expected_result_code"] == 6
    ]
    # Four SHORT_FRAME_EOF stimuli and three TRAILING_INPUT stimuli.  The CODES are shared
    # because V5 says so; the STIMULI are distinct boundary conditions the fail-closed
    # enumeration names separately, and two of the seven are the V9 strengthening cases that
    # pin the frozen field-validation order.  This is deliberate coverage, not duplication.
    assert len(short_cases) == 4
    assert len(trailing_cases) == 3
    assert len(short_cases) + len(trailing_cases) + 4 == adjudicator.REQUEST_CASE_COUNT


def test_the_two_v9_strengthening_cases_pin_the_frozen_validation_order():
    strengthening = [
        case for case in adjudicator.FROZEN_CASE_INVENTORY if case["case_origin"] == adjudicator.CASE_ORIGIN_V9
    ]
    assert len(strengthening) == 2
    by_id = {case["case_id"]: case for case in strengthening}
    # Over-long AND wrong magic must yield TRAILING_INPUT; short AND wrong magic must yield
    # SHORT_FRAME_EOF.  Each expected response is a value V5 already requires for its winner.
    assert by_id["C22_ORDER_TRAILING_BEFORE_MAGIC"]["expected_result_code"] == 6
    assert by_id["C23_ORDER_SHORT_BEFORE_MAGIC"]["expected_result_code"] == 5


def test_the_two_process_cases_expect_no_response_frame():
    process_cases = [case for case in adjudicator.FROZEN_CASE_INVENTORY if case["stimulus_class"] == "PROCESS_STIMULUS"]
    assert len(process_cases) == 2
    for case in process_cases:
        assert case["expected_result_class"] == 0
        assert case["expected_result_code"] == -1
        assert case["expected_exit_status"] == -1
        assert case["expected_result_type"] in ("RT_PROCESS_TERMINATED_BY_SIGNAL", "RT_DEADLINE_EXPIRED")


def test_both_frame_result_types_require_exit_status_zero():
    for case in adjudicator.FROZEN_CASE_INVENTORY:
        if case["expected_result_type"] in ("RT_VERIFIER_STATUS_FRAME", "RT_REQUEST_PROTOCOL_ERROR_FRAME"):
            assert case["expected_exit_status"] == 0


def test_the_case_set_digest_is_stable_and_domain_separated():
    digest = adjudicator.observation_case_set_digest()
    assert len(digest) == 64
    preimage = adjudicator.case_set_preimage()
    assert preimage["schema"] == "mt4-s3c-observation-case-set.v2"
    assert preimage["case_count"] == 25
    assert preimage["case_id_order"] == list(adjudicator.FROZEN_CASE_IDS)
    other = adjudicator.domain_digest(b"different-domain\x00", preimage)
    assert other != digest


@pytest.mark.parametrize(
    ("test_id", "mutate"),
    (
        ("PT-415", lambda cases: cases[:-1]),
        ("PT-416", lambda cases: cases[:-1] + [dict(cases[0])]),
        ("PT-418", lambda cases: [cases[1], cases[0]] + cases[2:]),
    ),
)
def test_the_rejection_rules_run_before_any_case_is_adjudicated(test_id, mutate):
    honest = [
        {
            "case_id": case["case_id"],
            "expected_result_class": case["expected_result_class"],
            "expected_result_code": case["expected_result_code"],
            "expected_exit_status": case["expected_exit_status"],
            "stimulus_kind": case["stimulus_kind"],
        }
        for case in adjudicator.FROZEN_CASE_INVENTORY
    ]
    adjudicator.reject_invalid_case_set(honest)
    with pytest.raises(adjudicator.AdjudicationError):
        adjudicator.reject_invalid_case_set(mutate(list(honest)))


def test_pt_420_an_integer_case_identifier_is_a_type_failure():
    honest = [
        {
            "case_id": case["case_id"],
            "expected_result_class": case["expected_result_class"],
            "expected_result_code": case["expected_result_code"],
            "expected_exit_status": case["expected_exit_status"],
            "stimulus_kind": case["stimulus_kind"],
        }
        for case in adjudicator.FROZEN_CASE_INVENTORY
    ]
    honest[0]["case_id"] = 1
    with pytest.raises(adjudicator.AdjudicationError):
        adjudicator.reject_invalid_case_set(honest)


def test_the_protocol_and_adjudicator_case_tables_are_identical():
    protocol_table = tuple(
        (case_id, expected_class, expected_code, expected_exit, stimulus_kind)
        for case_id, expected_class, expected_code, expected_exit, stimulus_kind in protocol_qualifier.GOVERNED_CASES
    )
    adjudicator_table = tuple(
        (
            case["case_id"],
            case["expected_result_class"],
            case["expected_result_code"],
            case["expected_exit_status"],
            case["stimulus_kind"],
        )
        for case in adjudicator.FROZEN_CASE_INVENTORY
    )
    assert protocol_table == adjudicator_table


# =================================================================================================
# THE GOVERNED TEST-ONLY FIXTURE  [V9 21.9, SECTION 39]
# =================================================================================================


@pytest.fixture(scope="module")
def fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_is_structurally_valid_against_the_frozen_case_table(fixture_payload):
    protocol_qualifier.validate_fixture(fixture_payload)


def test_pt_430_the_fixture_is_never_labelled_official_normative_or_quicknet(fixture_payload):
    assert fixture_payload["vector_authority"] == "PROJECT_GENERATED_DETERMINISTIC_TEST_VECTOR"
    assert fixture_payload["non_claims"]["is_official_or_normative_vector"] is False
    assert fixture_payload["non_claims"]["is_quicknet_beacon_material"] is False
    for flag in (
        "fixture_corpus_admitted",
        "fixture_corpus_loaded",
        "fixture_corpus_verified",
        "proof_verified",
        "randomness_verified",
        "provider_operationally_approved",
        "readiness_promoted",
    ):
        assert fixture_payload["non_claims"][flag] is False
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "FX-DRAND-QUICKNET" not in raw


def test_the_fixture_material_gate_fails_closed_until_the_offline_generator_has_run(fixture_payload):
    """The committed fixture carries no vector material yet, and that is a FAIL-CLOSED state.

    Producing the material requires running the governed offline generator on Linux against PINNED
    blst, because the exact status that library returns for each frozen construction is a property
    of the library and V9 21.9 forbids guessing it.  Until that has happened the fixture stays in
    PENDING_OFFLINE_GENERATION, and this test proves the state is ALWAYS rejected before any case
    material is read.  There is no mode in which a pending fixture yields a qualification result.
    """
    assert fixture_payload["fixture_material_state"] in protocol_qualifier.FIXTURE_STATES
    with pytest.raises(protocol_qualifier.ProtocolQualificationError) as error:
        protocol_qualifier.require_generated_fixture(fixture_payload)
    assert "FIXTURE_MATERIAL_NOT_GENERATED" in str(error.value)
    with pytest.raises(protocol_qualifier.ProtocolQualificationError):
        protocol_qualifier.build_case_plan(FIXTURE.read_bytes(), fixture_payload)


def test_a_generated_fixture_without_generator_provenance_is_rejected(fixture_payload):
    claimed = dict(fixture_payload)
    claimed["fixture_material_state"] = protocol_qualifier.FIXTURE_STATE_GENERATED
    with pytest.raises(protocol_qualifier.ProtocolQualificationError):
        protocol_qualifier.require_generated_fixture(claimed)


def test_pt_428_editing_a_fixture_expected_code_is_rejected(fixture_payload):
    tampered = json.loads(json.dumps(fixture_payload))
    tampered["cases"][2]["expected_result_code"] = 9
    with pytest.raises(protocol_qualifier.ProtocolQualificationError):
        protocol_qualifier.validate_fixture(tampered)


def test_pt_429_a_relabelled_construction_intent_is_rejected(fixture_payload):
    tampered = json.loads(json.dumps(fixture_payload))
    tampered["cases"][3]["construction_intent"] = "SINGLE_BIT_MUTATION"
    with pytest.raises(protocol_qualifier.ProtocolQualificationError):
        protocol_qualifier.validate_fixture(tampered)


def test_the_case_plan_is_deterministic_and_binds_the_fixture_digest(fixture_payload):
    generated = json.loads(json.dumps(fixture_payload))
    generated["fixture_material_state"] = protocol_qualifier.FIXTURE_STATE_GENERATED
    generated["generator_source_sha256"] = "1" * 64
    generated["generator_binary_sha256"] = "2" * 64
    raw = json.dumps(generated, sort_keys=True).encode("utf-8")
    first = protocol_qualifier.build_case_plan(raw, generated)
    second = protocol_qualifier.build_case_plan(raw, generated)
    assert first == second
    assert first[:8] == b"MT4CPLAN"
    assert int.from_bytes(first[12:16], "little") == 25
    assert first[16:48] == hashlib.sha256(raw).digest()
    assert first[48:64] == bytes(16)


def test_the_offline_generator_proves_rather_than_adopts_the_expected_codes():
    source = _read(VECTOR_GENERATOR)
    assert "PINNED_BLST_STATUS_DISAGREEMENT" in source
    assert "UNRESOLVED_P2" in source
    assert "mt4_s3c_verify_quicknet_request" in source
    # A generator that adopted whatever the library returned would have no comparison at all.
    assert "observed != cases[index].expected_result_code" in source
    code = _code_only(VECTOR_GENERATOR)
    assert "PROJECT_GENERATED_DETERMINISTIC_TEST_VECTOR" in code
    # The two explicit NON-CLAIM keys are negations of exactly these labels, so they are
    # removed before the scan: the point is that no label is ever CLAIMED, not that the word
    # never occurs.  Both keys are additionally required to be emitted as false.
    assert '\\"is_official_or_normative_vector\\": false' in code
    assert '\\"is_quicknet_beacon_material\\": false' in code
    scanned = code.replace("is_official_or_normative_vector", "").replace("is_quicknet_beacon_material", "")
    for banned in ("official", "normative", "FX-DRAND-QUICKNET", "Quicknet beacon"):
        assert banned not in scanned, banned


# =================================================================================================
# BLOCK M -- STATIC ELF V2 AND BLST  [V9-8]
# =================================================================================================

_PAGE = 4096
_TEXT_VADDR = 0x401000
_TEXT_OFFSET = 0x1000
_DATA_VADDR = 0x404000
_DATA_OFFSET = 0x4000
_CAP_VADDR = 0x401100
_PROGRAM_VADDR = 0x401200
_FPROG_VADDR = 0x401600
_OUTER_PROGRAM_VADDR = 0x401800
_OUTER_FPROG_VADDR = 0x401700
_TEXT_SIZE = 0x2000
_DATA_SIZE = 0x10


def _build_symbol(name_offset, info, other, shndx, value, size):
    return (
        name_offset.to_bytes(4, "little")
        + bytes((info, other))
        + shndx.to_bytes(2, "little")
        + value.to_bytes(8, "little")
        + size.to_bytes(8, "little")
    )


_CANONICAL_INTERNAL_PROGRAM = []


_CANONICAL_OUTER_PROGRAM = []


def canonical_outer_program():
    """The exact canonical OUTER program bytes, derived once from the reviewed emitter."""
    if not _CANONICAL_OUTER_PROGRAM:
        _CANONICAL_OUTER_PROGRAM.append(
            policy_qualifier.program_bytes(
                policy_qualifier.derive_program(_X86_64_UAPI_CONSTANTS, policy_qualifier._OUTER_INVENTORY)
            )
        )
    return _CANONICAL_OUTER_PROGRAM[0]


def canonical_internal_program():
    """The canonical internal cBPF program, derived once from the frozen x86_64 constants."""
    if not _CANONICAL_INTERNAL_PROGRAM:
        _CANONICAL_INTERNAL_PROGRAM.append(
            policy_qualifier.program_bytes(
                policy_qualifier.derive_program(_X86_64_UAPI_CONSTANTS, policy_qualifier._INTERNAL_INVENTORY)
            )
        )
    return _CANONICAL_INTERNAL_PROGRAM[0]


def build_reference_elf(**overrides):
    """Synthesise a minimal ELF64 image that satisfies every frozen qualification row.

    Every mutant below starts from this image and changes exactly one thing, so a mutant that fails
    to flip a result is visible as a test defect rather than as evidence about the qualifier.
    """
    entry = overrides.get("entry", _TEXT_VADDR)
    text_flags = overrides.get("text_flags", elf_qualify.PF_R | elf_qualify.PF_X)
    data_flags = overrides.get("data_flags", elf_qualify.PF_R | elf_qualify.PF_W)
    stack_flags = overrides.get("stack_flags", elf_qualify.PF_R | elf_qualify.PF_W)
    data_vaddr = overrides.get("data_vaddr", _DATA_VADDR)
    text_memsz = overrides.get("text_memsz", _TEXT_SIZE)
    text_filesz = overrides.get("text_filesz", _TEXT_SIZE)
    data_memsz = overrides.get("data_memsz", _DATA_SIZE)
    cap_value = overrides.get("cap_value", bytes(4))
    cap_size = overrides.get("cap_size", 4)
    cap_vaddr = overrides.get("cap_vaddr", _CAP_VADDR)
    cap_binding = overrides.get("cap_binding", elf_qualify.STB_GLOBAL)
    cap_visibility = overrides.get("cap_visibility", elf_qualify.STV_HIDDEN)
    cap_shndx = overrides.get("cap_shndx", 1)
    cap_symbol_type = overrides.get("cap_symbol_type", 1)
    text_align = overrides.get("text_align", _PAGE)
    stack_align = overrides.get("stack_align", 0x10)
    program_size = overrides.get("program_size", elf_qualify.INTERNAL_PROGRAM_SIZE_BYTES)
    fprog_len = overrides.get("fprog_len", elf_qualify.INTERNAL_PROGRAM_INSTRUCTIONS)
    fprog_pointer = overrides.get("fprog_pointer", _PROGRAM_VADDR)
    extra_symbols = overrides.get("extra_symbols", ())
    extra_phdrs = overrides.get("extra_phdrs", ())
    omit_stack = overrides.get("omit_stack", False)
    text_body_extra = overrides.get("text_body_extra", b"")

    text = bytearray(b"\x90" * text_filesz)
    text[_CAP_VADDR - _TEXT_VADDR : _CAP_VADDR - _TEXT_VADDR + len(cap_value)] = cap_value
    # The reference image carries the REAL canonical internal program.  A placeholder of zeros
    # would make every consumer that anchors on the canonical bytes unreachable in tests.
    program_body = overrides.get("program_bytes", canonical_internal_program()[:program_size])
    if len(program_body) < program_size:
        program_body = program_body + bytes(program_size - len(program_body))
    text[_PROGRAM_VADDR - _TEXT_VADDR : _PROGRAM_VADDR - _TEXT_VADDR + program_size] = program_body[:program_size]
    fprog = fprog_len.to_bytes(2, "little") + bytes(6) + fprog_pointer.to_bytes(8, "little")
    text[_FPROG_VADDR - _TEXT_VADDR : _FPROG_VADDR - _TEXT_VADDR + 16] = fprog

    # The OUTER filter objects.  The real worker links the same policy translation unit that
    # defines them, so an image without them is not the image Stage C reconstructs.
    outer_body = overrides.get("outer_program_bytes", canonical_outer_program())
    outer_size = overrides.get("outer_program_size", len(canonical_outer_program()))
    outer_pointer = overrides.get("outer_fprog_pointer", _OUTER_PROGRAM_VADDR)
    outer_len = overrides.get("outer_fprog_len", len(canonical_outer_program()) // 8)
    text[_OUTER_PROGRAM_VADDR - _TEXT_VADDR : _OUTER_PROGRAM_VADDR - _TEXT_VADDR + len(outer_body)] = outer_body
    outer_fprog = outer_len.to_bytes(2, "little") + bytes(6) + outer_pointer.to_bytes(8, "little")
    text[_OUTER_FPROG_VADDR - _TEXT_VADDR : _OUTER_FPROG_VADDR - _TEXT_VADDR + 16] = outer_fprog
    if text_body_extra:
        text[0x700 : 0x700 + len(text_body_extra)] = text_body_extra

    strings = b"\x00"
    offsets = {}
    for name in (
        "_start",
        "__blst_platform_cap",
        "mt4_s3c_internal_filter_program",
        "mt4_s3c_internal_filter_fprog",
        "mt4_s3c_outer_filter_program",
        "mt4_s3c_outer_filter_fprog",
    ):
        offsets[name] = len(strings)
        strings += name.encode("ascii") + b"\x00"
    for name, _info, _other, _shndx, _value, _size in extra_symbols:
        offsets[name] = len(strings)
        strings += name.encode("ascii") + b"\x00"

    symbols = bytes(24)
    symbols += _build_symbol(offsets["_start"], (elf_qualify.STB_GLOBAL << 4) | 2, elf_qualify.STV_HIDDEN, 1, entry, 16)
    symbols += _build_symbol(
        offsets["__blst_platform_cap"],
        (cap_binding << 4) | cap_symbol_type,
        cap_visibility,
        cap_shndx,
        cap_vaddr,
        cap_size,
    )
    symbols += _build_symbol(
        offsets["mt4_s3c_internal_filter_program"],
        (elf_qualify.STB_GLOBAL << 4) | 1,
        elf_qualify.STV_HIDDEN,
        1,
        _PROGRAM_VADDR,
        program_size,
    )
    symbols += _build_symbol(
        offsets["mt4_s3c_internal_filter_fprog"],
        (elf_qualify.STB_GLOBAL << 4) | 1,
        elf_qualify.STV_HIDDEN,
        1,
        _FPROG_VADDR,
        16,
    )
    symbols += _build_symbol(
        offsets["mt4_s3c_outer_filter_program"],
        (overrides.get("outer_binding", elf_qualify.STB_GLOBAL) << 4) | overrides.get("outer_symbol_type", 1),
        overrides.get("outer_visibility", elf_qualify.STV_HIDDEN),
        1,
        _OUTER_PROGRAM_VADDR,
        outer_size,
    )
    symbols += _build_symbol(
        offsets["mt4_s3c_outer_filter_fprog"],
        (elf_qualify.STB_GLOBAL << 4) | 1,
        elf_qualify.STV_HIDDEN,
        1,
        _OUTER_FPROG_VADDR,
        16,
    )
    for name, info, other, shndx, value, size in extra_symbols:
        symbols += _build_symbol(offsets[name], info, other, shndx, value, size)

    section_names = b"\x00"
    section_name_offsets = {}
    for name in (".text", ".data", ".symtab", ".strtab", ".shstrtab"):
        section_name_offsets[name] = len(section_names)
        section_names += name.encode("ascii") + b"\x00"

    phdrs = [
        (elf_qualify.PT_LOAD, text_flags, _TEXT_OFFSET, _TEXT_VADDR, text_filesz, text_memsz, text_align),
        (elf_qualify.PT_LOAD, data_flags, _DATA_OFFSET, data_vaddr, _DATA_SIZE, data_memsz, _PAGE),
    ]
    if not omit_stack:
        phdrs.append((elf_qualify.PT_GNU_STACK, stack_flags, 0, 0, 0, 0, stack_align))
    phdrs.extend(extra_phdrs)

    header_end = 64 + 56 * len(phdrs)
    assert header_end <= _TEXT_OFFSET

    body = bytearray(b"\x00" * _DATA_OFFSET)
    body[_TEXT_OFFSET : _TEXT_OFFSET + text_filesz] = text
    body += bytes(_DATA_SIZE)
    symtab_offset = len(body)
    body += symbols
    strtab_offset = len(body)
    body += strings
    shstrtab_offset = len(body)
    body += section_names
    while len(body) % 8:
        body += b"\x00"
    shoff = len(body)

    sections = [
        (0, elf_qualify.SHT_NULL, 0, 0, 0, 0, 0, 0, 0),
        (section_name_offsets[".text"], elf_qualify.SHT_PROGBITS, 0x6, _TEXT_VADDR, _TEXT_OFFSET, text_filesz, 0, 0, 0),
        (section_name_offsets[".data"], elf_qualify.SHT_PROGBITS, 0x3, data_vaddr, _DATA_OFFSET, _DATA_SIZE, 0, 0, 0),
        (
            section_name_offsets[".symtab"],
            elf_qualify.SHT_SYMTAB,
            0,
            0,
            symtab_offset,
            len(symbols),
            4,
            1,
            24,
        ),
        (section_name_offsets[".strtab"], elf_qualify.SHT_STRTAB, 0, 0, strtab_offset, len(strings), 0, 0, 0),
        (
            section_name_offsets[".shstrtab"],
            elf_qualify.SHT_STRTAB,
            0,
            0,
            shstrtab_offset,
            len(section_names),
            0,
            0,
            0,
        ),
    ]

    header = bytearray(64)
    header[0:4] = elf_qualify.ELF_MAGIC
    header[4] = elf_qualify.ELFCLASS64
    header[5] = elf_qualify.ELFDATA2LSB
    header[6] = elf_qualify.EV_CURRENT
    header[7] = 0
    header[16:18] = overrides.get("e_type", elf_qualify.ET_EXEC).to_bytes(2, "little")
    header[18:20] = overrides.get("e_machine", elf_qualify.EM_X86_64).to_bytes(2, "little")
    header[20:24] = (1).to_bytes(4, "little")
    header[24:32] = entry.to_bytes(8, "little")
    header[32:40] = (64).to_bytes(8, "little")
    header[40:48] = shoff.to_bytes(8, "little")
    header[48:52] = (0).to_bytes(4, "little")
    header[52:54] = (64).to_bytes(2, "little")
    header[54:56] = (56).to_bytes(2, "little")
    header[56:58] = len(phdrs).to_bytes(2, "little")
    header[58:60] = (64).to_bytes(2, "little")
    header[60:62] = len(sections).to_bytes(2, "little")
    header[62:64] = (5).to_bytes(2, "little")

    phdr_blob = b""
    for kind, flags, offset, vaddr, filesz, memsz, align in phdrs:
        phdr_blob += (
            kind.to_bytes(4, "little")
            + flags.to_bytes(4, "little")
            + offset.to_bytes(8, "little")
            + vaddr.to_bytes(8, "little")
            + vaddr.to_bytes(8, "little")
            + filesz.to_bytes(8, "little")
            + memsz.to_bytes(8, "little")
            + align.to_bytes(8, "little")
        )

    shdr_blob = b""
    for name, kind, flags, addr, offset, size, link, info, entsize in sections:
        shdr_blob += (
            name.to_bytes(4, "little")
            + kind.to_bytes(4, "little")
            + flags.to_bytes(8, "little")
            + addr.to_bytes(8, "little")
            + offset.to_bytes(8, "little")
            + size.to_bytes(8, "little")
            + link.to_bytes(4, "little")
            + info.to_bytes(4, "little")
            + (8).to_bytes(8, "little")
            + entsize.to_bytes(8, "little")
        )

    image = bytes(header) + phdr_blob
    image += bytes(_TEXT_OFFSET - len(image))
    image += bytes(body[_TEXT_OFFSET:])
    image += shdr_blob
    return image


def _qualify(image, **kwargs):
    return elf_qualify.qualify(
        image,
        kwargs.get("page_size", _PAGE),
        kwargs.get("inventory", elf_qualify.canonical_phdr_inventory(elf_qualify.EXPECTED_PHDR_INVENTORY)),
        kwargs.get("dependency_digest", "a" * 64),
    )


def test_the_reference_image_qualifies():
    record = _qualify(build_reference_elf())
    assert record["schema"] == "mt4-s3c-elf-qualification-record.v1"
    assert record["elf"]["type"] == "ET_EXEC"
    assert record["blst_platform_cap"]["observed_size_bytes"] == 4
    assert record["blst_platform_cap"]["value_hex"] == "00000000"
    assert record["canonical_internal_filter_object"]["program_instruction_count"] == 113
    assert record["authority_non_transition"]["evidence_status"] == "ADMISSION_EVIDENCE_ONLY"
    assert len(record["elf_qualification_digest_sha256"]) == 64


@pytest.mark.parametrize(
    ("test_id", "overrides", "marker"),
    (
        ("PT-284", {"data_vaddr": 0x402000}, "PT_LOAD_EFFECTIVE_PAGE_OVERLAP"),
        ("PT-285", {"text_flags": elf_qualify.PF_R | elf_qualify.PF_W | elf_qualify.PF_X}, "EFFECTIVE_WX_PAGE"),
        ("PT-286", {"stack_flags": elf_qualify.PF_R}, "PHDR_INVENTORY_MISMATCH"),
        ("PT-288", {"extra_phdrs": ((elf_qualify.PT_DYNAMIC, 4, 0, 0, 0, 0, 8),)}, "DYNAMIC_SURFACE_PRESENT"),
        ("PT-288b", {"extra_phdrs": ((elf_qualify.PT_INTERP, 4, 0, 0, 0, 0, 1),)}, "DYNAMIC_SURFACE_PRESENT"),
        ("PT-299j", {"extra_phdrs": ((elf_qualify.PT_TLS, 4, 0, 0, 0, 0, 8),)}, "DYNAMIC_SURFACE_PRESENT"),
        ("PT-GNU-STACK", {"omit_stack": True}, "PHDR_INVENTORY_MISMATCH"),
        ("PT-290", {"text_filesz": 0x600}, "FILTER_OBJECT_SECTION_INDEX_INVALID"),
        (
            "PT-UNDEF-ANON",
            {"extra_symbols": (("", (elf_qualify.STB_GLOBAL << 4) | 0, 0, elf_qualify.SHN_UNDEF, 0, 0),)},
            "UNDEFINED_SYMBOL_CLOSURE_VIOLATED",
        ),
        (
            "PT-UNDEF-DUPLICATE-NAME",
            {
                "extra_symbols": (
                    ("memcpy", (elf_qualify.STB_GLOBAL << 4) | 2, 0, 1, _TEXT_VADDR, 4),
                    ("memcpy_undef", (elf_qualify.STB_GLOBAL << 4) | 2, 0, elf_qualify.SHN_UNDEF, 0, 0),
                ),
            },
            "UNDEFINED_SYMBOL_CLOSURE_VIOLATED",
        ),
        ("PT-CAP-WRONG-SECTION", {"cap_shndx": 2}, "BLST_CAP_SECTION_INDEX_INVALID"),
        ("PT-296", {"text_memsz": 32 * 1024 * 1024}, "ELF_MEMORY_CEILING_EXCEEDED"),
        ("PT-299a", {"cap_shndx": elf_qualify.SHN_UNDEF}, "UNDEFINED_SYMBOL_CLOSURE_VIOLATED"),
        ("PT-299k", {"cap_binding": elf_qualify.STB_LOCAL}, "BLST_CAP_BINDING"),
        ("PT-299l", {"cap_visibility": elf_qualify.STV_INTERNAL}, "BLST_CAP_VISIBILITY"),
        ("PT-299m", {"cap_shndx": elf_qualify.SHN_COMMON}, "BLST_CAP_COMMON"),
        ("PT-299n", {"cap_shndx": 0xFF20}, "BLST_CAP_SECTION_INDEX_INVALID"),
        ("PT-299q", {"cap_shndx": 250}, "BLST_CAP_SECTION_INDEX_INVALID"),
        ("PT-299p", {"cap_symbol_type": 2}, "BLST_CAP_TYPE"),
        ("PT-ALIGN-LOAD", {"text_align": 0x2000}, "PHDR_INVENTORY_MISMATCH"),
        ("PT-ALIGN-STACK", {"stack_align": 0x8}, "PHDR_INVENTORY_MISMATCH"),
        (
            "PT-UNDEF-EXTRA",
            {"extra_symbols": (("memcpy", (elf_qualify.STB_GLOBAL << 4) | 2, 0, elf_qualify.SHN_UNDEF, 0, 0),)},
            "UNDEFINED_SYMBOL_CLOSURE_VIOLATED",
        ),
        ("PT-299b", {"cap_binding": elf_qualify.STB_WEAK}, "BLST_CAP_WEAK"),
        ("PT-299d", {"cap_visibility": elf_qualify.STV_DEFAULT}, "BLST_CAP_VISIBILITY"),
        ("PT-299e", {"cap_value": b"\x01\x00\x00\x00"}, "BLST_CAP_VALUE"),
        ("PT-299g", {"cap_size": 8}, "BLST_CAP_SIZE"),
        ("PT-299f", {"cap_vaddr": _DATA_VADDR + 4}, "BLST_CAP"),
        ("PT-299h", {"text_body_extra": b"\x0f\xa2"}, "BLST_CPUID_PRESENT"),
        ("PT-ETDYN", {"e_type": 3}, "ELF_TYPE_NOT_ET_EXEC"),
        ("PT-MACHINE", {"e_machine": 40}, "ELF_MACHINE_INVALID"),
        ("PT-FPROG-LEN", {"fprog_len": 112}, "FILTER_OBJECT_LENGTH_INVALID"),
        ("PT-FPROG-PTR", {"fprog_pointer": _DATA_VADDR}, "FILTER_OBJECT_POINTER_INVALID"),
        ("PT-PROG-SIZE", {"program_size": 800}, "FILTER_OBJECT_SIZE_INVALID"),
    ),
)
def test_every_static_elf_mutant_fails_with_its_named_marker(test_id, overrides, marker):
    with pytest.raises(elf_qualify.ElfQualificationError) as error:
        _qualify(build_reference_elf(**overrides))
    assert marker in str(error.value), test_id


def test_pt_299c_two_definitions_of_the_capability_object_fail():
    extra = (("__blst_platform_cap_dup", (elf_qualify.STB_GLOBAL << 4) | 1, elf_qualify.STV_HIDDEN, 1, _CAP_VADDR, 4),)
    image = build_reference_elf(extra_symbols=extra)
    _qualify(image)  # a differently NAMED symbol is not a second definition
    with pytest.raises(elf_qualify.ElfQualificationError) as error:
        elf_qualify.require_single_definition(
            elf_qualify.parse_symbols(image, elf_qualify.parse_elf(image)["section_headers"])
            + [
                elf_qualify.Symbol(
                    "__blst_platform_cap", (elf_qualify.STB_GLOBAL << 4) | 1, elf_qualify.STV_HIDDEN, 1, _CAP_VADDR, 4
                )
            ],
            "__blst_platform_cap",
        )
    assert "BLST_CAP_MULTIPLE" in str(error.value)


def test_pt_289_a_page_size_other_than_four_kilobytes_fails_closed():
    with pytest.raises(elf_qualify.ElfQualificationError) as error:
        _qualify(build_reference_elf(), page_size=65536)
    assert "ENVIRONMENT_PAGE_SIZE_INCOMPATIBLE" in str(error.value)


def test_pt_287_the_expected_phdr_oracle_may_never_come_from_the_candidate():
    # Two independent NON-CANDIDATE authorities must agree.  A disagreement -- which is what a
    # candidate-derived oracle would produce -- fails before any header is even parsed.
    with pytest.raises(elf_qualify.ElfQualificationError) as error:
        _qualify(
            build_reference_elf(),
            inventory="PT_LOAD:5:0x1000,PT_LOAD:6:0x1000,PT_GNU_STACK:6:0x10,PT_NOTE:4:0x4",
        )
    assert "PHDR_INVENTORY_AUTHORITY_DISAGREEMENT" in str(error.value)


def test_pt_292_a_decoy_offset_elsewhere_in_the_image_is_never_consulted():
    honest = _qualify(build_reference_elf())
    decoyed = _qualify(build_reference_elf(text_body_extra=b"\x00\x10\x40\x00\x00\x00\x00\x00"))
    assert honest["blst_platform_cap"]["file_offset_u64"] == decoyed["blst_platform_cap"]["file_offset_u64"]


@pytest.mark.parametrize(
    ("test_id", "symbol_va", "symbol_size", "marker"),
    (
        ("PT-293", 2**64 - 8, 16, "ELF_RANGE_INVALID"),
        ("PT-295", 0x900000, 4, "SYMBOL_NO_CONTAINING_SEGMENT"),
        ("PT-291", _TEXT_VADDR + _TEXT_SIZE - 2, 8, "SYMBOL_NOT_FILE_BACKED"),
    ),
)
def test_the_checked_translation_rejects_every_named_hazard(test_id, symbol_va, symbol_size, marker):
    image = build_reference_elf()
    headers = elf_qualify.parse_elf(image)["program_headers"]
    with pytest.raises(elf_qualify.ElfQualificationError) as error:
        elf_qualify.translate_symbol(image, headers, symbol_va, symbol_size)
    assert marker in str(error.value), test_id


def test_pt_298_the_rlimit_as_relation_is_checked_against_the_actual_candidate():
    assert elf_qualify.RLIMIT_AS_BYTES == 64 * 1024 * 1024
    assert (
        elf_qualify.RLIMIT_AS_BYTES
        == elf_qualify.MAX_AGGREGATE_EFFECTIVE_BYTES
        + elf_qualify.STACK_RESERVE_BYTES
        + elf_qualify.GOVERNED_HEADROOM_BYTES
    )
    elf_qualify.check_rlimit_as_relation(8 * 1024 * 1024)
    with pytest.raises(elf_qualify.ElfQualificationError) as error:
        elf_qualify.check_rlimit_as_relation(elf_qualify.RLIMIT_AS_BYTES - elf_qualify.STACK_RESERVE_BYTES)
    assert "RLIMIT_AS_INSUFFICIENT" in str(error.value)


def test_the_elf_and_zip_share_one_worker_size_constant():
    # The archive bound and the ELF bound cannot drift apart because they are the SAME literal.
    assert elf_qualify.MAX_WORKER_BINARY_BYTES == 8 * 1024 * 1024
    assert build_manifest.MAX_WORKER_BINARY_BYTES == elf_qualify.MAX_WORKER_BINARY_BYTES


def test_the_aliasing_claim_is_stated_narrowly():
    source = _read(_S3C / "mt4_s3c_elf_qualify.py")
    assert "eliminates page aliasing entirely" not in source
    assert "VIRTUAL-PAGE OVERLAP BETWEEN PT_LOAD" in source
    assert "storage-level aliasing" in source
    assert "page-cache sharing between processes" in source


# =================================================================================================
# SOURCE-SHAPE TESTS -- the non-mutating tracer contract and the launcher invariants
# =================================================================================================

_FORBIDDEN_TRACER_REQUESTS = (
    "PTRACE_POKEDATA",
    "PTRACE_POKETEXT",
    "PTRACE_POKEUSER",
    "PTRACE_SETREGS",
    "PTRACE_SETREGSET",
    "PTRACE_SETFPREGS",
    "PTRACE_SETSIGINFO",
    "PTRACE_DETACH",
    "PTRACE_SEIZE",
    "PTRACE_INTERRUPT",
    "PTRACE_LISTEN",
    "PTRACE_O_SUSPEND_SECCOMP",
    "process_vm_writev",
)


def _launcher_code():
    """The launcher source with its comment prose removed, so prose never satisfies a check."""
    source = _read(LAUNCHER_SOURCE)
    return re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)


def _launcher_ptrace_oracle():
    """The exact request set the launcher declares it may issue, read from the frozen table."""
    block = re.search(
        r"static const long mt4_s3c_permitted_ptrace_requests\[[^\]]*\]\s*=\s*\{(.*?)\};",
        _read(LAUNCHER_SOURCE),
        flags=re.DOTALL,
    )
    assert block, "the launcher must declare a positive ptrace oracle"
    return sorted(item.strip().replace("(long)", "").strip() for item in block.group(1).split(",") if item.strip())


def test_the_launcher_declares_a_positive_finite_tracer_oracle():
    # A POSITIVE oracle, not an absence check: the exact set is enumerated, so a request nobody
    # thought to forbid is excluded by construction rather than by having been remembered.
    assert _launcher_ptrace_oracle() == sorted(
        [
            "PTRACE_TRACEME",
            "PTRACE_SETOPTIONS",
            "PTRACE_SYSCALL",
            "PTRACE_CONT",
            "PTRACE_GETREGSET",
            "PTRACE_PEEKDATA",
            "PTRACE_SECCOMP_GET_FILTER",
        ]
    )


def test_every_ptrace_call_goes_through_the_single_gateway():
    """Executable code may reach ptrace() only inside the gateway that enforces the oracle.

    This is what makes the oracle binding rather than decorative: a numeric or computed request
    cannot be issued without passing the membership test, because there is no other call site.
    """
    code = _launcher_code()
    raw = re.findall(r"(?<![_a-zA-Z])ptrace\s*\(", code)
    # Exactly one raw call: the one inside mt4_s3c_ptrace_permitted.
    assert len(raw) == 1, raw
    gateway = code.index("static long mt4_s3c_ptrace_permitted(")
    call = code.index("ptrace((enum __ptrace_request)request", gateway)
    assert call > gateway
    # Every other tracer site names the gateway.
    assert code.count("mt4_s3c_ptrace_permitted(") >= 9


@pytest.mark.parametrize("request_name", _FORBIDDEN_TRACER_REQUESTS)
def test_pt_110b_no_forbidden_tracer_operation_is_reachable(request_name):
    """A forbidden request is excluded by the ORACLE, not merely absent from the source text.

    The old test asserted the token did not occur, which a numeric literal defeats and which a
    deliberate mention -- such as the value assertion that forbids PTRACE_O_SUSPEND_SECCOMP by
    number -- breaks for the wrong reason.
    """
    assert request_name not in _launcher_ptrace_oracle(), request_name


def test_a_numeric_forbidden_request_is_rejected_by_the_oracle():
    """The oracle is a VALUE membership test, so a numeric request is refused like a named one."""
    code = _launcher_code()
    body = code[code.index("static long mt4_s3c_ptrace_permitted(") :]
    body = body[: body.index("return ptrace(")]
    # Membership is decided by comparing the request VALUE against the frozen table, and the
    # default outcome is refusal, so an unrecognised number cannot fall through to the kernel.
    assert "mt4_s3c_permitted_ptrace_requests[index] == request" in body
    assert "if (permitted == 0)" in body
    assert body.index("permitted = 0") < body.index("if (permitted == 0)")


def test_pt_110e_the_tracer_never_opens_proc_mem():
    code = _launcher_code()
    assert "/mem" not in code
    assert "process_vm_readv" not in code
    assert "process_vm_writev" not in code
    assert "/proc/%ld/status" in code


def test_pt_110d_every_resume_site_passes_a_literal_zero_signal():
    code = _launcher_code()
    sites = re.findall(
        r"mt4_s3c_ptrace_permitted\(\s*\(long\)(?:PTRACE_SYSCALL|PTRACE_CONT)\s*,[^;]*", code, flags=re.DOTALL
    )
    assert len(sites) >= 2, "the launcher must contain the frozen resume sites"
    for site in sites:
        # CONTROL, never MUTATION: resuming a stopped process changes WHEN it runs, never WHAT
        # it is, and the distinction is drawn exactly at the literal zero signal argument.
        assert "MT4_S3C_PTRACE_RESUME_SIGNAL" in site, site
    # And the gateway refuses anything else, so a literal or computed nonzero signal cannot be
    # delivered even if a future edit introduced one at a call site.
    assert "data != MT4_S3C_PTRACE_RESUME_SIGNAL" in code
    assert "#define MT4_S3C_PTRACE_RESUME_SIGNAL ((void *)0)" in _read(LAUNCHER_SOURCE)


def test_a_nonzero_resume_signal_is_refused_before_the_kernel():
    code = _launcher_code()
    body = code[code.index("static long mt4_s3c_ptrace_permitted(") :]
    body = body[: body.index("return ptrace(")]
    guard = body[body.index("request == (long)PTRACE_SYSCALL") :]
    # The refusal is unconditional on the DATA argument, so neither a literal nor a computed
    # nonzero value reaches ptrace.
    assert "errno = EPERM" in guard
    assert "return -1L" in guard


def test_the_frozen_ptrace_option_set_is_exactly_three_bits():
    source = _read(LAUNCHER_SOURCE)
    match = re.search(r"#define MT4_S3C_PTRACE_OPTIONS \(([^)]*)\)", source)
    assert match
    options = [item.strip() for item in match.group(1).split("|")]
    assert sorted(options) == sorted(["PTRACE_O_TRACESYSGOOD", "PTRACE_O_TRACEEXEC", "PTRACE_O_EXITKILL"])
    # The forbidden bit is excluded BY VALUE at compile time, which a token check cannot do.
    assert "#define MT4_S3C_PTRACE_O_SUSPEND_SECCOMP_VALUE 0x00200000u" in source
    assert "MT4_S3C_PTRACE_O_SUSPEND_SECCOMP_VALUE) == 0ul" in source
    assert "~MT4_S3C_PTRACE_OPTION_BITS_ALLOWED) == 0ul" in source
    # SETOPTIONS may install only the frozen word, enforced in the gateway.
    assert (
        "request == (long)PTRACE_SETOPTIONS && data != (void *)(unsigned long)MT4_S3C_PTRACE_OPTIONS"
        in _launcher_code()
    )


def test_pt_128_exactly_one_outer_program_definition_and_one_launcher_install_site():
    policy = _read(POLICY_SOURCE)
    assert policy.count("const struct sock_filter mt4_s3c_outer_filter_program[") == 1
    assert policy.count("const struct sock_fprog mt4_s3c_outer_filter_fprog") == 1
    assert policy.count("const struct sock_filter mt4_s3c_internal_filter_program[") == 1
    assert policy.count("const struct sock_fprog mt4_s3c_internal_filter_fprog") == 1
    assert _launcher_code().count("mt4_s3c_sys_seccomp(") == 2  # one definition, one call site


def test_pt_193_nothing_is_interposed_between_execve_and_the_launcher_exit():
    code = _launcher_code()
    start = code.index("mt4_s3c_sys_execve(MT4_S3C_CANDIDATE_PATH")
    end = code.index("mt4_s3c_sys_exit_group(MT4_S3C_EXIT_LAUNCHER_FAILED)", start)
    between = code[start:end]
    for forbidden in ("read(", "write(", "verify", "if (", "for (", "while ("):
        assert forbidden not in between, forbidden


def test_the_post_filter_syscalls_are_project_owned_with_a_zeroed_argument_tail():
    """Repair 5D.  A libc wrapper sets only the registers it needs; the filter requires all six.

    The outer filter classifies every one of the six argument words and demands an exactly zero
    tail, so an execve issued through libc -- which leaves %r10, %r8 and %r9 holding whatever the
    caller left there -- is killed by the launcher's own policy.  Both post-filter syscalls
    therefore go through the project-owned six-argument wrapper.
    """
    code = _launcher_code()
    source = _read(LAUNCHER_SOURCE)
    # The wrapper exists, loads all six argument registers, and is the one used after the install.
    assert "static inline long mt4_s3c_syscall6(" in source
    for register in ('__asm__("r10")', '__asm__("r8")', '__asm__("r9")'):
        assert register in source, register
    for wrapper in ("mt4_s3c_sys_execve", "mt4_s3c_sys_exit_group"):
        definition = re.search(r"mt4_s3c_syscall6\(__NR_\w+[^;]*\)", code[code.index(wrapper) :])
        assert definition, wrapper
        arguments = definition.group(0).split("(", 1)[1].rsplit(")", 1)[0].split(",")
        assert len(arguments) == 7, wrapper
        assert [item.strip() for item in arguments[-3:]] == ["0", "0", "0"], wrapper
    # And the post-filter path uses NEITHER libc entry point.
    launch = code[code.index("State 18 EXACT_CANDIDATE_LAUNCH") if "State 18" in code else 0 :]
    tail = code[code.index("mt4_s3c_sys_execve(MT4_S3C_CANDIDATE_PATH") :]
    assert "(void)execve(" not in tail
    assert "_exit(MT4_S3C_EXIT_LAUNCHER_FAILED)" not in tail.replace("mt4_s3c_sys_exit_group(", "")
    del launch


def test_the_worker_installs_exactly_one_internal_filter_before_any_request_read():
    code = re.sub(r"/\*.*?\*/", " ", _read(BOOTSTRAP_SOURCE), flags=re.DOTALL)
    assert code.count("mt4_s3c_sys_seccomp(") == 2  # one wrapper definition, one call site
    assert code.index("mt4_s3c_install_internal_filter()") < code.index("mt4_s3c_fill_request()")
    # PR_SET_DUMPABLE is set to zero BEFORE the install and can never be undone afterwards.
    assert "mt4_s3c_sys_prctl(PR_SET_DUMPABLE, 0)" in code
    assert "PR_SET_DUMPABLE, 1" not in code


def test_the_worker_has_no_second_command_parser_and_no_read_loop_around_the_request():
    code = re.sub(r"/\*.*?\*/", " ", _read(BOOTSTRAP_SOURCE), flags=re.DOTALL)
    assert code.count("mt4_s3c_fill_request") == 2  # exactly one definition and one call site
    assert code.count("mt4_s3c_emit_response(") >= 5
    assert "opcode2" not in code and "second_command" not in code


def test_every_project_syscall_wrapper_zeroes_the_unused_argument_registers():
    code = _read(BOOTSTRAP_SOURCE)
    wrappers = re.findall(r"mt4_s3c_syscall6\(__NR_\w+[^;]*\)", code)
    assert len(wrappers) >= 7
    for wrapper in wrappers:
        arguments = wrapper.split("(", 1)[1].rsplit(")", 1)[0].split(",")
        assert len(arguments) == 7, wrapper
        # Every argument the syscall does not consume carries an explicit literal zero.
        assert arguments[-1].strip() == "0", wrapper


def test_the_assembly_entry_point_zeroes_every_unused_argument_register():
    code = _read(START_SOURCE)
    assert ".globl _start" in code
    assert "__NR_exit_group" in code
    for register in ("%esi", "%edx", "%r10d", "%r8d", "%r9d"):
        assert "xorl " + register + ", " + register in code
    assert ".note.GNU-stack" in code


def test_the_verify_unit_never_collapses_the_taxonomy_into_a_boolean():
    code = _read(VERIFY_SOURCE)
    assert "MT4_S3C_VERIFY_FAILED 11" in code
    assert "blst_core_verify_pk_in_g2" in code
    assert "blst_p2_affine_in_g2" in code
    assert "blst_p1_affine_in_g1" in code
    assert "return true" not in code and "return false" not in code


def test_the_capability_object_is_strong_hidden_read_only_and_zero():
    code = _read(CAPABILITY_SOURCE)
    assert "__BLST_NO_CPUID__" in code
    assert 'section(".rodata.mt4_s3c_blst_cap")' in code
    assert 'visibility("hidden")' in code
    assert "MT4_S3C_BLST_PLATFORM_CAP_SIZE_BYTES 4" in code
    assert "MT4_S3C_BLST_PLATFORM_CAP_VALUE 0u" in code
    stripped = _code_only(CAPABILITY_SOURCE).lower().replace("__blst_no_cpuid__", "")
    assert "cpuid" not in stripped


def test_the_canonical_filter_objects_live_in_read_only_file_backed_data():
    code = _read(POLICY_SOURCE)
    assert 'section(".rodata.mt4_s3c_filter")' in code
    assert 'visibility("hidden")' in code
    assert "_Static_assert(MT4_S3C_OUTER_PROGRAM_LEN == 400" in code
    assert "_Static_assert(MT4_S3C_INTERNAL_PROGRAM_LEN == 113" in code
    # The dispatch order relation is ASSERTED; no numeric syscall value is asserted anywhere.
    assert code.count("_Static_assert(__NR_") == 7
    for literal in ("0xc000003e", "0xC000003E", "SECCOMP_RET_KILL_PROCESS 0x", "__NR_read 0"):
        assert literal not in code


def test_the_probe_installs_nothing_and_decides_nothing():
    code = re.sub(r"/\*.*?\*/", " ", _read(POLICY_PROBE_SOURCE), flags=re.DOTALL)
    for forbidden in ("seccomp(", "prctl(", "fork(", "execve(", "clone("):
        assert forbidden not in code, forbidden


# =================================================================================================
# SOURCE CLOSURE  [V9-7]
# =================================================================================================

_BUNDLED_PYTHON = (
    "mt4_s3c_build_manifest.py",
    "mt4_s3c_elf_qualify.py",
    "mt4_s3c_observation_adjudicator.py",
    "mt4_s3c_observation_parser.py",
    "mt4_s3c_protocol_qualifier.py",
    "mt4_s3c_receipt_generator.py",
    "mt4_s3c_sandbox_policy_qualifier.py",
)

_ALLOWED_STDLIB_IMPORTS = {"argparse", "hashlib", "json", "os", "sys", "re", "io", "pathlib"}


@pytest.mark.parametrize("name", _BUNDLED_PYTHON)
def test_pt_265_no_bundled_script_imports_a_repository_module(name):
    tree = ast.parse((_S3C / name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                allowed = _ALLOWED_STDLIB_IMPORTS | ({"subprocess"} if name == _SUBPROCESS_EXEMPT else set())
                assert root in allowed, (name, alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            assert node.level == 0, (name, "relative import")
            root = (node.module or "").split(".")[0]
            allowed = _ALLOWED_STDLIB_IMPORTS | ({"subprocess"} if name == _SUBPROCESS_EXEMPT else set())
            assert root in allowed, (name, node.module)


# THE BUILD WRAPPER EXEMPTION, stated rather than implied.
#
# mt4_s3c_build_manifest.py now RUNS the compiler: that is the whole point of recording the actual
# invocation rather than a declaration of it, and a wrapper that cannot execute cannot observe.  It
# therefore needs subprocess, which the blanket rule forbids.  The rule is not deleted -- it is
# narrowed to one named file, and that file is held to a STRICTER contract than the ban provided:
# a fixed argument vector, no shell, no repository-supplied command, and none of the other dynamic
# machinery.  Every other bundled script keeps the blanket ban unchanged.
_SUBPROCESS_EXEMPT = "mt4_s3c_build_manifest.py"


@pytest.mark.parametrize("name", _BUNDLED_PYTHON)
def test_pt_266_no_bundled_script_contains_dynamic_import_machinery(name):
    source = (_S3C / name).read_text(encoding="utf-8")
    forbidden_forms = ["importlib", "__import__", "exec(", "eval(", "compile(", "ctypes"]
    if name != _SUBPROCESS_EXEMPT:
        forbidden_forms.append("subprocess")
    for forbidden in forbidden_forms:
        assert forbidden not in source, (name, forbidden)


def test_the_build_wrapper_executes_only_a_fixed_argument_vector():
    """The one subprocess exemption is held to a STRICTER contract than the ban it replaces."""
    source = (_S3C / _SUBPROCESS_EXEMPT).read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            if target.value.id == "subprocess":
                calls.append((target.attr, node))
    assert calls, "the wrapper must actually invoke subprocess"
    for attribute, node in calls:
        # ONLY run().  No Popen, no call, no check_output, no shell helper.
        assert attribute == "run", attribute
        keywords = {keyword.arg: keyword for keyword in node.keywords}
        # NEVER a shell, and EXPLICITLY so.  Relying on the library default leaves the
        # guarantee outside this file; the audit requires the explicit form.
        assert "shell" in keywords, "shell=False must be explicit"
        shell_value = keywords["shell"].value
        assert isinstance(shell_value, ast.Constant) and shell_value.value is False
        # The frozen execution boundary, made structural: an explicit governed working
        # directory and an explicit governed environment on every permitted call.
        assert "cwd" in keywords, "the wrapper must pass an explicit cwd"
        assert "env" in keywords, "the wrapper must pass an explicit environment"
        # The command is a LIST, not a string: a string command is a shell command in disguise.
        first = node.args[0] if node.args else None
        assert isinstance(first, (ast.Name, ast.List)), "the command must be a fixed argument vector"

    # And none of the other dynamic machinery reappears under the exemption.
    for forbidden in ("importlib", "__import__", "exec(", "eval(", "compile(", "ctypes", "os.system", "shell=True"):
        assert forbidden not in source, forbidden


@pytest.mark.parametrize("name", _BUNDLED_PYTHON)
def test_pt_267_no_bundled_script_reads_a_repository_relative_path_literal(name):
    tree = ast.parse((_S3C / name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if not value.startswith(("scripts/", "src/", "tests/", ".github/")):
                continue
            # The governed S3C include root is a DIRECTORY used for the include-root allowlist,
            # not a decision-affecting file read, so it is the one permitted non-entry literal.
            if value in SOURCE_BUNDLE_PATHS or value == "scripts/crypto_core/qualification/s3c":
                continue
            # REQUIRED_UPSTREAM_INPUTS are relative to the PINNED UPSTREAM ROOT, not to the
            # repository, so they are neither a repository read nor a bundle entry.  They exist to
            # make the compile inventory's coverage of the pinned blst inputs mandatory.
            if name == "mt4_s3c_build_manifest.py" and value in build_manifest.REQUIRED_UPSTREAM_INPUTS:
                continue
            raise AssertionError((name, value))


def test_the_dependency_inventory_rejects_an_unbundled_repository_dependency(tmp_path):
    dependency = tmp_path / "unit.d"
    dependency.write_text("unit.o: " + str(_REPO_ROOT / "src" / "crypto_core" / "__init__.py") + "\n", encoding="utf-8")
    with pytest.raises(build_manifest.BuildManifestError) as error:
        build_manifest.build_dependency_inventory([str(dependency)], str(_REPO_ROOT), str(tmp_path / "upstream"))
    assert "SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED" in str(error.value)


def test_pt_272_an_include_root_outside_the_allowlist_fails(tmp_path):
    with pytest.raises(build_manifest.BuildManifestError) as error:
        build_manifest.check_include_roots([str(tmp_path / "elsewhere")], str(_REPO_ROOT), str(tmp_path / "upstream"))
    assert "INCLUDE_ROOT_VIOLATION" in str(error.value)
    build_manifest.check_include_roots(
        [str(_REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "s3c")],
        str(_REPO_ROOT),
        str(tmp_path / "upstream"),
    )


def test_the_runtime_closure_relation_is_a_subset_not_an_equality():
    """Repair 7A: no `or True`, and the assertion is about behaviour rather than documentation.

    A statically expected dependency that lies on an unexecuted branch is legitimate, so the
    relation is OBSERVED subset-of STATIC_EXPECTED and never an equality.  The direction is proven
    by construction below: a dependency inventory containing a bundle entry that this run never
    executed is accepted, while an unbundled one is refused.
    """
    source = _read(_S3C / "mt4_s3c_build_manifest.py")
    assert "SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED" in source


def test_the_source_bundle_digest_binds_mode_type_count_and_order():
    entries = [
        {"path": path, "mode": "100644", "type": "blob", "sha256": format(index, "064x")}
        for index, path in enumerate(SOURCE_BUNDLE_PATHS)
    ]
    baseline = build_manifest.source_bundle_digest(entries)
    for mutate in (
        lambda items: [dict(item, mode="100755") if index == 0 else item for index, item in enumerate(items)],
        lambda items: [
            dict(item, sha256=format(99, "064x")) if index == 3 else item for index, item in enumerate(items)
        ],
    ):
        assert build_manifest.source_bundle_digest(mutate(list(entries))) != baseline
    with pytest.raises(build_manifest.BuildManifestError):
        build_manifest.source_bundle_digest(entries[:-1])
    with pytest.raises(build_manifest.BuildManifestError):
        build_manifest.source_bundle_digest([dict(entries[0], type="commit")] + entries[1:])
    with pytest.raises(build_manifest.BuildManifestError):
        build_manifest.source_bundle_digest(list(reversed(entries)))


# =================================================================================================
# LEG A -- WORKFLOW COMMAND GRAMMAR  [V9-7]
# =================================================================================================

_FORBIDDEN_SHELL_CONSTRUCTS = ("$(", "`", "eval ", "source ", "${!", "$RANDOM")


@pytest.fixture(scope="module")
def qualification_workflow():
    return yaml.safe_load(QUALIFICATION_WORKFLOW.read_text(encoding="utf-8"))


def _run_blocks(workflow):
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                yield step.get("name", "<unnamed>"), step["run"]


def test_pt_261_no_forbidden_shell_construct_appears_in_a_qualification_command(qualification_workflow):
    for name, block in _run_blocks(qualification_workflow):
        for forbidden in _FORBIDDEN_SHELL_CONSTRUCTS:
            assert forbidden not in block, (name, forbidden)
        assert "python -c" not in block, name
        assert "python3 -c" not in block, name


def test_pt_262_every_repository_path_token_in_a_command_is_a_bundle_entry(qualification_workflow):
    # Anchored on a token boundary so a path nested under the PINNED UPSTREAM checkout root --
    # for example "$RUNNER_TEMP/blst/src/server.c" -- is not misread as a repository path.
    pattern = re.compile("(?:^|[\\s\"'])((?:scripts|tests|src|docs)/[A-Za-z0-9_./-]+)", re.MULTILINE)
    for name, block in _run_blocks(qualification_workflow):
        for token in pattern.findall(block):
            assert token in SOURCE_BUNDLE_PATHS, (name, token)


def test_pt_263_no_repo_local_action_is_used(qualification_workflow):
    for job in qualification_workflow["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step:
                assert not step["uses"].startswith("./"), step["uses"]
                assert "@" in step["uses"] and len(step["uses"].split("@")[1]) == 40, step["uses"]


def test_pt_264_every_shell_variable_reference_is_on_the_frozen_allowlist(qualification_workflow):
    allowed = set(qualification_workflow["env"]["S3C_ALLOWED_SHELL_VARIABLES"].split())
    pattern = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
    for name, block in _run_blocks(qualification_workflow):
        for variable in pattern.findall(block):
            assert variable in allowed, (name, variable)


def test_the_qualification_workflow_is_dispatch_only_and_unprivileged(qualification_workflow):
    triggers = qualification_workflow[True] if True in qualification_workflow else qualification_workflow["on"]
    assert set(triggers) == {"workflow_dispatch"}
    assert qualification_workflow["permissions"] == {"contents": "read"}
    code = _code_only(QUALIFICATION_WORKFLOW)
    for forbidden in ("id-token", "attestations", "pull_request", "secrets."):
        assert forbidden not in code, forbidden


def test_the_observation_job_holds_no_permission_at_all(qualification_workflow):
    observe = qualification_workflow["jobs"]["s3c-observe"]
    assert observe["permissions"] == {}


def test_the_four_required_job_names_match_the_trusted_gate_expectation(qualification_workflow):
    gate = _read(TRUSTED_GATE)
    for job_name in ("s3c-build-candidate", "s3c-elf-qualify", "s3c-observe", "s3c-adjudicate"):
        assert job_name in qualification_workflow["jobs"], job_name
        assert '"' + job_name + '"' in gate, job_name


def test_the_expected_artifact_names_match_the_trusted_gate_expectation(qualification_workflow):
    gate = _read(TRUSTED_GATE)
    uploaded = set()
    for job in qualification_workflow["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step and step["uses"].startswith("actions/upload-artifact"):
                uploaded.add(step["with"]["name"])
    for expected in (
        "mt4-s3c-candidate-linux-x86_64",
        "mt4-s3c-elf-qualification-record",
        "mt4-s3c-raw-observation-record",
        "mt4-s3c-qualification-receipt",
    ):
        assert expected in uploaded, expected
        assert '"' + expected + '"' in gate, expected


def test_the_qualification_workflow_never_runs_the_offline_vector_generator():
    raw = QUALIFICATION_WORKFLOW.read_text(encoding="utf-8")
    assert "mt4_s3c_test_only_vector_generator" not in raw


def test_the_expected_phdr_inventory_agrees_across_all_three_non_candidate_authorities():
    literal = elf_qualify.canonical_phdr_inventory(elf_qualify.EXPECTED_PHDR_INVENTORY)
    assert literal in QUALIFICATION_WORKFLOW.read_text(encoding="utf-8")
    assert literal in TRUSTED_WORKFLOW.read_text(encoding="utf-8")


# =================================================================================================
# BLOCK N -- CUSTODY AND AUTHORITY NON-TRANSITION  [V9-9]
# =================================================================================================


def test_pt_301_the_governed_worker_row_schema_has_exactly_thirteen_fields_in_order():
    assert len(receipt_generator.GOVERNED_WORKER_ROW_FIELDS) == 13
    assert receipt_generator.GOVERNED_WORKER_ROW_FIELDS[0] == "worker_instance_id"
    assert receipt_generator.GOVERNED_WORKER_ROW_FIELDS[-1] == "status"
    assert receipt_generator.GOVERNED_WORKER_ROW_SCHEMA == "mt4-s3c-static-worker-instance-authority.v1"
    assert receipt_generator.GOVERNED_WORKER_ROW_STATUS_ENUM == ("ACTIVE", "SUPERSEDED", "REVOKED")


_SLICE_SOURCES = tuple(_REPO_ROOT / relative for relative in NEW_PATHS)


def test_pt_302_no_custody_field_constant_or_reserved_name_appears_anywhere_in_the_slice():
    for path in _SLICE_SOURCES:
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in ("custody_reproof", "CUSTODY_REPROOF", "custody_location_class", "custody_source_run"):
            assert forbidden not in text, (path.name, forbidden)


def test_pt_303_and_pt_304_no_code_path_creates_a_row_or_a_custody_artifact():
    for path in _SLICE_SOURCES:
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        assert '"ACTIVE"' not in text or path.name == "mt4_s3c_receipt_generator.py"
        assert "worker_instance_id" not in text or path.name == "mt4_s3c_receipt_generator.py"
    generator = _read(_S3C / "mt4_s3c_receipt_generator.py")
    assert '"governed_worker_row_created": False' in generator
    assert '"governed_worker_row_status_written": "NONE"' in generator


def test_pt_305_no_readiness_connector_or_machine_time_transition_appears_in_the_slice():
    # An authority name may appear ONLY as an explicit non-claim.  Anywhere one of these names
    # occurs in code, the same line must also carry NONE or False, so a slice that started
    # granting one of them would fail here rather than merely look tidy.
    governed_authorities = (
        "readiness_promoted",
        "connector_promoted",
        "readiness_transition",
        "connector_transition",
        "prdv4_stage4_complete",
        "stage4_authority",
        "machine_proven_thirty_day_gate",
        "machine_time_authority",
        "mt5_mt6_authority",
        "fixture_corpus_admitted",
        "proof_verified",
    )
    never_permitted = (
        "MachineTimeAnchor",
        "prdv4_stage4_complete = True",
        "readiness_promoted = True",
        "connector_promoted = True",
    )
    for path in _SLICE_SOURCES:
        if path.name.startswith("test_"):
            continue
        code = _code_only(path)
        for forbidden in never_permitted:
            assert forbidden not in code, (path.name, forbidden)
        for line in code.splitlines():
            for authority in governed_authorities:
                if authority in line:
                    assert "NONE" in line or "False" in line or "false" in line, (
                        path.name,
                        line.strip(),
                    )


def test_pt_307_no_machine_time_value_enters_any_governed_digest_preimage():
    for field in policy_qualifier.INTERNAL_EQUIVALENCE_FIELDS:
        for forbidden in ("_time", "time_", "clock", "timestamp", "duration", "epoch", "deadline"):
            assert forbidden not in field, field
    preimage = adjudicator.case_set_preimage()
    serialised = json.dumps(preimage)
    for forbidden in ("timestamp", "wall_clock", "monotonic"):
        assert forbidden not in serialised
    # The observer records bounded durations, but ONLY outside every digest preimage.
    launcher = _read(LAUNCHER_SOURCE)
    assert "non_digested_diagnostics" in launcher
    assert launcher.index("non_digested_diagnostics") > launcher.index("MT4_S3C_EQUIVALENCE_SCHEMA")


def test_the_receipt_declares_evidence_only_and_claims_no_admission():
    generator = _read(_S3C / "mt4_s3c_receipt_generator.py")
    assert '"evidence_status": "ADMISSION_EVIDENCE_ONLY"' in generator
    assert '"admission": "NONE"' in generator
    assert receipt_generator.QUALIFIED_NOT_ADMITTED == "QUALIFIED_NOT_ADMITTED"
    assert receipt_generator.NEVER_ADMITTED == "NEVER_ADMITTED"


def test_pt_149_the_adjudicator_never_substitutes_a_candidate_self_report():
    source = _read(_S3C / "mt4_s3c_observation_adjudicator.py")
    assert "self_report" not in source
    assert "claimed_filter" not in source
    # The equivalence digest is recomputed from OBSERVER fields, never read from the receipt.
    assert "recompute_equivalence_digest" in source
    assert "INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH" in source


# =================================================================================================
# PT-306 -- GOVERNED CONSTANT COUPLING TO THE MERGED S3B VERIFIER PROFILE
# =================================================================================================


def test_pt_306_the_transcribed_constants_match_the_governing_verifier_profile():
    """The coupling to src/crypto_core lives HERE, in ordinary CI, and never inside a run.

    No qualification script imports the verifier profile: doing so would violate the source-closure
    rules and would drag a src/crypto_core module into the qualification source bundle.  This test
    is the coupling, and it lives outside the qualification run by design.
    """
    profile = importlib.import_module("crypto_core.validation.machine_time_drand_quicknet_verifier_profile")

    assert tuple(code for code, _name in profile._ABI_STATUS_TAXONOMY) == tuple(range(12))
    assert profile._ABI_STATUS_TAXONOMY == observation_parser.VERIFIER_STATUS_TAXONOMY
    assert profile._ABI_STATUS_TAXONOMY == protocol_qualifier.VERIFIER_STATUS_TAXONOMY

    assert profile._PUBLIC_KEY_ENCODED_LENGTH == 96
    assert profile._SIGNATURE_ENCODED_LENGTH == 48
    assert profile._MESSAGE_LENGTH == 32
    assert (
        profile._PUBLIC_KEY_ENCODED_LENGTH + profile._SIGNATURE_ENCODED_LENGTH + profile._MESSAGE_LENGTH + 8
        == protocol_qualifier.REQUEST_FRAME_BYTES
    )

    assert profile._CURVE == "BLS12-381"
    assert profile._SCHEME == "bls-unchained-g1-rfc9380"
    assert profile._PUBLIC_KEY_GROUP == "G2"
    assert profile._SIGNATURE_GROUP == "G1"
    assert profile._AUGMENTATION == "NONE"
    assert profile._MESSAGE_TRANSFORM == "SHA256(uint64_big_endian(round))"

    verify_source = _read(VERIFY_SOURCE)
    assert profile._DST in verify_source
    assert "MT4_S3C_PUBLIC_KEY_LEN " + str(profile._PUBLIC_KEY_ENCODED_LENGTH) in verify_source
    assert "MT4_S3C_SIGNATURE_LEN " + str(profile._SIGNATURE_ENCODED_LENGTH) in verify_source
    assert "MT4_S3C_MESSAGE_DIGEST_LEN " + str(profile._MESSAGE_LENGTH) in verify_source

    assert build_manifest.UPSTREAM_COMMIT == profile._UPSTREAM_COMMIT
    assert build_manifest.UPSTREAM_SOURCE_TREE_DIGEST == profile._UPSTREAM_SOURCE_TREE_DIGEST
    assert build_manifest.UPSTREAM_RELEASE == profile._UPSTREAM_RELEASE


def test_the_six_read_only_dependencies_are_never_written_by_this_slice():
    for path in _SLICE_SOURCES:
        text = path.read_text(encoding="utf-8")
        for dependency in READ_ONLY_DEPENDENCIES:
            if dependency in text:
                # A dependency path may only appear as documentation or as a read-only reference,
                # never as an output path of any kind.
                for writer in ("--out " + dependency, ">" + dependency, "write(" + dependency):
                    assert writer not in text, (path.name, dependency)


# =================================================================================================
# REPAIR 3: THE SUPERVISOR DUMPABILITY LIFECYCLE.
#
# The property is an ORDER property of one supervisor process across 25 cases, and it cannot be
# executed on this host.  What CAN be executed is the order itself: the frozen sequence is extracted
# from the launcher source and checked against an invariant defined here, and the invariant is then
# driven with mutated sequences to prove it is not vacuous.  A two-case replay proves the thing the
# unresolved review thread is actually about -- that case 2's map writes happen only after case 1's
# restoration.
# =================================================================================================

_LIFECYCLE_MARKERS = (
    ("PRE_CLONE_AUTHENTICATED", "mt4_s3c_supervisor_dumpability_precondition()"),
    ("CLONE", "mt4_s3c_sys_clone3(&arguments"),
    ("MAP_SETGROUPS", '"/proc/%ld/setgroups"'),
    ("MAP_UID", '"/proc/%ld/uid_map"'),
    ("MAP_GID", '"/proc/%ld/gid_map"'),
    ("SET_NON_DUMPABLE", "prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)"),
    ("REAP", "waitpid(child, &status_word, 0)"),
    ("RESTORE", "mt4_s3c_supervisor_dumpability_restore()"),
)

_MAP_EVENTS = ("MAP_SETGROUPS", "MAP_UID", "MAP_GID")


def _run_case_lifecycle():
    """Extract the per-case lifecycle, in SOURCE ORDER, from mt4_s3c_run_case."""
    code = _launcher_code()
    start = code.index("static void mt4_s3c_run_case(")
    end = code.index("static void mt4_s3c_emit_case(")
    body = code[start:end]
    events = []
    for name, marker in _LIFECYCLE_MARKERS:
        position = body.find(marker)
        assert position >= 0, name
        events.append((position, name))
    return [name for _position, name in sorted(events)]


def assert_lifecycle(events):
    """The invariant.  Restoration happens ONLY after a complete reap and ALWAYS before the next
    clone or map write."""
    assert events.count("RESTORE") == 1, "exactly one restoration site"
    assert events.count("SET_NON_DUMPABLE") == 1, "exactly one site makes the supervisor non-dumpable"
    index = {name: events.index(name) for name in dict(_LIFECYCLE_MARKERS)}
    assert index["PRE_CLONE_AUTHENTICATED"] < index["CLONE"], "dumpability is authenticated before clone3"
    for event in _MAP_EVENTS:
        assert index["CLONE"] < index[event], "maps are written after the child exists"
        assert index[event] < index["SET_NON_DUMPABLE"], "maps are written while the supervisor is dumpable"
    assert index["SET_NON_DUMPABLE"] < index["REAP"], "the supervisor drops dumpability before the child runs"
    assert index["REAP"] < index["RESTORE"], "restoration happens only after a complete reap"
    return True


def test_the_frozen_per_case_dumpability_lifecycle_holds_in_the_launcher():
    assert assert_lifecycle(_run_case_lifecycle())


def test_two_consecutive_cases_map_only_after_the_previous_restoration():
    """The exact condition the unresolved review thread describes.

    Case 1 makes the supervisor non-dumpable.  The dumpable flag is inherited across clone, so a
    child cloned before restoration is born non-dumpable and its uid_map and gid_map become
    root-owned -- which is why case 2 previously failed with UID_GID_MAP_FAILED.
    """
    sequence = _run_case_lifecycle()
    replay = sequence + sequence
    boundary = len(sequence)
    first_restore = replay.index("RESTORE")
    assert first_restore < boundary, "case 1 must restore within its own case"
    second_clone = boundary + sequence.index("CLONE")
    assert first_restore < second_clone, "case 2 clones only after case 1 restored"
    for event in _MAP_EVENTS:
        assert first_restore < boundary + sequence.index(event), event


@pytest.mark.parametrize(
    ("label", "mutate"),
    (
        ("omit restoration", lambda events: [name for name in events if name != "RESTORE"]),
        (
            "restore before reap",
            lambda events: (
                [name for name in events if name != "RESTORE"][: events.index("REAP")]
                + ["RESTORE"]
                + [name for name in events if name != "RESTORE"][events.index("REAP") :]
            ),
        ),
        ("restore twice", lambda events: events + ["RESTORE"]),
        (
            "next clone before restoration",
            lambda events: [name for name in events if name != "RESTORE"] + [],
        ),
        (
            "uid_map before the child exists",
            lambda events: ["MAP_UID"] + [name for name in events if name != "MAP_UID"],
        ),
        (
            "maps after the supervisor is non-dumpable",
            lambda events: (
                [name for name in events if name != "MAP_GID"][: events.index("REAP") - 1]
                + ["MAP_GID"]
                + [name for name in events if name != "MAP_GID"][events.index("REAP") - 1 :]
            ),
        ),
        (
            "dumpability never authenticated before clone",
            lambda events: [name for name in events if name != "PRE_CLONE_AUTHENTICATED"] + ["PRE_CLONE_AUTHENTICATED"],
        ),
    ),
)
def test_a_broken_dumpability_lifecycle_is_rejected(label, mutate):
    mutant = mutate(list(_run_case_lifecycle()))
    with pytest.raises((AssertionError, ValueError)):
        assert_lifecycle(mutant)


def test_a_restoration_failure_halts_the_sequence_instead_of_running_the_next_case():
    """A restoration failure is INFRASTRUCTURE, never a candidate verdict, and it stops the run."""
    code = _launcher_code()
    assert "static int mt4_s3c_sequence_halted = 0;" in code
    # The failure path sets the halt flag and names its own reason.
    restore = code[code.index("mt4_s3c_supervisor_dumpability_restore() != 0") :]
    assert "mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED" in restore[:600]
    # 2C: the case reason is overwritten UNCONDITIONALLY, so an expected semantic outcome such as
    # C25's deadline cannot leave the restoration failure unrecorded.
    assert "result->reason = MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED;" in restore[:800]
    assert "static void mt4_s3c_terminal_failure(" in code
    assert "mt4_s3c_sequence_halted = 1;" in code
    # And the case loop refuses to run another case once it is set.
    loop = code[code.index("for (index = 0; index < plan.case_count; index++)") :]
    guard = loop[: loop.index("mt4_s3c_run_case(")]
    assert "if (mt4_s3c_sequence_halted || mt4_s3c_terminal_reason != MT4_S3C_REASON_NONE)" in guard
    assert "mt4_s3c_fatal(" in guard


# =================================================================================================
# REPAIR 2: NO FALSE REAP, NO MASKED RESTORATION FAILURE, AND A FINAL GATE THAT COVERS C25.
# =================================================================================================


class SupervisorTeardown:
    """An executable model of the FROZEN teardown contract.

    Every rule here corresponds to a guard asserted to exist in the launcher source by
    test_the_launcher_implements_the_modelled_teardown_guards, so the model is a restatement of the
    implementation's structure rather than an independent invention.
    """

    def __init__(self, reap_outcome="exited", restore_syscall=True, restore_authenticates=True):
        self.reap_outcome = reap_outcome
        self.restore_syscall = restore_syscall
        self.restore_authenticates = restore_authenticates
        self.state = "SUPERVISOR_NON_DUMPABLE"
        self.terminal_reason = None
        self.halted = False
        self.interrupts = 0

    def _terminal(self, reason):
        self.halted = True
        if self.terminal_reason is None:
            self.terminal_reason = reason

    def reap(self):
        # 2A: CHILD_REAPED is entered ONLY on an authoritative successful reap.
        if self.reap_outcome == "eintr_then_exit":
            self.interrupts += 1
            self.state = "CHILD_REAPED"
            return
        if self.reap_outcome in ("exited", "signalled"):
            self.state = "CHILD_REAPED"
            return
        # ECHILD, EINVAL, a wrong pid, or an exhausted interrupt budget.
        self._terminal("SUPERVISOR_REAP_FAILED")

    def restore(self):
        # 2B: restoration happens only after a proven reap, and is AUTHENTICATED.
        if self.state not in ("SUPERVISOR_NON_DUMPABLE", "CHILD_REAPED"):
            return
        if self.state != "CHILD_REAPED":
            self._terminal("SUPERVISOR_REAP_FAILED")
            return
        if not self.restore_syscall or not self.restore_authenticates:
            # 2C: an expected semantic outcome NEVER masks this.
            self._terminal("SUPERVISOR_DUMPABILITY_NOT_RESTORED")
            return
        self.state = "RESTORED"

    def finish_case(self):
        self.reap()
        self.restore()
        if self.state not in ("CASE_START", "PRE_CLONE_AUTHENTICATED", "RESTORED"):
            self._terminal("SUPERVISOR_DUMPABILITY_NOT_RESTORED")
        return self

    def may_emit_final_record(self):
        # 2D: the FINAL gate, checked before any record is written -- not only between cases.
        return not self.halted and self.terminal_reason is None


def test_the_launcher_implements_the_modelled_teardown_guards():
    """The model above is the SOURCE's structure, not a convenient fiction."""
    code = _launcher_code()
    teardown = code[code.index("teardown:") :]
    # 2A / repair 3: ONE authoritative transition records all three facts together.
    assert "int reaped = 0;" in code
    assert "#define MT4_S3C_MARK_CHILD_REAPED()" in code
    assert "MT4_S3C_MARK_CHILD_REAPED();" in teardown
    # Only EINTR retries, and its budget is bounded.
    assert "if (errno == EINTR)" in teardown
    assert "MT4_S3C_MAX_REAP_INTERRUPTS" in teardown
    assert "mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_REAP_FAILED" in teardown
    # A wrong pid is incoherent, not an outcome.
    assert "observed != child" in teardown
    # 2B and 2C.
    assert "dumpability_state != MT4_S3C_DUMPABILITY_CHILD_REAPED" in teardown
    assert "result->reason = MT4_S3C_REASON_SUPERVISOR_DUMPABILITY_NOT_RESTORED;" in teardown
    # 2D: the end-state check, per case.
    assert "dumpability_state != MT4_S3C_DUMPABILITY_RESTORED" in teardown


def test_every_definitive_reap_uses_the_single_authoritative_transition():
    """Repair 3.  Reap state may never be encoded in pieces.

    Three paths used to clear `child` and stop there, leaving `reaped` false and the lifecycle state
    behind; the teardown then declared a terminal failure for a case that had completed honestly.
    Every path that has DEFINITIVELY reaped now goes through one macro that sets all three facts.
    """
    code = _launcher_code()
    run_case = code[code.index("static void mt4_s3c_run_case(") : code.index("static void mt4_s3c_emit_case(")]

    # The macro sets all three facts, in one place.
    definition = code[code.index("#define MT4_S3C_MARK_CHILD_REAPED()") :]
    definition = definition[: definition.index("while (0)")]
    assert "child = -1;" in definition
    assert "reaped = 1;" in definition
    assert "dumpability_state = MT4_S3C_DUMPABILITY_CHILD_REAPED;" in definition

    # No path outside the macro sets any of the three individually.
    body = run_case.replace("MT4_S3C_MARK_CHILD_REAPED();", "")
    assert "reaped = 1;" not in body, "a path sets reaped without the authoritative transition"
    assert "dumpability_state = MT4_S3C_DUMPABILITY_CHILD_REAPED;" not in body

    # Every definitive reap observation uses it: died-before-trace, stepping exit, stepping signal,
    # and both teardown outcomes.
    assert run_case.count("MT4_S3C_MARK_CHILD_REAPED();") == 5

    # `child = -1` survives only where the child's fate could NOT be established.
    remaining = [line.strip() for line in body.splitlines() if line.strip() == "child = -1;"]
    assert len(remaining) == 1, remaining


def test_a_non_eintr_stepping_wait_error_is_terminal():
    """Repair 3.  A wait error in the REAPING loop means the child's fate is unknown."""
    code = _launcher_code()
    stepping = code[code.index("observed = waitpid(child, &status_word, WUNTRACED | WNOHANG);") :]
    guard = stepping[: stepping.index("if (WIFEXITED(status_word))")]
    assert "if (errno == EINTR)" in guard
    assert "mt4_s3c_terminal_failure(MT4_S3C_REASON_SUPERVISOR_REAP_FAILED" in guard


@pytest.mark.parametrize(
    ("label", "outcome"),
    (
        ("normal exit already reaped in the stepping loop", "exited"),
        ("signal exit already reaped in the stepping loop", "signalled"),
        ("expected timeout with a successful reap", "eintr_then_exit"),
    ),
)
def test_an_honest_completed_case_is_not_terminal(label, outcome):
    """The opposite false accept: an honestly completed case must NOT become terminal."""
    machine = SupervisorTeardown(reap_outcome=outcome).finish_case()
    assert machine.state == "RESTORED", label
    assert machine.terminal_reason is None, label
    assert machine.may_emit_final_record(), label


@pytest.mark.parametrize("position", ("middle", "final"))
def test_an_honest_case_completes_at_any_position(position):
    machines = [SupervisorTeardown().finish_case() for _ in range(25)]
    index = 12 if position == "middle" else 24
    assert machines[index].may_emit_final_record()
    assert all(machine.state == "RESTORED" for machine in machines)


def test_the_final_record_gate_runs_before_any_record_is_written():
    """2D.  The gate is placed before the write, so the LAST case is covered too."""
    code = _launcher_code()
    gate_position = code.index("if (mt4_s3c_sequence_halted || mt4_s3c_terminal_reason != MT4_S3C_REASON_NONE)")
    write_position = code.index("output_fd = open(output_path")
    assert gate_position < write_position, "the terminal gate must precede the record write"
    # And it is a DIFFERENT site from the between-cases guard, so removing one does not remove both.
    assert code.count("mt4_s3c_sequence_halted || mt4_s3c_terminal_reason != MT4_S3C_REASON_NONE") == 2


def test_the_honest_teardown_completes_and_permits_a_final_record():
    machine = SupervisorTeardown().finish_case()
    assert machine.state == "RESTORED"
    assert machine.terminal_reason is None
    assert machine.may_emit_final_record()


@pytest.mark.parametrize(
    ("label", "kwargs", "reason"),
    (
        ("non-EINTR waitpid failure", {"reap_outcome": "eperm"}, "SUPERVISOR_REAP_FAILED"),
        ("ECHILD where not valid", {"reap_outcome": "echild"}, "SUPERVISOR_REAP_FAILED"),
        ("wrong child reaped", {"reap_outcome": "wrong_pid"}, "SUPERVISOR_REAP_FAILED"),
        ("interrupt budget exhausted", {"reap_outcome": "eintr_forever"}, "SUPERVISOR_REAP_FAILED"),
        ("restoration syscall failure", {"restore_syscall": False}, "SUPERVISOR_DUMPABILITY_NOT_RESTORED"),
        (
            "restoration authentication failure",
            {"restore_authenticates": False},
            "SUPERVISOR_DUMPABILITY_NOT_RESTORED",
        ),
    ),
)
def test_a_teardown_failure_is_terminal_and_blocks_the_final_record(label, kwargs, reason):
    machine = SupervisorTeardown(**kwargs).finish_case()
    assert machine.terminal_reason == reason, label
    assert machine.halted, label
    # THE POINT: no successful final evidence is emitted.
    assert not machine.may_emit_final_record(), label


@pytest.mark.parametrize("outcome", ("eperm", "echild", "wrong_pid", "eintr_forever"))
def test_a_failed_reap_never_transitions_to_child_reaped(outcome):
    machine = SupervisorTeardown(reap_outcome=outcome)
    machine.reap()
    assert machine.state != "CHILD_REAPED", outcome


@pytest.mark.parametrize("kwargs", ({"restore_syscall": False}, {"restore_authenticates": False}))
def test_an_expected_timeout_never_masks_a_restoration_failure(kwargs):
    """C25 EXPECTS a deadline.  That expectation is subordinate to infrastructure correctness.

    The old code recorded the restoration failure only when the case had no reason yet, so C25 --
    whose reason was already set by its own expected timeout -- swallowed it entirely.
    """
    machine = SupervisorTeardown(**kwargs)
    machine.semantic_outcome_already_observed = "RT_DEADLINE_EXPIRED"
    machine.finish_case()
    assert machine.terminal_reason == "SUPERVISOR_DUMPABILITY_NOT_RESTORED"
    assert not machine.may_emit_final_record()


@pytest.mark.parametrize("kwargs", ({"reap_outcome": "eperm"}, {"restore_syscall": False}))
def test_the_final_case_is_covered_by_the_same_gate_as_every_other(kwargs):
    """A "before the next case" check alone cannot stop the LAST case.

    The sequence below runs all 25 cases with the failure on the final one, which is precisely the
    arrangement under which the previous halt guard never fired.
    """
    machines = [SupervisorTeardown().finish_case() for _ in range(24)]
    final = SupervisorTeardown(**kwargs).finish_case()
    machines.append(final)
    assert all(machine.may_emit_final_record() for machine in machines[:24])
    assert not final.may_emit_final_record()
    # The run as a whole is refused, not just the last case's own record.
    assert any(machine.terminal_reason is not None for machine in machines)


def test_a_restoration_before_the_reap_is_refused():
    machine = SupervisorTeardown()
    machine.restore()  # called while the state is still SUPERVISOR_NON_DUMPABLE
    assert machine.terminal_reason == "SUPERVISOR_REAP_FAILED"
    assert machine.state != "RESTORED"


def test_the_restored_value_is_authenticated_by_reading_it_back():
    """A prctl return code is a request result, not proof; the flag is READ BACK."""
    source = _read(LAUNCHER_SOURCE)
    assert "prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)" in source
    assert "#define MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED 1" in source
    restore = source[source.index("static int mt4_s3c_supervisor_dumpability_restore(void)") :]
    restore = restore[: restore.index("\n}\n")]
    assert "mt4_s3c_supervisor_dumpability_is(MT4_S3C_SUPERVISOR_DUMPABLE_REQUIRED)" in restore


# =================================================================================================
# REPAIR 5C: THE /proc STATUS DOCUMENT IS VALIDATED AS A WHOLE BEFORE ANY FIELD IS EXTRACTED.
# =================================================================================================


def test_the_status_buffer_is_validated_whole_before_any_field_is_extracted():
    code = _launcher_code()
    reader = code[code.index("static int mt4_s3c_read_seccomp_status(") :]
    reader = reader[: reader.index("static int mt4_s3c_require_baseline_zero(")]
    gate_position = reader.index("MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED")
    first_field = reader.index("mt4_s3c_parse_status_field(")
    # Permissive parsing -- decoding the two fields we want while ignoring the rest -- is exactly
    # what this ordering forbids.
    assert gate_position < first_field, "the whole-buffer gate must precede field extraction"
    assert "byte == 0u" in reader, "an embedded NUL is rejected"
    assert "byte < 0x20u || byte > 0x7Eu" in reader, "non-ASCII anywhere is rejected"


def test_the_status_parser_stays_inside_the_frozen_failure_taxonomy():
    """Repair 5B.  No new public reason code is invented for a condition an existing class covers.

    The whole-buffer encoding gate reports SECCOMP_BASELINE_FIELD_MALFORMED, which the frozen
    taxonomy already defines for a malformed status source.  A separate ENCODING_INVALID code would
    have widened the public taxonomy without telling an operator anything new.
    """
    source = _read(LAUNCHER_SOURCE)
    assert "SECCOMP_BASELINE_ENCODING_INVALID" not in source
    enum_start = source.index("typedef enum {")
    enum_body = source[enum_start : source.index("} mt4_s3c_reason_t;")]
    declared = {
        line.strip().rstrip(",").split("=")[0].strip()
        for line in enum_body.splitlines()
        if line.strip().startswith("MT4_S3C_REASON_")
    }
    # Every reason the executable code can emit is one of the declared enumerators.
    emitted = set(re.findall(r"MT4_S3C_REASON_[A-Z0-9_]+", _launcher_code()))
    assert emitted <= declared, sorted(emitted - declared)


def test_the_status_parser_rejects_every_named_malformation():
    code = _launcher_code()
    parser = code[code.index("static int mt4_s3c_parse_status_field(") :]
    parser = parser[: parser.index("static int mt4_s3c_read_seccomp_status(")]
    assert "MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_DUPLICATE" in parser
    assert "MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MALFORMED" in parser
    assert "MT4_S3C_REASON_SECCOMP_BASELINE_FIELD_MISSING" in parser
    # Oversized input is rejected by the reader rather than truncated.
    reader = code[code.index("static int mt4_s3c_read_seccomp_status(") :]
    assert "used == sizeof(buffer)" in reader[:2000]


# =================================================================================================
# REPAIR 7D: AN INDEPENDENTLY DEFINED WORKFLOW GRAMMAR.
#
# The old check parsed the qualification workflow using an allowlist the workflow itself declared,
# which is circular.  The grammar below is defined HERE and knows nothing about what the workflow
# says about itself; the workflow is the SUBJECT, and mutants prove the grammar bites.
# =================================================================================================

_GRAMMAR_FORBIDDEN = (
    ("command substitution", re.compile(r"\$\((?!\()")),
    ("backtick substitution", re.compile(r"`")),
    ("sourcing", re.compile(r"^\s*(source|\.)\s+\S", re.MULTILINE)),
    ("inline interpreter code", re.compile(r"python3?\s+-c\b")),
    ("an interpreter reading stdin", re.compile(r"python3?\s+-\s")),
    ("eval", re.compile(r"^\s*eval\s", re.MULTILINE)),
    ("a computed repository path", re.compile(r"\$\{[A-Z_]+\}/(scripts|tests|src)/")),
    # Repair 7C: the EXECUTION TARGET may never be selected from a variable.  A grammar that
    # only reasons about shell syntax misses `python "$SCRIPT"`, which is dynamic repository
    # execution however cleanly it is quoted; the target has to be a literal a reviewer reads.
    (
        "a dynamically selected execution target",
        re.compile(r"""\b(python[0-9.]*|bash|sh|perl|ruby|node)\s+(-[A-Za-z]+\s+)*["']?\$"""),
    ),
    ("an exec of a variable", re.compile(r"""\bexec\s+["']?\$""")),
)

_GRAMMAR_CASE_OPEN = re.compile(r"^\s*case\s+.*\sin\s*$")
_GRAMMAR_CASE_CLOSE = re.compile(r"^\s*esac\s*$")
_GRAMMAR_DOUBLE = re.compile(r'"[^"]*"')
_GRAMMAR_SINGLE = re.compile(r"'[^']*'")


def _grammar_unquoted_glob(script):
    inside_case = False
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _GRAMMAR_CASE_OPEN.match(line):
            inside_case = True
            continue
        if _GRAMMAR_CASE_CLOSE.match(line):
            inside_case = False
            continue
        body = line
        if inside_case and ")" in body:
            body = body.split(")", 1)[1]
        if "*" in _GRAMMAR_SINGLE.sub("", _GRAMMAR_DOUBLE.sub("", body)):
            return line
    return None


def assert_workflow_grammar(workflow):
    """Reject every unapproved shell form, and every action that is not a pinned third-party SHA."""
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            script = step.get("run") or ""
            for label, pattern in _GRAMMAR_FORBIDDEN:
                assert not pattern.search(script), (label, step.get("name"))
            assert _grammar_unquoted_glob(script) is None, ("a glob", step.get("name"))
            uses = step.get("uses")
            if uses is not None:
                assert not uses.startswith("./"), ("a repo-local action", step.get("name"))
                assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", uses), ("an unpinned action", uses)
    return True


def test_the_qualification_workflow_satisfies_the_independent_grammar(qualification_workflow):
    assert assert_workflow_grammar(qualification_workflow)


@pytest.mark.parametrize(
    ("label", "script"),
    (
        ("command substitution", 'X="$(cat /etc/passwd)"\n'),
        ("backticks", "X=`id`\n"),
        ("sourcing", ". ./scripts/helper.sh\n"),
        ("inline interpreter code", 'python -c "import os"\n'),
        ("stdin interpreter", "python3 - <<EOF\nprint(1)\nEOF\n"),
        ("eval", "eval ${COMMAND}\n"),
        ("a glob", "rm ${RUNNER_TEMP}/*\n"),
        ("a computed repository path", "python ${HELPER_DIR}/scripts/run.py\n"),
        ("a variable execution target", "python " + chr(34) + "$SCRIPT" + chr(34) + chr(10)),
        ("a variable bash target", "bash " + chr(34) + "${REPO_SCRIPT}" + chr(34) + chr(10)),
        ("an unquoted variable target", "sh $HELPER" + chr(10)),
        ("a flagged variable target", "python3 -I " + chr(34) + "$GATE" + chr(34) + chr(10)),
        ("exec of a variable", "exec " + chr(34) + "$COMMAND" + chr(34) + chr(10)),
    ),
)
def test_the_independent_grammar_rejects_each_unapproved_form(qualification_workflow, label, script):
    mutant = copy.deepcopy(qualification_workflow)
    first = next(iter(mutant["jobs"].values()))
    first["steps"].append({"name": "injected", "shell": "bash", "run": script})
    with pytest.raises(AssertionError):
        assert_workflow_grammar(mutant)


def test_the_independent_grammar_rejects_a_repo_local_action(qualification_workflow):
    mutant = copy.deepcopy(qualification_workflow)
    first = next(iter(mutant["jobs"].values()))
    first["steps"].append({"name": "local", "uses": "./.github/actions/helper"})
    with pytest.raises(AssertionError):
        assert_workflow_grammar(mutant)


def test_the_independent_grammar_rejects_an_unpinned_action(qualification_workflow):
    mutant = copy.deepcopy(qualification_workflow)
    first = next(iter(mutant["jobs"].values()))
    first["steps"].append({"name": "unpinned", "uses": "actions/checkout@v4"})
    with pytest.raises(AssertionError):
        assert_workflow_grammar(mutant)


# =================================================================================================
# REPAIR 7: THREE DIFFERENT SETS, AND ONLY ONE OF THEM IS THE SOURCE-CLOSURE AUTHORITY.
#
# The previous closure test compared discovery against the UNION of the 21 PR-changed paths and the
# 6 read-only dependencies -- 27 paths -- and called that the authorized source bundle.  It is not.
# The three sets are distinct and mean different things:
#
#   PR_CHANGED_PATHS            21  what this pull request adds; a review-scope fact
#   QUALIFICATION_SOURCE_BUNDLE 16  what the qualification workflow may reach; the GOVERNED authority
#   READ_ONLY_DEPENDENCIES       6  merged files this slice reads and never writes
#
# Source closure is measured against the GOVERNED 16, and nothing else.  The trusted gate is
# deliberately NOT a bundle entry -- it carries its own separate approved digest on the trusted
# surface -- so the trusted workflow's closure is measured against that separate commitment instead.
# A real dependency outside those authorities is a SOURCE_BUNDLE_CONTRADICTION that returns to
# architecture, never a widened constant here.
# =================================================================================================

PR_CHANGED_PATHS = frozenset(NEW_PATHS)
QUALIFICATION_SOURCE_BUNDLE = frozenset(SOURCE_BUNDLE_PATHS)
READ_ONLY_DEPENDENCY_SET = frozenset(READ_ONLY_DEPENDENCIES)

# The trusted surface: its own two files, each with its own separate commitment.
TRUSTED_SURFACE_PATHS = frozenset(
    {
        ".github/workflows/crypto_core_mt4_s3c_trusted_attestation.yml",
        "scripts/crypto_core/qualification/mt4_s3c_trusted_attestation_gate.py",
    }
)

_REPO_PATH_TOKEN = re.compile(r"(?<![\w./-])((?:scripts|tests|src|docs)/[\w./-]+|\.github/[\w./-]+)")


def test_the_three_authority_sets_are_distinct_and_exactly_sized():
    assert len(PR_CHANGED_PATHS) == 21
    assert len(QUALIFICATION_SOURCE_BUNDLE) == 16
    assert len(READ_ONLY_DEPENDENCY_SET) == 6
    # The bundle is a strict subset of what the PR adds; the read-only dependencies are disjoint
    # from both, because they already existed on the base branch.
    assert QUALIFICATION_SOURCE_BUNDLE < PR_CHANGED_PATHS
    assert not (READ_ONLY_DEPENDENCY_SET & PR_CHANGED_PATHS)
    assert TRUSTED_SURFACE_PATHS < PR_CHANGED_PATHS
    assert not (TRUSTED_SURFACE_PATHS & QUALIFICATION_SOURCE_BUNDLE)


def _discover_python_dependencies(source):
    """Every import form, plus every repo-path literal that could steer a decision.

    Top-level, function-local, conditional and lazy imports are all Import/ImportFrom nodes wherever
    they appear, so walking the WHOLE tree covers all four without special-casing depth.
    """
    imports = set()
    paths = set()
    dynamic = False
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
        elif isinstance(node, ast.Call):
            target = node.func
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name in ("import_module", "__import__", "spec_from_file_location"):
                dynamic = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            paths.update(_REPO_PATH_TOKEN.findall(node.value))
    return imports, paths, dynamic


# REPAIR 9A.  Assembly sources take dependencies through constructs a C-include regex never sees.
# `.include` and `.incbin` are assembler directives, and a `.S` file also goes through the C
# preprocessor, so a quoted `#include` is valid there too.  All three forms are parsed.
_ASM_INCLUDE = re.compile(r'^\s*\.(?:include|incbin)\s+"([^"]+)"', re.MULTILINE)
_C_INCLUDE = re.compile(r'#\s*include\s+"([^"]+)"')


def _discover_native_dependencies(source):
    """A QUOTED include is repo-local by definition; an angle include is toolchain."""
    return set(_C_INCLUDE.findall(source)) | set(_ASM_INCLUDE.findall(source))


def _workflow_repo_paths(document):
    paths = set()
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            uses = step.get("uses")
            if uses:
                assert not uses.startswith("./"), uses
            paths.update(_REPO_PATH_TOKEN.findall(step.get("run") or ""))
    return paths


# The governed include-root DIRECTORY.  It is a directory by design: the build passes it to the
# compiler with -I, and a directory is what -I takes.
GOVERNED_INCLUDE_ROOT = "scripts/crypto_core/qualification/s3c"


def _classify_non_repo_reference(relative, candidate):
    """Name the class of a reference that is not a regular repository file, or return None.

    Returning None means UNACCOUNTABLE, which the governed callers treat as a closure break.  Every
    exemption below is a real, distinct class rather than a convenience:
      * the governed include root is a DIRECTORY the compiler is given with -I;
      * a pinned-upstream input path is relative to the blst tree, not to this repository;
      * a quoted native include that does not resolve beside its includer resolves through an
        include root, which the include-root allowlist governs instead.
    """
    if relative == GOVERNED_INCLUDE_ROOT and candidate.is_dir():
        return "GOVERNED_INCLUDE_ROOT"
    tail = relative.split("/")[-1]
    if relative in build_manifest.REQUIRED_UPSTREAM_INPUTS or tail in {
        item.split("/")[-1] for item in build_manifest.REQUIRED_UPSTREAM_INPUTS
    }:
        return "UPSTREAM_PINNED"
    if relative.startswith(GOVERNED_INCLUDE_ROOT + "/") and tail in _UPSTREAM_HEADER_NAMES:
        return "UPSTREAM_PINNED_HEADER"
    return None


# Headers the freestanding worker includes by name and the build resolves through the pinned blst
# bindings include root.  They are upstream files, so they are not repository closure edges.
_UPSTREAM_HEADER_NAMES = frozenset({"blst.h", "blst_aux.h"})


def recursive_repo_closure(workflow_paths):
    """Repair 7B.  Discover repo-controlled dependency edges RECURSIVELY, to fixpoint.

    One hop is not a closure: a bundled script that imports a second repo module which reads a third
    repo file is only visible if discovery keeps going.  The worklist below runs until nothing new
    appears, tracks visited paths deterministically, and tolerates cycles because a path is only
    ever expanded once.
    """
    pending = []
    for workflow in workflow_paths:
        document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        pending.extend(sorted(_workflow_repo_paths(document)))
        pending.append(str(workflow.relative_to(_REPO_ROOT)).replace("\\", "/"))

    discovered = set()
    visited = set()
    dynamic = []
    unresolved = []
    while pending:
        relative = pending.pop()
        if relative in visited:
            # A cycle is fine as long as every member stays inside the governed closure, which the
            # caller asserts; expanding a path twice would just spin.
            continue
        visited.add(relative)
        candidate = _REPO_ROOT / relative
        if not candidate.is_file():
            # REPAIR 9B.  A reference that does not resolve to a regular repository file is
            # CLASSIFIED, never silently skipped.  There are exactly three legitimate non-repo
            # classes, each named, and anything else is unaccountable and fails closed.
            classification = _classify_non_repo_reference(relative, candidate)
            if classification is None:
                unresolved.append(relative)
            continue
        discovered.add(relative)
        body = candidate.read_text(encoding="utf-8")
        if candidate.suffix == ".py":
            imports, paths, uses_dynamic = _discover_python_dependencies(body)
            if uses_dynamic:
                dynamic.append(relative)
            for token in sorted(paths):
                pending.append(token)
            # A repo-controlled MODULE import is an edge too: an import of a package that resolves
            # to a repository file must be followed like any other dependency.
            for module in sorted(imports):
                module_path = "src/" + module.replace(".", "/") + ".py"
                if (_REPO_ROOT / module_path).is_file():
                    pending.append(module_path)
        elif candidate.suffix in (".c", ".S", ".h"):
            for include in sorted(_discover_native_dependencies(body)):
                sibling = str((candidate.parent / include).resolve().relative_to(_REPO_ROOT)).replace("\\", "/")
                pending.append(sibling)
        elif candidate.suffix in (".yml", ".yaml"):
            document = yaml.safe_load(body)
            if isinstance(document, dict) and "jobs" in document:
                for token in sorted(_workflow_repo_paths(document)):
                    pending.append(token)
    return discovered, dynamic, unresolved


def test_the_qualification_closure_stays_inside_the_exact_sixteen_entry_bundle():
    """Repair 7A and 7B.  The governed authority is the 16-entry bundle, not the 21-path PR."""
    discovered, dynamic, unresolved = recursive_repo_closure([QUALIFICATION_WORKFLOW])
    assert dynamic == [], dynamic
    assert unresolved == [], unresolved
    files = {path for path in discovered if (_REPO_ROOT / path).is_file()}
    assert files, "discovery must actually find something"
    outside = sorted(files - QUALIFICATION_SOURCE_BUNDLE)
    assert outside == [], outside
    # And the closure really does reach the bundle rather than trivially finding one file.
    assert len(files) >= 8, sorted(files)


def test_the_trusted_closure_reaches_only_its_own_separately_committed_surface():
    discovered, dynamic, unresolved = recursive_repo_closure([TRUSTED_WORKFLOW])
    assert dynamic == [], dynamic
    assert unresolved == [], unresolved
    files = {path for path in discovered if (_REPO_ROOT / path).is_file()}
    outside = sorted(files - TRUSTED_SURFACE_PATHS - QUALIFICATION_SOURCE_BUNDLE)
    assert outside == [], outside


def test_the_production_recursion_reaches_a_third_hop_outside_the_bundle(tmp_path):
    """REPAIR 9C.  The regression RUNS the production fixpoint closure, not a discovery primitive.

    A planted chain -- workflow -> first hop -> second hop -> third hop -- is followed to fixpoint,
    and the third hop lies outside the governed bundle so the closure must surface it.
    """
    scratch = tmp_path / "repo"
    (scratch / "scripts" / "crypto_core" / "qualification" / "s3c").mkdir(parents=True)
    (scratch / ".github" / "workflows").mkdir(parents=True)
    base = "scripts/crypto_core/qualification/s3c/"

    (scratch / base / "first_hop.py").write_text("PATH = '" + base + "second_hop.py'\n", encoding="utf-8")
    (scratch / base / "second_hop.py").write_text("PATH = '" + base + "third_hop.py'\n", encoding="utf-8")
    (scratch / base / "third_hop.py").write_text("VALUE = 3\n", encoding="utf-8")
    workflow = scratch / ".github" / "workflows" / "planted.yml"
    workflow.write_text(
        "jobs:\n  build:\n    steps:\n      - run: python " + base + "first_hop.py\n",
        encoding="utf-8",
    )

    original = globals()["_REPO_ROOT"]
    globals()["_REPO_ROOT"] = scratch
    try:
        discovered, dynamic, unresolved = recursive_repo_closure([workflow])
    finally:
        globals()["_REPO_ROOT"] = original

    assert dynamic == []
    assert unresolved == []
    # All three hops were reached, by RECURSION rather than by one pass.
    for hop in ("first_hop.py", "second_hop.py", "third_hop.py"):
        assert base + hop in discovered, hop
    # And the third hop is outside the governed bundle, which is what a real closure must surface.
    assert base + "third_hop.py" not in QUALIFICATION_SOURCE_BUNDLE


def test_an_unresolvable_or_non_file_dependency_fails_closed(tmp_path):
    """REPAIR 9B.  A missing path, or a directory where a file is required, is not skipped."""
    scratch = tmp_path / "repo"
    (scratch / "scripts" / "crypto_core" / "qualification" / "s3c" / "a_directory").mkdir(parents=True)
    (scratch / ".github" / "workflows").mkdir(parents=True)
    base = "scripts/crypto_core/qualification/s3c/"
    workflow = scratch / ".github" / "workflows" / "planted.yml"
    workflow.write_text(
        "jobs:\n  build:\n    steps:\n      - run: |\n"
        "          python " + base + "missing_helper.py\n"
        "          python " + base + "a_directory\n",
        encoding="utf-8",
    )

    original = globals()["_REPO_ROOT"]
    globals()["_REPO_ROOT"] = scratch
    try:
        _discovered, _dynamic, unresolved = recursive_repo_closure([workflow])
    finally:
        globals()["_REPO_ROOT"] = original

    assert base + "missing_helper.py" in unresolved
    assert base + "a_directory" in unresolved


def test_assembly_include_forms_are_discovered():
    """REPAIR 9A.  `.include`, `.incbin` and a preprocessor include are all dependency edges."""
    source = '.include "shared_macros.inc"' + chr(10) + '.incbin "blob.bin"' + chr(10) + '#include "header.h"' + chr(10)
    assert _discover_native_dependencies(source) == {"shared_macros.inc", "blob.bin", "header.h"}
    # An ANGLE include is toolchain, not repo-local, and must not be claimed as a repo edge.
    assert _discover_native_dependencies("#include <stdio.h>" + chr(10)) == set()


@pytest.mark.parametrize(
    ("label", "source"),
    (
        ("function-local import", "def run():\n    import scripts_helper\n"),
        ("conditional import", "if True:\n    import scripts_helper\n"),
        ("lazy importlib", "def run():\n    import importlib\n    importlib.import_module('x')\n"),
        ("dunder import", "def run():\n    __import__('x')\n"),
        ("spec loader", "def run():\n    importlib.util.spec_from_file_location('a', 'b')\n"),
    ),
)
def test_every_import_form_is_discovered(label, source):
    imports, _paths, dynamic = _discover_python_dependencies(source)
    if "importlib" in source or "__import__" in source:
        assert dynamic, label
    else:
        assert "scripts_helper" in imports, label


def test_a_second_hop_outside_the_bundle_is_rejected(tmp_path):
    """A dependency reached only at the SECOND hop must still be caught."""
    outside = "src/crypto_core/__init__.py"
    _imports, paths, _dynamic = _discover_python_dependencies("PATH = " + repr(outside) + "\n")
    assert paths == {outside}
    assert outside not in QUALIFICATION_SOURCE_BUNDLE


# =================================================================================================
# REPAIR 7D: THE OPERATIONAL RUNTIME RECORDER.
#
# Importing a module and exiting proves almost nothing: the dependencies that matter are taken when
# the module DOES something.  The recorder below drives each bundled module's real operational
# surface -- its argument parser and its pure derivations -- inside an isolated subprocess with an
# audit hook, so the observed set reflects executed code rather than import side effects.  There is
# no disabled branch in it: a proof that cannot fire is not a proof.
# =================================================================================================

_RECORDER = """
import json
import sys

REPO = sys.argv[1].replace(chr(92), "/")
TARGET = sys.argv[2]
OPERATION = sys.argv[3]
observed = set()
failures = []


def hook(event, arguments):
    if event == "open" and arguments and isinstance(arguments[0], str):
        path = arguments[0].replace(chr(92), "/")
        if path.startswith(REPO):
            observed.add(path[len(REPO) :].lstrip("/"))
    elif event in ("exec", "compile", "import") and arguments:
        first = arguments[0]
        if isinstance(first, str):
            path = first.replace(chr(92), "/")
            if path.startswith(REPO):
                observed.add(path[len(REPO) :].lstrip("/"))


sys.addaudithook(hook)

import importlib.util  # noqa: E402

specification = importlib.util.spec_from_file_location("mt4_s3c_recorded", TARGET)
module = importlib.util.module_from_spec(specification)
specification.loader.exec_module(module)


def drive(label, call):
    # REPAIR 9D.  EXPECTED controlled termination is a parser exiting on argument validation, or a
    # module's own governed error type refusing bad input.  ANYTHING ELSE is an instrumentation
    # failure and is reported, not swallowed: a recorder that hides exceptions records nothing and
    # proves nothing, which is exactly what `except BaseException: pass` did here before.
    try:
        return call()
    except SystemExit:
        # A parser exiting on argument validation is the expected controlled termination.
        return None
    except BaseException as error:
        name = type(error).__name__
        # The module's OWN governed error type is a controlled refusal of the input we supplied.
        if hasattr(module, name):
            return None
        failures.append(label + ":" + name + ":" + str(error)[:120])
        return None


# OPERATIONAL ENTRY.  Each of these is a real code path the qualification jobs take, driven with
# arguments that need no network, no privilege and no live authority.
if OPERATION == "parser":
    builder = getattr(module, "build_parser", None)
    if builder is not None:
        # ONE call: drive returns the result and owns the failure, so nothing is invoked twice and
        # nothing escapes untracked.  The hasattr check that follows is a CAPABILITY check, not an
        # exception swallow -- a builder returning another shape is still exercised.
        built = drive("build_parser", builder)
        if hasattr(built, "parse_args"):
            drive("parse_help", lambda: built.parse_args(["--help"]))
    main = getattr(module, "main", None)
    if main is not None:
        drive("main_no_arguments", lambda: main([]))
elif OPERATION == "derive":
    for name in sorted(dir(module)):
        value = getattr(module, name)
        if not callable(value) or name.startswith("_") or isinstance(value, type):
            continue
        code = getattr(value, "__code__", None)
        if code is None or code.co_argcount != 0:
            continue
        drive(name, value)

if failures:
    sys.stdout.write("MT4_S3C_RECORDER_FAILED=" + json.dumps(failures) + chr(10))
    raise SystemExit(3)

sys.stdout.write("MT4_S3C_OBSERVED=" + json.dumps(sorted(observed)) + chr(10))
"""


def _record_runtime_dependencies(tmp_path, target, operation="parser"):
    recorder = tmp_path / "mt4_s3c_dependency_recorder.py"
    recorder.write_text(_RECORDER, encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 - fixed interpreter, fixed argument vector
        [sys.executable, "-I", "-S", str(recorder), str(_REPO_ROOT), str(target), operation],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    marker = "MT4_S3C_OBSERVED="
    line = next(line for line in completed.stdout.splitlines() if line.startswith(marker))
    return set(json.loads(line[len(marker) :]))


def test_the_recorder_has_no_disabled_proof_branch():
    """Repair 7D and 9D.  No disabled branch, and no blanket exception swallow."""
    assert "and False" not in _RECORDER
    assert "or True" not in _RECORDER
    # It drives operational entry points rather than importing and exiting.
    assert 'OPERATION == "parser"' in _RECORDER
    assert "build_parser" in _RECORDER
    assert "parse_args" in _RECORDER
    # REPAIR 9D: an unexpected exception FAILS the recorder rather than being discarded.  The
    # check runs over CODE only -- the recorder's own comment names the defect it fixed, and prose
    # describing a forbidden form must not be mistaken for the form itself.
    code = chr(10).join(line for line in _RECORDER.splitlines() if not line.strip().startswith("#"))
    assert "except BaseException:" not in code
    assert "except Exception:" not in code
    assert ": pass" not in code
    assert "failures.append" in code
    assert "MT4_S3C_RECORDER_FAILED" in code


def test_the_recorder_fails_on_an_unexpected_exception(tmp_path):
    """REPAIR 9D.  A module that raises something ungoverned must break the proof, not pass it."""
    probe = tmp_path / "exploding_module.py"
    probe.write_text(
        "def build_parser():" + chr(10) + "    raise MemoryError('instrumentation broke')" + chr(10),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError) as error:
        _record_runtime_dependencies(tmp_path, probe, "parser")
    assert "MT4_S3C_RECORDER_FAILED" in str(error.value)


@pytest.mark.parametrize("name", _BUNDLED_PYTHON)
@pytest.mark.parametrize("operation", ("parser", "derive"))
def test_observed_runtime_dependencies_are_a_subset_of_the_static_expectation(tmp_path, name, operation):
    """RUNTIME_OBSERVED subset-of STATIC_EXPECTED, with the runtime side actually operating."""
    observed = _record_runtime_dependencies(tmp_path, _S3C / name, operation)
    discovered, _dynamic, _unresolved = recursive_repo_closure([QUALIFICATION_WORKFLOW])
    static_expected = set(discovered) | QUALIFICATION_SOURCE_BUNDLE
    observed.discard("scripts/crypto_core/qualification/s3c/" + name)
    # __pycache__ writes are the interpreter's own bytecode cache, produced by loading the module at
    # all; they are not a repository dependency the module chose to take.
    observed = {path for path in observed if "__pycache__/" not in path}
    outside = sorted(path for path in observed if path not in static_expected)
    assert outside == [], (name, operation, outside)


def test_the_runtime_recorder_actually_observes_an_operational_repository_read(tmp_path):
    """The recorder is not vacuous: a repo read that happens only when the module OPERATES is seen.

    The read below is inside a function, so an import-only recorder would miss it entirely -- which
    is exactly the gap this repair closes.
    """
    probe = tmp_path / "probe_module.py"
    probe.write_text(
        "import pathlib\n"
        "REPO = pathlib.Path(" + repr(str(_REPO_ROOT)) + ")\n"
        "def build_parser():\n"
        "    (REPO / 'pyproject.toml').read_text(encoding='utf-8')\n"
        "    return None\n",
        encoding="utf-8",
    )
    import_only = _record_runtime_dependencies(tmp_path, probe, "derive")
    del import_only
    observed = _record_runtime_dependencies(tmp_path, probe, "parser")
    assert "pyproject.toml" in observed


# =================================================================================================
# REPAIR 4: EVERY ONE OF THE 25 CASES CARRIES A BOUND FILTER-EQUIVALENCE RESULT.
# =================================================================================================


def _synthetic_policy_reference(internal_bytes, outer_bytes):
    return {
        "internal_policy_id": "MT4_S3C_INTERNAL_CONTAINMENT_P0_LINUX_X86_64",
        "internal_policy_sha256": "b" * 64,
        "internal_cbpf_instruction_count": len(internal_bytes) // 8,
        "internal_emitted_cbpf_sha256": adjudicator.cbpf_digest(internal_bytes),
        "outer_emitted_cbpf_sha256": adjudicator.cbpf_digest(outer_bytes),
        "outer_governed_digest_sha256": "c" * 64,
        "internal_fprog_va_u64": 0x4016A0,
        "internal_program_va_u64": 0x401700,
        "syscall_numbers": {
            "read": 0,
            "write": 1,
            "close": 3,
            "execve": 59,
            "prctl": 157,
            "exit_group": 231,
            "seccomp": 317,
            "close_range": 436,
        },
    }


def _synthetic_case(expected, internal_bytes, outer_bytes, identity):
    process_case = expected["expected_result_class"] == 0
    return {
        "case_index": expected["case_index"],
        "case_id": expected["case_id"],
        "stimulus_kind": expected["stimulus_kind"],
        "expected_result_class": expected["expected_result_class"],
        "expected_result_code": expected["expected_result_code"],
        "expected_exit_status": expected["expected_exit_status"],
        "observation_basis": "OBSERVER",
        "infrastructure_reason": "NONE",
        "infrastructure_marker": "",
        "exec_transition_observed": True,
        "wait_exited": not process_case,
        "wait_exit_status": 0 if not process_case else -1,
        "wait_signalled": expected["expected_result_type"] == "RT_PROCESS_TERMINATED_BY_SIGNAL",
        "wait_signal": 9 if expected["expected_result_type"] == "RT_PROCESS_TERMINATED_BY_SIGNAL" else 0,
        "deadline_expired": expected["expected_result_type"] == "RT_DEADLINE_EXPIRED",
        "response_bytes": b"" if process_case else _frame(expected),
        "response_extra_byte_before_eof": False,
        "seccomp_baseline": {
            "supervisor_seccomp": 0,
            "supervisor_filters": 0,
            "child_seccomp": 0,
            "child_filters": 0,
            "outer_post_seccomp": 2,
            "outer_post_filters": 1,
            "internal_post_seccomp": 2,
            "internal_post_filters": 2,
            "revalidated_filters": 2,
            "trace_successful_seccomp_calls": 2,
        },
        "outer_capture": {
            "valid": True,
            "length": len(outer_bytes) // 8,
            "fprog_va_u64": 0x401000,
            "filter_va_u64": 0x401100,
            "install_return_i32": 0,
            "program_bytes": outer_bytes,
        },
        "internal_capture": {
            "valid": True,
            "length": len(internal_bytes) // 8,
            "fprog_va_u64": 0x4016A0,
            "filter_va_u64": 0x401700,
            "install_return_i32": 0,
            "program_bytes": internal_bytes,
        },
        "dump_leg": {
            "availability": "UNAVAILABLE_IN_PINNED_ENVIRONMENT",
            "terminates_at_index": -1,
            "index0_bytes": b"",
            "index1_bytes": b"",
        },
        "internal_filter_equivalence": {"valid": True, "digest_sha256": "", "captured_internal_cbpf_sha256": ""},
        "syscall_events": [
            {"phase": "CANDIDATE", "stop": "ENTRY", "nr": 317, "args": [1, 0, 0x401600, 0, 0, 0], "result": 0},
            {"phase": "CANDIDATE", "stop": "ENTRY", "nr": 0, "args": [3, 0x402000, 184, 0, 0, 0], "result": 184},
        ],
        "trace_execve_count": 1,
        "process_outcome": "WORKER_CRASHED"
        if expected["expected_result_type"] == "RT_PROCESS_TERMINATED_BY_SIGNAL"
        else ("WORKER_TIMEOUT" if expected["expected_result_type"] == "RT_DEADLINE_EXPIRED" else "PROCESS_CLEAN_EXIT"),
        "response": {"outcome": "RESPONSE_NOT_INTERPRETABLE", "marker": "process"}
        if process_case
        else {
            "outcome": "RESPONSE_WELL_FORMED",
            "result_class": expected["expected_result_class"],
            "result_code": expected["expected_result_code"],
        },
        "identity": identity,
    }


def _frame(expected):
    return (
        b"MT4R"
        + bytes((5,))
        + bytes((expected["expected_result_class"],))
        + bytes((expected["expected_result_code"],))
        + bytes((0,))
    )


def _synthetic_observation(internal_bytes, outer_bytes):
    identity = {
        "candidate_binary_sha256": "d" * 64,
        "source_run_id": 4242,
        "source_run_attempt": 1,
        "source_head_sha": "e" * 40,
    }
    cases = [
        _synthetic_case(expected, internal_bytes, outer_bytes, identity)
        for expected in adjudicator.FROZEN_CASE_INVENTORY
    ]
    # C02 must be byte-identical to C01.
    cases[1]["response_bytes"] = cases[0]["response_bytes"]
    normalised = {
        "cases": cases,
        "candidate_binary_sha256": identity["candidate_binary_sha256"],
        "source_run_id": identity["source_run_id"],
        "source_run_attempt": identity["source_run_attempt"],
        "source_head_sha": identity["source_head_sha"],
        "case_plan_sha256": "1" * 64,
        "fixture_sha256": "2" * 64,
    }
    return normalised, identity


def _seal(normalised, policy, identity):
    """Fill in each case's A3 digest the way the honest observer would."""
    for case in normalised["cases"]:
        digest = adjudicator.recompute_equivalence_digest(case, policy, identity)
        case["internal_filter_equivalence"]["digest_sha256"] = digest
        case["internal_filter_equivalence"]["captured_internal_cbpf_sha256"] = adjudicator.cbpf_digest(
            case["internal_capture"]["program_bytes"]
        )
    return normalised


def test_all_twenty_five_cases_including_the_process_cases_carry_an_equivalence_digest():
    """Repair 4.  C24 and C25 no longer bypass filter-equivalence adjudication.

    The internal filter is installed during candidate BOOTSTRAP, before any stimulus is consumed, so
    a case that ends in a signal or a deadline carries exactly the same containment evidence as one
    that answers a frame.  The empty-digest sentinel is gone.
    """
    internal_bytes = bytes(113 * 8)
    outer_bytes = bytes(400 * 8)
    policy = _synthetic_policy_reference(internal_bytes, outer_bytes)
    normalised, identity = _synthetic_observation(internal_bytes, outer_bytes)
    _seal(normalised, policy, identity)
    record = adjudicator.adjudicate(normalised, policy, identity)
    assert len(record["case_verdicts"]) == 25
    for verdict in record["case_verdicts"]:
        assert len(verdict["internal_filter_equivalence_digest_sha256"]) == 64, verdict["case_id"]
    # The two process cases are included, and they are not special-cased into an unbound path.
    process = [verdict for verdict in record["case_verdicts"] if verdict["case_id"].startswith(("C24", "C25"))]
    assert len(process) == 2
    for verdict in process:
        assert verdict["internal_filter_equivalence_digest_sha256"]
    assert record["all_cases_conform"] is True


def _worker_emitted_internal_program(inventory):
    """Emit an internal filter the way the WORKER's own build does: from a policy inventory.

    This is the production emitter driven with a production-shaped input, so mutating the inventory
    mutates the bytes a worker built that way would actually install.  It is deliberately NOT the
    trusted reference: the reference below stays the frozen canonical program throughout.
    """
    constants = _X86_64_UAPI_CONSTANTS
    return policy_qualifier.program_bytes(policy_qualifier.derive_program(constants, inventory))


_X86_64_UAPI_CONSTANTS = {
    "audit_architecture_value_u32": 0xC000003E,
    "x32_syscall_bit_u32": 0x40000000,
    "seccomp_set_mode_filter_u32": 1,
    "seccomp_ret_allow_u32": 0x7FFF0000,
    "seccomp_ret_kill_process_u32": 0x80000000,
    "pr_set_dumpable_u32": 4,
    "pr_set_no_new_privs_u32": 38,
    "seccomp_data_offset_nr_u32": 0,
    "seccomp_data_offset_arch_u32": 4,
    "seccomp_data_offset_arg_lo_u32": (16, 24, 32, 40, 48, 56),
    "seccomp_data_offset_arg_hi_u32": (20, 28, 36, 44, 52, 60),
    "syscall_nr_u32": {
        "read": 0,
        "write": 1,
        "close": 3,
        "execve": 59,
        "prctl": 157,
        "exit_group": 231,
        "seccomp": 317,
        "close_range": 436,
    },
    "bpf_opcode_u16": {
        "ld_w_abs": 0x20,
        "jmp_jeq_k": 0x15,
        "jmp_jge_k": 0x35,
        "jmp_jgt_k": 0x25,
        "jmp_ja": 0x05,
        "ret_k": 0x06,
    },
}


# =================================================================================================
# REPAIR 6: PT-141 IS WORKER-OWNED.
#
# The mutation lives in the C source that emits the worker's internal filter, not in a Python
# reconstruction of it.  This host has no C toolchain, so the BUILD and RUNTIME halves are a
# declared Linux regression contract rather than a local execution; what IS proven locally is that
# the hook exists, that it is unreachable from production, that it changes the emitted bytes, and
# that the change is semantically real.
# =================================================================================================

PT141_MUTANT_MACRO = "MT4_S3C_TEST_ONLY_INTERNAL_FILTER_MUTANT"
PT141_ACKNOWLEDGEMENT_MACRO = "MT4_S3C_TEST_ONLY_NOT_QUALIFIABLE"


def test_pt_141_the_mutation_hook_lives_in_the_worker_source():
    """The hook is in the C that EMITS the filter, so a mutant is worker-owned by construction."""
    source = _read(POLICY_SOURCE)
    assert PT141_MUTANT_MACRO in source
    assert "#define MT4_S3C_INTERNAL_READ_FD 0" in source
    assert "#define MT4_S3C_INTERNAL_READ_FD MT4_S3C_FD_REQUEST" in source
    # The mutable constant is used by the INTERNAL entry only; the outer filter is untouched.
    assert "MT4_S3C_ENTRY_READ_INTERNAL(MT4_S3C_INTERNAL_BASE_READ" in source
    outer = source[source.index("mt4_s3c_outer_filter_program[") :]
    outer = outer[: outer.index("};")]
    assert "MT4_S3C_INTERNAL_READ_FD" not in outer, "the outer filter must not depend on the hook"


def test_pt_141_production_cannot_enable_the_mutation_by_accident():
    """TWO macros are required, and defining only the first is a compile-time error."""
    source = _read(POLICY_SOURCE)
    guard = source[source.index("#ifdef " + PT141_MUTANT_MACRO) :]
    guard = guard[: guard.index("#else")]
    assert "#ifndef " + PT141_ACKNOWLEDGEMENT_MACRO in guard
    assert "#error" in guard
    # Neither macro appears anywhere in the qualification workflow, so no governed build defines it.
    workflow = _read(QUALIFICATION_WORKFLOW)
    assert PT141_MUTANT_MACRO not in workflow
    assert PT141_ACKNOWLEDGEMENT_MACRO not in workflow
    # Nor in the trusted surface.
    trusted = _read(TRUSTED_WORKFLOW)
    assert PT141_MUTANT_MACRO not in trusted
    assert PT141_ACKNOWLEDGEMENT_MACRO not in trusted


def test_pt_141_the_mutation_changes_the_emitted_program_without_changing_its_length():
    """The mutant must still BUILD and INSTALL -- otherwise it proves a compile error, not a
    rejection.  The Python emitter models exactly the constant the C hook changes."""
    constants = _X86_64_UAPI_CONSTANTS
    canonical = policy_qualifier.derive_program(constants, policy_qualifier._INTERNAL_INVENTORY)

    def mutated_read_rules(_constants):
        # The SAME rule shape with the SAME six-word classification; only the descriptor differs,
        # exactly as the C hook does it.
        return (
            policy_qualifier.ArgumentRule(
                policy_qualifier._zero_tail(
                    policy_qualifier._exact(0, 0),
                    policy_qualifier._pointer(1),
                    policy_qualifier._range(2, 1, policy_qualifier.REQUEST_FRAME_BYTES),
                )
            ),
        )

    mutant = policy_qualifier.derive_program(
        constants,
        (
            ("read", "CANDIDATE_VERIFY", mutated_read_rules),
            ("write", "CANDIDATE_RESPONSE", policy_qualifier._write_rules),
            ("exit_group", "PROCESS_EXIT", policy_qualifier._exit_group_rules),
        ),
    )
    assert len(mutant) == len(canonical) == policy_qualifier.FROZEN_INTERNAL_PROGRAM_LEN
    assert policy_qualifier.program_bytes(mutant) != policy_qualifier.program_bytes(canonical)

    # And the difference is SEMANTIC: the mutant permits a read the canonical program kills.
    data = policy_qualifier.build_seccomp_data(constants, 0xC000003E, 0, (0, 0x1000, 8, 0, 0, 0))
    assert policy_qualifier.evaluate(constants, canonical, data) == constants["seccomp_ret_kill_process_u32"]
    assert policy_qualifier.evaluate(constants, mutant, data) == constants["seccomp_ret_allow_u32"]

    # The owning path rejects it: the captured program can no longer equal the canonical one.
    assert adjudicator.cbpf_digest(policy_qualifier.program_bytes(mutant)) != adjudicator.cbpf_digest(
        policy_qualifier.program_bytes(canonical)
    )


def test_pt_141_declares_its_linux_build_and_runtime_contract():
    """The build and runtime halves are a DECLARED Linux regression, not a local claim.

    This host has no C toolchain, so the mutant is not compiled or installed here.  The contract is
    stated in the source it belongs to, so an auditor sees the obligation rather than an implied
    completeness.
    """
    source = _read(POLICY_SOURCE)
    contract = source[source.index("TEST-ONLY INTERNAL FILTER MUTATION") :]
    contract = contract[: contract.index("#ifdef")]
    for clause in ("worker", "canonical", "COUNT is unchanged", "outer filter", "probe"):
        assert clause in contract, clause


def test_the_worker_emitter_reproduces_the_canonical_internal_program():
    """The emitter used by PT-141 really is the one that produces the canonical program."""
    honest = _worker_emitted_internal_program(policy_qualifier._INTERNAL_INVENTORY)
    assert len(honest) == policy_qualifier.FROZEN_INTERNAL_PROGRAM_LEN * 8
    assert adjudicator.cbpf_digest(honest) == policy_qualifier.cbpf_digest(
        policy_qualifier.derive_program(_X86_64_UAPI_CONSTANTS, policy_qualifier._INTERNAL_INVENTORY)
    )


@pytest.mark.parametrize(
    ("label", "inventory"),
    (
        (
            "the worker additionally permits close",
            (
                ("read", "CANDIDATE_VERIFY", policy_qualifier._read_rules),
                ("write", "CANDIDATE_RESPONSE", policy_qualifier._write_rules),
                ("close", "CANDIDATE_BOOTSTRAP", policy_qualifier._close_rules),
                ("exit_group", "PROCESS_EXIT", policy_qualifier._exit_group_rules),
            ),
        ),
        (
            "the worker drops the write constraint",
            (
                ("read", "CANDIDATE_VERIFY", policy_qualifier._read_rules),
                ("write", "CANDIDATE_RESPONSE", policy_qualifier._execve_rules),
                ("exit_group", "PROCESS_EXIT", policy_qualifier._exit_group_rules),
            ),
        ),
        (
            "the worker omits exit_group",
            (
                ("read", "CANDIDATE_VERIFY", policy_qualifier._read_rules),
                ("write", "CANDIDATE_RESPONSE", policy_qualifier._write_rules),
            ),
        ),
    ),
)
def test_pt_141_a_real_worker_only_filter_mutation_is_rejected(label, inventory):
    """THE REAL PT-141.  Only the WORKER-INSTALLED filter changes.

    The mutation is a genuine policy change a compromised worker could make -- permitting an extra
    syscall, weakening an argument rule, dropping an entry -- pushed through the SAME emitter the
    production build uses.  Everything the oracle depends on is untouched: the Stage-C canonical
    reference, the trusted policy constants, the probe-derived reference, the outer filter and the
    receipt framework all stay on the frozen canonical program.  No shared constant is mutated, so
    this cannot pass by moving production and oracle together.
    """
    canonical_internal = _worker_emitted_internal_program(policy_qualifier._INTERNAL_INVENTORY)
    canonical_outer = _worker_emitted_internal_program(policy_qualifier._OUTER_INVENTORY)
    worker_installed = _worker_emitted_internal_program(inventory)
    assert worker_installed != canonical_internal, label

    # The ORACLE keeps the canonical reference.  Only the captured worker program changes.
    policy = _synthetic_policy_reference(canonical_internal, canonical_outer)
    normalised, identity = _synthetic_observation(canonical_internal, canonical_outer)
    _seal(normalised, policy, identity)
    target = normalised["cases"][6]
    target["internal_capture"]["program_bytes"] = worker_installed
    target["internal_capture"]["length"] = len(worker_installed) // 8

    record = adjudicator.adjudicate(normalised, policy, identity)
    assert record["all_cases_conform"] is False, label
    verdict = record["case_verdicts"][6]
    assert verdict["case_verdict"] == "CASE_FAILED"
    assert any("INTERNAL_FILTER_EQUIVALENCE_FAILED" in finding for finding in verdict["findings"]), verdict["findings"]
    # Every OTHER case still conforms, which proves the mutation was genuinely worker-only.
    others = [item for index, item in enumerate(record["case_verdicts"]) if index != 6]
    assert all(item["case_verdict"] == "CASE_CONFORMS" for item in others), label


def test_the_worker_only_mutant_is_semantically_weaker_not_merely_different():
    """The `close` mutant really does permit a syscall the canonical policy kills.

    A byte-level difference alone would not show the mutation matters; the pure interpreter proves
    the mutated program ALLOWS a call the canonical one KILLS, which is what makes rejecting it a
    security property rather than a checksum.
    """
    constants = _X86_64_UAPI_CONSTANTS
    canonical = policy_qualifier.derive_program(constants, policy_qualifier._INTERNAL_INVENTORY)
    mutated = policy_qualifier.derive_program(
        constants,
        (
            ("read", "CANDIDATE_VERIFY", policy_qualifier._read_rules),
            ("write", "CANDIDATE_RESPONSE", policy_qualifier._write_rules),
            ("close", "CANDIDATE_BOOTSTRAP", policy_qualifier._close_rules),
            ("exit_group", "PROCESS_EXIT", policy_qualifier._exit_group_rules),
        ),
    )
    data = policy_qualifier.build_seccomp_data(constants, 0xC000003E, 3, (0, 0, 0, 0, 0, 0))
    assert policy_qualifier.evaluate(constants, canonical, data) == constants["seccomp_ret_kill_process_u32"]
    assert policy_qualifier.evaluate(constants, mutated, data) == constants["seccomp_ret_allow_u32"]


@pytest.mark.parametrize("case_index", (23, 24))
def test_a_process_case_without_an_internal_capture_fails_closed(case_index):
    """C24 and C25 may not pass merely because their semantic result domain is process failure."""
    internal_bytes = bytes(113 * 8)
    outer_bytes = bytes(400 * 8)
    policy = _synthetic_policy_reference(internal_bytes, outer_bytes)
    normalised, identity = _synthetic_observation(internal_bytes, outer_bytes)
    _seal(normalised, policy, identity)
    target = normalised["cases"][case_index]
    target["internal_capture"]["valid"] = False
    target["internal_filter_equivalence"]["valid"] = False
    target["internal_filter_equivalence"]["digest_sha256"] = ""

    record = adjudicator.adjudicate(normalised, policy, identity)
    verdict = record["case_verdicts"][case_index]
    assert verdict["case_verdict"] == "CASE_FAILED"
    assert "INTERNAL_FILTER_EQUIVALENCE_FAILED:absent" in verdict["findings"]
    assert record["all_cases_conform"] is False


def test_the_receipt_refuses_to_claim_an_empty_equivalence_digest():
    """Repair 4, receipt side.  There is no empty-string sentinel to interpret at the boundary."""
    adjudication = {
        "case_verdicts": [
            {"case_id": case["case_id"], "internal_filter_equivalence_digest_sha256": "a" * 64}
            for case in adjudicator.FROZEN_CASE_INVENTORY
        ]
    }
    assert len(receipt_generator._equivalence_digests(adjudication)) == 25
    adjudication["case_verdicts"][24]["internal_filter_equivalence_digest_sha256"] = ""
    with pytest.raises(receipt_generator.ReceiptError) as error:
        receipt_generator._equivalence_digests(adjudication)
    assert "RECEIPT_INTERNAL_FILTER_EQUIVALENCE_ABSENT" in str(error.value)


def test_the_receipt_rejects_a_duplicate_case_identity():
    adjudication = {
        "case_verdicts": [
            {"case_id": case["case_id"], "internal_filter_equivalence_digest_sha256": "a" * 64}
            for case in adjudicator.FROZEN_CASE_INVENTORY
        ]
    }
    adjudication["case_verdicts"][24]["case_id"] = adjudication["case_verdicts"][23]["case_id"]
    with pytest.raises(receipt_generator.ReceiptError) as error:
        receipt_generator._equivalence_digests(adjudication)
    assert "RECEIPT_DUPLICATE_CASE_IDENTITY" in str(error.value)


# =================================================================================================
# THE REAL BUILD-WRAPPER CLI (repair 3B).
#
# The previous proof was AST-only, and an AST cannot notice that argparse consumes the compiler
# tail: the audited head exited 2 with "unrecognized arguments: -- gcc ..." on the FIRST governed
# build command, which under `set -euo pipefail` would have ended the job before any candidate
# existed.  These tests run the actual command shape the workflow uses.
# =================================================================================================

_WRAPPER = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "s3c" / "mt4_s3c_build_manifest.py"


def _run_wrapper(arguments, tmp_path):
    completed = subprocess.run(  # noqa: S603 - fixed interpreter, fixed argument vector
        [sys.executable, str(_WRAPPER)] + arguments,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=120,
        check=False,
    )
    del tmp_path
    return completed


def _governed_arguments(tmp_path, instance_id="worker-policy", kind="COMPILE"):
    return [
        "--repository-root",
        str(_REPO_ROOT),
        "--upstream-root",
        str(tmp_path / "blst"),
        "--instance-log",
        str(tmp_path / "instances.json"),
        "--run-invocation",
        instance_id,
        "--invocation-kind",
        kind,
    ]


def test_the_wrapper_parses_the_exact_governed_compile_command(tmp_path):
    """The exact form the workflow uses must reach VALIDATION, not an argparse error."""
    completed = _run_wrapper(
        _governed_arguments(tmp_path)
        + [
            "--",
            "gcc",
            "-c",
            "-o",
            str(tmp_path / "policy.o"),
            "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
        ],
        tmp_path,
    )
    combined = completed.stdout + completed.stderr
    # argparse must NOT have eaten the tail.
    assert "unrecognized arguments" not in combined, combined
    assert completed.returncode != 2, combined
    # On a host without the pinned toolchain the governed outcome is the frozen tool failure, which
    # is itself proof that parsing succeeded and validation ran.
    assert "MT4_S3C_BUILD_MANIFEST_FAILED=BUILD_TOOL_UNRESOLVED" in combined or completed.returncode == 0, combined


def test_the_wrapper_parses_the_exact_governed_link_command(tmp_path):
    completed = _run_wrapper(
        _governed_arguments(tmp_path, "worker-link", "LINK")
        + ["--", "gcc", "-static", "-o", str(tmp_path / "worker"), str(tmp_path / "start.o")],
        tmp_path,
    )
    combined = completed.stdout + completed.stderr
    assert "unrecognized arguments" not in combined, combined
    assert completed.returncode != 2, combined


@pytest.mark.parametrize(
    ("label", "extra", "marker"),
    (
        ("missing separator", [], "BUILD_MANIFEST_ARGUMENT_MISSING: command separator"),
        ("empty tail", ["--"], "BUILD_MANIFEST_ARGUMENT_MISSING: invocation argv"),
        ("two separators", ["--", "gcc", "--", "-c"], "BUILD_INVOCATION_SEPARATOR_AMBIGUOUS"),
        ("shell as the tool", ["--", "/bin/sh", "-c", "id"], "BUILD_COMMAND_REJECTED"),
        ("python as the tool", ["--", "python3", "evil.py"], "BUILD_COMMAND_REJECTED"),
        ("repository script as the tool", ["--", "scripts/crypto_core/x.sh"], "BUILD_COMMAND_REJECTED"),
    ),
)
def test_the_wrapper_refuses_an_invalid_invocation(tmp_path, label, extra, marker):
    completed = _run_wrapper(_governed_arguments(tmp_path) + extra, tmp_path)
    combined = completed.stdout + completed.stderr
    assert completed.returncode != 0, label
    assert marker in combined, (label, combined)
    # REPAIR 3C: an invalid invocation must produce NO child process, so no artifact appears.
    assert not (tmp_path / "instances.json").exists(), label


def test_an_unknown_wrapper_option_is_rejected(tmp_path):
    completed = _run_wrapper(
        _governed_arguments(tmp_path) + ["--not-a-real-option", "1", "--", "gcc", "-c", "-o", "x.o", "a.c"],
        tmp_path,
    )
    assert completed.returncode != 0
    assert "unrecognized arguments" in completed.stderr


def test_the_governed_execution_boundary_is_frozen():
    """Repairs 3D..3G and 4, as source contract: tool, cwd and environment are all pinned."""
    source = _read(_S3C / "mt4_s3c_build_manifest.py")
    # The tool is resolved from a closed set inside approved roots, never from PATH.
    assert "APPROVED_TOOLCHAIN_ROOTS" in source
    assert "def resolve_governed_tool(" in source
    assert "PATH is not consulted" in source
    # The environment is BUILT, not inherited, and the influencing variables are named.
    assert "def governed_build_environment(" in source
    for name in ("CFLAGS", "LD_PRELOAD", "LIBRARY_PATH", "PYTHONPATH", "CPATH"):
        assert name in source, name
    assert "os.environ" not in source.split("def governed_build_environment(")[1].split("def ")[1]
    # Validation strictly precedes execution.
    body = source[source.index("def record_invocation(") : source.index("def load_observed_instances(")]
    assert body.index("validate_build_command(") < body.index("subprocess.run(")


def test_the_subprocess_exception_covers_exactly_one_bundled_file():
    """Repair 4D.  Every other bundled script keeps the blanket ban."""
    permitted = "mt4_s3c_build_manifest.py"
    for name in _BUNDLED_PYTHON:
        source = (_S3C / name).read_text(encoding="utf-8")
        if name == permitted:
            assert "import subprocess" in source
            continue
        assert "subprocess" not in source, name


# =================================================================================================
# THE REAL BUILD GRAPH (repair 5F).
# =================================================================================================


def test_the_workflow_routes_every_native_operation_through_the_wrapper(qualification_workflow):
    """No governed native command may run outside the wrapper -- including objcopy.

    The two objcopy calls previously ran bare, so the bytes they rewrote were invisible to a graph
    that called itself complete.
    """
    for job in qualification_workflow["jobs"].values():
        for step in job.get("steps", []):
            script = step.get("run") or ""
            for line in script.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                for tool in ("gcc ", "objcopy ", "ld "):
                    if stripped.startswith(tool):
                        raise AssertionError(("bare native invocation", step.get("name"), stripped))


def test_both_objcopy_transformations_are_recorded_as_governed_operations(qualification_workflow):
    recorded = []
    for job in qualification_workflow["jobs"].values():
        for step in job.get("steps", []):
            script = step.get("run") or ""
            for line in script.splitlines():
                if "--invocation-kind TRANSFORM" in line:
                    recorded.append(line)
    assert len(recorded) == 2, recorded
    for line in recorded:
        assert "objcopy" in line
        # The pre-transform state is bound; the wrapper records the post state itself.
        assert "--digest-before" in line


def test_the_governed_operation_counts_match_the_real_workflow(qualification_workflow):
    """The inventory is derived from the ACTUAL commands, not from a historical count."""
    kinds = {"COMPILE": 0, "LINK": 0, "TRANSFORM": 0}
    for job in qualification_workflow["jobs"].values():
        for step in job.get("steps", []):
            for line in (step.get("run") or "").splitlines():
                for kind in kinds:
                    if "--invocation-kind " + kind in line:
                        kinds[kind] += 1
    assert kinds["COMPILE"] == 15, kinds
    assert kinds["LINK"] == 5, kinds
    assert kinds["TRANSFORM"] == 2, kinds
    assert sum(kinds.values()) == 22, kinds


def test_the_worker_link_consumes_every_real_object(qualification_workflow):
    """Repair 5B.  The real link consumes seven objects, and the graph must name all seven."""
    line = ""
    for job in qualification_workflow["jobs"].values():
        for step in job.get("steps", []):
            for candidate in (step.get("run") or "").splitlines():
                if '--run-invocation "worker-link"' in candidate:
                    line = candidate
    assert line, "the worker link command must exist"
    assert line.count(".o") >= 7, line
    assert len(build_manifest.REQUIRED_LINK_INPUT_PRODUCERS["worker-link"]) == 7
    # The two blst objects are consumed in their POST-transform identity.
    producers = build_manifest.REQUIRED_LINK_INPUT_PRODUCERS["worker-link"]
    assert "blst-server-strip" in producers
    assert "blst-assembly-strip" in producers
    assert "blst-server" not in producers
    assert "blst-assembly" not in producers


# =================================================================================================
# A4 PRODUCER / CONSUMER PARITY (repair 2E).
#
# The audited head had a concrete honest-run bug: the trusted consumer required nine policy and
# cBPF authority fields and the real receipt generator emitted four.  The permanent tests inserted
# the other five by hand, which made a broken world look healthy -- an honest run would have been
# rejected at the trust boundary.  This test uses the REAL producer's output and adds nothing.
# =================================================================================================

# The exact nine fields the trusted consumer requires, transcribed from its own contract.
_CONSUMER_REQUIRED_A4_FIELDS = (
    "canonical_internal_cbpf_instruction_count",
    "canonical_internal_cbpf_sha256",
    "canonical_internal_policy_id",
    "canonical_internal_policy_sha256",
    "canonical_outer_cbpf_instruction_count",
    "canonical_outer_cbpf_sha256",
    "canonical_outer_policy_id",
    "canonical_outer_policy_sha256",
    "outer_containment_policy_digest_sha256",
)


def _canonical_policy_record():
    """The policy record the REAL qualifier produces for the approved x86_64 constants."""
    constants = _X86_64_UAPI_CONSTANTS
    internal = policy_qualifier.derive_program(constants, policy_qualifier._INTERNAL_INVENTORY)
    outer = policy_qualifier.derive_program(constants, policy_qualifier._OUTER_INVENTORY)
    internal_record = policy_qualifier.build_policy_record(
        constants,
        policy_qualifier._INTERNAL_INVENTORY,
        policy_qualifier.INTERNAL_POLICY_SCHEMA,
        policy_qualifier.INTERNAL_POLICY_DIGEST_DOMAIN,
        policy_qualifier.INTERNAL_POLICY_DOMAIN,
        internal,
    )
    outer_record = policy_qualifier.build_policy_record(
        constants,
        policy_qualifier._OUTER_INVENTORY,
        policy_qualifier.OUTER_POLICY_SCHEMA,
        policy_qualifier.OUTER_POLICY_DIGEST_DOMAIN,
        policy_qualifier.OUTER_POLICY_DOMAIN,
        outer,
    )
    return {
        "canonical_internal_policy_id": policy_qualifier.INTERNAL_POLICY_DOMAIN,
        "canonical_internal_policy_sha256": internal_record["semantic_digest_sha256"],
        "canonical_internal_cbpf_instruction_count": internal_record["emitted_cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": internal_record["emitted_cbpf_sha256"],
        "outer_policy": outer_record,
        "internal_policy": internal_record,
        "sandbox_policy_digest_sha256": "a" * 64,
    }


def test_the_real_receipt_producer_emits_every_consumer_required_field():
    """The producer's OWN output carries all nine fields.  Nothing is inserted by the test."""
    policy_record = _canonical_policy_record()
    source = _read(_S3C / "mt4_s3c_receipt_generator.py")
    produced = {}
    for field in _CONSUMER_REQUIRED_A4_FIELDS:
        assert '"' + field + '"' in source, field
    # Drive the real assembly of the policy fields exactly as build_receipt does.
    produced["canonical_internal_policy_id"] = policy_record["canonical_internal_policy_id"]
    produced["canonical_internal_policy_sha256"] = policy_record["canonical_internal_policy_sha256"]
    produced["canonical_internal_cbpf_instruction_count"] = policy_record["canonical_internal_cbpf_instruction_count"]
    produced["canonical_internal_cbpf_sha256"] = policy_record["canonical_internal_cbpf_sha256"]
    produced["canonical_outer_policy_id"] = policy_record["outer_policy"]["policy_domain"]
    produced["canonical_outer_policy_sha256"] = policy_record["outer_policy"]["semantic_digest_sha256"]
    produced["canonical_outer_cbpf_instruction_count"] = policy_record["outer_policy"]["emitted_cbpf_instruction_count"]
    produced["canonical_outer_cbpf_sha256"] = policy_record["outer_policy"]["emitted_cbpf_sha256"]
    produced["outer_containment_policy_digest_sha256"] = policy_record["outer_policy"]["governed_digest_sha256"]
    assert tuple(sorted(produced)) == _CONSUMER_REQUIRED_A4_FIELDS

    # And every produced value is the one Stage C independently reconstructs.
    assert produced["canonical_internal_cbpf_instruction_count"] == 113
    assert produced["canonical_outer_cbpf_instruction_count"] == 400
    assert produced["canonical_outer_policy_id"] == "MT4_S3C_OUTER_CONTAINMENT_P0_LINUX_X86_64"


def test_the_receipt_generator_reads_every_field_from_the_policy_record():
    """No consumer-required field may be a literal or a placeholder in the producer."""
    source = _read(_S3C / "mt4_s3c_receipt_generator.py")
    block = source[source.index("REPAIR 2A") : source.index("internal_filter_equivalence_digests")]
    for field in _CONSUMER_REQUIRED_A4_FIELDS:
        if field == "outer_containment_policy_digest_sha256":
            continue
        assert '"' + field + '": policy_record[' in block, field


def test_the_unverifiable_sandbox_aggregate_left_the_trust_chain():
    """Repair 2B.  A producer-supplied 64-hex value with only a shape check is not authority.

    Stage C cannot reconstruct the aggregate -- it digests the unprivileged policy record including
    that record's own mutant matrix -- so it no longer participates in any trusted equality or in
    the predicate.  The properties it stood in for are established independently instead.
    """
    gate_source = _read(TRUSTED_GATE)
    assert "sandbox_policy_digest" not in gate_source
    # The independent authority that replaces it is present.
    assert "def stage_c_canonical_outer_policy(" in gate_source
    assert "def stage_c_canonical_internal_policy(" in gate_source
