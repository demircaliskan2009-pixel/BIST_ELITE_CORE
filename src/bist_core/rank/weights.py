"""Weight normalization — deterministic sum-to-one."""

from __future__ import annotations


class InvalidWeightsError(Exception):
    """Raised when weights are invalid or empty."""

    pass


def normalize_weights(weights: dict) -> dict:
    """Normalize weights so sum equals 1.

    If sum != 1, scale deterministically.
    Empty weights → raise InvalidWeightsError.
    """
    if not weights:
        raise InvalidWeightsError("weights cannot be empty")
    total = sum(float(v) for v in weights.values())
    if total == 0:
        raise InvalidWeightsError("weights sum cannot be zero")
    return {k: float(v) / total for k, v in sorted(weights.items())}


__all__ = ["InvalidWeightsError", "normalize_weights"]
