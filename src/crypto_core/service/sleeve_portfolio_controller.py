"""Sleeve portfolio workflow controller — Phase 14B.

Deterministic crypto-only workflow controller for sleeve enable/disable/block
operations with governance-aware effective state projection.

Provides:
  1. SleevePortfolioWorkflowStatus — controller lifecycle state.
  2. SleeveOperatorOverride — explicit operator override for one sleeve.
  3. SleevePortfolioHistoryEntry — bounded compact change history entry.
  4. SleevePortfolioWorkflowCorruptError — fail-closed restore error.
  5. SleevePortfolioController — first-class sleeve workflow manager.

Design rules:
  - Reuses CryptoSleeveState / SleevePortfolioSnapshot as the contract surface.
  - Operator overrides are explicit and bounded; no hidden automation.
  - Governance uses existing readiness / escalation / external regime truth only.
  - Fail-closed: malformed persisted workflow state raises.
  - PAPER-ONLY.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from crypto_core.service.artifact_export import EscalationStage
from crypto_core.service.campaign import CampaignReport
from crypto_core.service.evidence_store import EvidenceStore, WriteResult
from crypto_core.service.readiness import ReadinessLevel, level_at_least
from crypto_core.service.sleeve_portfolio import (
    CryptoSleeveState,
    CryptoSleeveStatus,
    SleeveAllocationPolicy,
    SleevePortfolioCorruptError,
    SleevePortfolioSnapshot,
    SleeveReason,
    SleeveReasonSource,
    build_sleeve_portfolio_snapshot,
    build_sleeve_with_stage4_artifacts,
    crypto_sleeve_state_from_dict,
    crypto_sleeve_state_to_dict,
    sleeve_allocation_policy_from_dict,
    sleeve_allocation_policy_to_dict,
    sleeve_portfolio_snapshot_from_dict,
    sleeve_portfolio_snapshot_to_dict,
)
from crypto_core.validation.stage4_comparator import Stage4BacktestBaseline, Stage4PaperSummary
from crypto_core.validation.walk_forward import WalkForwardWindow

if TYPE_CHECKING:
    from crypto_core.service.paper_shadow_session_controller import (
        PaperPnLLedger,
        PaperShadowSessionSnapshot,
    )

_DEFAULT_HISTORY_LIMIT = 5
_WORKFLOW_SNAPSHOT_NAME = "sleeve_portfolio_workflow"
_WORKFLOW_REQUIRED_FIELDS = frozenset(
    {"status", "created_at_ns", "updated_at_ns", "defined_sleeves", "operator_overrides"}
)


class SleevePortfolioWorkflowStatus(str, Enum):
    """Deterministic sleeve workflow controller states."""

    CREATED = "created"
    ACTIVE = "active"


class SleeveOperatorMode(str, Enum):
    """Explicit operator override modes."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    BLOCKED = "blocked"


_STAGE_RANK = {
    EscalationStage.HOLD.value: 0,
    EscalationStage.INCONCLUSIVE.value: 1,
    EscalationStage.REJECT.value: 2,
    EscalationStage.PAPER_ONLY.value: 3,
    EscalationStage.CALIBRATED_PAPER.value: 4,
    EscalationStage.SHADOW_LIVE_REVIEW_ELIGIBLE.value: 5,
    EscalationStage.TINY_CAP_LIVE_REVIEW_ELIGIBLE.value: 6,
}


class SleevePortfolioWorkflowCorruptError(RuntimeError):
    """Raised when persisted sleeve workflow state is malformed."""


@dataclass(frozen=True)
class SleeveOperatorOverride:
    """Explicit operator override for one sleeve."""

    sleeve_id: str
    mode: SleeveOperatorMode
    reason_summary: str
    required_change: str
    updated_at_ns: int


@dataclass(frozen=True)
class SleevePortfolioHistoryEntry:
    """Compact bounded history entry for changed sleeve workflow state."""

    as_of_ns: int
    summary: str
    changed_sleeves: tuple[str, ...]
    enabled_sleeve_ids: tuple[str, ...]
    blocked_sleeve_ids: tuple[str, ...]
    disabled_sleeve_ids: tuple[str, ...]


class SleevePortfolioController:
    """First-class crypto sleeve workflow manager."""

    def __init__(
        self,
        *,
        defined_sleeves: tuple[CryptoSleeveState, ...] = (),
        evidence_store: EvidenceStore | None = None,
        created_at_ns: int | None = None,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
        operator_overrides: tuple[SleeveOperatorOverride, ...] = (),
        history: tuple[SleevePortfolioHistoryEntry, ...] = (),
        current_snapshot: SleevePortfolioSnapshot | None = None,
        allocation_policy: SleeveAllocationPolicy | None = None,
    ) -> None:
        now = created_at_ns if created_at_ns is not None else time.time_ns()
        self._created_at_ns = now
        self._updated_at_ns = now
        self._status = SleevePortfolioWorkflowStatus.CREATED
        self._history_limit = max(1, history_limit)
        self._evidence_store = evidence_store
        self._defined_sleeves = self._validated_sleeves(defined_sleeves)
        self._allocation_policy = SleeveAllocationPolicy() if allocation_policy is None else allocation_policy
        self._operator_overrides = self._validated_overrides(operator_overrides, self._defined_sleeves)
        self._history = self._bounded_history(history)
        self._current_snapshot = current_snapshot

    @property
    def status(self) -> SleevePortfolioWorkflowStatus:
        return self._status

    @property
    def defined_sleeves(self) -> tuple[CryptoSleeveState, ...]:
        return self._defined_sleeves

    @property
    def history(self) -> tuple[SleevePortfolioHistoryEntry, ...]:
        return self._history

    @property
    def allocation_policy(self) -> SleeveAllocationPolicy:
        return self._allocation_policy

    def configure_sleeves(self, sleeves: tuple[CryptoSleeveState, ...]) -> tuple[CryptoSleeveState, ...]:
        """Replace the configured sleeve definitions while preserving valid overrides."""
        self._defined_sleeves = self._validated_sleeves(sleeves)
        self._operator_overrides = self._validated_overrides(
            tuple(self._operator_overrides.values()), self._defined_sleeves
        )
        self._updated_at_ns = time.time_ns()
        self._persist_workflow()
        return self._defined_sleeves

    def configure_allocation_policy(self, policy: SleeveAllocationPolicy) -> SleeveAllocationPolicy:
        """Replace the explicit effective-allocation recompute policy."""
        self._allocation_policy = policy
        self._updated_at_ns = time.time_ns()
        self._persist_workflow()
        return self._allocation_policy

    def apply_stage4_artifacts(
        self,
        sleeve_id: str,
        *,
        windows: tuple[WalkForwardWindow, ...] | None = None,
        baseline: Stage4BacktestBaseline | None = None,
        paper_summary: Stage4PaperSummary | None = None,
        paper_ledger: PaperPnLLedger | None = None,
        paper_snapshot: PaperShadowSessionSnapshot | None = None,
        baseline_id: str | None = None,
        edge_id: str | None = None,
        as_of_ns: int | None = None,
        paper_id: str | None = None,
        min_duration_days: float = 30.0,
        min_sharpe_retention_ratio: float = 0.5,
    ) -> SleevePortfolioSnapshot:
        """Apply finalized Stage4 artifacts to one configured sleeve."""

        self._require_known_sleeve(sleeve_id)
        if windows is not None and (not baseline_id or not edge_id or as_of_ns is None):
            raise ValueError("stage4 windows require baseline_id, edge_id, and as_of_ns")
        if paper_summary is None and paper_ledger is not None and paper_snapshot is not None and not edge_id:
            raise ValueError("stage4 paper ledger/snapshot require edge_id")

        snapshot_as_of_ns = self._stage4_artifact_as_of_ns(as_of_ns)
        updated_sleeves = tuple(
            build_sleeve_with_stage4_artifacts(
                sleeve,
                windows=windows,
                baseline=baseline,
                ledger=paper_ledger,
                snapshot=paper_snapshot,
                paper_summary=paper_summary,
                baseline_id=baseline_id or "",
                edge_id=edge_id or "",
                as_of_ns=snapshot_as_of_ns,
                paper_id=paper_id,
                min_duration_days=min_duration_days,
                min_sharpe_retention_ratio=min_sharpe_retention_ratio,
            )
            if sleeve.sleeve_id == sleeve_id
            else sleeve
            for sleeve in self._defined_sleeves
        )
        self._defined_sleeves = self._validated_sleeves(updated_sleeves)
        previous = self._current_snapshot
        return self.current_snapshot(
            as_of_ns=snapshot_as_of_ns,
            readiness_level=None if previous is None else previous.readiness_level,
            readiness_is_supportive=False if previous is None else previous.readiness_is_supportive,
            escalation_allowed_next_step=None if previous is None else previous.escalation_allowed_next_step,
            external_regime_execution_blocked=(
                None if previous is None else previous.external_regime_execution_blocked
            ),
        )

    def enable_sleeve(self, sleeve_id: str, *, updated_at_ns: int | None = None) -> SleeveOperatorOverride:
        """Explicitly enable or unblock a sleeve at the operator layer."""
        return self._set_override(
            sleeve_id,
            SleeveOperatorMode.ENABLED,
            reason_summary="Explicitly enabled by operator.",
            required_change="",
            updated_at_ns=updated_at_ns,
        )

    def disable_sleeve(
        self,
        sleeve_id: str,
        *,
        reason_summary: str = "Explicitly disabled by operator.",
        required_change: str = "Use enable_sleeve after operator review.",
        updated_at_ns: int | None = None,
    ) -> SleeveOperatorOverride:
        """Explicitly disable a sleeve at the operator layer."""
        return self._set_override(
            sleeve_id,
            SleeveOperatorMode.DISABLED,
            reason_summary=reason_summary,
            required_change=required_change,
            updated_at_ns=updated_at_ns,
        )

    def block_sleeve(
        self,
        sleeve_id: str,
        *,
        reason_summary: str,
        required_change: str = "Clear the operator block before enabling.",
        updated_at_ns: int | None = None,
    ) -> SleeveOperatorOverride:
        """Explicitly block a sleeve at the operator layer."""
        if not reason_summary:
            raise ValueError("reason_summary must be non-empty for operator block")
        return self._set_override(
            sleeve_id,
            SleeveOperatorMode.BLOCKED,
            reason_summary=reason_summary,
            required_change=required_change,
            updated_at_ns=updated_at_ns,
        )

    def unblock_sleeve(self, sleeve_id: str, *, updated_at_ns: int | None = None) -> SleeveOperatorOverride:
        """Explicitly remove operator/configuration block pressure for a sleeve."""
        return self.enable_sleeve(sleeve_id, updated_at_ns=updated_at_ns)

    def current_snapshot(
        self,
        *,
        as_of_ns: int,
        campaign_report: CampaignReport | None = None,
        readiness_level: str | None,
        readiness_is_supportive: bool,
        escalation_allowed_next_step: str | None,
        external_regime_execution_blocked: bool | None,
    ) -> SleevePortfolioSnapshot:
        """Compute the effective sleeve portfolio snapshot and update bounded history."""
        workflow_status = SleevePortfolioWorkflowStatus.ACTIVE.value
        effective_sleeves = tuple(
            self._resolve_effective_sleeve(
                sleeve,
                readiness_level=readiness_level,
                readiness_is_supportive=readiness_is_supportive,
                escalation_allowed_next_step=escalation_allowed_next_step,
                external_regime_execution_blocked=external_regime_execution_blocked,
            )
            for sleeve in self._defined_sleeves
        )
        draft_snapshot = build_sleeve_portfolio_snapshot(
            sleeves=effective_sleeves,
            as_of_ns=as_of_ns,
            campaign_report=campaign_report,
            readiness_level=readiness_level,
            readiness_is_supportive=readiness_is_supportive,
            escalation_allowed_next_step=escalation_allowed_next_step,
            external_regime_execution_blocked=external_regime_execution_blocked,
            allocation_policy=self._allocation_policy,
            workflow_status=workflow_status,
        )
        comparison = self.compare_to_previous(draft_snapshot)
        history_summary = self.history_summary(draft_snapshot, comparison)
        snapshot = build_sleeve_portfolio_snapshot(
            sleeves=draft_snapshot.sleeves,
            as_of_ns=draft_snapshot.as_of_ns,
            campaign_report=campaign_report,
            readiness_level=draft_snapshot.readiness_level,
            readiness_is_supportive=draft_snapshot.readiness_is_supportive,
            escalation_allowed_next_step=draft_snapshot.escalation_allowed_next_step,
            external_regime_execution_blocked=draft_snapshot.external_regime_execution_blocked,
            allocation_policy=draft_snapshot.allocation_policy,
            workflow_status=workflow_status,
            comparison_to_previous=comparison,
            history_summary=history_summary,
        )
        self._update_current_snapshot(snapshot)
        return snapshot

    def compare_to_previous(self, snapshot: SleevePortfolioSnapshot) -> dict:
        """Compare a candidate snapshot with the previously materialized snapshot."""
        previous = self._current_snapshot
        if previous is None:
            return {
                "available": False,
                "changed": False,
                "previous_as_of_ns": None,
                "current_as_of_ns": snapshot.as_of_ns,
                "changed_sleeves": [],
            }

        prev_by_id = {item.sleeve_id: item for item in previous.sleeves}
        curr_by_id = {item.sleeve_id: item for item in snapshot.sleeves}
        changed_sleeves: list[dict] = []
        for sleeve_id in tuple(sorted(set(prev_by_id) | set(curr_by_id))):
            prev_state = prev_by_id.get(sleeve_id)
            curr_state = curr_by_id.get(sleeve_id)
            if self._state_signature(prev_state) == self._state_signature(curr_state):
                continue
            changed_sleeves.append(
                {
                    "sleeve_id": sleeve_id,
                    "previous_status": None if prev_state is None else prev_state.status.value,
                    "current_status": None if curr_state is None else curr_state.status.value,
                    "previous_reason_summary": None if prev_state is None else prev_state.reason_summary,
                    "current_reason_summary": None if curr_state is None else curr_state.reason_summary,
                    "previous_required_changes": ([] if prev_state is None else list(prev_state.required_changes)),
                    "current_required_changes": ([] if curr_state is None else list(curr_state.required_changes)),
                }
            )
        return {
            "available": True,
            "changed": bool(changed_sleeves),
            "previous_as_of_ns": previous.as_of_ns,
            "current_as_of_ns": snapshot.as_of_ns,
            "changed_sleeves": changed_sleeves,
        }

    def history_summary(
        self,
        snapshot: SleevePortfolioSnapshot,
        comparison: dict | None = None,
    ) -> dict:
        """Compact operator-facing summary of bounded workflow history."""
        comparison = comparison if comparison is not None else self.compare_to_previous(snapshot)
        latest = self._history[-1] if self._history else None
        changed_sleeves = comparison.get("changed_sleeves", []) if isinstance(comparison, dict) else []
        return {
            "total_recorded_changes": len(self._history),
            "latest_change_as_of_ns": None if latest is None else latest.as_of_ns,
            "latest_summary": None if latest is None else latest.summary,
            "current_enabled_sleeve_ids": list(snapshot.enabled_sleeve_ids),
            "current_blocked_sleeve_ids": list(snapshot.blocked_sleeve_ids),
            "current_disabled_sleeve_ids": [
                sleeve.sleeve_id for sleeve in snapshot.sleeves if sleeve.status == CryptoSleeveStatus.DISABLED
            ],
            "last_changed_sleeves": [item.get("sleeve_id") for item in changed_sleeves],
        }

    def save_state(self) -> WriteResult | None:
        """Persist the workflow state via EvidenceStore."""
        if self._evidence_store is None:
            return None
        return self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, self._workflow_state_to_dict())

    @classmethod
    def restore(
        cls,
        evidence_store: EvidenceStore,
        *,
        history_limit: int = _DEFAULT_HISTORY_LIMIT,
    ) -> SleevePortfolioController:
        """Restore controller state from persisted workflow snapshot."""
        envelope = evidence_store.load_snapshot(_WORKFLOW_SNAPSHOT_NAME)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise SleevePortfolioWorkflowCorruptError(
                f"Sleeve workflow 'data' must be a dict, got {type(data).__name__!r}"
            )
        missing = _WORKFLOW_REQUIRED_FIELDS - set(data)
        if missing:
            raise SleevePortfolioWorkflowCorruptError(f"Sleeve workflow missing required fields: {sorted(missing)!r}")

        status_str = data["status"]
        try:
            status = SleevePortfolioWorkflowStatus(status_str)
        except ValueError:
            raise SleevePortfolioWorkflowCorruptError(f"Invalid sleeve workflow status {status_str!r}") from None

        controller = cls(
            defined_sleeves=_tuple_of_sleeves(data.get("defined_sleeves", ())),
            evidence_store=evidence_store,
            created_at_ns=_require_non_negative_int(data["created_at_ns"], "created_at_ns"),
            history_limit=history_limit,
            operator_overrides=_tuple_of_overrides(data.get("operator_overrides", ())),
            history=_tuple_of_history(data.get("history", ()), history_limit=history_limit),
            current_snapshot=(
                None
                if data.get("current_snapshot") is None
                else sleeve_portfolio_snapshot_from_dict(dict(data.get("current_snapshot")))
            ),
            allocation_policy=(
                SleeveAllocationPolicy()
                if data.get("allocation_policy") is None
                else sleeve_allocation_policy_from_dict(dict(data.get("allocation_policy")))
            ),
        )
        controller._status = status
        controller._updated_at_ns = _require_non_negative_int(data["updated_at_ns"], "updated_at_ns")
        return controller

    def _set_override(
        self,
        sleeve_id: str,
        mode: SleeveOperatorMode,
        *,
        reason_summary: str,
        required_change: str,
        updated_at_ns: int | None,
    ) -> SleeveOperatorOverride:
        self._require_known_sleeve(sleeve_id)
        override = SleeveOperatorOverride(
            sleeve_id=sleeve_id,
            mode=mode,
            reason_summary=reason_summary,
            required_change=required_change,
            updated_at_ns=time.time_ns() if updated_at_ns is None else updated_at_ns,
        )
        self._operator_overrides = dict(self._operator_overrides)
        self._operator_overrides[sleeve_id] = override
        self._updated_at_ns = override.updated_at_ns
        self._persist_workflow()
        return override

    def _resolve_effective_sleeve(
        self,
        sleeve: CryptoSleeveState,
        *,
        readiness_level: str | None,
        readiness_is_supportive: bool,
        escalation_allowed_next_step: str | None,
        external_regime_execution_blocked: bool | None,
    ) -> CryptoSleeveState:
        operator_override = self._operator_overrides.get(sleeve.sleeve_id)
        reasons = list(self._configuration_reasons(sleeve))
        reasons.extend(
            self._governance_reasons(
                sleeve,
                readiness_level=readiness_level,
                readiness_is_supportive=readiness_is_supportive,
                escalation_allowed_next_step=escalation_allowed_next_step,
                external_regime_execution_blocked=external_regime_execution_blocked,
            )
        )
        if operator_override is not None:
            reasons.append(
                SleeveReason(
                    source=SleeveReasonSource.OPERATOR,
                    code=f"operator_{operator_override.mode.value}",
                    summary=operator_override.reason_summary,
                    required_change=operator_override.required_change,
                )
            )

        desired_status = self._desired_status(sleeve, operator_override)
        governance_blocked = any(
            item.source in {SleeveReasonSource.GOVERNANCE, SleeveReasonSource.EVIDENCE} for item in reasons
        )
        if desired_status == CryptoSleeveStatus.DISABLED:
            effective_status = CryptoSleeveStatus.DISABLED
        elif desired_status == CryptoSleeveStatus.BLOCKED or governance_blocked:
            effective_status = CryptoSleeveStatus.BLOCKED
        else:
            effective_status = desired_status

        target = sleeve.target_allocation
        active = target if effective_status == CryptoSleeveStatus.ALLOCATED else 0.0
        blocked = target if effective_status == CryptoSleeveStatus.BLOCKED else 0.0
        disabled = target if effective_status == CryptoSleeveStatus.DISABLED else 0.0
        blocked_reasons = tuple(item.summary for item in reasons if effective_status == CryptoSleeveStatus.BLOCKED)
        required_changes = tuple(dict.fromkeys(item.required_change for item in reasons if item.required_change))
        reason_summary = "; ".join(dict.fromkeys(item.summary for item in reasons if item.summary))
        return CryptoSleeveState(
            sleeve_id=sleeve.sleeve_id,
            sleeve_type=sleeve.sleeve_type,
            status=effective_status,
            target_allocation=target,
            active_allocation=active,
            blocked_allocation=blocked,
            disabled_allocation=disabled,
            blocked_reasons=blocked_reasons,
            reason_summary=reason_summary,
            readiness_level=sleeve.readiness_level,
            escalation_stage=sleeve.escalation_stage,
            reasons=tuple(reasons),
            required_changes=required_changes,
            validation_pipeline_result=sleeve.validation_pipeline_result,
            stage4_comparison_result=sleeve.stage4_comparison_result,
            stage4_comparison_required=sleeve.stage4_comparison_required,
            stage4_backtest_baseline=sleeve.stage4_backtest_baseline,
        )

    def _configuration_reasons(self, sleeve: CryptoSleeveState) -> tuple[SleeveReason, ...]:
        if sleeve.status == CryptoSleeveStatus.BLOCKED:
            summary = sleeve.reason_summary or ", ".join(sleeve.blocked_reasons) or "Blocked by configuration."
            return (
                SleeveReason(
                    source=SleeveReasonSource.CONFIGURATION,
                    code="configured_blocked",
                    summary=summary,
                    required_change="Use enable_sleeve or unblock_sleeve after review.",
                ),
            )
        if sleeve.status == CryptoSleeveStatus.DISABLED:
            return (
                SleeveReason(
                    source=SleeveReasonSource.CONFIGURATION,
                    code="configured_disabled",
                    summary=sleeve.reason_summary or "Disabled by configuration.",
                    required_change="Use enable_sleeve after review.",
                ),
            )
        return tuple(sleeve.reasons)

    def _governance_reasons(
        self,
        sleeve: CryptoSleeveState,
        *,
        readiness_level: str | None,
        readiness_is_supportive: bool,
        escalation_allowed_next_step: str | None,
        external_regime_execution_blocked: bool | None,
    ) -> tuple[SleeveReason, ...]:
        reasons: list[SleeveReason] = []
        readiness_name = readiness_level or ReadinessLevel.NOT_ASSESSED.value
        required_readiness_name = sleeve.readiness_level or ReadinessLevel.PAPER_LIVE.value
        current_readiness = _parse_readiness_level(readiness_name)
        required_readiness = _parse_readiness_level(required_readiness_name)
        if current_readiness == ReadinessLevel.NOT_ASSESSED:
            reasons.append(
                SleeveReason(
                    source=SleeveReasonSource.EVIDENCE,
                    code="readiness_not_assessed",
                    summary="Readiness has not been assessed for sleeve activation.",
                    required_change=f"Assess readiness to at least {required_readiness.value}.",
                )
            )
        elif not readiness_is_supportive or not level_at_least(current_readiness, required_readiness):
            reasons.append(
                SleeveReason(
                    source=SleeveReasonSource.GOVERNANCE,
                    code="readiness_not_supportive",
                    summary=(f"Readiness {current_readiness.value} is below required {required_readiness.value}."),
                    required_change=f"Raise readiness to at least {required_readiness.value}.",
                )
            )

        if sleeve.escalation_stage:
            current_rank = _STAGE_RANK.get(escalation_allowed_next_step or "", -1)
            required_rank = _STAGE_RANK.get(sleeve.escalation_stage, -1)
            paper_only_rank = _STAGE_RANK[EscalationStage.PAPER_ONLY.value]
            if escalation_allowed_next_step is None and required_rank > paper_only_rank:
                reasons.append(
                    SleeveReason(
                        source=SleeveReasonSource.EVIDENCE,
                        code="escalation_unavailable",
                        summary="Escalation stage is unavailable for sleeve activation.",
                        required_change=f"Produce escalation evidence for {sleeve.escalation_stage} or better.",
                    )
                )
            elif escalation_allowed_next_step is not None and required_rank >= 0 and current_rank < required_rank:
                reasons.append(
                    SleeveReason(
                        source=SleeveReasonSource.GOVERNANCE,
                        code="escalation_too_weak",
                        summary=(
                            f"Escalation stage {escalation_allowed_next_step} is below required {sleeve.escalation_stage}."
                        ),
                        required_change=f"Advance escalation to at least {sleeve.escalation_stage}.",
                    )
                )

        if external_regime_execution_blocked is True:
            reasons.append(
                SleeveReason(
                    source=SleeveReasonSource.GOVERNANCE,
                    code="external_regime_execution_blocked",
                    summary="External regime safety currently blocks sleeve execution.",
                    required_change="Wait until external regime execution block clears.",
                )
            )
        return tuple(reasons)

    def _desired_status(
        self,
        sleeve: CryptoSleeveState,
        override: SleeveOperatorOverride | None,
    ) -> CryptoSleeveStatus:
        if override is None:
            return sleeve.status
        if override.mode == SleeveOperatorMode.DISABLED:
            return CryptoSleeveStatus.DISABLED
        if override.mode == SleeveOperatorMode.BLOCKED:
            return CryptoSleeveStatus.BLOCKED
        if sleeve.target_allocation > 0.0:
            return CryptoSleeveStatus.ALLOCATED
        return CryptoSleeveStatus.ENABLED

    def _update_current_snapshot(self, snapshot: SleevePortfolioSnapshot) -> None:
        comparison = self.compare_to_previous(snapshot)
        if self._current_snapshot is not None and not comparison.get("changed", False):
            self._current_snapshot = snapshot
            self._status = SleevePortfolioWorkflowStatus.ACTIVE
            self._updated_at_ns = snapshot.as_of_ns
            self._persist_workflow()
            return

        self._current_snapshot = snapshot
        self._status = SleevePortfolioWorkflowStatus.ACTIVE
        self._updated_at_ns = snapshot.as_of_ns
        changed_sleeves = tuple(item.get("sleeve_id") for item in comparison.get("changed_sleeves", []))
        if changed_sleeves:
            history_entry = SleevePortfolioHistoryEntry(
                as_of_ns=snapshot.as_of_ns,
                summary=snapshot.summary,
                changed_sleeves=changed_sleeves,
                enabled_sleeve_ids=snapshot.enabled_sleeve_ids,
                blocked_sleeve_ids=snapshot.blocked_sleeve_ids,
                disabled_sleeve_ids=tuple(
                    sleeve.sleeve_id for sleeve in snapshot.sleeves if sleeve.status == CryptoSleeveStatus.DISABLED
                ),
            )
            self._history = self._bounded_history(self._history + (history_entry,))
        self._persist_workflow()

    def _persist_workflow(self) -> None:
        if self._evidence_store is not None:
            self._evidence_store.save_snapshot(_WORKFLOW_SNAPSHOT_NAME, self._workflow_state_to_dict())

    def _workflow_state_to_dict(self) -> dict:
        return {
            "status": self._status.value,
            "created_at_ns": self._created_at_ns,
            "updated_at_ns": self._updated_at_ns,
            "defined_sleeves": [crypto_sleeve_state_to_dict(item) for item in self._defined_sleeves],
            "allocation_policy": sleeve_allocation_policy_to_dict(self._allocation_policy),
            "operator_overrides": [
                sleeve_operator_override_to_dict(item) for item in self._operator_overrides.values()
            ],
            "history": [sleeve_portfolio_history_entry_to_dict(item) for item in self._history],
            "current_snapshot": (
                None if self._current_snapshot is None else sleeve_portfolio_snapshot_to_dict(self._current_snapshot)
            ),
            "history_limit": self._history_limit,
        }

    def _stage4_artifact_as_of_ns(self, as_of_ns: int | None) -> int:
        if as_of_ns is not None:
            return _require_non_negative_int(as_of_ns, "as_of_ns")
        if self._current_snapshot is not None:
            return self._current_snapshot.as_of_ns
        return 0

    def _require_known_sleeve(self, sleeve_id: str) -> None:
        if sleeve_id not in {item.sleeve_id for item in self._defined_sleeves}:
            raise KeyError(f"Unknown sleeve_id {sleeve_id!r}")

    def _validated_sleeves(self, sleeves: tuple[CryptoSleeveState, ...]) -> tuple[CryptoSleeveState, ...]:
        validated = build_sleeve_portfolio_snapshot(sleeves=sleeves, as_of_ns=0)
        return validated.sleeves

    def _validated_overrides(
        self,
        overrides: tuple[SleeveOperatorOverride, ...],
        sleeves: tuple[CryptoSleeveState, ...],
    ) -> dict[str, SleeveOperatorOverride]:
        known = {item.sleeve_id for item in sleeves}
        result: dict[str, SleeveOperatorOverride] = {}
        for override in overrides:
            if override.sleeve_id not in known:
                raise SleevePortfolioWorkflowCorruptError(
                    f"Override references unknown sleeve_id {override.sleeve_id!r}"
                )
            result[override.sleeve_id] = override
        return result

    def _bounded_history(
        self,
        history: tuple[SleevePortfolioHistoryEntry, ...],
    ) -> tuple[SleevePortfolioHistoryEntry, ...]:
        if len(history) <= self._history_limit:
            return history
        return history[-self._history_limit :]

    @staticmethod
    def _state_signature(state: CryptoSleeveState | None) -> tuple | None:
        if state is None:
            return None
        return (
            state.sleeve_id,
            state.status.value,
            state.target_allocation,
            state.active_allocation,
            state.blocked_allocation,
            state.disabled_allocation,
            state.reason_summary,
            tuple(state.required_changes),
            state.qualification.status.value,
            tuple(state.qualification.missing_evidence),
            tuple(state.qualification.blocking_reasons),
            state.recommendation.status.value,
            tuple(state.recommendation.missing_evidence),
            tuple(state.recommendation.blocking_reasons),
            state.recommendation.effective_allocation,
            state.campaign_evidence.status.value,
            state.campaign_evidence.campaign_evidence_available,
            state.campaign_evidence.explicit_link_available,
            state.campaign_evidence.linked_in_campaign,
            tuple(state.campaign_evidence.supporting_campaign_ids),
            tuple(state.campaign_evidence.missing_evidence),
            tuple(state.campaign_evidence.blocking_reasons),
            state.promotion_support.status.value,
            state.promotion_support.can_be_considered_later,
            tuple(state.promotion_support.missing_evidence),
            tuple(state.promotion_support.blocking_reasons),
            state.promotion_candidate.status.value,
            state.promotion_candidate.candidate_for_future_review,
            state.promotion_candidate.strongly_supported,
            tuple(state.promotion_candidate.missing_evidence),
            tuple(state.promotion_candidate.blocking_reasons),
            state.decision_pack.status.value,
            state.decision_pack.promotion_candidate,
            state.decision_pack.strongly_supported_candidate,
            tuple(state.decision_pack.missing_evidence),
            tuple(state.decision_pack.blocking_reasons),
        )


def sleeve_operator_override_to_dict(override: SleeveOperatorOverride) -> dict:
    return {
        "sleeve_id": override.sleeve_id,
        "mode": override.mode.value,
        "reason_summary": override.reason_summary,
        "required_change": override.required_change,
        "updated_at_ns": override.updated_at_ns,
    }


def sleeve_operator_override_from_dict(data: dict) -> SleeveOperatorOverride:
    if not isinstance(data, dict):
        raise SleevePortfolioWorkflowCorruptError(
            f"Sleeve operator override must be a dict, got {type(data).__name__!r}"
        )
    return SleeveOperatorOverride(
        sleeve_id=_require_non_empty_string(data.get("sleeve_id"), "sleeve_id"),
        mode=SleeveOperatorMode(_require_non_empty_string(data.get("mode"), "mode")),
        reason_summary="" if data.get("reason_summary", "") is None else str(data.get("reason_summary", "")),
        required_change="" if data.get("required_change", "") is None else str(data.get("required_change", "")),
        updated_at_ns=_require_non_negative_int(data.get("updated_at_ns"), "updated_at_ns"),
    )


def sleeve_portfolio_history_entry_to_dict(entry: SleevePortfolioHistoryEntry) -> dict:
    return {
        "as_of_ns": entry.as_of_ns,
        "summary": entry.summary,
        "changed_sleeves": list(entry.changed_sleeves),
        "enabled_sleeve_ids": list(entry.enabled_sleeve_ids),
        "blocked_sleeve_ids": list(entry.blocked_sleeve_ids),
        "disabled_sleeve_ids": list(entry.disabled_sleeve_ids),
    }


def sleeve_portfolio_history_entry_from_dict(data: dict) -> SleevePortfolioHistoryEntry:
    if not isinstance(data, dict):
        raise SleevePortfolioWorkflowCorruptError(f"Sleeve history entry must be a dict, got {type(data).__name__!r}")
    return SleevePortfolioHistoryEntry(
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        summary="" if data.get("summary", "") is None else str(data.get("summary", "")),
        changed_sleeves=_tuple_of_strings(data.get("changed_sleeves", ()), "changed_sleeves"),
        enabled_sleeve_ids=_tuple_of_strings(data.get("enabled_sleeve_ids", ()), "enabled_sleeve_ids"),
        blocked_sleeve_ids=_tuple_of_strings(data.get("blocked_sleeve_ids", ()), "blocked_sleeve_ids"),
        disabled_sleeve_ids=_tuple_of_strings(data.get("disabled_sleeve_ids", ()), "disabled_sleeve_ids"),
    )


def _tuple_of_sleeves(value: object) -> tuple[CryptoSleeveState, ...]:
    if not isinstance(value, (list, tuple)):
        raise SleevePortfolioWorkflowCorruptError("defined_sleeves must be a list/tuple")
    try:
        return tuple(
            item if isinstance(item, CryptoSleeveState) else crypto_sleeve_state_from_dict(dict(item)) for item in value
        )
    except SleevePortfolioCorruptError as exc:
        raise SleevePortfolioWorkflowCorruptError(str(exc)) from exc


def _tuple_of_overrides(value: object) -> tuple[SleeveOperatorOverride, ...]:
    if not isinstance(value, (list, tuple)):
        raise SleevePortfolioWorkflowCorruptError("operator_overrides must be a list/tuple")
    return tuple(
        item if isinstance(item, SleeveOperatorOverride) else sleeve_operator_override_from_dict(dict(item))
        for item in value
    )


def _tuple_of_history(
    value: object,
    *,
    history_limit: int,
) -> tuple[SleevePortfolioHistoryEntry, ...]:
    if not isinstance(value, (list, tuple)):
        raise SleevePortfolioWorkflowCorruptError("history must be a list/tuple")
    history = tuple(
        item if isinstance(item, SleevePortfolioHistoryEntry) else sleeve_portfolio_history_entry_from_dict(dict(item))
        for item in value
    )
    if len(history) <= history_limit:
        return history
    return history[-history_limit:]


def _tuple_of_strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise SleevePortfolioWorkflowCorruptError(f"{field_name!r} must be a list/tuple of str")
    return tuple(value)


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SleevePortfolioWorkflowCorruptError(f"{field_name!r} must be a non-empty str")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise SleevePortfolioWorkflowCorruptError(f"{field_name!r} must be a non-negative int")
    return value


def _parse_readiness_level(value: str) -> ReadinessLevel:
    try:
        return ReadinessLevel(value)
    except ValueError:
        return ReadinessLevel.NOT_ASSESSED
