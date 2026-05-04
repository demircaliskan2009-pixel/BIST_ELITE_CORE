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
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    Stage4ComparisonResult,
    Stage4PaperSummary,
    build_stage4_backtest_baseline,
    compare_stage4,
    stage4_backtest_baseline_to_dict,
    stage4_comparison_result_to_dict,
    stage4_paper_summary_to_dict,
)
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
    "Stage4BacktestBaseline",
    "Stage4ComparisonResult",
    "Stage4PaperSummary",
    "StressScenario",
    "StressScenarioResult",
    "StressTrade",
    "StressValidationResult",
    "ValidationPipelineResult",
    "ValidationPipelineStageStatus",
    "WalkForwardValidationResult",
    "WalkForwardWindow",
    "WalkForwardWindowResult",
    "build_stage4_backtest_baseline",
    "default_stress_scenarios",
    "compare_stage4",
    "stage4_backtest_baseline_to_dict",
    "stage4_comparison_result_to_dict",
    "stage4_paper_summary_to_dict",
    "validate_pipeline",
    "validate_pbo",
    "validate_stress_testing",
    "validate_walk_forward",
]
