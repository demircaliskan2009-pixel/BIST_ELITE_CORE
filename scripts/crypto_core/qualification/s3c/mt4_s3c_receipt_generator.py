"""MT4-S3C P0 qualification receipt generator.  Qualification infrastructure only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 7, 24, 25, 31, 39.
BUNDLE ENTRY 9 of the exact 16-entry qualification source bundle (V9 SECTION 8).

WHAT THIS MODULE PRODUCES.  Exactly one JSON member: the QUALIFICATION RECEIPT, artifact class A4.
Its evidence_status is ADMISSION_EVIDENCE_ONLY, always.  The receipt is a STRUCTURED RECORD, never a
trust anchor: every value it carries is independently re-derived by the trusted Stage-C gate before
it is believed, and receipt presence is never sufficient for admission.

WHAT IT DOES NOT PRODUCE.  No governed worker row of any kind -- not ACTIVE, not SUPERSEDED, not
REVOKED.  No custody artifact, no custody schema, no custody constant and no custody stub.  No
readiness, connector, product-native or machine-time authority transition.  A qualification PASS
means exactly this and nothing more: a specific candidate binary, identified by digest, behaved as
the governed contract requires, under a governed containment policy, inside a governed pipeline, in
one authenticated workflow run.  It is not permission to do anything with that binary.

THE RECEIPT SELF-ARTIFACT-ID ASYMMETRY (V9 SECTION 24), restated so it is not mistaken for a gap:
the receipt cannot honestly contain its OWN artifact service id, because that id does not exist
until after upload.  Stage C therefore obtains the receipt artifact's service id, archive digest and
name from GitHub itself, after download and verification; only the CANDIDATE ids are cross-checked
against receipt-claimed values.

SELF-CONTAINED.  This module imports no repository module and contains no dynamic import machinery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

RECEIPT_SCHEMA = "mt4-s3c-qualification-receipt.v1"
RECEIPT_DIGEST_DOMAIN = b"mt4-s3c-qualification-receipt.v1\x00"
PLATFORM_ID = "LINUX_X86_64"

# =================================================================================================
# THE GOVERNED WORKER ROW SCHEMA (V9 SECTION 31.1).
#
# EXACTLY THIRTEEN fields, in exactly the inherited order, under schema id
# mt4-s3c-static-worker-instance-authority.v1 with digest domain
# b"mt4-s3c-static-worker-instance-authority.v1/commitment\x00".  No field is added, removed,
# reordered or renamed, so every previously computed commitment stays valid.
#
# S3C P0 CREATES NO INSTANCE OF THIS ROW.  The schema is declared here so that the permanent test
# matrix can assert its field identity AND order, and so that a future slice inherits the exact
# contract.  Nothing in this module, and nothing anywhere in this slice, can construct a row: there
# is no writer, no status assignment and no activation path.
# =================================================================================================

GOVERNED_WORKER_ROW_SCHEMA = "mt4-s3c-static-worker-instance-authority.v1"
GOVERNED_WORKER_ROW_DIGEST_DOMAIN = b"mt4-s3c-static-worker-instance-authority.v1/commitment\x00"
GOVERNED_WORKER_ROW_FIELDS = (
    "worker_instance_id",
    "platform_id",
    "target_identity",
    "worker_binary_name",
    "worker_binary_sha256",
    "worker_manifest_sha256",
    "worker_qualification_receipt_sha256",
    "worker_build_recipe_sha256",
    "worker_attestation_bundle_sha256",
    "elf_qualification_digest_sha256",
    "protocol_conformance_digest_sha256",
    "sandbox_policy_digest_sha256",
    "status",
)
GOVERNED_WORKER_ROW_STATUS_ENUM = ("ACTIVE", "SUPERSEDED", "REVOKED")

# The two disjoint negative states, preserved and deliberately NOT representable as statuses.
QUALIFIED_NOT_ADMITTED = "QUALIFIED_NOT_ADMITTED"
NEVER_ADMITTED = "NEVER_ADMITTED"

EXACT_CASE_COUNT = 25


class ReceiptError(RuntimeError):
    """Any failure to prove a required receipt binding.  There is no partial success."""


def _fail(marker, detail=""):
    raise ReceiptError(marker if not detail else marker + ": " + detail)


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


def _is_hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _load_json(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _require_hex64(value, marker):
    if not _is_hex64(value):
        _fail(marker, str(value))
    return value


def _equivalence_digests(adjudication):
    """Repair 4: EVERY case carries a real digest, and the identity set is exact.

    The empty-string sentinel is gone.  A case whose containment evidence did not survive
    adjudication is a FAILED case, and a receipt that claimed an empty digest for it would push the
    interpretation of that emptiness onto the trust boundary, where A3 and A4 then disagreed by
    construction.  The receipt now either carries 25 real digests or is not produced at all.
    """
    verdicts = adjudication["case_verdicts"]
    if len(verdicts) != EXACT_CASE_COUNT:
        _fail("RECEIPT_CASE_COUNT_MISMATCH", str(len(verdicts)))
    digests = []
    seen = set()
    for verdict in verdicts:
        case_id = verdict["case_id"]
        if case_id in seen:
            _fail("RECEIPT_DUPLICATE_CASE_IDENTITY", case_id)
        seen.add(case_id)
        digest = verdict["internal_filter_equivalence_digest_sha256"]
        if not _is_hex64(digest):
            _fail("RECEIPT_INTERNAL_FILTER_EQUIVALENCE_ABSENT", case_id)
        digests.append({"case_id": case_id, "digest_sha256": digest})
    return digests


def build_receipt(manifest, elf_record, policy_record, protocol_record, adjudication, identity):
    """Assemble A4 with every binding of V9 SECTION 25 present and cross-checked."""
    # Cross-record identity binding.  One authenticated run identity, or nothing.
    candidate_digest = _require_hex64(manifest["worker_binary_sha256"], "CANDIDATE_IDENTITY_MISMATCH")
    if elf_record["candidate_binary_sha256"] != candidate_digest:
        _fail("CANDIDATE_IDENTITY_MISMATCH", "elf record")
    if adjudication["candidate_binary_sha256"] != candidate_digest:
        _fail("CANDIDATE_IDENTITY_MISMATCH", "adjudication record")
    if candidate_digest != identity["candidate_binary_sha256"]:
        _fail("CANDIDATE_IDENTITY_MISMATCH", "run identity")

    for record, name in ((manifest, "manifest"), (adjudication, "adjudication")):
        if record["source_run_id"] != identity["source_run_id"]:
            _fail("RUN_ATTEMPT_MISMATCH", name + " run id")
        if record["source_run_attempt"] != identity["source_run_attempt"]:
            _fail("RUN_ATTEMPT_MISMATCH", name + " run attempt")
        if record["source_head_sha"] != identity["source_head_sha"]:
            _fail("SOURCE_HEAD_MISMATCH", name)

    if adjudication["case_count"] != EXACT_CASE_COUNT:
        _fail("OBSERVATION_CASE_COUNT_MISMATCH", str(adjudication["case_count"]))
    if (
        adjudication["outer_containment_policy_digest_sha256"]
        != policy_record["outer_policy"]["governed_digest_sha256"]
    ):
        _fail("OUTER_POLICY_DIGEST_MISMATCH")
    if adjudication["canonical_internal_policy_sha256"] != policy_record["canonical_internal_policy_sha256"]:
        _fail("INTERNAL_POLICY_DIGEST_MISMATCH")
    if protocol_record["case_count"] != EXACT_CASE_COUNT:
        _fail("OBSERVATION_CASE_COUNT_MISMATCH", "protocol record")
    if protocol_record["fixture_sha256"] != adjudication["fixture_sha256"]:
        _fail("FIXTURE_DIGEST_MISMATCH")
    if protocol_record["case_plan_sha256"] != adjudication["case_plan_sha256"]:
        _fail("CASE_PLAN_DIGEST_MISMATCH")
    if (
        elf_record.get("compile_dependency_inventory_digest_sha256")
        != manifest["compile_dependency_inventory_digest_sha256"]
    ):
        _fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "elf record echo")

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "platform_id": PLATFORM_ID,
        "evidence_status": "ADMISSION_EVIDENCE_ONLY",
        "observation_basis": "EXECUTED_CANDIDATE_UNDER_OUTER_CONTAINMENT",
        # --- candidate and manifest identity (SECTION 25 items 8 and 9) ---
        "worker_binary_name": manifest["worker_binary_name"],
        "worker_binary_sha256": candidate_digest,
        "worker_binary_bytes": manifest["worker_binary_bytes"],
        "build_manifest_sha256": manifest["build_manifest_digest_sha256"],
        # --- authenticated source-run identity (items 5, 6, 7) ---
        "source_run_id": identity["source_run_id"],
        "source_run_attempt": identity["source_run_attempt"],
        "source_head_sha": identity["source_head_sha"],
        # --- candidate artifact service identity (items 1 and 2), claimed and re-derived by Stage C ---
        "candidate_artifact_id": identity["candidate_artifact_id"],
        "candidate_artifact_archive_digest": identity["candidate_artifact_archive_digest"],
        # --- governed worker-row digests (SECTION 7 placement) ---
        "elf_qualification_digest_sha256": elf_record["elf_qualification_digest_sha256"],
        "protocol_conformance_digest_sha256": protocol_record["protocol_conformance_digest_sha256"],
        "sandbox_policy_digest_sha256": policy_record["sandbox_policy_digest_sha256"],
        # --- environment-scoped digests, A3 and A4 ONLY, never the governed worker row ---
        "outer_containment_policy_digest_sha256": policy_record["outer_policy"]["governed_digest_sha256"],
        "observation_case_set_digest_sha256": adjudication["observation_case_set_digest_sha256"],
        "canonical_internal_policy_id": policy_record["canonical_internal_policy_id"],
        "canonical_internal_policy_sha256": policy_record["canonical_internal_policy_sha256"],
        "canonical_internal_cbpf_sha256": policy_record["canonical_internal_cbpf_sha256"],
        "internal_filter_equivalence_digests": _equivalence_digests(adjudication),
        # --- artifact-production identity, riding with the manifest it describes ---
        "compile_dependency_inventory_digest_sha256": manifest["compile_dependency_inventory_digest_sha256"],
        "compile_dependency_entry_count": manifest["compile_dependency_entry_count"],
        # --- pinned upstream identity ---
        "upstream_release": manifest["upstream_release"],
        "upstream_commit": manifest["upstream_commit"],
        "upstream_source_tree_digest": manifest["upstream_source_tree_digest"],
        # --- the observation outcome, as DATA ---
        "case_count": EXACT_CASE_COUNT,
        "verifier_case_count": adjudication["verifier_case_count"],
        "request_case_count": adjudication["request_case_count"],
        "process_case_count": adjudication["process_case_count"],
        "all_cases_conform": adjudication["all_cases_conform"],
        "adjudication_digest_sha256": adjudication["adjudication_digest_sha256"],
        "fixture_sha256": adjudication["fixture_sha256"],
        "case_plan_sha256": adjudication["case_plan_sha256"],
        # --- the governed worker row schema, DECLARED but never instantiated ---
        "governed_worker_row_schema": GOVERNED_WORKER_ROW_SCHEMA,
        "governed_worker_row_field_count": len(GOVERNED_WORKER_ROW_FIELDS),
        "governed_worker_row_created": False,
        "governed_worker_row_status_written": "NONE",
        "qualification_state": QUALIFIED_NOT_ADMITTED,
        # --- explicit non-claims (V9 SECTION 39) ---
        "authority_non_transition": {
            "admission": "NONE",
            "machine_time_authority": "NONE",
            "mt5_mt6_authority": "NONE",
            "machine_proven_thirty_day_gate": "NONE",
            "stage4_authority": "NONE",
            "readiness_transition": "NONE",
            "connector_transition": "NONE",
            "live_execution": "NONE",
            "shadow_execution": "NONE",
            "orders_or_order_routing": "NONE",
            "capital_mutation": "NONE",
            "scheduler_or_auto_loop": "NONE",
            "product_native_execution": "NO",
            "proof_verification": "DEFERRED",
            "windows_product_loader": "DEFERRED",
            "bist_surface": "NONE",
            "private_api_or_credentials": "NONE",
            "custody_artifact": "NONE",
            "fixture_corpus_admitted": False,
            "fixture_corpus_loaded": False,
            "fixture_corpus_verified": False,
            "proof_verified": False,
            "randomness_verified": False,
            "provider_operationally_approved": False,
            "readiness_promoted": False,
        },
    }
    receipt["qualification_receipt_digest_sha256"] = hashlib.sha256(
        RECEIPT_DIGEST_DOMAIN + canonical_json(receipt)
    ).hexdigest()
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description="MT4-S3C qualification receipt generator")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--elf-record", required=True)
    parser.add_argument("--policy-record", required=True)
    parser.add_argument("--protocol-record", required=True)
    parser.add_argument("--adjudication", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--source-run-attempt", required=True, type=int)
    parser.add_argument("--source-head-sha", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--candidate-artifact-id", required=True, type=int)
    parser.add_argument("--candidate-artifact-archive-digest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    identity = {
        "source_run_id": args.source_run_id,
        "source_run_attempt": args.source_run_attempt,
        "source_head_sha": args.source_head_sha,
        "candidate_binary_sha256": args.candidate_sha256,
        "candidate_artifact_id": args.candidate_artifact_id,
        "candidate_artifact_archive_digest": args.candidate_artifact_archive_digest,
    }
    receipt = build_receipt(
        _load_json(args.manifest),
        _load_json(args.elf_record),
        _load_json(args.policy_record),
        _load_json(args.protocol_record),
        _load_json(args.adjudication),
        identity,
    )
    with open(args.out, "wb") as handle:
        handle.write(canonical_json(receipt))
    sys.stdout.write("MT4_S3C_QUALIFICATION_RECEIPT_DIGEST=" + receipt["qualification_receipt_digest_sha256"] + "\n")
    sys.stdout.write("MT4_S3C_ALL_CASES_CONFORM=" + str(receipt["all_cases_conform"]) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
