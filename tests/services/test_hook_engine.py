from __future__ import annotations

import pytest

from bist_core.hooks.hook_engine import build_hook_context, load_hooks, run_post_hooks, run_pre_hooks
from bist_core.hooks.models import HookContext

KNOWN = ["ASELS", "AKBNK", "GARAN", "THYAO", "TUPRS", "EREGL"]


def test_load_hooks_reads_pre_and_post_rules() -> None:
    hooks = load_hooks()
    assert "pre" in hooks
    assert "post" in hooks
    assert hooks["pre"]
    assert hooks["post"]


def test_run_pre_hooks_rejects_missing_task_type() -> None:
    got = run_pre_hooks(HookContext(task_type=None, selected_prompt="x", context="complete", response_style="dynamic"))
    assert got.status == "rejected"
    assert got.reason == "TASK CLASSIFICATION MISSING"
    assert got.output == "INSUFFICIENT EVIDENCE"


def test_build_hook_context_selects_comparison_prompt() -> None:
    got = build_hook_context("AKBNK ile GARAN karşılaştır", known_symbols=KNOWN)
    assert got.task_type == "ANALYSIS"
    assert got.selected_prompt == ".github/prompts/comparison-fix.prompt.md"
    assert got.context == "complete"


def test_build_hook_context_fails_closed_when_classification_is_unknown() -> None:
    got = build_hook_context("merhaba", known_symbols=KNOWN)
    assert got.task_type is None
    assert got.selected_prompt is None
    assert got.context == "insufficient"


def test_run_post_hooks_rejects_template_response() -> None:
    got = run_post_hooks(
        {
            "body": "Karşılaştırma üretildi.",
            "hook_contract": {
                "sections": {
                    "WHAT WAS ANALYZED": "x",
                    "WHAT WAS FOUND": "y",
                    "WHAT WAS FIXED": "z",
                    "WHY IT WORKS": "a",
                    "RISKS": "b",
                },
                "contains_hallucination": False,
                "missing_data_used": False,
            },
        }
    )
    assert got.status == "rejected"
    assert got.reason == "TEMPLATE RESPONSE FORBIDDEN"


def test_run_post_hooks_rejects_missing_data_flag() -> None:
    got = run_post_hooks(
        {
            "body": "Deterministic response",
            "hook_contract": {
                "sections": {
                    "WHAT WAS ANALYZED": "x",
                    "WHAT WAS FOUND": "y",
                    "WHAT WAS FIXED": "z",
                    "WHY IT WORKS": "a",
                    "RISKS": "b",
                },
                "contains_hallucination": False,
                "missing_data_used": True,
            },
            "missing_data_used": True,
        }
    )
    assert got.status == "rejected"
    assert got.reason == "INVALID DATA USAGE"


def test_run_pre_hooks_fails_closed_on_hook_load_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bist_core.hooks.hook_engine.load_hooks", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    got = run_pre_hooks(
        HookContext(task_type="ANALYSIS", selected_prompt="x", context="complete", response_style="dynamic")
    )
    assert got.status == "rejected"
    assert got.output == "INSUFFICIENT EVIDENCE"


def test_run_post_hooks_normalizes_missing_sections_when_body_exists() -> None:
    got = run_post_hooks(
        {
            "ok": True,
            "route": "scan",
            "status": "ok",
            "body": "1) AKBNK | score=4.40",
        }
    )
    assert got.status == "accepted"


def test_detect_template_response_rejects_low_diversity_via_post_hook() -> None:
    got = run_post_hooks(
        {
            "body": "aynı aynı aynı aynı aynı aynı aynı aynı aynı aynı aynı aynı aynı aynı",
            "hook_contract": {
                "sections": {
                    "WHAT WAS ANALYZED": "x",
                    "WHAT WAS FOUND": "y",
                    "WHAT WAS FIXED": "z",
                    "WHY IT WORKS": "a",
                    "RISKS": "b",
                },
                "contains_hallucination": False,
                "missing_data_used": False,
            },
        }
    )
    assert got.status == "rejected"
    assert got.reason == "TEMPLATE RESPONSE FORBIDDEN"
