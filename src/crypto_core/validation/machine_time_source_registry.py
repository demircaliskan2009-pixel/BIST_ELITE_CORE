"""MT-3 machine-time source registry (structural, digest-bound, citation-backed metadata admission only).

This module compiles the controller-approved packet
``mt3-cloudflare-provenance-correction-2026-07-23.controller-v1`` into a deterministic, immutable,
fail-closed registry of the SEVEN candidate machine-time source classes and their verification-capability
METADATA. It is the MT-3 structural layer that the MT-2 sandwich policy (``machine_time_policy.py``) leaves
Deep-Research-gated: MT-2 pins the abstract not_before/not_after sandwich structure and binds no concrete
provider; MT-3 records the concrete candidate source metadata that a later MT-4 anchor adapter may consume.

Packet lineage. The CURRENT authority is the human-approved Cloudflare protocol-provenance correction
``mt3-cloudflare-provenance-correction-2026-07-23.authority-v1``, whose exact canonical approval data is
EMBEDDED in the packet's ``correction_authority`` block and whose digest is recomputed over that embedded
block at every admission (never a digest asserted over unembedded approval prose). It supersedes the
predecessor Deep Research controller packet ``mt3-dr-batch-b-2026-07-20.controller-v1``
(``d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a``, normalized from raw research packet
``mt3-dr-batch-b-2026-07-20.v2``). That predecessor lineage is retained as HISTORICAL provenance only: the
superseded packet content and the superseded digest are NOT current authority and fail current admission
(``REGISTRY_REJECTED``).

Cloudflare deployed-version decision: ``DEPLOYED_VERSION_UNPROVEN``. The registry records NO proven deployed
Roughtime protocol version for ``udp://roughtime.cloudflare.com:2003``. The official Cloudflare source at
revision ``75645289794cfbd71a08f0e7ecf9bc4f3f87d133`` describes Google-Roughtime and IETF draft08, and no
current public documentation publishes an immutable deployed protocol-version contract, so neither a
draft-19 nor a legacy-only deployment claim is admitted. UNPROVEN is not DISPROVEN: nothing here establishes
that any particular version is absent. In particular a timeout observation is not admitted as evidence of any
deployed protocol version, and it equally fails to disprove one
(``timeout_observation_proves_deployed_protocol_version`` is ``False`` in the embedded authority).
The Cloudflare provider record therefore carries ``protocol_version`` ``cloudflare-deployed-version-unproven``
and does NOT cite ``ROUGHTIME-DRAFT-19`` as deployment evidence (that citation survives only for generic
protocol/archive-policy facts that are not attributed to Cloudflare's current deployment). MT-4 verifier
profile selection is BLOCKED until protocol provenance exists.

The registry records admissible source METADATA only. It performs NO network I/O, contacts NO endpoint, reads
NO wall clock, consumes NO external proof, and proves NOTHING about reachability, operational approval,
quorum membership, proof acquisition, proof verification, machine-time origin, timestamp origin, an
operational day, a 30-day gate, Stage-4 completion, or connector/readiness state. Every such capability flag
is structurally ``False`` on every legitimate artifact, and every per-source ``operational_use_approved`` /
``quorum_countable`` / ``source_reachable_proven`` / ``proof_verified`` flag is structurally ``False``.
Deribit ``public/get_time`` is advisory-only unsigned exchange server time and is never a cryptographic
machine-time origin proof; Cloudflare Roughtime is beta with an unproven deployed protocol version and no
selected MT-4 verifier profile; OpenTimestamps finality policy is likewise deferred to MT-4.

``REGISTRY_READY`` is STRUCTURAL ONLY. It means, and only means, that: the embedded controller packet
recomputes to its pinned normalized digest under the canonical serializer; the embedded correction-authority
block recomputes to its pinned authority digest; the pinned correction-authority / predecessor packet lineage
matches exactly; the exact 7-source / 29-citation / 10-exclusion inventory is preserved in canonical order
with unique source identities; every source safety flag and every registry-wide operational/proof/quorum
decision is ``False``; and the artifact self-digest (and each source entry self-digest) is valid. It never
means any source was contacted, is reachable, is operationally approved, is quorum-countable, supplied or
verified a proof, that machine time or timestamp origin was proven, that a deployed provider protocol version
was proven, that MT-2 was mutated or upgraded, that an MT-4 verifier profile was selected or an MT-4 adapter
bound, or that any Stage-4/readiness/connector/live/order/capital transition occurred.

Version discipline. ``schema_version`` describes the PUBLIC ARTIFACT SHAPE and is unchanged (``.v1``): this
correction adds no artifact field and changes no field's interpretation. ``registry_version`` is bumped to
``.v2`` because the admitted registry CONTENT identity changed (corrected Cloudflare record, one added
unproven subject, one added allowed recommendation value). ``packet_schema`` is bumped to ``.v2`` because the
PACKET shape changed (new ``correction_authority`` block; correction/predecessor provenance keys).

Trust-boundary discipline: no caller-carried value participates in equality, ordering, arithmetic, hashing,
set construction, iteration, output projection, or serialization until its exact expected built-in type and
canonical representation have been proven. The controller packet is canonicalized and re-parsed to a
guaranteed-plain JSON structure before any traversal, so a lying ``str``/``int`` subclass or an
equality/hash/order-raising object can never have its custom operation invoked from a protected comparison;
every safely handleable malformed value is projected to a deterministic JSON-only built-in so that even a
``REGISTRY_REJECTED`` artifact still serializes and self-digests. A caller cannot substitute a different
packet authority: any deviation from the pinned digest/lineage/inventory yields ``REGISTRY_REJECTED``.

Content-addressed input binding: the supplied packet is first recursively normalized to EXACT built-in plain
data (a fresh copy of ``dict``/``list``/``str``/``int``/``bool`` only; every subtype, non-plain scalar,
non-string key, container cycle and over-depth is rejected with ``MachineTimeSourceRegistryError`` before any
subtype-defined comparison/ordering/hashing/iteration/mapping/string callback can run). The exact canonical
JSON text of that plain packet and its SHA-256 are stored on every artifact, and a single deterministic
evaluator derives all status/reason/projection state from that same canonical text — at build time and again
at every public boundary. Consequently the artifact is bound to the CURRENT canonical CONTENT of its input
packet: a ``REGISTRY_REJECTED`` artifact whose projected fields happen to match the approved artifact can
never be relabeled ``REGISTRY_READY`` (its carried canonical input still differs, so re-evaluation contradicts
the relabel). This proves current content, NOT which historical caller or constructor invocation produced the
artifact; reconstructing every field with the exact approved canonical packet simply yields the approved
value artifact, which is legitimate content reconstruction and is never described as origin provenance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from enum import Enum

_SCHEMA_VERSION = "machine-time-source-registry.v1"
_REGISTRY_VERSION = "machine-time-source-registry.v2"
_REASON_PREFIX = "machine_time_source_registry"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# CURRENT controller-approved packet lineage. The raw upstream authority for this packet revision is the
# human-approved Cloudflare protocol-provenance correction, whose exact canonical approval data is EMBEDDED in
# the packet (``correction_authority``). These are pinned constants; the builder recomputes BOTH the canonical
# digest over the embedded correction-authority block AND the normalized canonical digest over the whole
# embedded packet, and rejects any mismatch before READY.
_RAW_PACKET_ID = "mt3-cloudflare-provenance-correction-2026-07-23.authority-v1"
_RAW_PACKET_DIGEST = "4a09d5e3bb48ae2039c2c164abe1f88ee9b6ebe9edcf1e29e17147ac92dd5bd7"
_CONTROLLER_NORMALIZATION_ID = "mt3-controller-normalization-2026-07-23.cloudflare-provenance-correction-v1"
_CONTROLLER_APPROVED_PACKET_ID = "mt3-cloudflare-provenance-correction-2026-07-23.controller-v1"
_CONTROLLER_APPROVED_PACKET_DIGEST = "a575eaffd2098432f08c77ba9a3c84a8177992b24b91ff350e3348ecc93b9d82"
_PACKET_SCHEMA = "machine-time-source-research-packet.v2"
# Unchanged: this correction is a human-approved governance correction over already-acquired evidence, not a
# new research pass. Dating it later would falsely imply fresh research; the correction date lives in
# ``correction_authority.approved_on``.
_RESEARCHED_ON = "2026-07-20"

# Exact human governance authority for this correction. Its canonical data is embedded in the packet's
# ``correction_authority`` block; nothing here claims a digest over unembedded approval prose.
_HUMAN_APPROVAL_ID = "MT3-CLOUDFLARE-PROVENANCE-CORRECTION-HUMAN-APPROVAL-V1"
_HUMAN_APPROVAL_RESULT = "APPROVED_FOR_DEDICATED_MT3_CLOUDFLARE_PROVENANCE_CORRECTION_PREFLIGHT"
_CLOUDFLARE_DEPLOYED_VERSION_DECISION = "DEPLOYED_VERSION_UNPROVEN"

# SUPERSEDED predecessor lineage. Retained as HISTORICAL provenance only: this packet id/digest is explicitly
# NOT current authority, and the superseded packet content fails current admission.
_SUPERSEDED_RAW_PACKET_ID = "mt3-dr-batch-b-2026-07-20.v2"
_SUPERSEDED_RAW_PACKET_DIGEST = "f8ec03f63d4b790213bc0eea5b5089159cbd3da73792e02ab8db8d7c5d34f9d7"
_SUPERSEDED_CONTROLLER_PACKET_ID = "mt3-dr-batch-b-2026-07-20.controller-v1"
_SUPERSEDED_CONTROLLER_PACKET_DIGEST = "d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a"
_SUPERSEDED_STATUS = "SUPERSEDED_NOT_CURRENT_AUTHORITY"

# Exact expected inventory sizes (fail-closed: any deviation rejects).
_EXPECTED_SOURCE_COUNT = 7
_EXPECTED_CITATION_COUNT = 29
_EXPECTED_EXCLUSION_COUNT = 10

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
    "mt4_verifier_profile_selected",
    "roughtime_deployed_protocol_version_proven",
)

# Registry-wide controller decisions that MUST remain exactly ``True``. These are the fail-closed governance
# statements the correction depends on: READY is structural only, and Roughtime protocol provenance is
# REQUIRED BEFORE any MT-4 verifier-profile selection (never a statement that a profile/adapter was selected).
_REGISTRY_TRUE_DECISIONS = (
    "registry_ready_is_structural_only",
    "roughtime_protocol_provenance_required_before_mt4_profile_selection",
)

# Exact predecessor-lineage fields the packet MUST carry, and the exact values they must carry. They record
# HISTORY: the superseded packet is named so it can never be silently reintroduced as current authority, and
# a substituted predecessor id/digest rejects.
_PREDECESSOR_PROVENANCE_FIELDS = (
    ("predecessor_controller_approved_packet_id", _SUPERSEDED_CONTROLLER_PACKET_ID),
    ("predecessor_controller_approved_packet_digest", _SUPERSEDED_CONTROLLER_PACKET_DIGEST),
    ("predecessor_raw_deep_research_packet_id", _SUPERSEDED_RAW_PACKET_ID),
    ("predecessor_raw_deep_research_packet_digest", _SUPERSEDED_RAW_PACKET_DIGEST),
    ("predecessor_status", _SUPERSEDED_STATUS),
)

# Exact string fields the embedded human-approval authority block MUST carry.
_CORRECTION_AUTHORITY_STRING_FIELDS = (
    ("approval_id", _HUMAN_APPROVAL_ID),
    ("approval_result", _HUMAN_APPROVAL_RESULT),
    ("authority_id", _RAW_PACKET_ID),
    ("deployed_version_decision", _CLOUDFLARE_DEPLOYED_VERSION_DECISION),
    ("superseded_controller_approved_packet_id", _SUPERSEDED_CONTROLLER_PACKET_ID),
    ("superseded_controller_approved_packet_digest", _SUPERSEDED_CONTROLLER_PACKET_DIGEST),
    ("superseded_status", _SUPERSEDED_STATUS),
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
        "DEFER_PENDING_PROTOCOL_PROVENANCE",
        "INCLUDE_ADVISORY_ONLY",
    }
)

# CURRENT controller-approved packet (mt3-cloudflare-provenance-correction-2026-07-23.controller-v1).
# Embedded verbatim as COMPLETE canonical data — never a runtime patch over a superseded packet. The builder
# recomputes the embedded correction-authority digest and the whole-packet normalized canonical digest, and
# rejects any drift from the pinned constants.
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
        "CLOUDFLARE-ROUGHTIME": "https://github.com/cloudflare/roughtime/blob/75645289794cfbd71a08f0e7ecf9bc4f3f87d133/ecosystem.md",
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
        "ROUGHTIME-DRAFT-19": "https://datatracker.ietf.org/doc/html/draft-ietf-ntp-roughtime-19",
        "SIGSTORE-BUNDLE": "https://docs.sigstore.dev/about/bundle/",
        "SIGSTORE-REKOR-OVERVIEW": "https://docs.sigstore.dev/logging/overview/",
        "SIGSTORE-THREAT-MODEL": "https://docs.sigstore.dev/about/threat-model/",
    },
    "controller_decisions": {
        "all_operational_use_approved": False,
        "all_quorum_countable": False,
        "cloudflare_deployed_protocol_version_decision": "DEPLOYED_VERSION_UNPROVEN",
        "count_only_include_recommendations_for_role_totals": True,
        "exchange_time_advisory_only": True,
        "generic_ct_machine_time_use_excluded": True,
        "generic_sigstore_rekor_machine_time_use_unproven_or_excluded": True,
        "machine_time_origin_proven": False,
        "mt4_verifier_profile_selected": False,
        "not_after_class_count_supported": 2,
        "not_after_operational_quorum_ready": False,
        "not_before_class_count_supported": 3,
        "not_before_operational_quorum_ready": False,
        "opentimestamps_finality_policy_deferred_to_mt4": True,
        "operational_quorum_ready": False,
        "registry_ready_is_structural_only": True,
        "rfc3161_nonce_required_by_controller": True,
        "roughtime_deployed_protocol_version_proven": False,
        "roughtime_not_after_countable_without_adapter": False,
        "roughtime_protocol_provenance_required_before_mt4_profile_selection": True,
        "timestamp_origin_proven": False,
        "unverifiable_facts_excluded": True,
    },
    # Human governance authority for this packet revision, embedded as EXACT canonical data so its digest
    # (``provenance.correction_authority_digest`` == ``_RAW_PACKET_DIGEST``) is recomputed over data that is
    # actually present, never asserted over unembedded approval prose.
    "correction_authority": {
        "approval_id": "MT3-CLOUDFLARE-PROVENANCE-CORRECTION-HUMAN-APPROVAL-V1",
        "approval_result": "APPROVED_FOR_DEDICATED_MT3_CLOUDFLARE_PROVENANCE_CORRECTION_PREFLIGHT",
        "approved_evidence": {
            "cloudflare_official_ecosystem_description": "google-roughtime-and-ietf-draft08",
            "cloudflare_official_source_revision": "75645289794cfbd71a08f0e7ecf9bc4f3f87d133",
            "deployed_endpoint": "udp://roughtime.cloudflare.com:2003",
            "deployed_protocol_version_contract_published": False,
            "official_source_library_documented_draft_support": [
                "draft-ietf-ntp-roughtime-08",
                "draft-ietf-ntp-roughtime-11",
            ],
            "published_root_key_base64": "0GD7c3yP8xEc4Zl2zeuN2SlLvDVVocjsPSL8/Rl/7zg=",
            "timeout_observation_proves_deployed_protocol_version": False,
        },
        "approved_on": "2026-07-23",
        "authority_id": "mt3-cloudflare-provenance-correction-2026-07-23.authority-v1",
        "citation_ids": ["CLOUDFLARE-ROUGHTIME", "CLOUDFLARE-ROUGHTIME-USAGE"],
        "corrected_source_id": "cloudflare-roughtime-beta",
        "deployed_version_decision": "DEPLOYED_VERSION_UNPROVEN",
        "mt4_verifier_profile_selected": False,
        "superseded_controller_approved_packet_digest": (
            "d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a"
        ),
        "superseded_controller_approved_packet_id": "mt3-dr-batch-b-2026-07-20.controller-v1",
        "superseded_protocol_version_claim": "draft-ietf-ntp-roughtime-19",
        "superseded_status": "SUPERSEDED_NOT_CURRENT_AUTHORITY",
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
        # Appended last, after the nine predecessor subjects in their original order, so the canonical
        # exclusion ordering of the superseded packet is preserved exactly and the new subject has one
        # deterministic documented position.
        {
            "citation_ids": ["CLOUDFLARE-ROUGHTIME", "CLOUDFLARE-ROUGHTIME-USAGE"],
            "reason": "Current official Cloudflare source describes Google-Roughtime and IETF draft08, while current public documentation does not publish an immutable deployed protocol-version contract for roughtime.cloudflare.com:2003. No exact current draft-19 or legacy-only deployment claim is approved.",
            "status": "UNPROVEN",
            "subject": "cloudflare_deployed_roughtime_protocol_version",
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
        "deferred_pending_protocol_provenance_classes": ["authenticated-rough-time"],
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
    "packet_id": "mt3-cloudflare-provenance-correction-2026-07-23.controller-v1",
    "packet_schema": "machine-time-source-research-packet.v2",
    "provenance": {
        "controller_normalization_id": "mt3-controller-normalization-2026-07-23.cloudflare-provenance-correction-v1",
        "controller_normalization_notes": [
            "rfc3161_nonce_is_controller_required_not_protocol_mandatory",
            "archive_requirements_are_protocol_conditional",
            "roughtime_not_after_requires_mt4_digest_adapter",
            "opentimestamps_finality_policy_deferred_to_mt4",
            "production_software_documented_maturity_added",
            "cloudflare_deployed_protocol_version_recorded_as_unproven",
            "cloudflare_provider_record_no_longer_cites_roughtime_draft_19_as_deployment_evidence",
            "cloudflare_provider_fact_items_carry_no_deployed_draft_grammar_claim",
            "roughtime_protocol_provenance_required_before_mt4_verifier_profile_selection",
            "predecessor_controller_packet_retained_as_history_only_not_current_authority",
        ],
        # Current raw upstream authority: the embedded, human-approved correction authority. Its digest is
        # recomputed over ``correction_authority`` at every admission.
        "correction_authority_digest": "4a09d5e3bb48ae2039c2c164abe1f88ee9b6ebe9edcf1e29e17147ac92dd5bd7",
        "correction_authority_id": "mt3-cloudflare-provenance-correction-2026-07-23.authority-v1",
        # HISTORICAL predecessor lineage only — explicitly not current authority.
        "predecessor_controller_approved_packet_digest": (
            "d5de63d9cc441f6d4659e8775768abaa53d80c6b9e663a936f6fdbd4348bb77a"
        ),
        "predecessor_controller_approved_packet_id": "mt3-dr-batch-b-2026-07-20.controller-v1",
        "predecessor_raw_deep_research_packet_digest": (
            "f8ec03f63d4b790213bc0eea5b5089159cbd3da73792e02ab8db8d7c5d34f9d7"
        ),
        "predecessor_raw_deep_research_packet_id": "mt3-dr-batch-b-2026-07-20.v2",
        "predecessor_status": "SUPERSEDED_NOT_CURRENT_AUTHORITY",
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
        # Cloudflare provider record — DEPLOYED_VERSION_UNPROVEN. It records only Cloudflare-attributable
        # facts: the endpoint, the published root key, beta state, the exact official source revision and its
        # ecosystem description, and the explicit non-proof of any deployed protocol version. The generic
        # draft-19 grammar facts (Merkle request-inclusion root, signed-response nonce, uncertainty radius)
        # and the ROUGHTIME-DRAFT-19 citation were removed from THIS provider record because they were
        # readable as proof of Cloudflare's current deployed grammar; ROUGHTIME-DRAFT-19 survives in the
        # citation inventory only for generic protocol/archive-policy statements (``archive_policy`` and the
        # generic Roughtime exclusion subjects) that are not attributed to Cloudflare's current deployment.
        {
            "citation_ids": ["CLOUDFLARE-ROUGHTIME", "CLOUDFLARE-ROUGHTIME-USAGE"],
            "fact_items": {
                "beta_notice": True,
                "controller_digest_binding_adapter_required": True,
                "controller_native_exact_artifact_digest_commitment_registered": False,
                "deployed_draft19_proven": False,
                "deployed_protocol_version_proven": False,
                "mt4_verifier_profile_selected": False,
                "official_ecosystem_description": "google-roughtime-and-ietf-draft08",
                "official_source_revision": "75645289794cfbd71a08f0e7ecf9bc4f3f87d133",
                "root_key_base64": "0GD7c3yP8xEc4Zl2zeuN2SlLvDVVocjsPSL8/Rl/7zg=",
                "root_key_may_change": True,
                "signature_algorithm": "ed25519",
            },
            "maturity": "beta-provider-protocol-version-unproven",
            "official_endpoints": ["udp://roughtime.cloudflare.com:2003"],
            "operational_use_approved": False,
            "proof_verified": False,
            "protocol_version": "cloudflare-deployed-version-unproven",
            "provider_id": "cloudflare",
            "quorum_countable": False,
            "recommendation": "DEFER_PENDING_PROTOCOL_PROVENANCE",
            "recommended_role": "not_after",
            "source_class": "authenticated-rough-time",
            "source_id": "cloudflare-roughtime-beta",
            "source_reachable_proven": False,
            "verification_profile_id": "roughtime-provider-version-unproven-no-verifier.v1",
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

    READY is STRUCTURAL ONLY (see the module docstring): it proves the embedded controller packet and its
    embedded correction-authority block recompute to their pinned digests, the exact 7/29/10 inventory is
    preserved in canonical order, every safety/quorum/proof flag is ``False``, and the self-digest is valid.
    It binds no reachability, operational approval, proof, machine-time origin, deployed provider protocol
    version, MT-2 mutation, MT-4 verifier profile/adapter, Stage-4, readiness, or connector state.
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
    canonical_input_packet_json: str
    canonical_input_packet_digest: str
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


# Deterministic canonical integer magnitude bound, checked via ``bit_length()`` (never string conversion) so
# it is independent of Python's mutable ``sys.set_int_max_str_digits()`` state. Every legitimate current
# packet/source/count integer (unix timestamps, ports, bit/byte counts, protocol counts) fits comfortably
# within 63 bits; a hostile exact integer beyond this bound (for example ``10**100000``) is rejected here
# instead of surviving to a later canonical-JSON serialization boundary where it would raise a raw
# ``ValueError`` from CPython's int-to-string conversion guard.
_MAX_CANONICAL_INT_BIT_LENGTH = 63


def _is_exact_int(value: object) -> bool:
    """Exact built-in ``int`` (never ``bool``) within the deterministic canonical magnitude bound."""

    return type(value) is int and not isinstance(value, bool) and value.bit_length() <= _MAX_CANONICAL_INT_BIT_LENGTH


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


# Maximum container nesting depth accepted from a supplied packet. The controller-approved packet nests only a
# few levels; 64 is a generous but bounded ceiling that fails closed (never a raw RecursionError) on hostile
# deep input.
_MAX_PACKET_DEPTH = 64

# Exact built-in scalar domain of the controller-approved packet: str, int, bool. It carries no float and no
# null, so the normalizer deliberately does NOT broaden the domain to those (a wider domain is unnecessary and
# an unproved value is rejected, never coerced).


def _normalize_plain_packet(value: object, *, _depth: int = 0, _ancestors: tuple[int, ...] = ()) -> object:
    """Recursively copy a supplied packet into a tree of EXACT built-in plain data, or fail closed.

    Accepts only ``type(value) is`` exactly ``dict`` / ``list`` / ``str`` / ``int`` / ``bool`` (dict keys must
    be exact ``str``); every other value — including ``dict``/``list``/``str``/``int``/``bool`` SUBCLASSES,
    ``float`` and ``None`` — raises ``MachineTimeSourceRegistryError`` BEFORE any subtype-defined comparison,
    ordering, hashing, iteration, mapping or string behavior can run. Exact-container type is proven before any
    ``.items()`` / iteration; keys are proven exact ``str`` before insertion (so ``json.dumps(sort_keys=True)``
    later sorts only exact strings). Container cycles are detected by identity along the current path and depth
    is bounded, so no raw ``RecursionError`` escapes. The returned tree is a fresh plain copy safe to hand to
    the canonical serializer; the caller's original object is never mutated and its custom callbacks never run.
    """

    if _depth > _MAX_PACKET_DEPTH:
        raise MachineTimeSourceRegistryError(_reason("packet_max_depth_exceeded"))
    value_type = type(value)
    if value_type is dict:
        marker = id(value)
        if marker in _ancestors:
            raise MachineTimeSourceRegistryError(_reason("packet_cycle_detected"))
        next_ancestors = (*_ancestors, marker)
        result: dict[str, object] = {}
        for key, item in value.items():  # exact dict proven above → builtin .items()
            if type(key) is not str:
                raise MachineTimeSourceRegistryError(_reason("packet_non_string_key"))
            result[key] = _normalize_plain_packet(item, _depth=_depth + 1, _ancestors=next_ancestors)
        return result
    if value_type is list:
        marker = id(value)
        if marker in _ancestors:
            raise MachineTimeSourceRegistryError(_reason("packet_cycle_detected"))
        next_ancestors = (*_ancestors, marker)
        return [_normalize_plain_packet(item, _depth=_depth + 1, _ancestors=next_ancestors) for item in value]
    if value_type is bool or value_type is str:
        return value
    if value_type is int:
        # Bound checked here (before any canonical serialization) via ``bit_length()``, never string
        # conversion, so a hostile huge exact integer never reaches ``json.dumps`` and raises a raw
        # ``ValueError`` from CPython's int-to-string conversion guard.
        if value.bit_length() > _MAX_CANONICAL_INT_BIT_LENGTH:
            raise MachineTimeSourceRegistryError(_reason("packet_int_magnitude_exceeded"))
        return value
    raise MachineTimeSourceRegistryError(_reason("packet_non_plain_value"))


def _correction_authority_digest(verified: dict[str, object]) -> str | None:
    """Canonical SHA-256 over the packet's EMBEDDED ``correction_authority`` block, or ``None`` if malformed.

    The authority digest is therefore always recomputed over data that is actually present in the packet; the
    module never asserts a digest over approval prose that is not embedded. ``verified`` MUST already be exact
    plain JSON data (see ``_evaluate_plain_packet``), so this canonicalization invokes no caller callback. The
    block does not contain its own digest (that lives in ``provenance``), so there is no circularity.
    """

    authority = verified.get("correction_authority")
    if type(authority) is not dict:
        return None
    try:
        canonical = json.dumps(authority, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):  # pragma: no cover - plain JSON input is always serializable
        return None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    if not _eq_plain_str(provenance.get("correction_authority_id"), _RAW_PACKET_ID):
        return False
    if not _eq_plain_str(provenance.get("correction_authority_digest"), _RAW_PACKET_DIGEST):
        return False
    if _correction_authority_digest(verified) != _RAW_PACKET_DIGEST:
        return False
    if not _eq_plain_str(provenance.get("controller_normalization_id"), _CONTROLLER_NORMALIZATION_ID):
        return False
    for key, expected in _PREDECESSOR_PROVENANCE_FIELDS:
        if not _eq_plain_str(provenance.get(key), expected):
            return False
    authority = verified.get("correction_authority")
    if type(authority) is not dict:
        return False
    for key, expected in _CORRECTION_AUTHORITY_STRING_FIELDS:
        if not _eq_plain_str(authority.get(key), expected):
            return False
    if authority.get("mt4_verifier_profile_selected") is not False:
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
    for name in _REGISTRY_TRUE_DECISIONS:
        if decisions.get(name) is not True:
            return False
    if not _eq_plain_str(
        decisions.get("cloudflare_deployed_protocol_version_decision"), _CLOUDFLARE_DEPLOYED_VERSION_DECISION
    ):
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

    canonical, _digest = _approved_canonical_packet()
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


def _approved_canonical_packet() -> tuple[str, str]:
    """Canonical JSON text + SHA-256 of the embedded controller-approved packet (re-proven each call).

    Normalizes the embedded (mutable) module packet through the exact-plain-data boundary, canonicalizes it,
    and requires the digest to equal the pinned constant before returning — so a tampered embedded packet
    fails closed instead of yielding a weakened authority. This is the single source of the canonical approved
    packet text against which every READY artifact's carried input must match.
    """

    plain = _normalize_plain_packet(_CONTROLLER_APPROVED_PACKET)
    canonical = json.dumps(plain, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if digest != _CONTROLLER_APPROVED_PACKET_DIGEST:
        raise MachineTimeSourceRegistryError(_reason("embedded_packet_digest_mismatch"))
    # The embedded human-approval authority block must also recompute to its pinned digest, so a tampered
    # approval block fails closed here rather than yielding a weakened expected-semantics authority.
    if _correction_authority_digest(json.loads(canonical)) != _RAW_PACKET_DIGEST:
        raise MachineTimeSourceRegistryError(_reason("embedded_correction_authority_digest_mismatch"))
    return canonical, digest


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
    # READY requires the artifact to carry the EXACT approved canonical input packet (content binding), not
    # merely pinned lineage constants — a rejected artifact whose projected fields happen to match approved can
    # never be relabeled READY because its carried input still differs from this canonical text/digest.
    approved_json, approved_digest = _approved_canonical_packet()
    if registry.canonical_input_packet_digest != approved_digest:
        return False
    if registry.canonical_input_packet_json != approved_json:
        return False
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

    # P1-A content binding: the artifact must carry a reprovable EXACT canonical representation of its input
    # packet, and every derived field (status / ready / reason_codes / sources / inventories / counts) must
    # equal a deterministic re-evaluation of THAT carried packet. This is what makes a REJECTED artifact
    # un-relabelable to READY: changing only status / reason codes / projected fields (or resealing digests)
    # contradicts the re-evaluation of the still-different carried canonical input.
    canonical_input = registry.canonical_input_packet_json
    if type(canonical_input) is not str or not _is_hex64_string(registry.canonical_input_packet_digest):
        _fail()
    # Canonical JSON decoder boundary: translate every hostile-decoder failure mode (malformed JSON text,
    # excessive nesting) into the deterministic malformed_artifact rejection instead of letting a raw
    # ValueError/RecursionError escape this public boundary.
    try:
        decoded_input = json.loads(canonical_input)
    except (ValueError, RecursionError):
        _fail()
    # The carried canonical input must decode to an exact top-level dict before any evaluator access; a list,
    # scalar, or other non-dict top-level value fails deterministically instead of reaching a ``.get()`` call
    # on a non-mapping value.
    if type(decoded_input) is not dict:
        _fail()
    try:
        plain_input = _normalize_plain_packet(decoded_input)
    except MachineTimeSourceRegistryError:
        _fail()
    try:
        recanonical = json.dumps(plain_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        _fail()
    if recanonical != canonical_input:
        _fail()
    if hashlib.sha256(recanonical.encode("utf-8")).hexdigest() != registry.canonical_input_packet_digest:
        _fail()
    # ``plain_input`` is already exact plain-JSON-compatible data (produced by ``_normalize_plain_packet``),
    # so it is passed directly to the evaluator rather than performing a second, unguarded ``json.loads`` of
    # the recanonicalized text.
    evaluation = _evaluate_plain_packet(plain_input, registry.canonical_input_packet_digest)
    if (
        registry.status is not evaluation.status
        or registry.ready is not evaluation.ready
        or registry.reason_codes != evaluation.reason_codes
        or registry.sources != evaluation.records
        or registry.source_ids != evaluation.source_ids
        or registry.citation_ids != evaluation.citation_ids
        or registry.exclusion_subjects != evaluation.exclusion_subjects
        or registry.source_count != evaluation.source_count
        or registry.citation_count != evaluation.citation_count
        or registry.exclusion_count != evaluation.exclusion_count
    ):
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


@dataclass(frozen=True)
class _PacketEvaluation:
    """Internal deterministic evaluation of a plain-JSON packet — the single derivation of registry state."""

    status: MachineTimeSourceRegistryStatus
    ready: bool
    reason_codes: tuple[str, ...]
    records: tuple[MachineTimeSourceRecord, ...]
    source_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    exclusion_subjects: tuple[str, ...]
    source_count: int
    citation_count: int
    exclusion_count: int


def _evaluate_plain_packet(verified: dict[str, object], digest: str) -> _PacketEvaluation:
    """Deterministically evaluate a plain-JSON packet + its canonical digest into complete registry state.

    Pure function shared by the builder AND both public-boundary validators, so a stored artifact's
    status/ready/reason_codes and every projected field can be reproved from its carried canonical input and
    can never drift from what that input actually evaluates to. ``verified`` MUST already be exact plain JSON
    data: an exact ``dict`` produced either via ``json.loads`` of a canonical serialization of a normalized
    packet, or directly via ``_normalize_plain_packet`` (both yield equivalent exact plain data).
    """

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
    if not _eq_plain_str(provenance.get("correction_authority_id"), _RAW_PACKET_ID):
        hard.append(_reason("raw_packet_id_mismatch"))
    raw_digest_value = provenance.get("correction_authority_digest")
    if not _is_hex64_string(raw_digest_value):
        hard.append(_reason("raw_packet_digest_malformed"))
    if not _eq_plain_str(raw_digest_value, _RAW_PACKET_DIGEST):
        hard.append(_reason("raw_packet_digest_mismatch"))
    if not _eq_plain_str(provenance.get("controller_normalization_id"), _CONTROLLER_NORMALIZATION_ID):
        hard.append(_reason("controller_normalization_id_mismatch"))
    for key, expected in _PREDECESSOR_PROVENANCE_FIELDS:
        if not _eq_plain_str(provenance.get(key), expected):
            hard.append(_reason(f"{key}_mismatch"))

    # Correction authority: the digest carried in provenance MUST equal a fresh canonical recomputation over
    # the EMBEDDED approval block, so the authority digest is never an unbacked claim about approval prose.
    authority = verified.get("correction_authority")
    if type(authority) is not dict:
        hard.append(_reason("correction_authority_malformed"))
        authority = {}
    recomputed_authority_digest = _correction_authority_digest(verified)
    if recomputed_authority_digest is None or recomputed_authority_digest != _RAW_PACKET_DIGEST:
        hard.append(_reason("correction_authority_digest_mismatch"))
    for key, expected in _CORRECTION_AUTHORITY_STRING_FIELDS:
        if not _eq_plain_str(authority.get(key), expected):
            hard.append(_reason(f"correction_authority_{key}_mismatch"))
    if authority.get("mt4_verifier_profile_selected") is not False:
        hard.append(_reason("correction_authority_mt4_verifier_profile_selected_not_false"))

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
    if decisions.get("roughtime_protocol_provenance_required_before_mt4_profile_selection") is not True:
        hard.append(_reason("roughtime_protocol_provenance_gate_decision_missing"))
    if not _eq_plain_str(
        decisions.get("cloudflare_deployed_protocol_version_decision"), _CLOUDFLARE_DEPLOYED_VERSION_DECISION
    ):
        hard.append(_reason("cloudflare_deployed_version_decision_mismatch"))

    reason_codes = _sorted_unique(hard)
    ready = not reason_codes

    # Defensive READY invariant: re-prove the COMPLETE safety conclusion on the canonical packet itself.
    if ready and not _packet_semantic_ok(verified, digest):
        reason_codes = (_reason("ready_invariant_failed"),)
        ready = False

    status = (
        MachineTimeSourceRegistryStatus.REGISTRY_READY if ready else MachineTimeSourceRegistryStatus.REGISTRY_REJECTED
    )
    return _PacketEvaluation(
        status=status,
        ready=ready,
        reason_codes=reason_codes,
        records=tuple(records),
        source_ids=source_ids,
        citation_ids=citation_ids,
        exclusion_subjects=exclusion_subjects,
        source_count=len(raw_sources),
        citation_count=len(citation_ids),
        exclusion_count=len(exclusions),
    )


def build_machine_time_source_registry(*, packet: dict[str, object] | None = None) -> MachineTimeSourceRegistry:
    """Compile a supplied MT-3 source packet into a deterministic, digest-bound, content-addressed registry.

    With ``packet=None`` the embedded controller-approved packet is compiled (always ``REGISTRY_READY``). Any
    supplied packet is first recursively normalized to EXACT built-in plain data (rejecting subtypes, non-plain
    scalars, non-string keys, cycles and over-depth via ``MachineTimeSourceRegistryError`` before any subtype
    callback can run), canonicalized, and content-addressed: the exact canonical input text and its SHA-256 are
    stored on the artifact and every derived field is produced by the shared deterministic evaluator. A packet
    that is not exactly the approved packet yields ``REGISTRY_REJECTED`` (content-bound, never relabelable to
    READY). Only a non-``dict`` outer packet or a non-plain value raises ``MachineTimeSourceRegistryError``.

    The artifact binds the current canonical content of its input packet; it does NOT claim to prove which
    historical caller or constructor invocation produced it.
    """

    source_packet = _CONTROLLER_APPROVED_PACKET if packet is None else packet
    if type(source_packet) is not dict:
        raise MachineTimeSourceRegistryError(_reason("packet_not_mapping"))
    # P1-B: build a fresh EXACT-plain-data copy before any serialization/sorting so no nested subtype callback
    # (comparison, ordering, hashing, iteration, mapping, str) can execute on unproved caller data.
    plain_packet = _normalize_plain_packet(source_packet)
    canonical = json.dumps(plain_packet, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    verified = json.loads(canonical)
    evaluation = _evaluate_plain_packet(verified, digest)

    registry_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "registry_version": _REGISTRY_VERSION,
        "status": evaluation.status,
        "ready": evaluation.ready,
        "raw_packet_id": _RAW_PACKET_ID,
        "raw_packet_digest": _RAW_PACKET_DIGEST,
        "controller_normalization_id": _CONTROLLER_NORMALIZATION_ID,
        "controller_approved_packet_id": _CONTROLLER_APPROVED_PACKET_ID,
        "controller_approved_packet_digest": _CONTROLLER_APPROVED_PACKET_DIGEST,
        "packet_schema": _PACKET_SCHEMA,
        "researched_on": _RESEARCHED_ON,
        "canonical_input_packet_json": canonical,
        "canonical_input_packet_digest": digest,
        "sources": evaluation.records,
        "source_ids": evaluation.source_ids,
        "citation_ids": evaluation.citation_ids,
        "exclusion_subjects": evaluation.exclusion_subjects,
        "source_count": evaluation.source_count,
        "citation_count": evaluation.citation_count,
        "exclusion_count": evaluation.exclusion_count,
        "reason_codes": evaluation.reason_codes,
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
