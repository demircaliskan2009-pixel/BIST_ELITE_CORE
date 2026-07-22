"""Tests for the MT-3 machine-time source registry (structural, digest-bound, citation-backed, fail-closed).

The registry compiles the controller-approved packet
``mt3-cloudflare-provenance-correction-2026-07-23.controller-v1`` into an immutable, self-digesting inventory
of the seven candidate machine-time source classes. These tests assert the adversarial contract: exact
inventory, canonical ordering, deterministic digests, reseal/forgery detection, and that every
reachability/operational/quorum/proof/machine-time flag is structurally False.

They also assert the Cloudflare protocol-provenance correction: the deployed Cloudflare Roughtime protocol
version is recorded as UNPROVEN (never draft-19, draft-11 or draft-08), the correction authority's digest is
recomputed over EMBEDDED canonical approval data, the superseded predecessor packet is retained as history
but rejected as current authority, MT-4 verifier-profile selection stays blocked, and the six unrelated
source-entry digests are byte-identical to their pre-correction values.
"""

from __future__ import annotations

import ast
import copy
import hashlib
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

_PREDECESSOR_EXCLUSION_SUBJECTS = (
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

# The Cloudflare deployed-version unproven subject is appended last, after the nine preserved predecessor
# subjects in their original order.
_NEW_UNPROVEN_SUBJECT = "cloudflare_deployed_roughtime_protocol_version"
_EXPECTED_EXCLUSION_SUBJECTS = (*_PREDECESSOR_EXCLUSION_SUBJECTS, _NEW_UNPROVEN_SUBJECT)

# CURRENT authority (Cloudflare protocol-provenance correction).
_PACKET_ID = "mt3-cloudflare-provenance-correction-2026-07-23.controller-v1"
_PACKET_DIGEST = "a575eaffd2098432f08c77ba9a3c84a8177992b24b91ff350e3348ecc93b9d82"
_AUTHORITY_ID = "mt3-cloudflare-provenance-correction-2026-07-23.authority-v1"
_RAW_DIGEST = "4a09d5e3bb48ae2039c2c164abe1f88ee9b6ebe9edcf1e29e17147ac92dd5bd7"
_NORMALIZATION_ID = "mt3-controller-normalization-2026-07-23.cloudflare-provenance-correction-v1"
_HUMAN_APPROVAL_ID = "MT3-CLOUDFLARE-PROVENANCE-CORRECTION-HUMAN-APPROVAL-V1"

# SUPERSEDED predecessor authority — history only, never current.
_SUPERSEDED_PACKET_ID = "mt3-dr-batch-b-2026-07-20.controller-v1"
_SUPERSEDED_PACKET_DIGEST = "d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a"
_SUPERSEDED_RAW_PACKET_ID = "mt3-dr-batch-b-2026-07-20.v2"
_SUPERSEDED_RAW_PACKET_DIGEST = "f8ec03f63d4b790213bc0eea5b5089159cbd3da73792e02ab8db8d7c5d34f9d7"
_SUPERSEDED_PROTOCOL_VERSION_CLAIM = "draft-ietf-ntp-roughtime-19"

# Exact pre-correction entry digests of the six sources this correction must NOT touch. Captured from the
# merged predecessor registry before mutation; any drift here means the correction leaked outside Cloudflare.
_UNCHANGED_ENTRY_DIGESTS = {
    "drand-quicknet-mainnet": "c3dae5eab6e5fb046d30e66f841804c95e2ecffb65efd8e77553ef096be6eb3c",
    "nist-randomness-beacon-v2-beta": "416efc2bbe030f4a030d0738c0591178ec9af67e5ab5cddf48df9b6bda5664a4",
    "curby-public-beacon": "74679d65c31e9d2fb341e58821ea9c21ff4627872be51684d3a5c2a249539acf",
    "digicert-rfc3161-tsa": "c5783a22b5727f4e17ea77678402ea80cc3a25a38463cb0810383ddc7a3c11f2",
    "opentimestamps-bitcoin": "861d0f0a8f14a5876e2ab30294776f5e56435da11251101b807697d70cbbe572",
    "deribit-public-get-time": "d3b84c294e721607e543863a4d7b7e4cc2f6a2f22001b6f9dabbb59c169b38b8",
}
_PRE_CORRECTION_CLOUDFLARE_ENTRY_DIGEST = "e822748dbee977608e14512695f219adc6b2bf27b137e20e5c5ac6c7a92b0b54"
_PRE_CORRECTION_REGISTRY_DIGEST = "9f41f4ad51603f545a24b06d009fc042703b02531379a5fc58b43de99b07a72a"

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
    "mt4_verifier_profile_selected",
    "roughtime_deployed_protocol_version_proven",
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


def test_exact_ten_exclusion_inventory_in_packet_order() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.exclusion_count == 10
    assert registry.exclusion_subjects == _EXPECTED_EXCLUSION_SUBJECTS
    # The nine predecessor subjects survive in their original order; the new subject is appended once.
    assert registry.exclusion_subjects[:9] == _PREDECESSOR_EXCLUSION_SUBJECTS
    assert registry.exclusion_subjects.count(_NEW_UNPROVEN_SUBJECT) == 1


def test_packet_lineage_is_pinned() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.controller_approved_packet_id == _PACKET_ID
    assert registry.controller_approved_packet_digest == _PACKET_DIGEST
    assert registry.raw_packet_id == _AUTHORITY_ID
    assert registry.raw_packet_digest == _RAW_DIGEST
    assert registry.controller_normalization_id == _NORMALIZATION_ID
    assert registry.packet_schema == "machine-time-source-research-packet.v2"


def test_version_discipline_schema_unchanged_registry_bumped() -> None:
    # The public artifact SHAPE is unchanged, so schema_version stays .v1; the admitted registry CONTENT
    # identity changed, so registry_version is bumped. They are deliberately assessed separately.
    registry = build_approved_machine_time_source_registry()
    assert registry.schema_version == "machine-time-source-registry.v1"
    assert registry.registry_version == "machine-time-source-registry.v2"
    assert registry.schema_version != registry.registry_version


def test_embedded_packet_recomputes_to_pinned_digest() -> None:
    canonical = json.dumps(_APPROVED_PACKET, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == _PACKET_DIGEST
    assert _PACKET_DIGEST != _SUPERSEDED_PACKET_DIGEST


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
        ("cloudflare-roughtime-beta", "not_after", "DEFER_PENDING_PROTOCOL_PROVENANCE", "authenticated-rough-time"),
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
    _reject(lambda p: p.__setitem__("packet_id", "mt3-cloudflare-provenance-correction.forged"), "packet_id_mismatch")


def test_superseded_packet_id_is_not_current_authority() -> None:
    # Reinstating the superseded controller packet id fails current admission.
    _reject(lambda p: p.__setitem__("packet_id", _SUPERSEDED_PACKET_ID), "packet_id_mismatch")


def test_raw_packet_id_mutation_rejected() -> None:
    _reject(lambda p: p["provenance"].__setitem__("correction_authority_id", "forged"), "raw_packet_id_mismatch")


def test_raw_packet_digest_mutation_rejected() -> None:
    forged = "a" * 64
    _reject(
        lambda p: p["provenance"].__setitem__("correction_authority_digest", forged),
        "raw_packet_digest_mismatch",
    )


def test_malformed_63_char_raw_digest_rejected() -> None:
    malformed = _RAW_DIGEST[:63]
    assert len(malformed) == 63
    _reject(
        lambda p: p["provenance"].__setitem__("correction_authority_digest", malformed),
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


def test_new_unproven_subject_removal_rejected() -> None:
    # Dropping the Cloudflare deployed-version unproven subject must never silently succeed.
    def drop(packet: dict[str, object]) -> None:
        packet["excluded_or_unproven"] = [
            entry for entry in packet["excluded_or_unproven"] if entry["subject"] != _NEW_UNPROVEN_SUBJECT
        ]

    _reject(drop, "exclusion_count_mismatch")


def test_new_unproven_subject_mutation_rejected() -> None:
    def rename(packet: dict[str, object]) -> None:
        for entry in packet["excluded_or_unproven"]:
            if entry["subject"] == _NEW_UNPROVEN_SUBJECT:
                entry["subject"] = "cloudflare_deployed_roughtime_protocol_version_resolved"

    _reject(rename, "packet_digest_mismatch")


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


def test_non_plain_nested_value_raises() -> None:
    packet = _packet()
    packet["sources"][0]["fact_items"]["bad"] = object()  # type: ignore[index]
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("packet_non_plain_value")):
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


# --------------------------------------------------------------------------------------------------
# P1 repair: nested entry-digest verification + exact packet-to-artifact semantic binding
#
# Each forgery below carries a SELF-CONSISTENT outer digest (recomputed with the module's own canonical
# payload builder), so a passing test proves the validator rejects on merit — never merely because the outer
# digest is stale.
# --------------------------------------------------------------------------------------------------


def _self_consistent_outer(registry: MachineTimeSourceRegistry) -> MachineTimeSourceRegistry:
    """Return the registry carrying an outer digest that exactly matches its (forged) content."""

    payload = registry_module._registry_payload_from(registry)
    return replace(registry, registry_digest=registry_module._canonical_digest(payload))


def _reseal_entry(record):
    return replace(record, entry_digest=machine_time_source_entry_digest(record))


def test_wrong_nested_entry_digest_cannot_be_outer_resealed() -> None:
    registry = build_approved_machine_time_source_registry()
    other_hex = "b" * 64
    assert registry.sources[0].entry_digest != other_hex
    forged = replace(registry, sources=(replace(registry.sources[0], entry_digest=other_hex), *registry.sources[1:]))
    forged = _self_consistent_outer(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(forged)


@pytest.mark.parametrize(
    "mutation",
    [
        {"source_class": "forged-class"},
        {"provider_id": "forged-provider"},
        {"verification_profile_id": "forged-profile.v1"},
        {"protocol_version": "forged-protocol"},
        {"maturity": "forged-maturity"},
        {"official_endpoints": ("https://forged.example/api",)},
        {"fact_items": (("forged_fact", True),)},
    ],
)
def test_self_consistent_source_metadata_forgery_rejected(mutation: dict) -> None:
    registry = build_approved_machine_time_source_registry()
    forged_record = _reseal_entry(replace(registry.sources[0], **mutation))
    forged = _self_consistent_outer(replace(registry, sources=(forged_record, *registry.sources[1:])))
    # the nested entry digest is now self-consistent, so this rejection is exact-semantic binding (Fix B).
    assert machine_time_source_entry_digest(forged.sources[0]) == forged.sources[0].entry_digest
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(forged)


def test_self_consistent_source_citation_inventory_forgery_rejected() -> None:
    registry = build_approved_machine_time_source_registry()
    victim = registry.sources[0]
    replacement = "RFC9162"  # registered in the 29-id inventory, but not this source's real citation
    assert replacement in registry.citation_ids and replacement not in victim.citation_ids
    forged_record = _reseal_entry(replace(victim, citation_ids=(replacement,)))
    forged = _self_consistent_outer(replace(registry, sources=(forged_record, *registry.sources[1:])))
    assert machine_time_source_entry_digest(forged.sources[0]) == forged.sources[0].entry_digest
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(forged)


def test_same_count_registry_citation_inventory_forgery_rejected() -> None:
    registry = build_approved_machine_time_source_registry()
    forged_citations = ("AAA-UNUSED",) + registry.citation_ids[1:]  # canonical, sorted, same count
    assert len(forged_citations) == registry.citation_count
    assert list(forged_citations) == sorted(forged_citations)
    forged = _self_consistent_outer(replace(registry, citation_ids=forged_citations))
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(forged)


def test_same_count_exclusion_inventory_forgery_rejected() -> None:
    registry = build_approved_machine_time_source_registry()
    forged_subjects = ("forged-but-canonical-subject",) + registry.exclusion_subjects[1:]
    assert len(forged_subjects) == registry.exclusion_count
    forged = _self_consistent_outer(replace(registry, exclusion_subjects=forged_subjects))
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(forged)


def test_approved_registry_still_recomputes_and_serializes() -> None:
    registry = build_approved_machine_time_source_registry()
    assert registry.status is MachineTimeSourceRegistryStatus.REGISTRY_READY
    for record in registry.sources:
        assert machine_time_source_entry_digest(record) == record.entry_digest
    assert machine_time_source_registry_digest(registry) == registry.registry_digest
    payload = machine_time_source_registry_to_dict(registry)
    assert payload["registry_digest"] == registry.registry_digest
    assert build_approved_machine_time_source_registry().registry_digest == registry.registry_digest


# --------------------------------------------------------------------------------------------------
# P1 repair: content-addressed input binding (P1-A) + recursive exact-plain-data boundary (P1-B)
#
# The relabel/swap forgeries below compute a SELF-CONSISTENT outer digest with an INDEPENDENT, test-only
# canonicalizer (not the production private digest helper), so a passing test proves the semantic validator
# rejects on merit — never merely because the production helper was reused.
# --------------------------------------------------------------------------------------------------

_APPROVED_PACKET_DIGEST = _PACKET_DIGEST


def _independent_source_payload(record) -> dict:
    return {
        "source_id": record.source_id,
        "provider_id": record.provider_id,
        "source_class": record.source_class,
        "protocol_version": record.protocol_version,
        "maturity": record.maturity,
        "recommended_role": record.recommended_role,
        "recommendation": record.recommendation,
        "verification_profile_id": record.verification_profile_id,
        "official_endpoints": list(record.official_endpoints),
        "citation_ids": list(record.citation_ids),
        "fact_items": [[key, value] for key, value in record.fact_items],
        "operational_use_approved": record.operational_use_approved,
        "quorum_countable": record.quorum_countable,
        "source_reachable_proven": record.source_reachable_proven,
        "proof_verified": record.proof_verified,
        "entry_digest": record.entry_digest,
    }


def _independent_outer_digest(registry: MachineTimeSourceRegistry) -> str:
    """Recompute the outer registry digest with a fully independent test-only canonicalizer."""

    payload: dict = {}
    for field in fields(registry):
        if field.name == "registry_digest":
            continue
        value = getattr(registry, field.name)
        if field.name == "status":
            payload[field.name] = registry.status.value
        elif field.name == "sources":
            payload[field.name] = [_independent_source_payload(record) for record in registry.sources]
        elif isinstance(value, tuple):
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _independent_self_consistent(registry: MachineTimeSourceRegistry) -> MachineTimeSourceRegistry:
    return replace(registry, registry_digest=_independent_outer_digest(registry))


def test_independent_canonicalizer_matches_production() -> None:
    # If this drifts, the forgery tests below would be meaningless — assert the independent helper agrees with
    # the production digest on a legitimate artifact.
    registry = build_approved_machine_time_source_registry()
    assert _independent_outer_digest(registry) == registry.registry_digest


# TEST A — a REJECTED artifact whose projected content matches approved cannot be relabeled READY.
def test_rejected_content_cannot_be_relabeled_ready() -> None:
    packet = _packet()
    packet["zzz_non_projected_extra"] = "not-part-of-any-projection"
    rejected = build_machine_time_source_registry(packet=packet)
    assert rejected.status is MachineTimeSourceRegistryStatus.REGISTRY_REJECTED
    approved = build_approved_machine_time_source_registry()
    # The projected content is byte-identical to approved; only the (bound) canonical input differs.
    assert rejected.sources == approved.sources
    assert rejected.citation_ids == approved.citation_ids
    assert rejected.exclusion_subjects == approved.exclusion_subjects
    assert rejected.canonical_input_packet_json != approved.canonical_input_packet_json
    relabeled = replace(rejected, status=MachineTimeSourceRegistryStatus.REGISTRY_READY, ready=True, reason_codes=())
    relabeled = _independent_self_consistent(relabeled)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(relabeled)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(relabeled)


# TEST B — the carried canonical input is load-bearing: swapping it (even to another canonical packet) while
# keeping the projected metadata is rejected.
def test_canonical_input_is_load_bearing() -> None:
    approved = build_approved_machine_time_source_registry()
    packet = _packet()
    packet["zzz_non_projected_extra"] = True
    alt = build_machine_time_source_registry(packet=packet)  # different canonical input, same projection
    forged = replace(
        approved,
        canonical_input_packet_json=alt.canonical_input_packet_json,
        canonical_input_packet_digest=alt.canonical_input_packet_digest,
    )
    forged = _independent_self_consistent(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(forged)
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(forged)


# TEST C — the approved artifact's carried canonical input round-trips to the pinned approved packet.
def test_canonical_input_round_trips_to_approved() -> None:
    registry = build_approved_machine_time_source_registry()
    parsed = json.loads(registry.canonical_input_packet_json)
    recanonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert recanonical == registry.canonical_input_packet_json
    assert hashlib.sha256(recanonical.encode("utf-8")).hexdigest() == registry.canonical_input_packet_digest
    assert registry.canonical_input_packet_digest == _APPROVED_PACKET_DIGEST
    # Deterministic reconstruction from the carried input reproduces the identical artifact.
    reconstructed = build_machine_time_source_registry(packet=parsed)
    assert reconstructed.registry_digest == registry.registry_digest
    assert machine_time_source_registry_digest(registry) == registry.registry_digest


# TEST D — nested custom container/scalar subtypes are rejected without invoking any subtype callback.
def _callback_counter() -> dict:
    return {"n": 0}


def test_custom_subtype_value_callbacks_not_invoked() -> None:
    counter = _callback_counter()

    class _DictSub(dict):
        def __iter__(self):
            counter["n"] += 1
            return dict.__iter__(self)

        def items(self):
            counter["n"] += 1
            return dict.items(self)

    class _ListSub(list):
        def __iter__(self):
            counter["n"] += 1
            return list.__iter__(self)

    class _StrSub(str):
        def __lt__(self, other):
            counter["n"] += 1
            return str.__lt__(self, other)

        def __gt__(self, other):
            counter["n"] += 1
            return str.__gt__(self, other)

        def __le__(self, other):
            counter["n"] += 1
            return str.__le__(self, other)

        def __ge__(self, other):
            counter["n"] += 1
            return str.__ge__(self, other)

    class _IntSub(int):
        def __eq__(self, other):
            counter["n"] += 1
            return int.__eq__(self, other)

        __hash__ = int.__hash__

    for label, value in (
        ("dict", _DictSub({"a": 1})),
        ("list", _ListSub([1, 2])),
        ("str", _StrSub("x")),
        ("int", _IntSub(9)),
    ):
        packet = _packet()
        packet["zzz_subtype"] = value  # nested inside the exact outer dict, constructed first
        counter["n"] = 0  # reset AFTER construction, before the builder call
        with pytest.raises(MachineTimeSourceRegistryError, match=_rc("packet_non_plain_value")):
            build_machine_time_source_registry(packet=packet)
        assert counter["n"] == 0, label


# TEST E — a string-subtype dict key is rejected without invoking its comparison/ordering/string/hash callbacks.
def test_exact_dict_key_subtype_rejected_without_callbacks() -> None:
    counter = _callback_counter()

    class _KeySub(str):
        def __lt__(self, other):
            counter["n"] += 1
            return str.__lt__(self, other)

        def __gt__(self, other):
            counter["n"] += 1
            return str.__gt__(self, other)

        def __le__(self, other):
            counter["n"] += 1
            return str.__le__(self, other)

        def __ge__(self, other):
            counter["n"] += 1
            return str.__ge__(self, other)

        def __eq__(self, other):
            counter["n"] += 1
            return str.__eq__(self, other)

        def __hash__(self):
            counter["n"] += 1
            return str.__hash__(self)

    packet = _packet()
    nested = dict(packet["provenance"])
    nested[_KeySub("forged_key")] = "v"  # construction hashes the key once — that is before the reset
    packet["provenance"] = nested
    counter["n"] = 0  # reset AFTER construction, before the builder call
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("packet_non_string_key")):
        build_machine_time_source_registry(packet=packet)
    assert counter["n"] == 0


# TEST F — a container cycle and an over-depth structure fail closed (never a raw RecursionError).
def test_packet_cycle_fails_closed() -> None:
    packet = _packet()
    cyclic: dict = {}
    cyclic["self"] = cyclic
    packet["zzz_cyclic"] = cyclic
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("packet_cycle_detected")):
        build_machine_time_source_registry(packet=packet)


def test_packet_over_depth_fails_closed() -> None:
    packet = _packet()
    deep: dict = {}
    cursor = deep
    for _ in range(200):
        child: dict = {}
        cursor["n"] = child
        cursor = child
    packet["zzz_deep"] = deep
    with pytest.raises(MachineTimeSourceRegistryError, match=_rc("packet_max_depth_exceeded")):
        build_machine_time_source_registry(packet=packet)


def test_canonical_input_binding_is_digest_participating() -> None:
    # The two content-binding fields participate in equality and the outer digest.
    approved = build_approved_machine_time_source_registry()
    assert "canonical_input_packet_json" in {field.name for field in fields(approved)}
    tampered = replace(approved, canonical_input_packet_digest="0" * 64)
    assert _independent_outer_digest(tampered) != approved.registry_digest


# --------------------------------------------------------------------------------------------------
# Cloudflare protocol-provenance correction: correction authority + predecessor lineage
# --------------------------------------------------------------------------------------------------


def _packet_of(registry: MachineTimeSourceRegistry) -> dict:
    """Re-parse the artifact's own carried canonical input — never the module's mutable packet object."""

    return json.loads(registry.canonical_input_packet_json)


def _cloudflare(registry: MachineTimeSourceRegistry):
    return next(record for record in registry.sources if record.source_id == "cloudflare-roughtime-beta")


def test_correction_authority_identity_is_exact() -> None:
    registry = build_approved_machine_time_source_registry()
    authority = _packet_of(registry)["correction_authority"]
    assert registry.raw_packet_id == _AUTHORITY_ID
    assert authority["authority_id"] == _AUTHORITY_ID
    assert authority["approval_id"] == _HUMAN_APPROVAL_ID
    assert authority["approval_result"] == "APPROVED_FOR_DEDICATED_MT3_CLOUDFLARE_PROVENANCE_CORRECTION_PREFLIGHT"
    assert authority["deployed_version_decision"] == "DEPLOYED_VERSION_UNPROVEN"
    assert authority["corrected_source_id"] == "cloudflare-roughtime-beta"
    assert authority["mt4_verifier_profile_selected"] is False


def test_correction_authority_digest_recomputes_independently() -> None:
    # Independent recomputation: the authority digest is a digest over EMBEDDED canonical approval data, not
    # an unbacked claim about approval prose. This helper never calls the production digest helper.
    registry = build_approved_machine_time_source_registry()
    packet = _packet_of(registry)
    encoded = json.dumps(
        packet["correction_authority"], sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    recomputed = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert recomputed == _RAW_DIGEST
    assert recomputed == registry.raw_packet_digest
    assert recomputed == packet["provenance"]["correction_authority_digest"]


def test_correction_authority_approved_evidence_is_exact() -> None:
    registry = build_approved_machine_time_source_registry()
    evidence = _packet_of(registry)["correction_authority"]["approved_evidence"]
    assert evidence["cloudflare_official_source_revision"] == "75645289794cfbd71a08f0e7ecf9bc4f3f87d133"
    assert evidence["cloudflare_official_ecosystem_description"] == "google-roughtime-and-ietf-draft08"
    assert evidence["deployed_endpoint"] == "udp://roughtime.cloudflare.com:2003"
    assert evidence["published_root_key_base64"] == "0GD7c3yP8xEc4Zl2zeuN2SlLvDVVocjsPSL8/Rl/7zg="
    # No deployed-version contract is published, and a timeout observation proves no deployed version.
    assert evidence["deployed_protocol_version_contract_published"] is False
    assert evidence["timeout_observation_proves_deployed_protocol_version"] is False
    # The draft support recorded here is the official SOURCE LIBRARY's documented support, explicitly not a
    # claim about the deployed endpoint.
    assert evidence["official_source_library_documented_draft_support"] == [
        "draft-ietf-ntp-roughtime-08",
        "draft-ietf-ntp-roughtime-11",
    ]


def test_predecessor_lineage_is_preserved_as_history() -> None:
    registry = build_approved_machine_time_source_registry()
    provenance = _packet_of(registry)["provenance"]
    assert provenance["predecessor_controller_approved_packet_id"] == _SUPERSEDED_PACKET_ID
    assert provenance["predecessor_controller_approved_packet_digest"] == _SUPERSEDED_PACKET_DIGEST
    assert provenance["predecessor_raw_deep_research_packet_id"] == _SUPERSEDED_RAW_PACKET_ID
    assert provenance["predecessor_raw_deep_research_packet_digest"] == _SUPERSEDED_RAW_PACKET_DIGEST
    assert provenance["predecessor_status"] == "SUPERSEDED_NOT_CURRENT_AUTHORITY"
    # History is never current authority.
    assert registry.controller_approved_packet_id != _SUPERSEDED_PACKET_ID
    assert registry.controller_approved_packet_digest != _SUPERSEDED_PACKET_DIGEST
    assert registry.raw_packet_digest != _SUPERSEDED_RAW_PACKET_DIGEST


@pytest.mark.parametrize(
    ("key", "code"),
    [
        ("approval_id", "correction_authority_approval_id_mismatch"),
        ("approval_result", "correction_authority_approval_result_mismatch"),
        ("authority_id", "correction_authority_authority_id_mismatch"),
        ("deployed_version_decision", "correction_authority_deployed_version_decision_mismatch"),
        (
            "superseded_controller_approved_packet_id",
            "correction_authority_superseded_controller_approved_packet_id_mismatch",
        ),
        (
            "superseded_controller_approved_packet_digest",
            "correction_authority_superseded_controller_approved_packet_digest_mismatch",
        ),
        ("superseded_status", "correction_authority_superseded_status_mismatch"),
    ],
)
def test_correction_authority_field_substitution_rejected(key: str, code: str) -> None:
    registry = _mutate(lambda p, key=key: p["correction_authority"].__setitem__(key, "forged-authority-value"))
    assert registry.status is MachineTimeSourceRegistryStatus.REGISTRY_REJECTED
    assert _rc(code) in registry.reason_codes
    # Mutating the block also breaks its recomputed digest — the two guards are independent.
    assert _rc("correction_authority_digest_mismatch") in registry.reason_codes


def test_correction_authority_mt4_selection_forgery_rejected() -> None:
    _reject(
        lambda p: p["correction_authority"].__setitem__("mt4_verifier_profile_selected", True),
        "correction_authority_mt4_verifier_profile_selected_not_false",
    )


def test_correction_authority_removal_rejected() -> None:
    _reject(lambda p: p.pop("correction_authority"), "correction_authority_malformed")


@pytest.mark.parametrize(
    "key",
    [
        "predecessor_controller_approved_packet_id",
        "predecessor_controller_approved_packet_digest",
        "predecessor_raw_deep_research_packet_id",
        "predecessor_raw_deep_research_packet_digest",
        "predecessor_status",
    ],
)
def test_predecessor_lineage_substitution_rejected(key: str) -> None:
    _reject(lambda p, key=key: p["provenance"].__setitem__(key, "forged-predecessor"), f"{key}_mismatch")


def test_superseded_packet_content_fails_current_admission() -> None:
    # Restoring the superseded Cloudflare deployed-version claim is rejected: the superseded packet content is
    # not admissible under the current authority.
    def restore_superseded(packet: dict[str, object]) -> None:
        source = next(s for s in packet["sources"] if s["source_id"] == "cloudflare-roughtime-beta")
        source["protocol_version"] = _SUPERSEDED_PROTOCOL_VERSION_CLAIM
        source["recommendation"] = "DEFER_TO_MT4_ADAPTER"
        source["verification_profile_id"] = "roughtime-nonce-chain-adapter-required.v1"

    _reject(restore_superseded, "packet_digest_mismatch")


def test_superseded_digest_cannot_be_relabeled_current() -> None:
    registry = build_approved_machine_time_source_registry()
    for field_name in ("controller_approved_packet_digest", "canonical_input_packet_digest"):
        forged = _independent_self_consistent(replace(registry, **{field_name: _SUPERSEDED_PACKET_DIGEST}))
        with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
            machine_time_source_registry_digest(forged)
        with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
            machine_time_source_registry_to_dict(forged)


def test_superseded_lineage_ids_cannot_be_relabeled_current() -> None:
    registry = build_approved_machine_time_source_registry()
    forged = _independent_self_consistent(
        replace(registry, controller_approved_packet_id=_SUPERSEDED_PACKET_ID, raw_packet_id=_SUPERSEDED_RAW_PACKET_ID)
    )
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_digest(forged)


# --------------------------------------------------------------------------------------------------
# Cloudflare protocol-provenance correction: corrected source record
# --------------------------------------------------------------------------------------------------


def test_cloudflare_retained_identity_fields_are_exact() -> None:
    record = _cloudflare(build_approved_machine_time_source_registry())
    assert record.source_id == "cloudflare-roughtime-beta"
    assert record.provider_id == "cloudflare"
    assert record.source_class == "authenticated-rough-time"
    assert record.recommended_role == "not_after"
    assert record.official_endpoints == ("udp://roughtime.cloudflare.com:2003",)
    facts = dict(record.fact_items)
    assert facts["root_key_base64"] == "0GD7c3yP8xEc4Zl2zeuN2SlLvDVVocjsPSL8/Rl/7zg="
    assert facts["signature_algorithm"] == "ed25519"


def test_cloudflare_deployed_version_is_unproven() -> None:
    record = _cloudflare(build_approved_machine_time_source_registry())
    assert record.protocol_version == "cloudflare-deployed-version-unproven"
    assert record.maturity == "beta-provider-protocol-version-unproven"
    assert record.recommendation == "DEFER_PENDING_PROTOCOL_PROVENANCE"
    assert record.verification_profile_id == "roughtime-provider-version-unproven-no-verifier.v1"


def test_cloudflare_fact_items_are_exact() -> None:
    facts = dict(_cloudflare(build_approved_machine_time_source_registry()).fact_items)
    assert facts["beta_notice"] is True
    assert facts["root_key_may_change"] is True
    assert facts["deployed_protocol_version_proven"] is False
    assert facts["deployed_draft19_proven"] is False
    assert facts["controller_native_exact_artifact_digest_commitment_registered"] is False
    assert facts["mt4_verifier_profile_selected"] is False
    assert facts["official_source_revision"] == "75645289794cfbd71a08f0e7ecf9bc4f3f87d133"
    assert facts["official_ecosystem_description"] == "google-roughtime-and-ietf-draft08"


def test_cloudflare_record_carries_no_deployed_draft_version_claim() -> None:
    record = _cloudflare(build_approved_machine_time_source_registry())
    drafts = ("draft-ietf-ntp-roughtime-19", "draft-ietf-ntp-roughtime-11", "draft-ietf-ntp-roughtime-08")
    scalar_fields = (
        record.protocol_version,
        record.maturity,
        record.recommendation,
        record.verification_profile_id,
        record.source_class,
    )
    for value in scalar_fields:
        assert not any(draft in value for draft in drafts), value
    # The only fact carrying a draft token at all is the exact official ecosystem description, which describes
    # the official SOURCE, never the deployed endpoint.
    draft_facts = {key for key, value in record.fact_items if isinstance(value, str) and "draft" in value}
    assert draft_facts == {"official_ecosystem_description"}


def test_cloudflare_record_does_not_cite_roughtime_draft_19() -> None:
    registry = build_approved_machine_time_source_registry()
    record = _cloudflare(registry)
    assert record.citation_ids == ("CLOUDFLARE-ROUGHTIME", "CLOUDFLARE-ROUGHTIME-USAGE")
    assert "ROUGHTIME-DRAFT-19" not in record.citation_ids
    # The citation itself survives in the 29-id inventory for generic protocol/archive-policy use only.
    assert "ROUGHTIME-DRAFT-19" in registry.citation_ids
    assert registry.citation_count == 29


def test_pinned_cloudflare_and_roughtime_citation_urls() -> None:
    citations = _packet_of(build_approved_machine_time_source_registry())["citations"]
    assert citations["CLOUDFLARE-ROUGHTIME"] == (
        "https://github.com/cloudflare/roughtime/blob/75645289794cfbd71a08f0e7ecf9bc4f3f87d133/ecosystem.md"
    )
    assert citations["CLOUDFLARE-ROUGHTIME-USAGE"] == "https://developers.cloudflare.com/time-services/roughtime/usage/"
    assert citations["ROUGHTIME-DRAFT-19"] == "https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19"


def test_cloudflare_safety_flags_remain_false() -> None:
    record = _cloudflare(build_approved_machine_time_source_registry())
    for flag in _SOURCE_SAFETY_FLAGS:
        assert getattr(record, flag) is False


def test_new_unproven_subject_is_bound_to_cloudflare_citations() -> None:
    entries = _packet_of(build_approved_machine_time_source_registry())["excluded_or_unproven"]
    matches = [entry for entry in entries if entry["subject"] == _NEW_UNPROVEN_SUBJECT]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["status"] == "UNPROVEN"
    assert entry["citation_ids"] == ["CLOUDFLARE-ROUGHTIME", "CLOUDFLARE-ROUGHTIME-USAGE"]
    assert "does not publish an immutable deployed protocol-version contract" in entry["reason"]
    # Explicitly refuses BOTH a draft-19 and a legacy-only deployment claim.
    assert "No exact current draft-19 or legacy-only deployment claim is approved." in entry["reason"]


@pytest.mark.parametrize(
    ("field_name", "forged"),
    [
        ("protocol_version", _SUPERSEDED_PROTOCOL_VERSION_CLAIM),
        ("maturity", "beta-ietf-internet-draft"),
        ("verification_profile_id", "roughtime-draft19-verifier.v1"),
    ],
)
def test_cloudflare_scalar_substitution_rejected(field_name: str, forged: str) -> None:
    def substitute(packet: dict[str, object]) -> None:
        source = next(s for s in packet["sources"] if s["source_id"] == "cloudflare-roughtime-beta")
        source[field_name] = forged

    _reject(substitute, "packet_digest_mismatch")


def test_cloudflare_recommendation_substitution_rejected() -> None:
    def substitute(packet: dict[str, object]) -> None:
        source = next(s for s in packet["sources"] if s["source_id"] == "cloudflare-roughtime-beta")
        source["recommendation"] = "INCLUDE_NOT_AFTER_CANDIDATE"

    _reject(substitute, "packet_digest_mismatch")


@pytest.mark.parametrize(
    ("fact_key", "forged"),
    [
        ("official_source_revision", "0000000000000000000000000000000000000000"),
        ("official_ecosystem_description", "ietf-draft19-deployed"),
        ("deployed_protocol_version_proven", True),
        ("deployed_draft19_proven", True),
        ("mt4_verifier_profile_selected", True),
    ],
)
def test_cloudflare_fact_forgery_rejected(fact_key: str, forged: object) -> None:
    def substitute(packet: dict[str, object]) -> None:
        source = next(s for s in packet["sources"] if s["source_id"] == "cloudflare-roughtime-beta")
        source["fact_items"][fact_key] = forged

    _reject(substitute, "packet_digest_mismatch")


# --------------------------------------------------------------------------------------------------
# Cloudflare protocol-provenance correction: controller consistency + digest isolation
# --------------------------------------------------------------------------------------------------


def test_no_mt4_adapter_selection_contradiction_remains() -> None:
    decisions = _packet_of(build_approved_machine_time_source_registry())["controller_decisions"]
    # The contradictory "adapter deferred to MT-4" claim is gone; a provenance PRECONDITION replaces it.
    assert "roughtime_adapter_deferred_to_mt4" not in decisions
    assert decisions["roughtime_protocol_provenance_required_before_mt4_profile_selection"] is True
    assert decisions["mt4_verifier_profile_selected"] is False
    assert decisions["roughtime_deployed_protocol_version_proven"] is False
    assert decisions["cloudflare_deployed_protocol_version_decision"] == "DEPLOYED_VERSION_UNPROVEN"


def test_roughtime_remains_non_countable_without_governed_verifier() -> None:
    packet = _packet_of(build_approved_machine_time_source_registry())
    decisions = packet["controller_decisions"]
    assert decisions["roughtime_not_after_countable_without_adapter"] is False
    # not_after counting is unchanged and still excludes authenticated rough time.
    assert decisions["not_after_class_count_supported"] == 2
    independence = packet["independence_policy"]
    assert independence["not_after_classes_supported"] == [
        "rfc3161-timestamp-authority",
        "bitcoin-anchored-blockchain-timestamping",
    ]
    assert "authenticated-rough-time" not in independence["not_after_classes_supported"]
    assert independence["deferred_pending_protocol_provenance_classes"] == ["authenticated-rough-time"]
    assert "deferred_adapter_classes" not in independence


def test_protocol_provenance_gate_decision_cannot_be_weakened() -> None:
    _reject(
        lambda p: p["controller_decisions"].__setitem__(
            "roughtime_protocol_provenance_required_before_mt4_profile_selection", False
        ),
        "roughtime_protocol_provenance_gate_decision_missing",
    )


def test_cloudflare_deployed_version_decision_cannot_be_forged() -> None:
    _reject(
        lambda p: p["controller_decisions"].__setitem__(
            "cloudflare_deployed_protocol_version_decision", "DEPLOYED_DRAFT19_PROVEN"
        ),
        "cloudflare_deployed_version_decision_mismatch",
    )


def test_unrelated_source_entry_digests_are_byte_identical_to_pre_correction() -> None:
    # Digest isolation: the correction changed Cloudflare and nothing else.
    registry = build_approved_machine_time_source_registry()
    actual = {record.source_id: record.entry_digest for record in registry.sources}
    assert len(_UNCHANGED_ENTRY_DIGESTS) == 6
    for source_id, expected in _UNCHANGED_ENTRY_DIGESTS.items():
        assert actual[source_id] == expected, source_id


def test_cloudflare_entry_and_registry_digests_changed() -> None:
    registry = build_approved_machine_time_source_registry()
    assert _cloudflare(registry).entry_digest != _PRE_CORRECTION_CLOUDFLARE_ENTRY_DIGEST
    assert registry.registry_digest != _PRE_CORRECTION_REGISTRY_DIGEST
    assert registry.canonical_input_packet_digest == _PACKET_DIGEST
    assert registry.canonical_input_packet_digest != _SUPERSEDED_PACKET_DIGEST
    # Cloudflare's entry digest is the only source digest that moved.
    changed = {
        record.source_id
        for record in registry.sources
        if record.source_id not in _UNCHANGED_ENTRY_DIGESTS
        or record.entry_digest != _UNCHANGED_ENTRY_DIGESTS[record.source_id]
    }
    assert changed == {"cloudflare-roughtime-beta"}


def test_corrected_registry_is_deterministic_and_reseal_safe() -> None:
    first = build_approved_machine_time_source_registry()
    second = build_approved_machine_time_source_registry()
    assert first == second
    assert first.registry_digest == second.registry_digest
    assert machine_time_source_registry_digest(first) == first.registry_digest
    for record in first.sources:
        assert machine_time_source_entry_digest(record) == record.entry_digest
    assert machine_time_source_registry_to_dict(first)["registry_digest"] == first.registry_digest
    # A stale/forged outer digest is never accepted by the serializer boundary.
    with pytest.raises(MachineTimeSourceRegistryError, match="malformed"):
        machine_time_source_registry_to_dict(replace(first, registry_digest="0" * 64))


def test_correction_proves_no_operational_or_readiness_transition() -> None:
    registry = build_approved_machine_time_source_registry()
    for flag in _ARTIFACT_FALSE_FLAGS:
        assert getattr(registry, flag) is False
    assert registry.mt4_adapter_bound is False
    assert registry.machine_time_origin_proven is False
    assert registry.timestamp_origin_proven is False
    assert registry.operational_quorum_ready is False
    assert registry.readiness_promoted is False
    assert registry.connector_promoted is False
    for record in registry.sources:
        for flag in _SOURCE_SAFETY_FLAGS:
            assert getattr(record, flag) is False
