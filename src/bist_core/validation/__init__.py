"""Validation output parsing — stress run metrics, edge classification (deterministic)."""

from bist_core.validation.output_analyzer import (
    compute_derived,
    detect_failures,
    parse_validation_file,
    run_analysis,
)

__all__ = [
    "compute_derived",
    "detect_failures",
    "parse_validation_file",
    "run_analysis",
]

# auto_optimizer: python -m bist_core.validation.auto_optimizer
