"""LLM-ready explanation hook — deterministic string output only (no API calls)."""

from __future__ import annotations

from typing import Any


class ExplanationEngine:
    def build_prompt(self, decision: dict[str, Any]) -> str:
        return (
            f"Symbol: {decision.get('symbol')}\n"
            f"Action: {decision.get('action')}\n"
            f"Score: {decision.get('score')}\n"
            f"Regime: {decision.get('regime')}\n"
            f"Strategy: {decision.get('strategy')}\n"
        )

    def explain(self, decision: dict[str, Any]) -> str:
        return self.build_prompt(decision)


__all__ = ["ExplanationEngine"]
