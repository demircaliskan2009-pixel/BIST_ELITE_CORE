"""Validation foundations for deterministic pre-promotion checks."""

from crypto_core.validation.pbo import (
    CSCVMatrix,
    DSRInputs,
    MCPermutationInputs,
    PBOSplit,
    PBOValidationResult,
    RegimePBOResult,
    SensitivityInputs,
    validate_pbo,
)
from crypto_core.validation.pipeline import ValidationPipelineResult, ValidationPipelineStageStatus, validate_pipeline
from crypto_core.validation.stress_testing import (
    RegimeGateEvidence,
    StressScenario,
    StressScenarioResult,
    StressTrade,
    StressValidationResult,
    default_stress_scenarios,
    validate_stress_testing,
)
from crypto_core.validation.walk_forward import (
    WalkForwardValidationResult,
    WalkForwardWindow,
    WalkForwardWindowResult,
    validate_walk_forward,
)

__all__ = [
    "CSCVMatrix",
    "DSRInputs",
    "MCPermutationInputs",
    "PBOSplit",
    "PBOValidationResult",
    "RegimeGateEvidence",
    "RegimePBOResult",
    "SensitivityInputs",
    "StressScenario",
    "StressScenarioResult",
    "StressTrade",
    "StressValidationResult",
    "ValidationPipelineResult",
    "ValidationPipelineStageStatus",
    "WalkForwardValidationResult",
    "WalkForwardWindow",
    "WalkForwardWindowResult",
    "default_stress_scenarios",
    "validate_pipeline",
    "validate_pbo",
    "validate_stress_testing",
    "validate_walk_forward",
]
