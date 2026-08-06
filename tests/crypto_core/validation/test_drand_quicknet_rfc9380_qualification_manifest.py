"""Permanent MT4-S3A Drand Quicknet qualification-manifest regressions.

These tests are stdlib-only. They never access the network, never read a clock, never require the
candidate dependency ``pyblst`` and never require a Go toolchain. They pin the qualification manifest
inventory, recompute every stdlib-derivable protocol value, prove the qualification script cannot reach
the network or become a product runtime dependency, and prove the manifest admits nothing.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import pathlib
import re
import sys
import types

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_MANIFEST_PATH = _REPO_ROOT / "tests" / "crypto_core" / "fixtures" / "drand_quicknet_rfc9380_qualification_v1.json"
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "crypto_core" / "qualify_drand_quicknet_pyblst.py"
_DOC_PATH = _REPO_ROOT / "docs" / "crypto_core" / "mt4_s3a_drand_quicknet_pyblst_qualification.md"

_DEPENDENCY_QUALIFICATION = "BLOCKED"
_DEPENDENCY_BLOCKERS = ("package_version_identity_ambiguous",)
_FIXTURE_QUALIFICATION = "BLOCKED"
_FIXTURE_BLOCKERS = (
    "fixture_license_unresolved",
    "mandatory_subgroup_invalid_fixture_provenance_unresolved",
)
_EXPECTED_BLOCKED_COVERAGE_CLASSES = ("subgroup_invalid",)
_EXPECTED_PROVEN_COVERAGE_CLASSES = ("infinity", "non_canonical_encoding")
_G1_SOURCE_FILE = "g1.go"
_G1_SOURCE_SHA256 = "51143a23a7818f0347b60ed6d0bdc42fbbc1640344013ffded1dd48f99a709b6"
_G2_SOURCE_FILE = "g2.go"
_G2_SOURCE_SHA256 = "0c227f0ce968cb8350bc86bfbd400d88183b4781940adca66d042ce18b250b81"
_MODULUS_SOURCE_FILE = "bls12_381.go"
_MODULUS_SOURCE_SHA256 = "19dad068bf44c42af69fd15896540749172ec3ff31ece151c6f9d6bc3c673246"
_PACKAGE_SOURCE_CONTRADICTIONS = "UNRESOLVED_PACKAGE_VERSION_IDENTITY_AMBIGUITY"
_BLS12_381_BASE_FIELD_MODULUS = int(
    "1a0111ea397fe69a4b1ba7b6434bacd764774b84f38512bf6730d2a0f6b0f6241eabfffeb153ffffb9feffffffffaaab",
    16,
)

_EXPECTED_POSITIVE_IDS = (
    "pos_official_round_42",
    "pos_official_chain_info",
    "pos_repeated_deterministic_verification",
)
_EXPECTED_NEGATIVE_IDS = (
    "neg_round_zero",
    "neg_round_above_uint64",
    "neg_wrong_round",
    "neg_little_endian_round",
    "neg_no_sha256_prehash",
    "neg_wrong_dst",
    "neg_one_bit_signature_corruption",
    "neg_non_canonical_unreduced_x_signature",
    "neg_wrong_public_key",
    "neg_wrong_chain_hash",
    "neg_signature_47_bytes",
    "neg_signature_49_bytes",
    "neg_public_key_95_bytes",
    "neg_public_key_97_bytes",
    "neg_malformed_signature_encoding",
    "neg_malformed_public_key_encoding",
    "neg_g1_infinity_signature",
    "neg_g2_infinity_public_key",
    "neg_valid_signature_wrong_randomness",
    "neg_round_wrong_type_str",
    "neg_round_wrong_type_bool",
    "neg_signature_mutable_alias",
    "neg_signature_hostile_bytes_subclass",
    "neg_public_key_hostile_bytes_subclass",
)
_EXPECTED_BLOCKED_IDS = ("blocked_subgroup_invalid_g1_point",)
# Labels that MAY back a mandatory coverage class: official, or a hash-pinned upstream source.
_PROVENANCE_BACKING_LABELS = frozenset(
    {
        "OFFICIAL_DRAND_HTTP_API_V2",
        "OFFICIAL_DRAND_V2_1_6_KEYGROUP_BASE_POINT",
        "PINNED_UPSTREAM_SOURCE_KILIC_BLS12_381_V0_1_0",
    }
)
# Labels that are candidate evidence ONLY. No positive fixture is admitted (licence unresolved), so a
# derivation from one confers no provenance and must never back a mandatory coverage class.
_CANDIDATE_ONLY_PROVENANCE_LABELS = frozenset(
    {
        "DETERMINISTIC_MUTATION_OF_UNADMITTED_OFFICIAL_POSITIVE",
        "DETERMINISTIC_REPEAT_OF_UNADMITTED_OFFICIAL_POSITIVE",
    }
)
_ADMISSIBLE_PROVENANCE = _PROVENANCE_BACKING_LABELS | _CANDIDATE_ONLY_PROVENANCE_LABELS
# A provenance label is only admissible when the manifest also carries its evidence.
_PROVENANCE_REQUIRING_SOURCE_EVIDENCE = frozenset({"PINNED_UPSTREAM_SOURCE_KILIC_BLS12_381_V0_1_0"})
_REQUIRED_SOURCE_EVIDENCE_FIELDS = (
    "derivation_algorithm",
    "license_result",
    "source_file",
    "source_sha256",
    "source_uri",
    "source_version",
)
_ADMISSION_FLAGS = (
    "crypto_implementation_authorized",
    "dependency_admitted",
    "fixture_corpus_admitted",
    "machine_time_origin_proven",
    "mt4_verifier_profile_selected",
    "operational_quorum_ready",
    "operational_use_approved",
    "provider_operational_approval",
    "proof_verified",
    "quorum_countable",
    "readiness_promoted",
    "timestamp_origin_proven",
)
_NONCLAIM_FLAGS = (
    "no_bls_verifier_implemented_in_product",
    "no_capital_or_order_or_position_effect",
    "no_clock_access",
    "no_connector_transition",
    "no_environment_access",
    "no_fixture_acquisition_at_test_time",
    "no_network_access",
    "no_product_runtime_dependency_on_pyblst",
    "no_readiness_transition",
    "no_source_reachability_claim",
)

_OFFICIAL_ROUND = 42
_OFFICIAL_SIGNATURE_HEX = (
    "95a9f9f5b231b7714de1553105d8ffdf3dcda24cfdb1e689319bccf79a9c8ce430a91b811fbfaf763900bc998b5d686a"
)
_OFFICIAL_PUBLIC_KEY_HEX = (
    "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c"
    "8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb"
    "5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a"
)
_OFFICIAL_MESSAGE_DIGEST_HEX = "a6bb133cb1e3638ad7b8a3ff0539668e9e56f9b850ef1b2a810f5422eaa6c323"
_OFFICIAL_RANDOMNESS_HEX = "8ada64bae5c6c0f5540a6a13af56e663240edfbd2c76ac6a8f27671eb7259ce3"
_QUICKNET_DST = "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"
_QUICKNET_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
_GENESIS = 1_692_803_367
_PERIOD = 3
_HEX_CHARS = frozenset("0123456789abcdef")

_PROHIBITED_IMPORT_ROOTS = frozenset(
    {
        "aiohttp",
        "asyncio",
        "datetime",
        "ftplib",
        "http",
        "httpx",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "shutil",
        "socket",
        "ssl",
        "subprocess",
        "time",
        "urllib",
        "websockets",
    }
)
_PROHIBITED_CALL_NAMES = frozenset({"__import__", "compile", "eval", "exec", "input", "open"})
_PROHIBITED_CALL_ATTRIBUTES = frozenset(
    {
        "Popen",
        "check_output",
        "getenv",
        "now",
        "read_bytes",
        "read_text",
        "request",
        "run",
        "sleep",
        "socket",
        "system",
        "time",
        "today",
        "urlopen",
        "utcnow",
        "write_bytes",
        "write_text",
    }
)


def _manifest() -> dict:
    raw = _MANIFEST_PATH.read_bytes()
    raw.decode("utf-8", errors="strict")
    return json.loads(raw)


def _script_source() -> str:
    return _SCRIPT_PATH.read_text(encoding="utf-8")


def _load_script(unique_suffix: str):
    spec = importlib.util.spec_from_file_location(f"mt4_s3a_qualification_script_{unique_suffix}", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(section: str, fixture_id: str) -> dict:
    return next(entry for entry in _manifest()[section] if entry["fixture_id"] == fixture_id)


def test_manifest_is_strict_utf8_without_bom_and_pins_schema_identity() -> None:
    raw = _MANIFEST_PATH.read_bytes()
    raw.decode("utf-8", errors="strict")
    assert not raw.startswith(b"\xef\xbb\xbf")
    data = _manifest()
    assert data["schema"] == "mt4-s3a-drand-quicknet-qualification-manifest"
    assert data["version"] == 1
    assert data["corpus_id"] == "FX-DRAND-QUICKNET-RFC9380-QUALIFICATION.v1"


def test_manifest_admits_nothing() -> None:
    admission = _manifest()["admission"]
    assert admission["status"] == "BLOCKED_NOT_QUALIFIED_NOT_ADMITTED"
    assert set(admission) == set(_ADMISSION_FLAGS) | {
        "attribution_required",
        "dependency_blockers",
        "dependency_qualification",
        "fixture_blockers",
        "fixture_qualification",
        "fixture_reuse_license",
        "fixture_reuse_scope",
        "mt4_s3b_authorized",
        "package_source_contradictions",
        "roughtime_protocol_provenance_required_before_mt4_profile_selection",
        "status",
    }
    for flag in _ADMISSION_FLAGS:
        assert admission[flag] is False, flag
    assert admission["roughtime_protocol_provenance_required_before_mt4_profile_selection"] is True
    assert admission["mt4_s3b_authorized"] is False


def test_both_qualification_decisions_are_blocked_with_exact_blockers() -> None:
    admission = _manifest()["admission"]
    assert admission["dependency_qualification"] == _DEPENDENCY_QUALIFICATION
    assert tuple(admission["dependency_blockers"]) == _DEPENDENCY_BLOCKERS
    assert admission["fixture_qualification"] == _FIXTURE_QUALIFICATION
    assert tuple(admission["fixture_blockers"]) == _FIXTURE_BLOCKERS
    assert admission["package_source_contradictions"] == _PACKAGE_SOURCE_CONTRADICTIONS
    assert admission["fixture_reuse_license"] == "NOT_PROVEN"
    assert admission["fixture_reuse_scope"] == "UNKNOWN"
    assert admission["attribution_required"] == "UNKNOWN"


def test_no_authoritative_field_claims_a_passing_qualification() -> None:
    """No file may ASSERT PASS while an authoritative decision is BLOCKED.

    The document may still discuss ``PASS_CANDIDATE_ONLY`` when explaining why it does not apply, so
    the machine-readable files forbid the token outright while the document forbids the claim form.
    """
    for path in (_MANIFEST_PATH, _SCRIPT_PATH):
        text = path.read_text(encoding="utf-8")
        assert "PASS_CANDIDATE_ONLY" not in text, path.name
        assert "QUALIFIED_CANDIDATE_NOT_ADMITTED" not in text, path.name

    doc = _DOC_PATH.read_text(encoding="utf-8")
    assert "QUALIFIED_CANDIDATE_NOT_ADMITTED" not in doc
    claim = re.compile(r"(DEPENDENCY_QUALIFICATION|FIXTURE_QUALIFICATION)\s*:?\s*`?\s*PASS", re.IGNORECASE)
    assert claim.search(doc) is None, "document must never assert a passing qualification"
    # every mention of the passing token must be a negation, not a claim
    for line in doc.splitlines():
        if "PASS_CANDIDATE_ONLY" in line:
            assert "cannot be" in line, line

    # the round-level success reason must not be spelled "qualified"
    manifest_text = _MANIFEST_PATH.read_text(encoding="utf-8")
    assert '"qualified"' not in manifest_text
    module = _load_script("no_pass")
    assert not hasattr(module.QuicknetQualificationReason, "QUALIFIED")
    assert module.QuicknetQualificationReason.ROUND_STRUCTURALLY_VERIFIED.value == ("round_structurally_verified")


def test_script_manifest_and_document_agree_on_every_decision() -> None:
    module = _load_script("decisions")
    admission = _manifest()["admission"]
    doc = _DOC_PATH.read_text(encoding="utf-8")

    assert module.DEPENDENCY_QUALIFICATION == admission["dependency_qualification"]
    assert tuple(module.DEPENDENCY_QUALIFICATION_BLOCKERS) == tuple(admission["dependency_blockers"])
    assert module.FIXTURE_QUALIFICATION == admission["fixture_qualification"]
    assert tuple(module.FIXTURE_QUALIFICATION_BLOCKERS) == tuple(admission["fixture_blockers"])
    assert module.PACKAGE_SOURCE_CONTRADICTIONS == admission["package_source_contradictions"]

    assert "DEPENDENCY_QUALIFICATION:      BLOCKED" in doc
    assert "FIXTURE_QUALIFICATION:         BLOCKED" in doc
    assert "BLOCKED_NOT_QUALIFIED_NOT_ADMITTED" in doc
    for blocker in _DEPENDENCY_BLOCKERS + _FIXTURE_BLOCKERS:
        assert blocker in doc, blocker
    assert _PACKAGE_SOURCE_CONTRADICTIONS in doc


def test_document_fixture_inventory_matches_the_manifest_exactly() -> None:
    """The document's inventory sentence must be DERIVED from the manifest, not just hard-coded.

    A prior revision hard-coded ``0 blocked`` in this sentence and never updated it when a blocked
    fixture entry was later restored. This test recomputes the exact counts from the manifest at
    import time, so the assertion tracks the manifest even if the numbers change again.
    """
    manifest = _manifest()
    positive_count = len(manifest["positive_fixtures"])
    negative_count = len(manifest["negative_fixtures"])
    blocked_count = len(manifest["unresolved_or_blocked_fixtures"])

    doc = _DOC_PATH.read_text(encoding="utf-8")
    expected_inventory_sentence = f"{positive_count} positive,\n{negative_count} negative, {blocked_count} blocked."
    assert expected_inventory_sentence in doc, (
        positive_count,
        negative_count,
        blocked_count,
    )
    # the specific stale wording must never come back
    assert "24 negative, 0 blocked" not in doc


def test_document_subgroup_provenance_language_matches_the_manifest() -> None:
    """The document must describe the subgroup-invalid class exactly as the manifest records it."""
    manifest = _manifest()
    matrix_entry = manifest["mandatory_coverage_matrix"]["subgroup_invalid"]
    assert matrix_entry["result"] == "BLOCKED"
    assert matrix_entry["provenance_backed"] is False

    doc = _DOC_PATH.read_text(encoding="utf-8")
    subgroup_start = doc.index("Subgroup-invalid")
    subgroup_end = doc.index("Non-canonical", subgroup_start)
    section = doc[subgroup_start:subgroup_end]

    assert "unadmitted" in section.lower()
    assert "candidate evidence" in section.lower()
    assert "BLOCKED" in section

    # the stale claims that provenance was proven must never come back
    assert "mutation of an admitted positive fixture" not in doc
    assert "derived from an admitted positive fixture" not in doc


def test_tag_signature_authenticity_is_distinct_from_artifact_binding() -> None:
    """A valid signed commit proves the SOURCE is genuine; it does not bind any published artifact."""
    dependency = _manifest()["candidate_dependency"]
    assert dependency["tag_commit_signature"] == "VALID_GITHUB_VERIFIED_PGP_SIGNATURE"
    # authenticity of the commit must NOT be conflated with binding of the published bytes
    assert dependency["signed_tag_does_not_attest_pypi_artifacts"] is True
    assert dependency["source_to_sdist_binding"] == "NOT_PROVEN"
    assert dependency["source_to_wheel_binding"] == "NOT_PROVEN"


def test_ci_artifact_archive_digest_is_never_represented_as_a_wheel_or_sdist_file_hash() -> None:
    dependency = _manifest()["candidate_dependency"]
    assert dependency["artifact_digest_is_not_wheel_or_sdist_file_hash"] is True
    windows_digest = dependency["tag_ci_windows_artifact_digest"]
    sdist_digest = dependency["tag_ci_sdist_artifact_digest"]
    # the archive digests must be distinct from, and never asserted equal to, the PyPI file hashes
    assert windows_digest.removeprefix("sha256:") != dependency["wheel_sha256"]
    assert sdist_digest.removeprefix("sha256:") != dependency["sdist_sha256"]
    assert windows_digest == "sha256:ffdf9728d7d23488f6ab55adbb6f19a7733079daa93311b1b6cf1cf69abd75d6"
    assert sdist_digest == "sha256:5579477f52515428c3112cd3db007457578b5dbbb7b1b102cc91d1639a8f2d1a"


def test_expired_ci_artifacts_cannot_be_treated_as_downloaded_or_hash_compared() -> None:
    dependency = _manifest()["candidate_dependency"]
    assert dependency["tag_ci_artifacts_expired"] is True
    assert dependency["tag_ci_artifact_expiry"] == "2026-01-12T20:46:33Z"
    assert dependency["tag_ci_artifact_count"] == 7
    # expiry must gate binding proof - it cannot be silently treated as available evidence
    assert dependency["source_to_sdist_binding"] == "NOT_PROVEN"
    assert dependency["source_to_wheel_binding"] == "NOT_PROVEN"


def test_ci_job_log_download_result_is_recorded_as_gone() -> None:
    dependency = _manifest()["candidate_dependency"]
    assert dependency["tag_ci_job_log_download_result"] == "HTTP_410_GONE"


def test_source_bindings_remain_not_proven_after_the_research() -> None:
    dependency = _manifest()["candidate_dependency"]
    assert dependency["source_to_sdist_binding"] == "NOT_PROVEN"
    assert dependency["source_to_wheel_binding"] == "NOT_PROVEN"
    assert dependency["binary_source_correspondence_proven"] is False
    doc = _DOC_PATH.read_text(encoding="utf-8")
    assert "SOURCE_TO_SDIST_BINDING: NOT_PROVEN" in doc.replace("`", "")
    assert "SOURCE_TO_WHEEL_BINDING: NOT_PROVEN" in doc.replace("`", "")


def test_public_and_publicly_verifiable_wording_does_not_prove_fixture_reuse_license() -> None:
    rights = _manifest()["drand_rights_evidence"]
    assert rights["drand_output_is_publicly_available"] is True
    assert rights["drand_output_is_publicly_verifiable"] is True
    assert rights["official_api_use_documented"] is True
    assert rights["public_availability_is_not_a_redistribution_license"] is True
    # availability findings above must NOT flip the reuse licence to proven
    assert rights["fixture_reuse_license"] == "NOT_PROVEN"


def test_software_or_documentation_license_does_not_prove_api_output_redistribution() -> None:
    rights = _manifest()["drand_rights_evidence"]
    assert rights["explicit_output_copy_grant_found"] is False
    assert rights["explicit_output_redistribution_grant_found"] is False
    assert rights["explicit_test_fixture_commit_grant_found"] is False
    assert rights["fixture_reuse_license"] == "NOT_PROVEN"


def test_fixture_reuse_scope_and_attribution_remain_unknown() -> None:
    rights = _manifest()["drand_rights_evidence"]
    assert rights["fixture_reuse_scope"] == "UNKNOWN"
    assert rights["attribution_required"] == "UNKNOWN"
    admission = _manifest()["admission"]
    assert admission["fixture_reuse_scope"] == "UNKNOWN"
    assert admission["attribution_required"] == "UNKNOWN"
    # UNKNOWN must never be silently inferred as a NO or a PROVEN
    assert rights["fixture_reuse_scope"] not in ("NO", "PROVEN", "NONE")
    assert rights["attribution_required"] not in ("NO", "PROVEN", "NONE")


def test_external_research_did_not_clear_any_qualification_blocker() -> None:
    """The research documented here must leave every blocker exactly as it was."""
    admission = _manifest()["admission"]
    assert admission["dependency_qualification"] == "BLOCKED"
    assert admission["fixture_qualification"] == "BLOCKED"
    assert tuple(admission["dependency_blockers"]) == ("package_version_identity_ambiguous",)
    assert tuple(admission["fixture_blockers"]) == (
        "fixture_license_unresolved",
        "mandatory_subgroup_invalid_fixture_provenance_unresolved",
    )
    assert admission["dependency_admitted"] is False
    assert admission["fixture_corpus_admitted"] is False
    assert admission["mt4_s3b_authorized"] is False
    assert admission["crypto_implementation_authorized"] is False


def test_admission_readiness_and_connector_state_unchanged_by_external_evidence_record() -> None:
    admission = _manifest()["admission"]
    for flag in (
        "machine_time_origin_proven",
        "mt4_verifier_profile_selected",
        "operational_quorum_ready",
        "operational_use_approved",
        "proof_verified",
        "provider_operational_approval",
        "quorum_countable",
        "readiness_promoted",
        "timestamp_origin_proven",
    ):
        assert admission[flag] is False, flag

    from crypto_core.validation.machine_time_source_registry import (
        build_approved_machine_time_source_registry,
        machine_time_source_registry_to_dict,
    )
    from crypto_core.venue.public_feed_dialects import connector_ready_dialects

    payload = machine_time_source_registry_to_dict(build_approved_machine_time_source_registry())
    assert payload["readiness_promoted"] is False
    assert payload["connector_promoted"] is False
    assert tuple(spec.dialect_id for spec in connector_ready_dialects()) == (
        "deribit:l2_orderbook:book_instrument_interval",
    )


def test_script_permanent_false_governance_states_are_all_false() -> None:
    module = _load_script("governance")
    for name in (
        "DEPENDENCY_ADMITTED",
        "FIXTURE_CORPUS_ADMITTED",
        "CRYPTO_IMPLEMENTATION_AUTHORIZED",
        "PROVIDER_OPERATIONAL_APPROVAL",
        "MT4_VERIFIER_PROFILE_SELECTED",
        "READINESS_PROMOTED",
        "MACHINE_TIME_ORIGIN_PROVEN",
        "TIMESTAMP_ORIGIN_PROVEN",
        "PROOF_VERIFIED",
        "OPERATIONAL_USE_APPROVED",
        "QUORUM_COUNTABLE",
        "OPERATIONAL_QUORUM_READY",
    ):
        assert getattr(module, name) is False, name
    assert module.ROUGHTIME_PROTOCOL_PROVENANCE_REQUIRED_BEFORE_MT4_PROFILE_SELECTION is True


def test_manifest_states_every_required_nonclaim() -> None:
    nonclaims = _manifest()["nonclaims"]
    assert set(nonclaims) == set(_NONCLAIM_FLAGS)
    for flag in _NONCLAIM_FLAGS:
        assert nonclaims[flag] is True, flag


def test_manifest_fixture_inventory_is_exact_and_cannot_silently_widen() -> None:
    data = _manifest()
    positives = tuple(entry["fixture_id"] for entry in data["positive_fixtures"])
    negatives = tuple(entry["fixture_id"] for entry in data["negative_fixtures"])
    blocked = tuple(entry["fixture_id"] for entry in data["unresolved_or_blocked_fixtures"])
    assert positives == _EXPECTED_POSITIVE_IDS
    assert negatives == _EXPECTED_NEGATIVE_IDS
    assert blocked == _EXPECTED_BLOCKED_IDS
    every_id = positives + negatives + blocked
    assert len(set(every_id)) == len(every_id)
    assert set(data) == {
        "admission",
        "candidate_dependency",
        "chain_profile",
        "corpus_id",
        "curve_encoding_source",
        "drand_rights_evidence",
        "mandatory_coverage_matrix",
        "negative_fixtures",
        "nonclaims",
        "positive_fixtures",
        "reference_verifier",
        "schema",
        "unresolved_or_blocked_fixtures",
        "version",
    }


def test_every_admitted_fixture_declares_admissible_provenance() -> None:
    data = _manifest()
    for fixture in data["positive_fixtures"] + data["negative_fixtures"]:
        assert fixture["provenance"] in _ADMISSIBLE_PROVENANCE, fixture["fixture_id"]
        assert fixture["source_type"] in {
            "official_http_api",
            "official_reference",
            "pinned_upstream_source",
            "derived",
        }


def test_a_provenance_label_is_never_accepted_without_its_source_evidence() -> None:
    """A label alone is not provenance: any source-backed claim must carry pin, hash and licence."""
    data = _manifest()
    for fixture in data["positive_fixtures"] + data["negative_fixtures"]:
        if fixture["provenance"] not in _PROVENANCE_REQUIRING_SOURCE_EVIDENCE:
            continue
        for field in _REQUIRED_SOURCE_EVIDENCE_FIELDS:
            assert field in fixture, (fixture["fixture_id"], field)
            assert str(fixture[field]).strip(), (fixture["fixture_id"], field)
        assert len(fixture["source_sha256"]) == 64
        assert set(fixture["source_sha256"]) <= _HEX_CHARS
        assert fixture["source_uri"].startswith("https://")


def test_every_source_backed_fixture_pins_a_file_that_exists_with_the_matching_hash() -> None:
    manifest = _manifest()
    files = manifest["curve_encoding_source"]["files"]
    source = manifest["curve_encoding_source"]
    for fixture in manifest["negative_fixtures"]:
        if fixture["provenance"] not in _PROVENANCE_REQUIRING_SOURCE_EVIDENCE:
            continue
        name = fixture["source_file"]
        assert name in files, (fixture["fixture_id"], name)
        assert fixture["source_sha256"] == files[name]["sha256"], fixture["fixture_id"]
        assert fixture["source_version"] == source["version"], fixture["fixture_id"]
        assert fixture["source_uri"] == source["source_uri"], fixture["fixture_id"]
        assert fixture["license_result"] == source["license_result"], fixture["fixture_id"]


def test_g2_evidence_is_never_sourced_from_the_g1_implementation() -> None:
    """G2 compressed serialization is a separate contract in g2.go; g1.go must not stand in for it."""
    manifest = _manifest()
    for fixture in manifest["negative_fixtures"]:
        if fixture.get("group") == "G2" and "source_file" in fixture:
            assert fixture["source_file"] != _G1_SOURCE_FILE, fixture["fixture_id"]
            assert fixture["source_file"] == _G2_SOURCE_FILE, fixture["fixture_id"]
            assert fixture["source_sha256"] == _G2_SOURCE_SHA256, fixture["fixture_id"]
            assert fixture["source_symbol"] == "G2.FromCompressed", fixture["fixture_id"]
        if fixture.get("group") == "G1" and "source_file" in fixture:
            assert fixture["source_file"] in {_G1_SOURCE_FILE, _MODULUS_SOURCE_FILE}
            assert fixture["source_file"] != _G2_SOURCE_FILE, fixture["fixture_id"]

    g2 = _fixture("negative_fixtures", "neg_g2_infinity_public_key")
    assert g2["source_file"] == _G2_SOURCE_FILE
    assert g2["source_sha256"] == _G2_SOURCE_SHA256
    assert g2["group"] == "G2"
    assert "96" in g2["derivation_algorithm"]
    assert len(bytes.fromhex(g2["public_key_hex"])) == 96

    g1 = _fixture("negative_fixtures", "neg_g1_infinity_signature")
    assert g1["source_file"] == _G1_SOURCE_FILE
    assert g1["source_sha256"] == _G1_SOURCE_SHA256
    assert g1["group"] == "G1"
    assert "48" in g1["derivation_algorithm"]
    assert len(bytes.fromhex(g1["signature_hex"])) == 48


def test_group_specific_source_lines_are_recorded_for_both_groups() -> None:
    source = _manifest()["curve_encoding_source"]
    assert source["g1_compressed_infinity_symbol"] == "G1.FromCompressed"
    assert source["g2_compressed_infinity_symbol"] == "G2.FromCompressed"
    assert "48 bytes" in source["g1_length_source_line"]
    assert "96 bytes" in source["g2_length_source_line"]
    for key in ("g1_compression_flag_source_line", "g2_compression_flag_source_line"):
        assert "1<<7" in source[key], key
    for key in ("g1_compressed_infinity_source_line", "g2_compressed_infinity_source_line"):
        match = re.search(r"v\s*!=\s*0x([0-9a-fA-F]{2})", source[key])
        assert match is not None, key
        assert int(match.group(1), 16) == 0xC0, key
    # the old group-agnostic keys must not come back
    for stale in ("compressed_infinity_symbol", "compressed_infinity_source_line"):
        assert stale not in source, stale


def test_pinned_curve_encoding_source_carries_complete_evidence() -> None:
    source = _manifest()["curve_encoding_source"]
    assert source["module"] == "github.com/kilic/bls12-381"
    assert source["version"] == "v0.1.0"
    assert source["module_go_sum_h1"].startswith("h1:")
    assert source["source_uri"].startswith("https://")
    assert source["license_result"] == "APACHE-2.0"
    assert len(source["license_file_sha256"]) == 64
    for name, entry in source["files"].items():
        assert name.endswith(".go")
        assert len(entry["sha256"]) == 64
        assert set(entry["sha256"]) <= _HEX_CHARS
        assert entry["provides"].strip()
    # the pinned source must not be overclaimed as the normative specification
    assert source["is_normative_specification"] is False
    assert "NOT the normative specification" in source["scope_limitation"]
    assert source["evidence_origin"] == ("LOCALLY_PINNED_UPSTREAM_GO_MODULE_IN_OFFICIAL_DRAND_DEPENDENCY_GRAPH")


def test_field_modulus_is_derived_from_the_recorded_source_line_not_a_local_constant() -> None:
    """Re-derive p from the verbatim upstream source line the manifest records, then match bytes."""
    source = _manifest()["curve_encoding_source"]
    line = source["field_modulus_source_line"]
    match = re.search(r"0x([0-9a-fA-F]{96})", line)
    assert match is not None, line
    modulus_from_source = int(match.group(1), 16)

    fixture = _fixture("negative_fixtures", "neg_non_canonical_unreduced_x_signature")
    raw = bytes.fromhex(fixture["signature_hex"])
    x_coordinate = int.from_bytes(bytes([raw[0] & 0x1F]) + raw[1:], "big")
    assert x_coordinate == modulus_from_source
    # and only then cross-check the local duplicate, which is not the authority
    assert modulus_from_source == _BLS12_381_BASE_FIELD_MODULUS
    assert "must be less than modulus" in source["non_canonical_rule_source_line"]


def test_compressed_infinity_flag_byte_is_derived_from_the_recorded_source_line() -> None:
    source = _manifest()["curve_encoding_source"]
    for fixture_id, key, length, line_key in (
        ("neg_g1_infinity_signature", "signature_hex", 48, "g1_compressed_infinity_source_line"),
        ("neg_g2_infinity_public_key", "public_key_hex", 96, "g2_compressed_infinity_source_line"),
    ):
        match = re.search(r"v\s*!=\s*0x([0-9a-fA-F]{2})", source[line_key])
        assert match is not None, line_key
        flag_byte = int(match.group(1), 16)
        assert flag_byte == 0xC0, line_key
        raw = bytes.fromhex(_fixture("negative_fixtures", fixture_id)[key])
        assert len(raw) == length
        assert raw[0] == flag_byte
        assert not any(raw[1:])


def test_the_subgroup_invalid_class_is_recorded_as_blocked() -> None:
    blocked = _manifest()["unresolved_or_blocked_fixtures"]
    assert tuple(entry["fixture_id"] for entry in blocked) == _EXPECTED_BLOCKED_IDS
    entry = blocked[0]
    assert entry["status"] == "FIXTURE_ADMISSION_BLOCKED"
    assert entry["coverage_class"] == "subgroup_invalid"
    assert entry["blocked_reason"] == "mandatory_subgroup_invalid_fixture_provenance_unresolved"
    # the blocker must state WHY: the deterministic base positive is unadmitted
    assert "NOT admitted" in entry["note"]
    assert "license_explicitly_proven=false" in entry["note"]


def test_mandatory_coverage_matrix_separates_proven_classes_from_blocked_ones() -> None:
    matrix = _manifest()["mandatory_coverage_matrix"]
    assert set(matrix) == {"infinity", "non_canonical_encoding", "subgroup_invalid"}
    negative_ids = {entry["fixture_id"] for entry in _manifest()["negative_fixtures"]}

    for name in _EXPECTED_PROVEN_COVERAGE_CLASSES:
        entry = matrix[name]
        assert entry["result"] == "PROVENANCE_BACKED", name
        assert entry["provenance_backed"] is True, name
        assert entry["fixture_ids"], name
        assert entry["why_distinct"].strip(), name

    for name in _EXPECTED_BLOCKED_COVERAGE_CLASSES:
        entry = matrix[name]
        assert entry["result"] == "BLOCKED", name
        assert entry["provenance_backed"] is False, name
        assert entry["blocked_reason"], name
        assert entry["candidate_evidence_retained"].strip(), name

    for name, entry in matrix.items():
        for fixture_id in entry["fixture_ids"]:
            assert fixture_id in negative_ids, (name, fixture_id)
            fixture = _fixture("negative_fixtures", fixture_id)
            assert fixture["coverage_class"] == name, (name, fixture_id)
            assert fixture["observed_reproducibly"] is True, fixture_id


def test_a_provenance_backed_class_never_rests_on_an_unadmitted_positive() -> None:
    """No positive fixture is admitted, so a derivation from one cannot confer provenance."""
    manifest = _manifest()
    for fixture in manifest["positive_fixtures"]:
        assert fixture["license_explicitly_proven"] is False, fixture["fixture_id"]
    assert manifest["admission"]["fixture_corpus_admitted"] is False

    matrix = manifest["mandatory_coverage_matrix"]
    for name, entry in matrix.items():
        if entry["result"] != "PROVENANCE_BACKED":
            continue
        for fixture_id in entry["fixture_ids"]:
            provenance = _fixture("negative_fixtures", fixture_id)["provenance"]
            assert provenance in _PROVENANCE_BACKING_LABELS, (name, fixture_id, provenance)
            assert provenance not in _CANDIDATE_ONLY_PROVENANCE_LABELS

    # and no fixture anywhere may still claim derivation from an *admitted* positive
    raw = _MANIFEST_PATH.read_text(encoding="utf-8")
    assert "OF_ADMITTED_POSITIVE" not in raw
    assert "DERIVED_FROM_ADMITTED_POSITIVE" not in raw


def test_the_retained_subgroup_candidate_keeps_its_observed_evidence() -> None:
    """Downgrading provenance must not delete the reproducible BLST_POINT_NOT_IN_GROUP observation."""
    fixture = _fixture("negative_fixtures", "neg_one_bit_signature_corruption")
    assert fixture["provenance"] == "DETERMINISTIC_MUTATION_OF_UNADMITTED_OFFICIAL_POSITIVE"
    assert fixture["provenance_backed"] is False
    assert fixture["base_fixture_admitted"] is False
    assert fixture["evidence_status"] == "CANDIDATE_EVIDENCE_ONLY_NOT_PROVENANCE_BACKED"
    assert fixture["blocked_reason"] == "base_positive_fixture_unadmitted_license_unresolved"
    # evidence retained, not deleted
    assert fixture["observed_blst_code"] == "BLST_POINT_NOT_IN_GROUP"
    assert fixture["observed_reproducibly"] is True
    assert fixture["expected_reason"] == "subgroup_check_failed"
    # never relabelled official or normative
    assert fixture["source_type"] == "derived"


def test_coverage_classes_are_not_satisfied_by_length_rejections_or_by_each_other() -> None:
    matrix = _manifest()["mandatory_coverage_matrix"]
    length_rejection_ids = {
        "neg_signature_47_bytes",
        "neg_signature_49_bytes",
        "neg_public_key_95_bytes",
        "neg_public_key_97_bytes",
    }
    claimed: set[str] = set()
    for entry in matrix.values():
        ids = set(entry["fixture_ids"])
        assert not ids & length_rejection_ids
        assert not ids & claimed, "a fixture may not satisfy two mandatory classes at once"
        claimed |= ids

    # infinity must not be counted as subgroup-invalid coverage
    infinity_ids = set(matrix["infinity"]["fixture_ids"])
    assert not infinity_ids & set(matrix["subgroup_invalid"]["fixture_ids"])
    assert not infinity_ids & set(matrix["non_canonical_encoding"]["fixture_ids"])


def test_subgroup_invalid_candidate_is_a_real_subgroup_rejection_but_not_provenance_backed() -> None:
    """The observation is real; the provenance is not. The test name must not overstate either."""
    fixture = _fixture("negative_fixtures", "neg_one_bit_signature_corruption")
    assert fixture["coverage_class"] == "subgroup_invalid"
    assert fixture["expected_reason"] == "subgroup_check_failed"
    assert fixture["observed_blst_code"] == "BLST_POINT_NOT_IN_GROUP"
    assert fixture["provenance"] == "DETERMINISTIC_MUTATION_OF_UNADMITTED_OFFICIAL_POSITIVE"
    assert fixture["provenance_backed"] is False

    corrupted = bytes.fromhex(fixture["signature_hex"])
    official = bytes.fromhex(_OFFICIAL_SIGNATURE_HEX)
    assert len(corrupted) == 48, "must not be a length rejection"
    # exactly the stated derivation: final byte XOR 0x01
    assert corrupted == official[:-1] + bytes([official[-1] ^ 0x01])
    assert sum(bin(a ^ b).count("1") for a, b in zip(corrupted, official, strict=True)) == 1


def test_non_canonical_fixture_encodes_the_normative_field_modulus() -> None:
    fixture = _fixture("negative_fixtures", "neg_non_canonical_unreduced_x_signature")
    assert fixture["coverage_class"] == "non_canonical_encoding"
    assert fixture["provenance"] == "PINNED_UPSTREAM_SOURCE_KILIC_BLS12_381_V0_1_0"
    assert fixture["normative_constant"] == "BLS12_381_BASE_FIELD_MODULUS"
    assert fixture["observed_blst_code"] == "BLST_BAD_ENCODING"
    assert fixture["expected_reason"] == "signature_point_invalid"

    raw = bytes.fromhex(fixture["signature_hex"])
    assert len(raw) == 48, "must not be a length rejection"
    assert raw[0] & 0x80 == 0x80, "compression bit must be set"
    assert raw[0] & 0x40 == 0, "must not be an infinity encoding"
    x_coordinate = int.from_bytes(bytes([raw[0] & 0x1F]) + raw[1:], "big")
    assert x_coordinate == _BLS12_381_BASE_FIELD_MODULUS
    # non-canonical precisely because a canonical encoding requires x < p
    assert x_coordinate >= _BLS12_381_BASE_FIELD_MODULUS

    module = _load_script("modulus")
    assert module.BLS12_381_BASE_FIELD_MODULUS == _BLS12_381_BASE_FIELD_MODULUS


def test_fixture_license_support_is_recorded_honestly_as_unproven() -> None:
    for fixture in _manifest()["positive_fixtures"]:
        assert fixture["license_explicitly_proven"] is False, fixture["fixture_id"]
    assert "fixture_license_unresolved" in _manifest()["admission"]["fixture_blockers"]


def test_official_positive_fixtures_are_pinned_to_the_official_chain_endpoints() -> None:
    official = [entry for entry in _manifest()["positive_fixtures"] if entry["source_type"] == "official_http_api"]
    assert len(official) == 2
    for fixture in official:
        assert fixture["provenance"] == "OFFICIAL_DRAND_HTTP_API_V2"
        assert fixture["source_pin"].startswith("https://api.drand.sh/v2/chains/")
        assert _QUICKNET_CHAIN_HASH in fixture["source_pin"]
        assert len(fixture["raw_response_sha256"]) == 64
        assert set(fixture["raw_response_sha256"]) <= _HEX_CHARS
        assert fixture["license"].startswith("OFFICIAL_PUBLIC_RANDOMNESS_BEACON")
        assert fixture["expected_result"] == "round_structurally_verified"


def test_chain_profile_matches_the_reverified_official_quicknet_values() -> None:
    profile = _manifest()["chain_profile"]
    assert profile["chain_hash"] == _QUICKNET_CHAIN_HASH
    assert profile["beacon_id"] == "quicknet"
    assert profile["scheme_id"] == "bls-unchained-g1-rfc9380"
    assert profile["dst"] == _QUICKNET_DST
    assert profile["period_seconds"] == _PERIOD
    assert profile["genesis_time_seconds"] == _GENESIS
    assert profile["public_key_group"] == "G2"
    assert profile["signature_group"] == "G1"
    assert profile["public_key_encoded_length"] == 96
    assert profile["signature_encoded_length"] == 48
    assert profile["message_algorithm"] == "sha256(round.to_bytes(8, 'big', signed=False))"
    assert profile["randomness_algorithm"] == "sha256(signature_bytes)"
    assert profile["round_time_formula"] == "genesis_time + (round - 1) * period"


def test_round_message_is_big_endian_and_sha256_prehashed() -> None:
    round_bytes = _OFFICIAL_ROUND.to_bytes(8, "big", signed=False)
    assert round_bytes.hex() == "000000000000002a"
    assert hashlib.sha256(round_bytes).hexdigest() == _OFFICIAL_MESSAGE_DIGEST_HEX

    little_endian = _OFFICIAL_ROUND.to_bytes(8, "little", signed=False)
    assert little_endian.hex() == "2a00000000000000"
    assert hashlib.sha256(little_endian).hexdigest() != _OFFICIAL_MESSAGE_DIGEST_HEX
    assert round_bytes.hex() != _OFFICIAL_MESSAGE_DIGEST_HEX

    fixture = _fixture("positive_fixtures", "pos_official_round_42")
    assert fixture["expected_message_digest_hex"] == _OFFICIAL_MESSAGE_DIGEST_HEX
    assert fixture["round"] == _OFFICIAL_ROUND


def test_randomness_is_sha256_over_the_exact_signature_bytes() -> None:
    signature = bytes.fromhex(_OFFICIAL_SIGNATURE_HEX)
    assert len(signature) == 48
    assert hashlib.sha256(signature).hexdigest() == _OFFICIAL_RANDOMNESS_HEX

    fixture = _fixture("positive_fixtures", "pos_official_round_42")
    assert fixture["signature_hex"] == _OFFICIAL_SIGNATURE_HEX
    assert fixture["expected_randomness_hex"] == _OFFICIAL_RANDOMNESS_HEX
    # randomness must not be confused with the signed message digest
    assert _OFFICIAL_RANDOMNESS_HEX != _OFFICIAL_MESSAGE_DIGEST_HEX


def test_round_time_is_a_pure_formula_and_never_an_ambient_clock() -> None:
    expected = _GENESIS + (_OFFICIAL_ROUND - 1) * _PERIOD
    assert expected == 1_692_803_490
    assert _fixture("positive_fixtures", "pos_official_round_42")["expected_round_time"] == expected


def test_dst_is_pinned_exactly_to_the_g1_rfc9380_tag() -> None:
    assert _QUICKNET_DST == "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"
    assert len(_QUICKNET_DST.encode("ascii")) == 43
    assert _QUICKNET_DST.endswith("_NUL_")
    assert "BLS12381G2" not in _QUICKNET_DST
    assert _manifest()["chain_profile"]["dst"] == _QUICKNET_DST


def test_candidate_dependency_pins_and_the_version_ambiguity_are_recorded() -> None:
    dependency = _manifest()["candidate_dependency"]
    assert dependency["profile_id"] == "D-DEP-DRAND-PYBLST-0.3.15-CANDIDATE.v1"
    assert dependency["package"] == "pyblst"
    assert dependency["upstream_blst_version"] == "0.3.16"

    # exactly which object carries 0.3.15
    for field in (
        "distribution_version",
        "pypi_info_version",
        "wheel_metadata_version",
        "sdist_metadata_version",
        "pyproject_project_version",
    ):
        assert dependency[field] == "0.3.15", field
    # exactly which object remains 0.3.14
    assert dependency["cargo_toml_version"] == "0.3.14"
    assert dependency["cargo_lock_version"] == "0.3.14"
    # what could not be observed at all
    assert dependency["compiled_crate_version"] == "NOT_OBSERVABLE"
    # why the divergence is an ambiguity rather than a closed metadata contradiction
    assert dependency["version_identity_resolved"] is False
    assert dependency["binary_source_correspondence_proven"] is False
    assert dependency["attestations_present"] is False
    assert dependency["provenance_present"] is False
    assert dependency["version_0_3_14_also_published_as_a_distribution"] is True
    assert dependency["version_identity_ambiguity_reason"]


def test_upstream_tag_and_build_workflow_facts_are_recorded_not_erased() -> None:
    """The tag exists; NOT_OBSERVED was wrong and must never come back."""
    dependency = _manifest()["candidate_dependency"]
    assert dependency["upstream_repository"] == "OpShin/pyblst"
    assert dependency["tag_version"] == "0.3.15"
    assert dependency["tag_version"] != "NOT_OBSERVED"
    assert dependency["tag_commit"] == "dadf9cbac859774d8e9115881b34f8e7a82e61d8"
    assert dependency["tag_commit_message"] == "New release with locked cargo"
    assert dependency["tag_pyproject_version"] == "0.3.15"
    assert dependency["tag_cargo_toml_version"] == "0.3.14"
    assert dependency["tag_cargo_lock_version"] == "0.3.14"
    assert dependency["github_release_object"] == "NONE"
    assert dependency["tag_build_workflow"] == ".github/workflows/CI.yml"
    assert dependency["tag_ci_run_id"] == "18509666718"
    assert dependency["tag_ci_run_result"] == "SUCCESS"
    assert dependency["tag_ci_run_head"] == dependency["tag_commit"]
    assert dependency["tag_evidence_origin"] == "CONTROLLER_VERIFIED_NOT_LOCALLY_REFETCHED"


def test_a_tag_plus_successful_workflow_is_never_upgraded_to_artifact_attestation() -> None:
    dependency = _manifest()["candidate_dependency"]
    assert dependency["pypi_trusted_publishing"] == "NO"
    assert dependency["pypi_artifact_attestation"] == "ABSENT"
    assert dependency["source_to_sdist_binding"] == "NOT_PROVEN"
    assert dependency["source_to_wheel_binding"] == "NOT_PROVEN"
    assert dependency["binary_source_correspondence_proven"] is False
    # the blocker survives the stronger tag evidence
    assert _manifest()["admission"]["dependency_qualification"] == "BLOCKED"
    assert "package_version_identity_ambiguous" in _manifest()["admission"]["dependency_blockers"]
    assert dependency["pyo3_version"] == "0.26.0"
    assert dependency["wheel_sha256"] == ("0c2e1f73a4739e9c5c000f00e362d6abe8cd405ec4b94a7db509ef546033999a")
    assert dependency["sdist_sha256"] == ("258831210c069ece6d9894bffbe8013834f094d874f30070a4ad8d5a0e317c08")
    assert dependency["license_resolution"] == (
        "MIT_TEXT_IN_LICENSE_TXT_NO_SPDX_CLASSIFIER_AND_NULL_PYPI_LICENSE_FIELD"
    )
    for key in (
        "wheel_extension_sha256",
        "license_sdist_file_sha256",
        "license_wheel_file_sha256",
    ):
        assert len(dependency[key]) == 64
        assert set(dependency[key]) <= _HEX_CHARS, key


def test_official_reference_verifier_pin_is_recorded_exactly() -> None:
    reference = _manifest()["reference_verifier"]
    assert reference["module"] == "github.com/drand/drand/v2"
    assert reference["version"] == "v2.1.6"
    assert reference["go_toolchain"] == "go1.26.5 windows/amd64"
    assert reference["agreement"] == "EXACT_ON_ALL_COMPARED_CASES"
    assert len(reference["schemes_go_sha256"]) == 64
    assert set(reference["schemes_go_sha256"]) <= _HEX_CHARS
    assert reference["module_go_sum_h1"].startswith("h1:")


def test_qualification_script_has_no_network_clock_filesystem_or_environment_surface() -> None:
    parsed = ast.parse(_script_source())
    imported_roots: set[str] = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])
    assert not imported_roots & _PROHIBITED_IMPORT_ROOTS, sorted(imported_roots & _PROHIBITED_IMPORT_ROOTS)

    called_names = {
        node.func.id for node in ast.walk(parsed) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(parsed)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called_names & _PROHIBITED_CALL_NAMES, sorted(called_names & _PROHIBITED_CALL_NAMES)
    assert not called_attributes & _PROHIBITED_CALL_ATTRIBUTES, sorted(called_attributes & _PROHIBITED_CALL_ATTRIBUTES)


def test_qualification_script_imports_the_candidate_dependency_only_lazily() -> None:
    parsed = ast.parse(_script_source())
    module_level_imports = {alias.name for node in parsed.body if isinstance(node, ast.Import) for alias in node.names}
    assert "pyblst" not in module_level_imports

    function_bodies = [node for node in ast.walk(parsed) if isinstance(node, ast.FunctionDef)]
    lazy_import_functions = {
        func.name
        for func in function_bodies
        for node in ast.walk(func)
        if isinstance(node, ast.Import) and any(alias.name == "pyblst" for alias in node.names)
    }
    assert lazy_import_functions, "pyblst must be imported inside a function body"


def test_qualification_script_imports_and_computes_without_the_candidate_dependency() -> None:
    with pytest.raises(ImportError):
        importlib.import_module("pyblst")

    module = _load_script("compute")
    assert module.DRAND_QUICKNET_QUALIFICATION_PROFILE_ID == ("MT4-S3A-DRAND-QUICKNET-QUALIFICATION-CANDIDATE.v1")
    assert module.CANDIDATE_PACKAGE_VERSION == "0.3.15"
    assert module.QUICKNET_CHAIN_HASH == _QUICKNET_CHAIN_HASH
    assert module.QUICKNET_DST == _QUICKNET_DST.encode("ascii")
    assert module.quicknet_message_digest(_OFFICIAL_ROUND).hex() == _OFFICIAL_MESSAGE_DIGEST_HEX
    assert module.quicknet_randomness(bytes.fromhex(_OFFICIAL_SIGNATURE_HEX)).hex() == _OFFICIAL_RANDOMNESS_HEX
    assert module.quicknet_round_time(_OFFICIAL_ROUND, _GENESIS, _PERIOD) == 1_692_803_490
    assert len(module.BLS12_381_G2_GENERATOR_COMPRESSED) == 96


def test_qualification_reason_inventory_is_closed_and_complete() -> None:
    module = _load_script("reasons")
    reasons = {member.value for member in module.QuicknetQualificationReason}
    required = {
        "wrong_input_type",
        "field_inventory_invalid",
        "field_type_invalid",
        "resource_bound_exceeded",
        "chain_profile_binding_invalid",
        "round_invalid",
        "public_key_encoding_invalid",
        "signature_encoding_invalid",
        "public_key_point_invalid",
        "signature_point_invalid",
        "point_at_infinity_rejected",
        "subgroup_check_failed",
        "non_canonical_encoding",
        "message_encoding_invalid",
        "dst_mismatch",
        "signature_verification_failed",
        "randomness_mismatch",
        "dependency_profile_unavailable",
        "dependency_version_mismatch",
        "dependency_artifact_hash_mismatch",
        "dependency_exception",
        "reference_verifier_mismatch",
        "fixture_provenance_invalid",
        "fixture_license_unresolved",
        "governance_structural_violation",
        "artifact_inconsistent",
        "round_structurally_verified",
    }
    assert reasons == required
    # every negative fixture expectation must name a member of the closed inventory
    for fixture in _manifest()["negative_fixtures"]:
        assert fixture["expected_reason"] in reasons, fixture["fixture_id"]


def test_scalar_helpers_reject_wrong_exact_types_and_out_of_range_rounds() -> None:
    module = _load_script("helpers")
    for bad_round in ("42", True, 42.0):
        with pytest.raises(TypeError):
            module.quicknet_message_digest(bad_round)
    for bad_round in (0, -1, 1 << 64):
        with pytest.raises(ValueError, match="round_number out of range"):
            module.quicknet_message_digest(bad_round)

    signature = bytes.fromhex(_OFFICIAL_SIGNATURE_HEX)
    with pytest.raises(TypeError):
        module.quicknet_randomness(bytearray(signature))
    with pytest.raises(ValueError, match="exactly 48 bytes"):
        module.quicknet_randomness(signature[:47])
    with pytest.raises(TypeError):
        module.quicknet_round_time(_OFFICIAL_ROUND, _GENESIS, True)


def test_structural_rejections_fail_closed_before_the_dependency_is_needed() -> None:
    module = _load_script("structural")
    reason_type = module.QuicknetQualificationReason
    baseline = {
        "round_number": _OFFICIAL_ROUND,
        "public_key_bytes": bytes(96),
        "signature_bytes": bytes(48),
        "chain_hash": _QUICKNET_CHAIN_HASH,
    }
    cases = (
        ({"round_number": "42"}, reason_type.WRONG_INPUT_TYPE),
        ({"round_number": True}, reason_type.WRONG_INPUT_TYPE),
        ({"signature_bytes": bytearray(48)}, reason_type.WRONG_INPUT_TYPE),
        ({"public_key_bytes": bytearray(96)}, reason_type.WRONG_INPUT_TYPE),
        ({"chain_hash": b"\x00" * 32}, reason_type.WRONG_INPUT_TYPE),
        ({"dst": _QUICKNET_DST}, reason_type.WRONG_INPUT_TYPE),
        ({"genesis_time": True}, reason_type.FIELD_TYPE_INVALID),
        ({"period": 3.0}, reason_type.FIELD_TYPE_INVALID),
        ({"round_number": 0}, reason_type.ROUND_INVALID),
        ({"round_number": 1 << 64}, reason_type.ROUND_INVALID),
        ({"chain_hash": "00" * 32}, reason_type.CHAIN_PROFILE_BINDING_INVALID),
        ({"chain_hash": _QUICKNET_CHAIN_HASH.upper()}, reason_type.CHAIN_PROFILE_BINDING_INVALID),
        ({"chain_hash": _QUICKNET_CHAIN_HASH[:63]}, reason_type.CHAIN_PROFILE_BINDING_INVALID),
        ({"public_key_bytes": bytes(95)}, reason_type.PUBLIC_KEY_ENCODING_INVALID),
        ({"public_key_bytes": bytes(97)}, reason_type.PUBLIC_KEY_ENCODING_INVALID),
        ({"signature_bytes": bytes(47)}, reason_type.SIGNATURE_ENCODING_INVALID),
        ({"signature_bytes": bytes(49)}, reason_type.SIGNATURE_ENCODING_INVALID),
        ({"dst": b"BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_NUL_"}, reason_type.DST_MISMATCH),
        ({"dst": _QUICKNET_DST.encode("ascii") + b"\x00"}, reason_type.DST_MISMATCH),
    )
    for override, expected in cases:
        call = dict(baseline)
        call.update(override)
        qualified, reason, details = module.qualify_quicknet_round(**call)
        assert qualified is False, override
        assert reason is expected, (override, reason)
        assert details == {}


def test_hostile_bytes_subclasses_are_rejected_by_exact_type_checks() -> None:
    module = _load_script("subclass")
    reason_type = module.QuicknetQualificationReason

    class HostileBytes(bytes):
        __slots__ = ()

        def __len__(self) -> int:  # pragma: no cover - must never be reached
            raise AssertionError("length must not be consulted on a rejected subclass")

    baseline = {
        "round_number": _OFFICIAL_ROUND,
        "public_key_bytes": bytes(96),
        "signature_bytes": bytes(48),
        "chain_hash": _QUICKNET_CHAIN_HASH,
    }
    for field, length in (("signature_bytes", 48), ("public_key_bytes", 96)):
        call = dict(baseline)
        call[field] = HostileBytes(bytes(length))
        qualified, reason, details = module.qualify_quicknet_round(**call)
        assert qualified is False
        assert reason is reason_type.WRONG_INPUT_TYPE
        assert details == {}


def test_only_the_exact_quicknet_temporal_profile_can_ever_verify() -> None:
    """A successful round result must be impossible under any non-Quicknet genesis/period."""
    module = _load_script("temporal")
    reason_type = module.QuicknetQualificationReason
    baseline = {
        "round_number": _OFFICIAL_ROUND,
        "public_key_bytes": bytes(96),
        "signature_bytes": bytes(48),
        "chain_hash": _QUICKNET_CHAIN_HASH,
    }
    rejected_profiles = (
        {"genesis_time": _GENESIS - 1},
        {"genesis_time": _GENESIS + 1},
        {"genesis_time": 0},
        {"genesis_time": -1},
        {"genesis_time": 1 << 64},
        {"period": 0},
        {"period": -1},
        {"period": -7},
        {"period": 1},
        {"period": 4},
        {"period": 1 << 64},
        {"genesis_time": 0, "period": -7},
    )
    for override in rejected_profiles:
        call = dict(baseline)
        call.update(override)
        verified, reason, details = module.qualify_quicknet_round(**call)
        assert verified is False, override
        assert reason is reason_type.CHAIN_PROFILE_BINDING_INVALID, (override, reason)
        assert details == {}

    # wrong exact types are still type errors, never a silent profile override
    for override in (
        {"genesis_time": True},
        {"period": True},
        {"genesis_time": float(_GENESIS)},
        {"period": 3.0},
    ):
        call = dict(baseline)
        call.update(override)
        verified, reason, details = module.qualify_quicknet_round(**call)
        assert verified is False, override
        assert reason is reason_type.FIELD_TYPE_INVALID, (override, reason)
        assert details == {}


def test_temporal_profile_is_rejected_before_the_dependency_is_ever_loaded() -> None:
    """The wrong-profile rejection must precede dependency import, so it holds with pyblst absent."""
    with pytest.raises(ImportError):
        importlib.import_module("pyblst")
    module = _load_script("temporal_order")
    verified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX),
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
        genesis_time=0,
        period=-7,
    )
    # not DEPENDENCY_PROFILE_UNAVAILABLE: the profile check must win the race
    assert verified is False
    assert reason is module.QuicknetQualificationReason.CHAIN_PROFILE_BINDING_INVALID
    assert details == {}


def test_official_defaults_still_yield_the_exact_official_round_time() -> None:
    module = _load_script("official_time")
    assert module.QUICKNET_GENESIS_TIME_SECONDS == _GENESIS
    assert module.QUICKNET_PERIOD_SECONDS == _PERIOD
    assert module.quicknet_round_time(_OFFICIAL_ROUND, _GENESIS, _PERIOD) == 1_692_803_490


def test_canonical_infinity_is_rejected_before_any_pairing_work() -> None:
    module = _load_script("infinity")
    reason_type = module.QuicknetQualificationReason

    g1_infinity = bytes([0xC0]) + bytes(47)
    g2_infinity = bytes([0xC0]) + bytes(95)
    assert module._is_canonical_infinity(g1_infinity) is True
    assert module._is_canonical_infinity(g2_infinity) is True
    assert module._is_canonical_infinity(bytes.fromhex(_OFFICIAL_SIGNATURE_HEX)) is False
    assert module._is_canonical_infinity(b"") is False
    # canonical COMPRESSED infinity requires BOTH the compression bit 0x80 and the infinity bit 0x40.
    # 0x40 alone is the canonical UNCOMPRESSED infinity encoding and must NOT be classified here.
    assert module._is_canonical_infinity(bytes([0x40]) + bytes(47)) is False
    assert module._is_canonical_infinity(bytes([0x80]) + bytes(47)) is False
    # any non-zero residual bit in the flag byte or the body is NOT canonical infinity
    assert module._is_canonical_infinity(bytes([0xC1]) + bytes(47)) is False
    assert module._is_canonical_infinity(bytes([0xC0]) + bytes(46) + bytes([0x01])) is False
    assert module._is_canonical_infinity(bytes(48)) is False
    assert module._COMPRESSED_INFINITY_FLAG_BYTE == 0xC0

    baseline = {
        "round_number": _OFFICIAL_ROUND,
        "public_key_bytes": bytes(96),
        "signature_bytes": bytes(48),
        "chain_hash": _QUICKNET_CHAIN_HASH,
    }
    for override in ({"signature_bytes": g1_infinity}, {"public_key_bytes": g2_infinity}):
        call = dict(baseline)
        call.update(override)
        qualified, reason, details = module.qualify_quicknet_round(**call)
        assert qualified is False
        assert reason is reason_type.POINT_AT_INFINITY_REJECTED
        assert details == {}


def _decode_recording_pyblst(reject: dict[bytes, Exception]) -> types.ModuleType:
    """A fake dependency that records what reached each decoder and raises for chosen inputs.

    Everything not in ``reject`` decodes and re-compresses to the identical bytes, so the harness is
    forced all the way to the decoder under test rather than short-circuiting earlier.
    """
    seen: dict[str, list[bytes]] = {"g1": [], "g2": []}

    class P1:
        def __init__(self, raw: bytes) -> None:
            self._raw = raw

        @staticmethod
        def uncompress(raw):
            seen["g1"].append(bytes(raw))
            if raw in reject:
                raise reject[raw]
            return P1(bytes(raw))

        @staticmethod
        def hash_to_group(message, dst):
            return P1(bytes(48))

        def compress(self):
            return self._raw

    class P2:
        def __init__(self, raw: bytes) -> None:
            self._raw = raw

        @staticmethod
        def uncompress(raw):
            seen["g2"].append(bytes(raw))
            if raw in reject:
                raise reject[raw]
            return P2(bytes(raw))

        def compress(self):
            return self._raw

    fake = types.ModuleType("pyblst")
    fake.BlstP1Element = P1
    fake.BlstP2Element = P2
    fake.miller_loop = lambda a, b: object()
    fake.final_verify = lambda a, b: True
    fake._seen = seen
    return fake


def test_g1_0x40_reaches_g1_point_decoding_and_returns_signature_point_invalid(monkeypatch) -> None:
    """0x40||47 zeros must be routed to G1 decoding, not short-circuited anywhere earlier."""
    import importlib.metadata as importlib_metadata

    g1_uncompressed_infinity = bytes([0x40]) + bytes(47)
    fake = _decode_recording_pyblst({g1_uncompressed_infinity: ValueError("BLST_BAD_ENCODING")})
    monkeypatch.setitem(sys.modules, "pyblst", fake)
    monkeypatch.setattr(importlib_metadata, "version", lambda name: "0.3.15")
    module = _load_script("g1_0x40")
    reason_type = module.QuicknetQualificationReason

    assert module._is_canonical_infinity(g1_uncompressed_infinity) is False

    verified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX),
        signature_bytes=g1_uncompressed_infinity,
        chain_hash=_QUICKNET_CHAIN_HASH,
    )
    assert verified is False
    assert reason is reason_type.SIGNATURE_POINT_INVALID
    assert details == {}
    # the bytes must actually have reached the G1 decoder
    assert g1_uncompressed_infinity in fake._seen["g1"]
    # and none of the permissive fallbacks may be what produced the result
    assert reason not in {
        reason_type.DEPENDENCY_PROFILE_UNAVAILABLE,
        reason_type.SUBGROUP_CHECK_FAILED,
        reason_type.DEPENDENCY_EXCEPTION,
        reason_type.POINT_AT_INFINITY_REJECTED,
    }


def test_g2_0x40_reaches_g2_point_decoding_and_returns_public_key_point_invalid(monkeypatch) -> None:
    """0x40||95 zeros must be routed to G2 decoding, not short-circuited anywhere earlier."""
    import importlib.metadata as importlib_metadata

    g2_uncompressed_infinity = bytes([0x40]) + bytes(95)
    fake = _decode_recording_pyblst({g2_uncompressed_infinity: ValueError("BLST_BAD_ENCODING")})
    monkeypatch.setitem(sys.modules, "pyblst", fake)
    monkeypatch.setattr(importlib_metadata, "version", lambda name: "0.3.15")
    module = _load_script("g2_0x40")
    reason_type = module.QuicknetQualificationReason

    assert module._is_canonical_infinity(g2_uncompressed_infinity) is False

    verified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=g2_uncompressed_infinity,
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
    )
    assert verified is False
    assert reason is reason_type.PUBLIC_KEY_POINT_INVALID
    assert details == {}
    assert g2_uncompressed_infinity in fake._seen["g2"]
    assert reason not in {
        reason_type.DEPENDENCY_PROFILE_UNAVAILABLE,
        reason_type.SUBGROUP_CHECK_FAILED,
        reason_type.DEPENDENCY_EXCEPTION,
        reason_type.POINT_AT_INFINITY_REJECTED,
    }


def test_absent_candidate_dependency_fails_closed_and_never_qualifies() -> None:
    module = _load_script("absent")
    reason_type = module.QuicknetQualificationReason
    qualified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(
            "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c"
            "8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb"
            "5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a"
        ),
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
    )
    assert qualified is False
    assert reason is reason_type.DEPENDENCY_PROFILE_UNAVAILABLE
    assert details == {}


def test_no_diagnostic_ever_leaks_caller_bytes() -> None:
    module = _load_script("diagnostics")
    secret_marker = bytes([0xAB]) * 48
    qualified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes(96),
        signature_bytes=secret_marker,
        chain_hash="00" * 32,
    )
    assert qualified is False
    assert details == {}
    rendered = f"{reason!r}{reason.value}"
    assert secret_marker.hex() not in rendered
    assert "ab" * 8 not in rendered


def test_manifest_and_script_constants_cannot_drift_apart() -> None:
    module = _load_script("sync")
    profile = _manifest()["chain_profile"]
    assert module.QUICKNET_CHAIN_HASH == profile["chain_hash"]
    assert module.QUICKNET_BEACON_ID == profile["beacon_id"]
    assert module.QUICKNET_SCHEME_ID == profile["scheme_id"]
    assert module.QUICKNET_PERIOD_SECONDS == profile["period_seconds"]
    assert module.QUICKNET_GENESIS_TIME_SECONDS == profile["genesis_time_seconds"]
    assert module.QUICKNET_DST.decode("ascii") == profile["dst"]
    assert module._PUBLIC_KEY_LENGTH == profile["public_key_encoded_length"]
    assert module._SIGNATURE_LENGTH == profile["signature_encoded_length"]

    dependency = _manifest()["candidate_dependency"]
    assert module.CANDIDATE_DEPENDENCY_PROFILE_ID == dependency["profile_id"]
    assert module.CANDIDATE_PACKAGE_NAME == dependency["package"]
    assert module.CANDIDATE_PACKAGE_VERSION == dependency["distribution_version"]

    public_key_hex = _fixture("positive_fixtures", "pos_official_chain_info")["public_key_hex"]
    assert len(bytes.fromhex(public_key_hex)) == profile["public_key_encoded_length"]
    # the recorded G2 generator must never be mistaken for the chain public key
    assert module.BLS12_381_G2_GENERATOR_COMPRESSED.hex() != public_key_hex


_HOSTILE_MARKER = "HOSTILE_DEPENDENCY_MARKER"
_DEPENDENCY_STAGES = (
    "pk_uncompress",
    "sig_uncompress",
    "pk_compress",
    "sig_compress",
    "bytes_conversion",
    "hash_to_group",
    "generator_uncompress",
    "miller_loop",
    "final_verify",
)


def _hostile_pyblst(stage: str):
    """A fake candidate dependency that raises a marked RuntimeError at exactly one stage."""
    boom = RuntimeError(f"{_HOSTILE_MARKER}_{stage}")
    signature = bytes.fromhex(_OFFICIAL_SIGNATURE_HEX)
    public_key = bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX)

    class ExplodingBytes:
        def __bytes__(self):
            raise boom

    class P1:
        @staticmethod
        def uncompress(raw):
            if stage == "sig_uncompress":
                raise boom
            return P1()

        @staticmethod
        def hash_to_group(message, dst):
            if stage == "hash_to_group":
                raise boom
            return P1()

        def compress(self):
            if stage == "sig_compress":
                raise boom
            if stage == "bytes_conversion":
                return ExplodingBytes()
            return signature

    class P2:
        @staticmethod
        def uncompress(raw):
            if stage == "generator_uncompress" and raw != public_key:
                raise boom
            if stage == "pk_uncompress":
                raise boom
            return P2()

        def compress(self):
            if stage == "pk_compress":
                raise boom
            return public_key

    def miller_loop(a, b):
        if stage == "miller_loop":
            raise boom
        return object()

    def final_verify(a, b):
        if stage == "final_verify":
            raise boom
        return True

    fake = types.ModuleType("pyblst")
    fake.BlstP1Element = P1
    fake.BlstP2Element = P2
    fake.miller_loop = miller_loop
    fake.final_verify = final_verify
    return fake


@pytest.mark.parametrize("stage", _DEPENDENCY_STAGES)
def test_no_dependency_exception_escapes_raw_from_any_stage(stage: str, monkeypatch) -> None:
    import importlib.metadata as importlib_metadata

    monkeypatch.setitem(sys.modules, "pyblst", _hostile_pyblst(stage))
    monkeypatch.setattr(importlib_metadata, "version", lambda name: "0.3.15")
    module = _load_script(f"hostile_{stage}")

    verified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX),
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
    )
    assert verified is False, stage
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_EXCEPTION, (stage, reason)
    assert details == {}
    assert _HOSTILE_MARKER not in reason.value
    assert _HOSTILE_MARKER not in repr(details)


def _install_raising_pyblst(monkeypatch, exc: BaseException) -> None:
    class RaisingLoader(importlib.abc.Loader):
        def create_module(self, spec):
            return types.ModuleType(spec.name)

        def exec_module(self, module):
            raise exc

    class RaisingFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "pyblst":
                return importlib.machinery.ModuleSpec(fullname, RaisingLoader())
            return None

    monkeypatch.delitem(sys.modules, "pyblst", raising=False)
    monkeypatch.setattr(sys, "meta_path", [RaisingFinder(), *sys.meta_path])


def _qualify(module):
    return module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX),
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
    )


def test_genuine_package_absence_is_the_only_unavailable_import_case() -> None:
    """pyblst really is absent in the repo venv, so this is the true DEPENDENCY_PROFILE_UNAVAILABLE."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pyblst")
    module = _load_script("absent_import")
    verified, reason, details = _qualify(module)
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_PROFILE_UNAVAILABLE
    assert details == {}


def test_internal_pyblst_importerror_is_a_failure_not_an_absence(monkeypatch) -> None:
    _install_raising_pyblst(monkeypatch, ImportError("INTERNAL_PYBLST_IMPORT_FAILURE"))
    module = _load_script("internal_importerror")
    verified, reason, details = _qualify(module)
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_EXCEPTION
    assert reason is not module.QuicknetQualificationReason.DEPENDENCY_PROFILE_UNAVAILABLE
    assert details == {}
    assert "INTERNAL_PYBLST_IMPORT_FAILURE" not in reason.value


def test_missing_internal_dependency_of_pyblst_is_a_failure_not_an_absence(monkeypatch) -> None:
    _install_raising_pyblst(monkeypatch, ModuleNotFoundError("No module named 'blst_backend'", name="blst_backend"))
    module = _load_script("internal_modulenotfound")
    verified, reason, details = _qualify(module)
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_EXCEPTION
    assert details == {}


def test_modulenotfound_naming_pyblst_itself_is_an_absence(monkeypatch) -> None:
    _install_raising_pyblst(monkeypatch, ModuleNotFoundError("No module named 'pyblst'", name="pyblst"))
    module = _load_script("named_absence")
    verified, reason, details = _qualify(module)
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_PROFILE_UNAVAILABLE
    assert details == {}


def test_package_metadata_absence_is_unavailable_but_metadata_errors_are_not(monkeypatch) -> None:
    import importlib.metadata as importlib_metadata

    monkeypatch.setitem(sys.modules, "pyblst", types.ModuleType("pyblst"))

    def not_found(name):
        raise importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib_metadata, "version", not_found)
    module = _load_script("metadata_absent")
    verified, reason, details = _qualify(module)
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_PROFILE_UNAVAILABLE
    assert details == {}

    for error in (ImportError("METADATA_BACKEND_FAILURE"), RuntimeError("METADATA_BACKEND_EXPLODED")):

        def boom(name, _error=error):
            raise _error

        monkeypatch.setattr(importlib_metadata, "version", boom)
        module = _load_script(f"metadata_{type(error).__name__}")
        verified, reason, details = _qualify(module)
        assert verified is False, type(error).__name__
        assert reason is module.QuicknetQualificationReason.DEPENDENCY_EXCEPTION, type(error).__name__
        assert reason is not module.QuicknetQualificationReason.DEPENDENCY_PROFILE_UNAVAILABLE
        assert details == {}
        assert "METADATA_BACKEND" not in reason.value


def test_hostile_metadata_return_type_is_a_version_mismatch_not_a_crash(monkeypatch) -> None:
    import importlib.metadata as importlib_metadata

    monkeypatch.setitem(sys.modules, "pyblst", _hostile_pyblst("none"))

    class HostileVersion(str):
        def __eq__(self, other):
            raise RuntimeError("HOSTILE_VERSION_COMPARISON")

        __hash__ = None

    monkeypatch.setattr(importlib_metadata, "version", lambda name: HostileVersion("0.3.15"))
    module = _load_script("hostile_version_type")
    verified, reason, details = _qualify(module)
    assert verified is False
    # exact-type check rejects the subclass before its __eq__ can ever run
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_VERSION_MISMATCH
    assert details == {}


def test_dependency_import_failures_are_all_mapped(monkeypatch) -> None:
    import importlib.metadata as importlib_metadata

    # a non-ImportError raised during import must map to DEPENDENCY_EXCEPTION
    class BoomLoader(importlib.abc.Loader):
        def create_module(self, spec):
            return types.ModuleType(spec.name)

        def exec_module(self, module):
            raise RuntimeError(f"{_HOSTILE_MARKER}_import")

    class BoomFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "pyblst":
                return importlib.machinery.ModuleSpec(fullname, BoomLoader())
            return None

    monkeypatch.delitem(sys.modules, "pyblst", raising=False)
    finder = BoomFinder()
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    module = _load_script("hostile_import")
    verified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX),
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
    )
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_EXCEPTION
    assert details == {}
    assert _HOSTILE_MARKER not in reason.value

    # importlib.metadata raising something other than PackageNotFoundError must also be mapped
    monkeypatch.setattr(sys, "meta_path", [m for m in sys.meta_path if m is not finder])
    monkeypatch.setitem(sys.modules, "pyblst", types.ModuleType("pyblst"))

    def boom_version(name):
        raise RuntimeError(f"{_HOSTILE_MARKER}_metadata")

    monkeypatch.setattr(importlib_metadata, "version", boom_version)
    module = _load_script("hostile_metadata")
    verified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX),
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
    )
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_EXCEPTION
    assert details == {}


def test_dependency_version_mismatch_is_still_distinctly_reported(monkeypatch) -> None:
    import importlib.metadata as importlib_metadata

    monkeypatch.setitem(sys.modules, "pyblst", _hostile_pyblst("none"))
    monkeypatch.setattr(importlib_metadata, "version", lambda name: "0.3.14")
    module = _load_script("version_mismatch")
    verified, reason, details = module.qualify_quicknet_round(
        round_number=_OFFICIAL_ROUND,
        public_key_bytes=bytes.fromhex(_OFFICIAL_PUBLIC_KEY_HEX),
        signature_bytes=bytes.fromhex(_OFFICIAL_SIGNATURE_HEX),
        chain_hash=_QUICKNET_CHAIN_HASH,
    )
    assert verified is False
    assert reason is module.QuicknetQualificationReason.DEPENDENCY_VERSION_MISMATCH
    assert details == {}


def test_dependency_wrapper_never_catches_baseexception() -> None:
    source = _script_source()
    assert "except:" not in source
    parsed = ast.parse(source)
    for node in ast.walk(parsed):
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, "bare except is forbidden"
            names = (
                [node.type.id]
                if isinstance(node.type, ast.Name)
                else [e.id for e in getattr(node.type, "elts", []) if isinstance(e, ast.Name)]
            )
            assert "BaseException" not in names
            assert "KeyboardInterrupt" not in names
            assert "SystemExit" not in names


def test_the_candidate_dependency_is_not_a_project_runtime_dependency() -> None:
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "pyblst" not in pyproject
    assert "blst" not in pyproject
    requirements = _REPO_ROOT / "requirements.txt"
    if requirements.exists():
        assert "pyblst" not in requirements.read_text(encoding="utf-8")
    with pytest.raises(ImportError):
        importlib.import_module("pyblst")


def test_no_product_module_imports_the_qualification_script_or_the_candidate() -> None:
    source_root = _REPO_ROOT / "src" / "crypto_core"
    offenders = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "pyblst" in text or "qualify_drand_quicknet_pyblst" in text:
            offenders.append(path.name)
    assert offenders == []


def test_readiness_and_connector_projections_are_unchanged_by_qualification() -> None:
    from crypto_core.validation.machine_time_source_registry import (
        build_approved_machine_time_source_registry,
        machine_time_source_registry_to_dict,
    )
    from crypto_core.venue.public_feed_dialects import connector_ready_dialects

    payload = machine_time_source_registry_to_dict(build_approved_machine_time_source_registry())
    for flag in (
        "connector_invoked",
        "connector_promoted",
        "deribit_ready",
        "live_api_called",
        "live_ready",
        "machine_time_origin_proven",
        "network_fetch_performed",
        "operational_quorum_ready",
        "operationally_approved",
        "private_api_ready",
        "proof_verified",
        "readiness_promoted",
        "scheduler_enabled",
        "shadow_ready",
        "source_reachable_proven",
        "timestamp_origin_proven",
    ):
        assert payload[flag] is False, flag
    assert payload["paper_only"] is True
    assert payload["deterministic_offline_only"] is True

    for record in payload["sources"]:
        for flag in (
            "operational_use_approved",
            "proof_verified",
            "quorum_countable",
            "source_reachable_proven",
        ):
            assert record[flag] is False, (record["source_id"], flag)

    assert tuple(spec.dialect_id for spec in connector_ready_dialects()) == (
        "deribit:l2_orderbook:book_instrument_interval",
    )
