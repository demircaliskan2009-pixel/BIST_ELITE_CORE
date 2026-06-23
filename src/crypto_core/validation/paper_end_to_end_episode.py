"""Paper end-to-end episode — deterministic, paper-only, fail-closed binding of one auditable episode.

Phase-map slice 3 (``docs/crypto_core/paper_trading_phase_map.md`` §7.3): prove the §4 loop body
**intent → fill → position → realized PnL** as one frozen, digest-bound artifact by *binding existing
paper artifacts together* — it is an INTEGRATION SEAM / PROBE, not a parallel paper-trading engine. It
runs no backtest, simulates no fills, mutates no positions, computes no economics, routes no order, and
adds no runtime/persistence/scheduler/execution/venue path. It answers one question: "do these already-
produced paper artifacts describe ONE consistent deterministic episode that reaches realized PnL?"

It binds three already-built artifacts (each re-proven at its trust boundary via its PUBLIC digest
helper — stored digest must equal the recomputed digest and the caller's independent expected anchor):

  - ``StrategySignalToPaperIntent`` (READY)        — the signal → inert paper order-intent request bridge.
  - ``PaperEpisodeRunResult`` (COMPUTED)           — intent → fill → position → unrealized/MTM PnL.
  - ``PaperRealizedPnlEvent`` (COMPUTED / NO_REALIZED_PNL) — the realized-PnL leg over that same fill.

Linkage model (honest, no fake digest link): the episode-run-result and the realized-PnL event share
the SAME ``fill_simulation_result_digest`` / ``position_transition_digest`` / ``prior_position_state_digest``
/ ``new_position_state_digest`` — those are re-proven EQUAL (a strong digest-bound tie that the realized
leg covers the exact fill/transition/positions the episode produced). The strategy-signal bridge emits a
``PaperOrderIntentRequest`` (admission contract) which is intentionally a DIFFERENT representation from the
runner's ``PaperOrderIntent``; the two halves are therefore tied by deterministic LOGICAL consistency
(market symbol, side, correlation id), not by an intent digest — this is stated, not overclaimed.

Non-overclaim: a READY episode is a deterministic binding proof only. It is NOT PRDV4 Stage 4 completion
(no ≥30-day paper trading, no paper-vs-backtest metrics, no Sharpe gate), NOT live readiness, NOT shadow
readiness, NOT proof of profitability, NOT proof of edge, and NOT production execution. Those are carried
as explicit ``False`` flags. Paper only: no fees/equity/capital/margin/balance; reserves/mutates no
capital; routes no order; creates no venue/exchange/client order id / route id / execution instruction;
calls no live/private API; schedules nothing; runs no auto-loop; performs no wall-clock/random/IO/network.
It does NOT import or use ``crypto_core.service.readiness`` or ``crypto_core.execution.paper_adapter`` (or
any shadow/live/runtime/venue surface), no Deribit, no BIST.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunResult,
    PaperEpisodeRunStatus,
    paper_episode_run_result_digest,
)
from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlEvent,
    PaperRealizedPnlStatus,
    paper_realized_pnl_event_digest,
)
from crypto_core.validation.strategy_signal_to_paper_intent import (
    StrategySignalToPaperIntent,
    StrategySignalToPaperIntentStatus,
    strategy_signal_to_paper_intent_digest,
)

_SCHEMA_VERSION = "paper-end-to-end-episode.v1"
_EXPECTED_BRIDGE_SCHEMA_VERSION = "strategy-signal-to-paper-intent.v1"
_EXPECTED_EPISODE_SCHEMA_VERSION = "paper-episode-run-result.v1"
_EXPECTED_REALIZED_SCHEMA_VERSION = "paper-realized-pnl-event.v1"

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


class PaperEndToEndEpisodeError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata)."""


class PaperEndToEndEpisodeStatus(str, Enum):
    """Terminal episode verdict. Never an execution / capital / live / readiness action."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperEndToEndEpisode:
    """Deterministic, immutable, digest-bound binding of one paper episode: signal → fill → realized PnL.

    Binds the strategy-signal bridge, the episode run result, and the realized-PnL event by digest and
    re-proves their cross-consistency. ``paper_only`` True; every safety attestation False; every
    non-overclaim attestation False. PAPER ONLY — NOT PRDV4 Stage 4 completion, NOT live/shadow readiness,
    NOT profitability/edge proof, NOT production execution.
    """

    schema_version: str
    status: PaperEndToEndEpisodeStatus
    ready: bool
    episode_id: str
    run_id: str
    correlation_id: str
    strategy_id: str
    strategy_version: str
    market_symbol: str
    side: str
    requested_units: str
    requested_notional: str
    fill_side: str
    filled_units: str
    fill_price: str
    closed_units: str
    residual_open_units: str
    realized_pnl: str
    realized_pnl_status: str
    bridge_digest: str
    paper_order_intent_request_digest: str
    episode_run_digest: str
    order_intent_digest: str
    fill_simulation_result_digest: str
    position_transition_digest: str
    prior_position_state_digest: str
    new_position_state_digest: str
    mark_snapshot_digest: str
    pnl_report_digest: str
    realized_pnl_event_digest: str
    rejection_reasons: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    episode_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    execution_authorized: bool = False
    live_position_mutated: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    # Non-overclaim attestations (a READY episode proves none of these).
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    production_execution: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    """Exact plain ``str`` (no subclass) that is non-empty after strip."""
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _plain_str_or_empty(value: object) -> str:
    """Return ``value`` only if it is an exact plain ``str`` (no subclass); else ``""`` (fail-closed)."""
    return value if type(value) is str else ""


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        # Exact plain ``str`` only (no subclass) so a custom-hash/eq/strip subclass cannot bypass uniqueness
        # or the scope guard or collapse into a collision-prone key.
        if type(key) is not str or type(value) is not str:
            raise PaperEndToEndEpisodeError("paper_end_to_end_episode:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperEndToEndEpisodeError("paper_end_to_end_episode:metadata_malformed")
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


def _reprove_artifact_digest(*, artifact: object, recompute, stored: object, expected: str, label: str) -> str | None:
    """Re-prove an input artifact's self-digest via its PUBLIC serializer and the caller's expected anchor.

    Returns a fail-closed reason code on any failure, else ``None``. The stored digest must be an exact
    plain lowercase-hex64 string equal BOTH to the recomputed digest and to the caller's independent
    ``expected`` anchor — so a forged/foreign/tampered artifact (or a wrong expectation) can never bind a
    READY episode. A serializer that raises is reported as ``<label>_malformed``.
    """
    try:
        recomputed = recompute(artifact)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return f"paper_end_to_end_episode:{label}_malformed"
    if not _is_hex64_string(stored) or stored != recomputed or stored != expected:
        return f"paper_end_to_end_episode:{label}_digest_mismatch"
    return None


def _bridge_is_paper_safe(bridge: StrategySignalToPaperIntent) -> bool:
    return (
        bridge.paper_only is True
        and bridge.real_orders_enabled is False
        and bridge.real_money_enabled is False
        and bridge.capital_reserved is False
        and bridge.order_routed is False
        and bridge.venue_order_id_created is False
        and bridge.execution_authorized is False
        and bridge.fill_created is False
        and bridge.pnl_computed is False
        and bridge.position_mutated is False
        and bridge.live_api_called is False
        and bridge.scheduler_enabled is False
        and bridge.auto_loop_enabled is False
        and bridge.connector_invoked is False
        and bridge.prdv4_stage4_complete is False
        and bridge.live_ready is False
        and bridge.shadow_ready is False
        and bridge.profitability_proven is False
        and bridge.edge_proven is False
    )


def _episode_is_paper_safe(episode: PaperEpisodeRunResult) -> bool:
    return (
        episode.paper_only is True
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
        and episode.capital_reserved is False
        and episode.capital_mutated is False
        and episode.balance_mutated is False
        and episode.live_position_mutated is False
        and episode.realized_pnl_computed is False
    )


def _realized_is_paper_safe(event: PaperRealizedPnlEvent) -> bool:
    return (
        event.paper_only is True
        and event.real_money_enabled is False
        and event.real_orders_enabled is False
        and event.order_routed is False
        and event.venue_order_id_created is False
        and event.exchange_order_id_created is False
        and event.client_order_id_created is False
        and event.route_id_created is False
        and event.execution_instruction_created is False
        and event.live_api_called is False
        and event.scheduler_enabled is False
        and event.auto_loop_enabled is False
        and event.connector_invoked is False
        and event.capital_reserved is False
        and event.capital_mutated is False
        and event.balance_mutated is False
        and event.live_position_mutated is False
    )


def build_paper_end_to_end_episode(
    bridge: StrategySignalToPaperIntent,
    episode_run: PaperEpisodeRunResult,
    realized_pnl_event: PaperRealizedPnlEvent,
    *,
    expected_bridge_digest: str,
    expected_episode_run_digest: str,
    expected_realized_pnl_event_digest: str,
    episode_id: str,
    run_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperEndToEndEpisode:
    """Bind a strategy-signal bridge, an episode run result, and a realized-PnL event into one episode.

    ``bridge`` / ``episode_run`` / ``realized_pnl_event`` must be the exact frozen artifact types and each
    ``expected_*_digest`` an exact plain 64-lowercase-hex ``str``; ``episode_id`` / ``run_id`` /
    ``correlation_id`` exact plain non-empty ``str``; ``metadata`` ``Mapping[str, str]`` or ``None``. A
    wrong-typed artifact, an empty id, a malformed digest/metadata, or a forbidden BIST/live/order token
    raises ``PaperEndToEndEpisodeError``.

    READY only when: each artifact re-digests to its stored digest AND the caller's expected anchor; the
    bridge is READY + paper-safe; the episode run is COMPUTED (fill → position → MTM) + paper-safe; the
    realized event is COMPUTED/NO_REALIZED_PNL (not REJECTED) + paper-safe; the episode-run and realized
    event share the exact fill / transition / prior-state / new-state digests; and market symbol, side
    (bridge order side == realized fill side), correlation id, and run id are consistent across the chain.
    Every other outcome maps fail-closed to REJECTED. Deterministic and immutable; no wall-clock/random/IO;
    paper only; NOT PRDV4 Stage 4 / live / shadow readiness and NOT a profitability/edge/execution proof.
    """
    if not _is_hex64_string(expected_bridge_digest):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:expected_bridge_digest_invalid")
    if not _is_hex64_string(expected_episode_run_digest):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:expected_episode_run_digest_invalid")
    if not _is_hex64_string(expected_realized_pnl_event_digest):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:expected_realized_pnl_event_digest_invalid")
    for name, value in (("episode_id", episode_id), ("run_id", run_id), ("correlation_id", correlation_id)):
        if not _is_plain_non_empty_string(value):
            raise PaperEndToEndEpisodeError(f"paper_end_to_end_episode:{name}_invalid")
    if not isinstance(bridge, StrategySignalToPaperIntent):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:bridge_malformed")
    if not isinstance(episode_run, PaperEpisodeRunResult):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:episode_run_malformed")
    if not isinstance(realized_pnl_event, PaperRealizedPnlEvent):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:realized_pnl_event_malformed")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(episode_id, run_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperEndToEndEpisodeError("paper_end_to_end_episode:scope_violation")

    hard: list[str] = []

    # Trust boundaries: re-prove each artifact's self-digest via its PUBLIC serializer AND the caller anchor.
    bridge_reason = _reprove_artifact_digest(
        artifact=bridge,
        recompute=strategy_signal_to_paper_intent_digest,
        stored=bridge.bridge_digest,
        expected=expected_bridge_digest,
        label="bridge",
    )
    if bridge_reason is not None:
        hard.append(bridge_reason)
    episode_reason = _reprove_artifact_digest(
        artifact=episode_run,
        recompute=paper_episode_run_result_digest,
        stored=episode_run.episode_run_digest,
        expected=expected_episode_run_digest,
        label="episode_run",
    )
    if episode_reason is not None:
        hard.append(episode_reason)
    realized_reason = _reprove_artifact_digest(
        artifact=realized_pnl_event,
        recompute=paper_realized_pnl_event_digest,
        stored=realized_pnl_event.realized_pnl_event_digest,
        expected=expected_realized_pnl_event_digest,
        label="realized_pnl_event",
    )
    if realized_reason is not None:
        hard.append(realized_reason)

    # Status + schema + paper-safety re-proof per artifact.
    if bridge.schema_version != _EXPECTED_BRIDGE_SCHEMA_VERSION:
        hard.append("paper_end_to_end_episode:bridge_invalid")
    elif bridge.status is not StrategySignalToPaperIntentStatus.READY or bridge.ready is not True:
        hard.append("paper_end_to_end_episode:bridge_not_ready")
    if not _bridge_is_paper_safe(bridge):
        hard.append("paper_end_to_end_episode:bridge_unsafe_flags")

    if episode_run.schema_version != _EXPECTED_EPISODE_SCHEMA_VERSION:
        hard.append("paper_end_to_end_episode:episode_run_invalid")
    elif (
        episode_run.status is not PaperEpisodeRunStatus.COMPUTED
        or episode_run.episode_run_computed is not True
        or episode_run.position_state_updated is not True
        or episode_run.pnl_report_computed is not True
        or not _is_hex64_string(episode_run.new_position_state_digest)
        or not _is_hex64_string(episode_run.pnl_report_digest)
    ):
        hard.append("paper_end_to_end_episode:episode_run_not_computed")
    if not _episode_is_paper_safe(episode_run):
        hard.append("paper_end_to_end_episode:episode_run_unsafe_flags")

    if realized_pnl_event.schema_version != _EXPECTED_REALIZED_SCHEMA_VERSION:
        hard.append("paper_end_to_end_episode:realized_pnl_event_invalid")
    elif realized_pnl_event.status not in (PaperRealizedPnlStatus.COMPUTED, PaperRealizedPnlStatus.NO_REALIZED_PNL):
        hard.append("paper_end_to_end_episode:realized_pnl_event_rejected")
    elif not _is_hex64_string(realized_pnl_event.new_position_state_digest):
        hard.append("paper_end_to_end_episode:realized_pnl_event_invalid")
    if not _realized_is_paper_safe(realized_pnl_event):
        hard.append("paper_end_to_end_episode:realized_pnl_event_unsafe_flags")

    # Cross-artifact consistency. Market symbol / correlation id must agree across all three artifacts and
    # the caller-supplied correlation id; run id must equal the bridge's; the bridge order side must equal
    # the realized fill side. All comparisons are over exact plain strings (a str subclass yields "").
    symbols = {
        _plain_str_or_empty(bridge.market_symbol),
        _plain_str_or_empty(episode_run.market_symbol),
        _plain_str_or_empty(realized_pnl_event.market_symbol),
    }
    if len(symbols) != 1 or "" in symbols:
        hard.append("paper_end_to_end_episode:symbol_mismatch")
    correlations = {
        _plain_str_or_empty(bridge.correlation_id),
        _plain_str_or_empty(episode_run.correlation_id),
        _plain_str_or_empty(realized_pnl_event.correlation_id),
    }
    if correlations != {correlation_id}:
        hard.append("paper_end_to_end_episode:correlation_mismatch")
    if _plain_str_or_empty(bridge.run_id) != run_id:
        hard.append("paper_end_to_end_episode:run_id_mismatch")
    bridge_side = _plain_str_or_empty(bridge.side)
    if bridge_side == "" or bridge_side != _plain_str_or_empty(realized_pnl_event.fill_side):
        hard.append("paper_end_to_end_episode:side_mismatch")

    # Digest-bound chain link: the episode run and the realized event MUST reference the exact same fill /
    # transition / prior-state / new-state (so the realized leg covers the very fill the episode produced).
    chain_pairs = (
        (episode_run.fill_simulation_result_digest, realized_pnl_event.fill_simulation_result_digest),
        (episode_run.position_transition_digest, realized_pnl_event.position_transition_digest),
        (episode_run.prior_position_state_digest, realized_pnl_event.prior_position_state_digest),
        (episode_run.new_position_state_digest, realized_pnl_event.new_position_state_digest),
    )
    if any(not _is_hex64_string(left) or left != right for left, right in chain_pairs):
        hard.append("paper_end_to_end_episode:chain_digest_mismatch")

    rejection_reasons = tuple(sorted(set(hard)))
    status = PaperEndToEndEpisodeStatus.REJECTED if rejection_reasons else PaperEndToEndEpisodeStatus.READY

    return _finalize_episode(
        status=status,
        episode_id=episode_id,
        run_id=run_id,
        correlation_id=correlation_id,
        bridge=bridge,
        episode_run=episode_run,
        realized_pnl_event=realized_pnl_event,
        rejection_reasons=rejection_reasons,
        metadata=metadata_pairs,
    )


def _finalize_episode(
    *,
    status: PaperEndToEndEpisodeStatus,
    episode_id: str,
    run_id: str,
    correlation_id: str,
    bridge: StrategySignalToPaperIntent,
    episode_run: PaperEpisodeRunResult,
    realized_pnl_event: PaperRealizedPnlEvent,
    rejection_reasons: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperEndToEndEpisode:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status,
        "ready": status is PaperEndToEndEpisodeStatus.READY,
        "episode_id": episode_id,
        "run_id": run_id,
        "correlation_id": correlation_id,
        "strategy_id": _plain_str_or_empty(bridge.strategy_id),
        "strategy_version": _plain_str_or_empty(bridge.strategy_version),
        "market_symbol": _plain_str_or_empty(bridge.market_symbol),
        "side": _plain_str_or_empty(bridge.side),
        "requested_units": _plain_str_or_empty(bridge.requested_units),
        "requested_notional": _plain_str_or_empty(bridge.requested_notional),
        "fill_side": _plain_str_or_empty(realized_pnl_event.fill_side),
        "filled_units": _plain_str_or_empty(realized_pnl_event.filled_units),
        "fill_price": _plain_str_or_empty(realized_pnl_event.fill_price),
        "closed_units": _plain_str_or_empty(realized_pnl_event.closed_units),
        "residual_open_units": _plain_str_or_empty(realized_pnl_event.residual_open_units),
        "realized_pnl": _plain_str_or_empty(realized_pnl_event.realized_pnl),
        "realized_pnl_status": realized_pnl_event.status.value
        if isinstance(realized_pnl_event.status, PaperRealizedPnlStatus)
        else "",
        "bridge_digest": _plain_str_or_empty(bridge.bridge_digest),
        "paper_order_intent_request_digest": _plain_str_or_empty(bridge.paper_order_intent_request_digest),
        "episode_run_digest": _plain_str_or_empty(episode_run.episode_run_digest),
        "order_intent_digest": _plain_str_or_empty(episode_run.order_intent_digest),
        "fill_simulation_result_digest": _plain_str_or_empty(episode_run.fill_simulation_result_digest),
        "position_transition_digest": _plain_str_or_empty(episode_run.position_transition_digest),
        "prior_position_state_digest": _plain_str_or_empty(episode_run.prior_position_state_digest),
        "new_position_state_digest": _plain_str_or_empty(episode_run.new_position_state_digest),
        "mark_snapshot_digest": _plain_str_or_empty(episode_run.mark_snapshot_digest),
        "pnl_report_digest": _plain_str_or_empty(episode_run.pnl_report_digest),
        "realized_pnl_event_digest": _plain_str_or_empty(realized_pnl_event.realized_pnl_event_digest),
        "rejection_reasons": rejection_reasons,
        "metadata": metadata,
    }
    seed = PaperEndToEndEpisode(episode_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_end_to_end_episode_digest(seed))


def _replace_digest(episode: PaperEndToEndEpisode, digest: str) -> PaperEndToEndEpisode:
    fields = _episode_fields(episode)
    fields["episode_digest"] = digest
    return PaperEndToEndEpisode(**fields)  # type: ignore[arg-type]


def _episode_fields(episode: PaperEndToEndEpisode) -> dict[str, object]:
    return {
        "schema_version": episode.schema_version,
        "status": episode.status,
        "ready": episode.ready,
        "episode_id": episode.episode_id,
        "run_id": episode.run_id,
        "correlation_id": episode.correlation_id,
        "strategy_id": episode.strategy_id,
        "strategy_version": episode.strategy_version,
        "market_symbol": episode.market_symbol,
        "side": episode.side,
        "requested_units": episode.requested_units,
        "requested_notional": episode.requested_notional,
        "fill_side": episode.fill_side,
        "filled_units": episode.filled_units,
        "fill_price": episode.fill_price,
        "closed_units": episode.closed_units,
        "residual_open_units": episode.residual_open_units,
        "realized_pnl": episode.realized_pnl,
        "realized_pnl_status": episode.realized_pnl_status,
        "bridge_digest": episode.bridge_digest,
        "paper_order_intent_request_digest": episode.paper_order_intent_request_digest,
        "episode_run_digest": episode.episode_run_digest,
        "order_intent_digest": episode.order_intent_digest,
        "fill_simulation_result_digest": episode.fill_simulation_result_digest,
        "position_transition_digest": episode.position_transition_digest,
        "prior_position_state_digest": episode.prior_position_state_digest,
        "new_position_state_digest": episode.new_position_state_digest,
        "mark_snapshot_digest": episode.mark_snapshot_digest,
        "pnl_report_digest": episode.pnl_report_digest,
        "realized_pnl_event_digest": episode.realized_pnl_event_digest,
        "rejection_reasons": episode.rejection_reasons,
        "metadata": episode.metadata,
    }


def _episode_payload_from(episode: PaperEndToEndEpisode) -> dict[str, object]:
    return {
        "schema_version": episode.schema_version,
        "status": episode.status.value,
        "ready": episode.ready,
        "episode_id": episode.episode_id,
        "run_id": episode.run_id,
        "correlation_id": episode.correlation_id,
        "strategy_id": episode.strategy_id,
        "strategy_version": episode.strategy_version,
        "market_symbol": episode.market_symbol,
        "side": episode.side,
        "requested_units": episode.requested_units,
        "requested_notional": episode.requested_notional,
        "fill_side": episode.fill_side,
        "filled_units": episode.filled_units,
        "fill_price": episode.fill_price,
        "closed_units": episode.closed_units,
        "residual_open_units": episode.residual_open_units,
        "realized_pnl": episode.realized_pnl,
        "realized_pnl_status": episode.realized_pnl_status,
        "bridge_digest": episode.bridge_digest,
        "paper_order_intent_request_digest": episode.paper_order_intent_request_digest,
        "episode_run_digest": episode.episode_run_digest,
        "order_intent_digest": episode.order_intent_digest,
        "fill_simulation_result_digest": episode.fill_simulation_result_digest,
        "position_transition_digest": episode.position_transition_digest,
        "prior_position_state_digest": episode.prior_position_state_digest,
        "new_position_state_digest": episode.new_position_state_digest,
        "mark_snapshot_digest": episode.mark_snapshot_digest,
        "pnl_report_digest": episode.pnl_report_digest,
        "realized_pnl_event_digest": episode.realized_pnl_event_digest,
        "rejection_reasons": list(episode.rejection_reasons),
        "metadata": _serialize_metadata(episode.metadata),
        "paper_only": episode.paper_only,
        "real_orders_enabled": episode.real_orders_enabled,
        "real_money_enabled": episode.real_money_enabled,
        "capital_reserved": episode.capital_reserved,
        "capital_mutated": episode.capital_mutated,
        "balance_mutated": episode.balance_mutated,
        "order_routed": episode.order_routed,
        "venue_order_id_created": episode.venue_order_id_created,
        "exchange_order_id_created": episode.exchange_order_id_created,
        "client_order_id_created": episode.client_order_id_created,
        "route_id_created": episode.route_id_created,
        "execution_instruction_created": episode.execution_instruction_created,
        "execution_authorized": episode.execution_authorized,
        "live_position_mutated": episode.live_position_mutated,
        "live_api_called": episode.live_api_called,
        "scheduler_enabled": episode.scheduler_enabled,
        "auto_loop_enabled": episode.auto_loop_enabled,
        "connector_invoked": episode.connector_invoked,
        "prdv4_stage4_complete": episode.prdv4_stage4_complete,
        "live_ready": episode.live_ready,
        "shadow_ready": episode.shadow_ready,
        "profitability_proven": episode.profitability_proven,
        "edge_proven": episode.edge_proven,
        "production_execution": episode.production_execution,
    }


def paper_end_to_end_episode_to_dict(episode: PaperEndToEndEpisode) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for an episode (deterministic shape, includes self-digest)."""
    payload = _episode_payload_from(episode)
    payload["episode_digest"] = episode.episode_digest
    return payload


def paper_end_to_end_episode_digest(episode: PaperEndToEndEpisode) -> str:
    """Recompute the canonical episode digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_episode_payload_from(episode))


__all__ = [
    "PaperEndToEndEpisode",
    "PaperEndToEndEpisodeError",
    "PaperEndToEndEpisodeStatus",
    "build_paper_end_to_end_episode",
    "paper_end_to_end_episode_digest",
    "paper_end_to_end_episode_to_dict",
]
