"""Tests for the deterministic, paper-only paper trade tick / trade-intent contract."""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal
from crypto_core.validation.paper_trade_tick import (
    PaperTradeIntent,
    PaperTradeIntentAction,
    PaperTradeIntentType,
    PaperTradeTickError,
    PaperTradeTickStatus,
    build_paper_trade_intent,
    build_paper_trade_tick,
    paper_trade_intent_digest,
    paper_trade_intent_to_dict,
    paper_trade_tick_digest,
    paper_trade_tick_to_dict,
)

_VALID_DIGEST = "f" * 64
_MODULE_PATH = Path(__file__).resolve().parents[3] / "src" / "crypto_core" / "validation" / "paper_trade_tick.py"


def _kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tick_id": "tick-1",
        "action": "BUY",
        "intent_type": "LIMIT",
        "instrument_id": "BTC-USD",
        "quantity": "1.5",
        "strategy_id": "momentum-1",
        "run_plan_id": "run-1",
        "upstream_report_digest": _VALID_DIGEST,
        "correlation_id": "corr-1",
        "limit_price": "20000.5",
    }
    base.update(overrides)
    return base


def _intent_kwargs(**overrides: object) -> dict[str, object]:
    base = _kwargs()
    base.pop("tick_id")
    base.update(overrides)
    return base


def _is_hex64(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


# 1. valid BUY paper trade tick builds ACCEPTED and digest is 64-hex.
def test_buy_tick_accepted_with_hex_digest() -> None:
    tick = build_paper_trade_tick(**_kwargs())
    assert tick.status is PaperTradeTickStatus.ACCEPTED
    assert tick.accepted is True
    assert tick.rejection_reasons == ()
    assert _is_hex64(tick.paper_trade_tick_digest)
    assert tick.paper_only is True
    assert tick.real_orders_enabled is False
    assert tick.real_money_enabled is False


# 2. valid SELL paper trade tick builds ACCEPTED and the digest is deterministic across builds.
def test_sell_tick_digest_is_deterministic() -> None:
    first = build_paper_trade_tick(**_kwargs(action="SELL"))
    second = build_paper_trade_tick(**_kwargs(action="SELL"))
    assert first.status is PaperTradeTickStatus.ACCEPTED
    assert first.paper_trade_tick_digest == second.paper_trade_tick_digest
    assert paper_trade_tick_digest(first) == first.paper_trade_tick_digest


# 3. HOLD requires zero quantity and builds ACCEPTED when safe (no executable price).
def test_hold_zero_quantity_accepted() -> None:
    tick = build_paper_trade_tick(**_kwargs(action="HOLD", quantity="0", limit_price=None))
    assert tick.status is PaperTradeTickStatus.ACCEPTED
    assert tick.accepted is True


# 4. BUY/SELL/REDUCE/FLATTEN reject zero or negative quantity.
@pytest.mark.parametrize("action", ["BUY", "SELL", "REDUCE", "FLATTEN"])
@pytest.mark.parametrize("quantity", ["0", "-1", "-0.5"])
def test_executable_actions_reject_non_positive_quantity(action: str, quantity: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(action=action, quantity=quantity))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert tick.accepted is False
    assert "paper_trade_tick:quantity_not_positive" in tick.rejection_reasons


# 5. limit price must be positive for priced intents.
@pytest.mark.parametrize("limit_price", ["0", "-1", "-0.01"])
def test_non_positive_limit_price_rejected(limit_price: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(limit_price=limit_price))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:limit_price_not_positive" in tick.rejection_reasons


def test_priced_executable_intent_requires_limit_price() -> None:
    tick = build_paper_trade_tick(**_kwargs(limit_price=None))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:limit_price_required" in tick.rejection_reasons


# 6. malformed quantity/price, NaN, inf, float-drift inputs fail closed (no float path).
@pytest.mark.parametrize("quantity", ["NaN", "inf", "Infinity", "1e5", "1.", ".5", "00", "1_000", " 1 ", "abc", ""])
def test_malformed_quantity_strings_rejected(quantity: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(quantity=quantity))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:quantity_not_decimal_string" in tick.rejection_reasons


def test_float_quantity_is_rejected_not_coerced() -> None:
    tick = build_paper_trade_tick(**_kwargs(quantity=1.5))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:quantity_not_decimal_string" in tick.rejection_reasons
    assert tick.quantity == ""


@pytest.mark.parametrize("limit_price", ["NaN", "inf", "1e5", "1.", "abc"])
def test_malformed_limit_price_strings_rejected(limit_price: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(limit_price=limit_price))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:limit_price_not_decimal_string" in tick.rejection_reasons


# 7. missing/empty ids reject (or raise) per contract.
def test_empty_correlation_id_raises() -> None:
    with pytest.raises(PaperTradeTickError):
        build_paper_trade_tick(**_kwargs(correlation_id="   "))


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("tick_id", "paper_trade_tick:tick_id_invalid"),
        ("instrument_id", "paper_trade_tick:instrument_id_invalid"),
        ("strategy_id", "paper_trade_tick:strategy_id_invalid"),
        ("run_plan_id", "paper_trade_tick:run_plan_id_invalid"),
    ],
)
def test_empty_identity_fields_rejected(field: str, reason: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(**{field: ""}))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert reason in tick.rejection_reasons


def test_missing_upstream_digest_is_insufficient_evidence() -> None:
    tick = build_paper_trade_tick(**_kwargs(upstream_report_digest=""))
    assert tick.status is PaperTradeTickStatus.INSUFFICIENT_EVIDENCE
    assert tick.accepted is False
    assert "paper_trade_tick:upstream_report_digest_missing" in tick.rejection_reasons


def test_malformed_upstream_digest_rejected() -> None:
    tick = build_paper_trade_tick(**_kwargs(upstream_report_digest="not-a-digest"))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:upstream_report_digest_invalid" in tick.rejection_reasons


# 8. paper_only=False / real_orders_enabled=True / real_money_enabled=True fail closed.
@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        ({"paper_only": False}, "paper_trade_tick:tick_not_paper_only"),
        ({"real_orders_enabled": True}, "paper_trade_tick:tick_real_orders_enabled"),
        ({"real_money_enabled": True}, "paper_trade_tick:tick_real_money_enabled"),
    ],
)
def test_paper_safety_triple_enforced(flags: dict[str, bool], reason: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(**flags))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert reason in tick.rejection_reasons
    # Stored attestation always remains the safe constant.
    assert tick.paper_only is True
    assert tick.real_orders_enabled is False
    assert tick.real_money_enabled is False


# 9. live/private/order-routing/scheduler/connector/shadow/BIST tokens fail closed.
@pytest.mark.parametrize(
    "token",
    [
        "live",
        "live_order",
        "private_api",
        "order_router",
        "place_order",
        "scheduler",
        "connector_ready",
        "shadow",
        "bist",
        "borsa",
        "matriks",
        "kap",
        "orders",
    ],
)
def test_forbidden_tokens_in_metadata_rejected(token: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(metadata={"note": token}))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert any(
        reason in {"paper_trade_tick:forbidden_scope_token", "paper_trade_tick:bist_scope_leakage"}
        for reason in tick.rejection_reasons
    )


def test_forbidden_token_in_strategy_id_rejected() -> None:
    tick = build_paper_trade_tick(**_kwargs(strategy_id="order_router_v2"))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:forbidden_scope_token" in tick.rejection_reasons


# 10. order_book/order_flow remain allowed as market-data metadata.
@pytest.mark.parametrize("term", ["order_book", "order_flow", "limit_order_book"])
def test_market_data_order_terms_allowed(term: str) -> None:
    tick = build_paper_trade_tick(**_kwargs(metadata={"market_data_source": term}))
    assert tick.status is PaperTradeTickStatus.ACCEPTED
    assert tick.accepted is True


# 11. serializer excludes the self-digest from the digest basis and is stable.
def test_serializer_excludes_self_digest_from_basis() -> None:
    tick = build_paper_trade_tick(**_kwargs())
    payload = paper_trade_tick_to_dict(tick)
    assert payload["paper_trade_tick_digest"] == tick.paper_trade_tick_digest
    assert paper_trade_tick_digest(tick) == tick.paper_trade_tick_digest
    # Recompute is over the basis without the self-digest field; tampering the stored field cannot change it.
    tampered = dataclasses.replace(tick, paper_trade_tick_digest="0" * 64)
    assert paper_trade_tick_digest(tampered) == tick.paper_trade_tick_digest


# 12. changing any material field changes the digest.
@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": "2.5"},
        {"limit_price": "20001"},
        {"action": "SELL"},
        {"intent_type": "PASSIVE_LIMIT"},
        {"instrument_id": "ETH-USD"},
        {"tick_id": "tick-2"},
        {"run_plan_id": "run-2"},
        {"strategy_id": "momentum-2"},
        {"correlation_id": "corr-2"},
        {"metadata": {"k": "v"}},
    ],
)
def test_material_field_change_changes_digest(overrides: dict[str, object]) -> None:
    base = build_paper_trade_tick(**_kwargs())
    changed = build_paper_trade_tick(**_kwargs(**overrides))
    assert base.paper_trade_tick_digest != changed.paper_trade_tick_digest


# 13. wrong enum/string values fail closed.
def test_unknown_action_rejected() -> None:
    tick = build_paper_trade_tick(**_kwargs(action="MARKET"))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:action_unknown" in tick.rejection_reasons


def test_unknown_intent_type_rejected() -> None:
    tick = build_paper_trade_tick(**_kwargs(intent_type="ICEBERG"))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert "paper_trade_tick:intent_type_unknown" in tick.rejection_reasons


# 14. rejection reasons are deterministic and sorted-unique.
def test_rejection_reasons_sorted_unique() -> None:
    tick = build_paper_trade_tick(**_kwargs(action="MARKET", quantity="-1", tick_id="", limit_price="0"))
    assert tick.status is PaperTradeTickStatus.REJECTED
    assert tick.rejection_reasons == tuple(sorted(set(tick.rejection_reasons)))
    assert "paper_trade_tick:tick_id_invalid" in tick.rejection_reasons
    assert "paper_trade_tick:action_unknown" in tick.rejection_reasons


# 15. dataclasses are frozen/immutable.
def test_tick_is_frozen() -> None:
    tick = build_paper_trade_tick(**_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        tick.accepted = False  # type: ignore[misc]


def test_intent_is_frozen() -> None:
    intent = build_paper_trade_intent(**_intent_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        intent.quantity = "9"  # type: ignore[misc]


# 16. module purity: no IO/clock/random/threading/network/service/connector/runtime imports.
def test_module_imports_are_pure() -> None:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            imported_roots.add(node.module.split(".")[0])
    forbidden = {
        "os",
        "sys",
        "io",
        "pathlib",
        "time",
        "datetime",
        "random",
        "secrets",
        "uuid",
        "threading",
        "asyncio",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
        "sqlite3",
    }
    assert imported_roots.isdisjoint(forbidden)
    assert imported_roots == {"__future__", "hashlib", "json", "re", "collections", "dataclasses", "decimal", "enum"}


# 17. no implementation surface for live/order-routing/scheduler/connector/BIST in the public API.
def test_public_api_has_no_execution_surface() -> None:
    import crypto_core.validation.paper_trade_tick as module

    banned_substrings = (
        "execute",
        "route",
        "router",
        "send",
        "submit",
        "schedule",
        "connector",
        "place_order",
        "live",
        "fill",
        "pnl",
        "bist",
    )
    for name in module.__all__:
        lowered = name.lower()
        assert all(banned not in lowered for banned in banned_substrings), name


# 18. no fill/PnL/execution fields are present on the contract.
def test_no_execution_fields_in_serialized_tick() -> None:
    tick = build_paper_trade_tick(**_kwargs())
    keys = set(paper_trade_tick_to_dict(tick).keys())
    banned = {
        "fill",
        "filled",
        "fills",
        "fill_price",
        "avg_fill_price",
        "executed",
        "execution",
        "pnl",
        "realized_pnl",
        "position",
        "order_id",
        "venue",
    }
    assert keys.isdisjoint(banned)


# 19. schema_version tamper is detectable via digest recompute.
def test_schema_version_tamper_breaks_digest() -> None:
    tick = build_paper_trade_tick(**_kwargs())
    tampered = dataclasses.replace(tick, schema_version="paper-trade-tick.v2")
    assert paper_trade_tick_digest(tampered) != tampered.paper_trade_tick_digest


# 20. an ACCEPTED tick dict is compatible with the EvidenceJournal token guard.
def test_accepted_tick_dict_appends_to_evidence_journal() -> None:
    tick = build_paper_trade_tick(**_kwargs(metadata={"market_data_source": "order_book"}))
    assert tick.status is PaperTradeTickStatus.ACCEPTED
    journal = EvidenceJournal()
    entry = journal.append(
        EvidenceArtifactType.PAPER_REPLAY_RESULT_REPORT,
        paper_trade_tick_to_dict(tick),
        correlation_id=tick.correlation_id,
    )
    assert journal.entry_count == 1
    assert entry.payload["paper_trade_tick_digest"] == tick.paper_trade_tick_digest


# Standalone intent contract: strict builder + deterministic digest.
def test_build_intent_digest_is_hex_and_reproves() -> None:
    intent = build_paper_trade_intent(**_intent_kwargs())
    assert isinstance(intent, PaperTradeIntent)
    assert _is_hex64(intent.intent_digest)
    assert paper_trade_intent_digest(intent) == intent.intent_digest
    payload = paper_trade_intent_to_dict(intent)
    assert payload["intent_digest"] == intent.intent_digest
    assert payload["paper_only"] is True
    assert payload["real_orders_enabled"] is False
    assert payload["real_money_enabled"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": "MARKET"},
        {"intent_type": "ICEBERG"},
        {"instrument_id": ""},
        {"quantity": 1.5},
        {"upstream_report_digest": "bad"},
        {"paper_only": False},
        {"real_orders_enabled": True},
        {"real_money_enabled": True},
        {"strategy_id": "order_router"},
    ],
)
def test_build_intent_raises_on_malformed_call(overrides: dict[str, object]) -> None:
    with pytest.raises(PaperTradeTickError):
        build_paper_trade_intent(**_intent_kwargs(**overrides))


def test_intent_action_and_type_enums_round_trip() -> None:
    assert PaperTradeIntentAction("FLATTEN") is PaperTradeIntentAction.FLATTEN
    assert PaperTradeIntentType("CANCEL_INTENT") is PaperTradeIntentType.CANCEL_INTENT
    assert {a.value for a in PaperTradeIntentAction} == {"BUY", "SELL", "HOLD", "REDUCE", "FLATTEN"}
