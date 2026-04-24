"""Advisory generator, plan, and explain (deterministic advice_records.jsonl, advisory_plan.json, explain.json)."""

from __future__ import annotations

from bist_core.advisory.explain import EXPLAIN_SCHEMA_VERSION, build_explain, write_explain
from bist_core.advisory.generate import generate_advice
from bist_core.advisory.plan import ADVISORY_PLAN_SCHEMA_VERSION, build_advisory_plan, write_advisory_plan

__all__ = [
    "generate_advice",
    "ADVISORY_PLAN_SCHEMA_VERSION",
    "build_advisory_plan",
    "write_advisory_plan",
    "EXPLAIN_SCHEMA_VERSION",
    "build_explain",
    "write_explain",
]
