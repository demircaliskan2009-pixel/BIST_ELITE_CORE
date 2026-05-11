"""External regime data plane — Phase 11A.

Deterministic management of options, event, and on-chain regime state
with explicit freshness tracking, staleness detection, and fail-closed
unavailable handling.

Composes the raw regime contracts from execution.regime_contracts (Phase 9B)
into an operationalized data plane with:
  - Per-dimension freshness assessment
  - Staleness threshold enforcement
  - Aggregate risk / availability / sufficiency assessment
  - Deterministic snapshot production
  - Serialization for persistence and reporting

Design rules:
  - Missing data remains UNAVAILABLE — never silently becomes normal.
  - Stale data remains STALE — never silently appears fresh.
  - No fake provider data fabricated.
  - All state is explicit and auditable.
  - Frozen snapshots for thread-safe read access.

PRD reference: §1.4 Edge Family D, §1.29 System State, §4 Data Pipeline.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from crypto_core.execution.regime_contracts import (
    CompositeRegimeState,
    DataFreshness,
    EventRegimeLevel,
    EventRegimeState,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
)
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreCorruptError, WriteResult

logger = logging.getLogger(__name__)

_NS_PER_S: int = 1_000_000_000
_EXTERNAL_REGIME_SNAPSHOT_NAME = "external_regime_state"
_SUPPORTED_EXTERNAL_REGIME_INPUT_FORMATS = frozenset({"dict", "json", "json_file"})

EXT_REGIME_EXECUTION_UNAVAILABLE = "external_regime_unavailable"
EXT_REGIME_EXECUTION_STALE = "external_regime_stale"
EXT_REGIME_EXECUTION_HIGH_RISK = "external_regime_high_risk"

EXT_REGIME_ACTIVATION_EVENT_RISK_BLOCKED = "external_regime_event_risk_blocked"
EXT_REGIME_ACTIVATION_OPTIONS_EXTREME_BLOCKED = "external_regime_options_extreme_blocked"
EXT_REGIME_ACTIVATION_ON_CHAIN_STRESS_BLOCKED = "external_regime_on_chain_stress_blocked"
EXT_REGIME_ACTIVATION_REDUCED = "external_regime_high_risk_reduced"

_OPTIONS_PAYLOAD_REQUIRED_FIELDS = frozenset({"symbol", "level", "snapshot_ns", "source"})
_OPTIONS_PAYLOAD_ALLOWED_FIELDS = frozenset(
    {
        "symbol",
        "level",
        "snapshot_ns",
        "source",
        "implied_vol_30d",
        "implied_vol_7d",
        "put_call_ratio",
        "skew_25d",
        "term_structure_slope",
        "evidence",
    }
)
_EVENT_PAYLOAD_REQUIRED_FIELDS = frozenset({"level", "snapshot_ns", "source"})
_EVENT_PAYLOAD_ALLOWED_FIELDS = frozenset(
    {
        "level",
        "snapshot_ns",
        "source",
        "event_category",
        "event_label",
        "hours_until_event",
        "hours_since_event",
        "impact_estimate",
        "evidence",
    }
)
_ON_CHAIN_PAYLOAD_REQUIRED_FIELDS = frozenset({"symbol", "level", "snapshot_ns", "source"})
_ON_CHAIN_PAYLOAD_ALLOWED_FIELDS = frozenset(
    {
        "symbol",
        "level",
        "snapshot_ns",
        "source",
        "exchange_net_flow_24h_usd",
        "whale_transfer_count_24h",
        "active_addresses_7d_change_pct",
        "staking_ratio_change_7d_pct",
        "evidence",
    }
)
_BUNDLE_PAYLOAD_ALLOWED_FIELDS = frozenset(
    {
        "bundle_id",
        "source",
        "observed_at_ns",
        "received_at_ns",
        "options",
        "event",
        "on_chain",
    }
)


# ---------------------------------------------------------------------------
# Freshness model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimensionFreshness:
    """Freshness assessment for a single external regime dimension.

    freshness:        categorical freshness state.
    last_update_ns:   timestamp of last update, None if never received.
    staleness_seconds: seconds since last update, None if never received.
    source:           data source identifier, None if never received.
    """

    freshness: DataFreshness
    last_update_ns: int | None
    staleness_seconds: float | None
    source: str | None
    staleness_threshold_s: float | None = None


@dataclass(frozen=True)
class ExternalRegimeFreshnessPolicy:
    """Explicit per-dimension freshness thresholds for external regime truth."""

    options_staleness_threshold_s: float = 3600.0
    event_staleness_threshold_s: float = 3600.0
    on_chain_staleness_threshold_s: float = 3600.0

    def __post_init__(self) -> None:
        for name, value in (
            ("options_staleness_threshold_s", self.options_staleness_threshold_s),
            ("event_staleness_threshold_s", self.event_staleness_threshold_s),
            ("on_chain_staleness_threshold_s", self.on_chain_staleness_threshold_s),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be > 0, got {value}")

    @classmethod
    def uniform(cls, threshold_s: float) -> ExternalRegimeFreshnessPolicy:
        return cls(
            options_staleness_threshold_s=threshold_s,
            event_staleness_threshold_s=threshold_s,
            on_chain_staleness_threshold_s=threshold_s,
        )

    def threshold_for_dimension(self, dimension: str) -> float:
        if dimension == "options":
            return self.options_staleness_threshold_s
        if dimension == "event":
            return self.event_staleness_threshold_s
        if dimension == "on_chain":
            return self.on_chain_staleness_threshold_s
        raise ValueError(f"unsupported_dimension:{dimension!r}")

    @property
    def max_staleness_threshold_s(self) -> float:
        return max(
            self.options_staleness_threshold_s,
            self.event_staleness_threshold_s,
            self.on_chain_staleness_threshold_s,
        )


class ExternalRegimeProviderTrust(str, Enum):
    """Trust class for raw external regime providers."""

    TRUSTED = "trusted"
    PROVISIONAL = "provisional"
    UNSUPPORTED = "unsupported"


class ExternalRegimeProviderRole(str, Enum):
    """Per-dimension provider role used by overwrite policy."""

    PREFERRED = "preferred"
    FALLBACK = "fallback"
    DISALLOWED = "disallowed"


@dataclass(frozen=True)
class ExternalRegimeProviderProfile:
    """Provider/source profile for one logical raw payload source."""

    provider: str
    trust: ExternalRegimeProviderTrust
    options_role: ExternalRegimeProviderRole = ExternalRegimeProviderRole.DISALLOWED
    event_role: ExternalRegimeProviderRole = ExternalRegimeProviderRole.DISALLOWED
    on_chain_role: ExternalRegimeProviderRole = ExternalRegimeProviderRole.DISALLOWED

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider must be a non-empty string")
        if self.trust is ExternalRegimeProviderTrust.UNSUPPORTED and any(
            role is not ExternalRegimeProviderRole.DISALLOWED
            for role in (self.options_role, self.event_role, self.on_chain_role)
        ):
            raise ValueError("unsupported providers must be disallowed for every dimension")

    def role_for_dimension(self, dimension: str) -> ExternalRegimeProviderRole:
        if dimension == "options":
            return self.options_role
        if dimension == "event":
            return self.event_role
        if dimension == "on_chain":
            return self.on_chain_role
        raise ValueError(f"unsupported_dimension:{dimension!r}")


_DEFAULT_EXTERNAL_REGIME_PROVIDER_PROFILES = (
    ExternalRegimeProviderProfile(
        provider="manual",
        trust=ExternalRegimeProviderTrust.TRUSTED,
        options_role=ExternalRegimeProviderRole.PREFERRED,
        event_role=ExternalRegimeProviderRole.PREFERRED,
        on_chain_role=ExternalRegimeProviderRole.PREFERRED,
    ),
    ExternalRegimeProviderProfile(
        provider="calendar",
        trust=ExternalRegimeProviderTrust.TRUSTED,
        event_role=ExternalRegimeProviderRole.PREFERRED,
    ),
    ExternalRegimeProviderProfile(
        provider="glassnode",
        trust=ExternalRegimeProviderTrust.TRUSTED,
        on_chain_role=ExternalRegimeProviderRole.PREFERRED,
    ),
)


@dataclass(frozen=True)
class ExternalRegimeProviderPolicy:
    """Deterministic payload-source policy for raw adapter ingestion."""

    profiles: tuple[ExternalRegimeProviderProfile, ...] = _DEFAULT_EXTERNAL_REGIME_PROVIDER_PROFILES
    allow_trusted_overwrite_provisional: bool = True
    allow_provisional_overwrite_trusted: bool = False
    allow_fallback_overwrite_preferred: bool = False
    require_trusted_when_current_owner_unknown: bool = True

    def __post_init__(self) -> None:
        if not self.profiles:
            raise ValueError("profiles must not be empty")
        seen: set[str] = set()
        for profile in self.profiles:
            if profile.provider in seen:
                raise ValueError(f"duplicate_provider_profile:{profile.provider}")
            seen.add(profile.provider)

    def profile_for_provider(self, provider: str) -> ExternalRegimeProviderProfile:
        if isinstance(provider, str):
            for profile in self.profiles:
                if profile.provider == provider:
                    return profile
        return ExternalRegimeProviderProfile(
            provider=provider if isinstance(provider, str) and provider else "unsupported",
            trust=ExternalRegimeProviderTrust.UNSUPPORTED,
        )


@dataclass(frozen=True)
class ExternalRegimeDimensionSourceState:
    """Current owner metadata for one regime dimension."""

    dimension: str
    ownership_mode: str
    provider: str | None
    source_label: str | None
    trust: str | None
    role: str | None
    state_snapshot_ns: int | None
    received_at_ns: int


# ---------------------------------------------------------------------------
# External regime snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExternalRegimeSnapshot:
    """Point-in-time external regime assessment with freshness tracking.

    Combines regime contract states with operational freshness metadata
    for truthful operator surfacing.  Frozen, deterministic.
    """

    snapshot_ns: int

    # Component states (from regime_contracts, may be None)
    options: OptionsRegimeState | None
    event: EventRegimeState | None
    on_chain: OnChainRegimeState | None

    # Freshness per dimension
    options_freshness: DimensionFreshness
    event_freshness: DimensionFreshness
    on_chain_freshness: DimensionFreshness

    # Aggregate assessments
    any_extreme: bool
    any_unavailable_critical: bool
    high_risk_regime_present: bool
    evidence_sufficient: bool

    # Dimension summaries
    available_dimensions: tuple[str, ...]
    unavailable_dimensions: tuple[str, ...]
    stale_dimensions: tuple[str, ...]

    regime_summary: str


@dataclass
class ExternalRegimeSafetyPolicy:
    """Conservative external regime safety policy shared across runtime gates."""

    block_execution_on_unavailable: bool = True
    block_execution_on_stale: bool = True
    block_execution_on_high_risk: bool = True
    block_activation_on_event_risk: bool = True
    block_activation_on_options_extreme: bool = True
    block_activation_on_on_chain_stress: bool = True
    reduce_activation_on_elevated_options: bool = True
    reduce_activation_on_whale_activity: bool = True
    activation_reduced_scale: float = 0.50

    def __post_init__(self) -> None:
        if self.activation_reduced_scale <= 0.0 or self.activation_reduced_scale > 1.0:
            raise ValueError(f"activation_reduced_scale must be in (0, 1], got {self.activation_reduced_scale}")


@dataclass(frozen=True)
class ExternalRegimeSafetyFacts:
    """Deterministic classification of external regime safety facts."""

    snapshot_configured: bool
    evidence_available: bool
    evidence_sufficient: bool
    any_unavailable_critical: bool
    high_risk_regime_present: bool
    any_extreme: bool
    unavailable_dimensions: tuple[str, ...]
    stale_dimensions: tuple[str, ...]
    available_dimensions: tuple[str, ...]
    options_level: str | None
    event_level: str | None
    on_chain_level: str | None
    options_extreme: bool
    options_elevated: bool
    event_risk_active: bool
    on_chain_stress: bool
    on_chain_whale_active: bool
    regime_summary: str


@dataclass(frozen=True)
class ExternalRegimeExecutionSafetyDecision:
    """Execution/routing safety decision derived from external regime truth."""

    blocked: bool
    reason: str | None
    evidence: dict[str, object]


@dataclass(frozen=True)
class ExternalRegimeActivationSafetyDecision:
    """Activation safety decision derived from external regime truth."""

    blocked: bool
    reason: str | None
    allocation_scale: float
    evidence: dict[str, object]


class ExternalRegimeUpdateStatus(str, Enum):
    """Outcome classification for a regime update attempt."""

    ACCEPTED = "accepted"
    REJECTED_INVALID = "rejected_invalid"
    REJECTED_STALE = "rejected_stale"
    RESET = "reset"


@dataclass(frozen=True)
class ExternalRegimeUpdateRecord:
    """Deterministic record of one external regime update attempt."""

    dimension: str
    status: ExternalRegimeUpdateStatus
    accepted: bool
    received_at_ns: int
    state_snapshot_ns: int | None
    source_label: str | None
    level: str | None
    freshness: DataFreshness
    replaced_existing: bool
    reason: str


@dataclass(frozen=True)
class ExternalRegimePayloadIngestionRecord:
    """Deterministic record of one raw external regime payload ingestion attempt."""

    dimension: str
    provider: str
    input_format: str
    accepted: bool
    received_at_ns: int
    source_label: str | None
    state_snapshot_ns: int | None
    level: str | None
    provider_trust: str | None
    provider_role: str | None
    freshness_threshold_s: float | None
    update_status: str | None
    reason: str
    rejection_stage: str | None
    payload_origin: str | None
    payload_summary: dict[str, object]


class ExternalRegimeBundleApplyMode(str, Enum):
    """Bundle application policy for multi-dimension ingestion."""

    ATOMIC = "atomic"
    PARTIAL = "partial"


class ExternalRegimeBundleIngestionOutcome(str, Enum):
    """Top-level outcome for one bundle ingestion attempt."""

    FULLY_ACCEPTED = "fully_accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    FULLY_REJECTED = "fully_rejected"


@dataclass(frozen=True)
class ExternalRegimePayloadBundle:
    """Normalized external-regime bundle carrying one or more dimensions."""

    bundle_id: str | None
    source: str | None
    observed_at_ns: int | None
    received_at_ns: int | None
    options: dict[str, object] | None
    event: dict[str, object] | None
    on_chain: dict[str, object] | None


@dataclass(frozen=True)
class ExternalRegimeBundleIngestionRecord:
    """Deterministic outcome for one bundle ingestion attempt."""

    bundle_id: str | None
    provider: str
    input_format: str
    apply_mode: str
    outcome: str
    accepted: bool
    partially_accepted: bool
    replayable: bool
    received_at_ns: int
    observed_at_ns: int | None
    source: str | None
    payload_origin: str | None
    dimensions_present: tuple[str, ...]
    changed_dimensions: tuple[str, ...]
    failed_dimensions: tuple[str, ...]
    reason: str
    dimension_results: tuple[ExternalRegimePayloadIngestionRecord, ...]


@dataclass(frozen=True)
class ExternalRegimeBundleReplayArtifact:
    """Replayable audit artifact for deterministic bundle reruns."""

    bundle_id: str | None
    provider: str
    input_format: str
    apply_mode: str
    received_at_ns: int
    observed_at_ns: int | None
    source: str | None
    payload_origin: str | None
    raw_bundle_payload: dict[str, object]
    normalized_bundle: ExternalRegimePayloadBundle
    result: ExternalRegimeBundleIngestionRecord


@dataclass(frozen=True)
class ExternalRegimeScenarioStep:
    """One deterministic external-regime scenario step."""

    step_id: str
    received_at_ns: int
    provider: str
    input_format: str = "dict"
    apply_mode: str = ExternalRegimeBundleApplyMode.ATOMIC.value
    bundle_payload: dict[str, object] | None = None
    dimension_payloads: dict[str, dict[str, object]] | None = None
    replay_artifact: ExternalRegimeBundleReplayArtifact | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, str) or not self.step_id.strip():
            raise ValueError("step_id must be a non-empty string")
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("provider must be a non-empty string")
        if not isinstance(self.received_at_ns, int) or self.received_at_ns < 0:
            raise ValueError(f"received_at_ns must be >= 0, got {self.received_at_ns!r}")
        payload_modes = sum(
            1
            for candidate in (self.bundle_payload, self.dimension_payloads, self.replay_artifact)
            if candidate is not None
        )
        if payload_modes != 1:
            raise ValueError("exactly one of bundle_payload, dimension_payloads, or replay_artifact must be provided")
        if self.bundle_payload is not None and not isinstance(self.bundle_payload, dict):
            raise ValueError("bundle_payload must be a dict when provided")
        if self.dimension_payloads is not None:
            if not isinstance(self.dimension_payloads, dict) or not self.dimension_payloads:
                raise ValueError("dimension_payloads must be a non-empty dict when provided")
            for dimension, payload in self.dimension_payloads.items():
                if dimension not in {"options", "event", "on_chain"}:
                    raise ValueError(f"unsupported_dimension:{dimension!r}")
                if not isinstance(payload, dict):
                    raise ValueError(f"dimension payload for {dimension!r} must be a dict")


@dataclass(frozen=True)
class ExternalRegimeScenario:
    """Ordered deterministic external-regime scenario."""

    scenario_id: str
    steps: tuple[ExternalRegimeScenarioStep, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("scenario_id must be a non-empty string")
        if not self.steps:
            raise ValueError("steps must not be empty")
        previous_ns = -1
        seen_ids: set[str] = set()
        for step in self.steps:
            if step.step_id in seen_ids:
                raise ValueError(f"duplicate_scenario_step_id:{step.step_id}")
            seen_ids.add(step.step_id)
            if step.received_at_ns < previous_ns:
                raise ValueError("scenario steps must be ordered by non-decreasing received_at_ns")
            previous_ns = step.received_at_ns


@dataclass(frozen=True)
class ExternalRegimeScenarioStepRecord:
    """Deterministic outcome for one scenario step."""

    step_id: str
    received_at_ns: int
    provider: str
    operation: str
    accepted: bool
    partially_accepted: bool
    replayed: bool
    accepted_count: int
    rejected_count: int
    changed_dimensions: tuple[str, ...]
    failed_dimensions: tuple[str, ...]
    activation_blocked: bool
    activation_reason: str | None
    activation_allocation_scale: float
    execution_blocked: bool
    execution_reason: str | None
    stale_dimensions: tuple[str, ...]
    unavailable_dimensions: tuple[str, ...]
    high_risk: bool
    bundle_result: ExternalRegimeBundleIngestionRecord | None
    dimension_results: tuple[ExternalRegimePayloadIngestionRecord, ...]
    snapshot: ExternalRegimeSnapshot


@dataclass(frozen=True)
class ExternalRegimeScenarioResult:
    """Aggregate deterministic result for a completed scenario replay."""

    scenario_id: str
    status: str
    step_count: int
    accepted_steps: int
    rejected_steps: int
    replayed_steps: int
    partially_accepted_steps: int
    execution_blocked_steps: int
    activation_blocked_steps: int
    activation_reduced_steps: int
    stale_steps: int
    unavailable_steps: int
    high_risk_steps: int
    safe_steps: int
    last_step_ns: int
    summary: str
    step_records: tuple[ExternalRegimeScenarioStepRecord, ...]
    final_snapshot: ExternalRegimeSnapshot | None


@dataclass(frozen=True)
class _PreparedExternalRegimePayloadIngestion:
    """Internal prepared payload candidate used by bundle and single ingestion."""

    dimension: str
    provider: str
    input_format: str
    received_at_ns: int
    payload_origin: str | None
    payload_summary: dict[str, object]
    state: OptionsRegimeState | EventRegimeState | OnChainRegimeState
    provider_trust: str | None
    provider_role: str | None
    freshness_threshold_s: float | None


@dataclass(frozen=True)
class ExternalRegimePersistenceState:
    """Persistence / restore status for the managed external regime state."""

    evidence_store_configured: bool
    snapshot_name: str
    snapshot_present: bool
    restored_from_snapshot: bool
    history_limit: int


class ExternalRegimeStateCorruptError(RuntimeError):
    """Raised when persisted external regime state is malformed."""


# ---------------------------------------------------------------------------
# Data plane class
# ---------------------------------------------------------------------------


class ExternalRegimeDataPlane:
    """Manages external regime state with freshness tracking.

    Accepts updates from external providers and produces deterministic
    snapshots with freshness assessment.  Does NOT fabricate data — only
    tracks what was explicitly provided.

    Thread safety: NOT thread-safe — use from one thread.

    Usage::

        plane = ExternalRegimeDataPlane(staleness_threshold_s=3600)
        plane.update_options(options_state)
        plane.update_event(event_state)
        snap = plane.snapshot(now_ns)
    """

    def __init__(
        self,
        *,
        staleness_threshold_s: float = 3600.0,
        freshness_policy: ExternalRegimeFreshnessPolicy | None = None,
    ) -> None:
        if freshness_policy is not None and staleness_threshold_s != 3600.0:
            raise ValueError("provide either staleness_threshold_s or freshness_policy, not both")
        self._freshness_policy = freshness_policy or ExternalRegimeFreshnessPolicy.uniform(staleness_threshold_s)
        self._staleness_threshold_s = self._freshness_policy.max_staleness_threshold_s

        self._options: OptionsRegimeState | None = None
        self._options_update_ns: int | None = None

        self._event: EventRegimeState | None = None
        self._event_update_ns: int | None = None

        self._on_chain: OnChainRegimeState | None = None
        self._on_chain_update_ns: int | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def staleness_threshold_s(self) -> float:
        """Legacy global staleness accessor for backward compatibility."""
        return self._staleness_threshold_s

    @property
    def freshness_policy(self) -> ExternalRegimeFreshnessPolicy:
        """Configured per-dimension freshness policy."""
        return self._freshness_policy

    @property
    def options_state(self) -> OptionsRegimeState | None:
        """Last received options regime state."""
        return self._options

    @property
    def event_state(self) -> EventRegimeState | None:
        """Last received event regime state."""
        return self._event

    @property
    def on_chain_state(self) -> OnChainRegimeState | None:
        """Last received on-chain regime state."""
        return self._on_chain

    # ------------------------------------------------------------------
    # Update methods (called by providers)
    # ------------------------------------------------------------------

    def update_options(self, state: OptionsRegimeState) -> None:
        """Update options regime state from provider."""
        self._options = state
        self._options_update_ns = state.snapshot_ns
        logger.debug("Options regime updated: level=%s", state.level.value)

    def update_event(self, state: EventRegimeState) -> None:
        """Update event regime state from provider."""
        self._event = state
        self._event_update_ns = state.snapshot_ns
        logger.debug("Event regime updated: level=%s", state.level.value)

    def update_on_chain(self, state: OnChainRegimeState) -> None:
        """Update on-chain regime state from provider."""
        self._on_chain = state
        self._on_chain_update_ns = state.snapshot_ns
        logger.debug("On-chain regime updated: level=%s", state.level.value)

    # ------------------------------------------------------------------
    # Snapshot production
    # ------------------------------------------------------------------

    def snapshot(self, now_ns: int) -> ExternalRegimeSnapshot:
        """Produce a deterministic external regime snapshot.

        Assesses freshness, staleness, availability, and aggregate
        risk for all dimensions at the given timestamp.

        Args:
            now_ns: current wall-clock timestamp in nanoseconds.

        Returns:
            Frozen ExternalRegimeSnapshot.
        """
        opt_fresh = self._build_dimension_freshness("options", self._options, self._options_update_ns, now_ns)
        evt_fresh = self._build_dimension_freshness("event", self._event, self._event_update_ns, now_ns)
        oc_fresh = self._build_dimension_freshness("on_chain", self._on_chain, self._on_chain_update_ns, now_ns)

        # Classify dimensions
        available: list[str] = []
        unavailable: list[str] = []
        stale: list[str] = []

        for name, freshness in [
            ("options", opt_fresh),
            ("event", evt_fresh),
            ("on_chain", oc_fresh),
        ]:
            if freshness.freshness == DataFreshness.UNAVAILABLE:
                unavailable.append(name)
            elif freshness.freshness == DataFreshness.STALE:
                stale.append(name)
                available.append(name)  # available but stale
            elif freshness.freshness in (DataFreshness.FRESH, DataFreshness.DEGRADED):
                available.append(name)

        # Aggregate assessments
        any_extreme = self._check_any_extreme()
        any_unavailable_critical = len(unavailable) > 0
        high_risk = any_extreme or self._check_elevated_risk()

        # Evidence sufficiency: at least 2 of 3 dimensions fresh or degraded
        fresh_or_degraded_count = sum(
            1 for f in (opt_fresh, evt_fresh, oc_fresh) if f.freshness in (DataFreshness.FRESH, DataFreshness.DEGRADED)
        )
        evidence_sufficient = fresh_or_degraded_count >= 2

        summary = _build_summary(available, unavailable, stale, any_extreme, high_risk)

        return ExternalRegimeSnapshot(
            snapshot_ns=now_ns,
            options=self._options,
            event=self._event,
            on_chain=self._on_chain,
            options_freshness=opt_fresh,
            event_freshness=evt_fresh,
            on_chain_freshness=oc_fresh,
            any_extreme=any_extreme,
            any_unavailable_critical=any_unavailable_critical,
            high_risk_regime_present=high_risk,
            evidence_sufficient=evidence_sufficient,
            available_dimensions=tuple(available),
            unavailable_dimensions=tuple(unavailable),
            stale_dimensions=tuple(stale),
            regime_summary=summary,
        )

    def composite_regime(self, now_ns: int) -> CompositeRegimeState:
        """Produce a CompositeRegimeState for backward compatibility.

        Args:
            now_ns: current wall-clock timestamp.

        Returns:
            CompositeRegimeState from the existing regime_contracts module.
        """
        return CompositeRegimeState(
            snapshot_ns=now_ns,
            options=self._options,
            event=self._event,
            on_chain=self._on_chain,
        )

    def reset(self) -> None:
        """Clear all state.  Use between test cases for isolation."""
        self._options = None
        self._options_update_ns = None
        self._event = None
        self._event_update_ns = None
        self._on_chain = None
        self._on_chain_update_ns = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_dimension_freshness(
        self,
        dimension: str,
        state: OptionsRegimeState | EventRegimeState | OnChainRegimeState | None,
        update_ns: int | None,
        now_ns: int,
    ) -> DimensionFreshness:
        """Assess freshness for a single regime dimension."""
        threshold_s = self._freshness_policy.threshold_for_dimension(dimension)
        # Never received
        if state is None or update_ns is None:
            return DimensionFreshness(
                freshness=DataFreshness.UNAVAILABLE,
                last_update_ns=None,
                staleness_seconds=None,
                staleness_threshold_s=threshold_s,
                source=None,
            )

        # Source reports unavailable
        if not state.is_available:
            return DimensionFreshness(
                freshness=DataFreshness.UNAVAILABLE,
                last_update_ns=update_ns,
                staleness_seconds=None,
                staleness_threshold_s=threshold_s,
                source=state.source,
            )

        # Compute staleness
        staleness_s = max(0.0, (now_ns - update_ns) / _NS_PER_S)

        # Stale check
        if staleness_s > threshold_s:
            return DimensionFreshness(
                freshness=DataFreshness.STALE,
                last_update_ns=update_ns,
                staleness_seconds=staleness_s,
                staleness_threshold_s=threshold_s,
                source=state.source,
            )

        # Degradation check: available but material evidence gaps
        if _has_evidence_gaps(state):
            return DimensionFreshness(
                freshness=DataFreshness.DEGRADED,
                last_update_ns=update_ns,
                staleness_seconds=staleness_s,
                staleness_threshold_s=threshold_s,
                source=state.source,
            )

        # Fresh
        return DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=update_ns,
            staleness_seconds=staleness_s,
            staleness_threshold_s=threshold_s,
            source=state.source,
        )

    def _check_any_extreme(self) -> bool:
        """True if any dimension indicates extreme / stress / active event."""
        if self._options is not None and self._options.is_extreme:
            return True
        if self._event is not None and self._event.is_active_or_pending:
            return True
        if self._on_chain is not None and self._on_chain.is_stress:
            return True
        return False

    def _check_elevated_risk(self) -> bool:
        """True if any dimension has elevated (non-extreme) risk conditions."""
        if self._options is not None and self._options.level in (
            OptionsRegimeLevel.ELEVATED,
            OptionsRegimeLevel.EXTREME,
        ):
            return True
        if self._event is not None and self._event.level == EventRegimeLevel.ACTIVE:
            return True
        if self._on_chain is not None and self._on_chain.level in (
            OnChainRegimeLevel.STRESS,
            OnChainRegimeLevel.WHALE_ACTIVE,
        ):
            return True
        return False


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _has_evidence_gaps(
    state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
) -> bool:
    """Check if available state has material evidence gaps (DEGRADED)."""
    if isinstance(state, OptionsRegimeState):
        return state.implied_vol_30d is None and state.implied_vol_7d is None
    if isinstance(state, OnChainRegimeState):
        return state.exchange_net_flow_24h_usd is None and state.whale_transfer_count_24h is None
    # EventRegimeState: no degradation concept for events
    return False


def _build_summary(
    available: list[str],
    unavailable: list[str],
    stale: list[str],
    any_extreme: bool,
    high_risk: bool,
) -> str:
    """Build a human-readable regime summary string."""
    parts: list[str] = []

    if not available and not stale:
        parts.append("No external regime data available.")
    else:
        if available:
            parts.append(f"Available: {', '.join(available)}.")
        if stale:
            parts.append(f"Stale: {', '.join(stale)}.")
        if unavailable:
            parts.append(f"Unavailable: {', '.join(unavailable)}.")

    if any_extreme:
        parts.append("EXTREME external regime conditions detected.")
    elif high_risk:
        parts.append("Elevated external risk conditions present.")

    return " ".join(parts)


def build_external_regime_safety_facts(
    snap: ExternalRegimeSnapshot | None,
) -> ExternalRegimeSafetyFacts:
    """Build the shared external regime safety facts used by runtime gates."""
    if snap is None:
        return ExternalRegimeSafetyFacts(
            snapshot_configured=False,
            evidence_available=False,
            evidence_sufficient=False,
            any_unavailable_critical=False,
            high_risk_regime_present=False,
            any_extreme=False,
            unavailable_dimensions=(),
            stale_dimensions=(),
            available_dimensions=(),
            options_level=None,
            event_level=None,
            on_chain_level=None,
            options_extreme=False,
            options_elevated=False,
            event_risk_active=False,
            on_chain_stress=False,
            on_chain_whale_active=False,
            regime_summary="external_regime_not_configured",
        )

    return ExternalRegimeSafetyFacts(
        snapshot_configured=True,
        evidence_available=len(snap.available_dimensions) > 0,
        evidence_sufficient=snap.evidence_sufficient,
        any_unavailable_critical=snap.any_unavailable_critical,
        high_risk_regime_present=snap.high_risk_regime_present,
        any_extreme=snap.any_extreme,
        unavailable_dimensions=snap.unavailable_dimensions,
        stale_dimensions=snap.stale_dimensions,
        available_dimensions=snap.available_dimensions,
        options_level=snap.options.level.value if snap.options is not None else None,
        event_level=snap.event.level.value if snap.event is not None else None,
        on_chain_level=snap.on_chain.level.value if snap.on_chain is not None else None,
        options_extreme=(snap.options is not None and snap.options.level == OptionsRegimeLevel.EXTREME),
        options_elevated=(snap.options is not None and snap.options.level == OptionsRegimeLevel.ELEVATED),
        event_risk_active=(snap.event is not None and snap.event.is_active_or_pending),
        on_chain_stress=(snap.on_chain is not None and snap.on_chain.level == OnChainRegimeLevel.STRESS),
        on_chain_whale_active=(snap.on_chain is not None and snap.on_chain.level == OnChainRegimeLevel.WHALE_ACTIVE),
        regime_summary=snap.regime_summary,
    )


def external_regime_safety_facts_to_dict(facts: ExternalRegimeSafetyFacts) -> dict[str, object]:
    """Serialize external regime safety facts to a plain dict."""
    return {
        "snapshot_configured": facts.snapshot_configured,
        "evidence_available": facts.evidence_available,
        "evidence_sufficient": facts.evidence_sufficient,
        "any_unavailable_critical": facts.any_unavailable_critical,
        "high_risk_regime_present": facts.high_risk_regime_present,
        "any_extreme": facts.any_extreme,
        "unavailable_dimensions": list(facts.unavailable_dimensions),
        "stale_dimensions": list(facts.stale_dimensions),
        "available_dimensions": list(facts.available_dimensions),
        "options_level": facts.options_level,
        "event_level": facts.event_level,
        "on_chain_level": facts.on_chain_level,
        "options_extreme": facts.options_extreme,
        "options_elevated": facts.options_elevated,
        "event_risk_active": facts.event_risk_active,
        "on_chain_stress": facts.on_chain_stress,
        "on_chain_whale_active": facts.on_chain_whale_active,
        "regime_summary": facts.regime_summary,
    }


def evaluate_external_regime_execution_safety(
    snap: ExternalRegimeSnapshot | None,
    policy: ExternalRegimeSafetyPolicy | None,
) -> ExternalRegimeExecutionSafetyDecision:
    """Evaluate external regime execution/routing safety in one deterministic place."""
    facts = build_external_regime_safety_facts(snap)
    if policy is None:
        return ExternalRegimeExecutionSafetyDecision(
            blocked=False,
            reason=None,
            evidence={"policy_enabled": False, "facts": external_regime_safety_facts_to_dict(facts)},
        )

    evidence: dict[str, object] = {
        "policy_enabled": True,
        "policy": {
            "block_execution_on_unavailable": policy.block_execution_on_unavailable,
            "block_execution_on_stale": policy.block_execution_on_stale,
            "block_execution_on_high_risk": policy.block_execution_on_high_risk,
        },
        "facts": external_regime_safety_facts_to_dict(facts),
    }
    if not facts.snapshot_configured:
        evidence["reason"] = "external_regime_not_configured"
        return ExternalRegimeExecutionSafetyDecision(blocked=False, reason=None, evidence=evidence)

    if policy.block_execution_on_unavailable and facts.any_unavailable_critical:
        evidence["blocked_dimensions"] = list(facts.unavailable_dimensions)
        return ExternalRegimeExecutionSafetyDecision(
            blocked=True,
            reason=EXT_REGIME_EXECUTION_UNAVAILABLE,
            evidence=evidence,
        )

    if policy.block_execution_on_stale and facts.stale_dimensions:
        evidence["blocked_dimensions"] = list(facts.stale_dimensions)
        return ExternalRegimeExecutionSafetyDecision(
            blocked=True,
            reason=EXT_REGIME_EXECUTION_STALE,
            evidence=evidence,
        )

    risk_triggers: list[str] = []
    if facts.event_risk_active:
        risk_triggers.append("event_risk_active")
    if facts.options_extreme:
        risk_triggers.append("options_extreme")
    if facts.on_chain_stress:
        risk_triggers.append("on_chain_stress")
    if policy.block_execution_on_high_risk and risk_triggers:
        evidence["risk_triggers"] = risk_triggers
        return ExternalRegimeExecutionSafetyDecision(
            blocked=True,
            reason=EXT_REGIME_EXECUTION_HIGH_RISK,
            evidence=evidence,
        )

    if facts.high_risk_regime_present:
        evidence["high_risk_observed"] = True
    return ExternalRegimeExecutionSafetyDecision(blocked=False, reason=None, evidence=evidence)


def evaluate_external_regime_activation_safety(
    snap: ExternalRegimeSnapshot | None,
    policy: ExternalRegimeSafetyPolicy | None,
) -> ExternalRegimeActivationSafetyDecision:
    """Evaluate activation tightening / blocking from external regime truth."""
    facts = build_external_regime_safety_facts(snap)
    if policy is None:
        return ExternalRegimeActivationSafetyDecision(
            blocked=False,
            reason=None,
            allocation_scale=1.0,
            evidence={"policy_enabled": False, "facts": external_regime_safety_facts_to_dict(facts)},
        )

    evidence: dict[str, object] = {
        "policy_enabled": True,
        "policy": {
            "block_activation_on_event_risk": policy.block_activation_on_event_risk,
            "block_activation_on_options_extreme": policy.block_activation_on_options_extreme,
            "block_activation_on_on_chain_stress": policy.block_activation_on_on_chain_stress,
            "reduce_activation_on_elevated_options": policy.reduce_activation_on_elevated_options,
            "reduce_activation_on_whale_activity": policy.reduce_activation_on_whale_activity,
            "activation_reduced_scale": policy.activation_reduced_scale,
        },
        "facts": external_regime_safety_facts_to_dict(facts),
    }
    if not facts.snapshot_configured:
        evidence["reason"] = "external_regime_not_configured"
        return ExternalRegimeActivationSafetyDecision(
            blocked=False,
            reason=None,
            allocation_scale=1.0,
            evidence=evidence,
        )

    if policy.block_activation_on_event_risk and facts.event_risk_active:
        evidence["risk_trigger"] = "event_risk_active"
        return ExternalRegimeActivationSafetyDecision(
            blocked=True,
            reason=EXT_REGIME_ACTIVATION_EVENT_RISK_BLOCKED,
            allocation_scale=0.0,
            evidence=evidence,
        )

    if policy.block_activation_on_options_extreme and facts.options_extreme:
        evidence["risk_trigger"] = "options_extreme"
        return ExternalRegimeActivationSafetyDecision(
            blocked=True,
            reason=EXT_REGIME_ACTIVATION_OPTIONS_EXTREME_BLOCKED,
            allocation_scale=0.0,
            evidence=evidence,
        )

    if policy.block_activation_on_on_chain_stress and facts.on_chain_stress:
        evidence["risk_trigger"] = "on_chain_stress"
        return ExternalRegimeActivationSafetyDecision(
            blocked=True,
            reason=EXT_REGIME_ACTIVATION_ON_CHAIN_STRESS_BLOCKED,
            allocation_scale=0.0,
            evidence=evidence,
        )

    allow_tags: list[str] = []
    allocation_scale = 1.0
    if policy.reduce_activation_on_elevated_options and facts.options_elevated:
        allocation_scale = min(allocation_scale, policy.activation_reduced_scale)
        allow_tags.append("options_elevated")
    if policy.reduce_activation_on_whale_activity and facts.on_chain_whale_active:
        allocation_scale = min(allocation_scale, policy.activation_reduced_scale)
        allow_tags.append("on_chain_whale_activity")

    if allow_tags:
        evidence["allow_tags"] = allow_tags
        return ExternalRegimeActivationSafetyDecision(
            blocked=False,
            reason=EXT_REGIME_ACTIVATION_REDUCED,
            allocation_scale=allocation_scale,
            evidence=evidence,
        )

    return ExternalRegimeActivationSafetyDecision(
        blocked=False,
        reason=None,
        allocation_scale=1.0,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Provider adapter layer
# ---------------------------------------------------------------------------


def build_options_regime_state_from_payload(
    payload: object,
    *,
    provider: str,
    input_format: str,
    payload_origin: str | None = None,
) -> OptionsRegimeState:
    """Build OptionsRegimeState from a validated provider payload."""
    data = _require_payload_dict(
        payload,
        dimension="options",
        required_fields=_OPTIONS_PAYLOAD_REQUIRED_FIELDS,
        allowed_fields=_OPTIONS_PAYLOAD_ALLOWED_FIELDS,
    )
    evidence = _build_adapter_evidence(
        data.get("evidence"),
        provider=provider,
        input_format=input_format,
        payload_origin=payload_origin,
    )
    return OptionsRegimeState(
        symbol=_required_non_empty_string(data, "symbol"),
        level=_enum_field(OptionsRegimeLevel, data, "level"),
        snapshot_ns=_required_non_negative_int(data, "snapshot_ns"),
        source=_required_non_empty_string(data, "source"),
        implied_vol_30d=_optional_float(data, "implied_vol_30d"),
        implied_vol_7d=_optional_float(data, "implied_vol_7d"),
        put_call_ratio=_optional_float(data, "put_call_ratio"),
        skew_25d=_optional_float(data, "skew_25d"),
        term_structure_slope=_optional_float(data, "term_structure_slope"),
        evidence=evidence,
    )


def build_event_regime_state_from_payload(
    payload: object,
    *,
    provider: str,
    input_format: str,
    payload_origin: str | None = None,
) -> EventRegimeState:
    """Build EventRegimeState from a validated provider payload."""
    from crypto_core.execution.regime_contracts import EventCategory

    data = _require_payload_dict(
        payload,
        dimension="event",
        required_fields=_EVENT_PAYLOAD_REQUIRED_FIELDS,
        allowed_fields=_EVENT_PAYLOAD_ALLOWED_FIELDS,
    )
    impact_estimate = _optional_float(data, "impact_estimate")
    if impact_estimate is not None and not 0.0 <= impact_estimate <= 1.0:
        raise ValueError(f"event.impact_estimate_out_of_range:{impact_estimate!r}")
    evidence = _build_adapter_evidence(
        data.get("evidence"),
        provider=provider,
        input_format=input_format,
        payload_origin=payload_origin,
    )
    return EventRegimeState(
        level=_enum_field(EventRegimeLevel, data, "level"),
        snapshot_ns=_required_non_negative_int(data, "snapshot_ns"),
        source=_required_non_empty_string(data, "source"),
        event_category=_optional_enum_field(EventCategory, data, "event_category", default=EventCategory.UNKNOWN),
        event_label=_optional_string(data, "event_label"),
        hours_until_event=_optional_non_negative_float(data, "hours_until_event"),
        hours_since_event=_optional_non_negative_float(data, "hours_since_event"),
        impact_estimate=impact_estimate,
        evidence=evidence,
    )


def build_on_chain_regime_state_from_payload(
    payload: object,
    *,
    provider: str,
    input_format: str,
    payload_origin: str | None = None,
) -> OnChainRegimeState:
    """Build OnChainRegimeState from a validated provider payload."""
    data = _require_payload_dict(
        payload,
        dimension="on_chain",
        required_fields=_ON_CHAIN_PAYLOAD_REQUIRED_FIELDS,
        allowed_fields=_ON_CHAIN_PAYLOAD_ALLOWED_FIELDS,
    )
    evidence = _build_adapter_evidence(
        data.get("evidence"),
        provider=provider,
        input_format=input_format,
        payload_origin=payload_origin,
    )
    return OnChainRegimeState(
        symbol=_required_non_empty_string(data, "symbol"),
        level=_enum_field(OnChainRegimeLevel, data, "level"),
        snapshot_ns=_required_non_negative_int(data, "snapshot_ns"),
        source=_required_non_empty_string(data, "source"),
        exchange_net_flow_24h_usd=_optional_float(data, "exchange_net_flow_24h_usd"),
        whale_transfer_count_24h=_optional_non_negative_int(data, "whale_transfer_count_24h"),
        active_addresses_7d_change_pct=_optional_float(data, "active_addresses_7d_change_pct"),
        staking_ratio_change_7d_pct=_optional_float(data, "staking_ratio_change_7d_pct"),
        evidence=evidence,
    )


def load_external_regime_payload(
    payload: object,
    *,
    input_format: str,
) -> tuple[dict[str, object], str | None]:
    """Normalize a raw external-regime payload into a dict plus origin label."""
    if input_format not in _SUPPORTED_EXTERNAL_REGIME_INPUT_FORMATS:
        raise ValueError(f"invalid_input_format:{input_format!r}")

    if input_format == "dict":
        if not isinstance(payload, dict):
            raise ValueError(f"payload_root_must_be_object:{type(payload).__name__}")
        return dict(payload), None

    if input_format == "json":
        if not isinstance(payload, str):
            raise ValueError(f"json_payload_must_be_string:{type(payload).__name__}")
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_json_payload:{exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"payload_root_must_be_object:{type(parsed).__name__}")
        return parsed, None

    path = payload if isinstance(payload, Path) else Path(payload) if isinstance(payload, str) else None
    if path is None:
        raise ValueError(f"json_file_payload_must_be_path:{type(payload).__name__}")
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"json_file_unreadable:{path}:{exc.strerror or exc.__class__.__name__}") from exc
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json_file:{path}:{exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"payload_root_must_be_object:{type(parsed).__name__}")
    return parsed, str(path)


def external_regime_payload_ingestion_record_to_dict(record: ExternalRegimePayloadIngestionRecord) -> dict:
    """Serialize an ingestion record to a plain dict."""
    return {
        "dimension": record.dimension,
        "provider": record.provider,
        "input_format": record.input_format,
        "accepted": record.accepted,
        "received_at_ns": record.received_at_ns,
        "source_label": record.source_label,
        "state_snapshot_ns": record.state_snapshot_ns,
        "level": record.level,
        "provider_trust": record.provider_trust,
        "provider_role": record.provider_role,
        "freshness_threshold_s": record.freshness_threshold_s,
        "update_status": record.update_status,
        "reason": record.reason,
        "rejection_stage": record.rejection_stage,
        "payload_origin": record.payload_origin,
        "payload_summary": dict(record.payload_summary),
    }


def external_regime_payload_ingestion_record_from_dict(d: dict) -> ExternalRegimePayloadIngestionRecord:
    """Deserialize an ingestion record from a plain dict."""
    try:
        payload_summary = d.get("payload_summary", {})
        if not isinstance(payload_summary, dict):
            raise ValueError("payload_summary must be dict")
        return ExternalRegimePayloadIngestionRecord(
            dimension=str(d["dimension"]),
            provider=str(d["provider"]),
            input_format=str(d["input_format"]),
            accepted=bool(d["accepted"]),
            received_at_ns=int(d["received_at_ns"]),
            source_label=d.get("source_label"),
            state_snapshot_ns=(int(d["state_snapshot_ns"]) if d.get("state_snapshot_ns") is not None else None),
            level=d.get("level"),
            provider_trust=d.get("provider_trust"),
            provider_role=d.get("provider_role"),
            freshness_threshold_s=(
                float(d["freshness_threshold_s"]) if d.get("freshness_threshold_s") is not None else None
            ),
            update_status=d.get("update_status"),
            reason=str(d["reason"]),
            rejection_stage=d.get("rejection_stage"),
            payload_origin=d.get("payload_origin"),
            payload_summary=dict(payload_summary),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimePayloadIngestionRecord: {exc}") from exc


def external_regime_payload_bundle_to_dict(bundle: ExternalRegimePayloadBundle) -> dict:
    """Serialize a normalized external-regime bundle."""
    return {
        "bundle_id": bundle.bundle_id,
        "source": bundle.source,
        "observed_at_ns": bundle.observed_at_ns,
        "received_at_ns": bundle.received_at_ns,
        "options": None if bundle.options is None else dict(bundle.options),
        "event": None if bundle.event is None else dict(bundle.event),
        "on_chain": None if bundle.on_chain is None else dict(bundle.on_chain),
    }


def external_regime_payload_bundle_from_dict(d: dict) -> ExternalRegimePayloadBundle:
    """Deserialize a normalized external-regime bundle."""
    try:
        return ExternalRegimePayloadBundle(
            bundle_id=d.get("bundle_id"),
            source=d.get("source"),
            observed_at_ns=(int(d["observed_at_ns"]) if d.get("observed_at_ns") is not None else None),
            received_at_ns=(int(d["received_at_ns"]) if d.get("received_at_ns") is not None else None),
            options=_optional_bundle_dimension_payload(d, "options"),
            event=_optional_bundle_dimension_payload(d, "event"),
            on_chain=_optional_bundle_dimension_payload(d, "on_chain"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimePayloadBundle: {exc}") from exc


def external_regime_bundle_ingestion_record_to_dict(record: ExternalRegimeBundleIngestionRecord) -> dict:
    """Serialize a bundle ingestion result."""
    return {
        "bundle_id": record.bundle_id,
        "provider": record.provider,
        "input_format": record.input_format,
        "apply_mode": record.apply_mode,
        "outcome": record.outcome,
        "accepted": record.accepted,
        "partially_accepted": record.partially_accepted,
        "replayable": record.replayable,
        "received_at_ns": record.received_at_ns,
        "observed_at_ns": record.observed_at_ns,
        "source": record.source,
        "payload_origin": record.payload_origin,
        "dimensions_present": list(record.dimensions_present),
        "changed_dimensions": list(record.changed_dimensions),
        "failed_dimensions": list(record.failed_dimensions),
        "reason": record.reason,
        "dimension_results": [
            external_regime_payload_ingestion_record_to_dict(item) for item in record.dimension_results
        ],
    }


def external_regime_bundle_ingestion_record_from_dict(d: dict) -> ExternalRegimeBundleIngestionRecord:
    """Deserialize a bundle ingestion result."""
    try:
        return ExternalRegimeBundleIngestionRecord(
            bundle_id=d.get("bundle_id"),
            provider=str(d["provider"]),
            input_format=str(d["input_format"]),
            apply_mode=str(d["apply_mode"]),
            outcome=str(d["outcome"]),
            accepted=bool(d["accepted"]),
            partially_accepted=bool(d["partially_accepted"]),
            replayable=bool(d["replayable"]),
            received_at_ns=int(d["received_at_ns"]),
            observed_at_ns=(int(d["observed_at_ns"]) if d.get("observed_at_ns") is not None else None),
            source=d.get("source"),
            payload_origin=d.get("payload_origin"),
            dimensions_present=tuple(d.get("dimensions_present", ())),
            changed_dimensions=tuple(d.get("changed_dimensions", ())),
            failed_dimensions=tuple(d.get("failed_dimensions", ())),
            reason=str(d["reason"]),
            dimension_results=tuple(
                external_regime_payload_ingestion_record_from_dict(item) for item in d.get("dimension_results", ())
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeBundleIngestionRecord: {exc}") from exc


def external_regime_bundle_replay_artifact_to_dict(artifact: ExternalRegimeBundleReplayArtifact) -> dict:
    """Serialize a replayable bundle artifact."""
    return {
        "bundle_id": artifact.bundle_id,
        "provider": artifact.provider,
        "input_format": artifact.input_format,
        "apply_mode": artifact.apply_mode,
        "received_at_ns": artifact.received_at_ns,
        "observed_at_ns": artifact.observed_at_ns,
        "source": artifact.source,
        "payload_origin": artifact.payload_origin,
        "raw_bundle_payload": dict(artifact.raw_bundle_payload),
        "normalized_bundle": external_regime_payload_bundle_to_dict(artifact.normalized_bundle),
        "result": external_regime_bundle_ingestion_record_to_dict(artifact.result),
    }


def external_regime_bundle_replay_artifact_from_dict(d: dict) -> ExternalRegimeBundleReplayArtifact:
    """Deserialize a replayable bundle artifact."""
    try:
        raw_bundle_payload = d.get("raw_bundle_payload", {})
        if not isinstance(raw_bundle_payload, dict):
            raise ValueError("raw_bundle_payload must be dict")
        return ExternalRegimeBundleReplayArtifact(
            bundle_id=d.get("bundle_id"),
            provider=str(d["provider"]),
            input_format=str(d["input_format"]),
            apply_mode=str(d["apply_mode"]),
            received_at_ns=int(d["received_at_ns"]),
            observed_at_ns=(int(d["observed_at_ns"]) if d.get("observed_at_ns") is not None else None),
            source=d.get("source"),
            payload_origin=d.get("payload_origin"),
            raw_bundle_payload=dict(raw_bundle_payload),
            normalized_bundle=external_regime_payload_bundle_from_dict(d["normalized_bundle"]),
            result=external_regime_bundle_ingestion_record_from_dict(d["result"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeBundleReplayArtifact: {exc}") from exc


def external_regime_scenario_step_to_dict(step: ExternalRegimeScenarioStep) -> dict:
    """Serialize one scenario step."""
    return {
        "step_id": step.step_id,
        "received_at_ns": step.received_at_ns,
        "provider": step.provider,
        "input_format": step.input_format,
        "apply_mode": step.apply_mode,
        "bundle_payload": (dict(step.bundle_payload) if step.bundle_payload is not None else None),
        "dimension_payloads": (
            {dimension: dict(payload) for dimension, payload in step.dimension_payloads.items()}
            if step.dimension_payloads is not None
            else None
        ),
        "replay_artifact": (
            external_regime_bundle_replay_artifact_to_dict(step.replay_artifact)
            if step.replay_artifact is not None
            else None
        ),
        "note": step.note,
    }


def external_regime_scenario_step_from_dict(d: dict) -> ExternalRegimeScenarioStep:
    """Deserialize one scenario step."""
    try:
        dimension_payloads_raw = d.get("dimension_payloads")
        if dimension_payloads_raw is not None and not isinstance(dimension_payloads_raw, dict):
            raise ValueError("dimension_payloads must be a dict")
        dimension_payloads = None
        if isinstance(dimension_payloads_raw, dict):
            dimension_payloads = {
                str(dimension): dict(payload)
                for dimension, payload in dimension_payloads_raw.items()
                if isinstance(payload, dict)
            }
        bundle_payload_raw = d.get("bundle_payload")
        if bundle_payload_raw is not None and not isinstance(bundle_payload_raw, dict):
            raise ValueError("bundle_payload must be a dict")
        replay_artifact_raw = d.get("replay_artifact")
        return ExternalRegimeScenarioStep(
            step_id=str(d["step_id"]),
            received_at_ns=int(d["received_at_ns"]),
            provider=str(d["provider"]),
            input_format=str(d.get("input_format", "dict")),
            apply_mode=str(d.get("apply_mode", ExternalRegimeBundleApplyMode.ATOMIC.value)),
            bundle_payload=(dict(bundle_payload_raw) if isinstance(bundle_payload_raw, dict) else None),
            dimension_payloads=dimension_payloads,
            replay_artifact=(
                external_regime_bundle_replay_artifact_from_dict(replay_artifact_raw)
                if isinstance(replay_artifact_raw, dict)
                else None
            ),
            note=d.get("note"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeScenarioStep: {exc}") from exc


def external_regime_scenario_to_dict(scenario: ExternalRegimeScenario) -> dict:
    """Serialize one scenario definition."""
    return {
        "scenario_id": scenario.scenario_id,
        "steps": [external_regime_scenario_step_to_dict(step) for step in scenario.steps],
    }


def external_regime_scenario_from_dict(d: dict) -> ExternalRegimeScenario:
    """Deserialize one scenario definition."""
    try:
        return ExternalRegimeScenario(
            scenario_id=str(d["scenario_id"]),
            steps=tuple(external_regime_scenario_step_from_dict(item) for item in d.get("steps", ())),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeScenario: {exc}") from exc


def external_regime_scenario_step_record_to_dict(record: ExternalRegimeScenarioStepRecord) -> dict:
    """Serialize one scenario step result."""
    return {
        "step_id": record.step_id,
        "received_at_ns": record.received_at_ns,
        "provider": record.provider,
        "operation": record.operation,
        "accepted": record.accepted,
        "partially_accepted": record.partially_accepted,
        "replayed": record.replayed,
        "accepted_count": record.accepted_count,
        "rejected_count": record.rejected_count,
        "changed_dimensions": list(record.changed_dimensions),
        "failed_dimensions": list(record.failed_dimensions),
        "activation_blocked": record.activation_blocked,
        "activation_reason": record.activation_reason,
        "activation_allocation_scale": record.activation_allocation_scale,
        "execution_blocked": record.execution_blocked,
        "execution_reason": record.execution_reason,
        "stale_dimensions": list(record.stale_dimensions),
        "unavailable_dimensions": list(record.unavailable_dimensions),
        "high_risk": record.high_risk,
        "bundle_result": (
            external_regime_bundle_ingestion_record_to_dict(record.bundle_result)
            if record.bundle_result is not None
            else None
        ),
        "dimension_results": [
            external_regime_payload_ingestion_record_to_dict(item) for item in record.dimension_results
        ],
        "snapshot": external_regime_snapshot_to_dict(record.snapshot),
    }


def external_regime_scenario_step_record_from_dict(d: dict) -> ExternalRegimeScenarioStepRecord:
    """Deserialize one scenario step result."""
    try:
        return ExternalRegimeScenarioStepRecord(
            step_id=str(d["step_id"]),
            received_at_ns=int(d["received_at_ns"]),
            provider=str(d["provider"]),
            operation=str(d["operation"]),
            accepted=bool(d["accepted"]),
            partially_accepted=bool(d["partially_accepted"]),
            replayed=bool(d["replayed"]),
            accepted_count=int(d["accepted_count"]),
            rejected_count=int(d["rejected_count"]),
            changed_dimensions=tuple(d.get("changed_dimensions", ())),
            failed_dimensions=tuple(d.get("failed_dimensions", ())),
            activation_blocked=bool(d["activation_blocked"]),
            activation_reason=d.get("activation_reason"),
            activation_allocation_scale=float(d["activation_allocation_scale"]),
            execution_blocked=bool(d["execution_blocked"]),
            execution_reason=d.get("execution_reason"),
            stale_dimensions=tuple(d.get("stale_dimensions", ())),
            unavailable_dimensions=tuple(d.get("unavailable_dimensions", ())),
            high_risk=bool(d["high_risk"]),
            bundle_result=(
                external_regime_bundle_ingestion_record_from_dict(d["bundle_result"])
                if d.get("bundle_result") is not None
                else None
            ),
            dimension_results=tuple(
                external_regime_payload_ingestion_record_from_dict(item) for item in d.get("dimension_results", ())
            ),
            snapshot=external_regime_snapshot_from_dict(d["snapshot"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeScenarioStepRecord: {exc}") from exc


def external_regime_scenario_result_to_dict(result: ExternalRegimeScenarioResult) -> dict:
    """Serialize one completed scenario result."""
    return {
        "scenario_id": result.scenario_id,
        "status": result.status,
        "step_count": result.step_count,
        "accepted_steps": result.accepted_steps,
        "rejected_steps": result.rejected_steps,
        "replayed_steps": result.replayed_steps,
        "partially_accepted_steps": result.partially_accepted_steps,
        "execution_blocked_steps": result.execution_blocked_steps,
        "activation_blocked_steps": result.activation_blocked_steps,
        "activation_reduced_steps": result.activation_reduced_steps,
        "stale_steps": result.stale_steps,
        "unavailable_steps": result.unavailable_steps,
        "high_risk_steps": result.high_risk_steps,
        "safe_steps": result.safe_steps,
        "last_step_ns": result.last_step_ns,
        "summary": result.summary,
        "step_records": [external_regime_scenario_step_record_to_dict(item) for item in result.step_records],
        "final_snapshot": (
            external_regime_snapshot_to_dict(result.final_snapshot) if result.final_snapshot is not None else None
        ),
    }


def external_regime_scenario_result_from_dict(d: dict) -> ExternalRegimeScenarioResult:
    """Deserialize one completed scenario result."""
    try:
        return ExternalRegimeScenarioResult(
            scenario_id=str(d["scenario_id"]),
            status=str(d["status"]),
            step_count=int(d["step_count"]),
            accepted_steps=int(d["accepted_steps"]),
            rejected_steps=int(d["rejected_steps"]),
            replayed_steps=int(d["replayed_steps"]),
            partially_accepted_steps=int(d["partially_accepted_steps"]),
            execution_blocked_steps=int(d["execution_blocked_steps"]),
            activation_blocked_steps=int(d["activation_blocked_steps"]),
            activation_reduced_steps=int(d["activation_reduced_steps"]),
            stale_steps=int(d["stale_steps"]),
            unavailable_steps=int(d["unavailable_steps"]),
            high_risk_steps=int(d["high_risk_steps"]),
            safe_steps=int(d["safe_steps"]),
            last_step_ns=int(d["last_step_ns"]),
            summary=str(d["summary"]),
            step_records=tuple(
                external_regime_scenario_step_record_from_dict(item) for item in d.get("step_records", ())
            ),
            final_snapshot=(
                external_regime_snapshot_from_dict(d["final_snapshot"]) if d.get("final_snapshot") is not None else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeScenarioResult: {exc}") from exc


def load_external_regime_bundle_payload(
    payload: object,
    *,
    input_format: str,
) -> tuple[dict[str, object], ExternalRegimePayloadBundle, str | None]:
    """Load and normalize one multi-dimension external-regime bundle."""
    payload_dict, payload_origin = load_external_regime_payload(payload, input_format=input_format)
    data = _require_payload_dict(
        payload_dict,
        dimension="bundle",
        required_fields=frozenset(),
        allowed_fields=_BUNDLE_PAYLOAD_ALLOWED_FIELDS,
    )
    if not any(data.get(name) is not None for name in ("options", "event", "on_chain")):
        raise ValueError("bundle.missing_dimensions")
    observed_at_ns = _optional_non_negative_int(data, "observed_at_ns")
    bundle_received_at_ns = _optional_non_negative_int(data, "received_at_ns")
    bundle_id = _optional_string(data, "bundle_id")
    source = _optional_string(data, "source")
    for field_name, value in (("bundle_id", bundle_id), ("source", source)):
        if value is not None and not value.strip():
            raise ValueError(f"bundle.{field_name}.must_be_non_empty_string")
    bundle = ExternalRegimePayloadBundle(
        bundle_id=bundle_id,
        source=source,
        observed_at_ns=observed_at_ns,
        received_at_ns=bundle_received_at_ns,
        options=_optional_bundle_dimension_payload(data, "options"),
        event=_optional_bundle_dimension_payload(data, "event"),
        on_chain=_optional_bundle_dimension_payload(data, "on_chain"),
    )
    return data, bundle, payload_origin


def _optional_bundle_dimension_payload(payload: dict[str, object], field_name: str) -> dict[str, object] | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"bundle.{field_name}.must_be_object")
    return dict(value)


def _require_payload_dict(
    payload: object,
    *,
    dimension: str,
    required_fields: frozenset[str],
    allowed_fields: frozenset[str],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError(f"{dimension}.payload_root_must_be_object:{type(payload).__name__}")
    fields = set(payload)
    missing = sorted(required_fields - fields)
    if missing:
        raise ValueError(f"{dimension}.missing_fields:{','.join(missing)}")
    unknown = sorted(fields - allowed_fields)
    if unknown:
        raise ValueError(f"{dimension}.unknown_fields:{','.join(unknown)}")
    return dict(payload)


def _required_non_empty_string(payload: dict[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}.must_be_non_empty_string")
    return value


def _optional_string(payload: dict[str, object], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name}.must_be_string")
    return value


def _required_non_negative_int(payload: dict[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name}.must_be_non_negative_int")
    return value


def _optional_non_negative_int(payload: dict[str, object], field_name: str) -> int | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name}.must_be_non_negative_int")
    return value


def _optional_float(payload: dict[str, object], field_name: str) -> float | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name}.must_be_number")
    return float(value)


def _optional_non_negative_float(payload: dict[str, object], field_name: str) -> float | None:
    value = _optional_float(payload, field_name)
    if value is not None and value < 0.0:
        raise ValueError(f"{field_name}.must_be_non_negative_number")
    return value


def _enum_field(enum_type: type[Enum], payload: dict[str, object], field_name: str):
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}.must_be_non_empty_string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name}.invalid_enum:{value!r}") from exc


def _optional_enum_field(enum_type: type[Enum], payload: dict[str, object], field_name: str, *, default):
    value = payload.get(field_name)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}.must_be_non_empty_string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name}.invalid_enum:{value!r}") from exc


def _build_adapter_evidence(
    evidence: object,
    *,
    provider: str,
    input_format: str,
    payload_origin: str | None,
) -> dict:
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider.must_be_non_empty_string")
    if evidence is None:
        base: dict = {}
    elif isinstance(evidence, dict):
        base = dict(evidence)
    else:
        raise ValueError("evidence.must_be_dict")
    adapter_evidence = {
        "provider": provider,
        "input_format": input_format,
    }
    if payload_origin is not None:
        adapter_evidence["payload_origin"] = payload_origin
    base["adapter"] = adapter_evidence
    return base


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def dimension_freshness_to_dict(f: DimensionFreshness) -> dict:
    """Serialize DimensionFreshness to a plain dict."""
    return {
        "freshness": f.freshness.value,
        "last_update_ns": f.last_update_ns,
        "staleness_seconds": f.staleness_seconds,
        "staleness_threshold_s": f.staleness_threshold_s,
        "source": f.source,
    }


def dimension_freshness_from_dict(d: dict) -> DimensionFreshness:
    """Deserialize DimensionFreshness from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        return DimensionFreshness(
            freshness=DataFreshness(d["freshness"]),
            last_update_ns=d.get("last_update_ns"),
            staleness_seconds=d.get("staleness_seconds"),
            staleness_threshold_s=d.get("staleness_threshold_s"),
            source=d.get("source"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed DimensionFreshness: {exc}") from exc


def external_regime_freshness_policy_to_dict(policy: ExternalRegimeFreshnessPolicy) -> dict:
    """Serialize per-dimension freshness policy."""
    return {
        "options_staleness_threshold_s": policy.options_staleness_threshold_s,
        "event_staleness_threshold_s": policy.event_staleness_threshold_s,
        "on_chain_staleness_threshold_s": policy.on_chain_staleness_threshold_s,
    }


def external_regime_freshness_policy_from_dict(d: dict) -> ExternalRegimeFreshnessPolicy:
    """Deserialize per-dimension freshness policy."""
    try:
        return ExternalRegimeFreshnessPolicy(
            options_staleness_threshold_s=float(d["options_staleness_threshold_s"]),
            event_staleness_threshold_s=float(d["event_staleness_threshold_s"]),
            on_chain_staleness_threshold_s=float(d["on_chain_staleness_threshold_s"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeFreshnessPolicy: {exc}") from exc


def external_regime_provider_profile_to_dict(profile: ExternalRegimeProviderProfile) -> dict:
    """Serialize provider profile."""
    return {
        "provider": profile.provider,
        "trust": profile.trust.value,
        "options_role": profile.options_role.value,
        "event_role": profile.event_role.value,
        "on_chain_role": profile.on_chain_role.value,
    }


def external_regime_provider_profile_from_dict(d: dict) -> ExternalRegimeProviderProfile:
    """Deserialize provider profile."""
    try:
        return ExternalRegimeProviderProfile(
            provider=str(d["provider"]),
            trust=ExternalRegimeProviderTrust(d["trust"]),
            options_role=ExternalRegimeProviderRole(d.get("options_role", ExternalRegimeProviderRole.DISALLOWED.value)),
            event_role=ExternalRegimeProviderRole(d.get("event_role", ExternalRegimeProviderRole.DISALLOWED.value)),
            on_chain_role=ExternalRegimeProviderRole(
                d.get("on_chain_role", ExternalRegimeProviderRole.DISALLOWED.value)
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeProviderProfile: {exc}") from exc


def external_regime_provider_policy_to_dict(policy: ExternalRegimeProviderPolicy) -> dict:
    """Serialize provider policy."""
    return {
        "profiles": [external_regime_provider_profile_to_dict(profile) for profile in policy.profiles],
        "allow_trusted_overwrite_provisional": policy.allow_trusted_overwrite_provisional,
        "allow_provisional_overwrite_trusted": policy.allow_provisional_overwrite_trusted,
        "allow_fallback_overwrite_preferred": policy.allow_fallback_overwrite_preferred,
        "require_trusted_when_current_owner_unknown": policy.require_trusted_when_current_owner_unknown,
    }


def external_regime_provider_policy_from_dict(d: dict) -> ExternalRegimeProviderPolicy:
    """Deserialize provider policy."""
    try:
        return ExternalRegimeProviderPolicy(
            profiles=tuple(external_regime_provider_profile_from_dict(item) for item in d.get("profiles", ()))
            or _DEFAULT_EXTERNAL_REGIME_PROVIDER_PROFILES,
            allow_trusted_overwrite_provisional=bool(d.get("allow_trusted_overwrite_provisional", True)),
            allow_provisional_overwrite_trusted=bool(d.get("allow_provisional_overwrite_trusted", False)),
            allow_fallback_overwrite_preferred=bool(d.get("allow_fallback_overwrite_preferred", False)),
            require_trusted_when_current_owner_unknown=bool(d.get("require_trusted_when_current_owner_unknown", True)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeProviderPolicy: {exc}") from exc


def external_regime_dimension_source_state_to_dict(owner: ExternalRegimeDimensionSourceState) -> dict:
    """Serialize current dimension owner metadata."""
    return {
        "dimension": owner.dimension,
        "ownership_mode": owner.ownership_mode,
        "provider": owner.provider,
        "source_label": owner.source_label,
        "trust": owner.trust,
        "role": owner.role,
        "state_snapshot_ns": owner.state_snapshot_ns,
        "received_at_ns": owner.received_at_ns,
    }


def external_regime_dimension_source_state_from_dict(d: dict) -> ExternalRegimeDimensionSourceState:
    """Deserialize current dimension owner metadata."""
    try:
        return ExternalRegimeDimensionSourceState(
            dimension=str(d["dimension"]),
            ownership_mode=str(d["ownership_mode"]),
            provider=d.get("provider"),
            source_label=d.get("source_label"),
            trust=d.get("trust"),
            role=d.get("role"),
            state_snapshot_ns=(int(d["state_snapshot_ns"]) if d.get("state_snapshot_ns") is not None else None),
            received_at_ns=int(d["received_at_ns"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeDimensionSourceState: {exc}") from exc


def external_regime_snapshot_to_dict(snap: ExternalRegimeSnapshot) -> dict:
    """Serialize ExternalRegimeSnapshot to a plain dict."""
    from crypto_core.execution.regime_contracts import _event_to_dict, _onchain_to_dict, _options_to_dict

    return {
        "snapshot_ns": snap.snapshot_ns,
        "options": _options_to_dict(snap.options) if snap.options else None,
        "event": _event_to_dict(snap.event) if snap.event else None,
        "on_chain": _onchain_to_dict(snap.on_chain) if snap.on_chain else None,
        "options_freshness": dimension_freshness_to_dict(snap.options_freshness),
        "event_freshness": dimension_freshness_to_dict(snap.event_freshness),
        "on_chain_freshness": dimension_freshness_to_dict(snap.on_chain_freshness),
        "any_extreme": snap.any_extreme,
        "any_unavailable_critical": snap.any_unavailable_critical,
        "high_risk_regime_present": snap.high_risk_regime_present,
        "evidence_sufficient": snap.evidence_sufficient,
        "available_dimensions": list(snap.available_dimensions),
        "unavailable_dimensions": list(snap.unavailable_dimensions),
        "stale_dimensions": list(snap.stale_dimensions),
        "regime_summary": snap.regime_summary,
    }


def external_regime_snapshot_from_dict(d: dict) -> ExternalRegimeSnapshot:
    """Deserialize ExternalRegimeSnapshot from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    from crypto_core.execution.regime_contracts import _event_from_dict, _onchain_from_dict, _options_from_dict

    try:
        return ExternalRegimeSnapshot(
            snapshot_ns=int(d["snapshot_ns"]),
            options=(_options_from_dict(d["options"]) if d.get("options") else None),
            event=_event_from_dict(d["event"]) if d.get("event") else None,
            on_chain=(_onchain_from_dict(d["on_chain"]) if d.get("on_chain") else None),
            options_freshness=dimension_freshness_from_dict(d["options_freshness"]),
            event_freshness=dimension_freshness_from_dict(d["event_freshness"]),
            on_chain_freshness=dimension_freshness_from_dict(d["on_chain_freshness"]),
            any_extreme=bool(d["any_extreme"]),
            any_unavailable_critical=bool(d["any_unavailable_critical"]),
            high_risk_regime_present=bool(d["high_risk_regime_present"]),
            evidence_sufficient=bool(d["evidence_sufficient"]),
            available_dimensions=tuple(d.get("available_dimensions", ())),
            unavailable_dimensions=tuple(d.get("unavailable_dimensions", ())),
            stale_dimensions=tuple(d.get("stale_dimensions", ())),
            regime_summary=str(d.get("regime_summary", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeSnapshot: {exc}") from exc


def external_regime_plane_to_dict(plane: ExternalRegimeDataPlane) -> dict:
    """Serialize the current data plane state for persistence."""
    from crypto_core.execution.regime_contracts import _event_to_dict, _onchain_to_dict, _options_to_dict

    return {
        "staleness_threshold_s": plane.staleness_threshold_s,
        "freshness_policy": external_regime_freshness_policy_to_dict(plane.freshness_policy),
        "options": _options_to_dict(plane.options_state) if plane.options_state else None,
        "event": _event_to_dict(plane.event_state) if plane.event_state else None,
        "on_chain": _onchain_to_dict(plane.on_chain_state) if plane.on_chain_state else None,
    }


def external_regime_plane_from_dict(d: dict) -> ExternalRegimeDataPlane:
    """Deserialize the data plane state from persistence."""
    from crypto_core.execution.regime_contracts import _event_from_dict, _onchain_from_dict, _options_from_dict

    try:
        if d.get("freshness_policy") is not None:
            plane = ExternalRegimeDataPlane(
                freshness_policy=external_regime_freshness_policy_from_dict(d["freshness_policy"])
            )
        else:
            threshold = float(d["staleness_threshold_s"])
            plane = ExternalRegimeDataPlane(staleness_threshold_s=threshold)
        if d.get("options") is not None:
            plane.update_options(_options_from_dict(d["options"]))
        if d.get("event") is not None:
            plane.update_event(_event_from_dict(d["event"]))
        if d.get("on_chain") is not None:
            plane.update_on_chain(_onchain_from_dict(d["on_chain"]))
        return plane
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeDataPlane: {exc}") from exc


def external_regime_update_record_to_dict(record: ExternalRegimeUpdateRecord) -> dict:
    """Serialize an update record to a plain dict."""
    return {
        "dimension": record.dimension,
        "status": record.status.value,
        "accepted": record.accepted,
        "received_at_ns": record.received_at_ns,
        "state_snapshot_ns": record.state_snapshot_ns,
        "source_label": record.source_label,
        "level": record.level,
        "freshness": record.freshness.value,
        "replaced_existing": record.replaced_existing,
        "reason": record.reason,
    }


def external_regime_update_record_from_dict(d: dict) -> ExternalRegimeUpdateRecord:
    """Deserialize an update record from a plain dict."""
    try:
        return ExternalRegimeUpdateRecord(
            dimension=str(d["dimension"]),
            status=ExternalRegimeUpdateStatus(d["status"]),
            accepted=bool(d["accepted"]),
            received_at_ns=int(d["received_at_ns"]),
            state_snapshot_ns=(int(d["state_snapshot_ns"]) if d.get("state_snapshot_ns") is not None else None),
            source_label=d.get("source_label"),
            level=d.get("level"),
            freshness=DataFreshness(d["freshness"]),
            replaced_existing=bool(d["replaced_existing"]),
            reason=str(d.get("reason", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed ExternalRegimeUpdateRecord: {exc}") from exc


def external_regime_persistence_state_to_dict(state: ExternalRegimePersistenceState) -> dict:
    """Serialize persistence state to a plain dict."""
    return {
        "evidence_store_configured": state.evidence_store_configured,
        "snapshot_name": state.snapshot_name,
        "snapshot_present": state.snapshot_present,
        "restored_from_snapshot": state.restored_from_snapshot,
        "history_limit": state.history_limit,
    }


class ExternalRegimeManager:
    """Managed update / persistence lifecycle for external regime state.

    Reuses ExternalRegimeDataPlane as the underlying truth engine while adding:
      - deterministic update acceptance / rejection records,
      - bounded recent update history,
      - persistent current-state snapshots,
      - safe restore semantics,
      - operator-facing reporting helpers.
    """

    def __init__(
        self,
        *,
        plane: ExternalRegimeDataPlane | None = None,
        evidence_store: EvidenceStore | None = None,
        provider_policy: ExternalRegimeProviderPolicy | None = None,
        history_limit: int = 50,
    ) -> None:
        if history_limit <= 0:
            raise ValueError(f"history_limit must be > 0, got {history_limit}")
        self._plane = plane or ExternalRegimeDataPlane()
        self._evidence_store = evidence_store
        self._provider_policy = provider_policy or ExternalRegimeProviderPolicy()
        self._history_limit = history_limit
        self._history: deque[ExternalRegimeUpdateRecord] = deque(maxlen=history_limit)
        self._latest_update: ExternalRegimeUpdateRecord | None = None
        self._latest_accepted_payload: ExternalRegimePayloadIngestionRecord | None = None
        self._latest_rejected_payload: ExternalRegimePayloadIngestionRecord | None = None
        self._latest_bundle_result: ExternalRegimeBundleIngestionRecord | None = None
        self._latest_bundle_replay_artifact: ExternalRegimeBundleReplayArtifact | None = None
        self._scenario_status = "idle"
        self._latest_scenario_result: ExternalRegimeScenarioResult | None = None
        self._options_source_owner: ExternalRegimeDimensionSourceState | None = None
        self._event_source_owner: ExternalRegimeDimensionSourceState | None = None
        self._on_chain_source_owner: ExternalRegimeDimensionSourceState | None = None
        self._restored_from_snapshot = False

    @property
    def plane(self) -> ExternalRegimeDataPlane:
        """Underlying external regime data plane."""
        return self._plane

    @property
    def latest_update(self) -> ExternalRegimeUpdateRecord | None:
        """Most recent update attempt, accepted or rejected."""
        return self._latest_update

    @property
    def history_limit(self) -> int:
        """Maximum number of update records retained in memory."""
        return self._history_limit

    @property
    def latest_accepted_payload(self) -> ExternalRegimePayloadIngestionRecord | None:
        """Most recent raw payload accepted through the adapter seam."""
        return self._latest_accepted_payload

    @property
    def latest_rejected_payload(self) -> ExternalRegimePayloadIngestionRecord | None:
        """Most recent raw payload rejected through the adapter seam."""
        return self._latest_rejected_payload

    @property
    def provider_policy(self) -> ExternalRegimeProviderPolicy:
        """Configured provider/source policy for payload ingestion."""
        return self._provider_policy

    @property
    def latest_bundle_result(self) -> ExternalRegimeBundleIngestionRecord | None:
        """Most recent bundle ingestion result."""
        return self._latest_bundle_result

    @property
    def latest_bundle_replay_artifact(self) -> ExternalRegimeBundleReplayArtifact | None:
        """Most recent replayable bundle artifact."""
        return self._latest_bundle_replay_artifact

    @property
    def scenario_status(self) -> str:
        """Most recent scenario runner status."""
        return self._scenario_status

    @property
    def latest_scenario_result(self) -> ExternalRegimeScenarioResult | None:
        """Most recent completed scenario result."""
        return self._latest_scenario_result

    def recent_update_history(self) -> tuple[ExternalRegimeUpdateRecord, ...]:
        """Bounded recent update history, oldest first."""
        return tuple(self._history)

    def has_current_state(self) -> bool:
        """True when at least one regime dimension is currently populated."""
        return any(
            state is not None
            for state in (
                self._plane.options_state,
                self._plane.event_state,
                self._plane.on_chain_state,
            )
        )

    def snapshot(self, now_ns: int) -> ExternalRegimeSnapshot:
        """Current truthful external regime snapshot."""
        return self._plane.snapshot(now_ns)

    def update_options(
        self,
        state: OptionsRegimeState,
        *,
        received_at_ns: int | None = None,
        source_owner: ExternalRegimeDimensionSourceState | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one options regime update with explicit acceptance semantics."""
        return self._apply_update(
            dimension="options",
            state=state,
            expected_type=OptionsRegimeState,
            current_state=self._plane.options_state,
            apply_update=self._plane.update_options,
            received_at_ns=received_at_ns,
            source_owner=(source_owner or self._build_direct_source_owner("options", state, received_at_ns)),
        )

    def update_event(
        self,
        state: EventRegimeState,
        *,
        received_at_ns: int | None = None,
        source_owner: ExternalRegimeDimensionSourceState | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one event regime update with explicit acceptance semantics."""
        return self._apply_update(
            dimension="event",
            state=state,
            expected_type=EventRegimeState,
            current_state=self._plane.event_state,
            apply_update=self._plane.update_event,
            received_at_ns=received_at_ns,
            source_owner=(source_owner or self._build_direct_source_owner("event", state, received_at_ns)),
        )

    def update_on_chain(
        self,
        state: OnChainRegimeState,
        *,
        received_at_ns: int | None = None,
        source_owner: ExternalRegimeDimensionSourceState | None = None,
    ) -> ExternalRegimeUpdateRecord:
        """Apply one on-chain regime update with explicit acceptance semantics."""
        return self._apply_update(
            dimension="on_chain",
            state=state,
            expected_type=OnChainRegimeState,
            current_state=self._plane.on_chain_state,
            apply_update=self._plane.update_on_chain,
            received_at_ns=received_at_ns,
            source_owner=(source_owner or self._build_direct_source_owner("on_chain", state, received_at_ns)),
        )

    def update_composite(
        self,
        *,
        options: OptionsRegimeState | None = None,
        event: EventRegimeState | None = None,
        on_chain: OnChainRegimeState | None = None,
        received_at_ns: int | None = None,
    ) -> tuple[ExternalRegimeUpdateRecord, ...]:
        """Apply multiple dimension updates in one deterministic batch order."""
        results: list[ExternalRegimeUpdateRecord] = []
        if options is not None:
            results.append(self.update_options(options, received_at_ns=received_at_ns))
        if event is not None:
            results.append(self.update_event(event, received_at_ns=received_at_ns))
        if on_chain is not None:
            results.append(self.update_on_chain(on_chain, received_at_ns=received_at_ns))
        return tuple(results)

    def ingest_payload(
        self,
        *,
        dimension: str,
        payload: object,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw external-regime payload."""
        if dimension == "options":
            return self.ingest_options_payload(
                payload,
                provider=provider,
                input_format=input_format,
                received_at_ns=received_at_ns,
            )
        if dimension == "event":
            return self.ingest_event_payload(
                payload,
                provider=provider,
                input_format=input_format,
                received_at_ns=received_at_ns,
            )
        if dimension == "on_chain":
            return self.ingest_on_chain_payload(
                payload,
                provider=provider,
                input_format=input_format,
                received_at_ns=received_at_ns,
            )
        result = ExternalRegimePayloadIngestionRecord(
            dimension=dimension,
            provider=provider,
            input_format=input_format,
            accepted=False,
            received_at_ns=0 if received_at_ns is None else received_at_ns,
            source_label=None,
            state_snapshot_ns=None,
            level=None,
            provider_trust=None,
            provider_role=None,
            freshness_threshold_s=None,
            update_status=None,
            reason=f"invalid_dimension:{dimension!r}",
            rejection_stage="adapter_validation",
            payload_origin=None,
            payload_summary={"provider": provider, "input_format": input_format},
        )
        self._record_payload_ingestion(result)
        return result

    def ingest_options_payload(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw options payload."""
        return self._ingest_payload(
            dimension="options",
            payload=payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=received_at_ns,
            build_state=build_options_regime_state_from_payload,
            apply_update=self.update_options,
        )

    def ingest_event_payload(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw event payload."""
        return self._ingest_payload(
            dimension="event",
            payload=payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=received_at_ns,
            build_state=build_event_regime_state_from_payload,
            apply_update=self.update_event,
        )

    def ingest_on_chain_payload(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        received_at_ns: int | None = None,
    ) -> ExternalRegimePayloadIngestionRecord:
        """Validate and ingest one raw on-chain payload."""
        return self._ingest_payload(
            dimension="on_chain",
            payload=payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=received_at_ns,
            build_state=build_on_chain_regime_state_from_payload,
            apply_update=self.update_on_chain,
        )

    def ingest_bundle_payload(
        self,
        payload: object,
        *,
        provider: str,
        input_format: str = "dict",
        apply_mode: ExternalRegimeBundleApplyMode | str = ExternalRegimeBundleApplyMode.ATOMIC,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeBundleIngestionRecord:
        """Validate and ingest a multi-dimension external-regime bundle."""
        try:
            resolved_apply_mode = ExternalRegimeBundleApplyMode(apply_mode)
        except ValueError:
            result = ExternalRegimeBundleIngestionRecord(
                bundle_id=None,
                provider=provider,
                input_format=input_format,
                apply_mode=str(apply_mode),
                outcome=ExternalRegimeBundleIngestionOutcome.FULLY_REJECTED.value,
                accepted=False,
                partially_accepted=False,
                replayable=False,
                received_at_ns=0 if received_at_ns is None else received_at_ns,
                observed_at_ns=None,
                source=None,
                payload_origin=None,
                dimensions_present=(),
                changed_dimensions=(),
                failed_dimensions=(),
                reason=f"invalid_bundle_apply_mode:{apply_mode!r}",
                dimension_results=(),
            )
            self._record_bundle_ingestion(result, artifact=None)
            return result

        try:
            raw_bundle_payload, bundle, payload_origin = load_external_regime_bundle_payload(
                payload,
                input_format=input_format,
            )
        except ValueError as exc:
            result = ExternalRegimeBundleIngestionRecord(
                bundle_id=None,
                provider=provider,
                input_format=input_format,
                apply_mode=resolved_apply_mode.value,
                outcome=ExternalRegimeBundleIngestionOutcome.FULLY_REJECTED.value,
                accepted=False,
                partially_accepted=False,
                replayable=False,
                received_at_ns=0 if received_at_ns is None else received_at_ns,
                observed_at_ns=None,
                source=None,
                payload_origin=(
                    str(payload) if input_format == "json_file" and isinstance(payload, (str, Path)) else None
                ),
                dimensions_present=(),
                changed_dimensions=(),
                failed_dimensions=(),
                reason=str(exc),
                dimension_results=(),
            )
            self._record_bundle_ingestion(result, artifact=None)
            return result

        bundle_received_at_ns = (
            received_at_ns
            if received_at_ns is not None
            else (bundle.received_at_ns if bundle.received_at_ns is not None else bundle.observed_at_ns)
        )
        dimensions_present = tuple(
            dimension
            for dimension, dimension_payload in (
                ("options", bundle.options),
                ("event", bundle.event),
                ("on_chain", bundle.on_chain),
            )
            if dimension_payload is not None
        )
        prepared_candidates: list[_PreparedExternalRegimePayloadIngestion] = []
        failed_records: list[ExternalRegimePayloadIngestionRecord] = []
        for dimension in dimensions_present:
            prepare_result = self._prepare_payload_ingestion(
                dimension=dimension,
                payload=getattr(bundle, dimension),
                provider=provider,
                input_format="dict",
                received_at_ns=bundle_received_at_ns,
                build_state=self._build_state_for_dimension(dimension),
            )
            if isinstance(prepare_result, ExternalRegimePayloadIngestionRecord):
                failed_records.append(prepare_result)
            else:
                prepared_candidates.append(prepare_result)

        applied_records: list[ExternalRegimePayloadIngestionRecord] = []
        if resolved_apply_mode is ExternalRegimeBundleApplyMode.ATOMIC and failed_records:
            failure_reason = failed_records[0].reason
            dimension_results = list(failed_records)
            for prepared in prepared_candidates:
                dimension_results.append(
                    self._bundle_policy_rejected_record(
                        prepared,
                        reason=f"bundle_atomic_rejected:{failure_reason}",
                    )
                )
            outcome = ExternalRegimeBundleIngestionOutcome.FULLY_REJECTED
        else:
            for prepared in prepared_candidates:
                applied_records.append(self._apply_prepared_payload_ingestion(prepared))
            dimension_results = [*applied_records, *failed_records]
            accepted_records = [record for record in dimension_results if record.accepted]
            rejected_records = [record for record in dimension_results if not record.accepted]
            if rejected_records and accepted_records:
                outcome = ExternalRegimeBundleIngestionOutcome.PARTIALLY_ACCEPTED
            elif rejected_records:
                outcome = ExternalRegimeBundleIngestionOutcome.FULLY_REJECTED
            else:
                outcome = ExternalRegimeBundleIngestionOutcome.FULLY_ACCEPTED

        ordered_dimension_results = tuple(
            sorted(dimension_results, key=lambda item: dimensions_present.index(item.dimension))
        )
        changed_dimensions = tuple(record.dimension for record in ordered_dimension_results if record.accepted)
        failed_dimensions = tuple(record.dimension for record in ordered_dimension_results if not record.accepted)
        result = ExternalRegimeBundleIngestionRecord(
            bundle_id=bundle.bundle_id,
            provider=provider,
            input_format=input_format,
            apply_mode=resolved_apply_mode.value,
            outcome=outcome.value,
            accepted=outcome is ExternalRegimeBundleIngestionOutcome.FULLY_ACCEPTED,
            partially_accepted=outcome is ExternalRegimeBundleIngestionOutcome.PARTIALLY_ACCEPTED,
            replayable=True,
            received_at_ns=0 if bundle_received_at_ns is None else bundle_received_at_ns,
            observed_at_ns=bundle.observed_at_ns,
            source=bundle.source,
            payload_origin=payload_origin,
            dimensions_present=dimensions_present,
            changed_dimensions=changed_dimensions,
            failed_dimensions=failed_dimensions,
            reason=self._bundle_reason_from_outcome(outcome, dimension_results),
            dimension_results=ordered_dimension_results,
        )
        artifact = ExternalRegimeBundleReplayArtifact(
            bundle_id=bundle.bundle_id,
            provider=provider,
            input_format=input_format,
            apply_mode=resolved_apply_mode.value,
            received_at_ns=0 if bundle_received_at_ns is None else bundle_received_at_ns,
            observed_at_ns=bundle.observed_at_ns,
            source=bundle.source,
            payload_origin=payload_origin,
            raw_bundle_payload=raw_bundle_payload,
            normalized_bundle=bundle,
            result=result,
        )
        self._record_bundle_ingestion(result, artifact=artifact)
        return result

    def replay_bundle_artifact(
        self,
        artifact: ExternalRegimeBundleReplayArtifact,
        *,
        received_at_ns: int | None = None,
    ) -> ExternalRegimeBundleIngestionRecord:
        """Replay a previously captured bundle artifact through the same ingestion path."""
        if not isinstance(artifact, ExternalRegimeBundleReplayArtifact):
            raise ValueError(f"artifact must be ExternalRegimeBundleReplayArtifact, got {type(artifact).__name__}")
        return self.ingest_bundle_payload(
            dict(artifact.raw_bundle_payload),
            provider=artifact.provider,
            input_format="dict",
            apply_mode=artifact.apply_mode,
            received_at_ns=(artifact.received_at_ns if received_at_ns is None else received_at_ns),
        )

    def run_scenario(
        self,
        scenario: ExternalRegimeScenario,
        *,
        policy: ExternalRegimeSafetyPolicy | None = None,
    ) -> ExternalRegimeScenarioResult:
        """Replay a deterministic sequence of external-regime steps."""
        if not isinstance(scenario, ExternalRegimeScenario):
            raise ValueError(f"scenario must be ExternalRegimeScenario, got {type(scenario).__name__}")
        resolved_policy = policy or ExternalRegimeSafetyPolicy()
        self._scenario_status = "running"
        step_records: list[ExternalRegimeScenarioStepRecord] = []
        try:
            for step in scenario.steps:
                step_records.append(self._run_scenario_step(step, resolved_policy))
            result = self._build_scenario_result(scenario.scenario_id, step_records)
            self._latest_scenario_result = result
            self._scenario_status = result.status
            self._append_audit_record(
                event_name="external_regime_scenario_run",
                data=external_regime_scenario_result_to_dict(result),
            )
            self.persist_state()
            return result
        except Exception:
            self._scenario_status = "failed"
            raise

    def reset(
        self,
        *,
        received_at_ns: int,
        reason: str = "operator_reset",
        source_label: str = "operator_reset",
    ) -> ExternalRegimeUpdateRecord:
        """Explicitly clear all regime dimensions and persist the cleared state."""
        if not isinstance(received_at_ns, int) or received_at_ns < 0:
            raise ValueError(f"received_at_ns must be >= 0, got {received_at_ns!r}")
        replaced_existing = self.has_current_state()
        self._plane.reset()
        self._restored_from_snapshot = False
        record = ExternalRegimeUpdateRecord(
            dimension="all",
            status=ExternalRegimeUpdateStatus.RESET,
            accepted=True,
            received_at_ns=received_at_ns,
            state_snapshot_ns=None,
            source_label=source_label,
            level=None,
            freshness=DataFreshness.UNAVAILABLE,
            replaced_existing=replaced_existing,
            reason=reason,
        )
        self._record(record)
        return record

    def persist_state(self) -> WriteResult | None:
        """Persist the managed external regime state snapshot."""
        if self._evidence_store is None:
            return None
        return self._evidence_store.save_snapshot(
            _EXTERNAL_REGIME_SNAPSHOT_NAME,
            self._state_to_dict(),
        )

    def restore_state(self) -> bool:
        """Restore the last persisted external regime state, if present."""
        if self._evidence_store is None:
            raise RuntimeError("No evidence store configured for external regime restore")
        if self.has_current_state():
            raise RuntimeError("Cannot restore external regime over existing in-memory state")
        if not self._evidence_store.snapshot_exists(_EXTERNAL_REGIME_SNAPSHOT_NAME):
            return False

        try:
            envelope = self._evidence_store.load_snapshot(_EXTERNAL_REGIME_SNAPSHOT_NAME)
        except EvidenceStoreCorruptError as exc:
            raise ExternalRegimeStateCorruptError(str(exc)) from exc

        data = envelope.get("data")
        if not isinstance(data, dict):
            raise ExternalRegimeStateCorruptError(
                f"External regime state 'data' must be a dict, got {type(data).__name__!r}"
            )

        required = {"plane", "history_limit", "recent_history", "persistence"}
        missing = required - set(data)
        if missing:
            raise ExternalRegimeStateCorruptError(f"External regime state missing required fields: {sorted(missing)!r}")

        try:
            plane = external_regime_plane_from_dict(data["plane"])
            history_limit = int(data["history_limit"])
            if history_limit <= 0:
                raise ValueError(f"history_limit must be > 0, got {history_limit}")
            history = [external_regime_update_record_from_dict(item) for item in data.get("recent_history", [])]
            latest_accepted_payload_raw = data.get("latest_accepted_payload")
            latest_rejected_payload_raw = data.get("latest_rejected_payload")
            latest_raw = data.get("latest_update")
            latest = (
                external_regime_update_record_from_dict(latest_raw)
                if latest_raw is not None
                else (history[-1] if history else None)
            )
            latest_accepted_payload = (
                external_regime_payload_ingestion_record_from_dict(latest_accepted_payload_raw)
                if latest_accepted_payload_raw is not None
                else None
            )
            latest_rejected_payload = (
                external_regime_payload_ingestion_record_from_dict(latest_rejected_payload_raw)
                if latest_rejected_payload_raw is not None
                else None
            )
            latest_bundle_result_raw = data.get("latest_bundle_result")
            latest_bundle_artifact_raw = data.get("latest_bundle_replay_artifact")
            latest_bundle_result = (
                external_regime_bundle_ingestion_record_from_dict(latest_bundle_result_raw)
                if latest_bundle_result_raw is not None
                else None
            )
            latest_bundle_artifact = (
                external_regime_bundle_replay_artifact_from_dict(latest_bundle_artifact_raw)
                if latest_bundle_artifact_raw is not None
                else None
            )
            latest_scenario_result_raw = data.get("latest_scenario_result")
            latest_scenario_result = (
                external_regime_scenario_result_from_dict(latest_scenario_result_raw)
                if latest_scenario_result_raw is not None
                else None
            )
        except ValueError as exc:
            raise ExternalRegimeStateCorruptError(str(exc)) from exc

        self._plane = plane
        self._history_limit = history_limit
        self._history = deque(history, maxlen=history_limit)
        self._latest_update = latest
        self._latest_accepted_payload = latest_accepted_payload
        self._latest_rejected_payload = latest_rejected_payload
        self._latest_bundle_result = latest_bundle_result
        self._latest_bundle_replay_artifact = latest_bundle_artifact
        self._scenario_status = str(data.get("scenario_status", "idle"))
        self._latest_scenario_result = latest_scenario_result
        self._provider_policy = (
            external_regime_provider_policy_from_dict(data["provider_policy"])
            if data.get("provider_policy") is not None
            else ExternalRegimeProviderPolicy()
        )
        source_owners = data.get("current_dimension_sources", {})
        if source_owners is not None and not isinstance(source_owners, dict):
            raise ExternalRegimeStateCorruptError("current_dimension_sources must be a dict")
        self._options_source_owner = (
            external_regime_dimension_source_state_from_dict(source_owners["options"])
            if isinstance(source_owners, dict) and source_owners.get("options") is not None
            else None
        )
        self._event_source_owner = (
            external_regime_dimension_source_state_from_dict(source_owners["event"])
            if isinstance(source_owners, dict) and source_owners.get("event") is not None
            else None
        )
        self._on_chain_source_owner = (
            external_regime_dimension_source_state_from_dict(source_owners["on_chain"])
            if isinstance(source_owners, dict) and source_owners.get("on_chain") is not None
            else None
        )
        self._restored_from_snapshot = True
        self._append_audit_record(
            event_name="external_regime_restore",
            data={
                "snapshot_name": _EXTERNAL_REGIME_SNAPSHOT_NAME,
                "restored": True,
                "history_count": len(history),
                "has_current_state": self.has_current_state(),
            },
        )
        return True

    def persistence_state(self) -> ExternalRegimePersistenceState:
        """Current persistence / restore status."""
        snapshot_present = False
        if self._evidence_store is not None:
            snapshot_present = self._evidence_store.snapshot_exists(_EXTERNAL_REGIME_SNAPSHOT_NAME)
        return ExternalRegimePersistenceState(
            evidence_store_configured=self._evidence_store is not None,
            snapshot_name=_EXTERNAL_REGIME_SNAPSHOT_NAME,
            snapshot_present=snapshot_present,
            restored_from_snapshot=self._restored_from_snapshot,
            history_limit=self._history_limit,
        )

    def status_dict(self, now_ns: int) -> dict:
        """Operator-facing lifecycle view of current regime state."""
        snap = self.snapshot(now_ns)
        return {
            "current_snapshot": external_regime_snapshot_to_dict(snap),
            "freshness_policy": external_regime_freshness_policy_to_dict(self._plane.freshness_policy),
            "provider_policy": external_regime_provider_policy_to_dict(self._provider_policy),
            "current_dimension_sources": {
                "options": self._dimension_source_owner_to_dict(self._options_source_owner),
                "event": self._dimension_source_owner_to_dict(self._event_source_owner),
                "on_chain": self._dimension_source_owner_to_dict(self._on_chain_source_owner),
            },
            "latest_update": (
                external_regime_update_record_to_dict(self._latest_update) if self._latest_update is not None else None
            ),
            "latest_accepted_payload": (
                external_regime_payload_ingestion_record_to_dict(self._latest_accepted_payload)
                if self._latest_accepted_payload is not None
                else None
            ),
            "latest_rejected_payload": (
                external_regime_payload_ingestion_record_to_dict(self._latest_rejected_payload)
                if self._latest_rejected_payload is not None
                else None
            ),
            "latest_bundle_result": (
                external_regime_bundle_ingestion_record_to_dict(self._latest_bundle_result)
                if self._latest_bundle_result is not None
                else None
            ),
            "latest_bundle_replay_artifact": (
                external_regime_bundle_replay_artifact_to_dict(self._latest_bundle_replay_artifact)
                if self._latest_bundle_replay_artifact is not None
                else None
            ),
            "scenario_status": self._scenario_status,
            "latest_scenario_result": (
                external_regime_scenario_result_to_dict(self._latest_scenario_result)
                if self._latest_scenario_result is not None
                else None
            ),
            "recent_history": [external_regime_update_record_to_dict(record) for record in self._history],
            "persistence": external_regime_persistence_state_to_dict(self.persistence_state()),
        }

    def _ingest_payload(
        self,
        *,
        dimension: str,
        payload: object,
        provider: str,
        input_format: str,
        received_at_ns: int | None,
        build_state,
        apply_update,
    ) -> ExternalRegimePayloadIngestionRecord:
        prepared = self._prepare_payload_ingestion(
            dimension=dimension,
            payload=payload,
            provider=provider,
            input_format=input_format,
            received_at_ns=received_at_ns,
            build_state=build_state,
        )
        if isinstance(prepared, ExternalRegimePayloadIngestionRecord):
            self._record_payload_ingestion(prepared)
            return prepared
        result = self._apply_prepared_payload_ingestion(prepared, apply_update=apply_update)
        self._record_payload_ingestion(result)
        return result

    def _prepare_payload_ingestion(
        self,
        *,
        dimension: str,
        payload: object,
        provider: str,
        input_format: str,
        received_at_ns: int | None,
        build_state,
    ) -> _PreparedExternalRegimePayloadIngestion | ExternalRegimePayloadIngestionRecord:
        threshold_s = self._plane.freshness_policy.threshold_for_dimension(dimension)
        profile, role = self._resolve_provider_context(provider=provider, dimension=dimension)
        payload_origin: str | None = None
        payload_summary: dict[str, object] = {
            "provider": provider,
            "input_format": input_format,
            "provider_trust": None if profile is None else profile.trust.value,
            "provider_role": None if role is None else role.value,
            "freshness_threshold_s": threshold_s,
        }
        resolved_received_at_ns = received_at_ns
        if received_at_ns is not None and (not isinstance(received_at_ns, int) or received_at_ns < 0):
            return ExternalRegimePayloadIngestionRecord(
                dimension=dimension,
                provider=provider,
                input_format=input_format,
                accepted=False,
                received_at_ns=0 if not isinstance(received_at_ns, int) else received_at_ns,
                source_label=None,
                state_snapshot_ns=None,
                level=None,
                provider_trust=None if profile is None else profile.trust.value,
                provider_role=None if role is None else role.value,
                freshness_threshold_s=threshold_s,
                update_status=None,
                reason=f"invalid_received_at_ns:{received_at_ns!r}",
                rejection_stage="adapter_validation",
                payload_origin=None,
                payload_summary=payload_summary,
            )

        try:
            payload_dict, payload_origin = load_external_regime_payload(payload, input_format=input_format)
            state = build_state(
                payload_dict,
                provider=provider,
                input_format=input_format,
                payload_origin=payload_origin,
            )
        except ValueError as exc:
            if input_format == "json_file" and isinstance(payload, (str, Path)):
                payload_origin = str(payload)
            if payload_origin is not None:
                payload_summary["payload_origin"] = payload_origin
            return ExternalRegimePayloadIngestionRecord(
                dimension=dimension,
                provider=provider,
                input_format=input_format,
                accepted=False,
                received_at_ns=0 if resolved_received_at_ns is None else resolved_received_at_ns,
                source_label=None,
                state_snapshot_ns=None,
                level=None,
                provider_trust=None if profile is None else profile.trust.value,
                provider_role=None if role is None else role.value,
                freshness_threshold_s=threshold_s,
                update_status=None,
                reason=str(exc),
                rejection_stage="adapter_validation",
                payload_origin=payload_origin,
                payload_summary=payload_summary,
            )

        resolved_received_at_ns = state.snapshot_ns if resolved_received_at_ns is None else resolved_received_at_ns
        payload_summary = _payload_summary_for_state(
            dimension=dimension,
            provider=provider,
            input_format=input_format,
            payload_origin=payload_origin,
            state=state,
        )
        payload_summary["provider_trust"] = None if profile is None else profile.trust.value
        payload_summary["provider_role"] = None if role is None else role.value
        payload_summary["freshness_threshold_s"] = threshold_s
        current_owner = self._dimension_source_owner(dimension)
        if current_owner is not None:
            payload_summary["current_owner_provider"] = current_owner.provider
            payload_summary["current_owner_trust"] = current_owner.trust
            payload_summary["current_owner_role"] = current_owner.role

        source_policy_reason = self._validate_payload_source_policy(
            dimension=dimension,
            state=state,
            provider=provider,
            profile=profile,
            role=role,
        )
        if source_policy_reason is not None:
            return ExternalRegimePayloadIngestionRecord(
                dimension=dimension,
                provider=provider,
                input_format=input_format,
                accepted=False,
                received_at_ns=resolved_received_at_ns,
                source_label=state.source,
                state_snapshot_ns=state.snapshot_ns,
                level=state.level.value,
                provider_trust=None if profile is None else profile.trust.value,
                provider_role=None if role is None else role.value,
                freshness_threshold_s=threshold_s,
                update_status=None,
                reason=source_policy_reason,
                rejection_stage="source_policy",
                payload_origin=payload_origin,
                payload_summary=payload_summary,
            )

        update_validation_rejection = self._validate_update(
            dimension=dimension,
            state=state,
            expected_type=self._expected_type_for_dimension(dimension),
            current_state=self._current_state_for_dimension(dimension),
            received_at_ns=resolved_received_at_ns,
        )
        if update_validation_rejection is not None:
            return ExternalRegimePayloadIngestionRecord(
                dimension=dimension,
                provider=provider,
                input_format=input_format,
                accepted=False,
                received_at_ns=resolved_received_at_ns,
                source_label=update_validation_rejection.source_label,
                state_snapshot_ns=update_validation_rejection.state_snapshot_ns,
                level=update_validation_rejection.level,
                provider_trust=None if profile is None else profile.trust.value,
                provider_role=None if role is None else role.value,
                freshness_threshold_s=threshold_s,
                update_status=update_validation_rejection.status.value,
                reason=update_validation_rejection.reason,
                rejection_stage="update_validation",
                payload_origin=payload_origin,
                payload_summary=payload_summary,
            )

        return _PreparedExternalRegimePayloadIngestion(
            dimension=dimension,
            provider=provider,
            input_format=input_format,
            received_at_ns=resolved_received_at_ns,
            payload_origin=payload_origin,
            payload_summary=payload_summary,
            state=state,
            provider_trust=None if profile is None else profile.trust.value,
            provider_role=None if role is None else role.value,
            freshness_threshold_s=threshold_s,
        )

    def _apply_prepared_payload_ingestion(
        self,
        prepared: _PreparedExternalRegimePayloadIngestion,
        *,
        apply_update=None,
    ) -> ExternalRegimePayloadIngestionRecord:
        update_func = apply_update or self._apply_update_for_dimension(prepared.dimension)
        update_record = update_func(
            prepared.state,
            received_at_ns=prepared.received_at_ns,
            source_owner=self._build_payload_source_owner(
                dimension=prepared.dimension,
                provider=prepared.provider,
                state=prepared.state,
                trust=prepared.provider_trust,
                role=prepared.provider_role,
                received_at_ns=prepared.received_at_ns,
            ),
        )
        return ExternalRegimePayloadIngestionRecord(
            dimension=prepared.dimension,
            provider=prepared.provider,
            input_format=prepared.input_format,
            accepted=update_record.accepted,
            received_at_ns=prepared.received_at_ns,
            source_label=update_record.source_label,
            state_snapshot_ns=update_record.state_snapshot_ns,
            level=update_record.level,
            provider_trust=prepared.provider_trust,
            provider_role=prepared.provider_role,
            freshness_threshold_s=prepared.freshness_threshold_s,
            update_status=update_record.status.value,
            reason=update_record.reason,
            rejection_stage=None if update_record.accepted else "update_validation",
            payload_origin=prepared.payload_origin,
            payload_summary=dict(prepared.payload_summary),
        )

    @staticmethod
    def _bundle_policy_rejected_record(
        prepared: _PreparedExternalRegimePayloadIngestion,
        *,
        reason: str,
    ) -> ExternalRegimePayloadIngestionRecord:
        return ExternalRegimePayloadIngestionRecord(
            dimension=prepared.dimension,
            provider=prepared.provider,
            input_format=prepared.input_format,
            accepted=False,
            received_at_ns=prepared.received_at_ns,
            source_label=prepared.state.source,
            state_snapshot_ns=prepared.state.snapshot_ns,
            level=prepared.state.level.value,
            provider_trust=prepared.provider_trust,
            provider_role=prepared.provider_role,
            freshness_threshold_s=prepared.freshness_threshold_s,
            update_status=None,
            reason=reason,
            rejection_stage="bundle_policy",
            payload_origin=prepared.payload_origin,
            payload_summary=dict(prepared.payload_summary),
        )

    def _apply_update(
        self,
        *,
        dimension: str,
        state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
        expected_type: type,
        current_state: OptionsRegimeState | EventRegimeState | OnChainRegimeState | None,
        apply_update,
        received_at_ns: int | None,
        source_owner: ExternalRegimeDimensionSourceState | None,
    ) -> ExternalRegimeUpdateRecord:
        received = state.snapshot_ns if received_at_ns is None else received_at_ns
        rejected = self._validate_update(
            dimension=dimension,
            state=state,
            expected_type=expected_type,
            current_state=current_state,
            received_at_ns=received,
        )
        if rejected is not None:
            self._record(rejected)
            return rejected

        replaced_existing = current_state is not None and state.snapshot_ns > current_state.snapshot_ns
        apply_update(state)
        if source_owner is not None:
            self._set_dimension_source_owner(dimension, source_owner)
        snap = self._plane.snapshot(received)
        record = ExternalRegimeUpdateRecord(
            dimension=dimension,
            status=ExternalRegimeUpdateStatus.ACCEPTED,
            accepted=True,
            received_at_ns=received,
            state_snapshot_ns=state.snapshot_ns,
            source_label=state.source,
            level=state.level.value,
            freshness=self._dimension_freshness(snap, dimension),
            replaced_existing=replaced_existing,
            reason="accepted",
        )
        self._restored_from_snapshot = False
        self._record(record)
        return record

    def _validate_update(
        self,
        *,
        dimension: str,
        state: object,
        expected_type: type,
        current_state: OptionsRegimeState | EventRegimeState | OnChainRegimeState | None,
        received_at_ns: int,
    ) -> ExternalRegimeUpdateRecord | None:
        if not isinstance(received_at_ns, int) or received_at_ns < 0:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=0 if not isinstance(received_at_ns, int) else received_at_ns,
                source_label=None,
                reason=f"invalid_received_at_ns:{received_at_ns!r}",
            )

        if not isinstance(state, expected_type):
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=None,
                reason=f"invalid_type:{type(state).__name__}",
            )

        if not isinstance(state.snapshot_ns, int) or state.snapshot_ns < 0:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=state.source if isinstance(state.source, str) else None,
                reason=f"invalid_snapshot_ns:{state.snapshot_ns!r}",
            )

        if not isinstance(state.source, str) or not state.source.strip():
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=None,
                reason="missing_source_label",
            )

        symbol = getattr(state, "symbol", None)
        if dimension in {"options", "on_chain"} and (not isinstance(symbol, str) or not symbol.strip()):
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=state.source,
                reason="missing_symbol",
            )

        if current_state is not None and state.snapshot_ns < current_state.snapshot_ns:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_STALE,
                received_at_ns=received_at_ns,
                source_label=state.source,
                reason=f"stale_update:{state.snapshot_ns}<{current_state.snapshot_ns}",
                state_snapshot_ns=state.snapshot_ns,
                level=state.level.value,
            )

        if current_state is not None and state.snapshot_ns == current_state.snapshot_ns and state != current_state:
            return self._rejected_record(
                dimension=dimension,
                status=ExternalRegimeUpdateStatus.REJECTED_INVALID,
                received_at_ns=received_at_ns,
                source_label=state.source,
                reason="contradictory_same_timestamp",
                state_snapshot_ns=state.snapshot_ns,
                level=state.level.value,
            )

        return None

    def _record(self, record: ExternalRegimeUpdateRecord) -> None:
        self._latest_update = record
        self._history.append(record)
        self._append_audit_record(
            event_name="external_regime_update",
            data=external_regime_update_record_to_dict(record),
        )
        self.persist_state()

    def _record_payload_ingestion(self, record: ExternalRegimePayloadIngestionRecord) -> None:
        if record.accepted:
            self._latest_accepted_payload = record
        else:
            self._latest_rejected_payload = record
        self._append_audit_record(
            event_name="external_regime_payload_ingestion",
            data=external_regime_payload_ingestion_record_to_dict(record),
        )
        self.persist_state()

    def _record_bundle_ingestion(
        self,
        record: ExternalRegimeBundleIngestionRecord,
        *,
        artifact: ExternalRegimeBundleReplayArtifact | None,
    ) -> None:
        self._latest_bundle_result = record
        self._latest_bundle_replay_artifact = artifact
        self._append_audit_record(
            event_name="external_regime_bundle_ingestion",
            data=external_regime_bundle_ingestion_record_to_dict(record),
        )
        self.persist_state()

    @staticmethod
    def _bundle_reason_from_outcome(
        outcome: ExternalRegimeBundleIngestionOutcome,
        dimension_results: list[ExternalRegimePayloadIngestionRecord],
    ) -> str:
        if outcome is ExternalRegimeBundleIngestionOutcome.FULLY_ACCEPTED:
            return "accepted"
        if not dimension_results:
            return "bundle_rejected"
        first_failure = next((record.reason for record in dimension_results if not record.accepted), "bundle_rejected")
        if outcome is ExternalRegimeBundleIngestionOutcome.PARTIALLY_ACCEPTED:
            return f"partial:{first_failure}"
        return first_failure

    def _build_state_for_dimension(self, dimension: str):
        if dimension == "options":
            return build_options_regime_state_from_payload
        if dimension == "event":
            return build_event_regime_state_from_payload
        if dimension == "on_chain":
            return build_on_chain_regime_state_from_payload
        raise ValueError(f"unsupported_dimension:{dimension!r}")

    def _apply_update_for_dimension(self, dimension: str):
        if dimension == "options":
            return self.update_options
        if dimension == "event":
            return self.update_event
        if dimension == "on_chain":
            return self.update_on_chain
        raise ValueError(f"unsupported_dimension:{dimension!r}")

    @staticmethod
    def _expected_type_for_dimension(dimension: str) -> type:
        if dimension == "options":
            return OptionsRegimeState
        if dimension == "event":
            return EventRegimeState
        if dimension == "on_chain":
            return OnChainRegimeState
        raise ValueError(f"unsupported_dimension:{dimension!r}")

    def _resolve_provider_context(
        self,
        *,
        provider: str,
        dimension: str,
    ) -> tuple[ExternalRegimeProviderProfile | None, ExternalRegimeProviderRole | None]:
        if not isinstance(provider, str) or not provider.strip():
            return None, None
        profile = self._provider_policy.profile_for_provider(provider)
        return profile, profile.role_for_dimension(dimension)

    def _validate_payload_source_policy(
        self,
        *,
        dimension: str,
        state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
        provider: str,
        profile: ExternalRegimeProviderProfile | None,
        role: ExternalRegimeProviderRole | None,
    ) -> str | None:
        if profile is None or role is None:
            return "invalid_provider_context"
        if profile.trust is ExternalRegimeProviderTrust.UNSUPPORTED:
            return f"unsupported_provider:{provider}"
        if role is ExternalRegimeProviderRole.DISALLOWED:
            return f"provider_not_allowed_for_dimension:{provider}:{dimension}"

        current_state = self._current_state_for_dimension(dimension)
        current_owner = self._dimension_source_owner(dimension)
        if current_state is None:
            return None

        if state.snapshot_ns == current_state.snapshot_ns:
            if current_owner is None:
                return "equal_timestamp_owner_unknown"
            if (
                provider != current_owner.provider
                or profile.trust.value != current_owner.trust
                or role.value != current_owner.role
            ):
                return f"equal_timestamp_source_conflict:{provider}:{current_owner.provider or 'unknown'}"
            return None

        if current_owner is None or current_owner.trust is None:
            if (
                self._provider_policy.require_trusted_when_current_owner_unknown
                and profile.trust is not ExternalRegimeProviderTrust.TRUSTED
            ):
                return f"owner_metadata_missing_requires_trusted:{provider}:{dimension}"
            return None

        incoming_rank = _provider_trust_rank(profile.trust.value)
        current_rank = _provider_trust_rank(current_owner.trust)
        if incoming_rank < current_rank and not self._provider_policy.allow_provisional_overwrite_trusted:
            return f"lower_trust_overwrite_blocked:{profile.trust.value}<{current_owner.trust}"
        if (
            incoming_rank > current_rank
            and not self._provider_policy.allow_trusted_overwrite_provisional
            and current_owner.trust == ExternalRegimeProviderTrust.PROVISIONAL.value
        ):
            return f"higher_trust_overwrite_blocked:{profile.trust.value}>{current_owner.trust}"
        if (
            incoming_rank == current_rank
            and current_owner.role == ExternalRegimeProviderRole.PREFERRED.value
            and role is ExternalRegimeProviderRole.FALLBACK
            and not self._provider_policy.allow_fallback_overwrite_preferred
        ):
            return f"fallback_overwrite_blocked:{provider}:{dimension}"
        return None

    def _build_direct_source_owner(
        self,
        dimension: str,
        state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
        received_at_ns: int | None,
    ) -> ExternalRegimeDimensionSourceState:
        return ExternalRegimeDimensionSourceState(
            dimension=dimension,
            ownership_mode="direct_update",
            provider=None,
            source_label=state.source,
            trust=None,
            role=None,
            state_snapshot_ns=state.snapshot_ns,
            received_at_ns=state.snapshot_ns if received_at_ns is None else received_at_ns,
        )

    @staticmethod
    def _build_payload_source_owner(
        *,
        dimension: str,
        provider: str,
        state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
        trust: str | None,
        role: str | None,
        received_at_ns: int,
    ) -> ExternalRegimeDimensionSourceState:
        return ExternalRegimeDimensionSourceState(
            dimension=dimension,
            ownership_mode="payload_ingestion",
            provider=provider,
            source_label=state.source,
            trust=trust,
            role=role,
            state_snapshot_ns=state.snapshot_ns,
            received_at_ns=received_at_ns,
        )

    def _current_state_for_dimension(
        self,
        dimension: str,
    ) -> OptionsRegimeState | EventRegimeState | OnChainRegimeState | None:
        if dimension == "options":
            return self._plane.options_state
        if dimension == "event":
            return self._plane.event_state
        if dimension == "on_chain":
            return self._plane.on_chain_state
        raise ValueError(f"unsupported_dimension:{dimension!r}")

    def _dimension_source_owner(self, dimension: str) -> ExternalRegimeDimensionSourceState | None:
        if dimension == "options":
            return self._options_source_owner
        if dimension == "event":
            return self._event_source_owner
        if dimension == "on_chain":
            return self._on_chain_source_owner
        raise ValueError(f"unsupported_dimension:{dimension!r}")

    def _set_dimension_source_owner(self, dimension: str, owner: ExternalRegimeDimensionSourceState) -> None:
        if dimension == "options":
            self._options_source_owner = owner
            return
        if dimension == "event":
            self._event_source_owner = owner
            return
        if dimension == "on_chain":
            self._on_chain_source_owner = owner
            return
        raise ValueError(f"unsupported_dimension:{dimension!r}")

    @staticmethod
    def _dimension_source_owner_to_dict(owner: ExternalRegimeDimensionSourceState | None) -> dict | None:
        if owner is None:
            return None
        return external_regime_dimension_source_state_to_dict(owner)

    def _append_audit_record(self, *, event_name: str, data: dict) -> None:
        if self._evidence_store is None:
            return
        payload = {"record_type": event_name, **data}
        self._evidence_store.append_evidence("audit_record", payload)

    @staticmethod
    def _dimension_freshness(snap: ExternalRegimeSnapshot, dimension: str) -> DataFreshness:
        if dimension == "options":
            return snap.options_freshness.freshness
        if dimension == "event":
            return snap.event_freshness.freshness
        if dimension == "on_chain":
            return snap.on_chain_freshness.freshness
        return DataFreshness.UNAVAILABLE

    @staticmethod
    def _rejected_record(
        *,
        dimension: str,
        status: ExternalRegimeUpdateStatus,
        received_at_ns: int,
        source_label: str | None,
        reason: str,
        state_snapshot_ns: int | None = None,
        level: str | None = None,
    ) -> ExternalRegimeUpdateRecord:
        return ExternalRegimeUpdateRecord(
            dimension=dimension,
            status=status,
            accepted=False,
            received_at_ns=received_at_ns,
            state_snapshot_ns=state_snapshot_ns,
            source_label=source_label,
            level=level,
            freshness=DataFreshness.UNAVAILABLE,
            replaced_existing=False,
            reason=reason,
        )

    def _state_to_dict(self) -> dict:
        return {
            "plane": external_regime_plane_to_dict(self._plane),
            "provider_policy": external_regime_provider_policy_to_dict(self._provider_policy),
            "current_dimension_sources": {
                "options": self._dimension_source_owner_to_dict(self._options_source_owner),
                "event": self._dimension_source_owner_to_dict(self._event_source_owner),
                "on_chain": self._dimension_source_owner_to_dict(self._on_chain_source_owner),
            },
            "history_limit": self._history_limit,
            "latest_update": (
                external_regime_update_record_to_dict(self._latest_update) if self._latest_update is not None else None
            ),
            "latest_accepted_payload": (
                external_regime_payload_ingestion_record_to_dict(self._latest_accepted_payload)
                if self._latest_accepted_payload is not None
                else None
            ),
            "latest_rejected_payload": (
                external_regime_payload_ingestion_record_to_dict(self._latest_rejected_payload)
                if self._latest_rejected_payload is not None
                else None
            ),
            "latest_bundle_result": (
                external_regime_bundle_ingestion_record_to_dict(self._latest_bundle_result)
                if self._latest_bundle_result is not None
                else None
            ),
            "latest_bundle_replay_artifact": (
                external_regime_bundle_replay_artifact_to_dict(self._latest_bundle_replay_artifact)
                if self._latest_bundle_replay_artifact is not None
                else None
            ),
            "scenario_status": self._scenario_status,
            "latest_scenario_result": (
                external_regime_scenario_result_to_dict(self._latest_scenario_result)
                if self._latest_scenario_result is not None
                else None
            ),
            "recent_history": [external_regime_update_record_to_dict(record) for record in self._history],
            "persistence": external_regime_persistence_state_to_dict(self.persistence_state()),
        }

    def _run_scenario_step(
        self,
        step: ExternalRegimeScenarioStep,
        policy: ExternalRegimeSafetyPolicy,
    ) -> ExternalRegimeScenarioStepRecord:
        bundle_result: ExternalRegimeBundleIngestionRecord | None = None
        dimension_results: tuple[ExternalRegimePayloadIngestionRecord, ...] = ()
        operation = "bundle"
        replayed = False
        if step.replay_artifact is not None:
            operation = "bundle_replay"
            replayed = True
            bundle_result = self.replay_bundle_artifact(step.replay_artifact, received_at_ns=step.received_at_ns)
            accepted_count = len(bundle_result.changed_dimensions)
            rejected_count = len(bundle_result.failed_dimensions)
            changed_dimensions = bundle_result.changed_dimensions
            failed_dimensions = bundle_result.failed_dimensions
            accepted = bundle_result.accepted
            partially_accepted = bundle_result.partially_accepted
        elif step.bundle_payload is not None:
            bundle_result = self.ingest_bundle_payload(
                dict(step.bundle_payload),
                provider=step.provider,
                input_format=step.input_format,
                apply_mode=step.apply_mode,
                received_at_ns=step.received_at_ns,
            )
            accepted_count = len(bundle_result.changed_dimensions)
            rejected_count = len(bundle_result.failed_dimensions)
            changed_dimensions = bundle_result.changed_dimensions
            failed_dimensions = bundle_result.failed_dimensions
            accepted = bundle_result.accepted
            partially_accepted = bundle_result.partially_accepted
        else:
            operation = "dimension_batch"
            results: list[ExternalRegimePayloadIngestionRecord] = []
            for dimension in ("options", "event", "on_chain"):
                payload = None if step.dimension_payloads is None else step.dimension_payloads.get(dimension)
                if payload is None:
                    continue
                results.append(
                    self.ingest_payload(
                        dimension=dimension,
                        payload=dict(payload),
                        provider=step.provider,
                        input_format=step.input_format,
                        received_at_ns=step.received_at_ns,
                    )
                )
            dimension_results = tuple(results)
            accepted_count = sum(1 for item in dimension_results if item.accepted)
            rejected_count = sum(1 for item in dimension_results if not item.accepted)
            changed_dimensions = tuple(item.dimension for item in dimension_results if item.accepted)
            failed_dimensions = tuple(item.dimension for item in dimension_results if not item.accepted)
            accepted = rejected_count == 0 and accepted_count > 0
            partially_accepted = accepted_count > 0 and rejected_count > 0

        snap = self.snapshot(step.received_at_ns)
        activation = evaluate_external_regime_activation_safety(snap, policy)
        execution = evaluate_external_regime_execution_safety(snap, policy)
        return ExternalRegimeScenarioStepRecord(
            step_id=step.step_id,
            received_at_ns=step.received_at_ns,
            provider=step.provider,
            operation=operation,
            accepted=accepted,
            partially_accepted=partially_accepted,
            replayed=replayed,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            changed_dimensions=changed_dimensions,
            failed_dimensions=failed_dimensions,
            activation_blocked=activation.blocked,
            activation_reason=activation.reason,
            activation_allocation_scale=activation.allocation_scale,
            execution_blocked=execution.blocked,
            execution_reason=execution.reason,
            stale_dimensions=snap.stale_dimensions,
            unavailable_dimensions=snap.unavailable_dimensions,
            high_risk=snap.high_risk_regime_present,
            bundle_result=bundle_result,
            dimension_results=dimension_results,
            snapshot=snap,
        )

    @staticmethod
    def _build_scenario_result(
        scenario_id: str,
        step_records: list[ExternalRegimeScenarioStepRecord],
    ) -> ExternalRegimeScenarioResult:
        step_count = len(step_records)
        accepted_steps = sum(1 for item in step_records if item.accepted)
        partially_accepted_steps = sum(1 for item in step_records if item.partially_accepted)
        rejected_steps = sum(1 for item in step_records if not item.accepted and not item.partially_accepted)
        replayed_steps = sum(1 for item in step_records if item.replayed)
        execution_blocked_steps = sum(1 for item in step_records if item.execution_blocked)
        activation_blocked_steps = sum(1 for item in step_records if item.activation_blocked)
        activation_reduced_steps = sum(
            1 for item in step_records if not item.activation_blocked and item.activation_allocation_scale < 1.0
        )
        stale_steps = sum(1 for item in step_records if item.stale_dimensions)
        unavailable_steps = sum(1 for item in step_records if item.unavailable_dimensions)
        high_risk_steps = sum(1 for item in step_records if item.high_risk)
        safe_steps = sum(
            1
            for item in step_records
            if not item.execution_blocked
            and not item.activation_blocked
            and item.activation_allocation_scale >= 1.0
            and not item.stale_dimensions
            and not item.unavailable_dimensions
            and not item.high_risk
        )
        summary_parts = [f"steps={step_count}"]
        if execution_blocked_steps:
            summary_parts.append(f"execution_blocked={execution_blocked_steps}")
        if activation_blocked_steps:
            summary_parts.append(f"activation_blocked={activation_blocked_steps}")
        if activation_reduced_steps:
            summary_parts.append(f"activation_reduced={activation_reduced_steps}")
        if stale_steps:
            summary_parts.append(f"stale={stale_steps}")
        if unavailable_steps:
            summary_parts.append(f"unavailable={unavailable_steps}")
        if high_risk_steps:
            summary_parts.append(f"high_risk={high_risk_steps}")
        if safe_steps:
            summary_parts.append(f"safe={safe_steps}")
        return ExternalRegimeScenarioResult(
            scenario_id=scenario_id,
            status="completed",
            step_count=step_count,
            accepted_steps=accepted_steps,
            rejected_steps=rejected_steps,
            replayed_steps=replayed_steps,
            partially_accepted_steps=partially_accepted_steps,
            execution_blocked_steps=execution_blocked_steps,
            activation_blocked_steps=activation_blocked_steps,
            activation_reduced_steps=activation_reduced_steps,
            stale_steps=stale_steps,
            unavailable_steps=unavailable_steps,
            high_risk_steps=high_risk_steps,
            safe_steps=safe_steps,
            last_step_ns=(step_records[-1].received_at_ns if step_records else 0),
            summary="; ".join(summary_parts),
            step_records=tuple(step_records),
            final_snapshot=(step_records[-1].snapshot if step_records else None),
        )


def _payload_summary_for_state(
    *,
    dimension: str,
    provider: str,
    input_format: str,
    payload_origin: str | None,
    state: OptionsRegimeState | EventRegimeState | OnChainRegimeState,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "dimension": dimension,
        "provider": provider,
        "input_format": input_format,
        "source": state.source,
        "snapshot_ns": state.snapshot_ns,
        "level": state.level.value,
    }
    symbol = getattr(state, "symbol", None)
    if symbol is not None:
        summary["symbol"] = symbol
    event_label = getattr(state, "event_label", None)
    if event_label is not None:
        summary["event_label"] = event_label
    if payload_origin is not None:
        summary["payload_origin"] = payload_origin
    return summary


def _provider_trust_rank(trust: str | None) -> int:
    if trust == ExternalRegimeProviderTrust.TRUSTED.value:
        return 2
    if trust == ExternalRegimeProviderTrust.PROVISIONAL.value:
        return 1
    return 0
