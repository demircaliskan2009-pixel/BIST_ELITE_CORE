"""MT-3 machine-time source registry (structural, digest-bound, citation-backed metadata admission only).

This module compiles the controller-approved Deep Research packet
``mt3-dr-batch-b-2026-07-20.controller-v1`` (normalized canonical digest
``d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a``, normalized from raw research packet
``mt3-dr-batch-b-2026-07-20.v2``) into a deterministic, immutable, fail-closed registry of the SEVEN
candidate machine-time source classes and their verification-capability METADATA. It is the MT-3 structural
layer that the MT-2 sandwich policy (``machine_time_policy.py``) leaves Deep-Research-gated: MT-2 pins the
abstract not_before/not_after sandwich structure and binds no concrete provider; MT-3 records the concrete
candidate source metadata that a later MT-4 anchor adapter may consume.

The registry records admissible source METADATA only. It performs NO network I/O, contacts NO endpoint, reads
NO wall clock, consumes NO external proof, and proves NOTHING about reachability, operational approval,
quorum membership, proof acquisition, proof verification, machine-time origin, timestamp origin, an
operational day, a 30-day gate, Stage-4 completion, or connector/readiness state. Every such capability flag
is structurally ``False`` on every legitimate artifact, and every per-source ``operational_use_approved`` /
``quorum_countable`` / ``source_reachable_proven`` / ``proof_verified`` flag is structurally ``False``.
Deribit ``public/get_time`` is advisory-only unsigned exchange server time and is never a cryptographic
machine-time origin proof; Cloudflare Roughtime is beta and its exact-artifact digest-binding adapter is
deferred to MT-4; OpenTimestamps finality policy is likewise deferred to MT-4.

``REGISTRY_READY`` is STRUCTURAL ONLY. It means, and only means, that: the embedded controller packet
recomputes to its pinned normalized digest under the canonical serializer; the pinned raw/normalized packet
lineage matches exactly; the exact 7-source / 29-citation / 9-exclusion inventory is preserved in canonical
order with unique source identities; every source safety flag and every registry-wide operational/proof/
quorum decision is ``False``; and the artifact self-digest (and each source entry self-digest) is valid. It
never means any source was contacted, is reachable, is operationally approved, is quorum-countable, supplied
or verified a proof, that machine time or timestamp origin was proven, that MT-2 was mutated or upgraded,
that an MT-4 adapter was bound, or that any Stage-4/readiness/connector/live/order/capital transition
occurred.

Trust-boundary discipline: no caller-carried value participates in equality, ordering, arithmetic, hashing,
set construction, iteration, output projection, or serialization until its exact expected built-in type and
canonical representation have been proven. The controller packet is canonicalized and re-parsed to a
guaranteed-plain JSON structure before any traversal, so a lying ``str``/``int`` subclass or an
equality/hash/order-raising object can never have its custom operation invoked from a protected comparison;
every safely handleable malformed value is projected to a deterministic JSON-only built-in so that even a
``REGISTRY_REJECTED`` artifact still serializes and self-digests. A caller cannot substitute a different
packet authority: any deviation from the pinned digest/lineage/inventory yields ``REGISTRY_REJECTED``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from enum import Enum

_SCHEMA_VERSION = "machine-time-source-registry.v1"
_REGISTRY_VERSION = "machine-time-source-registry.v1"
_REASON_PREFIX = "machine_time_source_registry"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Controller-approved Deep Research packet lineage. These are pinned constants; the builder recomputes the
# normalized canonical digest over the embedded packet and rejects any mismatch before READY.
_RAW_PACKET_ID = "mt3-dr-batch-b-2026-07-20.v2"
_RAW_PACKET_DIGEST = "f8ec03f63d4b790213bc0eea5b5089159cbd3da73792e02ab8db8d7c5d34f9d7"
_CONTROLLER_NORMALIZATION_ID = "mt3-controller-normalization-2026-07-20.v1"
_CONTROLLER_APPROVED_PACKET_ID = "mt3-dr-batch-b-2026-07-20.controller-v1"
_CONTROLLER_APPROVED_PACKET_DIGEST = "d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a"
_PACKET_SCHEMA = "machine-time-source-research-packet.v1"
_RESEARCHED_ON = "2026-07-20"

# Exact expected inventory sizes (fail-closed: any deviation rejects).
_EXPECTED_SOURCE_COUNT = 7
_EXPECTED_CITATION_COUNT = 29
_EXPECTED_EXCLUSION_COUNT = 9

# Canonical registry ordering == controller packet ordering. Wrong order or wrong inventory rejects.
_EXPECTED_SOURCE_IDS = (
    "drand-quicknet-mainnet",
    "nist-randomness-beacon-v2-beta",
    "curby-public-beacon",
    "digicert-rfc3161-tsa",
    "opentimestamps-bitcoin",
    "cloudflare-roughtime-beta",
    "deribit-public-get-time",
)

# Per-source safety flags that MUST remain exactly ``False`` in the approved packet and on every record.
_SOURCE_SAFETY_FLAGS = (
    "operational_use_approved",
    "quorum_countable",
    "source_reachable_proven",
    "proof_verified",
)

# Registry-wide controller decisions that MUST remain exactly ``False``.
_REGISTRY_FALSE_DECISIONS = (
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_quorum_ready",
    "all_operational_use_approved",
    "all_quorum_countable",
    "not_before_operational_quorum_ready",
    "not_after_operational_quorum_ready",
)

# Scalar string fields projected verbatim from each packet source record.
_SOURCE_STRING_FIELDS = (
    "source_id",
    "provider_id",
    "source_class",
    "protocol_version",
    "maturity",
    "recommended_role",
    "recommendation",
    "verification_profile_id",
)

# Closed value domains (a mutated role/recommendation yields a precise rejection in addition to the digest
# mismatch). These are the exact controller-approved value sets, never an invented taxonomy.
_ALLOWED_RECOMMENDED_ROLES = frozenset({"not_before", "not_after", "advisory_only"})
_ALLOWED_RECOMMENDATIONS = frozenset(
    {
        "INCLUDE_NOT_BEFORE_CANDIDATE",
        "INCLUDE_NOT_AFTER_CANDIDATE",
        "DEFER_TO_MT4_ADAPTER",
        "INCLUDE_ADVISORY_ONLY",
    }
)

# Controller-approved Deep Research packet (mt3-dr-batch-b-2026-07-20.controller-v1). Embedded verbatim;
# the builder recomputes its normalized canonical digest and rejects any drift from the pinned constant.
_CONTROLLER_APPROVED_PACKET = {
    "archive_policy": {
        "acquisition_endpoint_metadata_required": True,
        "acquisition_time_is_proof": False,
        "byte_preservation_rule": "preserve_exact_original_bytes_no_reencoding_for_verification",
        "certificate_chain_required_for_x509_cms": True,
        "citation_ids": ["RFC3161", "RFC5816", "OPENTS-CLIENT", "ROUGHTIME-DRAFT-19", "RFC4648", "RFC7468"],
        "content_type_required_when_defined": True,
        "digest_algorithm": "sha256",
        "display_encoding": "lowercase_hex_for_opaque_bytes__rfc7468_textual_encoding_only_for_pkix_pkcs_cms_text_artifacts",
        "network_or_chain_id_required_when_defined": True,
        "offline_reverification_required": True,
        "policy_identifier_required_for_rfc3161": True,
        "profile_id": "machine-time-proof-archive.v1",
        "protocol_version_required": True,
        "public_key_snapshot_required_when_keyed_signature_protocol": True,
        "raw_request_bytes_required_when_protocol_has_request": True,
        "raw_response_or_proof_bytes_required": True,
        "request_nonce_required_for_rfc3161_by_controller": True,
        "request_nonce_required_for_roughtime_adapter": True,
        "revocation_snapshot_required_for_x509_cms": True,
        "round_or_sequence_required_when_defined": True,
        "signature_algorithm_required_when_signed": True,
        "source_id_required": True,
        "trust_anchor_snapshot_required_for_x509_cms": True,
        "verification_software_metadata_required": True,
    },
    "citations": {
        "BITCOIN-GETBLOCKCHAININFO": "https://developer.bitcoin.org/reference/rpc/getblockchaininfo.html",
        "BITCOIN-GETBLOCKHEADER": "https://developer.bitcoin.org/reference/rpc/getblockheader.html",
        "CLOUDFLARE-ROUGHTIME": "https://developers.cloudflare.com/time-services/roughtime/",
        "CLOUDFLARE-ROUGHTIME-USAGE": "https://developers.cloudflare.com/time-services/roughtime/usage/",
        "CURBY-API": "https://random.colorado.edu/api-docs",
        "CURBY-CONCEPTS": "https://random.colorado.edu/concepts",
        "CURBY-HOME": "https://random.colorado.edu/",
        "CURBY-NETWORK": "https://random.colorado.edu/concepts/curby-network",
        "CURBY-USAGE": "https://random.colorado.edu/usage/usage",
        "DERIBIT-GET-TIME": "https://docs.deribit.com/api-reference/supporting/public-get_time",
        "DIGICERT-TSA": "https://knowledge.digicert.com/general-information/rfc3161-compliant-time-stamp-authority-server",
        "DIGICERT-TSA-TROUBLESHOOT": "https://knowledge.digicert.com/solution/troubleshooting-timestamping-problems",
        "DRAND-DEVELOPER": "https://docs.drand.love/developer/",
        "DRAND-HTTP-API": "https://docs.drand.love/developer/API-v2/drand-http-api/",
        "DRAND-QUICKNET-ANNOUNCEMENT": "https://docs.drand.love/blog/2023/10/16/quicknet-is-live/",
        "DRAND-SPEC": "https://docs.drand.love/docs/specification/",
        "NIST-BEACON-20": "https://csrc.nist.gov/Projects/interoperable-randomness-beacons/beacon-20",
        "NIST-IR8213-DRAFT": "https://csrc.nist.gov/pubs/ir/8213/ipd",
        "OPENTS-CLIENT": "https://github.com/opentimestamps/opentimestamps-client",
        "OPENTS-HOME": "https://opentimestamps.org/",
        "RFC3161": "https://www.rfc-editor.org/info/rfc3161/",
        "RFC4648": "https://www.rfc-editor.org/info/rfc4648/",
        "RFC5816": "https://www.rfc-editor.org/info/rfc5816/",
        "RFC7468": "https://www.rfc-editor.org/info/rfc7468/",
        "RFC9162": "https://www.rfc-editor.org/rfc/rfc9162.html",
        "ROUGHTIME-DRAFT-19": "https://datatracker.ietf.org/doc/draft-ietf-ntp-roughtime/",
        "SIGSTORE-BUNDLE": "https://docs.sigstore.dev/about/bundle/",
        "SIGSTORE-REKOR-OVERVIEW": "https://docs.sigstore.dev/logging/overview/",
        "SIGSTORE-THREAT-MODEL": "https://docs.sigstore.dev/about/threat-model/",
    },
    "controller_decisions": {
        "all_operational_use_approved": False,
        "all_quorum_countable": False,
        "count_only_include_recommendations_for_role_totals": True,
        "exchange_time_advisory_only": True,
        "generic_ct_machine_time_use_excluded": True,
        "generic_sigstore_rekor_machine_time_use_unproven_or_excluded": True,
        "machine_time_origin_proven": False,
        "not_after_class_count_supported": 2,
        "not_after_operational_quorum_ready": False,
        "not_before_class_count_supported": 3,
        "not_before_operational_quorum_ready": False,
        "opentimestamps_finality_policy_deferred_to_mt4": True,
        "operational_quorum_ready": False,
        "registry_ready_is_structural_only": True,
        "rfc3161_nonce_required_by_controller": True,
        "roughtime_adapter_deferred_to_mt4": True,
        "roughtime_not_after_countable_without_adapter": False,
        "timestamp_origin_proven": False,
        "unverifiable_facts_excluded": True,
    },
    "excluded_or_unproven": [
        {
            "citation_ids": ["RFC9162"],
            "reason": "Official CT specs remain certificate/precertificate logging with accepted trust anchors, not a provider-neutral exact-artifact-digest notarization source for this project.",
            "status": "EXCLUDE",
            "subject": "certificate-transparency-v2-generic-machine-time-use",
        },
        {
            "citation_ids": ["SIGSTORE-REKOR-OVERVIEW", "SIGSTORE-THREAT-MODEL", "SIGSTORE-BUNDLE"],
            "reason": "Official Sigstore materials describe a transparency log for signed software metadata and inclusion proofs, but this repo would need extra signing, identity, trust-root, and archival assumptions that are not yet controller-neutral MT-3 constants.",
            "status": "UNPROVEN_OR_EXCLUDE",
            "subject": "sigstore-rekor-generic-machine-time-use",
        },
        {
            "citation_ids": ["NIST-BEACON-20"],
            "reason": "The service page documents certificate retrieval, but this report does not fetch a live certificate artifact or pin a current fingerprint.",
            "status": "UNPROVEN",
            "subject": "nist-beacon-v2-live_certificate_fingerprint",
        },
        {
            "citation_ids": ["CURBY-HOME", "CURBY-USAGE"],
            "reason": "The official pages document ongoing relocation/upgrade and proof-of-concept status, but not a finalized post-upgrade steady-state assurance.",
            "status": "UNPROVEN",
            "subject": "curby_current_post_upgrade_operational_steady_state",
        },
        {
            "citation_ids": ["DIGICERT-TSA"],
            "reason": "Available official KB material documents the TSA endpoint and chain, but not a full public-use SLA or rate-limit contract for this repo's purposes.",
            "status": "UNPROVEN",
            "subject": "digicert_public_use_sla_and_rate_limits",
        },
        {
            "citation_ids": ["ROUGHTIME-DRAFT-19", "CLOUDFLARE-ROUGHTIME-USAGE"],
            "reason": "The protocol signs time and includes request-root proofs, but the exact governed-artifact digest-binding adapter must be specified separately.",
            "status": "DEFER_TO_MT4",
            "subject": "roughtime_exact_artifact_digest_binding_format",
        },
        {
            "citation_ids": ["RFC3161"],
            "reason": "RFC 3161 defines nonce as optional; the registry records nonce use as a controller requirement, not as a protocol-mandatory provider fact.",
            "status": "EXCLUDE",
            "subject": "rfc3161_nonce_is_protocol_mandatory",
        },
        {
            "citation_ids": ["OPENTS-HOME", "OPENTS-CLIENT", "BITCOIN-GETBLOCKHEADER", "BITCOIN-GETBLOCKCHAININFO"],
            "reason": "The exact confirmation/finality policy required by this repository is not fixed by the MT-3 evidence packet and must be specified by the later verifier/adapter design.",
            "status": "DEFER_TO_MT4",
            "subject": "opentimestamps_confirmation_or_finality_threshold",
        },
        {
            "citation_ids": ["ROUGHTIME-DRAFT-19", "CLOUDFLARE-ROUGHTIME-USAGE"],
            "reason": "Authenticated rough time alone does not satisfy the repository's exact artifact-digest commitment contract; MT-4 must define and validate an adapter before any later eligibility review.",
            "status": "EXCLUDE",
            "subject": "roughtime_not_after_quorum_without_digest_adapter",
        },
    ],
    "independence_policy": {
        "advisory_classes": ["exchange-server-time"],
        "correlated_failure_notes": [
            "curby_network_docs_describe_drand_mixins",
            "rfc3161_depends_on_x509_trust_and_revocation_evidence",
            "opentimestamps_depends_on_bitcoin_consensus_time_and_block_header_availability",
            "roughtime_depends_on_server_list_and_root_key_management",
        ],
        "counting_rule": "count_independent_source_classes_not_provider_endpoints",
        "curby_drand_correlation_documented": True,
        "deferred_adapter_classes": ["authenticated-rough-time"],
        "invalid_double_counting_examples": [
            "multiple_drand_relays",
            "multiple_calendars_of_same_opentimestamps_trust_system",
            "multiple_endpoints_under_one_tsa_program",
            "unsigned_exchange_time_variants",
        ],
        "not_after_classes_supported": ["rfc3161-timestamp-authority", "bitcoin-anchored-blockchain-timestamping"],
        "not_before_classes_supported": [
            "distributed-threshold-randomness-beacon",
            "signed-hash-chained-public-randomness-beacon",
            "traceable-twine-randomness-beacon",
        ],
        "only_structurally_supported_not_after_pair": [
            "rfc3161-timestamp-authority",
            "bitcoin-anchored-blockchain-timestamping",
        ],
        "strongest_not_before_pair": [
            "distributed-threshold-randomness-beacon",
            "signed-hash-chained-public-randomness-beacon",
        ],
    },
    "packet_id": "mt3-dr-batch-b-2026-07-20.controller-v1",
    "packet_schema": "machine-time-source-research-packet.v1",
    "provenance": {
        "controller_normalization_id": "mt3-controller-normalization-2026-07-20.v1",
        "controller_normalization_notes": [
            "rfc3161_nonce_is_controller_required_not_protocol_mandatory",
            "archive_requirements_are_protocol_conditional",
            "roughtime_not_after_requires_mt4_digest_adapter",
            "opentimestamps_finality_policy_deferred_to_mt4",
            "production_software_documented_maturity_added",
        ],
        "raw_deep_research_packet_digest": "f8ec03f63d4b790213bc0eea5b5089159cbd3da73792e02ab8db8d7c5d34f9d7",
        "raw_deep_research_packet_id": "mt3-dr-batch-b-2026-07-20.v2",
    },
    "researched_on": "2026-07-20",
    "sources": [
        {
            "citation_ids": ["DRAND-DEVELOPER", "DRAND-HTTP-API", "DRAND-SPEC", "DRAND-QUICKNET-ANNOUNCEMENT"],
            "fact_items": {
                "chain_hash": "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971",
                "genesis_unix_seconds": 1692803367,
                "mainnet_documented": True,
                "period_seconds": 3,
                "public_key": "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a",
                "scheme": "bls-unchained-g1-rfc9380",
            },
            "maturity": "mainnet-documented",
            "official_endpoints": [
                "https://api.drand.sh",
                "https://api2.drand.sh",
                "https://api3.drand.sh",
                "https://drand.cloudflare.com",
                "https://api.drand.secureweb3.com:6875",
            ],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "drand-http-api-v2-with-chain-info",
            "provider_id": "league-of-entropy",
            "quorum_countable": False,
            "recommendation": "INCLUDE_NOT_BEFORE_CANDIDATE",
            "recommended_role": "not_before",
            "source_class": "distributed-threshold-randomness-beacon",
            "source_id": "drand-quicknet-mainnet",
            "source_reachable_proven": False,
            "verification_profile_id": "drand-quicknet-signature-and-chain-info-offline.v1",
        },
        {
            "citation_ids": ["NIST-BEACON-20", "NIST-IR8213-DRAFT"],
            "fact_items": {
                "certificate_api_available": True,
                "output_bits": 512,
                "period_seconds": 60,
                "previous_value_hash_chained": True,
                "sequence_numbered": True,
                "signed": True,
                "timestamped": True,
            },
            "maturity": "beta-draft",
            "official_endpoints": [
                "https://beacon.nist.gov/beacon/2.0",
                "https://beacon.nist.gov/beacon/2.0/pulse/last",
                "https://beacon.nist.gov/beacon/2.0/chain/last/pulse/last",
                "https://beacon.nist.gov/beacon/2.0/certificate/<certificateIdentifier>",
            ],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "beacon-2.0-beta",
            "provider_id": "nist",
            "quorum_countable": False,
            "recommendation": "INCLUDE_NOT_BEFORE_CANDIDATE",
            "recommended_role": "not_before",
            "source_class": "signed-hash-chained-public-randomness-beacon",
            "source_id": "nist-randomness-beacon-v2-beta",
            "source_reachable_proven": False,
            "verification_profile_id": "nist-beacon-v2-pulse-signature-hash-chain-offline.v1",
        },
        {
            "citation_ids": ["CURBY-HOME", "CURBY-API", "CURBY-USAGE", "CURBY-CONCEPTS", "CURBY-NETWORK"],
            "fact_items": {
                "client_verification_recommended": True,
                "proof_of_concept_warning": True,
                "public_api_documented": True,
                "response_format": "dag-json",
                "twine_traceability_documented": True,
            },
            "maturity": "proof-of-concept",
            "official_endpoints": ["https://random.colorado.edu/api"],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "curby-http-api-dag-json",
            "provider_id": "university-of-colorado-boulder",
            "quorum_countable": False,
            "recommendation": "INCLUDE_NOT_BEFORE_CANDIDATE",
            "recommended_role": "not_before",
            "source_class": "traceable-twine-randomness-beacon",
            "source_id": "curby-public-beacon",
            "source_reachable_proven": False,
            "verification_profile_id": "curby-twine-client-and-pulse-offline.v1",
        },
        {
            "citation_ids": ["RFC3161", "RFC5816", "DIGICERT-TSA", "DIGICERT-TSA-TROUBLESHOOT"],
            "fact_items": {
                "cms_signed_token": True,
                "controller_requires_nonce": True,
                "esscertidv2_update_available": True,
                "message_imprint_exact_digest_commitment": True,
                "rfc3161_nonce_if_present_must_match": True,
                "trust_material_download_documented": True,
                "tsa_cert_rotation_documented_at_least_every_15_months": True,
            },
            "maturity": "commercial-service-documented",
            "official_endpoints": ["http://timestamp.digicert.com"],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "rfc3161-rfc5816-over-http",
            "provider_id": "digicert",
            "quorum_countable": False,
            "recommendation": "INCLUDE_NOT_AFTER_CANDIDATE",
            "recommended_role": "not_after",
            "source_class": "rfc3161-timestamp-authority",
            "source_id": "digicert-rfc3161-tsa",
            "source_reachable_proven": False,
            "verification_profile_id": "rfc3161-sha256-nonce-cms-pki-offline.v1",
        },
        {
            "citation_ids": ["OPENTS-HOME", "OPENTS-CLIENT", "BITCOIN-GETBLOCKHEADER", "BITCOIN-GETBLOCKCHAININFO"],
            "fact_items": {
                "bitcoin_attestation_supported": True,
                "calendar_mirroring_supported": True,
                "calendar_rest_protocol_may_change": True,
                "controller_finality_policy_deferred_to_mt4": True,
                "format_stability_claimed": True,
                "local_bitcoin_core_required_for_direct_verification": True,
                "local_hashing_privacy": True,
                "production_software_claimed": True,
                "proof_file_extension": ".ots",
            },
            "maturity": "production-software-documented",
            "official_endpoints": [
                "https://opentimestamps.org/",
                "https://alice.btc.calendar.opentimestamps.org",
                "https://bob.btc.calendar.opentimestamps.org",
                "https://finney.calendar.eternitywall.com",
                "https://ots.btc.catallaxy.com",
            ],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "ots-proof-format-stable__calendar-rest-protocol-may-change",
            "provider_id": "opentimestamps",
            "quorum_countable": False,
            "recommendation": "INCLUDE_NOT_AFTER_CANDIDATE",
            "recommended_role": "not_after",
            "source_class": "bitcoin-anchored-blockchain-timestamping",
            "source_id": "opentimestamps-bitcoin",
            "source_reachable_proven": False,
            "verification_profile_id": "opentimestamps-bitcoin-commitment-offline.v1",
        },
        {
            "citation_ids": ["ROUGHTIME-DRAFT-19", "CLOUDFLARE-ROUGHTIME", "CLOUDFLARE-ROUGHTIME-USAGE"],
            "fact_items": {
                "beta_notice": True,
                "controller_digest_binding_adapter_required": True,
                "controller_native_exact_artifact_digest_commitment_registered": False,
                "merkle_root_proves_request_inclusion": True,
                "root_key_base64": "0GD7c3yP8xEc4Zl2zeuN2SlLvDVVocjsPSL8/Rl/7zg=",
                "root_key_may_change": True,
                "signature_algorithm": "ed25519",
                "signed_response_includes_request_nonce": True,
                "uncertainty_radius_present": True,
            },
            "maturity": "beta-ietf-internet-draft",
            "official_endpoints": ["udp://roughtime.cloudflare.com:2003"],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "draft-ietf-ntp-roughtime-19",
            "provider_id": "cloudflare",
            "quorum_countable": False,
            "recommendation": "DEFER_TO_MT4_ADAPTER",
            "recommended_role": "not_after",
            "source_class": "authenticated-rough-time",
            "source_id": "cloudflare-roughtime-beta",
            "source_reachable_proven": False,
            "verification_profile_id": "roughtime-nonce-chain-adapter-required.v1",
        },
        {
            "citation_ids": ["DERIBIT-GET-TIME"],
            "fact_items": {
                "controller_cryptographic_artifact_commitment_registered": False,
                "controller_signature_registered": False,
                "documented_use": "clock-skew-check",
                "response_unit": "milliseconds-since-unix-epoch",
            },
            "maturity": "documented-public-api",
            "official_endpoints": ["public/get_time"],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "deribit-json-rpc-v2",
            "provider_id": "deribit",
            "quorum_countable": False,
            "recommendation": "INCLUDE_ADVISORY_ONLY",
            "recommended_role": "advisory_only",
            "source_class": "exchange-server-time",
            "source_id": "deribit-public-get-time",
            "source_reachable_proven": False,
            "verification_profile_id": "unsigned-exchange-time-advisory-only.v1",
        },
    ],
}


class MachineTimeSourceRegistryError(RuntimeError):
    """Raised on malformed caller input or a malformed artifact at the MT-3 public boundary."""


class MachineTimeSourceRegistryStatus(str, Enum):
    """MT-3 registry status. READY is structural metadata admission only, never machine-time proof."""

    REGISTRY_READY = "REGISTRY_READY"
    REGISTRY_REJECTED = "REGISTRY_REJECTED"


@dataclass(frozen=True)
class MachineTimeSourceRecord:
    """Immutable, digest-bound metadata for one candidate machine-time source class.

    Records stable registry metadata only. Every safety flag is structurally ``False``: the record proves
    nothing about reachability, operational approval, quorum membership, or proof verification.
    """

    source_id: str
    provider_id: str
    source_class: str
    protocol_version: str
    maturity: str
    recommended_role: str
    recommendation: str
    verification_profile_id: str
    official_endpoints: tuple[str, ...]
    citation_ids: tuple[str, ...]
    fact_items: tuple[tuple[str, bool | int | str], ...]
    entry_digest: str
    operational_use_approved: bool = False
    quorum_countable: bool = False
    source_reachable_proven: bool = False
    proof_verified: bool = False


@dataclass(frozen=True)
class MachineTimeSourceRegistry:
    """Immutable, digest-bound MT-3 registry of the controller-approved candidate machine-time sources.

    READY is STRUCTURAL ONLY (see the module docstring): it proves the embedded controller packet recomputes
    to its pinned digest, the exact 7/29/9 inventory is preserved in canonical order, every safety/quorum/
    proof flag is ``False``, and the self-digest is valid. It binds no reachability, operational approval,
    proof, machine-time origin, MT-2 mutation, MT-4 adapter, Stage-4, readiness, or connector state.
    """

    schema_version: str
    registry_version: str
    status: MachineTimeSourceRegistryStatus
    ready: bool
    raw_packet_id: str
    raw_packet_digest: str
    controller_normalization_id: str
    controller_approved_packet_id: str
    controller_approved_packet_digest: str
    packet_schema: str
    researched_on: str
    sources: tuple[MachineTimeSourceRecord, ...]
    source_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    exclusion_subjects: tuple[str, ...]
    source_count: int
    citation_count: int
    exclusion_count: int
    reason_codes: tuple[str, ...]
    registry_digest: str
    # Structural markers — exactly ``True`` on every legitimate artifact.
    paper_only: bool = True
    structural_metadata_only: bool = True
    registry_ready_is_structural_only: bool = True
    deterministic_offline_only: bool = True
    network_fetch_in_builder_forbidden: bool = True
    no_wall_clock_dependency: bool = True
    citation_backed: bool = True
    controller_packet_bound: bool = True
    source_facts_immutable: bool = True
    # Non-claim / capability flags — exactly ``False`` on every legitimate artifact.
    operationally_approved: bool = False
    currently_reachable: bool = False
    proof_acquired: bool = False
    proof_verified: bool = False
    quorum_approved: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    operational_quorum_ready: bool = False
    source_reachable_proven: bool = False
    network_fetch_performed: bool = False
    real_wall_clock_used: bool = False
    machine_proven_day_decided: bool = False
    thirty_day_gate_decided: bool = False
    stage4_completion_decided: bool = False
    prdv4_stage4_complete: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    capital_mutation_enabled: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    readiness_promoted: bool = False
    connector_promoted: bool = False
    mt4_adapter_bound: bool = False
    mt2_policy_mutated: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


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


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return (
        type(value) is str
        and value.strip() != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_canonical_text(value: object) -> bool:
    """Exact built-in ``str`` that is stripped and free of ASCII control/DEL characters (empty allowed)."""

    return (
        type(value) is str and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_canonical_or_empty_string(value: object) -> bool:
    return type(value) is str and (value == "" or _is_plain_non_empty_string(value))


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_plain_string_tuple(value: object) -> bool:
    return type(value) is tuple and all(_is_plain_non_empty_string(item) for item in value)


def _eq_plain_str(value: object, expected: str) -> bool:
    return type(value) is str and value == expected


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _is_canonical_reason_codes(value: object) -> bool:
    if type(value) is not tuple:
        return False
    for reason in value:
        if not _is_plain_non_empty_string(reason) or not reason.startswith(f"{_REASON_PREFIX}:"):
            return False
    return list(value) == sorted(value) and len(set(value)) == len(value)


def _is_canonical_fact_items(value: object) -> bool:
    if type(value) is not tuple:
        return False
    keys: list[str] = []
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            return False
        key, item = pair
        if not _is_canonical_text(key) or key == "":
            return False
        if not (type(item) is bool or _is_exact_int(item) or type(item) is str):
            return False
        keys.append(key)
    return value == tuple(sorted(value, key=lambda pair: pair[0])) and len(set(keys)) == len(keys)


def _safe_string_tuple(value: object) -> tuple[str, ...] | None:
    """A list of exact plain non-empty strings projects to a tuple; anything else projects to ``None``."""

    if type(value) is not list:
        return None
    if not all(_is_plain_non_empty_string(item) for item in value):
        return None
    return tuple(value)


def _safe_fact_items(value: object) -> tuple[tuple[tuple[str, bool | int | str], ...], bool]:
    """Project a ``fact_items`` mapping to a canonical (key-sorted) tuple of scalar pairs.

    Returns ``(pairs, ok)``. ``ok`` is ``False`` when the input is not an exact ``dict`` of canonical
    non-empty ``str`` keys to ``bool``/``int``/``str`` scalar values; malformed pairs are dropped so the
    projection stays deterministic and serializable even in a rejected artifact.
    """

    if type(value) is not dict:
        return (), False
    items: list[tuple[str, bool | int | str]] = []
    ok = True
    for key, item in value.items():
        if _is_canonical_text(key) and key != "" and (type(item) is bool or _is_exact_int(item) or type(item) is str):
            items.append((key, item))
        else:
            ok = False
    return tuple(sorted(items, key=lambda pair: pair[0])), ok


def _source_record_core_payload(record: MachineTimeSourceRecord) -> dict[str, object]:
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
    }


def _source_record_payload(record: MachineTimeSourceRecord) -> dict[str, object]:
    payload = _source_record_core_payload(record)
    payload["entry_digest"] = record.entry_digest
    return payload


def _expected_entry_digest(record: MachineTimeSourceRecord) -> str:
    """Canonical recomputation of a record's entry digest over every field except the entry self-digest.

    Pure and non-recursive (never calls ``machine_time_source_entry_digest`` or the registry validator), so it
    can be reused both by the recompute API and by the nested-digest verification inside the artifact
    validator without creating a cycle. Callers MUST pass a record whose shape is already proven.
    """

    return _canonical_digest(_source_record_core_payload(record))


def _validate_source_record(
    record: object, *, require_populated_self_digest: bool, verify_entry_digest: bool = False
) -> MachineTimeSourceRecord:
    if type(record) is not MachineTimeSourceRecord:
        raise MachineTimeSourceRegistryError(_reason("malformed_source_record"))

    def _fail() -> None:
        raise MachineTimeSourceRegistryError(_reason("malformed_source_record"))

    for field_name in _SOURCE_STRING_FIELDS:
        if not _is_canonical_or_empty_string(getattr(record, field_name)):
            _fail()
    if not _is_plain_string_tuple(record.official_endpoints):
        _fail()
    if not _is_plain_string_tuple(record.citation_ids):
        _fail()
    if not _is_canonical_fact_items(record.fact_items):
        _fail()
    for field_name in _SOURCE_SAFETY_FLAGS:
        if getattr(record, field_name) is not False:
            _fail()
    digest_value = record.entry_digest
    if type(digest_value) is not str:
        _fail()
    elif require_populated_self_digest:
        if not _is_hex64_string(digest_value):
            _fail()
    elif not (digest_value == "" or _is_hex64_string(digest_value)):
        _fail()
    # Nested-digest verification: a populated entry digest must equal the record's own recomputation, so a
    # caller cannot swap a well-formed-but-false nested self-digest (or mutate a source field and reseal the
    # entry digest) and have the artifact validator accept it. The record shape is fully proven above, so the
    # core payload is JSON-serializable and this recomputation is safe and non-recursive.
    if verify_entry_digest and _is_hex64_string(digest_value) and digest_value != _expected_entry_digest(record):
        _fail()
    return record


def machine_time_source_entry_digest(record: MachineTimeSourceRecord) -> str:
    """Recompute the canonical entry digest over every record field except the entry self-digest.

    Recompute API: it never trusts the carried ``entry_digest`` (``verify_entry_digest=False``) and always
    returns the canonical recomputation, so it can seal a fresh record or re-derive a stale one.
    """

    validated = _validate_source_record(record, require_populated_self_digest=False, verify_entry_digest=False)
    return _expected_entry_digest(validated)


def _replace_entry_digest(record: MachineTimeSourceRecord, digest: str) -> MachineTimeSourceRecord:
    values = {field.name: getattr(record, field.name) for field in fields(record) if field.name != "entry_digest"}
    values["entry_digest"] = digest
    return MachineTimeSourceRecord(**values)  # type: ignore[arg-type]


def _project_source_record(source_obj: object) -> tuple[MachineTimeSourceRecord, list[str]]:
    """Project one packet source object into a sealed-shape record + its precise rejection reasons.

    Exact-type-guarded and side-effect-free: any malformed field projects to a deterministic JSON-only
    built-in and adds a precise reason, so a rejected registry still serializes and self-digests.
    """

    extra: list[str] = []
    if type(source_obj) is not dict:
        source_obj = {}
        extra.append(_reason("source_record_malformed"))
    strings: dict[str, str] = {}
    for field_name in _SOURCE_STRING_FIELDS:
        value = source_obj.get(field_name)
        if _is_plain_non_empty_string(value):
            strings[field_name] = value  # type: ignore[assignment]
        else:
            strings[field_name] = ""
            extra.append(_reason(f"source_field_{field_name}_invalid"))
    if strings["recommended_role"] not in _ALLOWED_RECOMMENDED_ROLES:
        extra.append(_reason("recommended_role_unsupported"))
    if strings["recommendation"] not in _ALLOWED_RECOMMENDATIONS:
        extra.append(_reason("recommendation_unsupported"))
    endpoints = _safe_string_tuple(source_obj.get("official_endpoints"))
    if endpoints is None:
        endpoints = ()
        extra.append(_reason("official_endpoints_malformed"))
    citation_ids = _safe_string_tuple(source_obj.get("citation_ids"))
    if citation_ids is None:
        citation_ids = ()
        extra.append(_reason("source_citation_ids_malformed"))
    fact_items, fact_ok = _safe_fact_items(source_obj.get("fact_items"))
    if not fact_ok:
        extra.append(_reason("fact_items_malformed"))
    for field_name in _SOURCE_SAFETY_FLAGS:
        if source_obj.get(field_name) is not False:
            extra.append(_reason(f"source_flag_{field_name}_not_false"))
    seed_record = MachineTimeSourceRecord(
        source_id=strings["source_id"],
        provider_id=strings["provider_id"],
        source_class=strings["source_class"],
        protocol_version=strings["protocol_version"],
        maturity=strings["maturity"],
        recommended_role=strings["recommended_role"],
        recommendation=strings["recommendation"],
        verification_profile_id=strings["verification_profile_id"],
        official_endpoints=endpoints,
        citation_ids=citation_ids,
        fact_items=fact_items,
        entry_digest="",
        operational_use_approved=False,
        quorum_countable=False,
        source_reachable_proven=False,
        proof_verified=False,
    )
    return seed_record, extra


def _packet_semantic_ok(verified: dict[str, object], digest: str) -> bool:
    """Reproof of the COMPLETE READY contract on the canonical (re-parsed, plain-JSON) packet.

    ``verified`` is the product of ``json.loads(json.dumps(packet, ...))`` so every value is a plain JSON
    built-in; every check below is exact-type-before-operation and never invokes a caller-controlled method.
    """

    if digest != _CONTROLLER_APPROVED_PACKET_DIGEST:
        return False
    if not _eq_plain_str(verified.get("packet_id"), _CONTROLLER_APPROVED_PACKET_ID):
        return False
    if not _eq_plain_str(verified.get("packet_schema"), _PACKET_SCHEMA):
        return False
    provenance = verified.get("provenance")
    if type(provenance) is not dict:
        return False
    if not _eq_plain_str(provenance.get("raw_deep_research_packet_id"), _RAW_PACKET_ID):
        return False
    if not _eq_plain_str(provenance.get("raw_deep_research_packet_digest"), _RAW_PACKET_DIGEST):
        return False
    if not _eq_plain_str(provenance.get("controller_normalization_id"), _CONTROLLER_NORMALIZATION_ID):
        return False
    sources = verified.get("sources")
    if type(sources) is not list or len(sources) != _EXPECTED_SOURCE_COUNT:
        return False
    ids: list[object] = []
    for source_obj in sources:
        if type(source_obj) is not dict:
            return False
        for flag in _SOURCE_SAFETY_FLAGS:
            if source_obj.get(flag) is not False:
                return False
        if source_obj.get("recommended_role") not in _ALLOWED_RECOMMENDED_ROLES:
            return False
        if source_obj.get("recommendation") not in _ALLOWED_RECOMMENDATIONS:
            return False
        ids.append(source_obj.get("source_id"))
    if tuple(ids) != _EXPECTED_SOURCE_IDS:
        return False
    citations = verified.get("citations")
    if type(citations) is not dict or len(citations) != _EXPECTED_CITATION_COUNT:
        return False
    exclusions = verified.get("excluded_or_unproven")
    if type(exclusions) is not list or len(exclusions) != _EXPECTED_EXCLUSION_COUNT:
        return False
    decisions = verified.get("controller_decisions")
    if type(decisions) is not dict:
        return False
    for name in _REGISTRY_FALSE_DECISIONS:
        if decisions.get(name) is not False:
            return False
    if decisions.get("registry_ready_is_structural_only") is not True:
        return False
    return True


def _expected_registry_semantics() -> tuple[tuple[MachineTimeSourceRecord, ...], tuple[str, ...], tuple[str, ...]]:
    """Derive the authoritative ``(sources, citation_ids, exclusion_subjects)`` from the embedded packet.

    Re-proves that the embedded (mutable) module packet still canonicalizes to the pinned normalized digest
    BEFORE deriving anything, then rebuilds the exact sealed source records, the sorted citation-ID inventory,
    and the packet-ordered exclusion subjects from a freshly re-parsed canonical copy. The approved packet
    must project cleanly; a corrupted or tampered embedded packet fails closed rather than yielding weakened
    expectations. This is the single authority for READY semantic equality — never a hand-maintained partial
    field list.
    """

    canonical = json.dumps(
        _CONTROLLER_APPROVED_PACKET, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != _CONTROLLER_APPROVED_PACKET_DIGEST:
        raise MachineTimeSourceRegistryError(_reason("embedded_packet_digest_mismatch"))
    verified = json.loads(canonical)
    records: list[MachineTimeSourceRecord] = []
    for source_obj in verified["sources"]:
        seed_record, reasons = _project_source_record(source_obj)
        if reasons:
            raise MachineTimeSourceRegistryError(_reason("embedded_packet_source_malformed"))
        records.append(_replace_entry_digest(seed_record, machine_time_source_entry_digest(seed_record)))
    citation_ids = tuple(sorted(verified["citations"].keys()))
    exclusion_subjects = tuple(entry["subject"] for entry in verified["excluded_or_unproven"])
    return tuple(records), citation_ids, exclusion_subjects


def _registry_semantic_ok(registry: MachineTimeSourceRegistry) -> bool:
    """Artifact-side reproof of EXACT semantic equality with the controller-approved packet.

    Called only after the shape validator proves every field's exact type (and every nested entry digest is
    self-consistent). Beyond lineage / counts / ids it requires the artifact's source records, citation-ID
    inventory, and exclusion subjects to equal the records / inventory derived from the re-verified embedded
    packet, so a caller cannot mutate any load-bearing source field (provider / class / protocol / maturity /
    verification profile / endpoints / fact items / per-source citations), reseal the nested and outer
    digests, and still be accepted. Exact frozen-dataclass equality over the full source tuple binds every
    source field, including its entry digest.
    """

    expected_records, expected_citation_ids, expected_exclusion_subjects = _expected_registry_semantics()
    if registry.controller_approved_packet_digest != _CONTROLLER_APPROVED_PACKET_DIGEST:
        return False
    if registry.controller_approved_packet_id != _CONTROLLER_APPROVED_PACKET_ID:
        return False
    if registry.raw_packet_id != _RAW_PACKET_ID or registry.raw_packet_digest != _RAW_PACKET_DIGEST:
        return False
    if registry.controller_normalization_id != _CONTROLLER_NORMALIZATION_ID:
        return False
    if registry.packet_schema != _PACKET_SCHEMA or registry.researched_on != _RESEARCHED_ON:
        return False
    if registry.source_count != _EXPECTED_SOURCE_COUNT:
        return False
    if registry.citation_count != _EXPECTED_CITATION_COUNT:
        return False
    if registry.exclusion_count != _EXPECTED_EXCLUSION_COUNT:
        return False
    if registry.source_ids != _EXPECTED_SOURCE_IDS:
        return False
    if registry.citation_ids != expected_citation_ids:
        return False
    if registry.exclusion_subjects != expected_exclusion_subjects:
        return False
    if len(registry.sources) != len(expected_records):
        return False
    return registry.sources == expected_records


def _registry_payload_from(registry: MachineTimeSourceRegistry) -> dict[str, object]:
    """Build the canonical payload. Callers MUST pass an artifact already proven by the validator."""

    payload: dict[str, object] = {}
    for field in fields(registry):
        if field.name == "registry_digest":
            continue
        value = getattr(registry, field.name)
        if field.name == "status":
            payload[field.name] = registry.status.value
        elif field.name == "sources":
            payload[field.name] = [_source_record_payload(record) for record in registry.sources]
        elif type(value) is tuple:
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    return payload


def _validate_machine_time_source_registry_artifact(
    registry: object, *, require_populated_self_digest: bool
) -> MachineTimeSourceRegistry:
    """Prove the COMPLETE exact runtime + canonical contract of every public field before any traversal."""

    if type(registry) is not MachineTimeSourceRegistry:
        raise MachineTimeSourceRegistryError(_reason("malformed_artifact"))

    def _fail() -> None:
        raise MachineTimeSourceRegistryError(_reason("malformed_artifact"))

    if not (
        _eq_plain_str(registry.schema_version, _SCHEMA_VERSION)
        and _eq_plain_str(registry.registry_version, _REGISTRY_VERSION)
    ):
        _fail()
    if not (
        _eq_plain_str(registry.raw_packet_id, _RAW_PACKET_ID)
        and _eq_plain_str(registry.raw_packet_digest, _RAW_PACKET_DIGEST)
        and _eq_plain_str(registry.controller_normalization_id, _CONTROLLER_NORMALIZATION_ID)
        and _eq_plain_str(registry.controller_approved_packet_id, _CONTROLLER_APPROVED_PACKET_ID)
        and _eq_plain_str(registry.controller_approved_packet_digest, _CONTROLLER_APPROVED_PACKET_DIGEST)
        and _eq_plain_str(registry.packet_schema, _PACKET_SCHEMA)
        and _eq_plain_str(registry.researched_on, _RESEARCHED_ON)
    ):
        _fail()

    if type(registry.status) is not MachineTimeSourceRegistryStatus or type(registry.ready) is not bool:
        _fail()
    if not _is_canonical_reason_codes(registry.reason_codes):
        _fail()
    if registry.status is MachineTimeSourceRegistryStatus.REGISTRY_READY:
        if registry.ready is not True or registry.reason_codes != ():
            _fail()
    elif registry.status is MachineTimeSourceRegistryStatus.REGISTRY_REJECTED:
        if registry.ready is not False or registry.reason_codes == ():
            _fail()
    else:  # pragma: no cover - the enum has exactly two members
        _fail()

    for field_name in ("source_count", "citation_count", "exclusion_count"):
        value = getattr(registry, field_name)
        if not _is_exact_int(value) or value < 0:
            _fail()

    if type(registry.sources) is not tuple:
        _fail()
    # Every nested source record in a registry is always sealed (the builder reseals each record before
    # constructing the artifact), so require a populated, self-consistent entry digest for every one — this
    # protects reconstructed / caller-held artifacts, not only freshly built ones (review P1: recompute entry
    # digests before accepting artifacts).
    for record in registry.sources:
        _validate_source_record(record, require_populated_self_digest=True, verify_entry_digest=True)

    if type(registry.source_ids) is not tuple or not all(
        _is_canonical_or_empty_string(source_id) for source_id in registry.source_ids
    ):
        _fail()
    if registry.source_ids != tuple(record.source_id for record in registry.sources):
        _fail()

    if not _is_plain_string_tuple(registry.citation_ids):
        _fail()
    if list(registry.citation_ids) != sorted(registry.citation_ids) or len(set(registry.citation_ids)) != len(
        registry.citation_ids
    ):
        _fail()
    if len(registry.citation_ids) != registry.citation_count:
        _fail()

    if type(registry.exclusion_subjects) is not tuple or not all(
        _is_canonical_or_empty_string(subject) for subject in registry.exclusion_subjects
    ):
        _fail()
    if len(registry.exclusion_subjects) != registry.exclusion_count:
        _fail()

    for field_name in _ARTIFACT_TRUE_FLAGS:
        if getattr(registry, field_name) is not True:
            _fail()
    for field_name in _ARTIFACT_FALSE_FLAGS:
        if getattr(registry, field_name) is not False:
            _fail()

    if registry.status is MachineTimeSourceRegistryStatus.REGISTRY_READY and not _registry_semantic_ok(registry):
        _fail()

    digest_value = registry.registry_digest
    if type(digest_value) is not str:
        _fail()
    elif require_populated_self_digest:
        if not _is_hex64_string(digest_value):
            _fail()
    elif not (digest_value == "" or _is_hex64_string(digest_value)):
        _fail()

    return registry


def machine_time_source_registry_digest(registry: MachineTimeSourceRegistry) -> str:
    """Recompute the canonical registry digest over every public field except the self-digest.

    Never trusts the carried ``registry_digest``; always recomputes from the canonical payload. A forged
    exact dataclass with a malformed field, a structural overclaim, or a canonical-but-invalid READY value
    raises ``MachineTimeSourceRegistryError`` (``malformed_artifact``) instead of resealing a digest.
    """

    validated = _validate_machine_time_source_registry_artifact(registry, require_populated_self_digest=False)
    return _canonical_digest(_registry_payload_from(validated))


def machine_time_source_registry_to_dict(registry: MachineTimeSourceRegistry) -> dict[str, object]:
    """Canonical JSON-ready mapping for the MT-3 registry, including its self-digest.

    Requires an exact ``MachineTimeSourceRegistry`` whose every public field is canonical, whose self-digest
    is a populated lowercase hex64, and whose carried self-digest exactly equals the canonical recomputation
    over every other field. Any wrong-typed or malformed artifact raises ``MachineTimeSourceRegistryError``.
    """

    validated = _validate_machine_time_source_registry_artifact(registry, require_populated_self_digest=True)
    payload = _registry_payload_from(validated)
    if validated.registry_digest != _canonical_digest(payload):
        raise MachineTimeSourceRegistryError(_reason("malformed_artifact"))
    payload["registry_digest"] = validated.registry_digest
    return payload


def _replace_registry_digest(registry: MachineTimeSourceRegistry, digest: str) -> MachineTimeSourceRegistry:
    values = {
        field.name: getattr(registry, field.name) for field in fields(registry) if field.name != "registry_digest"
    }
    values["registry_digest"] = digest
    return MachineTimeSourceRegistry(**values)  # type: ignore[arg-type]


def build_machine_time_source_registry(*, packet: dict[str, object] | None = None) -> MachineTimeSourceRegistry:
    """Compile the controller-approved MT-3 source packet into a deterministic, digest-bound registry.

    With ``packet=None`` the embedded controller-approved packet is compiled (always ``REGISTRY_READY``). Any
    caller-supplied packet is canonicalized, re-parsed to plain JSON, and verified against the pinned
    digest/lineage/inventory/flag contract; any deviation yields ``REGISTRY_REJECTED`` with precise reasons.
    A caller cannot substitute a different packet authority and obtain READY. Only a non-``dict`` or a
    non-JSON-serializable packet raises ``MachineTimeSourceRegistryError``.
    """

    source_packet = _CONTROLLER_APPROVED_PACKET if packet is None else packet
    if type(source_packet) is not dict:
        raise MachineTimeSourceRegistryError(_reason("packet_not_mapping"))
    try:
        canonical = json.dumps(source_packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise MachineTimeSourceRegistryError(_reason("packet_not_serializable")) from exc
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    verified = json.loads(canonical)

    hard: list[str] = []
    if digest != _CONTROLLER_APPROVED_PACKET_DIGEST:
        hard.append(_reason("packet_digest_mismatch"))
    if not _eq_plain_str(verified.get("packet_id"), _CONTROLLER_APPROVED_PACKET_ID):
        hard.append(_reason("packet_id_mismatch"))
    if not _eq_plain_str(verified.get("packet_schema"), _PACKET_SCHEMA):
        hard.append(_reason("packet_schema_mismatch"))

    provenance = verified.get("provenance")
    if type(provenance) is not dict:
        hard.append(_reason("provenance_malformed"))
        provenance = {}
    if not _eq_plain_str(provenance.get("raw_deep_research_packet_id"), _RAW_PACKET_ID):
        hard.append(_reason("raw_packet_id_mismatch"))
    raw_digest_value = provenance.get("raw_deep_research_packet_digest")
    if not _is_hex64_string(raw_digest_value):
        hard.append(_reason("raw_packet_digest_malformed"))
    if not _eq_plain_str(raw_digest_value, _RAW_PACKET_DIGEST):
        hard.append(_reason("raw_packet_digest_mismatch"))
    if not _eq_plain_str(provenance.get("controller_normalization_id"), _CONTROLLER_NORMALIZATION_ID):
        hard.append(_reason("controller_normalization_id_mismatch"))

    raw_sources = verified.get("sources")
    if type(raw_sources) is not list:
        hard.append(_reason("sources_malformed"))
        raw_sources = []
    if len(raw_sources) != _EXPECTED_SOURCE_COUNT:
        hard.append(_reason("source_count_mismatch"))
    records: list[MachineTimeSourceRecord] = []
    seen_ids: list[str] = []
    for source_obj in raw_sources:
        seed_record, record_reasons = _project_source_record(source_obj)
        record = _replace_entry_digest(seed_record, machine_time_source_entry_digest(seed_record))
        records.append(record)
        hard.extend(record_reasons)
        seen_ids.append(record.source_id)
    source_ids = tuple(seen_ids)
    if source_ids != _EXPECTED_SOURCE_IDS:
        if len(set(seen_ids)) == len(seen_ids) and sorted(seen_ids) == sorted(_EXPECTED_SOURCE_IDS):
            hard.append(_reason("source_order_mismatch"))
        else:
            hard.append(_reason("source_inventory_mismatch"))
    if len(set(seen_ids)) != len(seen_ids):
        hard.append(_reason("duplicate_source_id"))

    citations = verified.get("citations")
    if type(citations) is not dict:
        hard.append(_reason("citations_malformed"))
        citation_ids: tuple[str, ...] = ()
    else:
        if not all(_is_plain_non_empty_string(key) for key in citations):
            hard.append(_reason("citations_malformed"))
        citation_ids = tuple(sorted(key for key in citations if _is_plain_non_empty_string(key)))
    if len(citation_ids) != _EXPECTED_CITATION_COUNT:
        hard.append(_reason("citation_count_mismatch"))
    citation_id_set = set(citation_ids)
    for record in records:
        if any(citation_id not in citation_id_set for citation_id in record.citation_ids):
            hard.append(_reason("source_citation_unregistered"))
            break

    exclusions = verified.get("excluded_or_unproven")
    if type(exclusions) is not list:
        hard.append(_reason("exclusions_malformed"))
        exclusions = []
    if len(exclusions) != _EXPECTED_EXCLUSION_COUNT:
        hard.append(_reason("exclusion_count_mismatch"))
    exclusion_subjects = tuple(
        entry.get("subject") if type(entry) is dict and _is_plain_non_empty_string(entry.get("subject")) else ""
        for entry in exclusions
    )
    if any(subject == "" for subject in exclusion_subjects):
        hard.append(_reason("exclusion_subject_malformed"))

    decisions = verified.get("controller_decisions")
    if type(decisions) is not dict:
        hard.append(_reason("controller_decisions_malformed"))
        decisions = {}
    for name in _REGISTRY_FALSE_DECISIONS:
        if decisions.get(name) is not False:
            hard.append(_reason(f"decision_{name}_not_false"))
    if decisions.get("registry_ready_is_structural_only") is not True:
        hard.append(_reason("registry_structural_only_decision_missing"))

    reason_codes = _sorted_unique(hard)
    ready = not reason_codes

    # Defensive READY invariant: re-prove the COMPLETE safety conclusion on the canonical packet itself.
    if ready and not _packet_semantic_ok(verified, digest):
        reason_codes = (_reason("ready_invariant_failed"),)
        ready = False

    status = (
        MachineTimeSourceRegistryStatus.REGISTRY_READY if ready else MachineTimeSourceRegistryStatus.REGISTRY_REJECTED
    )

    registry_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "registry_version": _REGISTRY_VERSION,
        "status": status,
        "ready": ready,
        "raw_packet_id": _RAW_PACKET_ID,
        "raw_packet_digest": _RAW_PACKET_DIGEST,
        "controller_normalization_id": _CONTROLLER_NORMALIZATION_ID,
        "controller_approved_packet_id": _CONTROLLER_APPROVED_PACKET_ID,
        "controller_approved_packet_digest": _CONTROLLER_APPROVED_PACKET_DIGEST,
        "packet_schema": _PACKET_SCHEMA,
        "researched_on": _RESEARCHED_ON,
        "sources": tuple(records),
        "source_ids": source_ids,
        "citation_ids": citation_ids,
        "exclusion_subjects": exclusion_subjects,
        "source_count": len(raw_sources),
        "citation_count": len(citation_ids),
        "exclusion_count": len(exclusions),
        "reason_codes": reason_codes,
    }
    seed = MachineTimeSourceRegistry(registry_digest="", **registry_fields)  # type: ignore[arg-type]
    return _replace_registry_digest(seed, machine_time_source_registry_digest(seed))


def build_approved_machine_time_source_registry() -> MachineTimeSourceRegistry:
    """Compile the embedded controller-approved MT-3 packet (always ``REGISTRY_READY``, structural only)."""

    return build_machine_time_source_registry()


__all__ = [
    "MachineTimeSourceRegistryError",
    "MachineTimeSourceRegistryStatus",
    "MachineTimeSourceRecord",
    "MachineTimeSourceRegistry",
    "build_machine_time_source_registry",
    "build_approved_machine_time_source_registry",
    "machine_time_source_registry_digest",
    "machine_time_source_registry_to_dict",
    "machine_time_source_entry_digest",
]
