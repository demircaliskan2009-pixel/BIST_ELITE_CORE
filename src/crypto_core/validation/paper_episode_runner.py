"""Deterministic paper episode runner — single-step orchestration over existing paper artifacts.

A small, immutable, fail-closed orchestration seam that threads already-validated paper artifacts
through their existing public operations and emits one frozen, digest-bound ``PaperEpisodeRunResult``:

    PaperOrderIntent + prior PaperPositionState + PaperFillMarketSnapshot + PaperFillPolicy
      → simulate_paper_fill        → PaperFillSimulationResult
      → apply_paper_fill_to_position → PaperPositionTransitionResult (+ new PaperPositionState)
      → compute_paper_pnl_report   → PaperPnlReport (unrealized / MTM only)
      → PaperEpisodeRunResult

It is a **single deterministic step**: not a scheduler, not an auto-loop, not a live runner, not a
multi-order loop. It introduces no new economics (no Decimal arithmetic at all): every fill / position
/ PnL number is produced by the existing child operations and only their digests are bound here. It
routes no order, creates no venue/exchange/client order id / route id / execution instruction, calls no
live/private API, computes no realized/total PnL, mutates no capital/balance/position, and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal
surface, no Deribit, no BIST.

The runner does not blindly trust its inputs: each of the five input artifacts is re-proven at the
boundary via its PUBLIC digest helper (mismatch fails closed) and the market symbol is required to be
consistent across order / position / fill-snapshot / mark. The deep structural re-proof of every input
is delegated to the child operations (which already perform it); a child operation's typed failure is
re-raised as ``PaperEpisodeRunnerError`` so the runner presents a single fail-closed error surface.
Every child digest is bound into the result.

Episode semantics:
  - fill ``FILLED`` / ``PARTIALLY_FILLED`` ⇒ transition must be ``APPLIED`` with a new state; an MTM
    report is computed over the new state + mark; status ``COMPUTED`` (binds new-position + pnl digests).
  - fill ``REJECTED`` ⇒ transition must be ``REJECTED`` with no new state; no MTM report is computed;
    status ``FILL_REJECTED`` with ``new_position_state_digest=None`` / ``pnl_report_digest=None`` and
    ``reason_codes`` including ``fill_rejected`` (plus the underlying fill reasons).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_fill_simulator import (
    PaperFillMarketSnapshot,
    PaperFillPolicy,
    PaperFillSimulationError,
    PaperFillSimulationStatus,
    paper_fill_market_snapshot_digest,
    paper_fill_policy_digest,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import (
    PaperOrderIntent,
    paper_order_intent_digest,
)
from crypto_core.validation.paper_pnl_report import (
    PaperMarkSnapshot,
    PaperPnlReportError,
    compute_paper_pnl_report,
    paper_mark_snapshot_digest,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionState,
    PaperPositionStateError,
    PaperPositionTransitionStatus,
    apply_paper_fill_to_position,
    paper_position_state_digest,
)

_EPISODE_SCHEMA_VERSION = "paper-episode-run-result.v1"

_REASON_FILL_REJECTED = "fill_rejected"

# Scope guard mirrors the sibling validation modules (word-bounded) and rejects bare
# ``connector``/``route_id``/``execution_instruction``/``deribit``/``venue|exchange|client_order_id``
# tokens relevant to this seam. Market-data terms are scrubbed before the scan.
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


class PaperEpisodeRunnerError(RuntimeError):
    """Raised when episode inputs are wrong-typed/malformed/forged or a child operation fails (fail-closed)."""


class PaperEpisodeRunStatus(str, Enum):
    """Deterministic paper episode outcome. Never an execution / capital / live action."""

    COMPUTED = "COMPUTED"
    FILL_REJECTED = "FILL_REJECTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperEpisodeRunResult:
    """Deterministic, immutable digest-bound single-step paper episode result. PAPER ONLY.

    Binds every child artifact by digest. ``episode_run_computed`` is True only for a fully-computed
    episode (``COMPUTED``); ``position_state_updated`` / ``pnl_report_computed`` are True only when the
    corresponding child artifact exists. Every other attestation is False — the non-execution,
    non-realized-PnL, non-capital contract is auditable.
    """

    schema_version: str
    episode_run_id: str
    status: PaperEpisodeRunStatus
    market_symbol: str
    order_intent_digest: str
    prior_position_state_digest: str
    fill_market_snapshot_digest: str
    fill_policy_digest: str
    fill_simulation_result_digest: str
    fill_status: str
    position_transition_digest: str
    transition_status: str
    new_position_state_digest: str | None
    mark_snapshot_digest: str
    pnl_report_digest: str | None
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    episode_run_digest: str
    paper_only: bool = True
    episode_run_computed: bool = False
    fill_simulated: bool = True
    position_state_updated: bool = False
    pnl_report_computed: bool = False
    realized_pnl_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    live_position_mutated: bool = False
    real_money_enabled: bool = False
    real_orders_enabled: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    connector_invoked: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperEpisodeRunnerError("paper_episode_runner:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperEpisodeRunnerError("paper_episode_runner:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


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


def _reprove_input_digest(*, actual: object, recompute, label: str) -> None:
    """Re-prove an input artifact's stored self-digest via its PUBLIC serializer (fail-closed).

    A malformed artifact whose serializer raises is reported as ``<label>_malformed``; a stored digest
    that does not equal the recomputed one is ``<label>_digest_mismatch``. (A self-consistent forged
    artifact passes here and is caught by the child operation's deep structural re-proof.)
    """
    try:
        expected = recompute(actual)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperEpisodeRunnerError(f"paper_episode_runner:{label}_malformed") from exc
    stored = getattr(actual, _DIGEST_ATTR[label])
    if not isinstance(stored, str) or stored != expected:
        raise PaperEpisodeRunnerError(f"paper_episode_runner:{label}_digest_mismatch")


_DIGEST_ATTR = {
    "order_intent": "intent_digest",
    "prior_position_state": "position_state_digest",
    "fill_market_snapshot": "snapshot_digest",
    "fill_policy": "policy_digest",
    "mark_snapshot": "mark_snapshot_digest",
}


def run_paper_episode(
    order_intent: PaperOrderIntent,
    prior_position_state: PaperPositionState,
    fill_market_snapshot: PaperFillMarketSnapshot,
    fill_policy: PaperFillPolicy,
    mark_snapshot: PaperMarkSnapshot,
    *,
    fill_simulation_id: str,
    position_transition_id: str,
    new_position_state_id: str,
    pnl_report_id: str,
    episode_run_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperEpisodeRunResult:
    """Run one deterministic paper episode over existing artifacts; bind every child digest.

    Re-proves each input artifact's PUBLIC digest (mismatch raises) and requires a consistent market
    symbol across order / prior position / fill snapshot / mark, then simulates the fill, applies it to
    the prior position, and (only for an applied fill) computes an unrealized/MTM PnL report — copying
    all trading/economic fields from the artifacts and the child operations; the caller supplies only
    operational ids/correlation/metadata. A ``REJECTED`` fill yields ``FILL_REJECTED`` with no new state
    or PnL report. Wrong-typed/malformed/forged inputs (including those caught by a child operation)
    raise ``PaperEpisodeRunnerError``. No realized/total PnL, no capital/balance mutation, no order
    routing, no live API, no scheduler; inputs are never mutated.
    """
    for value, label in (
        (fill_simulation_id, "fill_simulation_id"),
        (position_transition_id, "position_transition_id"),
        (new_position_state_id, "new_position_state_id"),
        (pnl_report_id, "pnl_report_id"),
        (episode_run_id, "episode_run_id"),
        (correlation_id, "correlation_id"),
    ):
        if not _is_non_empty_string(value):
            raise PaperEpisodeRunnerError(f"paper_episode_runner:{label}_invalid")
    episode_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(
        fill_simulation_id,
        position_transition_id,
        new_position_state_id,
        pnl_report_id,
        episode_run_id,
        correlation_id,
        *_metadata_texts(episode_metadata),
    ):
        raise PaperEpisodeRunnerError("paper_episode_runner:scope_violation")

    if not isinstance(order_intent, PaperOrderIntent):
        raise PaperEpisodeRunnerError("paper_episode_runner:order_intent_malformed")
    if not isinstance(prior_position_state, PaperPositionState):
        raise PaperEpisodeRunnerError("paper_episode_runner:prior_position_state_malformed")
    if not isinstance(fill_market_snapshot, PaperFillMarketSnapshot):
        raise PaperEpisodeRunnerError("paper_episode_runner:fill_market_snapshot_malformed")
    if not isinstance(fill_policy, PaperFillPolicy):
        raise PaperEpisodeRunnerError("paper_episode_runner:fill_policy_malformed")
    if not isinstance(mark_snapshot, PaperMarkSnapshot):
        raise PaperEpisodeRunnerError("paper_episode_runner:mark_snapshot_malformed")

    # Digest boundaries: re-prove every input artifact's self-digest via its PUBLIC serializer.
    _reprove_input_digest(actual=order_intent, recompute=paper_order_intent_digest, label="order_intent")
    _reprove_input_digest(
        actual=prior_position_state, recompute=paper_position_state_digest, label="prior_position_state"
    )
    _reprove_input_digest(
        actual=fill_market_snapshot, recompute=paper_fill_market_snapshot_digest, label="fill_market_snapshot"
    )
    _reprove_input_digest(actual=fill_policy, recompute=paper_fill_policy_digest, label="fill_policy")
    _reprove_input_digest(actual=mark_snapshot, recompute=paper_mark_snapshot_digest, label="mark_snapshot")

    market_symbol = order_intent.market_symbol
    for artifact_symbol in (
        prior_position_state.market_symbol,
        fill_market_snapshot.market_symbol,
        mark_snapshot.market_symbol,
    ):
        if artifact_symbol != market_symbol:
            raise PaperEpisodeRunnerError("paper_episode_runner:symbol_mismatch")

    # Step 1: simulate the fill (re-proves intent/snapshot/policy structure deeply, fail-closed).
    try:
        fill_result = simulate_paper_fill(
            order_intent,
            fill_market_snapshot,
            fill_policy,
            fill_simulation_id=fill_simulation_id,
            correlation_id=correlation_id,
        )
    except PaperFillSimulationError as exc:
        raise PaperEpisodeRunnerError("paper_episode_runner:fill_simulation_failed") from exc

    # Step 2: apply the fill to the prior position (re-proves prior state + fill result deeply).
    try:
        transition, new_state = apply_paper_fill_to_position(
            prior_position_state,
            fill_result,
            transition_id=position_transition_id,
            new_position_state_id=new_position_state_id,
            correlation_id=correlation_id,
        )
    except PaperPositionStateError as exc:
        raise PaperEpisodeRunnerError("paper_episode_runner:position_transition_failed") from exc

    if fill_result.status is PaperFillSimulationStatus.REJECTED:
        if transition.status is not PaperPositionTransitionStatus.REJECTED or new_state is not None:
            raise PaperEpisodeRunnerError("paper_episode_runner:transition_inconsistent")
        return _finalize_episode(
            episode_run_id=episode_run_id,
            status=PaperEpisodeRunStatus.FILL_REJECTED,
            market_symbol=market_symbol,
            order_intent=order_intent,
            prior_position_state=prior_position_state,
            fill_market_snapshot=fill_market_snapshot,
            fill_policy=fill_policy,
            fill_result=fill_result,
            transition=transition,
            new_state=None,
            mark_snapshot=mark_snapshot,
            pnl_report=None,
            reasons=(_REASON_FILL_REJECTED, *fill_result.reason_codes),
            correlation_id=correlation_id,
            metadata=episode_metadata,
        )

    if transition.status is not PaperPositionTransitionStatus.APPLIED or new_state is None:
        raise PaperEpisodeRunnerError("paper_episode_runner:transition_inconsistent")

    # Step 3: compute the unrealized/MTM PnL report (re-proves new state + mark deeply).
    try:
        pnl_report = compute_paper_pnl_report(
            new_state,
            mark_snapshot,
            pnl_report_id=pnl_report_id,
            correlation_id=correlation_id,
        )
    except PaperPnlReportError as exc:
        raise PaperEpisodeRunnerError("paper_episode_runner:pnl_report_failed") from exc

    return _finalize_episode(
        episode_run_id=episode_run_id,
        status=PaperEpisodeRunStatus.COMPUTED,
        market_symbol=market_symbol,
        order_intent=order_intent,
        prior_position_state=prior_position_state,
        fill_market_snapshot=fill_market_snapshot,
        fill_policy=fill_policy,
        fill_result=fill_result,
        transition=transition,
        new_state=new_state,
        mark_snapshot=mark_snapshot,
        pnl_report=pnl_report,
        reasons=(),
        correlation_id=correlation_id,
        metadata=episode_metadata,
    )


def _finalize_episode(
    *,
    episode_run_id: str,
    status: PaperEpisodeRunStatus,
    market_symbol: str,
    order_intent: PaperOrderIntent,
    prior_position_state: PaperPositionState,
    fill_market_snapshot: PaperFillMarketSnapshot,
    fill_policy: PaperFillPolicy,
    fill_result,
    transition,
    new_state: PaperPositionState | None,
    mark_snapshot: PaperMarkSnapshot,
    pnl_report,
    reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperEpisodeRunResult:
    computed = status is PaperEpisodeRunStatus.COMPUTED
    new_position_state_digest = new_state.position_state_digest if new_state is not None else None
    pnl_report_digest = pnl_report.pnl_report_digest if pnl_report is not None else None
    fields: dict[str, object] = {
        "schema_version": _EPISODE_SCHEMA_VERSION,
        "episode_run_id": episode_run_id,
        "status": status,
        "market_symbol": market_symbol,
        "order_intent_digest": order_intent.intent_digest,
        "prior_position_state_digest": prior_position_state.position_state_digest,
        "fill_market_snapshot_digest": fill_market_snapshot.snapshot_digest,
        "fill_policy_digest": fill_policy.policy_digest,
        "fill_simulation_result_digest": fill_result.result_digest,
        "fill_status": fill_result.status.value,
        "position_transition_digest": transition.transition_digest,
        "transition_status": transition.status.value,
        "new_position_state_digest": new_position_state_digest,
        "mark_snapshot_digest": mark_snapshot.mark_snapshot_digest,
        "pnl_report_digest": pnl_report_digest,
        "reason_codes": _sorted_unique(reasons),
        "correlation_id": correlation_id,
        "metadata": metadata,
        "episode_run_computed": computed,
        "position_state_updated": new_state is not None,
        "pnl_report_computed": pnl_report is not None,
    }
    seed = PaperEpisodeRunResult(episode_run_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_episode_run_result_digest(seed))


def _replace_digest(result: PaperEpisodeRunResult, digest: str) -> PaperEpisodeRunResult:
    fields = _result_fields(result)
    fields["episode_run_digest"] = digest
    return PaperEpisodeRunResult(**fields)  # type: ignore[arg-type]


def _result_fields(result: PaperEpisodeRunResult) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "episode_run_id": result.episode_run_id,
        "status": result.status,
        "market_symbol": result.market_symbol,
        "order_intent_digest": result.order_intent_digest,
        "prior_position_state_digest": result.prior_position_state_digest,
        "fill_market_snapshot_digest": result.fill_market_snapshot_digest,
        "fill_policy_digest": result.fill_policy_digest,
        "fill_simulation_result_digest": result.fill_simulation_result_digest,
        "fill_status": result.fill_status,
        "position_transition_digest": result.position_transition_digest,
        "transition_status": result.transition_status,
        "new_position_state_digest": result.new_position_state_digest,
        "mark_snapshot_digest": result.mark_snapshot_digest,
        "pnl_report_digest": result.pnl_report_digest,
        "reason_codes": result.reason_codes,
        "correlation_id": result.correlation_id,
        "metadata": result.metadata,
        "episode_run_computed": result.episode_run_computed,
        "position_state_updated": result.position_state_updated,
        "pnl_report_computed": result.pnl_report_computed,
    }


def _episode_payload_from(result: PaperEpisodeRunResult) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "episode_run_id": result.episode_run_id,
        "status": result.status.value,
        "market_symbol": result.market_symbol,
        "order_intent_digest": result.order_intent_digest,
        "prior_position_state_digest": result.prior_position_state_digest,
        "fill_market_snapshot_digest": result.fill_market_snapshot_digest,
        "fill_policy_digest": result.fill_policy_digest,
        "fill_simulation_result_digest": result.fill_simulation_result_digest,
        "fill_status": result.fill_status,
        "position_transition_digest": result.position_transition_digest,
        "transition_status": result.transition_status,
        "new_position_state_digest": result.new_position_state_digest,
        "mark_snapshot_digest": result.mark_snapshot_digest,
        "pnl_report_digest": result.pnl_report_digest,
        "reason_codes": list(result.reason_codes),
        "correlation_id": result.correlation_id,
        "metadata": [list(pair) for pair in result.metadata],
        "paper_only": result.paper_only,
        "episode_run_computed": result.episode_run_computed,
        "fill_simulated": result.fill_simulated,
        "position_state_updated": result.position_state_updated,
        "pnl_report_computed": result.pnl_report_computed,
        "realized_pnl_computed": result.realized_pnl_computed,
        "capital_reserved": result.capital_reserved,
        "capital_mutated": result.capital_mutated,
        "balance_mutated": result.balance_mutated,
        "live_position_mutated": result.live_position_mutated,
        "real_money_enabled": result.real_money_enabled,
        "real_orders_enabled": result.real_orders_enabled,
        "order_routed": result.order_routed,
        "venue_order_id_created": result.venue_order_id_created,
        "exchange_order_id_created": result.exchange_order_id_created,
        "client_order_id_created": result.client_order_id_created,
        "route_id_created": result.route_id_created,
        "execution_instruction_created": result.execution_instruction_created,
        "live_api_called": result.live_api_called,
        "scheduler_enabled": result.scheduler_enabled,
        "connector_invoked": result.connector_invoked,
    }


def paper_episode_run_result_to_dict(result: PaperEpisodeRunResult) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an episode result (deterministic shape, includes self-digest)."""
    payload = _episode_payload_from(result)
    payload["episode_run_digest"] = result.episode_run_digest
    return payload


def paper_episode_run_result_digest(result: PaperEpisodeRunResult) -> str:
    """Recompute the canonical episode-result digest from the serializer output, excluding self-digest."""
    return _canonical_digest(_episode_payload_from(result))


__all__ = [
    "PaperEpisodeRunResult",
    "PaperEpisodeRunStatus",
    "PaperEpisodeRunnerError",
    "paper_episode_run_result_digest",
    "paper_episode_run_result_to_dict",
    "run_paper_episode",
]
