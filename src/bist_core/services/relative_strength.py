from __future__ import annotations


def compute_relative_strength(
    symbol_a: str,
    symbol_b: str,
    price_a: float,
    price_b: float,
) -> dict[str, object]:
    ratio = price_a / price_b
    outperformer = symbol_a if ratio > 1 else symbol_b
    return {
        "ratio": ratio,
        "outperformer": outperformer,
    }

