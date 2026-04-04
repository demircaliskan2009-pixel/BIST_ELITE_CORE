from __future__ import annotations

from bist_core.services.relative_strength import compute_relative_strength


def test_compute_relative_strength_ratio_greater_than_one() -> None:
    result = compute_relative_strength("AAA", "BBB", 200, 100)
    assert result["ratio"] == 2
    assert result["outperformer"] == "AAA"


def test_compute_relative_strength_ratio_lower_than_one() -> None:
    result = compute_relative_strength("AAA", "BBB", 50, 100)
    assert result["ratio"] == 0.5
    assert result["outperformer"] == "BBB"


def test_compute_relative_strength_ratio_equal_to_one() -> None:
    result = compute_relative_strength("AAA", "BBB", 100, 100)
    assert result["ratio"] == 1
    assert result["outperformer"] == "BBB"

