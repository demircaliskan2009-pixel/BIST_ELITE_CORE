"""DataValidator — dual-source price check."""

from __future__ import annotations

from bist_core.live.data_validator import DataValidator


def test_ideal_only_matriks_none_accepts() -> None:
    v = DataValidator()
    assert v.validate(100.0, None) is True


def test_ideal_and_matriks_close() -> None:
    v = DataValidator(threshold=0.02)
    assert v.validate(100.0, 101.0) is True


def test_ideal_corrupt_matriks_not_used_in_validate() -> None:
    v = DataValidator()
    assert v.validate(-1.0, 100.0) is False


def test_both_invalid_ideal_zero() -> None:
    v = DataValidator()
    assert v.validate(0.0, 100.0) is False


def test_mismatch_over_threshold() -> None:
    v = DataValidator(threshold=0.02)
    assert v.validate(100.0, 110.0) is False


def test_small_prices_symmetric_denominator() -> None:
    """Uses max(ideal, matriks, 1e-6) as base — avoids inflated diff on tiny prices."""
    v = DataValidator(threshold=0.05)
    assert v.validate(2.5, 2.52) is True


def test_validate_strict_ideal_invalid() -> None:
    v = DataValidator()
    assert v.validate_strict(None, 100.0) is False
    assert v.validate_strict(0.0, 100.0) is False


def test_validate_strict_matriks_missing_allows() -> None:
    v = DataValidator()
    assert v.validate_strict(100.0, None) is True
    assert v.validate_strict(100.0, 0.0) is True


def test_validate_strict_within_2pct() -> None:
    v = DataValidator()
    assert v.validate_strict(100.0, 101.0) is True
    assert v.validate_strict(100.0, 102.0) is True


def test_validate_strict_over_2pct() -> None:
    v = DataValidator()
    assert v.validate_strict(100.0, 110.0) is False
