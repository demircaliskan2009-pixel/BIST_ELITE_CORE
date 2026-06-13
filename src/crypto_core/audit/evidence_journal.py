"""Append-only in-memory evidence journal with deterministic hash chaining."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

_SCHEMA_VERSION = "1.0"
_JOURNAL_EXPORT_SCHEMA_VERSION = "evidence-journal.v1"
_JOURNAL_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "entry_count",
        "head_digest",
        "entries",
    }
)
_ENTRY_EXPORT_FIELDS = frozenset(
    {
        "schema_version",
        "journal_seq",
        "entry_type",
        "payload",
        "payload_digest",
        "prev_entry_digest",
        "entry_digest",
        "correlation_id",
    }
)

_WALL_CLOCK_TOKENS = (
    "created_at",
    "timestamp",
    "timestamp_ns",
    "time_ns",
    "utcnow",
    "now",
    "wall_clock",
)

_FORBIDDEN_SCOPE_TOKENS = (
    "live",
    "private_api",
    "credential",
    "credentials",
    "secret",
    "api_key",
    "order",
    "orders",
    "scheduler",
    "auto_loop",
    "connector_ready",
    "shadow",
)

_SAFE_ORDER_MARKET_DATA_TERMS = (
    "limit_order_book",
    "order_book",
    "order_flow",
)

# Exact paper-safety attestation field NAMES whose key text legitimately contains the ``orders`` token.
# The exemption is a *negative* attestation only: it applies solely when the key is an exact full-key
# match AND the associated value is exactly boolean ``False`` (``real_orders_enabled=False`` attests *no*
# real orders; ``real_money_enabled=False`` attests no real money). A ``True`` (or any non-``False``)
# value is NOT exempt and falls through to normal scanning, so an attestation that claims real orders are
# enabled still fails closed on the forbidden ``orders`` token. This is a key-only, value-gated exemption:
# values and every other key are still fully scanned, so ``order``, ``orders``, ``order_router``,
# ``live_order``, ``real_orders_enabled_live``, ``my_real_orders_enabled`` etc. all remain rejected.
_SAFE_ATTESTATION_KEYS = frozenset({"real_orders_enabled", "real_money_enabled"})


class EvidenceJournalError(RuntimeError):
    """Raised when evidence journal input or chain integrity fails closed."""


class EvidenceArtifactType(str, Enum):
    SOURCE_PACKET = "SOURCE_PACKET"
    STRATEGY_VALIDATION_BUNDLE = "STRATEGY_VALIDATION_BUNDLE"
    BACKTEST_ADMISSION_DECISION = "BACKTEST_ADMISSION_DECISION"
    BACKTEST_REPLAY_BRIDGE_RESULT = "BACKTEST_REPLAY_BRIDGE_RESULT"
    REPLAY_EVIDENCE_MANIFEST = "REPLAY_EVIDENCE_MANIFEST"
    PAPER_REPLAY_INTAKE = "PAPER_REPLAY_INTAKE"
    PAPER_REPLAY_RUN_PLAN = "PAPER_REPLAY_RUN_PLAN"
    PAPER_REPLAY_RESULT_REPORT = "PAPER_REPLAY_RESULT_REPORT"
    PAPER_REPLAY_PROMOTION_READINESS = "PAPER_REPLAY_PROMOTION_READINESS"
    PAPER_REPLAY_GOVERNANCE_REVIEW_DECISION = "PAPER_REPLAY_GOVERNANCE_REVIEW_DECISION"
    PAPER_SLEEVE_ADMISSION_REVIEW_READINESS = "PAPER_SLEEVE_ADMISSION_REVIEW_READINESS"


@dataclass(frozen=True)
class EvidenceJournalEntry:
    schema_version: str
    journal_seq: int
    entry_type: EvidenceArtifactType
    payload: Mapping[str, object]
    payload_digest: str
    prev_entry_digest: str | None
    entry_digest: str
    correlation_id: str


@dataclass(frozen=True)
class EvidenceJournalVerification:
    accepted: bool
    entry_count: int
    head_digest: str | None
    rejection_reasons: tuple[str, ...] = ()


class EvidenceJournal:
    """Deterministic append-only evidence journal.

    The token guard is intentionally narrow: it rejects explicit wall-clock,
    BIST, and runtime/live execution markers while allowing market-data terms
    such as ``order_book`` and ``order_flow``.
    """

    def __init__(self) -> None:
        self._entries: list[EvidenceJournalEntry] = []
        self._entries_by_seq: dict[int, EvidenceJournalEntry] = {}
        self._entries_by_entry_digest: dict[str, EvidenceJournalEntry] = {}
        self._entries_by_payload_digest: dict[str, EvidenceJournalEntry] = {}

    @property
    def head_digest(self) -> str | None:
        return self._verify_or_raise().head_digest

    @property
    def entry_count(self) -> int:
        return self._verify_or_raise().entry_count

    def append(
        self,
        entry_type: EvidenceArtifactType | str,
        payload: Mapping[str, object],
        *,
        correlation_id: str,
        payload_digest: str | None = None,
    ) -> EvidenceJournalEntry:
        verified = self._verify_or_raise()
        parsed_entry_type = _parse_entry_type(entry_type)
        normalized_payload = _normalize_payload(payload)
        _reject_scope_tokens(normalized_payload, correlation_id)

        computed_payload_digest = _digest_mapping(normalized_payload)
        if payload_digest is not None and payload_digest != computed_payload_digest:
            raise EvidenceJournalError("evidence_journal:payload_digest_mismatch")
        if computed_payload_digest in self._entries_by_payload_digest:
            raise EvidenceJournalError("evidence_journal:payload_digest_replay")

        if not _is_non_empty_string(correlation_id):
            raise EvidenceJournalError("evidence_journal:correlation_id_missing")

        entry = EvidenceJournalEntry(
            schema_version=_SCHEMA_VERSION,
            journal_seq=verified.entry_count,
            entry_type=parsed_entry_type,
            payload=normalized_payload,
            payload_digest=computed_payload_digest,
            prev_entry_digest=verified.head_digest,
            entry_digest="",
            correlation_id=correlation_id.strip(),
        )
        entry = EvidenceJournalEntry(
            schema_version=entry.schema_version,
            journal_seq=entry.journal_seq,
            entry_type=entry.entry_type,
            payload=entry.payload,
            payload_digest=entry.payload_digest,
            prev_entry_digest=entry.prev_entry_digest,
            entry_digest=evidence_journal_entry_digest(entry),
            correlation_id=entry.correlation_id,
        )
        if entry.entry_digest in self._entries_by_entry_digest:
            raise EvidenceJournalError("evidence_journal:entry_digest_replay")

        self._entries.append(entry)
        self._entries_by_seq[entry.journal_seq] = entry
        self._entries_by_entry_digest[entry.entry_digest] = entry
        self._entries_by_payload_digest[entry.payload_digest] = entry
        return _defensive_entry_copy(entry)

    def get_by_sequence(self, journal_seq: int) -> EvidenceJournalEntry:
        self._verify_or_raise()
        if journal_seq not in self._entries_by_seq:
            raise EvidenceJournalError("evidence_journal:sequence_missing")
        return _defensive_entry_copy(self._entries_by_seq[journal_seq])

    def get_by_entry_digest(self, entry_digest: str) -> EvidenceJournalEntry:
        self._verify_or_raise()
        if entry_digest not in self._entries_by_entry_digest:
            raise EvidenceJournalError("evidence_journal:entry_digest_missing")
        return _defensive_entry_copy(self._entries_by_entry_digest[entry_digest])

    def get_by_payload_digest(self, payload_digest: str) -> EvidenceJournalEntry:
        self._verify_or_raise()
        if payload_digest not in self._entries_by_payload_digest:
            raise EvidenceJournalError("evidence_journal:payload_digest_missing")
        return _defensive_entry_copy(self._entries_by_payload_digest[payload_digest])

    def snapshot(self) -> tuple[EvidenceJournalEntry, ...]:
        self._verify_or_raise()
        return tuple(_defensive_entry_copy(entry) for entry in self._entries)

    def verify_chain(self) -> EvidenceJournalVerification:
        rejection_reasons: list[str] = []
        seen_sequences: set[int] = set()
        seen_entry_digests: set[str] = set()
        seen_payload_digests: set[str] = set()
        previous_digest: str | None = None

        for expected_seq, entry in enumerate(self._entries):
            if not isinstance(entry, EvidenceJournalEntry):
                rejection_reasons.append("evidence_journal:entry_malformed")
                continue
            if entry.journal_seq != expected_seq:
                rejection_reasons.append("evidence_journal:sequence_discontinuity")
            if entry.journal_seq in seen_sequences:
                rejection_reasons.append("evidence_journal:sequence_duplicate")
            seen_sequences.add(entry.journal_seq)

            entry_rejections = _validate_entry(entry)
            rejection_reasons.extend(entry_rejections)

            if expected_seq == 0 and entry.prev_entry_digest is not None:
                rejection_reasons.append("evidence_journal:genesis_prev_digest_present")
            if expected_seq > 0 and entry.prev_entry_digest is None:
                rejection_reasons.append("evidence_journal:second_genesis")
            if entry.prev_entry_digest != previous_digest:
                rejection_reasons.append("evidence_journal:prev_entry_digest_mismatch")

            if entry.entry_digest in seen_entry_digests:
                rejection_reasons.append("evidence_journal:entry_digest_replay")
            seen_entry_digests.add(entry.entry_digest)
            if entry.payload_digest in seen_payload_digests:
                rejection_reasons.append("evidence_journal:payload_digest_replay")
            seen_payload_digests.add(entry.payload_digest)

            previous_digest = entry.entry_digest

        index_rejections = self._validate_indexes()
        rejection_reasons.extend(index_rejections)

        stable_rejections = _stable_unique(rejection_reasons)
        return EvidenceJournalVerification(
            accepted=not stable_rejections,
            entry_count=len(self._entries),
            head_digest=previous_digest,
            rejection_reasons=stable_rejections,
        )

    def _verify_or_raise(self) -> EvidenceJournalVerification:
        verification = self.verify_chain()
        if not verification.accepted:
            raise EvidenceJournalError(";".join(verification.rejection_reasons))
        return verification

    def _validate_indexes(self) -> tuple[str, ...]:
        by_seq = {entry.journal_seq: entry for entry in self._entries if isinstance(entry, EvidenceJournalEntry)}
        by_entry_digest = {
            entry.entry_digest: entry for entry in self._entries if isinstance(entry, EvidenceJournalEntry)
        }
        by_payload_digest = {
            entry.payload_digest: entry for entry in self._entries if isinstance(entry, EvidenceJournalEntry)
        }
        rejection_reasons: list[str] = []
        if by_seq != self._entries_by_seq:
            rejection_reasons.append("evidence_journal:sequence_index_mismatch")
        if by_entry_digest != self._entries_by_entry_digest:
            rejection_reasons.append("evidence_journal:entry_digest_index_mismatch")
        if by_payload_digest != self._entries_by_payload_digest:
            rejection_reasons.append("evidence_journal:payload_digest_index_mismatch")
        return tuple(rejection_reasons)


def evidence_journal_entry_to_dict(entry: EvidenceJournalEntry) -> dict[str, Any]:
    return {
        "schema_version": entry.schema_version,
        "journal_seq": entry.journal_seq,
        "entry_type": _enum_value(entry.entry_type),
        "payload": _normalize_payload(entry.payload),
        "payload_digest": entry.payload_digest,
        "prev_entry_digest": entry.prev_entry_digest,
        "entry_digest": entry.entry_digest,
        "correlation_id": entry.correlation_id,
    }


def evidence_journal_to_dict(journal: EvidenceJournal) -> dict[str, object]:
    if not isinstance(journal, EvidenceJournal):
        raise EvidenceJournalError("evidence_journal:journal_malformed")
    return {
        "schema_version": _JOURNAL_EXPORT_SCHEMA_VERSION,
        "entry_count": journal.entry_count,
        "head_digest": journal.head_digest,
        "entries": [evidence_journal_entry_to_dict(entry) for entry in journal.snapshot()],
    }


def evidence_journal_from_dict(
    data: Mapping[str, object],
    *,
    expected_entry_count: int,
    expected_head_digest: str | None,
) -> EvidenceJournal:
    """Load a journal only when trusted external count/head anchors match.

    The expected values must come from a trusted external anchor, not from the
    same untrusted envelope being imported.
    """
    if not isinstance(expected_entry_count, int) or isinstance(expected_entry_count, bool) or expected_entry_count < 0:
        raise EvidenceJournalError("evidence_journal:expected_entry_count_malformed")
    if expected_head_digest is not None and not isinstance(expected_head_digest, str):
        raise EvidenceJournalError("evidence_journal:expected_head_digest_malformed")

    envelope = _require_mapping(data, "evidence_journal:envelope_malformed")
    _require_exact_fields(envelope, _JOURNAL_ENVELOPE_FIELDS, "evidence_journal:envelope_fields_mismatch")

    if envelope["schema_version"] != _JOURNAL_EXPORT_SCHEMA_VERSION:
        raise EvidenceJournalError("evidence_journal:envelope_schema_version_mismatch")

    entry_count = envelope["entry_count"]
    if not isinstance(entry_count, int) or isinstance(entry_count, bool) or entry_count < 0:
        raise EvidenceJournalError("evidence_journal:envelope_entry_count_malformed")

    head_digest = envelope["head_digest"]
    if head_digest is not None and not isinstance(head_digest, str):
        raise EvidenceJournalError("evidence_journal:envelope_head_digest_malformed")

    entries = envelope["entries"]
    if not isinstance(entries, list):
        raise EvidenceJournalError("evidence_journal:envelope_entries_malformed")

    journal = EvidenceJournal()
    for entry_data in entries:
        stored_entry = _entry_from_export_dict(entry_data)
        rebuilt_entry = journal.append(
            stored_entry.entry_type,
            stored_entry.payload,
            correlation_id=stored_entry.correlation_id,
        )
        _reject_rebuilt_entry_mismatch(rebuilt_entry, stored_entry)

    verification = journal.verify_chain()
    _reject_import_anchor_mismatch(
        verification,
        envelope_entry_count=entry_count,
        envelope_head_digest=head_digest,
        expected_entry_count=expected_entry_count,
        expected_head_digest=expected_head_digest,
    )
    return journal


def evidence_journal_entry_digest(entry: EvidenceJournalEntry) -> str:
    payload = evidence_journal_entry_to_dict(entry)
    payload.pop("entry_digest", None)
    return _digest_mapping(payload)


def _defensive_entry_copy(entry: EvidenceJournalEntry) -> EvidenceJournalEntry:
    return EvidenceJournalEntry(
        schema_version=entry.schema_version,
        journal_seq=entry.journal_seq,
        entry_type=entry.entry_type,
        payload=_normalize_payload(entry.payload),
        payload_digest=entry.payload_digest,
        prev_entry_digest=entry.prev_entry_digest,
        entry_digest=entry.entry_digest,
        correlation_id=entry.correlation_id,
    )


def _entry_from_export_dict(data: object) -> EvidenceJournalEntry:
    entry = _require_mapping(data, "evidence_journal:entry_malformed")
    _require_exact_fields(entry, _ENTRY_EXPORT_FIELDS, "evidence_journal:entry_fields_mismatch")

    schema_version = entry["schema_version"]
    if not isinstance(schema_version, str):
        raise EvidenceJournalError("evidence_journal:schema_version_malformed")

    journal_seq = entry["journal_seq"]
    if not isinstance(journal_seq, int) or isinstance(journal_seq, bool) or journal_seq < 0:
        raise EvidenceJournalError("evidence_journal:sequence_malformed")

    payload_digest = entry["payload_digest"]
    if not isinstance(payload_digest, str):
        raise EvidenceJournalError("evidence_journal:payload_digest_malformed")

    prev_entry_digest = entry["prev_entry_digest"]
    if prev_entry_digest is not None and not isinstance(prev_entry_digest, str):
        raise EvidenceJournalError("evidence_journal:prev_entry_digest_malformed")

    entry_digest = entry["entry_digest"]
    if not isinstance(entry_digest, str):
        raise EvidenceJournalError("evidence_journal:entry_digest_malformed")

    correlation_id = entry["correlation_id"]
    if not _is_non_empty_string(correlation_id):
        raise EvidenceJournalError("evidence_journal:correlation_id_missing")

    return EvidenceJournalEntry(
        schema_version=schema_version,
        journal_seq=journal_seq,
        entry_type=_parse_entry_type(entry["entry_type"]),
        payload=_normalize_payload(entry["payload"]),
        payload_digest=payload_digest,
        prev_entry_digest=prev_entry_digest,
        entry_digest=entry_digest,
        correlation_id=correlation_id,
    )


def _reject_rebuilt_entry_mismatch(rebuilt_entry: EvidenceJournalEntry, stored_entry: EvidenceJournalEntry) -> None:
    if rebuilt_entry.schema_version != stored_entry.schema_version:
        raise EvidenceJournalError("evidence_journal:stored_schema_version_mismatch")
    if rebuilt_entry.journal_seq != stored_entry.journal_seq:
        raise EvidenceJournalError("evidence_journal:stored_sequence_mismatch")
    if rebuilt_entry.entry_type != stored_entry.entry_type:
        raise EvidenceJournalError("evidence_journal:stored_entry_type_mismatch")
    if _normalize_payload(rebuilt_entry.payload) != _normalize_payload(stored_entry.payload):
        raise EvidenceJournalError("evidence_journal:stored_payload_mismatch")
    if rebuilt_entry.payload_digest != stored_entry.payload_digest:
        raise EvidenceJournalError("evidence_journal:stored_payload_digest_mismatch")
    if rebuilt_entry.prev_entry_digest != stored_entry.prev_entry_digest:
        raise EvidenceJournalError("evidence_journal:stored_prev_entry_digest_mismatch")
    if rebuilt_entry.entry_digest != stored_entry.entry_digest:
        raise EvidenceJournalError("evidence_journal:stored_entry_digest_mismatch")
    if rebuilt_entry.correlation_id != stored_entry.correlation_id:
        raise EvidenceJournalError("evidence_journal:stored_correlation_id_mismatch")


def _reject_import_anchor_mismatch(
    verification: EvidenceJournalVerification,
    *,
    envelope_entry_count: int,
    envelope_head_digest: str | None,
    expected_entry_count: int,
    expected_head_digest: str | None,
) -> None:
    if not verification.accepted:
        raise EvidenceJournalError(";".join(verification.rejection_reasons))
    if verification.entry_count != envelope_entry_count:
        raise EvidenceJournalError("evidence_journal:envelope_entry_count_mismatch")
    if verification.head_digest != envelope_head_digest:
        raise EvidenceJournalError("evidence_journal:envelope_head_digest_mismatch")
    if verification.entry_count != expected_entry_count:
        raise EvidenceJournalError("evidence_journal:expected_entry_count_mismatch")
    if verification.head_digest != expected_head_digest:
        raise EvidenceJournalError("evidence_journal:expected_head_digest_mismatch")


def _validate_entry(entry: EvidenceJournalEntry) -> tuple[str, ...]:
    rejection_reasons: list[str] = []
    if entry.schema_version != _SCHEMA_VERSION:
        rejection_reasons.append("evidence_journal:schema_version_mismatch")
    if not isinstance(entry.journal_seq, int) or isinstance(entry.journal_seq, bool) or entry.journal_seq < 0:
        rejection_reasons.append("evidence_journal:sequence_malformed")
    if not isinstance(entry.entry_type, EvidenceArtifactType):
        rejection_reasons.append("evidence_journal:entry_type_malformed")
    if not _is_non_empty_string(entry.correlation_id):
        rejection_reasons.append("evidence_journal:correlation_id_missing")
    try:
        normalized_payload = _normalize_payload(entry.payload)
        _reject_scope_tokens(normalized_payload, entry.correlation_id)
        if entry.payload_digest != _digest_mapping(normalized_payload):
            rejection_reasons.append("evidence_journal:payload_digest_mismatch")
        if entry.entry_digest != evidence_journal_entry_digest(entry):
            rejection_reasons.append("evidence_journal:entry_digest_mismatch")
    except EvidenceJournalError as exc:
        rejection_reasons.append(str(exc))
    return _stable_unique(rejection_reasons)


def _parse_entry_type(entry_type: EvidenceArtifactType | str) -> EvidenceArtifactType:
    if isinstance(entry_type, EvidenceArtifactType):
        return entry_type
    if isinstance(entry_type, str):
        try:
            return EvidenceArtifactType(entry_type)
        except ValueError as exc:
            raise EvidenceJournalError("evidence_journal:entry_type_unknown") from exc
    raise EvidenceJournalError("evidence_journal:entry_type_malformed")


def _normalize_payload(payload: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise EvidenceJournalError("evidence_journal:payload_malformed")
    _validate_json_value(payload)
    return json.loads(_canonical_json(payload))


def _require_mapping(value: object, reason: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvidenceJournalError(reason)
    return value


def _require_exact_fields(mapping: Mapping[str, object], expected_fields: frozenset[str], reason: str) -> None:
    keys = tuple(mapping.keys())
    if any(not isinstance(key, str) for key in keys) or set(keys) != expected_fields:
        raise EvidenceJournalError(reason)


def _validate_json_value(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceJournalError("evidence_journal:payload_key_malformed")
            _validate_json_value(item)
        return
    if isinstance(value, list | tuple):
        for item in value:
            _validate_json_value(item)
        return
    if value is None or isinstance(value, str | bool | int | float):
        return
    raise EvidenceJournalError("evidence_journal:payload_value_malformed")


def _canonical_json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceJournalError("evidence_journal:payload_not_canonical_json") from exc


def _digest_mapping(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _is_negative_attestation_item(key: object, value: object) -> bool:
    # ``value is False`` is a strict identity check: only the boolean ``False`` qualifies, so ``0``,
    # ``"false"``, ``None`` and ``True`` are all non-exempt and remain subject to forbidden-token scanning.
    return isinstance(key, str) and key in _SAFE_ATTESTATION_KEYS and value is False


def _reject_scope_tokens(payload: Mapping[str, Any], correlation_id: str) -> None:
    rejection_reasons = list(_scope_token_rejections(correlation_id))

    def _walk(node: object) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if not _is_negative_attestation_item(key, value):
                    rejection_reasons.extend(_scope_token_rejections(key))
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, str):
            rejection_reasons.extend(_scope_token_rejections(node))

    _walk(payload)
    stable_rejections = _stable_unique(rejection_reasons)
    if stable_rejections:
        raise EvidenceJournalError(";".join(stable_rejections))


def _scope_token_rejections(text: object) -> tuple[str, ...]:
    if not isinstance(text, str):
        return ()
    lowered = text.lower()
    tokens = _identifier_tokens(lowered)
    rejection_reasons: list[str] = []

    if "bist" in lowered:
        rejection_reasons.append("evidence_journal:bist_scope_leakage")

    for marker in _WALL_CLOCK_TOKENS:
        if _text_matches_marker(lowered, tokens, marker):
            rejection_reasons.append(f"evidence_journal:wall_clock_token_{marker}")

    for marker in _FORBIDDEN_SCOPE_TOKENS:
        if marker in {"order", "orders"}:
            if _contains_forbidden_order_marker(tokens):
                rejection_reasons.append(f"evidence_journal:forbidden_token_{marker}")
            continue
        if marker in {"private_api", "api_key", "auto_loop", "connector_ready"}:
            if _text_matches_marker(lowered, tokens, marker):
                rejection_reasons.append(f"evidence_journal:forbidden_token_{marker}")
            continue
        if marker == "credential":
            if "credential" in tokens or "credentials" in tokens:
                rejection_reasons.append("evidence_journal:forbidden_token_credential")
            continue
        if _text_matches_marker(lowered, tokens, marker):
            rejection_reasons.append(f"evidence_journal:forbidden_token_{marker}")
    return _stable_unique(rejection_reasons)


def _text_matches_marker(lowered: str, tokens: tuple[str, ...], marker: str) -> bool:
    if "_" in marker:
        return marker in lowered or _contains_token_sequence(tokens, tuple(marker.split("_")))
    return lowered == marker or marker in tokens


def _contains_forbidden_order_marker(tokens: tuple[str, ...]) -> bool:
    covered_indexes: set[int] = set()
    for safe_term in _SAFE_ORDER_MARKET_DATA_TERMS:
        safe_tokens = tuple(safe_term.split("_"))
        for start_index in _token_sequence_start_indexes(tokens, safe_tokens):
            covered_indexes.update(range(start_index, start_index + len(safe_tokens)))
    return any(token in {"order", "orders"} and index not in covered_indexes for index, token in enumerate(tokens))


def _contains_token_sequence(tokens: tuple[str, ...], sequence: tuple[str, ...]) -> bool:
    return bool(_token_sequence_start_indexes(tokens, sequence))


def _token_sequence_start_indexes(tokens: tuple[str, ...], sequence: tuple[str, ...]) -> tuple[int, ...]:
    if not sequence or len(sequence) > len(tokens):
        return ()
    starts: list[int] = []
    last_start = len(tokens) - len(sequence)
    for start_index in range(last_start + 1):
        if tokens[start_index : start_index + len(sequence)] == sequence:
            starts.append(start_index)
    return tuple(starts)


def _identifier_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    token_chars: list[str] = []
    for char in text:
        if char.isalnum():
            token_chars.append(char)
            continue
        if token_chars:
            tokens.append("".join(token_chars))
            token_chars = []
    if token_chars:
        tokens.append("".join(token_chars))
    return tuple(tokens)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _enum_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    return value


def _stable_unique(reasons: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


__all__ = [
    "EvidenceArtifactType",
    "EvidenceJournal",
    "EvidenceJournalEntry",
    "EvidenceJournalError",
    "EvidenceJournalVerification",
    "evidence_journal_from_dict",
    "evidence_journal_entry_digest",
    "evidence_journal_entry_to_dict",
    "evidence_journal_to_dict",
]
