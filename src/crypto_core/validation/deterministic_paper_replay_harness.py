"""Deterministic paper replay harness — deterministic, paper-only, fail-closed proof that a paper chain
replays digest-identically at its highest merged public-contract boundary.

Phase-map slice 6 (``docs/crypto_core/paper_trading_phase_map.md`` §7.6): *replay the same paper run and
prove digest equality (discrepancy = fail-closed).* This harness is a **validation / audit artifact /
probe**, NOT a replay engine: it runs no backtest, re-runs no strategy/governor, simulates no fills, mutates
no positions, computes no economics, schedules nothing, and adds no runtime/persistence/venue path. It answers
one question: "are an ORIGINAL and a REPLAY ``PaperGovernorDecision`` digest-identical at every relevant public
contract boundary?"

It consumes the highest merged paper-chain artifact — ``PaperGovernorDecision`` — for both the original and the
replay run. That single artifact transitively binds the whole chain by value: the ledger-bridge digest (§7.4),
the episode digest (§7.3), the admitted manifest / realized-PnL-event digests, the policy digest, the gross
paper totals (realized PnL, closed units, computed/​source-event counts), the governance verdict, and the full
paper-safety / non-overclaim attestations — all serialized into the decision's own self-digest. The harness
re-proves EACH consumed decision's self-digest via the PUBLIC ``paper_governor_decision_digest`` (stored digest
must equal the recompute AND the caller's independent expected anchor), confirms each is a TRUSTED, DECIDED,
paper-safe, lineage-proven decision whose ids match the caller, and only THEN compares the original vs replay
digests at each embedded boundary. Because every embedded boundary value is itself bound into the re-proven
decision digest, a tampered embedded field cannot pass the self-digest re-proof — so the boundary comparison is
tamper-evident, not a bare stored-string trust.

Outcome (fail-closed):
  - ``REJECTED`` — a consumed decision is untrusted: digest re-proof fails, schema/status not DECIDED, an unsafe
    or over-claiming flag, missing lineage, malformed count, or an id that does not match the caller anchor. No
    partial match under untrusted input.
  - ``MISMATCHED`` — both decisions are individually trusted but differ at ≥1 boundary (the replay was NOT
    digest-identical). This is the core replay-discrepancy signal.
  - ``MATCHED`` — both trusted AND every compared boundary is exactly equal (``matched`` / ``ready`` True).

Non-overclaim: a MATCHED replay proves only deterministic paper-replay equality for the two supplied artifacts.
It is NOT PRDV4 Stage 4 completion, NOT live readiness, NOT shadow readiness, NOT a profitability/edge proof,
and NOT production execution; it reserves NO real capital — all carried as explicit ``False`` flags, digest-bound.
It does NOT import or use ``crypto_core.service.readiness`` or ``crypto_core.execution.paper_adapter`` (or any
shadow/live/runtime/venue surface), no Deribit, no BIST. Deterministic and immutable; no wall-clock/random/IO.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_governor_decision import (
    PaperGovernorDecision,
    PaperGovernorDecisionStatus,
    PaperGovernorVerdict,
    paper_governor_decision_digest,
)

_SCHEMA_VERSION = "deterministic-paper-replay-harness.v1"
_EXPECTED_DECISION_SCHEMA_VERSION = "paper-governor-decision.v1"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Scope guard mirrors the sibling validation modules (word-bounded). Market-data terms scrubbed first.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")

# The public contract boundaries compared between the original and replay decisions (deterministic, static).
_COMPARED_BOUNDARIES: tuple[str, ...] = (
    "decision_digest",
    "ledger_bridge_digest",
    "expected_ledger_bridge_digest",
    "policy_digest",
    "policy_id",
    "episode_digest",
    "manifest_digest",
    "realized_pnl_event_digest",
    "realized_pnl_total",
    "closed_units_total",
    "computed_event_count",
    "source_event_digest_count",
    "ledger_bridge_status",
    "market_symbol",
    "decision_status",
    "verdict",
    "allowed",
)


class DeterministicPaperReplayHarnessError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed decisions / ids / digests / metadata)."""


class DeterministicPaperReplayHarnessStatus(str, Enum):
    """Terminal replay-harness verdict. Never an execution / capital / live / readiness action."""

    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class DeterministicPaperReplayHarnessResult:
    """Deterministic, immutable, digest-bound result of comparing an original vs replay paper governor decision.

    ``status`` is MATCHED only when both decisions re-prove their self-digests, are TRUSTED/DECIDED/paper-safe
    /lineage-proven with caller-matching ids, AND every compared public boundary is exactly equal; MISMATCHED
    when both are trusted but a boundary differs; REJECTED when a consumed decision is untrusted. ``matched`` /
    ``ready`` True only for MATCHED. ``paper_only`` True; every safety / non-overclaim attestation False. PAPER
    ONLY — NOT PRDV4 Stage 4 completion, NOT live/shadow readiness, NOT profitability/edge proof.
    """

    schema_version: str
    status: DeterministicPaperReplayHarnessStatus
    matched: bool
    ready: bool
    run_id: str
    episode_id: str
    correlation_id: str
    market_symbol: str
    expected_original_digest: str
    expected_replay_digest: str
    original_decision_digest: str
    replay_decision_digest: str
    original_decision_status: str
    replay_decision_status: str
    original_verdict: str
    replay_verdict: str
    original_ledger_bridge_digest: str
    replay_ledger_bridge_digest: str
    original_policy_digest: str
    replay_policy_digest: str
    original_episode_digest: str
    replay_episode_digest: str
    original_manifest_digest: str
    replay_manifest_digest: str
    original_realized_pnl_event_digest: str
    replay_realized_pnl_event_digest: str
    original_realized_pnl_total: str
    replay_realized_pnl_total: str
    original_closed_units_total: str
    replay_closed_units_total: str
    original_computed_event_count: int
    replay_computed_event_count: int
    original_source_event_digest_count: int
    replay_source_event_digest_count: int
    compared_boundaries: tuple[str, ...]
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    replay_result_digest: str
    paper_only: bool = True
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    order_routed: bool = False
    execution_authorized: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _plain_str_or_empty(value: object) -> str:
    """Return ``value`` only if it is an exact plain ``str`` (no subclass); else ``""`` (fail-closed)."""
    return value if type(value) is str else ""


def _int_or_none(value: object) -> int | None:
    return value if _is_int(value) else None


def _bool_or_none(value: object) -> bool | None:
    return value if type(value) is bool else None


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise DeterministicPaperReplayHarnessError("deterministic_paper_replay_harness:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise DeterministicPaperReplayHarnessError("deterministic_paper_replay_harness:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise DeterministicPaperReplayHarnessError("deterministic_paper_replay_harness:metadata_malformed")
        pairs.append([pair[0], pair[1]])
    return pairs


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _decision_is_paper_safe(decision: PaperGovernorDecision) -> bool:
    return (
        decision.paper_only is True
        and decision.real_orders_enabled is False
        and decision.real_money_enabled is False
        and decision.real_capital_reserved is False
        and decision.order_routed is False
        and decision.execution_authorized is False
        and decision.live_api_called is False
        and decision.scheduler_enabled is False
        and decision.auto_loop_enabled is False
        and decision.connector_invoked is False
        and decision.prdv4_stage4_complete is False
        and decision.live_ready is False
        and decision.shadow_ready is False
        and decision.profitability_proven is False
        and decision.edge_proven is False
        and decision.production_execution is False
    )


def _decision_status_value(decision: PaperGovernorDecision) -> str:
    return decision.status.value if isinstance(decision.status, PaperGovernorDecisionStatus) else ""


def _verdict_value(decision: PaperGovernorDecision) -> str:
    return decision.decision.value if isinstance(decision.decision, PaperGovernorVerdict) else ""


def _reprove_decision_trust(
    decision: PaperGovernorDecision,
    expected_digest: str,
    *,
    side: str,
    run_id: str,
    episode_id: str,
    correlation_id: str,
) -> list[str]:
    """Re-prove one consumed decision is a TRUSTED input. Returns fail-closed reason codes (empty == trusted).

    The self-digest is re-proven via the PUBLIC ``paper_governor_decision_digest`` and must equal the stored
    digest AND the caller's independent ``expected_digest``; the decision must be DECIDED + paper-safe +
    lineage-proven (``source_event_digest_count`` >= 1) with a well-formed count and ids matching the caller
    anchors. A serializer that raises is ``<side>_decision_malformed``; a digest mismatch (or equality-liar /
    subclass digest, caught by the exact ``type(x) is str`` hex check) is ``<side>_decision_digest_mismatch``.
    """
    hard: list[str] = []
    try:
        recomputed = paper_governor_decision_digest(decision)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        recomputed = None
    stored = decision.decision_digest
    if recomputed is None:
        hard.append(f"deterministic_paper_replay_harness:{side}_decision_malformed")
    elif not _is_hex64_string(stored) or stored != recomputed or stored != expected_digest:
        hard.append(f"deterministic_paper_replay_harness:{side}_decision_digest_mismatch")
    if decision.schema_version != _EXPECTED_DECISION_SCHEMA_VERSION:
        hard.append(f"deterministic_paper_replay_harness:{side}_decision_schema_invalid")
    if not (
        isinstance(decision.status, PaperGovernorDecisionStatus)
        and decision.status is PaperGovernorDecisionStatus.DECIDED
        and decision.decided is True
    ):
        hard.append(f"deterministic_paper_replay_harness:{side}_decision_not_decided")
    if not _decision_is_paper_safe(decision):
        hard.append(f"deterministic_paper_replay_harness:{side}_decision_unsafe_flags")
    if not _is_int(decision.source_event_digest_count) or decision.source_event_digest_count < 1:
        hard.append(f"deterministic_paper_replay_harness:{side}_decision_lineage_unproven")
    if not _is_int(decision.computed_event_count) or decision.computed_event_count < 0:
        hard.append(f"deterministic_paper_replay_harness:{side}_decision_count_malformed")
    if _plain_str_or_empty(decision.run_id) != run_id:
        hard.append(f"deterministic_paper_replay_harness:{side}_run_id_mismatch")
    if _plain_str_or_empty(decision.episode_id) != episode_id:
        hard.append(f"deterministic_paper_replay_harness:{side}_episode_id_mismatch")
    if _plain_str_or_empty(decision.correlation_id) != correlation_id:
        hard.append(f"deterministic_paper_replay_harness:{side}_correlation_id_mismatch")
    return hard


def _boundary_mismatches(original: PaperGovernorDecision, replay: PaperGovernorDecision) -> list[str]:
    """Compare every public boundary between two TRUSTED decisions. Returns mismatch reason codes (empty == equal).

    String boundaries are normalized via ``_plain_str_or_empty`` (a ``str`` subclass / equality-liar normalizes
    to ``""`` and therefore cannot mask a real difference); counts/bools compare exact plain values.
    """
    mismatch: list[str] = []
    string_boundaries: tuple[tuple[str, object, object], ...] = (
        ("decision_digest", original.decision_digest, replay.decision_digest),
        ("ledger_bridge_digest", original.ledger_bridge_digest, replay.ledger_bridge_digest),
        ("expected_ledger_bridge_digest", original.expected_ledger_bridge_digest, replay.expected_ledger_bridge_digest),
        ("policy_digest", original.policy_digest, replay.policy_digest),
        ("policy_id", original.policy_id, replay.policy_id),
        ("episode_digest", original.episode_digest, replay.episode_digest),
        ("manifest_digest", original.manifest_digest, replay.manifest_digest),
        ("realized_pnl_event_digest", original.realized_pnl_event_digest, replay.realized_pnl_event_digest),
        ("realized_pnl_total", original.realized_pnl_total, replay.realized_pnl_total),
        ("closed_units_total", original.closed_units_total, replay.closed_units_total),
        ("ledger_bridge_status", original.ledger_bridge_status, replay.ledger_bridge_status),
        ("market_symbol", original.market_symbol, replay.market_symbol),
        ("decision_status", _decision_status_value(original), _decision_status_value(replay)),
        ("verdict", _verdict_value(original), _verdict_value(replay)),
    )
    for name, original_value, replay_value in string_boundaries:
        if _plain_str_or_empty(original_value) != _plain_str_or_empty(replay_value):
            mismatch.append(f"deterministic_paper_replay_harness:{name}_mismatch")
    int_boundaries: tuple[tuple[str, object, object], ...] = (
        ("computed_event_count", original.computed_event_count, replay.computed_event_count),
        ("source_event_digest_count", original.source_event_digest_count, replay.source_event_digest_count),
    )
    for name, original_value, replay_value in int_boundaries:
        if _int_or_none(original_value) != _int_or_none(replay_value):
            mismatch.append(f"deterministic_paper_replay_harness:{name}_mismatch")
    if _bool_or_none(original.allowed) != _bool_or_none(replay.allowed):
        mismatch.append("deterministic_paper_replay_harness:allowed_mismatch")
    return mismatch


def verify_deterministic_paper_replay(
    original: PaperGovernorDecision,
    replay: PaperGovernorDecision,
    *,
    expected_original_digest: str,
    expected_replay_digest: str,
    run_id: str,
    episode_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> DeterministicPaperReplayHarnessResult:
    """Prove an ``original`` and ``replay`` ``PaperGovernorDecision`` are digest-identical at every public boundary.

    Both ``original`` and ``replay`` must be ``PaperGovernorDecision``; ``expected_original_digest`` /
    ``expected_replay_digest`` exact plain 64-lowercase-hex ``str`` (the caller's INDEPENDENT anchors for each
    side's ``decision_digest``); ``run_id`` / ``episode_id`` / ``correlation_id`` exact plain non-empty ``str``
    (both decisions must carry these exact ids); ``metadata`` ``Mapping[str, str]`` or ``None``. A wrong type,
    malformed digest, empty id, a forbidden BIST/live/order token, or malformed metadata raises
    ``DeterministicPaperReplayHarnessError`` before any work.

    Each consumed decision's self-digest is re-proven via ``paper_governor_decision_digest`` (== stored ==
    expected anchor) and must be DECIDED + paper-safe + lineage-proven with caller-matching ids; any untrusted
    decision maps to ``status=REJECTED`` (no partial match). Only when BOTH are trusted are the original vs
    replay digests compared at every embedded boundary: ``status=MATCHED`` (``matched`` / ``ready`` True) when
    all match, else ``status=MISMATCHED`` with stable per-boundary reason codes. Deterministic and immutable;
    no wall-clock/random/IO; paper only; reserves NO real capital; the inputs are never mutated.
    """
    if not isinstance(original, PaperGovernorDecision):
        raise DeterministicPaperReplayHarnessError("deterministic_paper_replay_harness:original_malformed")
    if not isinstance(replay, PaperGovernorDecision):
        raise DeterministicPaperReplayHarnessError("deterministic_paper_replay_harness:replay_malformed")
    if not _is_hex64_string(expected_original_digest):
        raise DeterministicPaperReplayHarnessError(
            "deterministic_paper_replay_harness:expected_original_digest_invalid"
        )
    if not _is_hex64_string(expected_replay_digest):
        raise DeterministicPaperReplayHarnessError("deterministic_paper_replay_harness:expected_replay_digest_invalid")
    for name, value in (("episode_id", episode_id), ("run_id", run_id), ("correlation_id", correlation_id)):
        if not _is_plain_non_empty_string(value):
            raise DeterministicPaperReplayHarnessError(f"deterministic_paper_replay_harness:{name}_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(episode_id, run_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise DeterministicPaperReplayHarnessError("deterministic_paper_replay_harness:scope_violation")

    hard: list[str] = []
    hard.extend(
        _reprove_decision_trust(
            original,
            expected_original_digest,
            side="original",
            run_id=run_id,
            episode_id=episode_id,
            correlation_id=correlation_id,
        )
    )
    hard.extend(
        _reprove_decision_trust(
            replay,
            expected_replay_digest,
            side="replay",
            run_id=run_id,
            episode_id=episode_id,
            correlation_id=correlation_id,
        )
    )

    if hard:
        status = DeterministicPaperReplayHarnessStatus.REJECTED
        reason_codes = tuple(sorted(set(hard)))
    else:
        mismatch = _boundary_mismatches(original, replay)
        if mismatch:
            status = DeterministicPaperReplayHarnessStatus.MISMATCHED
            reason_codes = tuple(sorted(set(mismatch)))
        else:
            status = DeterministicPaperReplayHarnessStatus.MATCHED
            reason_codes = ()

    return _finalize_result(
        status=status,
        original=original,
        replay=replay,
        expected_original_digest=expected_original_digest,
        expected_replay_digest=expected_replay_digest,
        run_id=run_id,
        episode_id=episode_id,
        correlation_id=correlation_id,
        reason_codes=reason_codes,
        metadata=metadata_pairs,
    )


def _finalize_result(
    *,
    status: DeterministicPaperReplayHarnessStatus,
    original: PaperGovernorDecision,
    replay: PaperGovernorDecision,
    expected_original_digest: str,
    expected_replay_digest: str,
    run_id: str,
    episode_id: str,
    correlation_id: str,
    reason_codes: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> DeterministicPaperReplayHarnessResult:
    matched = status is DeterministicPaperReplayHarnessStatus.MATCHED
    # ``market_symbol`` is reported only when both sides agree (a divergence is surfaced via the boundary reason).
    original_symbol = _plain_str_or_empty(original.market_symbol)
    replay_symbol = _plain_str_or_empty(replay.market_symbol)
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "matched": matched,
        "ready": matched,
        "run_id": run_id,
        "episode_id": episode_id,
        "correlation_id": correlation_id,
        "market_symbol": original_symbol if original_symbol == replay_symbol else "",
        "expected_original_digest": expected_original_digest,
        "expected_replay_digest": expected_replay_digest,
        "original_decision_digest": _plain_str_or_empty(original.decision_digest),
        "replay_decision_digest": _plain_str_or_empty(replay.decision_digest),
        "original_decision_status": _decision_status_value(original),
        "replay_decision_status": _decision_status_value(replay),
        "original_verdict": _verdict_value(original),
        "replay_verdict": _verdict_value(replay),
        "original_ledger_bridge_digest": _plain_str_or_empty(original.ledger_bridge_digest),
        "replay_ledger_bridge_digest": _plain_str_or_empty(replay.ledger_bridge_digest),
        "original_policy_digest": _plain_str_or_empty(original.policy_digest),
        "replay_policy_digest": _plain_str_or_empty(replay.policy_digest),
        "original_episode_digest": _plain_str_or_empty(original.episode_digest),
        "replay_episode_digest": _plain_str_or_empty(replay.episode_digest),
        "original_manifest_digest": _plain_str_or_empty(original.manifest_digest),
        "replay_manifest_digest": _plain_str_or_empty(replay.manifest_digest),
        "original_realized_pnl_event_digest": _plain_str_or_empty(original.realized_pnl_event_digest),
        "replay_realized_pnl_event_digest": _plain_str_or_empty(replay.realized_pnl_event_digest),
        "original_realized_pnl_total": _plain_str_or_empty(original.realized_pnl_total),
        "replay_realized_pnl_total": _plain_str_or_empty(replay.realized_pnl_total),
        "original_closed_units_total": _plain_str_or_empty(original.closed_units_total),
        "replay_closed_units_total": _plain_str_or_empty(replay.closed_units_total),
        "original_computed_event_count": original.computed_event_count if _is_int(original.computed_event_count) else 0,
        "replay_computed_event_count": replay.computed_event_count if _is_int(replay.computed_event_count) else 0,
        "original_source_event_digest_count": original.source_event_digest_count
        if _is_int(original.source_event_digest_count)
        else 0,
        "replay_source_event_digest_count": replay.source_event_digest_count
        if _is_int(replay.source_event_digest_count)
        else 0,
        "compared_boundaries": _COMPARED_BOUNDARIES,
        "reason_codes": reason_codes,
        "metadata": metadata,
    }
    seed = DeterministicPaperReplayHarnessResult(replay_result_digest="", **fields)  # type: ignore[arg-type]
    return _replace_result_digest(seed, deterministic_paper_replay_harness_result_digest(seed))


def _replace_result_digest(
    result: DeterministicPaperReplayHarnessResult, digest: str
) -> DeterministicPaperReplayHarnessResult:
    fields = _result_fields(result)
    fields["replay_result_digest"] = digest
    return DeterministicPaperReplayHarnessResult(**fields)  # type: ignore[arg-type]


def _result_fields(result: DeterministicPaperReplayHarnessResult) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "status": result.status,
        "matched": result.matched,
        "ready": result.ready,
        "run_id": result.run_id,
        "episode_id": result.episode_id,
        "correlation_id": result.correlation_id,
        "market_symbol": result.market_symbol,
        "expected_original_digest": result.expected_original_digest,
        "expected_replay_digest": result.expected_replay_digest,
        "original_decision_digest": result.original_decision_digest,
        "replay_decision_digest": result.replay_decision_digest,
        "original_decision_status": result.original_decision_status,
        "replay_decision_status": result.replay_decision_status,
        "original_verdict": result.original_verdict,
        "replay_verdict": result.replay_verdict,
        "original_ledger_bridge_digest": result.original_ledger_bridge_digest,
        "replay_ledger_bridge_digest": result.replay_ledger_bridge_digest,
        "original_policy_digest": result.original_policy_digest,
        "replay_policy_digest": result.replay_policy_digest,
        "original_episode_digest": result.original_episode_digest,
        "replay_episode_digest": result.replay_episode_digest,
        "original_manifest_digest": result.original_manifest_digest,
        "replay_manifest_digest": result.replay_manifest_digest,
        "original_realized_pnl_event_digest": result.original_realized_pnl_event_digest,
        "replay_realized_pnl_event_digest": result.replay_realized_pnl_event_digest,
        "original_realized_pnl_total": result.original_realized_pnl_total,
        "replay_realized_pnl_total": result.replay_realized_pnl_total,
        "original_closed_units_total": result.original_closed_units_total,
        "replay_closed_units_total": result.replay_closed_units_total,
        "original_computed_event_count": result.original_computed_event_count,
        "replay_computed_event_count": result.replay_computed_event_count,
        "original_source_event_digest_count": result.original_source_event_digest_count,
        "replay_source_event_digest_count": result.replay_source_event_digest_count,
        "compared_boundaries": result.compared_boundaries,
        "reason_codes": result.reason_codes,
        "metadata": result.metadata,
    }


def _result_payload_from(result: DeterministicPaperReplayHarnessResult) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "status": result.status.value,
        "matched": result.matched,
        "ready": result.ready,
        "run_id": result.run_id,
        "episode_id": result.episode_id,
        "correlation_id": result.correlation_id,
        "market_symbol": result.market_symbol,
        "expected_original_digest": result.expected_original_digest,
        "expected_replay_digest": result.expected_replay_digest,
        "original_decision_digest": result.original_decision_digest,
        "replay_decision_digest": result.replay_decision_digest,
        "original_decision_status": result.original_decision_status,
        "replay_decision_status": result.replay_decision_status,
        "original_verdict": result.original_verdict,
        "replay_verdict": result.replay_verdict,
        "original_ledger_bridge_digest": result.original_ledger_bridge_digest,
        "replay_ledger_bridge_digest": result.replay_ledger_bridge_digest,
        "original_policy_digest": result.original_policy_digest,
        "replay_policy_digest": result.replay_policy_digest,
        "original_episode_digest": result.original_episode_digest,
        "replay_episode_digest": result.replay_episode_digest,
        "original_manifest_digest": result.original_manifest_digest,
        "replay_manifest_digest": result.replay_manifest_digest,
        "original_realized_pnl_event_digest": result.original_realized_pnl_event_digest,
        "replay_realized_pnl_event_digest": result.replay_realized_pnl_event_digest,
        "original_realized_pnl_total": result.original_realized_pnl_total,
        "replay_realized_pnl_total": result.replay_realized_pnl_total,
        "original_closed_units_total": result.original_closed_units_total,
        "replay_closed_units_total": result.replay_closed_units_total,
        "original_computed_event_count": result.original_computed_event_count,
        "replay_computed_event_count": result.replay_computed_event_count,
        "original_source_event_digest_count": result.original_source_event_digest_count,
        "replay_source_event_digest_count": result.replay_source_event_digest_count,
        "compared_boundaries": list(result.compared_boundaries),
        "reason_codes": list(result.reason_codes),
        "metadata": _serialize_metadata(result.metadata),
        "paper_only": result.paper_only,
        "prdv4_stage4_complete": result.prdv4_stage4_complete,
        "live_ready": result.live_ready,
        "shadow_ready": result.shadow_ready,
        "profitability_proven": result.profitability_proven,
        "edge_proven": result.edge_proven,
        "production_execution": result.production_execution,
        "real_orders_enabled": result.real_orders_enabled,
        "real_money_enabled": result.real_money_enabled,
        "real_capital_reserved": result.real_capital_reserved,
        "order_routed": result.order_routed,
        "execution_authorized": result.execution_authorized,
        "live_api_called": result.live_api_called,
        "scheduler_enabled": result.scheduler_enabled,
        "auto_loop_enabled": result.auto_loop_enabled,
        "connector_invoked": result.connector_invoked,
    }


def deterministic_paper_replay_harness_result_to_dict(
    result: DeterministicPaperReplayHarnessResult,
) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for a result (deterministic shape, includes self-digest)."""
    payload = _result_payload_from(result)
    payload["replay_result_digest"] = result.replay_result_digest
    return payload


def deterministic_paper_replay_harness_result_digest(result: DeterministicPaperReplayHarnessResult) -> str:
    """Recompute the canonical result digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_result_payload_from(result))


__all__ = [
    "DeterministicPaperReplayHarnessError",
    "DeterministicPaperReplayHarnessResult",
    "DeterministicPaperReplayHarnessStatus",
    "deterministic_paper_replay_harness_result_digest",
    "deterministic_paper_replay_harness_result_to_dict",
    "verify_deterministic_paper_replay",
]
