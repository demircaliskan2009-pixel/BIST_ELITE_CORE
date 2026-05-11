"""Deterministic validation pipeline sequencing foundation."""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.validation.pbo import PBOValidationResult
from crypto_core.validation.stress_testing import StressValidationResult
from crypto_core.validation.walk_forward import WalkForwardValidationResult

_STAGE2 = "stage2_walk_forward"
_PBO = "pbo"
_STAGE3 = "stage3_stress"


@dataclass(frozen=True)
class ValidationPipelineStageStatus:
    stage: str
    ran: bool
    passed: bool
    skipped: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ValidationPipelineResult:
    validation_ready: bool
    stage2_status: ValidationPipelineStageStatus
    pbo_status: ValidationPipelineStageStatus
    stage3_status: ValidationPipelineStageStatus
    pbo_allocation_cap: float | None
    rejection_reasons: tuple[str, ...]
    missing_stages: tuple[str, ...]


def _stage_status(
    stage: str,
    *,
    ran: bool,
    passed: bool,
    skipped: bool,
    rejection_reasons: tuple[str, ...] = (),
) -> ValidationPipelineStageStatus:
    return ValidationPipelineStageStatus(
        stage=stage,
        ran=ran,
        passed=passed,
        skipped=skipped,
        rejection_reasons=rejection_reasons,
    )


def _missing_status(stage: str, reason: str) -> ValidationPipelineStageStatus:
    return _stage_status(stage, ran=False, passed=False, skipped=False, rejection_reasons=(reason,))


def _skipped_status(stage: str) -> ValidationPipelineStageStatus:
    return _stage_status(stage, ran=False, passed=False, skipped=True)


def _prefixed_reasons(prefix: str, reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{prefix}:{reason}" for reason in reasons)


def _build_result(
    stage2_status: ValidationPipelineStageStatus,
    pbo_status: ValidationPipelineStageStatus,
    stage3_status: ValidationPipelineStageStatus,
    *,
    pbo_allocation_cap: float | None = None,
) -> ValidationPipelineResult:
    rejection_reasons = (
        *stage2_status.rejection_reasons,
        *pbo_status.rejection_reasons,
        *stage3_status.rejection_reasons,
    )
    missing_stages = tuple(status.stage for status in (stage2_status, pbo_status, stage3_status) if not status.ran)
    return ValidationPipelineResult(
        validation_ready=stage2_status.passed and pbo_status.passed and stage3_status.passed,
        stage2_status=stage2_status,
        pbo_status=pbo_status,
        stage3_status=stage3_status,
        pbo_allocation_cap=pbo_allocation_cap,
        rejection_reasons=rejection_reasons,
        missing_stages=missing_stages,
    )


def validate_pipeline(
    walk_forward_result: WalkForwardValidationResult | None,
    pbo_result: PBOValidationResult | None,
    stress_result: StressValidationResult | None,
) -> ValidationPipelineResult:
    if walk_forward_result is None:
        return _build_result(
            _missing_status(_STAGE2, "stage2:stage2_missing"),
            _skipped_status(_PBO),
            _skipped_status(_STAGE3),
        )
    if not isinstance(walk_forward_result, WalkForwardValidationResult):
        return _build_result(
            _missing_status(_STAGE2, "stage2:stage2_malformed"),
            _skipped_status(_PBO),
            _skipped_status(_STAGE3),
        )

    stage2_status = _stage_status(
        _STAGE2,
        ran=True,
        passed=walk_forward_result.supportive,
        skipped=False,
        rejection_reasons=(
            () if walk_forward_result.supportive else _prefixed_reasons("stage2", walk_forward_result.rejection_reasons)
        ),
    )
    if not stage2_status.passed:
        return _build_result(stage2_status, _skipped_status(_PBO), _skipped_status(_STAGE3))

    if pbo_result is None:
        return _build_result(
            stage2_status,
            _missing_status(_PBO, "pbo:pbo_missing"),
            _skipped_status(_STAGE3),
        )
    if not isinstance(pbo_result, PBOValidationResult):
        return _build_result(
            stage2_status,
            _missing_status(_PBO, "pbo:pbo_malformed"),
            _skipped_status(_STAGE3),
        )

    pbo_status = _stage_status(
        _PBO,
        ran=True,
        passed=pbo_result.approved,
        skipped=False,
        rejection_reasons=() if pbo_result.approved else _prefixed_reasons("pbo", pbo_result.rejection_reasons),
    )
    if not pbo_status.passed:
        return _build_result(
            stage2_status,
            pbo_status,
            _skipped_status(_STAGE3),
            pbo_allocation_cap=pbo_result.allocation_cap,
        )

    if stress_result is None:
        return _build_result(
            stage2_status,
            pbo_status,
            _missing_status(_STAGE3, "stage3:stage3_missing"),
            pbo_allocation_cap=pbo_result.allocation_cap,
        )
    if not isinstance(stress_result, StressValidationResult):
        return _build_result(
            stage2_status,
            pbo_status,
            _missing_status(_STAGE3, "stage3:stage3_malformed"),
            pbo_allocation_cap=pbo_result.allocation_cap,
        )

    stage3_status = _stage_status(
        _STAGE3,
        ran=True,
        passed=stress_result.all_passed,
        skipped=False,
        rejection_reasons=(
            () if stress_result.all_passed else _prefixed_reasons("stage3", stress_result.rejection_reasons)
        ),
    )
    return _build_result(
        stage2_status,
        pbo_status,
        stage3_status,
        pbo_allocation_cap=pbo_result.allocation_cap,
    )
