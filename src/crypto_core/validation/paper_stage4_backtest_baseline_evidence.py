"""Deterministic paper Stage-4 backtest-baseline evidence (PRDV4 Stage 4 comparator prerequisite).

This validation artifact binds a CALLER-SUPPLIED ``Stage4BacktestBaseline`` to a proven, merged
``PaperEdgeIdentityEvidence`` by edge-id IDENTITY equality. It is paper-only, deterministic, digest-bound,
and fail-closed.

Governance (user-approved for this slice):

* baseline source: the ``Stage4BacktestBaseline`` is CALLER-SUPPLIED; this artifact NEVER constructs a
  baseline. It re-proves the supplied baseline by a canonical digest computed from the PUBLIC
  ``stage4_backtest_baseline_to_dict`` serializer (the same bridge-local representation used by
  ``paper_vs_backtest_comparator_bridge``: ``sha256(canonical_json(stage4_backtest_baseline_to_dict(baseline)))``)
  and requires it to equal the caller's INDEPENDENT ``expected_baseline_digest``;
* same-edge contract (identity-only): ``backtest_baseline.edge_id`` must equal
  ``PaperEdgeIdentityEvidence.paper_edge_id``, and that edge_id must be a lowercase hex64 produced by the approved
  derivation ``sha256(canonical_json({"strategy_id": ..., "market_symbol": ...}))`` (re-proven via the edge
  identity's ``edge_id_form`` / ``edge_id_derivation_policy``). This proves edge-id IDENTITY equality ONLY.

EXPLICIT LIMITATION (serializer-visible + digest-bound): edge-id equality proves identity, NOT backtest
validity, NOT edge validity, NOT profitability, NOT same-edge performance quality, NOT Stage-4 completion. The
backtest baseline carries no ``spec_digest`` and no provenance chain, so this binding is
``edge_id_identity_only`` and ``paper_chain_link_cryptographic=False``.

It does NOT construct a ``Stage4BacktestBaseline`` or ``Stage4PaperSummary``, does NOT invoke the Stage-4
comparator (``compare_stage4``), does NOT consume ``PaperSharpeEvidence`` / ``PaperVsBacktestMethodology`` /
daily-return / 30-day-gate / operational-day evidence, does NOT set ``prdv4_stage4_complete``, and does NOT
prove comparison readiness, live readiness, shadow readiness, Deribit readiness, or operational readiness. It
calls no wall-clock, runtime, service, execution, venue, scheduler, filesystem, network, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_edge_identity_evidence import (
    PaperEdgeIdentityEvidence,
    PaperEdgeIdentityEvidenceStatus,
    paper_edge_identity_evidence_digest,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    stage4_backtest_baseline_to_dict,
)

_SCHEMA_ID = "paper-stage4-backtest-baseline-evidence.v1"
_SCHEMA_VERSION = "paper-stage4-backtest-baseline-evidence.v1"
_EVIDENCE_VERSION = "paper-stage4-backtest-baseline-evidence.v1"
_BASELINE_SOURCE = "caller_supplied_stage4_backtest_baseline.v1"
_SAME_EDGE_IDENTITY_POLICY = "baseline_edge_id_equals_paper_edge_identity.v1"
_EXPECTED_EDGE_IDENTITY_SCHEMA_VERSION = "paper-edge-identity-evidence.v1"
_EDGE_ID_FORM = "hex64_sha256"
_EDGE_ID_DERIVATION_POLICY = "sha256_canonical_strategy_id_market_symbol.v1"
_BINDING_IDENTITY = "BASELINE_EDGE_ID_IDENTITY_BOUND"
_BINDING_UNRESOLVED = "UNRESOLVED"
_PAPER_CHAIN_LINK = "edge_id_identity_only"
_PAPER_CHAIN_LINK_LIMITATION = "baseline_bound_by_edge_id_identity_not_backtest_validity_or_performance.v1"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"compare_stage4|Stage4PaperSummary|capital|margin|balance|"
    r"reservation|real_account_equity|account_equity|real_equity)\w*"
    r"|crypto_core\.(?:service|execution|venue|runtime|orchestrator|temporal|session|data|portfolio)\b"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")
_CLOCK_TOKENS = (
    "wall_clock",
    "wall-clock",
    "wallclock",
    "datetime.now",
    "datetime.utcnow",
    "utcnow",
    "time.time_ns",
    "time.time",
    "perf_counter",
    "monotonic",
    "server_time",
    "exchange_time",
    "live_time",
    "real_time",
    "realtime",
    "system_time",
    "clock",
    "now()",
)


class PaperStage4BacktestBaselineEvidenceError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata / tokens)."""


class PaperStage4BacktestBaselineEvidenceStatus(str, Enum):
    """Whether a trusted, same-edge-bound baseline evidence could be produced. Never an execution/live action."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperStage4BacktestBaselineEvidence:
    """Immutable, digest-bound paper Stage-4 backtest-baseline evidence (edge-id identity binding only).

    ``status`` READY only when the caller-supplied baseline re-proves its canonical digest, is well-formed, and
    its ``edge_id`` equals the resolved ``PaperEdgeIdentityEvidence.paper_edge_id`` (a lowercase hex64 of the
    approved derivation form). ``baseline_bound`` / ``same_edge_identity_equal`` are True only when READY.
    Identity-only: ``same_edge_as_backtest_proven`` / ``backtest_validity_proven`` /
    ``baseline_profitability_proven`` are constant False. ``paper_only`` True; every safety / non-overclaim
    attestation False. NOT a comparator run, NOT a Stage-4 / live / shadow / operational readiness claim.
    """

    schema_id: str
    schema_version: str
    evidence_version: str
    status: PaperStage4BacktestBaselineEvidenceStatus
    ready: bool
    baseline_evidence_id: str
    correlation_id: str
    baseline_bound: bool
    baseline_source: str
    expected_baseline_digest: str
    baseline_digest: str
    expected_edge_identity_digest: str
    edge_identity_digest: str
    baseline_id: str
    edge_id: str
    paper_edge_id: str
    baseline_as_of_ns: int
    baseline_source_window_ids: tuple[str, ...]
    baseline_source_window_id_count: int
    same_edge_identity_equal: bool
    same_edge_identity_policy: str
    edge_identity_id: str
    paper_id: str
    strategy_id: str
    strategy_version: str
    strategy_family: str
    edge_family: str
    market_type: str
    market_symbol: str
    edge_id_form: str
    edge_id_derivation_policy: str
    binding_strength: str
    paper_chain_link: str
    paper_chain_link_cryptographic: bool
    paper_chain_spec_digest_carried: bool
    paper_chain_link_limitation: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    baseline_evidence_digest: str
    paper_only: bool = True
    baseline_constructed: bool = False
    same_edge_as_backtest_proven: bool = False
    backtest_validity_proven: bool = False
    baseline_profitability_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    comparison_ready: bool = False
    paper_vs_backtest_comparison_ready: bool = False
    stage4_comparator_invoked: bool = False
    thirty_day_gate_satisfied: bool = False
    prdv4_stage4_complete: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    real_wall_clock_used: bool = False
    real_account_equity_used: bool = False
    real_capital_used: bool = False


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


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_positive_int(value: object) -> bool:
    return _is_exact_int(value) and value > 0


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value)


def _is_rate(value: object) -> bool:
    return _is_finite_number(value) and 0.0 <= float(value) <= 1.0


def _is_non_negative_optional_number(value: object) -> bool:
    return value is None or (_is_finite_number(value) and float(value) >= 0.0)


def _is_optional_rate(value: object) -> bool:
    return value is None or _is_rate(value)


def _plain_str_or_empty(value: object) -> str:
    return value if type(value) is str else ""


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperStage4BacktestBaselineEvidenceError(f"paper_stage4_backtest_baseline_evidence:{field_name}_invalid")
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperStage4BacktestBaselineEvidenceError("paper_stage4_backtest_baseline_evidence:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperStage4BacktestBaselineEvidenceError("paper_stage4_backtest_baseline_evidence:metadata_malformed")
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperStage4BacktestBaselineEvidenceError("paper_stage4_backtest_baseline_evidence:metadata_malformed")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperStage4BacktestBaselineEvidenceError("paper_stage4_backtest_baseline_evidence:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _has_clock_token(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _CLOCK_TOKENS):
            return True
    return False


def _backtest_baseline_digest(baseline: Stage4BacktestBaseline) -> str:
    """Canonical digest of a caller-supplied baseline via the PUBLIC ``stage4_backtest_baseline_to_dict``.

    Mirrors the bridge-local representation in ``paper_vs_backtest_comparator_bridge`` exactly:
    ``Stage4BacktestBaseline`` carries no self-digest, so the whole serialized payload is bound (``allow_nan=False``
    fails closed on non-finite floats). Used only to re-prove a supplied baseline — never to run the comparator.
    """
    return _canonical_digest(stage4_backtest_baseline_to_dict(baseline))


def _baseline_string_fields(baseline: Stage4BacktestBaseline) -> tuple[str, ...]:
    texts: list[str] = []
    if type(baseline.baseline_id) is str:
        texts.append(baseline.baseline_id)
    if type(baseline.edge_id) is str:
        texts.append(baseline.edge_id)
    if type(baseline.source_window_ids) is tuple:
        texts.extend(item for item in baseline.source_window_ids if type(item) is str)
    return tuple(texts)


def _baseline_value_failures(baseline: Stage4BacktestBaseline) -> list[str]:
    """Re-prove caller-supplied baseline well-formedness. Mirrors ``stage4_comparator._validate_baseline`` ranges.

    The same numeric contract the comparator enforces (sharpe > 0, hit/fill rates in [0,1], slippage >= 0 or
    ``None``, positive ``as_of_ns``, well-formed ``source_window_ids``) so a baseline accepted here is one the
    comparator would also accept for its baseline portion. Value failures are REJECTED, not raised.
    """
    hard: list[str] = []
    if not _is_plain_non_empty_string(baseline.baseline_id):
        hard.append("paper_stage4_backtest_baseline_evidence:baseline_id_invalid")
    if not _is_hex64_string(baseline.edge_id):
        hard.append("paper_stage4_backtest_baseline_evidence:baseline_edge_id_invalid")
    if not _is_positive_int(baseline.as_of_ns):
        hard.append("paper_stage4_backtest_baseline_evidence:baseline_as_of_ns_invalid")
    if not _is_finite_number(baseline.backtest_sharpe) or float(baseline.backtest_sharpe) <= 0.0:
        hard.append("paper_stage4_backtest_baseline_evidence:backtest_sharpe_non_positive")
    if not _is_rate(baseline.backtest_hit_rate):
        hard.append("paper_stage4_backtest_baseline_evidence:backtest_hit_rate_invalid")
    if not _is_non_negative_optional_number(baseline.backtest_slippage_bps):
        hard.append("paper_stage4_backtest_baseline_evidence:backtest_slippage_invalid")
    if not _is_optional_rate(baseline.backtest_fill_rate):
        hard.append("paper_stage4_backtest_baseline_evidence:backtest_fill_rate_invalid")
    if type(baseline.source_window_ids) is not tuple or not all(
        _is_plain_non_empty_string(item) for item in baseline.source_window_ids
    ):
        hard.append("paper_stage4_backtest_baseline_evidence:source_window_ids_invalid")
    return hard


_EDGE_IDENTITY_SAFE_FLAGS = (
    "edge_proven",
    "profitability_proven",
    "same_edge_as_backtest_proven",
    "same_edge_comparison_ready",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
    "paper_chain_link_cryptographic",
    "paper_chain_spec_digest_carried",
)


def _edge_identity_hard_failures(
    edge_identity: PaperEdgeIdentityEvidence, expected_edge_identity_digest: str
) -> list[str]:
    hard: list[str] = []
    try:
        recomputed = paper_edge_identity_evidence_digest(edge_identity)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        recomputed = None
    if (
        recomputed is None
        or not _is_hex64_string(edge_identity.edge_identity_digest)
        or edge_identity.edge_identity_digest != recomputed
        or edge_identity.edge_identity_digest != expected_edge_identity_digest
    ):
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_digest_mismatch")

    if edge_identity.schema_version != _EXPECTED_EDGE_IDENTITY_SCHEMA_VERSION:
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_schema_invalid")
    if (
        edge_identity.status is not PaperEdgeIdentityEvidenceStatus.READY
        or edge_identity.ready is not True
        or edge_identity.reason_codes != ()
    ):
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_not_ready")
    if edge_identity.edge_identity_resolved is not True or edge_identity.strategy_spec_identity_proven is not True:
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_not_resolved")
    if not _is_hex64_string(edge_identity.paper_edge_id):
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_paper_edge_id_invalid")
    if edge_identity.edge_id_form != _EDGE_ID_FORM:
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_edge_id_form_invalid")
    if edge_identity.edge_id_derivation_policy != _EDGE_ID_DERIVATION_POLICY:
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_derivation_policy_mismatch")
    if edge_identity.paper_only is not True or any(
        getattr(edge_identity, flag) is not False for flag in _EDGE_IDENTITY_SAFE_FLAGS
    ):
        hard.append("paper_stage4_backtest_baseline_evidence:edge_identity_unsafe_flags")
    return hard


def build_paper_stage4_backtest_baseline_evidence(
    backtest_baseline: Stage4BacktestBaseline,
    *,
    expected_baseline_digest: str,
    edge_identity: PaperEdgeIdentityEvidence,
    expected_edge_identity_digest: str,
    baseline_evidence_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperStage4BacktestBaselineEvidence:
    """Bind a caller-supplied ``Stage4BacktestBaseline`` to a proven paper edge identity by edge-id equality.

    ``backtest_baseline`` must be an exact ``Stage4BacktestBaseline`` (NEVER constructed here);
    ``expected_baseline_digest`` the caller's INDEPENDENT 64-lowercase-hex anchor (== the canonical digest of
    ``stage4_backtest_baseline_to_dict(backtest_baseline)``); ``edge_identity`` an exact, merged, READY
    ``PaperEdgeIdentityEvidence`` re-proven via ``paper_edge_identity_evidence_digest`` (== stored ==
    ``expected_edge_identity_digest``); ``baseline_evidence_id`` / ``correlation_id`` exact plain non-empty
    ``str``; ``metadata`` ``Mapping[str, str]`` or ``None``. A wrong type, malformed digest, empty/subclass/
    control-char id, a forbidden BIST/live/order/capital/readiness/clock token, or malformed metadata raises
    ``PaperStage4BacktestBaselineEvidenceError`` before any work.

    ``status=READY`` only when the baseline re-proves + is well-formed AND ``backtest_baseline.edge_id ==
    edge_identity.paper_edge_id`` (a lowercase hex64 of the approved derivation form). Edge-id equality proves
    IDENTITY only — never backtest validity, edge validity, profitability, same-edge performance, or Stage-4
    completion. Any trust / value / same-edge failure maps to ``status=REJECTED``. Deterministic and immutable;
    no wall-clock/random/IO; inputs unmutated; no comparator run; no baseline / ``Stage4PaperSummary`` construction.
    """
    if type(backtest_baseline) is not Stage4BacktestBaseline:
        raise PaperStage4BacktestBaselineEvidenceError(
            "paper_stage4_backtest_baseline_evidence:backtest_baseline_malformed"
        )
    if type(edge_identity) is not PaperEdgeIdentityEvidence:
        raise PaperStage4BacktestBaselineEvidenceError(
            "paper_stage4_backtest_baseline_evidence:edge_identity_malformed"
        )
    if not _is_hex64_string(expected_baseline_digest):
        raise PaperStage4BacktestBaselineEvidenceError(
            "paper_stage4_backtest_baseline_evidence:expected_baseline_digest_invalid"
        )
    if not _is_hex64_string(expected_edge_identity_digest):
        raise PaperStage4BacktestBaselineEvidenceError(
            "paper_stage4_backtest_baseline_evidence:expected_edge_identity_digest_invalid"
        )
    baseline_evidence_id = _require_plain_non_empty_string(baseline_evidence_id, "baseline_evidence_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (baseline_evidence_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperStage4BacktestBaselineEvidenceError("paper_stage4_backtest_baseline_evidence:scope_violation")
    if _has_clock_token(*scope_texts):
        raise PaperStage4BacktestBaselineEvidenceError("paper_stage4_backtest_baseline_evidence:clock_token_forbidden")

    hard: list[str] = []

    # Trust boundary: re-prove the caller-supplied baseline by its canonical digest (== caller anchor).
    try:
        recomputed_baseline = _backtest_baseline_digest(backtest_baseline)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        recomputed_baseline = None
    if recomputed_baseline is None or recomputed_baseline != expected_baseline_digest:
        hard.append("paper_stage4_backtest_baseline_evidence:baseline_digest_mismatch")
        baseline_digest = ""
    else:
        baseline_digest = recomputed_baseline

    # Caller-supplied baseline well-formedness + scope (value failures, not raises).
    hard.extend(_baseline_value_failures(backtest_baseline))
    if _has_scope_violation(*_baseline_string_fields(backtest_baseline)):
        hard.append("paper_stage4_backtest_baseline_evidence:baseline_scope_violation")
    if _has_clock_token(*_baseline_string_fields(backtest_baseline)):
        hard.append("paper_stage4_backtest_baseline_evidence:baseline_clock_token")

    # Trust boundary: re-prove the merged edge identity (digest + schema + status + resolution + policy + flags).
    hard.extend(_edge_identity_hard_failures(edge_identity, expected_edge_identity_digest))

    # Same-edge IDENTITY equality: the baseline's edge_id must equal the resolved paper edge identity.
    baseline_edge_id = _plain_str_or_empty(backtest_baseline.edge_id)
    paper_edge_id = _plain_str_or_empty(edge_identity.paper_edge_id)
    if (
        not _is_hex64_string(baseline_edge_id)
        or not _is_hex64_string(paper_edge_id)
        or baseline_edge_id != paper_edge_id
    ):
        hard.append("paper_stage4_backtest_baseline_evidence:same_edge_identity_mismatch")

    hard = sorted(set(hard))
    if hard:
        status = PaperStage4BacktestBaselineEvidenceStatus.REJECTED
        ready = False
        reason_codes = tuple(hard)
        binding_strength = _BINDING_UNRESOLVED
    else:
        status = PaperStage4BacktestBaselineEvidenceStatus.READY
        ready = True
        reason_codes = ()
        binding_strength = _BINDING_IDENTITY

    source_window_ids = (
        tuple(backtest_baseline.source_window_ids)
        if type(backtest_baseline.source_window_ids) is tuple
        and all(type(item) is str for item in backtest_baseline.source_window_ids)
        else ()
    )
    fields: dict[str, object] = {
        "schema_id": _SCHEMA_ID,
        "schema_version": _SCHEMA_VERSION,
        "evidence_version": _EVIDENCE_VERSION,
        "status": status,
        "ready": ready,
        "baseline_evidence_id": baseline_evidence_id,
        "correlation_id": correlation_id,
        "baseline_bound": ready,
        "baseline_source": _BASELINE_SOURCE,
        "expected_baseline_digest": expected_baseline_digest,
        "baseline_digest": baseline_digest,
        "expected_edge_identity_digest": expected_edge_identity_digest,
        "edge_identity_digest": _plain_str_or_empty(edge_identity.edge_identity_digest),
        "baseline_id": _plain_str_or_empty(backtest_baseline.baseline_id),
        "edge_id": baseline_edge_id,
        "paper_edge_id": paper_edge_id,
        "baseline_as_of_ns": backtest_baseline.as_of_ns if _is_exact_int(backtest_baseline.as_of_ns) else 0,
        "baseline_source_window_ids": source_window_ids,
        "baseline_source_window_id_count": len(source_window_ids),
        "same_edge_identity_equal": ready,
        "same_edge_identity_policy": _SAME_EDGE_IDENTITY_POLICY,
        "edge_identity_id": _plain_str_or_empty(edge_identity.edge_identity_id),
        "paper_id": _plain_str_or_empty(edge_identity.paper_id),
        "strategy_id": _plain_str_or_empty(edge_identity.strategy_id),
        "strategy_version": _plain_str_or_empty(edge_identity.strategy_version),
        "strategy_family": _plain_str_or_empty(edge_identity.strategy_family),
        "edge_family": _plain_str_or_empty(edge_identity.edge_family),
        "market_type": _plain_str_or_empty(edge_identity.market_type),
        "market_symbol": _plain_str_or_empty(edge_identity.market_symbol),
        "edge_id_form": _EDGE_ID_FORM,
        "edge_id_derivation_policy": _EDGE_ID_DERIVATION_POLICY,
        "binding_strength": binding_strength,
        "paper_chain_link": _PAPER_CHAIN_LINK,
        "paper_chain_link_cryptographic": False,
        "paper_chain_spec_digest_carried": False,
        "paper_chain_link_limitation": _PAPER_CHAIN_LINK_LIMITATION,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperStage4BacktestBaselineEvidence(baseline_evidence_digest="", **fields)  # type: ignore[arg-type]
    return _replace_evidence_digest(seed, paper_stage4_backtest_baseline_evidence_digest(seed))


def _replace_evidence_digest(
    evidence: PaperStage4BacktestBaselineEvidence, digest: str
) -> PaperStage4BacktestBaselineEvidence:
    fields = _evidence_fields(evidence)
    fields["baseline_evidence_digest"] = digest
    return PaperStage4BacktestBaselineEvidence(**fields)  # type: ignore[arg-type]


def _evidence_fields(evidence: PaperStage4BacktestBaselineEvidence) -> dict[str, object]:
    return {
        "schema_id": evidence.schema_id,
        "schema_version": evidence.schema_version,
        "evidence_version": evidence.evidence_version,
        "status": evidence.status,
        "ready": evidence.ready,
        "baseline_evidence_id": evidence.baseline_evidence_id,
        "correlation_id": evidence.correlation_id,
        "baseline_bound": evidence.baseline_bound,
        "baseline_source": evidence.baseline_source,
        "expected_baseline_digest": evidence.expected_baseline_digest,
        "baseline_digest": evidence.baseline_digest,
        "expected_edge_identity_digest": evidence.expected_edge_identity_digest,
        "edge_identity_digest": evidence.edge_identity_digest,
        "baseline_id": evidence.baseline_id,
        "edge_id": evidence.edge_id,
        "paper_edge_id": evidence.paper_edge_id,
        "baseline_as_of_ns": evidence.baseline_as_of_ns,
        "baseline_source_window_ids": evidence.baseline_source_window_ids,
        "baseline_source_window_id_count": evidence.baseline_source_window_id_count,
        "same_edge_identity_equal": evidence.same_edge_identity_equal,
        "same_edge_identity_policy": evidence.same_edge_identity_policy,
        "edge_identity_id": evidence.edge_identity_id,
        "paper_id": evidence.paper_id,
        "strategy_id": evidence.strategy_id,
        "strategy_version": evidence.strategy_version,
        "strategy_family": evidence.strategy_family,
        "edge_family": evidence.edge_family,
        "market_type": evidence.market_type,
        "market_symbol": evidence.market_symbol,
        "edge_id_form": evidence.edge_id_form,
        "edge_id_derivation_policy": evidence.edge_id_derivation_policy,
        "binding_strength": evidence.binding_strength,
        "paper_chain_link": evidence.paper_chain_link,
        "paper_chain_link_cryptographic": evidence.paper_chain_link_cryptographic,
        "paper_chain_spec_digest_carried": evidence.paper_chain_spec_digest_carried,
        "paper_chain_link_limitation": evidence.paper_chain_link_limitation,
        "reason_codes": evidence.reason_codes,
        "metadata": evidence.metadata,
    }


def _evidence_payload_from(evidence: PaperStage4BacktestBaselineEvidence) -> dict[str, object]:
    return {
        "schema_id": evidence.schema_id,
        "schema_version": evidence.schema_version,
        "evidence_version": evidence.evidence_version,
        "status": evidence.status.value,
        "ready": evidence.ready,
        "baseline_evidence_id": evidence.baseline_evidence_id,
        "correlation_id": evidence.correlation_id,
        "baseline_bound": evidence.baseline_bound,
        "baseline_source": evidence.baseline_source,
        "expected_baseline_digest": evidence.expected_baseline_digest,
        "baseline_digest": evidence.baseline_digest,
        "expected_edge_identity_digest": evidence.expected_edge_identity_digest,
        "edge_identity_digest": evidence.edge_identity_digest,
        "baseline_id": evidence.baseline_id,
        "edge_id": evidence.edge_id,
        "paper_edge_id": evidence.paper_edge_id,
        "baseline_as_of_ns": evidence.baseline_as_of_ns,
        "baseline_source_window_ids": list(evidence.baseline_source_window_ids),
        "baseline_source_window_id_count": evidence.baseline_source_window_id_count,
        "same_edge_identity_equal": evidence.same_edge_identity_equal,
        "same_edge_identity_policy": evidence.same_edge_identity_policy,
        "edge_identity_id": evidence.edge_identity_id,
        "paper_id": evidence.paper_id,
        "strategy_id": evidence.strategy_id,
        "strategy_version": evidence.strategy_version,
        "strategy_family": evidence.strategy_family,
        "edge_family": evidence.edge_family,
        "market_type": evidence.market_type,
        "market_symbol": evidence.market_symbol,
        "edge_id_form": evidence.edge_id_form,
        "edge_id_derivation_policy": evidence.edge_id_derivation_policy,
        "binding_strength": evidence.binding_strength,
        "paper_chain_link": evidence.paper_chain_link,
        "paper_chain_link_cryptographic": evidence.paper_chain_link_cryptographic,
        "paper_chain_spec_digest_carried": evidence.paper_chain_spec_digest_carried,
        "paper_chain_link_limitation": evidence.paper_chain_link_limitation,
        "reason_codes": list(evidence.reason_codes),
        "metadata": _serialize_metadata(evidence.metadata),
        "paper_only": evidence.paper_only,
        "baseline_constructed": evidence.baseline_constructed,
        "same_edge_as_backtest_proven": evidence.same_edge_as_backtest_proven,
        "backtest_validity_proven": evidence.backtest_validity_proven,
        "baseline_profitability_proven": evidence.baseline_profitability_proven,
        "edge_proven": evidence.edge_proven,
        "profitability_proven": evidence.profitability_proven,
        "comparison_ready": evidence.comparison_ready,
        "paper_vs_backtest_comparison_ready": evidence.paper_vs_backtest_comparison_ready,
        "stage4_comparator_invoked": evidence.stage4_comparator_invoked,
        "thirty_day_gate_satisfied": evidence.thirty_day_gate_satisfied,
        "prdv4_stage4_complete": evidence.prdv4_stage4_complete,
        "operational_readiness": evidence.operational_readiness,
        "live_ready": evidence.live_ready,
        "shadow_ready": evidence.shadow_ready,
        "deribit_ready": evidence.deribit_ready,
        "production_execution": evidence.production_execution,
        "real_orders_enabled": evidence.real_orders_enabled,
        "real_money_enabled": evidence.real_money_enabled,
        "real_capital_reserved": evidence.real_capital_reserved,
        "scheduler_enabled": evidence.scheduler_enabled,
        "auto_loop_enabled": evidence.auto_loop_enabled,
        "connector_invoked": evidence.connector_invoked,
        "private_api_ready": evidence.private_api_ready,
        "live_api_called": evidence.live_api_called,
        "real_wall_clock_used": evidence.real_wall_clock_used,
        "real_account_equity_used": evidence.real_account_equity_used,
        "real_capital_used": evidence.real_capital_used,
    }


def paper_stage4_backtest_baseline_evidence_to_dict(
    evidence: PaperStage4BacktestBaselineEvidence,
) -> dict[str, object]:
    """Canonical JSON-ready mapping for the baseline evidence, including its self-digest."""

    payload = _evidence_payload_from(evidence)
    payload["baseline_evidence_digest"] = evidence.baseline_evidence_digest
    return payload


def paper_stage4_backtest_baseline_evidence_digest(evidence: PaperStage4BacktestBaselineEvidence) -> str:
    """Recompute the canonical baseline-evidence digest, excluding only the self-digest field."""

    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperStage4BacktestBaselineEvidence",
    "PaperStage4BacktestBaselineEvidenceError",
    "PaperStage4BacktestBaselineEvidenceStatus",
    "build_paper_stage4_backtest_baseline_evidence",
    "paper_stage4_backtest_baseline_evidence_digest",
    "paper_stage4_backtest_baseline_evidence_to_dict",
]
