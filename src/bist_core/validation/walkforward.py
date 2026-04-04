"""Walk-forward train / holdout split for out-of-sample validation (deterministic)."""

from __future__ import annotations

from typing import Sequence, Tuple, TypeVar

T = TypeVar("T")


def walkforward_split(
    data: Sequence[T],
    train_size: float = 0.7,
) -> Tuple[Sequence[T], Sequence[T]]:
    """Split ordered data into train (in-sample) and test (out-of-sample) segments.

    No shuffle — preserves time order; last segment is OOS.
    """
    n = len(data)
    split = int(n * train_size)
    return data[:split], data[split:]


__all__ = ["walkforward_split"]
