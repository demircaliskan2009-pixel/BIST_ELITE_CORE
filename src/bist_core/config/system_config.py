"""Central system constants — single source for risk and targeting knobs."""

from __future__ import annotations


class SystemConfig:
    def __init__(self) -> None:
        self.max_positions = 5
        self.max_drawdown = 0.10

        self.enable_mean_reversion = True
        self.enable_trend = True

        self.strategy_weights: dict[str, float] = {
            "trend": 0.6,
            "mean_reversion": 0.4,
        }

        self.volatility_target = 0.02
        # Backward compatibility (same value as volatility_target)
        self.vol_target = float(self.volatility_target)


CONFIG = SystemConfig()

__all__ = ["SystemConfig", "CONFIG"]
