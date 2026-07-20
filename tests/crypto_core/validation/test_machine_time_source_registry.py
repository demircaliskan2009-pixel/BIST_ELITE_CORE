"""Tests for the MT-3 machine-time source registry (structural, digest-bound, citation-backed, fail-closed).

The registry compiles the controller-approved Deep Research packet ``mt3-dr-batch-b-2026-07-20.controller-v1``
into an immutable, self-digesting inventory of the seven candidate machine-time source classes. These tests
assert the adversarial contract: exact inventory, canonical ordering, deterministic digests, reseal/forgery
detection, and that every reachability/operational/quorum/proof/machine-time flag is structurally False.
"""

from __future__ import annotations

import ast
import copy
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.machine_time_source_registry as registry_module
from crypto_core.validation.machine_time_source_registry import (
    MachineTimeSourceRegistry,
    MachineTimeSourceRegistryError,
    MachineTimeSourceRegistryStatus,
    build_approved_machine_time_source_registry,
    build_machine_time_source_registry,
    machine_time_source_entry_digest,
    machine_time_source_registry_digest,
    machine_time_source_registry_to_dict,
)

_APPROVED_PACKET = registry_module._CONTROLLER_APPROVED_PACKET

_EXPECTED_SOURCE_IDS = (
    "drand-quicknet-mainnet",
    "nist-randomness-beacon-v2-beta",
    "curby-public-beacon",
    "digicert-rfc3161-tsa",
    "opentimestamps-bitcoin",
    "cloudflare-roughtime-beta",
    "deribit-public-get-time",
)

_EXPECTED_CITATION_IDS = (
    "BITCOIN-GETBLOCKCHAININFO",
    "BITCOIN-GETBLOCKHEADER",
    "CLOUDFLARE-ROUGHTIME",
    "CLOUDFLARE-ROUGHTIME-USAGE",
    "CURBY-API",
    "CURBY-CONCEPTS",
    "CURBY-HOME",
    "CURBY-NETWORK",
    "CURBY-USAGE",
    "DERIBIT-GET-TIME",
    "DIGICERT-TSA",
    "DIGICERT-TSA-TROUBLESHOOT",
    "DRAND-DEVELOPER",
    "DRAND-HTTP-API",
    "DRAND-QUICKNET-ANNOUNCEMENT",
    "DRAND-SPEC",
    "NIST-BEACON-20",
    "NIST-IR8213-DRAFT",
    "OPENTS-CLIENT",
    "OPENTS-HOME",
    "RFC3161",
    "RFC4648",
    "RFC5816",
    "RFC7468",
    "RFC9162",
    "ROUGHTIME-DRAFT-19",
    "SIGSTORE-BUNDLE",
    "SIGSTORE-REKOR-OVERVIEW",
    "SIGSTORE-THREAT-MODEL",
)

_EXPECTED_EXCLUSION_SUBJECTS = (
    "certificate-transparency-v2-generic-machine-time-use",
    "sigstore-rekor-generic-machine-time-use",
    "nist-beacon-v2-live_certificate_fingerprint",
    "curby_current_post_upgrade_operational_steady_state",
    "digicert_public_use_sla_and_rate_limits",
    "roughtime_exact_artifact_digest_binding_format",
    "rfc3161_nonce_is_protocol_mandatory",
    "opentimestamps_confirmation_or_finality_threshold",
    "roughtime_not_after_quorum_without_digest_adapter",
)

_PACKET_DIGEST = "d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a"
_RAW_DIGEST = "f8ec03f63d4b790213bc0eea5b5089159cbd3da73792e02ab8db8d7c5d34f9d7"

_SOURCE_SAFETY_FLAGS = (
    "operational_use_approved",
    "quorum_countable",
    "source_reachable_proven",
    "proof_verified",
)

_REGISTRY_FALSE_DECISIONS = (
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_quorum_ready",
    "all_operational_use_approved",
    "all_quorum_countable",
    "not_before_operational_quorum_ready",
    "not_after_operational_quorum_ready",
)

_ARTIFACT_TRUE_FLAGS = (
    "paper_only",
    "structural_metadata_only",
    "registry_ready_is_structural_only",
    "deterministic_offline_only",
    "network_fetch_in_builder_forbidden",
    "no_wall_clock_dependency",
    "citation_backed",
    "controller_packet_bound",
    "source_facts_immutable",
)

_ARTIFACT_FALSE_FLAGS = (
    "operationally_approved",
    "currently_reachable",
    "proof_acquired",
    "proof_verified",
    "quorum_approved",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_quorum_ready",
    "source_reachable_proven",
    "network_fetch_performed",
    "real_wall_clock_used",
    "machine_proven_day_decided",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "private_api_ready",
    "live_api_called",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "readiness_promoted",
    "connector_promoted",
    "mt4_adapter_bound",
    "mt2_policy_mutated",
    "edge_proven",
    "profitability_proven",
)


def _rc(code: str) -> str:
    return f"machine_time_source_registry:{code}"


def _packet() -> dict[str, object]:
    return copy.deepcopy(_APPROVED_PACKET)


def _mutate(mutation) -> MachineTimeSourceRegistry:
    packet = _packet()
    mutation(packet)
    return build_machine_time_source_registry(packet=packet)


# --------------------------------------------------------------------------------------------------
# Approved construction / inventory
# --------------------------------------------------------------------------------------------------


def test_approved_registry_is_ready() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.status is MachineTimeSourceRegistryStatus.REGISTRY_READY
    assert registry.ready is True
    assert registry.reason_codes == ()


def test_approved_equals_default_builder() -> None:
    assert build_approved_machine_time_source_registry() == build_machine_time_source_registry()


def test_exact_seven_source_inventory_in_canonical_order() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.source_count == 7
    assert registry.source_ids == _EXPECTED_SOURCE_IDS
    assert tuple(record.source_id for record in registry.sources) == _EXPECTED_SOURCE_IDS
    assert len(set(registry.source_ids)) == 7


def test_exact_twenty_nine_citation_inventory() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.citation_count == 29
    assert registry.citation_ids == _EXPECTED_CITATION_IDS
    assert list(registry.citation_ids) == sorted(registry.citation_ids)


def test_exact_nine_exclusion_inventory_in_packet_order() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.exclusion_count == 9
    assert registry.exclusion_subjects == _EXPECTED_EXCLUSION_SUBJECTS


def test_packet_lineage_is_pinned() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.controller_approved_packet_id == "mt3-dr-batch-b-2026-07-20.controller-v1"
    assert registry.controller_approved_packet_digest == _PACKET_DIGEST
    assert registry.raw_packet_id == "mt3-dr-batch-b-2026-07-20.v2"
    assert registry.raw_packet_digest == _RAW_DIGEST
    assert registry.controller_normalization_id == "mt3-controller-normalization-2026-07-20.v1"
    assert registry.packet_schema == "machine-time-source-research-packet.v1"


def test_embedded_packet_recomputes_to_pinned_digest() -> None:
    canonical = json.dumps(_APPROVED_PACKET, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    import hashlib

    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == _PACKET_DIGEST


@pytest.mark.parametrize(
    ("source_id", "role", "recommendation", "source_class"),
    [
        (
            "drand-quicknet-mainnet",
            "not_before",
            "INCLUDE_NOT_BEFORE_CANDIDATE",
            "distributed-threshold-randomness-beacon",
        ),
        (
            "nist-randomness-beacon-v2-beta",
            "not_before",
            "INCLUDE_NOT_BEFORE_CANDIDATE",
            "signed-hash-chained-public-randomness-beacon",
        ),
        ("curby-public-beacon", "not_before", "INCLUDE_NOT_BEFORE_CANDIDATE", "traceable-twine-randomness-beacon"),
        ("digicert-rfc3161-tsa", "not_after", "INCLUDE_NOT_AFTER_CANDIDATE", "rfc3161-timestamp-authority"),
        (
            "opentimestamps-bitcoin",
            "not_after",
            "INCLUDE_NOT_AFTER_CANDIDATE",
            "bitcoin-anchored-blockchain-timestamping",
        ),
        ("cloudflare-roughtime-beta", "not_after", "DEFER_TO_MT4_ADAPTER", "authenticated-rough-time"),
        ("deribit-public-get-time", "advisory_only", "INCLUDE_ADVISORY_ONLY", "exchange-server-time"),
    ],
)
def test_source_roles_and_classes(source_id: str, role: str, recommendation: str, source_class: str) -> None:
    registry = build_approved_machine_time_source_registry()
    record = next(r for r in registry.sources if r.source_id == source_id)
    assert record.recommended_role == role
    assert record.recommendation == recommendation
    assert record.source_class == source_class


def test_every_source_safety_flag_is_false() -> None:
    registry = build_approved_machine_time_source_registry()
    for record in registry.sources:
        for flag in _SOURCE_SAFETY_FLAGS:
            assert getattr(record, flag) is False


def test_fact_items_are_immutable_pairs_with_scalar_values() -> None:
    registry = build_approved_machine_time_source_registry()
    drand = next(r for r in registry.sources if r.source_id == "drand-quicknet-mainnet")
    assert isinstance(drand.fact_items, tuple)
    fact_map = dict(drand.fact_items)
    # canonical numeric/bool facts survive verbatim (a True fact is DATA, not a safety flag).
    assert fact_map["period_seconds"] == 3
    assert fact_map["mainnet_documented"] is True
    assert fact_map["scheme"] == "bls-unchained-g1-rfc9380"
    # keys are sorted for determinism
    keys = [key for key, _ in drand.fact_items]
    assert keys == sorted(keys)


def test_deribit_is_advisory_only_and_never_a_proof() -> None:
    registry = build_approved_machine_time_source_registry()
    deribit = next(r for r in registry.sources if r.source_id == "deribit-public-get-time")
    assert deribit.recommended_role == "advisory_only"
    assert deribit.proof_verified is False
    assert deribit.source_reachable_proven is False
    assert registry.deribit_ready is False


# --------------------------------------------------------------------------------------------------
# Determinism / digest / reseal / immutability
# --------------------------------------------------------------------------------------------------


def test_registry_digest_is_deterministic() -> None:
    first = build_approved_machine_time_source_registry()
    second = build_approved_machine_time_source_registry()
    assert first.registry_digest == second.registry_digest
    assert first == second


def test_registry_self_digest_recomputes() -> None:
    registry = build_approved_machine_time_source_registry()
    assert machine_time_source_registry_digest(registry) == registry.registry_digest


def test_entry_digest_recomputes_and_is_populated() -> None:
    registry = build_approved_machine_time_source_registry()
    for record in registry.sources:
        assert len(record.entry_digest) == 64
        assert machine_time_source_entry_digest(record) == record.entry_digest


def test_registry_is_frozen() -> None:
    registry = build_approved_machine_time_source_registry()
    with pytest.raises(FrozenInstanceError):
        registry.ready = False  # type: ignore[misc]


def test_source_record_is_frozen() -> None:
    registry = build_approved_machine_time_source_registry()
    with pytest.raises(FrozenInstanceError):
        registry.sources[0].proof_verified = True  # type: ignore[misc]


def test_serializer_is_fields_complete() -> None:
    registry = build_approved_machine_time_source_registry()
    payload = machine_time_source_registry_to_dict(registry)
    assert set(payload) == {field.name for field in fields(registry)}
    assert payload["status"] == registry.status.value
    assert payload["source_ids"] == list(_EXPECTED_SOURCE_IDS)
    assert payload["citation_ids"] == list(_EXPECTED_CITATION_IDS)
    assert payload["registry_digest"] == registry.registry_digest
    assert len(payload["sources"]) == 7
    assert all(len(source["entry_digest"]) == 64 for source in payload["sources"])


def test_serializer_json_roundtrip_stable() -> None:
    registry = build_approved_machine_time_source_registry()
    payload = machine_time_source_registry_to_dict(registry)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert json.loads(encoded)["registry_digest"] == registry.registry_digest


def test_reseal_of_stale_valid_digest_is_ignored_by_recompute() -> None:
    registry = build_approved_machine_time_source_registry()
    stale = replace(registry, registry_digest="0" * 64)
    assert machine_time_source_registry_digest(stale) == registry.registry_digest


def test_serializer_rejects_stale_carried_digest() -> None:
    registry = build_approved_machine_time_source_registry()
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("malformed_artifact")):
        machine_time_source_registry_to_dict(replace(registry, registry_digest="0" * 64))


@pytest.mark.parametrize("flag", _ARTIFACT_FALSE_FLAGS)
def test_forged_false_flag_overclaim_cannot_be_resealed(flag: str) -> None:
    registry = build_approved_machine_time_source_registry()
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("malformed_artifact")):
        machine_time_source_registry_digest(replace(registry, **{flag: True}))


@pytest.mark.parametrize("flag", _ARTIFACT_TRUE_FLAGS)
def test_forged_true_marker_weakening_cannot_be_resealed(flag: str) -> None:
    registry = build_approved_machine_time_source_registry()
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("malformed_artifact")):
        machine_time_source_registry_digest(replace(registry, **{flag: False}))


def test_forged_lineage_digest_cannot_be_resealed() -> None:
    registry = build_approved_machine_time_source_registry()
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("malformed_artifact")):
        machine_time_source_registry_digest(replace(registry, controller_approved_packet_digest="a" * 64))


def test_nested_source_removal_after_sealing_is_detected() -> None:
    registry = build_approved_machine_time_source_registry()
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("malformed_artifact")):
        machine_time_source_registry_digest(replace(registry, sources=registry.sources[:-1]))


def test_builder_does_not_alias_caller_packet() -> None:
    packet = _packet()
    registry = build_machine_time_source_registry(packet=packet)
    packet["sources"][0]["source_id"] = "hacked"  # type: ignore[index]
    packet["citations"]["RFC3161"] = "hacked"  # type: ignore[index]
    packet["sources"][0]["fact_items"]["period_seconds"] = 999  # type: ignore[index]
    assert registry.source_ids == _EXPECTED_SOURCE_IDS
    assert registry.sources[0].source_id == "drand-quicknet-mainnet"
    assert isinstance(registry.sources, tuple)
    assert isinstance(registry.sources[0].citation_ids, tuple)
    assert isinstance(registry.sources[0].fact_items, tuple)


# --------------------------------------------------------------------------------------------------
# Fail-closed: authority / lineage
# --------------------------------------------------------------------------------------------------


def _reject(mutation, code: str) -> None:
    registry = _mutate(mutation)
    assert registry.status is MachineTimeSourceRegistryStatus.REGISTRY_REJECTED
    assert registry.ready is False
    assert _rc(code) in registry.reason_codes


def test_any_content_mutation_breaks_packet_digest() -> None:
    _reject(lambda p: p.__setitem__("researched_on", "1999-01-01"), "packet_digest_mismatch")


def test_packet_id_mutation_rejected() -> None:
    _reject(lambda p: p.__setitem__("packet_id", "mt3-dr-batch-b-2026-07-20.forged"), "packet_id_mismatch")


def test_raw_packet_id_mutation_rejected() -> None:
    _reject(lambda p: p["provenance"].__setitem__("raw_deep_research_packet_id", "forged"), "raw_packet_id_mismatch")


def test_raw_packet_digest_mutation_rejected() -> None:
    forged = "a" * 64
    _reject(
        lambda p: p["provenance"].__setitem__("raw_deep_research_packet_digest", forged),
        "raw_packet_digest_mismatch",
    )


def test_malformed_63_char_raw_digest_rejected() -> None:
    malformed = "f8ec03f63d4b790213bc0eea5b5089159cbd3da73792e02ab8db8d7c5d34f9d"  # 63 chars
    assert len(malformed) == 63
    _reject(
        lambda p: p["provenance"].__setitem__("raw_deep_research_packet_digest", malformed),
        "raw_packet_digest_malformed",
    )


def test_controller_normalization_id_mutation_rejected() -> None:
    _reject(
        lambda p: p["provenance"].__setitem__("controller_normalization_id", "forged"),
        "controller_normalization_id_mismatch",
    )


def test_packet_schema_mutation_rejected() -> None:
    _reject(lambda p: p.__setitem__("packet_schema", "forged.v1"), "packet_schema_mismatch")


# --------------------------------------------------------------------------------------------------
# Fail-closed: inventory / ordering
# --------------------------------------------------------------------------------------------------


def test_missing_source_rejected() -> None:
    _reject(lambda p: p["sources"].pop(), "source_count_mismatch")


def test_extra_source_rejected() -> None:
    def add_source(packet: dict[str, object]) -> None:
        clone = copy.deepcopy(packet["sources"][0])
        clone["source_id"] = "eighth-forbidden-source"
        packet["sources"].append(clone)

    _reject(add_source, "source_count_mismatch")


def test_duplicate_source_id_rejected() -> None:
    _reject(lambda p: p["sources"][1].__setitem__("source_id", "drand-quicknet-mainnet"), "duplicate_source_id")


def test_wrong_source_order_rejected() -> None:
    def swap(packet: dict[str, object]) -> None:
        sources = packet["sources"]
        sources[0], sources[1] = sources[1], sources[0]

    _reject(swap, "source_order_mismatch")


def test_wrong_source_identity_rejected() -> None:
    _reject(lambda p: p["sources"][0].__setitem__("source_id", "unknown-source"), "source_inventory_mismatch")


# --------------------------------------------------------------------------------------------------
# Fail-closed: source metadata / citations
# --------------------------------------------------------------------------------------------------


def test_unsupported_recommended_role_rejected() -> None:
    _reject(lambda p: p["sources"][0].__setitem__("recommended_role", "operational"), "recommended_role_unsupported")


def test_unsupported_recommendation_rejected() -> None:
    _reject(lambda p: p["sources"][0].__setitem__("recommendation", "APPROVE_NOW"), "recommendation_unsupported")


def test_source_class_mutation_breaks_digest() -> None:
    _reject(lambda p: p["sources"][0].__setitem__("source_class", "forged-class"), "packet_digest_mismatch")


def test_source_citation_mutation_to_unregistered_id_rejected() -> None:
    _reject(
        lambda p: p["sources"][0].__setitem__("citation_ids", ["UNREGISTERED-CITATION"]),
        "source_citation_unregistered",
    )


def test_citation_count_mutation_rejected() -> None:
    _reject(lambda p: p["citations"].pop("RFC9162"), "citation_count_mismatch")


def test_exclusion_count_mutation_rejected() -> None:
    _reject(lambda p: p["excluded_or_unproven"].pop(), "exclusion_count_mismatch")


# --------------------------------------------------------------------------------------------------
# Fail-closed: unsafe positive flags
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", _SOURCE_SAFETY_FLAGS)
def test_source_safety_flag_true_rejected(flag: str) -> None:
    _reject(lambda p, flag=flag: p["sources"][0].__setitem__(flag, True), f"source_flag_{flag}_not_false")


@pytest.mark.parametrize("decision", _REGISTRY_FALSE_DECISIONS)
def test_registry_decision_true_rejected(decision: str) -> None:
    _reject(
        lambda p, decision=decision: p["controller_decisions"].__setitem__(decision, True),
        f"decision_{decision}_not_false",
    )


def test_registry_structural_only_decision_must_be_true() -> None:
    _reject(
        lambda p: p["controller_decisions"].__setitem__("registry_ready_is_structural_only", False),
        "registry_structural_only_decision_missing",
    )


def test_machine_time_origin_proven_true_rejected() -> None:
    registry = _mutate(lambda p: p["controller_decisions"].__setitem__("machine_time_origin_proven", True))
    assert registry.status is MachineTimeSourceRegistryStatus.REGISTRY_REJECTED
    assert _rc("decision_machine_time_origin_proven_not_false") in registry.reason_codes
    assert registry.machine_time_origin_proven is False


# --------------------------------------------------------------------------------------------------
# Fail-closed: caller input types
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, [], "packet", 7, ("a",)])
def test_non_dict_packet_raises(value: object) -> None:
    if value is None:
        pytest.skip("None selects the embedded approved packet")
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("packet_not_mapping")):
        build_machine_time_source_registry(packet=value)  # type: ignore[arg-type]


def test_non_serializable_packet_raises() -> None:
    packet = _packet()
    packet["sources"][0]["fact_items"]["bad"] = object()  # type: ignore[index]
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("packet_not_serializable")):
        build_machine_time_source_registry(packet=packet)


def test_reason_codes_are_sorted_unique_and_prefixed() -> None:
    registry = _mutate(lambda p: (p["sources"].pop(), p["citations"].pop("RFC9162")))
    assert registry.status is MachineTimeSourceRegistryStatus.REGISTRY_REJECTED
    assert list(registry.reason_codes) == sorted(set(registry.reason_codes))
    assert all(code.startswith("machine_time_source_registry:") for code in registry.reason_codes)


# --------------------------------------------------------------------------------------------------
# Structural markers
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", _ARTIFACT_TRUE_FLAGS)
def test_structural_true_markers(flag: str) -> None:
    assert getattr(build_approved_machine_time_source_registry(), flag) is True


@pytest.mark.parametrize("flag", _ARTIFACT_FALSE_FLAGS)
def test_non_claim_false_flags(flag: str) -> None:
    assert getattr(build_approved_machine_time_source_registry(), flag) is False


# --------------------------------------------------------------------------------------------------
# No network / no side channels / import discipline
# --------------------------------------------------------------------------------------------------


def test_ast_forbidden_imports_and_calls() -> None:
    source = Path(registry_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "os",
        "io",
        "pathlib",
        "time",
        "datetime",
        "random",
        "secrets",
        "socket",
        "ssl",
        "requests",
        "urllib",
        "http",
        "threading",
        "asyncio",
        "subprocess",
        "sqlite3",
    )
    forbidden_call_names = {
        "open",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
        "system",
        "getenv",
        "eval",
        "exec",
        "urlopen",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == module or alias.name.startswith(f"{module}.") for module in forbidden_modules
                ), alias.name
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                node.module == module or node.module.startswith(f"{module}.") for module in forbidden_modules
            ), node.module
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names, function.id
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names, function.attr


def test_module_imports_no_crypto_core_dependencies() -> None:
    # MT-3 records metadata only: it must not import MT-2, venue, readiness, execution, runtime, or any
    # crypto_core surface, so it can never mutate MT-2 or move a readiness/connector state.
    source = Path(registry_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not node.module.startswith("crypto_core"), node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("crypto_core"), alias.name


def test_no_positive_capability_helpers_exist() -> None:
    forbidden = {"is_ready", "is_operational", "proves_machine_time", "approved_sources", "is_reachable"}
    for name in forbidden:
        assert not hasattr(registry_module, name), name


def test_no_equivalent_builder_exists() -> None:
    validation_dir = Path(registry_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "def build_machine_time_source_registry(" in path.read_text(encoding="utf-8")
    )
    assert builders == ["machine_time_source_registry.py"]


def test_direct_module_path_import_works() -> None:
    module = __import__(
        "crypto_core.validation.machine_time_source_registry", fromlist=["build_machine_time_source_registry"]
    )
    assert module.build_approved_machine_time_source_registry().ready is True


# --------------------------------------------------------------------------------------------------
# MT-2 boundary: MT-3 must not touch MT-2 and must not prove machine-time origin
# --------------------------------------------------------------------------------------------------


def test_mt2_policy_remains_blocked_and_unproven() -> None:
    from crypto_core.validation.machine_time_policy import build_machine_time_policy

    policy = build_machine_time_policy(policy_id="mt2-policy-1", correlation_id="corr-1")
    assert policy.machine_time_origin_proven is False
    assert policy.concrete_source_registry_bound is False
    # Building the MT-3 registry does not mutate or bind MT-2.
    build_approved_machine_time_source_registry()
    policy_again = build_machine_time_policy(policy_id="mt2-policy-1", correlation_id="corr-1")
    assert policy_again.machine_time_origin_proven is False
    assert policy_again.concrete_source_registry_bound is False


def test_registry_never_proves_machine_time_or_readiness() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.machine_time_origin_proven is False
    assert registry.timestamp_origin_proven is False
    assert registry.operational_quorum_ready is False
    assert registry.operational_readiness is False
    assert registry.mt4_adapter_bound is False
    assert registry.prdv4_stage4_complete is False
