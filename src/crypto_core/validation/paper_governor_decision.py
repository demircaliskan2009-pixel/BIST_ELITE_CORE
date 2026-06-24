"""Paper governor decision — deterministic, paper-only, fail-closed governance verdict over a READY
``PaperAdmissionLedgerBridge`` against a static, digest-bound policy snapshot.

Phase-map slice 5 (``docs/crypto_core/paper_trading_phase_map.md`` §7.5): a **paper-only** risk / governor
decision artifact — **no real capital / equity / margin / balance / reservation**. It is a *validation /
audit decision artifact / probe*, NOT a real risk engine and NOT a live execution gate. It consumes the
already-proven paper evidence chain (the ``PaperAdmissionLedgerBridge`` — which transitively bound the
episode → fill → realized-PnL → admission → journal lineage) plus a deterministic ``PaperGovernorPolicy``
snapshot, and renders one paper-only verdict: ``ALLOW_PAPER`` / ``REVIEW_REQUIRED`` / ``BLOCK_PAPER``.

It models no account: it reserves no real capital, computes no real equity/margin/balance, routes no order,
calls no live/private API, schedules nothing, and performs no wall-clock/random/IO/network/persistence. Its
rules are static deterministic thresholds over the bridge's already-bound GROSS paper figures
(``realized_pnl_total`` magnitude, ``closed_units_total``, ``computed_event_count``) — sanity governance,
not a capital/risk model.

Trust boundary (fail-closed): the bridge self-digest is re-proven via the PUBLIC
``paper_admission_ledger_bridge_digest`` and must equal the bridge's stored ``ledger_digest`` AND the
caller's independent ``expected_ledger_bridge_digest``; the policy self-digest is re-proven via
``paper_governor_policy_digest``. Any digest mismatch, a non-READY / non-appended / unsafe / over-claiming
bridge, an unproven lineage (``source_event_digest_count`` < 1), a run/episode/correlation mismatch, a
malformed policy, or malformed bridge totals maps to ``status=REJECTED`` with ``decision=BLOCK_PAPER`` (the
input is untrusted, so the only safe verdict is BLOCK). Only a fully re-proven bridge yields
``status=DECIDED``, after which the static policy decides ALLOW / REVIEW / BLOCK. No partial ALLOW. Call-level
malformed input (wrong-typed bridge/policy, malformed expected digest, empty/forbidden ids, malformed
metadata) raises ``PaperGovernorDecisionError`` before any work.

Non-overclaim: a paper governor decision proves none of PRDV4 Stage 4 completion, live readiness, shadow
readiness, profitability, edge, or production execution, and reserves NO real capital — all carried as
explicit ``False`` flags, digest-bound. It does NOT import or use ``crypto_core.service.readiness`` or
``crypto_core.execution.paper_adapter`` (or any shadow/live/runtime/venue surface), no Deribit, no BIST.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_admission_ledger_bridge import (
    PaperAdmissionLedgerBridge,
    PaperAdmissionLedgerBridgeStatus,
    paper_admission_ledger_bridge_digest,
)

_DECISION_SCHEMA_VERSION = "paper-governor-decision.v1"
_POLICY_SCHEMA_VERSION = "paper-governor-policy.v1"
_EXPECTED_BRIDGE_SCHEMA_VERSION = "paper-admission-ledger-bridge.v1"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Strict decimal-string grammar (mirrors the sibling realized-PnL modules): optional sign, no leading zeros
# (except a bare ``0``), optional fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

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


class PaperGovernorDecisionError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed bridge/policy / ids / digests / metadata)."""


class PaperGovernorPolicyError(RuntimeError):
    """Raised when a paper governor policy is built from malformed thresholds / ids / metadata."""


class PaperGovernorDecisionStatus(str, Enum):
    """Whether a trusted decision could be rendered. Never an execution / capital / live action."""

    DECIDED = "DECIDED"
    REJECTED = "REJECTED"


class PaperGovernorVerdict(str, Enum):
    """Paper-only governance verdict. Never a real-capital reservation or live execution authorization."""

    ALLOW_PAPER = "ALLOW_PAPER"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCK_PAPER = "BLOCK_PAPER"


@dataclass(frozen=True)
class PaperGovernorPolicy:
    """Deterministic, immutable, digest-bound static paper governance policy snapshot.

    Thresholds are over GROSS paper figures only — no real capital/equity/margin/balance. ``paper_only`` True.
    """

    schema_version: str
    policy_id: str
    min_computed_event_count: int
    max_abs_realized_pnl: str
    review_abs_realized_pnl: str
    max_closed_units: str
    metadata: tuple[tuple[str, str], ...]
    policy_digest: str
    paper_only: bool = True
    real_capital_modeled: bool = False


@dataclass(frozen=True)
class PaperGovernorDecision:
    """Deterministic, immutable, digest-bound paper-only governance decision over one admission ledger bridge.

    ``status`` DECIDED only when the bridge + policy fully re-prove; otherwise REJECTED. ``decision`` is the
    paper-only verdict (ALLOW_PAPER / REVIEW_REQUIRED / BLOCK_PAPER); an untrusted input is always BLOCK_PAPER.
    ``paper_only`` True; every safety / non-overclaim attestation False (incl. ``real_capital_reserved``).
    PAPER ONLY — NOT PRDV4 Stage 4 completion, NOT live/shadow readiness, NOT profitability/edge proof.
    """

    schema_version: str
    status: PaperGovernorDecisionStatus
    decided: bool
    decision: PaperGovernorVerdict
    allowed: bool
    run_id: str
    episode_id: str
    correlation_id: str
    market_symbol: str
    ledger_bridge_digest: str
    expected_ledger_bridge_digest: str
    ledger_bridge_status: str
    policy_id: str
    policy_digest: str
    episode_digest: str
    manifest_digest: str
    realized_pnl_event_digest: str
    realized_pnl_total: str
    closed_units_total: str
    computed_event_count: int
    source_event_digest_count: int
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    decision_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    order_routed: bool = False
    execution_authorized: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
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
    return type(value) is str and value.strip() != ""


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _plain_str_or_empty(value: object) -> str:
    return value if type(value) is str else ""


def _normalize_metadata(metadata: object, error: type[RuntimeError], reason: str) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise error(reason)
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise error(reason)
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(
    metadata: tuple[tuple[str, str], ...], error: type[RuntimeError], reason: str
) -> list[list[str]]:
    pairs: list[list[str]] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise error(reason)
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


def _parse_decimal(value: object) -> Decimal | None:
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _render_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _canonical_decimal(value: object) -> Decimal | None:
    """Parse a strict decimal string that is ALSO already in canonical render form, else ``None``."""
    parsed = _parse_decimal(value)
    if parsed is None or _render_decimal(parsed) != value:
        return None
    return parsed


# --------------------------------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------------------------------


def build_paper_governor_policy(
    *,
    policy_id: str,
    min_computed_event_count: int,
    max_abs_realized_pnl: str,
    review_abs_realized_pnl: str,
    max_closed_units: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperGovernorPolicy:
    """Build a deterministic, digest-bound static paper governance policy snapshot.

    Thresholds are GROSS paper bounds only (no real capital/equity/margin). ``max_abs_realized_pnl`` /
    ``review_abs_realized_pnl`` / ``max_closed_units`` must be canonical non-negative decimal strings with
    ``review_abs_realized_pnl <= max_abs_realized_pnl``; ``min_computed_event_count`` a non-negative ``int``.
    A malformed id/threshold/metadata or a forbidden token raises ``PaperGovernorPolicyError``.
    """
    if not _is_plain_non_empty_string(policy_id):
        raise PaperGovernorPolicyError("paper_governor_policy:policy_id_invalid")
    if not _is_int(min_computed_event_count) or min_computed_event_count < 0:
        raise PaperGovernorPolicyError("paper_governor_policy:min_computed_event_count_invalid")
    max_abs = _canonical_decimal(max_abs_realized_pnl)
    review_abs = _canonical_decimal(review_abs_realized_pnl)
    max_units = _canonical_decimal(max_closed_units)
    if max_abs is None or max_abs < 0:
        raise PaperGovernorPolicyError("paper_governor_policy:max_abs_realized_pnl_invalid")
    if review_abs is None or review_abs < 0:
        raise PaperGovernorPolicyError("paper_governor_policy:review_abs_realized_pnl_invalid")
    if max_units is None or max_units < 0:
        raise PaperGovernorPolicyError("paper_governor_policy:max_closed_units_invalid")
    if review_abs > max_abs:
        raise PaperGovernorPolicyError("paper_governor_policy:review_threshold_exceeds_block_threshold")
    metadata_pairs = _normalize_metadata(metadata, PaperGovernorPolicyError, "paper_governor_policy:metadata_malformed")
    if _has_scope_violation(policy_id, *_metadata_texts(metadata_pairs)):
        raise PaperGovernorPolicyError("paper_governor_policy:scope_violation")

    seed = PaperGovernorPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        min_computed_event_count=min_computed_event_count,
        max_abs_realized_pnl=max_abs_realized_pnl,
        review_abs_realized_pnl=review_abs_realized_pnl,
        max_closed_units=max_closed_units,
        metadata=metadata_pairs,
        policy_digest="",
    )
    return _replace_policy_digest(seed, paper_governor_policy_digest(seed))


def _replace_policy_digest(policy: PaperGovernorPolicy, digest: str) -> PaperGovernorPolicy:
    return PaperGovernorPolicy(
        schema_version=policy.schema_version,
        policy_id=policy.policy_id,
        min_computed_event_count=policy.min_computed_event_count,
        max_abs_realized_pnl=policy.max_abs_realized_pnl,
        review_abs_realized_pnl=policy.review_abs_realized_pnl,
        max_closed_units=policy.max_closed_units,
        metadata=policy.metadata,
        policy_digest=digest,
        paper_only=policy.paper_only,
        real_capital_modeled=policy.real_capital_modeled,
    )


def _policy_payload_from(policy: PaperGovernorPolicy) -> dict[str, object]:
    return {
        "schema_version": policy.schema_version,
        "policy_id": policy.policy_id,
        "min_computed_event_count": policy.min_computed_event_count,
        "max_abs_realized_pnl": policy.max_abs_realized_pnl,
        "review_abs_realized_pnl": policy.review_abs_realized_pnl,
        "max_closed_units": policy.max_closed_units,
        "metadata": _serialize_metadata(
            policy.metadata, PaperGovernorPolicyError, "paper_governor_policy:metadata_malformed"
        ),
        "paper_only": policy.paper_only,
        "real_capital_modeled": policy.real_capital_modeled,
    }


def paper_governor_policy_to_dict(policy: PaperGovernorPolicy) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a policy (deterministic shape, includes self-digest)."""
    payload = _policy_payload_from(policy)
    payload["policy_digest"] = policy.policy_digest
    return payload


def paper_governor_policy_digest(policy: PaperGovernorPolicy) -> str:
    """Recompute the canonical policy digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_policy_payload_from(policy))


# --------------------------------------------------------------------------------------------------
# Decision
# --------------------------------------------------------------------------------------------------


def _bridge_is_paper_safe(bridge: PaperAdmissionLedgerBridge) -> bool:
    return (
        bridge.paper_only is True
        and bridge.real_orders_enabled is False
        and bridge.real_money_enabled is False
        and bridge.capital_reserved is False
        and bridge.capital_mutated is False
        and bridge.balance_mutated is False
        and bridge.order_routed is False
        and bridge.venue_order_id_created is False
        and bridge.exchange_order_id_created is False
        and bridge.client_order_id_created is False
        and bridge.route_id_created is False
        and bridge.execution_instruction_created is False
        and bridge.execution_authorized is False
        and bridge.live_position_mutated is False
        and bridge.live_api_called is False
        and bridge.scheduler_enabled is False
        and bridge.auto_loop_enabled is False
        and bridge.connector_invoked is False
        and bridge.prdv4_stage4_complete is False
        and bridge.live_ready is False
        and bridge.shadow_ready is False
        and bridge.profitability_proven is False
        and bridge.edge_proven is False
        and bridge.production_execution is False
    )


def decide_paper_governor(
    ledger_bridge: PaperAdmissionLedgerBridge,
    policy: PaperGovernorPolicy,
    *,
    expected_ledger_bridge_digest: str,
    episode_id: str,
    run_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperGovernorDecision:
    """Render a deterministic, paper-only governance verdict over one READY ``PaperAdmissionLedgerBridge``.

    ``ledger_bridge`` must be a ``PaperAdmissionLedgerBridge`` and ``policy`` a ``PaperGovernorPolicy``;
    ``expected_ledger_bridge_digest`` an exact plain 64-lowercase-hex ``str`` (the caller's INDEPENDENT
    anchor); ``episode_id`` / ``run_id`` / ``correlation_id`` exact plain non-empty ``str``; ``metadata``
    ``Mapping[str, str]`` or ``None``. A wrong type, malformed digest, empty id, a forbidden BIST/live/order
    token, or malformed metadata raises ``PaperGovernorDecisionError`` before any work.

    The bridge self-digest is re-proven (``paper_admission_ledger_bridge_digest`` == stored ``ledger_digest``
    == ``expected_ledger_bridge_digest``) and the policy self-digest re-proven. Status is DECIDED only when the
    bridge is READY + appended + paper-safe + non-over-claiming + lineage-proven (``source_event_digest_count``
    >= 1) and its run/episode/correlation match the caller anchors and the policy + bridge totals are
    well-formed; then the static policy decides ALLOW_PAPER (all gross thresholds satisfied), REVIEW_REQUIRED
    (soft realized-PnL boundary), or BLOCK_PAPER (a hard gross threshold fails). Any trust failure maps to
    status REJECTED + decision BLOCK_PAPER (no partial ALLOW). Deterministic and immutable; no
    wall-clock/random/IO; paper only; reserves NO real capital.
    """
    if not isinstance(ledger_bridge, PaperAdmissionLedgerBridge):
        raise PaperGovernorDecisionError("paper_governor_decision:ledger_bridge_malformed")
    if not isinstance(policy, PaperGovernorPolicy):
        raise PaperGovernorDecisionError("paper_governor_decision:policy_malformed")
    if not _is_hex64_string(expected_ledger_bridge_digest):
        raise PaperGovernorDecisionError("paper_governor_decision:expected_ledger_bridge_digest_invalid")
    for name, value in (("episode_id", episode_id), ("run_id", run_id), ("correlation_id", correlation_id)):
        if not _is_plain_non_empty_string(value):
            raise PaperGovernorDecisionError(f"paper_governor_decision:{name}_invalid")
    metadata_pairs = _normalize_metadata(
        metadata, PaperGovernorDecisionError, "paper_governor_decision:metadata_malformed"
    )
    if _has_scope_violation(episode_id, run_id, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperGovernorDecisionError("paper_governor_decision:scope_violation")

    hard: list[str] = []

    # Trust boundary: re-prove the bridge self-digest via its PUBLIC serializer AND the caller anchor.
    try:
        recomputed_bridge = paper_admission_ledger_bridge_digest(ledger_bridge)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        recomputed_bridge = None
    stored_bridge = ledger_bridge.ledger_digest
    if recomputed_bridge is None:
        hard.append("paper_governor_decision:ledger_bridge_malformed")
    elif (
        not _is_hex64_string(stored_bridge)
        or stored_bridge != recomputed_bridge
        or stored_bridge != expected_ledger_bridge_digest
    ):
        hard.append("paper_governor_decision:ledger_bridge_digest_mismatch")

    # Policy self-digest re-proof (a tampered policy is untrusted -> fail closed).
    try:
        recomputed_policy = paper_governor_policy_digest(policy)
    except Exception:  # noqa: BLE001
        recomputed_policy = None
    if (
        recomputed_policy is None
        or not _is_hex64_string(policy.policy_digest)
        or policy.policy_digest != recomputed_policy
    ):
        hard.append("paper_governor_decision:policy_digest_mismatch")
    if (
        policy.schema_version != _POLICY_SCHEMA_VERSION
        or policy.paper_only is not True
        or policy.real_capital_modeled is not False
    ):
        hard.append("paper_governor_decision:policy_invalid")

    # Bridge schema + status + completeness + paper-safety + lineage.
    if ledger_bridge.schema_version != _EXPECTED_BRIDGE_SCHEMA_VERSION:
        hard.append("paper_governor_decision:ledger_bridge_schema_invalid")
    elif ledger_bridge.status is not PaperAdmissionLedgerBridgeStatus.READY or ledger_bridge.ready is not True:
        hard.append("paper_governor_decision:ledger_bridge_not_ready")
    if ledger_bridge.appended is not True:
        hard.append("paper_governor_decision:ledger_bridge_not_appended")
    if not _bridge_is_paper_safe(ledger_bridge):
        hard.append("paper_governor_decision:ledger_bridge_unsafe_flags")
    if not _is_int(ledger_bridge.source_event_digest_count) or ledger_bridge.source_event_digest_count < 1:
        hard.append("paper_governor_decision:ledger_bridge_lineage_unproven")

    # Cross-artifact identity: the caller anchors must match the (digest-proven) bridge.
    if _plain_str_or_empty(ledger_bridge.episode_id) != episode_id:
        hard.append("paper_governor_decision:episode_id_mismatch")
    if _plain_str_or_empty(ledger_bridge.run_id) != run_id:
        hard.append("paper_governor_decision:run_id_mismatch")
    if _plain_str_or_empty(ledger_bridge.correlation_id) != correlation_id:
        hard.append("paper_governor_decision:correlation_id_mismatch")

    # Bridge gross totals + policy thresholds must be well-formed before the policy can decide.
    realized = _canonical_decimal(ledger_bridge.realized_pnl_total)
    closed = _canonical_decimal(ledger_bridge.closed_units_total)
    if realized is None or closed is None or closed < 0:
        hard.append("paper_governor_decision:ledger_bridge_totals_malformed")
    if not _is_int(ledger_bridge.computed_event_count) or ledger_bridge.computed_event_count < 0:
        hard.append("paper_governor_decision:ledger_bridge_count_malformed")
    max_abs = _canonical_decimal(policy.max_abs_realized_pnl)
    review_abs = _canonical_decimal(policy.review_abs_realized_pnl)
    max_units = _canonical_decimal(policy.max_closed_units)
    min_events = policy.min_computed_event_count
    # Re-prove the FULL policy threshold invariants at the decision boundary. ``PaperGovernorPolicy`` is a
    # public frozen dataclass, so a caller can construct malformed thresholds and reseal ``policy_digest`` —
    # the digest re-proof alone would then pass. The builder's invariants are NOT trusted transitively; every
    # invariant ``build_paper_governor_policy`` enforces (canonical decimals, non-negative thresholds/count,
    # ``review_abs_realized_pnl <= max_abs_realized_pnl``) is re-checked here. Any violation maps fail-closed to
    # REJECTED + BLOCK_PAPER (never DECIDED, never a partial ALLOW). ``and`` short-circuits so no None is compared.
    policy_thresholds_ok = (
        max_abs is not None
        and review_abs is not None
        and max_units is not None
        and _is_int(min_events)
        and min_events >= 0
        and max_abs >= 0
        and review_abs >= 0
        and max_units >= 0
        and review_abs <= max_abs
    )
    if not policy_thresholds_ok:
        hard.append("paper_governor_decision:policy_thresholds_malformed")

    if hard:
        status = PaperGovernorDecisionStatus.REJECTED
        verdict = PaperGovernorVerdict.BLOCK_PAPER
        reason_codes = tuple(sorted(set(hard)))
    else:
        block: list[str] = []
        review: list[str] = []
        if ledger_bridge.computed_event_count < policy.min_computed_event_count:
            block.append("paper_governor_decision:insufficient_computed_events")
        if closed > max_units:  # type: ignore[operator]
            block.append("paper_governor_decision:closed_units_exceeds_max")
        abs_realized = abs(realized)  # type: ignore[arg-type]
        if abs_realized > max_abs:  # type: ignore[operator]
            block.append("paper_governor_decision:realized_pnl_exceeds_block_threshold")
        elif abs_realized > review_abs:  # type: ignore[operator]
            review.append("paper_governor_decision:realized_pnl_exceeds_review_threshold")
        status = PaperGovernorDecisionStatus.DECIDED
        if block:
            verdict = PaperGovernorVerdict.BLOCK_PAPER
            reason_codes = tuple(sorted(set(block + review)))
        elif review:
            verdict = PaperGovernorVerdict.REVIEW_REQUIRED
            reason_codes = tuple(sorted(set(review)))
        else:
            verdict = PaperGovernorVerdict.ALLOW_PAPER
            reason_codes = ()

    return _finalize_decision(
        status=status,
        verdict=verdict,
        ledger_bridge=ledger_bridge,
        policy=policy,
        expected_ledger_bridge_digest=expected_ledger_bridge_digest,
        episode_id=episode_id,
        run_id=run_id,
        correlation_id=correlation_id,
        reason_codes=reason_codes,
        metadata=metadata_pairs,
    )


def _finalize_decision(
    *,
    status: PaperGovernorDecisionStatus,
    verdict: PaperGovernorVerdict,
    ledger_bridge: PaperAdmissionLedgerBridge,
    policy: PaperGovernorPolicy,
    expected_ledger_bridge_digest: str,
    episode_id: str,
    run_id: str,
    correlation_id: str,
    reason_codes: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperGovernorDecision:
    fields: dict[str, object] = {
        "schema_version": _DECISION_SCHEMA_VERSION,
        "status": status,
        "decided": status is PaperGovernorDecisionStatus.DECIDED,
        "decision": verdict,
        "allowed": verdict is PaperGovernorVerdict.ALLOW_PAPER,
        "run_id": run_id,
        "episode_id": episode_id,
        "correlation_id": correlation_id,
        "market_symbol": _plain_str_or_empty(ledger_bridge.market_symbol),
        "ledger_bridge_digest": _plain_str_or_empty(ledger_bridge.ledger_digest),
        "expected_ledger_bridge_digest": expected_ledger_bridge_digest,
        "ledger_bridge_status": ledger_bridge.status.value
        if isinstance(ledger_bridge.status, PaperAdmissionLedgerBridgeStatus)
        else "",
        "policy_id": _plain_str_or_empty(policy.policy_id),
        "policy_digest": _plain_str_or_empty(policy.policy_digest),
        "episode_digest": _plain_str_or_empty(ledger_bridge.episode_digest),
        "manifest_digest": _plain_str_or_empty(ledger_bridge.manifest_digest),
        "realized_pnl_event_digest": _plain_str_or_empty(ledger_bridge.realized_pnl_event_digest),
        "realized_pnl_total": _plain_str_or_empty(ledger_bridge.realized_pnl_total),
        "closed_units_total": _plain_str_or_empty(ledger_bridge.closed_units_total),
        "computed_event_count": ledger_bridge.computed_event_count
        if _is_int(ledger_bridge.computed_event_count)
        else 0,
        "source_event_digest_count": ledger_bridge.source_event_digest_count
        if _is_int(ledger_bridge.source_event_digest_count)
        else 0,
        "reason_codes": reason_codes,
        "metadata": metadata,
    }
    seed = PaperGovernorDecision(decision_digest="", **fields)  # type: ignore[arg-type]
    return _replace_decision_digest(seed, paper_governor_decision_digest(seed))


def _replace_decision_digest(decision: PaperGovernorDecision, digest: str) -> PaperGovernorDecision:
    fields = _decision_fields(decision)
    fields["decision_digest"] = digest
    return PaperGovernorDecision(**fields)  # type: ignore[arg-type]


def _decision_fields(decision: PaperGovernorDecision) -> dict[str, object]:
    return {
        "schema_version": decision.schema_version,
        "status": decision.status,
        "decided": decision.decided,
        "decision": decision.decision,
        "allowed": decision.allowed,
        "run_id": decision.run_id,
        "episode_id": decision.episode_id,
        "correlation_id": decision.correlation_id,
        "market_symbol": decision.market_symbol,
        "ledger_bridge_digest": decision.ledger_bridge_digest,
        "expected_ledger_bridge_digest": decision.expected_ledger_bridge_digest,
        "ledger_bridge_status": decision.ledger_bridge_status,
        "policy_id": decision.policy_id,
        "policy_digest": decision.policy_digest,
        "episode_digest": decision.episode_digest,
        "manifest_digest": decision.manifest_digest,
        "realized_pnl_event_digest": decision.realized_pnl_event_digest,
        "realized_pnl_total": decision.realized_pnl_total,
        "closed_units_total": decision.closed_units_total,
        "computed_event_count": decision.computed_event_count,
        "source_event_digest_count": decision.source_event_digest_count,
        "reason_codes": decision.reason_codes,
        "metadata": decision.metadata,
    }


def _decision_payload_from(decision: PaperGovernorDecision) -> dict[str, object]:
    return {
        "schema_version": decision.schema_version,
        "status": decision.status.value,
        "decided": decision.decided,
        "decision": decision.decision.value,
        "allowed": decision.allowed,
        "run_id": decision.run_id,
        "episode_id": decision.episode_id,
        "correlation_id": decision.correlation_id,
        "market_symbol": decision.market_symbol,
        "ledger_bridge_digest": decision.ledger_bridge_digest,
        "expected_ledger_bridge_digest": decision.expected_ledger_bridge_digest,
        "ledger_bridge_status": decision.ledger_bridge_status,
        "policy_id": decision.policy_id,
        "policy_digest": decision.policy_digest,
        "episode_digest": decision.episode_digest,
        "manifest_digest": decision.manifest_digest,
        "realized_pnl_event_digest": decision.realized_pnl_event_digest,
        "realized_pnl_total": decision.realized_pnl_total,
        "closed_units_total": decision.closed_units_total,
        "computed_event_count": decision.computed_event_count,
        "source_event_digest_count": decision.source_event_digest_count,
        "reason_codes": list(decision.reason_codes),
        "metadata": _serialize_metadata(
            decision.metadata, PaperGovernorDecisionError, "paper_governor_decision:metadata_malformed"
        ),
        "paper_only": decision.paper_only,
        "real_orders_enabled": decision.real_orders_enabled,
        "real_money_enabled": decision.real_money_enabled,
        "real_capital_reserved": decision.real_capital_reserved,
        "order_routed": decision.order_routed,
        "execution_authorized": decision.execution_authorized,
        "live_api_called": decision.live_api_called,
        "scheduler_enabled": decision.scheduler_enabled,
        "auto_loop_enabled": decision.auto_loop_enabled,
        "connector_invoked": decision.connector_invoked,
        "prdv4_stage4_complete": decision.prdv4_stage4_complete,
        "live_ready": decision.live_ready,
        "shadow_ready": decision.shadow_ready,
        "profitability_proven": decision.profitability_proven,
        "edge_proven": decision.edge_proven,
        "production_execution": decision.production_execution,
    }


def paper_governor_decision_to_dict(decision: PaperGovernorDecision) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for a decision (deterministic shape, includes self-digest)."""
    payload = _decision_payload_from(decision)
    payload["decision_digest"] = decision.decision_digest
    return payload


def paper_governor_decision_digest(decision: PaperGovernorDecision) -> str:
    """Recompute the canonical decision digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_decision_payload_from(decision))


__all__ = [
    "PaperGovernorDecision",
    "PaperGovernorDecisionError",
    "PaperGovernorDecisionStatus",
    "PaperGovernorPolicy",
    "PaperGovernorPolicyError",
    "PaperGovernorVerdict",
    "build_paper_governor_policy",
    "decide_paper_governor",
    "paper_governor_decision_digest",
    "paper_governor_decision_to_dict",
    "paper_governor_policy_digest",
    "paper_governor_policy_to_dict",
]
