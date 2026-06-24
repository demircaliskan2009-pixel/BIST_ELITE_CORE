"""Paper Stage-4 readiness decision — deterministic, paper-only, fail-closed decision over whether the
completed deterministic paper substrate is internally consistent enough to be a *paper-substrate* candidate.

Phase-map slice 7 (``docs/crypto_core/paper_trading_phase_map.md`` §7.7): consume the merged deterministic
paper evidence (the §7.6 ``DeterministicPaperReplayHarnessResult`` proving replay equality + the §7.5
``PaperGovernorDecision`` governance verdict) and render ONE paper-substrate readiness verdict —
``PAPER_STAGE4_CANDIDATE`` / ``PAPER_REVIEW_REQUIRED`` / ``PAPER_BLOCKED``. It is a **validation / audit
decision artifact / probe**, NOT a readiness engine: it runs no backtest, re-runs no strategy/governor/replay,
calls no ``service/readiness``, no ``execution/paper_adapter``, no live/shadow/runtime/venue/connector surface,
schedules nothing, and performs no wall-clock/random/IO. It only re-proves and cross-binds two already-produced
deterministic paper artifacts and applies a static deterministic readiness rule.

Trust boundary (fail-closed): the replay-harness result self-digest is re-proven via the PUBLIC
``deterministic_paper_replay_harness_result_digest`` and the governor decision self-digest via
``paper_governor_decision_digest`` (each stored digest must equal the recompute AND the caller's INDEPENDENT
expected anchor). The two artifacts must describe the SAME paper chain: the governor decision is the original
replayed run, so ``governor.decision_digest == replay.original_decision_digest`` and the governor's embedded
episode / ledger-bridge / manifest / realized-PnL-event / policy digests must equal the replay result's
``original_*`` boundary digests. Both must be paper-safe, non-over-claiming, lineage-proven, and carry the
caller's ids. Static readiness rule, applied only over TRUSTED inputs:

  - replay ``MATCHED`` + governor ``ALLOW_PAPER``   → ``DECIDED`` + ``PAPER_STAGE4_CANDIDATE`` (``ready`` True)
  - replay ``MATCHED`` + governor ``REVIEW_REQUIRED`` → ``DECIDED`` + ``PAPER_REVIEW_REQUIRED``
  - replay ``MATCHED`` + governor ``BLOCK_PAPER``    → ``DECIDED`` + ``PAPER_BLOCKED``
  - replay ``MISMATCHED`` (governor ``DECIDED``)      → ``DECIDED`` + ``PAPER_BLOCKED`` (replay not deterministic)
  - any untrusted / malformed / unsafe / over-claiming / mismatched-chain / non-DECIDED-governor /
    self-``REJECTED``-replay input → ``REJECTED`` + ``PAPER_BLOCKED`` (no partial candidate under any failure).

Non-overclaim: a ``PAPER_STAGE4_CANDIDATE`` proves ONLY that the supplied deterministic paper artifacts are
internally consistent enough to enter the next paper-substrate review. It is NOT PRDV4 Stage 4 completion (which
additionally requires ≥30-day paper trading, paper-vs-backtest metrics, and the Sharpe gate), NOT live readiness,
NOT shadow readiness, NOT production/operational readiness, NOT Deribit/connector/exchange readiness, NOT a
profitability/edge proof, and reserves NO real capital — all carried as explicit ``False`` flags, digest-bound.
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

from crypto_core.validation.deterministic_paper_replay_harness import (
    DeterministicPaperReplayHarnessResult,
    DeterministicPaperReplayHarnessStatus,
    deterministic_paper_replay_harness_result_digest,
)
from crypto_core.validation.paper_governor_decision import (
    PaperGovernorDecision,
    PaperGovernorDecisionStatus,
    PaperGovernorVerdict,
    paper_governor_decision_digest,
)

_SCHEMA_VERSION = "paper-stage4-readiness-decision.v1"
_READINESS_CRITERIA_VERSION = "paper-stage4-readiness-criteria.v1"
_EXPECTED_REPLAY_SCHEMA_VERSION = "deterministic-paper-replay-harness.v1"
_EXPECTED_GOVERNOR_SCHEMA_VERSION = "paper-governor-decision.v1"

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


class PaperStage4ReadinessDecisionError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata)."""


class PaperStage4ReadinessStatus(str, Enum):
    """Whether a trusted readiness decision could be rendered. Never an execution / live / readiness action."""

    DECIDED = "DECIDED"
    REJECTED = "REJECTED"


class PaperStage4ReadinessVerdict(str, Enum):
    """Paper-substrate readiness verdict. Never live/shadow/production/Deribit/real-capital readiness."""

    PAPER_STAGE4_CANDIDATE = "PAPER_STAGE4_CANDIDATE"
    PAPER_REVIEW_REQUIRED = "PAPER_REVIEW_REQUIRED"
    PAPER_BLOCKED = "PAPER_BLOCKED"


@dataclass(frozen=True)
class PaperStage4ReadinessDecision:
    """Deterministic, immutable, digest-bound paper-substrate readiness decision over the deterministic paper chain.

    ``status`` DECIDED only when both consumed artifacts re-prove + cross-bind to the same chain and are trusted;
    otherwise REJECTED. ``verdict`` is the paper-substrate readiness outcome; ``ready`` True only for
    ``PAPER_STAGE4_CANDIDATE``. ``paper_only`` True; every safety / non-overclaim attestation False. PAPER
    SUBSTRATE ONLY — NOT PRDV4 Stage 4 completion, NOT live/shadow/production readiness, NOT Deribit/connector
    readiness, NOT a profitability/edge proof.
    """

    schema_version: str
    readiness_criteria_version: str
    status: PaperStage4ReadinessStatus
    decided: bool
    verdict: PaperStage4ReadinessVerdict
    ready: bool
    run_id: str
    episode_id: str
    correlation_id: str
    market_symbol: str
    expected_replay_result_digest: str
    expected_governor_decision_digest: str
    replay_result_digest: str
    replay_status: str
    replay_matched: bool
    governor_decision_digest: str
    governor_status: str
    governor_verdict: str
    episode_digest: str
    ledger_bridge_digest: str
    manifest_digest: str
    realized_pnl_event_digest: str
    policy_digest: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    readiness_decision_digest: str
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
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    deribit_ready: bool = False
    operational_readiness: bool = False


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


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperStage4ReadinessDecisionError("paper_stage4_readiness_decision:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperStage4ReadinessDecisionError("paper_stage4_readiness_decision:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperStage4ReadinessDecisionError("paper_stage4_readiness_decision:metadata_malformed")
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


def _replay_result_is_paper_safe(replay_result: DeterministicPaperReplayHarnessResult) -> bool:
    return (
        replay_result.paper_only is True
        and replay_result.prdv4_stage4_complete is False
        and replay_result.live_ready is False
        and replay_result.shadow_ready is False
        and replay_result.profitability_proven is False
        and replay_result.edge_proven is False
        and replay_result.production_execution is False
        and replay_result.real_orders_enabled is False
        and replay_result.real_money_enabled is False
        and replay_result.real_capital_reserved is False
        and replay_result.order_routed is False
        and replay_result.execution_authorized is False
        and replay_result.live_api_called is False
        and replay_result.scheduler_enabled is False
        and replay_result.auto_loop_enabled is False
        and replay_result.connector_invoked is False
    )


def _governor_is_paper_safe(governor: PaperGovernorDecision) -> bool:
    return (
        governor.paper_only is True
        and governor.real_orders_enabled is False
        and governor.real_money_enabled is False
        and governor.real_capital_reserved is False
        and governor.order_routed is False
        and governor.execution_authorized is False
        and governor.live_api_called is False
        and governor.scheduler_enabled is False
        and governor.auto_loop_enabled is False
        and governor.connector_invoked is False
        and governor.prdv4_stage4_complete is False
        and governor.live_ready is False
        and governor.shadow_ready is False
        and governor.profitability_proven is False
        and governor.edge_proven is False
        and governor.production_execution is False
    )


def _reprove_self_digest(artifact: object, recompute, stored: object, expected: str, label: str) -> str | None:
    """Re-prove an artifact's self-digest via its PUBLIC serializer AND the caller anchor. Reason or ``None``."""
    try:
        recomputed = recompute(artifact)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return f"paper_stage4_readiness_decision:{label}_malformed"
    if not _is_hex64_string(stored) or stored != recomputed or stored != expected:
        return f"paper_stage4_readiness_decision:{label}_digest_mismatch"
    return None


def decide_paper_stage4_readiness(
    replay_result: DeterministicPaperReplayHarnessResult,
    governor_decision: PaperGovernorDecision,
    *,
    expected_replay_result_digest: str,
    expected_governor_decision_digest: str,
    run_id: str,
    episode_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperStage4ReadinessDecision:
    """Render a deterministic paper-substrate readiness verdict over a replay-harness result + governor decision.

    ``replay_result`` must be a ``DeterministicPaperReplayHarnessResult`` and ``governor_decision`` a
    ``PaperGovernorDecision``; ``expected_replay_result_digest`` / ``expected_governor_decision_digest`` exact
    plain 64-lowercase-hex ``str`` (the caller's INDEPENDENT anchors); ``run_id`` / ``episode_id`` /
    ``correlation_id`` exact plain non-empty ``str`` (both artifacts must carry these ids); ``metadata``
    ``Mapping[str, str]`` or ``None``. A wrong type, malformed digest, empty id, a forbidden BIST/live/order
    token, or malformed metadata raises ``PaperStage4ReadinessDecisionError`` before any work.

    Each artifact self-digest is re-proven via its PUBLIC serializer (== stored == expected anchor); both must be
    paper-safe + non-over-claiming, the governor DECIDED + lineage-proven, the replay a self-consistent terminal
    result, and both must describe the SAME chain (``governor.decision_digest == replay.original_decision_digest``
    and the governor's embedded boundary digests == the replay ``original_*`` digests). Only over fully trusted
    inputs does the static rule decide: replay MATCHED + governor ALLOW_PAPER → PAPER_STAGE4_CANDIDATE; MATCHED +
    REVIEW_REQUIRED → PAPER_REVIEW_REQUIRED; MATCHED + BLOCK_PAPER → PAPER_BLOCKED; replay MISMATCHED →
    PAPER_BLOCKED. Any trust failure maps to ``status=REJECTED`` + ``PAPER_BLOCKED`` (no partial candidate).
    Deterministic and immutable; no wall-clock/random/IO; paper only; reserves NO real capital; inputs unmutated.
    """
    if not isinstance(replay_result, DeterministicPaperReplayHarnessResult):
        raise PaperStage4ReadinessDecisionError("paper_stage4_readiness_decision:replay_result_malformed")
    if not isinstance(governor_decision, PaperGovernorDecision):
        raise PaperStage4ReadinessDecisionError("paper_stage4_readiness_decision:governor_decision_malformed")
    if not _is_hex64_string(expected_replay_result_digest):
        raise PaperStage4ReadinessDecisionError("paper_stage4_readiness_decision:expected_replay_result_digest_invalid")
    if not _is_hex64_string(expected_governor_decision_digest):
        raise PaperStage4ReadinessDecisionError(
            "paper_stage4_readiness_decision:expected_governor_decision_digest_invalid"
        )
    for name, value in (("episode_id", episode_id), ("run_id", run_id), ("correlation_id", correlation_id)):
        if not _is_plain_non_empty_string(value):
            raise PaperStage4ReadinessDecisionError(f"paper_stage4_readiness_decision:{name}_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(episode_id, run_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperStage4ReadinessDecisionError("paper_stage4_readiness_decision:scope_violation")

    hard: list[str] = []

    # Trust boundaries: re-prove each artifact's self-digest via its PUBLIC serializer AND the caller anchor.
    replay_reason = _reprove_self_digest(
        replay_result,
        deterministic_paper_replay_harness_result_digest,
        replay_result.replay_result_digest,
        expected_replay_result_digest,
        "replay_result",
    )
    if replay_reason is not None:
        hard.append(replay_reason)
    governor_reason = _reprove_self_digest(
        governor_decision,
        paper_governor_decision_digest,
        governor_decision.decision_digest,
        expected_governor_decision_digest,
        "governor_decision",
    )
    if governor_reason is not None:
        hard.append(governor_reason)

    # Schema + safety + non-overclaim per artifact.
    if replay_result.schema_version != _EXPECTED_REPLAY_SCHEMA_VERSION:
        hard.append("paper_stage4_readiness_decision:replay_result_schema_invalid")
    if governor_decision.schema_version != _EXPECTED_GOVERNOR_SCHEMA_VERSION:
        hard.append("paper_stage4_readiness_decision:governor_decision_schema_invalid")
    if not _replay_result_is_paper_safe(replay_result):
        hard.append("paper_stage4_readiness_decision:replay_result_unsafe_flags")
    if not _governor_is_paper_safe(governor_decision):
        hard.append("paper_stage4_readiness_decision:governor_decision_unsafe_flags")

    # Replay terminal-state trust + status/matched/ready self-consistency.
    replay_status = replay_result.status
    if not isinstance(replay_status, DeterministicPaperReplayHarnessStatus):
        hard.append("paper_stage4_readiness_decision:replay_result_status_invalid")
        replay_status = None
    elif replay_status is DeterministicPaperReplayHarnessStatus.MATCHED:
        if replay_result.matched is not True or replay_result.ready is not True:
            hard.append("paper_stage4_readiness_decision:replay_result_inconsistent")
    elif replay_status is DeterministicPaperReplayHarnessStatus.MISMATCHED:
        if replay_result.matched is not False or replay_result.ready is not False:
            hard.append("paper_stage4_readiness_decision:replay_result_inconsistent")
    else:  # the replay harness itself REJECTED its inputs -> not trustworthy readiness evidence
        hard.append("paper_stage4_readiness_decision:replay_result_not_trusted")

    # Governor must be a trusted DECIDED verdict with proven lineage.
    if not (
        isinstance(governor_decision.status, PaperGovernorDecisionStatus)
        and governor_decision.status is PaperGovernorDecisionStatus.DECIDED
        and governor_decision.decided is True
    ):
        hard.append("paper_stage4_readiness_decision:governor_decision_not_decided")
    if not _is_int(governor_decision.source_event_digest_count) or governor_decision.source_event_digest_count < 1:
        hard.append("paper_stage4_readiness_decision:governor_decision_lineage_unproven")

    # Caller ids must match BOTH artifacts.
    if _plain_str_or_empty(replay_result.run_id) != run_id:
        hard.append("paper_stage4_readiness_decision:replay_run_id_mismatch")
    if _plain_str_or_empty(replay_result.episode_id) != episode_id:
        hard.append("paper_stage4_readiness_decision:replay_episode_id_mismatch")
    if _plain_str_or_empty(replay_result.correlation_id) != correlation_id:
        hard.append("paper_stage4_readiness_decision:replay_correlation_id_mismatch")
    if _plain_str_or_empty(governor_decision.run_id) != run_id:
        hard.append("paper_stage4_readiness_decision:governor_run_id_mismatch")
    if _plain_str_or_empty(governor_decision.episode_id) != episode_id:
        hard.append("paper_stage4_readiness_decision:governor_episode_id_mismatch")
    if _plain_str_or_empty(governor_decision.correlation_id) != correlation_id:
        hard.append("paper_stage4_readiness_decision:governor_correlation_id_mismatch")

    # Same-chain binding: the governor decision IS the original replayed run, so its self-digest and every
    # embedded boundary digest must equal the replay result's ORIGINAL-side digests. A divergence means the two
    # artifacts describe different paper chains (or one was tampered) -> fail closed.
    chain_pairs: tuple[tuple[str, object, object], ...] = (
        ("decision", governor_decision.decision_digest, replay_result.original_decision_digest),
        ("episode_digest", governor_decision.episode_digest, replay_result.original_episode_digest),
        ("ledger_bridge_digest", governor_decision.ledger_bridge_digest, replay_result.original_ledger_bridge_digest),
        ("manifest_digest", governor_decision.manifest_digest, replay_result.original_manifest_digest),
        (
            "realized_pnl_event_digest",
            governor_decision.realized_pnl_event_digest,
            replay_result.original_realized_pnl_event_digest,
        ),
        ("policy_digest", governor_decision.policy_digest, replay_result.original_policy_digest),
    )
    for name, governor_value, replay_value in chain_pairs:
        if _plain_str_or_empty(governor_value) == "" or _plain_str_or_empty(governor_value) != _plain_str_or_empty(
            replay_value
        ):
            hard.append(f"paper_stage4_readiness_decision:replay_governor_{name}_mismatch")

    if hard:
        status = PaperStage4ReadinessStatus.REJECTED
        verdict = PaperStage4ReadinessVerdict.PAPER_BLOCKED
        reason_codes = tuple(sorted(set(hard)))
    elif replay_status is DeterministicPaperReplayHarnessStatus.MISMATCHED:
        status = PaperStage4ReadinessStatus.DECIDED
        verdict = PaperStage4ReadinessVerdict.PAPER_BLOCKED
        reason_codes = ("paper_stage4_readiness_decision:replay_not_matched",)
    else:  # replay MATCHED + governor DECIDED + fully trusted -> the governor verdict drives readiness
        governor_verdict = governor_decision.decision
        status = PaperStage4ReadinessStatus.DECIDED
        if governor_verdict is PaperGovernorVerdict.ALLOW_PAPER:
            verdict = PaperStage4ReadinessVerdict.PAPER_STAGE4_CANDIDATE
            reason_codes = ()
        elif governor_verdict is PaperGovernorVerdict.REVIEW_REQUIRED:
            verdict = PaperStage4ReadinessVerdict.PAPER_REVIEW_REQUIRED
            reason_codes = ("paper_stage4_readiness_decision:governor_review_required",)
        elif governor_verdict is PaperGovernorVerdict.BLOCK_PAPER:
            verdict = PaperStage4ReadinessVerdict.PAPER_BLOCKED
            reason_codes = ("paper_stage4_readiness_decision:governor_block_paper",)
        else:  # unknown verdict enum -> untrusted, fail closed
            status = PaperStage4ReadinessStatus.REJECTED
            verdict = PaperStage4ReadinessVerdict.PAPER_BLOCKED
            reason_codes = ("paper_stage4_readiness_decision:governor_verdict_invalid",)

    return _finalize_decision(
        status=status,
        verdict=verdict,
        replay_result=replay_result,
        governor_decision=governor_decision,
        expected_replay_result_digest=expected_replay_result_digest,
        expected_governor_decision_digest=expected_governor_decision_digest,
        run_id=run_id,
        episode_id=episode_id,
        correlation_id=correlation_id,
        reason_codes=reason_codes,
        metadata=metadata_pairs,
    )


def _finalize_decision(
    *,
    status: PaperStage4ReadinessStatus,
    verdict: PaperStage4ReadinessVerdict,
    replay_result: DeterministicPaperReplayHarnessResult,
    governor_decision: PaperGovernorDecision,
    expected_replay_result_digest: str,
    expected_governor_decision_digest: str,
    run_id: str,
    episode_id: str,
    correlation_id: str,
    reason_codes: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperStage4ReadinessDecision:
    replay_status = (
        replay_result.status.value if isinstance(replay_result.status, DeterministicPaperReplayHarnessStatus) else ""
    )
    governor_status = (
        governor_decision.status.value if isinstance(governor_decision.status, PaperGovernorDecisionStatus) else ""
    )
    governor_verdict = (
        governor_decision.decision.value if isinstance(governor_decision.decision, PaperGovernorVerdict) else ""
    )
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "readiness_criteria_version": _READINESS_CRITERIA_VERSION,
        "status": status,
        "decided": status is PaperStage4ReadinessStatus.DECIDED,
        "verdict": verdict,
        "ready": verdict is PaperStage4ReadinessVerdict.PAPER_STAGE4_CANDIDATE,
        "run_id": run_id,
        "episode_id": episode_id,
        "correlation_id": correlation_id,
        "market_symbol": _plain_str_or_empty(governor_decision.market_symbol),
        "expected_replay_result_digest": expected_replay_result_digest,
        "expected_governor_decision_digest": expected_governor_decision_digest,
        "replay_result_digest": _plain_str_or_empty(replay_result.replay_result_digest),
        "replay_status": replay_status,
        "replay_matched": replay_result.matched if type(replay_result.matched) is bool else False,
        "governor_decision_digest": _plain_str_or_empty(governor_decision.decision_digest),
        "governor_status": governor_status,
        "governor_verdict": governor_verdict,
        "episode_digest": _plain_str_or_empty(governor_decision.episode_digest),
        "ledger_bridge_digest": _plain_str_or_empty(governor_decision.ledger_bridge_digest),
        "manifest_digest": _plain_str_or_empty(governor_decision.manifest_digest),
        "realized_pnl_event_digest": _plain_str_or_empty(governor_decision.realized_pnl_event_digest),
        "policy_digest": _plain_str_or_empty(governor_decision.policy_digest),
        "reason_codes": reason_codes,
        "metadata": metadata,
    }
    seed = PaperStage4ReadinessDecision(readiness_decision_digest="", **fields)  # type: ignore[arg-type]
    return _replace_decision_digest(seed, paper_stage4_readiness_decision_digest(seed))


def _replace_decision_digest(decision: PaperStage4ReadinessDecision, digest: str) -> PaperStage4ReadinessDecision:
    fields = _decision_fields(decision)
    fields["readiness_decision_digest"] = digest
    return PaperStage4ReadinessDecision(**fields)  # type: ignore[arg-type]


def _decision_fields(decision: PaperStage4ReadinessDecision) -> dict[str, object]:
    return {
        "schema_version": decision.schema_version,
        "readiness_criteria_version": decision.readiness_criteria_version,
        "status": decision.status,
        "decided": decision.decided,
        "verdict": decision.verdict,
        "ready": decision.ready,
        "run_id": decision.run_id,
        "episode_id": decision.episode_id,
        "correlation_id": decision.correlation_id,
        "market_symbol": decision.market_symbol,
        "expected_replay_result_digest": decision.expected_replay_result_digest,
        "expected_governor_decision_digest": decision.expected_governor_decision_digest,
        "replay_result_digest": decision.replay_result_digest,
        "replay_status": decision.replay_status,
        "replay_matched": decision.replay_matched,
        "governor_decision_digest": decision.governor_decision_digest,
        "governor_status": decision.governor_status,
        "governor_verdict": decision.governor_verdict,
        "episode_digest": decision.episode_digest,
        "ledger_bridge_digest": decision.ledger_bridge_digest,
        "manifest_digest": decision.manifest_digest,
        "realized_pnl_event_digest": decision.realized_pnl_event_digest,
        "policy_digest": decision.policy_digest,
        "reason_codes": decision.reason_codes,
        "metadata": decision.metadata,
    }


def _decision_payload_from(decision: PaperStage4ReadinessDecision) -> dict[str, object]:
    return {
        "schema_version": decision.schema_version,
        "readiness_criteria_version": decision.readiness_criteria_version,
        "status": decision.status.value,
        "decided": decision.decided,
        "verdict": decision.verdict.value,
        "ready": decision.ready,
        "run_id": decision.run_id,
        "episode_id": decision.episode_id,
        "correlation_id": decision.correlation_id,
        "market_symbol": decision.market_symbol,
        "expected_replay_result_digest": decision.expected_replay_result_digest,
        "expected_governor_decision_digest": decision.expected_governor_decision_digest,
        "replay_result_digest": decision.replay_result_digest,
        "replay_status": decision.replay_status,
        "replay_matched": decision.replay_matched,
        "governor_decision_digest": decision.governor_decision_digest,
        "governor_status": decision.governor_status,
        "governor_verdict": decision.governor_verdict,
        "episode_digest": decision.episode_digest,
        "ledger_bridge_digest": decision.ledger_bridge_digest,
        "manifest_digest": decision.manifest_digest,
        "realized_pnl_event_digest": decision.realized_pnl_event_digest,
        "policy_digest": decision.policy_digest,
        "reason_codes": list(decision.reason_codes),
        "metadata": _serialize_metadata(decision.metadata),
        "paper_only": decision.paper_only,
        "prdv4_stage4_complete": decision.prdv4_stage4_complete,
        "live_ready": decision.live_ready,
        "shadow_ready": decision.shadow_ready,
        "profitability_proven": decision.profitability_proven,
        "edge_proven": decision.edge_proven,
        "production_execution": decision.production_execution,
        "real_orders_enabled": decision.real_orders_enabled,
        "real_money_enabled": decision.real_money_enabled,
        "real_capital_reserved": decision.real_capital_reserved,
        "live_api_called": decision.live_api_called,
        "scheduler_enabled": decision.scheduler_enabled,
        "auto_loop_enabled": decision.auto_loop_enabled,
        "connector_invoked": decision.connector_invoked,
        "deribit_ready": decision.deribit_ready,
        "operational_readiness": decision.operational_readiness,
    }


def paper_stage4_readiness_decision_to_dict(decision: PaperStage4ReadinessDecision) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for a decision (deterministic shape, includes self-digest)."""
    payload = _decision_payload_from(decision)
    payload["readiness_decision_digest"] = decision.readiness_decision_digest
    return payload


def paper_stage4_readiness_decision_digest(decision: PaperStage4ReadinessDecision) -> str:
    """Recompute the canonical decision digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_decision_payload_from(decision))


__all__ = [
    "PaperStage4ReadinessDecision",
    "PaperStage4ReadinessDecisionError",
    "PaperStage4ReadinessStatus",
    "PaperStage4ReadinessVerdict",
    "decide_paper_stage4_readiness",
    "paper_stage4_readiness_decision_digest",
    "paper_stage4_readiness_decision_to_dict",
]
