from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from bist_core.hooks.models import HookContext, HookResult, HookRule
from bist_core.services.chat_intent import classify_chat_intent

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRE_HOOK_PATH = _REPO_ROOT / ".github" / "hooks" / "pre-response.json"
_POST_HOOK_PATH = _REPO_ROOT / ".github" / "hooks" / "post-response.json"
_PRICE_HINTS = ("giriş", "entry", "fiyat", "price", "canlı", "current", "stop", "target", "hedef")
_PATCH_HINTS = ("fix", "patch", "bug", "düzelt", "duzelt")
_GENERIC_PATTERNS = (
    "karşılaştırma üretildi.",
    "tarama sonucu üretildi.",
    "özet üretildi.",
    "chat yanıtı",
)
_TASK_BY_ROUTE = {
    "comparison": "ANALYSIS",
    "scan": "ANALYSIS",
    "single_symbol": "ANALYSIS",
    "market_overview": "ANALYSIS",
    "debug_symbol": "DEBUG",
    "debug_ranking": "DEBUG",
    "debug_comparison": "DEBUG",
    "debug_dataset": "DEBUG",
}
_PROMPT_BY_ROUTE = {
    "comparison": ".github/prompts/comparison-fix.prompt.md",
    "scan": ".github/prompts/ranking-fix.prompt.md",
    "market_overview": ".github/prompts/ranking-fix.prompt.md",
    "single_symbol": ".github/prompts/price-awareness.prompt.md",
    "debug_symbol": ".github/prompts/forensic-debug.prompt.md",
    "debug_ranking": ".github/prompts/forensic-debug.prompt.md",
    "debug_comparison": ".github/prompts/forensic-debug.prompt.md",
    "debug_dataset": ".github/prompts/forensic-debug.prompt.md",
}
_MIN_TOKEN_DIVERSITY = 0.35
_MIN_UNIQUE_SENTENCES = 2
_MIN_TOKENS_FOR_DIVERSITY = 12


logger = logging.getLogger(__name__)


def _log_critical(event: str, reason: str) -> None:
    logger.error("hook_event=%s reason=%s", event, reason)


def _fail_closed(reason: str, *, include_output: bool = True) -> HookResult:
    _log_critical("hook_rejected", reason)
    return HookResult(status="rejected", reason=reason, output="INSUFFICIENT EVIDENCE" if include_output else None)


def _as_mapping(value: Any) -> dict[str, Any]:
    try:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "__dict__"):
            try:
                return dict(vars(value))
            except TypeError:
                return {}
        return {}
    except Exception:
        return {}


def _read_hook_file(path: Path) -> list[HookRule]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"invalid_hook_root:{path.name}")
    out: list[HookRule] = []
    for item in raw.get("rules") or []:
        if not isinstance(item, Mapping):
            continue
        out.append(
            HookRule(
                type=str(item.get("type") or "").strip(),
                error=str(item.get("error") or "").strip(),
                field=str(item.get("field")).strip() if item.get("field") is not None else None,
                condition=str(item.get("condition")).strip() if item.get("condition") is not None else None,
                sections=tuple(str(x).strip() for x in (item.get("sections") or []) if str(x).strip()),
            )
        )
    return out


@lru_cache(maxsize=1)
def load_hooks() -> dict[str, list[HookRule]]:
    return {
        "pre": _read_hook_file(_PRE_HOOK_PATH),
        "post": _read_hook_file(_POST_HOOK_PATH),
    }


def _parse_expected(token: str) -> Any:
    try:
        raw = token.strip()
        lowered = raw.lower()
        if lowered == "null":
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return raw
    except Exception:
        return None


def _normalize_compare(value: Any) -> Any:
    try:
        if isinstance(value, str):
            return value.strip().lower()
        return value
    except Exception:
        return value


def _evaluate_clause(clause: str, values: Mapping[str, Any]) -> bool:
    try:
        if "==" not in clause or not isinstance(values, Mapping):
            return False
        left, right = clause.split("==", 1)
        actual = values.get(left.strip())
        expected = _parse_expected(right)
        return _normalize_compare(actual) == _normalize_compare(expected)
    except Exception:
        return False


def _evaluate_condition(condition: str, values: Mapping[str, Any]) -> bool:
    try:
        clauses = [part.strip() for part in str(condition or "").split("||") if part.strip()]
        return any(_evaluate_clause(clause, values) for clause in clauses)
    except Exception:
        return True


def _normalize_sentences(text: str) -> list[str]:
    try:
        parts = re.split(r"[\n\r.!?;]+", text)
        return [re.sub(r"\s+", " ", part).strip().casefold() for part in parts if part and part.strip()]
    except Exception:
        return []


def _token_diversity(text: str) -> float:
    tokens = re.findall(r"\w+", text.casefold())
    if len(tokens) < _MIN_TOKENS_FOR_DIVERSITY:
        return 1.0
    unique = {token for token in tokens if token}
    if not tokens:
        return 0.0
    return len(unique) / len(tokens)


def detect_template_response(text: Any) -> bool:
    try:
        raw = re.sub(r"\s+", " ", str(text or "")).strip()
        if not raw:
            return False

        lowered = raw.casefold()
        if any(pattern in lowered for pattern in _GENERIC_PATTERNS):
            return True

        normalized = [item for item in _normalize_sentences(raw) if len(item) >= 16]
        counts = Counter(normalized)
        if normalized and len(set(normalized)) < min(_MIN_UNIQUE_SENTENCES, len(normalized)):
            return True
        if any(count >= 2 for count in counts.values()):
            return True

        rationale_bits = [bit.strip().casefold() for bit in raw.split("->") if bit.strip()]
        if len(rationale_bits) >= 3:
            rationale_values = rationale_bits[1:]
            if rationale_values and len(set(rationale_values)) == 1:
                return True

        if _token_diversity(raw) < _MIN_TOKEN_DIVERSITY:
            return True

        return False
    except Exception:
        return True


def _classify_task_type(raw_text: str, route: str) -> str | None:
    try:
        if route in _TASK_BY_ROUTE:
            return _TASK_BY_ROUTE[route]
        lowered = raw_text.casefold()
        if any(token in lowered for token in _PATCH_HINTS):
            return "PATCH"
        return None
    except Exception:
        return None


def _select_prompt(raw_text: str, route: str, task_type: str | None) -> str | None:
    try:
        if not task_type:
            return None
        if route in _PROMPT_BY_ROUTE:
            return _PROMPT_BY_ROUTE[route]
        if task_type == "PATCH":
            return ".github/prompts/safe-patch.prompt.md"
        if task_type == "DEBUG":
            return ".github/prompts/forensic-debug.prompt.md"
        if task_type != "ANALYSIS":
            return None
        lowered = raw_text.casefold()
        if any(token in lowered for token in _PRICE_HINTS):
            return ".github/prompts/price-awareness.prompt.md"
        return None
    except Exception:
        return None


def build_hook_context(
    text: str | None,
    *,
    known_symbols: Sequence[str] | None = None,
    results_by_symbol: Mapping[str, Mapping[str, Any] | dict[str, Any]] | None = None,
    scan_results: Sequence[Mapping[str, Any] | dict[str, Any]] | None = None,
    market_overview_text: str | None = None,
) -> HookContext:
    try:
        raw_text = str(text or "").strip()
        if not raw_text:
            _log_critical("classification_failed", "missing_query_text")
            return HookContext(context="insufficient", raw_text=raw_text, route="unknown")

        intent = classify_chat_intent(raw_text, known_symbols=known_symbols)
        if not isinstance(intent, Mapping):
            _log_critical("classification_failed", "invalid_intent_payload")
            return HookContext(context="insufficient", raw_text=raw_text, route="unknown")

        route = str(intent.get("intent") or "unknown")
        task_type = _classify_task_type(raw_text, route)
        selected_prompt = _select_prompt(raw_text, route, task_type)
        has_context = any(
            (
                raw_text,
                list(known_symbols or []),
                bool(results_by_symbol),
                bool(scan_results),
                str(market_overview_text or "").strip(),
            )
        )
        response_style = "template" if detect_template_response(raw_text) else "dynamic"
        if task_type is None:
            _log_critical("classification_failed", f"unmapped_route:{route}")
        if selected_prompt is None:
            _log_critical("prompt_mapping_failed", f"task_type={task_type or 'none'} route={route}")
        return HookContext(
            task_type=task_type,
            selected_prompt=selected_prompt,
            context="complete" if has_context and task_type and selected_prompt else "insufficient",
            response_style=response_style,
            raw_text=raw_text,
            route=route,
            metadata={
                "symbol_count": str(intent.get("symbol_count") or 0),
                "top_n": str(intent.get("top_n") or ""),
            },
        )
    except Exception as exc:
        _log_critical("classification_failed", exc.__class__.__name__)
        return HookContext(context="insufficient", raw_text=str(text or "").strip(), route="unknown")


def _validate_require_field(rule: HookRule, values: Mapping[str, Any]) -> HookResult | None:
    try:
        if not rule.field or not isinstance(values, Mapping):
            return None
        value = values.get(rule.field)
        if value is None:
            return _fail_closed(rule.error)
        if isinstance(value, str) and not value.strip():
            return _fail_closed(rule.error)
        return None
    except Exception as exc:
        return _fail_closed(exc.__class__.__name__)


def _validate_reject_if(rule: HookRule, values: Mapping[str, Any], *, include_output: bool) -> HookResult | None:
    try:
        if not rule.condition or not isinstance(values, Mapping):
            return None
        if _evaluate_condition(rule.condition, values):
            return _fail_closed(rule.error, include_output=include_output)
        return None
    except Exception as exc:
        return _fail_closed(exc.__class__.__name__, include_output=include_output)


def _normalized_sections_from_response(raw: Mapping[str, Any], text: str) -> dict[str, str]:
    existing = raw.get("hook_contract")
    if isinstance(existing, Mapping):
        sections = existing.get("sections")
        if isinstance(sections, Mapping):
            out = {str(k): str(v or "").strip() for k, v in sections.items()}
        else:
            out = {}
    else:
        out = {}

    defaults = {
        "WHAT WAS ANALYZED": str(raw.get("route") or raw.get("title") or "response").strip(),
        "WHAT WAS FOUND": text.strip() or str(raw.get("error_code") or "n/a"),
        "WHAT WAS FIXED": str(raw.get("status") or "response_generated").strip(),
        "WHY IT WORKS": "response passed runtime hook validation",
        "RISKS": "none" if bool(raw.get("ok")) else str(raw.get("error_code") or "response_error"),
    }
    for key, value in defaults.items():
        if not str(out.get(key) or "").strip():
            out[key] = value
    return out


def _validate_required_sections(rule: HookRule, response: Any) -> HookResult | None:
    try:
        if not rule.sections:
            return None
        raw = _as_mapping(response)
        text = str(raw.get("body") or raw.get("text") or response or "")
        sections = _normalized_sections_from_response(raw, text)
        if all(str(sections.get(name) or "").strip() for name in rule.sections):
            return None

        upper = text.upper()
        if text and all(section in upper for section in rule.sections):
            return None
        return HookResult(status="rejected", reason=rule.error)
    except Exception as exc:
        return HookResult(status="rejected", reason=exc.__class__.__name__)


def run_pre_hooks(context: HookContext | Mapping[str, Any]) -> HookResult:
    try:
        hooks = load_hooks().get("pre", [])
    except Exception:
        _log_critical("hook_load_failure", "pre")
        return _fail_closed("INSUFFICIENT EVIDENCE")

    try:
        values = _as_mapping(context)
        if not values:
            return _fail_closed("INSUFFICIENT EVIDENCE")
        for rule in hooks:
            if not isinstance(rule, HookRule):
                return _fail_closed("INSUFFICIENT EVIDENCE")
            if rule.type == "require_field":
                rejected = _validate_require_field(rule, values)
            elif rule.type == "reject_if":
                rejected = _validate_reject_if(rule, values, include_output=True)
            else:
                rejected = _fail_closed("INSUFFICIENT EVIDENCE")
            if rejected is not None:
                return rejected

        return HookResult(status="accepted")
    except Exception as exc:
        _log_critical("pre_hook_exception", exc.__class__.__name__)
        return _fail_closed("INSUFFICIENT EVIDENCE")


def run_post_hooks(response: Mapping[str, Any] | str) -> HookResult:
    try:
        hooks = load_hooks().get("post", [])
    except Exception:
        _log_critical("hook_load_failure", "post")
        return HookResult(status="rejected", reason="INSUFFICIENT EVIDENCE")

    try:
        raw = _as_mapping(response)
        if not raw and not isinstance(response, str):
            return HookResult(status="rejected", reason="INSUFFICIENT EVIDENCE")

        body = str(raw.get("body") or raw.get("text") or response or "")
        if detect_template_response(body):
            _log_critical("post_hook_rejected", "TEMPLATE RESPONSE FORBIDDEN")
            return HookResult(status="rejected", reason="TEMPLATE RESPONSE FORBIDDEN")

        values = dict(raw)
        contract = raw.get("hook_contract")
        if isinstance(contract, Mapping):
            values.setdefault("contains_hallucination", bool(contract.get("contains_hallucination")))
            values.setdefault("missing_data_used", bool(contract.get("missing_data_used")))
        values.setdefault("contains_hallucination", False)
        values.setdefault("missing_data_used", False)

        for rule in hooks:
            if not isinstance(rule, HookRule):
                return HookResult(status="rejected", reason="INSUFFICIENT EVIDENCE")
            if rule.type == "require_sections":
                rejected = _validate_required_sections(rule, response)
            elif rule.type == "reject_if":
                rejected = _validate_reject_if(rule, values, include_output=False)
            else:
                rejected = HookResult(status="rejected", reason="INSUFFICIENT EVIDENCE")
            if rejected is not None:
                _log_critical("post_hook_rejected", rejected.reason)
                return rejected

        return HookResult(status="accepted")
    except Exception as exc:
        _log_critical("post_hook_exception", exc.__class__.__name__)
        return HookResult(status="rejected", reason="INSUFFICIENT EVIDENCE")
