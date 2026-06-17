"""Paper session sequence — deterministic, immutable, digest-bound ordering of paper episode results.

A small, immutable, fail-closed *sequence artifact* that binds an ordered list of already-produced
``PaperEpisodeRunResult`` records into one frozen, digest-bound ``PaperSessionSequenceResult``. It does
**not** execute episodes, call the runner, schedule anything, create an auto-loop, simulate fills,
create positions, or compute PnL — it only validates, orders, de-duplicates, binds, and counts existing
episode-result digests. It routes no order, creates no venue/exchange/client order id / route id /
execution instruction, calls no live/private API, computes no realized/total PnL, mutates no
capital/balance/position, and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal
surface, no Deribit, no BIST. No Decimal arithmetic (counts are plain ints).

Each input ``PaperEpisodeRunResult`` is re-proven at the boundary via the PUBLIC
``paper_episode_run_result_digest`` (mismatch fails closed) and then structurally re-proven for session
consumption (schema, status enum, ids, paper-safe flags, child-digest shapes per status, status/reason
consistency). Digest equality alone is not trusted: a self-consistent forged episode (digest recomputed
over a tampered payload) is still rejected. All episodes must share one ``market_symbol``; duplicate
``episode_run_digest`` or ``episode_run_id`` is rejected; caller order is preserved exactly.

Summary semantics: the session counts COMPUTED / FILL_REJECTED episodes and exposes the final position
and PnL-report digests taken from the **last COMPUTED episode in order** (or ``None`` if there is none).
No PnL is aggregated; no total/equity/capital is computed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunResult,
    PaperEpisodeRunStatus,
    paper_episode_run_result_digest,
)

_SESSION_SCHEMA_VERSION = "paper-session-sequence.v1"
_EXPECTED_EPISODE_SCHEMA_VERSION = "paper-episode-run-result.v1"

_REASON_FILL_REJECTED = "fill_rejected"

_VALID_FILL_STATUSES = frozenset({"FILLED", "PARTIALLY_FILLED", "REJECTED"})

# Scope guard mirrors the sibling validation modules (word-bounded) and rejects bare
# ``connector``/``route_id``/``execution_instruction``/``deribit``/``venue|exchange|client_order_id``
# tokens. Market-data terms are scrubbed before the scan.
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


class PaperSessionSequenceError(RuntimeError):
    """Raised when session/episode inputs are wrong-typed/malformed/forged or fail re-proof (fail-closed)."""


class PaperSessionSequenceStatus(str, Enum):
    """Deterministic paper session sequence outcome. Never an execution / capital / live action."""

    COMPUTED = "COMPUTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperSessionSequenceResult:
    """Deterministic, immutable digest-bound ordered sequence of paper episode results. PAPER ONLY.

    Binds each episode by digest and summarizes counts + final position/PnL digests. Never executes,
    schedules, or loops; computes no realized/total PnL or capital. Every negative attestation is False.
    """

    schema_version: str
    paper_session_id: str
    status: PaperSessionSequenceStatus
    market_symbol: str
    episode_count: int
    episode_run_digests: tuple[str, ...]
    first_episode_run_digest: str
    last_episode_run_digest: str
    computed_episode_count: int
    fill_rejected_episode_count: int
    rejected_episode_count: int
    final_position_state_digest: str | None
    final_pnl_report_digest: str | None
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    paper_session_sequence_digest: str
    paper_only: bool = True
    session_sequence_computed: bool = True
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    real_money_enabled: bool = False
    real_orders_enabled: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    realized_pnl_computed: bool = False
    total_pnl_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    live_position_mutated: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_sorted_unique_reasons(reasons: object) -> bool:
    if not isinstance(reasons, tuple):
        return False
    if not all(isinstance(reason, str) and reason != "" for reason in reasons):
        return False
    return list(reasons) == sorted(set(reasons))


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperSessionSequenceError("paper_session_sequence:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSessionSequenceError("paper_session_sequence:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _is_metadata_tuple(metadata: object) -> bool:
    if not isinstance(metadata, tuple):
        return False
    for pair in metadata:
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
        ):
            return False
    return metadata == tuple(sorted(metadata))


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


# --------------------------------------------------------------------------------------------------
# Episode re-proof
# --------------------------------------------------------------------------------------------------

_ALWAYS_PRESENT_EPISODE_DIGESTS = (
    "order_intent_digest",
    "prior_position_state_digest",
    "fill_market_snapshot_digest",
    "fill_policy_digest",
    "fill_simulation_result_digest",
    "position_transition_digest",
    "mark_snapshot_digest",
)


def _episode_is_paper_safe(episode: PaperEpisodeRunResult) -> bool:
    return (
        episode.paper_only is True
        and episode.fill_simulated is True
        and episode.realized_pnl_computed is False
        and episode.capital_reserved is False
        and episode.capital_mutated is False
        and episode.balance_mutated is False
        and episode.live_position_mutated is False
        and episode.real_money_enabled is False
        and episode.real_orders_enabled is False
        and episode.order_routed is False
        and episode.venue_order_id_created is False
        and episode.exchange_order_id_created is False
        and episode.client_order_id_created is False
        and episode.route_id_created is False
        and episode.execution_instruction_created is False
        and episode.live_api_called is False
        and episode.scheduler_enabled is False
        and episode.connector_invoked is False
    )


def _reprove_episode(episode: PaperEpisodeRunResult) -> None:
    """Re-prove a digest-valid episode result's structure/safety/status-consistency (fail-closed).

    A self-consistent forged episode (digest recomputed over a tampered payload) must still fail here.
    The reserved ``REJECTED`` episode status is not emitted by the runner and is rejected fail-closed.
    """
    if episode.schema_version != _EXPECTED_EPISODE_SCHEMA_VERSION:
        raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
    if not isinstance(episode.status, PaperEpisodeRunStatus):
        raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
    if episode.status not in (PaperEpisodeRunStatus.COMPUTED, PaperEpisodeRunStatus.FILL_REJECTED):
        raise PaperSessionSequenceError("paper_session_sequence:episode_status_invalid")
    if not (
        _is_non_empty_string(episode.episode_run_id)
        and _is_non_empty_string(episode.market_symbol)
        and _is_non_empty_string(episode.correlation_id)
    ):
        raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
    if not _episode_is_paper_safe(episode):
        raise PaperSessionSequenceError("paper_session_sequence:episode_unsafe_flags")
    for attr in _ALWAYS_PRESENT_EPISODE_DIGESTS:
        if not _is_hex64_string(getattr(episode, attr)):
            raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
    if episode.fill_status not in _VALID_FILL_STATUSES or episode.transition_status not in {"APPLIED", "REJECTED"}:
        raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
    if not _is_metadata_tuple(episode.metadata):
        raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
    if not _is_sorted_unique_reasons(episode.reason_codes):
        raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
    if _has_scope_violation(
        episode.episode_run_id, episode.market_symbol, episode.correlation_id, *_metadata_texts(episode.metadata)
    ):
        raise PaperSessionSequenceError("paper_session_sequence:episode_scope_violation")

    if episode.status is PaperEpisodeRunStatus.COMPUTED:
        if episode.fill_status not in {"FILLED", "PARTIALLY_FILLED"} or episode.transition_status != "APPLIED":
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")
        if not _is_hex64_string(episode.new_position_state_digest) or not _is_hex64_string(episode.pnl_report_digest):
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")
        if episode.reason_codes != ():
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")
        if not (
            episode.episode_run_computed is True
            and episode.position_state_updated is True
            and episode.pnl_report_computed is True
        ):
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")
    else:  # FILL_REJECTED
        if episode.fill_status != "REJECTED" or episode.transition_status != "REJECTED":
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")
        if episode.new_position_state_digest is not None or episode.pnl_report_digest is not None:
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")
        if _REASON_FILL_REJECTED not in episode.reason_codes:
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")
        if not (
            episode.episode_run_computed is False
            and episode.position_state_updated is False
            and episode.pnl_report_computed is False
        ):
            raise PaperSessionSequenceError("paper_session_sequence:episode_inconsistent")


# --------------------------------------------------------------------------------------------------
# Session construction
# --------------------------------------------------------------------------------------------------


def build_paper_session_sequence(
    episodes: Sequence[PaperEpisodeRunResult],
    *,
    paper_session_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSessionSequenceResult:
    """Build a deterministic, immutable digest-bound paper session sequence from ordered episode results.

    Each episode is re-proven via the PUBLIC ``paper_episode_run_result_digest`` (mismatch raises) and
    structurally re-proven for session consumption; all episodes must share one ``market_symbol`` and
    have unique ``episode_run_digest`` / ``episode_run_id``; caller order is preserved. The final
    position and PnL-report digests are taken from the last COMPUTED episode (or None). No execution, no
    scheduling, no PnL aggregation, no capital. Wrong-typed/malformed/forged inputs raise
    ``PaperSessionSequenceError``; inputs are never mutated.
    """
    if not _is_non_empty_string(paper_session_id):
        raise PaperSessionSequenceError("paper_session_sequence:paper_session_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperSessionSequenceError("paper_session_sequence:correlation_id_invalid")
    session_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(paper_session_id, correlation_id, *_metadata_texts(session_metadata)):
        raise PaperSessionSequenceError("paper_session_sequence:scope_violation")
    if isinstance(episodes, (str, bytes)) or not isinstance(episodes, Sequence):
        raise PaperSessionSequenceError("paper_session_sequence:episodes_malformed")
    episode_tuple = tuple(episodes)
    if not episode_tuple:
        raise PaperSessionSequenceError("paper_session_sequence:episodes_empty")

    market_symbol: str | None = None
    digests: list[str] = []
    ids: list[str] = []
    computed = 0
    fill_rejected = 0
    final_position_state_digest: str | None = None
    final_pnl_report_digest: str | None = None

    for episode in episode_tuple:
        if not isinstance(episode, PaperEpisodeRunResult):
            raise PaperSessionSequenceError("paper_session_sequence:episode_malformed")
        try:
            expected_digest = paper_episode_run_result_digest(episode)
        except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
            raise PaperSessionSequenceError("paper_session_sequence:episode_malformed") from exc
        if not isinstance(episode.episode_run_digest, str) or episode.episode_run_digest != expected_digest:
            raise PaperSessionSequenceError("paper_session_sequence:episode_digest_mismatch")
        _reprove_episode(episode)

        if market_symbol is None:
            market_symbol = episode.market_symbol
        elif episode.market_symbol != market_symbol:
            raise PaperSessionSequenceError("paper_session_sequence:symbol_mismatch")

        digests.append(episode.episode_run_digest)
        ids.append(episode.episode_run_id)
        if episode.status is PaperEpisodeRunStatus.COMPUTED:
            computed += 1
            final_position_state_digest = episode.new_position_state_digest
            final_pnl_report_digest = episode.pnl_report_digest
        else:  # FILL_REJECTED (REJECTED already rejected by _reprove_episode)
            fill_rejected += 1

    if len(set(digests)) != len(digests):
        raise PaperSessionSequenceError("paper_session_sequence:duplicate_episode_digest")
    if len(set(ids)) != len(ids):
        raise PaperSessionSequenceError("paper_session_sequence:duplicate_episode_id")

    episode_count = len(episode_tuple)
    assert market_symbol is not None  # noqa: S101 - guaranteed non-empty by the loop above
    return _finalize_session(
        paper_session_id=paper_session_id,
        market_symbol=market_symbol,
        episode_run_digests=tuple(digests),
        episode_count=episode_count,
        computed_episode_count=computed,
        fill_rejected_episode_count=fill_rejected,
        rejected_episode_count=episode_count - computed - fill_rejected,
        final_position_state_digest=final_position_state_digest,
        final_pnl_report_digest=final_pnl_report_digest,
        correlation_id=correlation_id,
        metadata=session_metadata,
    )


def _finalize_session(
    *,
    paper_session_id: str,
    market_symbol: str,
    episode_run_digests: tuple[str, ...],
    episode_count: int,
    computed_episode_count: int,
    fill_rejected_episode_count: int,
    rejected_episode_count: int,
    final_position_state_digest: str | None,
    final_pnl_report_digest: str | None,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperSessionSequenceResult:
    fields: dict[str, object] = {
        "schema_version": _SESSION_SCHEMA_VERSION,
        "paper_session_id": paper_session_id,
        "status": PaperSessionSequenceStatus.COMPUTED,
        "market_symbol": market_symbol,
        "episode_count": episode_count,
        "episode_run_digests": episode_run_digests,
        "first_episode_run_digest": episode_run_digests[0],
        "last_episode_run_digest": episode_run_digests[-1],
        "computed_episode_count": computed_episode_count,
        "fill_rejected_episode_count": fill_rejected_episode_count,
        "rejected_episode_count": rejected_episode_count,
        "final_position_state_digest": final_position_state_digest,
        "final_pnl_report_digest": final_pnl_report_digest,
        "reason_codes": (),
        "correlation_id": correlation_id,
        "metadata": metadata,
    }
    seed = PaperSessionSequenceResult(paper_session_sequence_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_session_sequence_result_digest(seed))


def _replace_digest(result: PaperSessionSequenceResult, digest: str) -> PaperSessionSequenceResult:
    fields = _result_fields(result)
    fields["paper_session_sequence_digest"] = digest
    return PaperSessionSequenceResult(**fields)  # type: ignore[arg-type]


def _result_fields(result: PaperSessionSequenceResult) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "paper_session_id": result.paper_session_id,
        "status": result.status,
        "market_symbol": result.market_symbol,
        "episode_count": result.episode_count,
        "episode_run_digests": result.episode_run_digests,
        "first_episode_run_digest": result.first_episode_run_digest,
        "last_episode_run_digest": result.last_episode_run_digest,
        "computed_episode_count": result.computed_episode_count,
        "fill_rejected_episode_count": result.fill_rejected_episode_count,
        "rejected_episode_count": result.rejected_episode_count,
        "final_position_state_digest": result.final_position_state_digest,
        "final_pnl_report_digest": result.final_pnl_report_digest,
        "reason_codes": result.reason_codes,
        "correlation_id": result.correlation_id,
        "metadata": result.metadata,
    }


def _session_payload_from(result: PaperSessionSequenceResult) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "paper_session_id": result.paper_session_id,
        "status": result.status.value,
        "market_symbol": result.market_symbol,
        "episode_count": result.episode_count,
        "episode_run_digests": list(result.episode_run_digests),
        "first_episode_run_digest": result.first_episode_run_digest,
        "last_episode_run_digest": result.last_episode_run_digest,
        "computed_episode_count": result.computed_episode_count,
        "fill_rejected_episode_count": result.fill_rejected_episode_count,
        "rejected_episode_count": result.rejected_episode_count,
        "final_position_state_digest": result.final_position_state_digest,
        "final_pnl_report_digest": result.final_pnl_report_digest,
        "reason_codes": list(result.reason_codes),
        "correlation_id": result.correlation_id,
        "metadata": [list(pair) for pair in result.metadata],
        "paper_only": result.paper_only,
        "session_sequence_computed": result.session_sequence_computed,
        "scheduler_enabled": result.scheduler_enabled,
        "auto_loop_enabled": result.auto_loop_enabled,
        "live_api_called": result.live_api_called,
        "connector_invoked": result.connector_invoked,
        "real_money_enabled": result.real_money_enabled,
        "real_orders_enabled": result.real_orders_enabled,
        "order_routed": result.order_routed,
        "venue_order_id_created": result.venue_order_id_created,
        "exchange_order_id_created": result.exchange_order_id_created,
        "client_order_id_created": result.client_order_id_created,
        "route_id_created": result.route_id_created,
        "execution_instruction_created": result.execution_instruction_created,
        "realized_pnl_computed": result.realized_pnl_computed,
        "total_pnl_computed": result.total_pnl_computed,
        "capital_reserved": result.capital_reserved,
        "capital_mutated": result.capital_mutated,
        "balance_mutated": result.balance_mutated,
        "live_position_mutated": result.live_position_mutated,
    }


def paper_session_sequence_result_to_dict(result: PaperSessionSequenceResult) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a session sequence (deterministic shape, includes self-digest)."""
    payload = _session_payload_from(result)
    payload["paper_session_sequence_digest"] = result.paper_session_sequence_digest
    return payload


def paper_session_sequence_result_digest(result: PaperSessionSequenceResult) -> str:
    """Recompute the canonical session-sequence digest from the serializer output, excluding self-digest."""
    return _canonical_digest(_session_payload_from(result))


__all__ = [
    "PaperSessionSequenceError",
    "PaperSessionSequenceResult",
    "PaperSessionSequenceStatus",
    "build_paper_session_sequence",
    "paper_session_sequence_result_digest",
    "paper_session_sequence_result_to_dict",
]
