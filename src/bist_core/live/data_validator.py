"""Cross-check iDeal vs Matriks prices (fail-closed on mismatch when both present)."""

from __future__ import annotations


class DataValidator:
    def __init__(self, threshold: float = 0.02) -> None:
        self.threshold = float(threshold)

    def _relative_diff(self, a: float, b: float) -> float:
        base = max(abs(float(a)), abs(float(b)), 1e-6)
        return abs(float(a) - float(b)) / base

    def validate(self, ideal_price: float, matriks_price: float | None) -> bool:
        if ideal_price <= 0:
            return False

        if matriks_price is None:
            return True

        if matriks_price <= 0:
            return False

        return self._relative_diff(ideal_price, matriks_price) < self.threshold

    def validate_strict(
        self, ideal_price: float | None, matriks_price: float | None
    ) -> bool:
        """
        Strict iDeal vs Matriks check for live decisions (deterministic, no exceptions).

        - Invalid/missing iDeal price → False (fail-closed; no decision on bad ideal).
        - Matriks missing or non-positive → True (Matriks not used for cross-check).
        - Both positive: relative diff must be ≤ 2% (strict threshold).
        """
        try:
            if ideal_price is None:
                return False
            ip = float(ideal_price)
        except (TypeError, ValueError):
            return False
        if ip <= 0 or not (ip == ip):  # NaN
            return False

        try:
            if matriks_price is None:
                return True
            mp = float(matriks_price)
        except (TypeError, ValueError):
            return True
        if mp <= 0 or not (mp == mp):
            return True

        diff = abs(ip - mp) / max(ip, 1e-6)
        if diff > 0.02:
            return False
        return True

    def compare_ohlc_to_ref(self, o: float, h: float, l: float, c: float, ref: float) -> bool:
        """Ideal OHLC vs Matriks reference quote — all legs within relative threshold."""
        if ref <= 0:
            return False
        for px in (o, h, l, c):
            if not isinstance(px, (int, float)) or float(px) <= 0:
                return False
            if self._relative_diff(float(px), float(ref)) >= self.threshold:
                return False
        return True


__all__ = ["DataValidator"]
