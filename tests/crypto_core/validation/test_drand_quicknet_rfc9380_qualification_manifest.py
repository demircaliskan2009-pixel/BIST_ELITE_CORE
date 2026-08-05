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
import importlib.util
import json
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_MANIFEST_PATH = _REPO_ROOT / "tests" / "crypto_core" / "fixtures" / "drand_quicknet_rfc9380_qualification_v1.json"
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "crypto_core" / "qualify_drand_quicknet_pyblst.py"

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
_EXPECTED_BLOCKED_IDS = (
    "blocked_subgroup_invalid_g1_point",
    "blocked_non_canonical_encoding_point",
)
_ADMISSIBLE_PROVENANCE = frozenset(
    {
        "OFFICIAL_DRAND_HTTP_API_V2",
        "OFFICIAL_DRAND_V2_1_6_KEYGROUP_BASE_POINT",
        "NORMATIVE_CANONICAL_ENCODING",
        "DETERMINISTIC_MUTATION_OF_ADMITTED_POSITIVE",
        "DETERMINISTIC_REPEAT_OF_ADMITTED_POSITIVE",
    }
)
_ADMISSION_FLAGS = (
    "crypto_implementation_authorized",
    "dependency_admitted",
    "fixture_corpus_admitted",
    "machine_time_origin_proven",
    "provider_operational_approval",
    "proof_verified",
    "quorum_countable",
    "readiness_promoted",
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
    assert admission["status"] == "QUALIFIED_CANDIDATE_NOT_ADMITTED"
    assert set(admission) == set(_ADMISSION_FLAGS) | {"status"}
    for flag in _ADMISSION_FLAGS:
        assert admission[flag] is False, flag


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
        assert fixture["source_type"] in {"official_http_api", "official_reference", "normative", "derived"}


def test_blocked_fixtures_are_declared_blocked_and_carry_no_invented_bytes() -> None:
    for fixture in _manifest()["unresolved_or_blocked_fixtures"]:
        assert fixture["status"] == "FIXTURE_ADMISSION_BLOCKED"
        assert fixture["blocked_reason"] == "fixture_provenance_invalid"
        assert "provenance" not in fixture
        assert set(fixture) == {"blocked_reason", "fixture_id", "note", "status"}
        for banned in ("signature_hex", "public_key_hex", "bytes_hex", "expected_result"):
            assert banned not in fixture, (fixture["fixture_id"], banned)


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
        assert fixture["expected_result"] == "qualified"


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


def test_candidate_dependency_pins_and_the_version_contradiction_are_recorded() -> None:
    dependency = _manifest()["candidate_dependency"]
    assert dependency["profile_id"] == "D-DEP-DRAND-PYBLST-0.3.15-CANDIDATE.v1"
    assert dependency["package"] == "pyblst"
    assert dependency["distribution_version"] == "0.3.15"
    assert dependency["cargo_package_version"] == "0.3.14"
    assert dependency["cargo_package_version_contradicts_distribution_version"] is True
    assert dependency["upstream_blst_version"] == "0.3.16"
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
        "qualified",
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


def test_canonical_infinity_is_rejected_before_any_pairing_work() -> None:
    module = _load_script("infinity")
    reason_type = module.QuicknetQualificationReason

    g1_infinity = bytes([0xC0]) + bytes(47)
    g2_infinity = bytes([0xC0]) + bytes(95)
    assert module._is_canonical_infinity(g1_infinity) is True
    assert module._is_canonical_infinity(g2_infinity) is True
    assert module._is_canonical_infinity(bytes.fromhex(_OFFICIAL_SIGNATURE_HEX)) is False
    assert module._is_canonical_infinity(b"") is False
    # the infinity flag is bit 0x40; it is treated as infinity with or without the 0x80 compression
    # bit, so an uncompressed-flagged infinity encoding is rejected on the same path
    assert module._is_canonical_infinity(bytes([0x40]) + bytes(47)) is True
    # any non-zero residual bit in the flag byte or the body is NOT canonical infinity
    assert module._is_canonical_infinity(bytes([0xC1]) + bytes(47)) is False
    assert module._is_canonical_infinity(bytes([0xC0]) + bytes(46) + bytes([0x01])) is False
    assert module._is_canonical_infinity(bytes(48)) is False

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
