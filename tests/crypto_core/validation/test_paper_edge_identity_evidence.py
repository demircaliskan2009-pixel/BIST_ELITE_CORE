"""Tests for deterministic paper edge-identity evidence."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.strategy.spec import (
    StrategySpec,
    strategy_spec_digest,
    validate_strategy_spec,
)
from crypto_core.validation import paper_edge_identity_evidence as edge_module
from crypto_core.validation.paper_edge_identity_evidence import (
    PaperEdgeIdentityEvidenceError,
    PaperEdgeIdentityEvidenceStatus,
    build_paper_edge_identity_evidence,
    paper_edge_identity_evidence_digest,
    paper_edge_identity_evidence_to_dict,
)
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
)
from crypto_core.validation.strategy_signal_to_paper_intent import (
    build_strategy_signal_to_paper_intent,
)

_HEX_A = "a" * 64
_MARKET = "BTC-PERPETUAL"


class _LiarStr(str):
    """A string subclass rejected by exact string checks."""


class _SneakyStr(str):
    """A ``str`` subclass that lies about being non-empty — must never produce a divergent READY identity."""

    def strip(self, *args, **kwargs):  # noqa: D401 - adversarial override
        return "definitely-not-empty"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _spec(**overrides: object) -> StrategySpec:
    payload: dict[str, object] = {
        "schema_version": "strategy-spec.v1",
        "strategy_id": "alpha-funding-carry",
        "strategy_version": "1.0.0",
        "strategy_family": "carry",
        "edge_family": "funding_basis_carry",
        "instrument_universe": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
        "market_type": "usdt_perp",
        "venue_assumptions": ["perp_linear"],
        "timeframe": "1h",
        "bar_definition": "time_1h",
        "entry_conditions": ["funding_positive"],
        "exit_conditions": ["funding_neutral"],
        "invalidation_conditions": ["regime_break"],
        "risk_caps": {"max_leverage": 2.0},
        "data_requirements": {"funding_rate": "1h"},
        "feature_requirements": {"funding_zscore": "rolling"},
        "latency_sensitivity": "low",
        "funding_sensitivity": "high",
        "fee_model_requirement": "taker_10bps",
        "slippage_model_requirement": "depth_aware",
        "expected_regime": "ranging",
        "failure_modes": ["funding_flip"],
        "kill_switch_triggers": ["max_dd"],
        "telemetry_fields": ["funding"],
        "promotion_requirements": ["walk_forward"],
    }
    payload.update(overrides)
    result = validate_strategy_spec(payload)
    assert result.accepted, result.rejection_reasons + result.needs_research_reasons
    assert result.spec is not None
    return result.spec


def _bridge(spec: StrategySpec | None = None, **overrides: object):
    spec = spec if spec is not None else _spec()
    kwargs: dict[str, object] = {
        "expected_spec_digest": strategy_spec_digest(spec),
        "signal_id": "sig-1",
        "run_id": "run-1",
        "correlation_id": "corr-1",
        "market_symbol": _MARKET,
        "side": PaperOrderSide.BUY,
        "intent_type": PaperOrderIntentType.MARKET,
        "requested_units": "10",
        "requested_notional": "100",
        "capacity_decision_digest": _HEX_A,
        "limit_price": None,
    }
    kwargs.update(overrides)
    return build_strategy_signal_to_paper_intent(spec, **kwargs)  # type: ignore[arg-type]


def _build(spec: StrategySpec | None = None, **overrides: object):
    spec = spec if spec is not None else _spec()
    payload: dict[str, object] = {
        "expected_strategy_spec_digest": strategy_spec_digest(spec),
        "market_symbol": _MARKET,
        "edge_identity_id": "edge-identity-1",
        "paper_id": "paper-1",
        "correlation_id": "corr-1",
        "metadata": {"purpose": "paper edge identity"},
    }
    payload.update(overrides)
    return build_paper_edge_identity_evidence(spec, **payload)  # type: ignore[arg-type]


def _expected_edge_id(strategy_id: str, market_symbol: str) -> str:
    canonical = json.dumps(
        {"strategy_id": strategy_id, "market_symbol": market_symbol},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- 1. Public API / duplicate ------------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(edge_module.__all__) == {
        "PaperEdgeIdentityEvidence",
        "PaperEdgeIdentityEvidenceError",
        "PaperEdgeIdentityEvidenceStatus",
        "build_paper_edge_identity_evidence",
        "paper_edge_identity_evidence_digest",
        "paper_edge_identity_evidence_to_dict",
    }


def test_no_equivalent_artifact_exists() -> None:
    validation_dir = Path(edge_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "build_paper_edge_identity_evidence" in path.read_text(encoding="utf-8")
    )
    assert builders == ["paper_edge_identity_evidence.py"]


def test_output_is_frozen() -> None:
    result = _build()
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


# --- 2. Happy READY (spec-only) -----------------------------------------------------------------------------


def test_happy_path_spec_only() -> None:
    result = _build()
    payload = paper_edge_identity_evidence_to_dict(result)

    assert result.status is PaperEdgeIdentityEvidenceStatus.READY
    assert result.ready is True
    assert result.edge_identity_resolved is True
    assert result.strategy_spec_identity_proven is True
    assert result.signal_bridge_consumed is False
    assert _is_hex64(result.paper_edge_id)
    assert result.paper_edge_id == _expected_edge_id("alpha-funding-carry", _MARKET)
    assert result.edge_id_form == "hex64_sha256"
    assert result.edge_id_derivation_policy == "sha256_canonical_strategy_id_market_symbol.v1"
    assert result.edge_id_derivation_inputs == ("strategy_id", "market_symbol")
    assert result.strategy_id == "alpha-funding-carry"
    assert result.strategy_version == "1.0.0"
    assert result.strategy_family == "carry"
    assert result.edge_family == "funding_basis_carry"
    assert result.market_type == "usdt_perp"
    assert result.market_symbol == _MARKET
    assert result.verified_strategy_spec_digest == result.expected_strategy_spec_digest
    assert result.binding_strength == "STRATEGY_SPEC_DIGEST_BOUND"
    assert result.signal_bridge_digest == ""
    assert result.expected_signal_bridge_digest == ""
    assert result.verified_signal_bridge_digest == ""
    assert result.paper_chain_link == "correlation_and_market_only"
    assert result.paper_chain_link_cryptographic is False
    assert result.paper_chain_spec_digest_carried is False
    assert result.paper_chain_link_limitation == "merged_stage10_4_chain_does_not_carry_strategy_spec_digest.v1"
    assert result.reason_codes == ()
    assert _is_hex64(result.edge_identity_digest)
    assert payload["status"] == "READY"
    assert payload["edge_identity_digest"] == paper_edge_identity_evidence_digest(result)


def test_paper_edge_id_matches_governance_derivation() -> None:
    result = _build()
    expected = _expected_edge_id(result.strategy_id, result.market_symbol)
    assert result.paper_edge_id == expected
    assert result.paper_edge_id == result.paper_edge_id.lower()


# --- 3. Happy READY (with bridge) ---------------------------------------------------------------------------


def test_happy_path_with_bridge() -> None:
    spec = _spec()
    bridge = _bridge(spec)
    result = _build(
        spec,
        signal_to_paper_intent=bridge,
        expected_signal_bridge_digest=bridge.bridge_digest,
    )

    assert result.status is PaperEdgeIdentityEvidenceStatus.READY
    assert result.signal_bridge_consumed is True
    assert result.binding_strength == "SPEC_DIGEST_AND_SIGNAL_BRIDGE_BOUND"
    assert result.signal_bridge_digest == bridge.bridge_digest
    assert result.expected_signal_bridge_digest == bridge.bridge_digest
    assert result.verified_signal_bridge_digest == bridge.bridge_digest
    assert result.paper_edge_id == _expected_edge_id("alpha-funding-carry", _MARKET)


# --- 4. Edge-id determinism ---------------------------------------------------------------------------------


def test_repeated_build_deterministic() -> None:
    assert _build().edge_identity_digest == _build().edge_identity_digest
    assert _build().paper_edge_id == _build().paper_edge_id


def test_different_market_changes_edge_id() -> None:
    base = _build()
    other = _build(market_symbol="ETH-PERPETUAL")
    assert base.paper_edge_id != other.paper_edge_id


def test_different_strategy_id_changes_edge_id() -> None:
    base = _build()
    other_spec = _spec(strategy_id="beta-basis-carry")
    other = _build(other_spec)
    assert base.paper_edge_id != other.paper_edge_id


def test_edge_family_change_does_not_change_edge_id_but_changes_spec_digest() -> None:
    # Approved governance: paper_edge_id derives ONLY from {strategy_id, market_symbol}; edge_family changes the
    # StrategySpec digest but not the edge id.
    base = _build()
    other_spec = _spec(edge_family="momentum_breakout")
    other = _build(other_spec)
    assert base.paper_edge_id == other.paper_edge_id
    assert base.verified_strategy_spec_digest != other.verified_strategy_spec_digest


# --- 5. StrategySpec fail-closed ----------------------------------------------------------------------------


def test_exact_strategy_spec_type_required() -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="strategy_spec_malformed"):
        build_paper_edge_identity_evidence(
            object(),  # type: ignore[arg-type]
            expected_strategy_spec_digest=_HEX_A,
            market_symbol=_MARKET,
            edge_identity_id="edge-1",
            paper_id="paper-1",
            correlation_id="corr-1",
        )


def test_malformed_expected_spec_digest_raises() -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="expected_strategy_spec_digest_invalid"):
        _build(expected_strategy_spec_digest="not-a-digest")


def test_spec_digest_mismatch_rejects() -> None:
    result = _build(expected_strategy_spec_digest="b" * 64)
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert result.edge_identity_resolved is False
    assert result.paper_edge_id == ""
    assert result.binding_strength == "UNRESOLVED"
    assert "paper_edge_identity_evidence:strategy_spec_digest_mismatch" in result.reason_codes


def test_invalid_strategy_spec_rejects() -> None:
    bad_spec = replace(_spec(), strategy_id="")
    result = build_paper_edge_identity_evidence(
        bad_spec,
        expected_strategy_spec_digest=strategy_spec_digest(bad_spec),
        market_symbol=_MARKET,
        edge_identity_id="edge-1",
        paper_id="paper-1",
        correlation_id="corr-1",
    )
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:strategy_spec_invalid" in result.reason_codes


def test_market_symbol_not_in_universe_rejects() -> None:
    result = _build(market_symbol="SOL-PERPETUAL")
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:market_symbol_not_in_universe" in result.reason_codes


def test_unsupported_market_type_rejects() -> None:
    bad_spec = replace(_spec(), market_type="weird_market")  # type: ignore[arg-type]
    result = build_paper_edge_identity_evidence(
        bad_spec,
        expected_strategy_spec_digest=_HEX_A,
        market_symbol=_MARKET,
        edge_identity_id="edge-1",
        paper_id="paper-1",
        correlation_id="corr-1",
    )
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:unsupported_market_type" in result.reason_codes


def test_strategy_spec_not_mutated() -> None:
    spec = _spec()
    before = strategy_spec_digest(spec)
    _build(spec)
    assert strategy_spec_digest(spec) == before


def test_spec_forbidden_scope_value_rejects() -> None:
    # The artifact's no-venue/no-live/no-clock contract must apply to the spec's VALUES (validate only rejects
    # forbidden keys). A spec carrying e.g. venue_assumptions=("deribit",) must fail closed even when validated.
    forged = replace(_spec(), venue_assumptions=("deribit",))
    result = build_paper_edge_identity_evidence(
        forged,
        expected_strategy_spec_digest=strategy_spec_digest(forged),
        market_symbol=_MARKET,
        edge_identity_id="edge-1",
        paper_id="paper-1",
        correlation_id="corr-1",
    )
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:strategy_spec_scope_violation" in result.reason_codes


def test_spec_forbidden_clock_value_rejects() -> None:
    forged = replace(_spec(), bar_definition="datetime.now")
    result = build_paper_edge_identity_evidence(
        forged,
        expected_strategy_spec_digest=strategy_spec_digest(forged),
        market_symbol=_MARKET,
        edge_identity_id="edge-1",
        paper_id="paper-1",
        correlation_id="corr-1",
    )
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:strategy_spec_clock_token" in result.reason_codes


def test_sneaky_subclass_strategy_id_cannot_diverge_identity() -> None:
    # A forged StrategySpec with a lying empty str-subclass strategy_id must NOT pass as READY with a divergent
    # (empty) emitted identity: the canonical snapshot round-trips to a plain "" and fails closed.
    forged = replace(_spec(), strategy_id=_SneakyStr(""))
    result = build_paper_edge_identity_evidence(
        forged,
        expected_strategy_spec_digest=strategy_spec_digest(forged),
        market_symbol=_MARKET,
        edge_identity_id="edge-1",
        paper_id="paper-1",
        correlation_id="corr-1",
    )
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert result.edge_identity_resolved is False
    assert result.paper_edge_id == ""
    assert "paper_edge_identity_evidence:strategy_id_invalid" in result.reason_codes


# --- 6. Bridge fail-closed ----------------------------------------------------------------------------------


def test_bridge_without_expected_digest_raises() -> None:
    spec = _spec()
    bridge = _bridge(spec)
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="expected_signal_bridge_digest_invalid"):
        _build(spec, signal_to_paper_intent=bridge, expected_signal_bridge_digest=None)


def test_expected_bridge_digest_without_bridge_raises() -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="expected_signal_bridge_digest_unexpected"):
        _build(expected_signal_bridge_digest=_HEX_A)


def test_malformed_expected_bridge_digest_raises() -> None:
    spec = _spec()
    bridge = _bridge(spec)
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="expected_signal_bridge_digest_invalid"):
        _build(spec, signal_to_paper_intent=bridge, expected_signal_bridge_digest="not-hex")


def test_wrong_bridge_type_raises() -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="signal_to_paper_intent_malformed"):
        _build(signal_to_paper_intent=object(), expected_signal_bridge_digest=_HEX_A)


def test_bridge_digest_mismatch_rejects() -> None:
    spec = _spec()
    bridge = _bridge(spec)
    result = _build(spec, signal_to_paper_intent=bridge, expected_signal_bridge_digest="b" * 64)
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:signal_bridge_digest_mismatch" in result.reason_codes


def test_bridge_strategy_id_mismatch_rejects() -> None:
    spec_a = _spec()
    spec_b = _spec(strategy_id="other-strategy")
    bridge_b = _bridge(spec_b)
    result = _build(spec_a, signal_to_paper_intent=bridge_b, expected_signal_bridge_digest=bridge_b.bridge_digest)
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:signal_bridge_strategy_id_mismatch" in result.reason_codes


def test_bridge_correlation_mismatch_rejects() -> None:
    spec = _spec()
    bridge = _bridge(spec, correlation_id="corr-1")
    result = _build(
        spec,
        correlation_id="corr-2",
        signal_to_paper_intent=bridge,
        expected_signal_bridge_digest=bridge.bridge_digest,
    )
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:signal_bridge_correlation_id_mismatch" in result.reason_codes


def test_bridge_market_symbol_mismatch_rejects() -> None:
    spec = _spec()
    bridge = _bridge(spec, market_symbol="ETH-PERPETUAL")
    result = _build(spec, signal_to_paper_intent=bridge, expected_signal_bridge_digest=bridge.bridge_digest)
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:signal_bridge_market_symbol_mismatch" in result.reason_codes


def test_bridge_not_ready_rejects() -> None:
    spec = _spec()
    rejected_bridge = _bridge(spec, expected_spec_digest="d" * 64)
    assert rejected_bridge.ready is False
    result = _build(
        spec,
        signal_to_paper_intent=rejected_bridge,
        expected_signal_bridge_digest=rejected_bridge.bridge_digest,
    )
    assert result.status is PaperEdgeIdentityEvidenceStatus.REJECTED
    assert "paper_edge_identity_evidence:signal_bridge_not_ready" in result.reason_codes


# --- 7. Digest / provenance ---------------------------------------------------------------------------------


def test_digest_excludes_only_self_digest() -> None:
    result = _build()
    assert paper_edge_identity_evidence_digest(result) == result.edge_identity_digest
    resealed = replace(result, edge_identity_digest="0" * 64)
    assert paper_edge_identity_evidence_digest(resealed) == result.edge_identity_digest


def test_serializer_matches_dataclass_fields() -> None:
    result = _build()
    payload = paper_edge_identity_evidence_to_dict(result)
    dataclass_field_names = {field.name for field in fields(result)}

    assert set(payload) == dataclass_field_names
    assert payload["status"] == result.status.value
    assert payload["edge_id_derivation_inputs"] == ["strategy_id", "market_symbol"]
    assert payload["metadata"] == [["purpose", "paper edge identity"]]


def test_metadata_changes_digest_and_is_order_independent() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    changed = _build(metadata={"a": "1", "b": "3"})

    assert first.edge_identity_digest == second.edge_identity_digest
    assert changed.edge_identity_digest != first.edge_identity_digest


@pytest.mark.parametrize(
    "override",
    [
        {"paper_edge_id": "f" * 64},
        {"binding_strength": "UNRESOLVED"},
        {"paper_chain_link_cryptographic": True},
        {"market_type": "spot"},
        {"edge_family": "tampered"},
        {"prdv4_stage4_complete": True},
    ],
)
def test_every_field_is_digest_bound(override: dict[str, object]) -> None:
    result = _build()
    tampered = replace(result, **override)
    assert paper_edge_identity_evidence_digest(tampered) != result.edge_identity_digest


def test_rejection_status_and_reasons_digest_bound() -> None:
    result = _build(expected_strategy_spec_digest="b" * 64)
    payload = paper_edge_identity_evidence_to_dict(result)
    assert payload["status"] == "REJECTED"
    assert payload["ready"] is False
    assert payload["edge_identity_digest"] == paper_edge_identity_evidence_digest(result)


def test_inputs_not_mutated() -> None:
    metadata = {"b": "2", "a": "1"}
    _build(metadata=metadata)
    assert metadata == {"b": "2", "a": "1"}


# --- 8. IDs / metadata --------------------------------------------------------------------------------------


def test_empty_and_subclass_ids_raise() -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="edge_identity_id_invalid"):
        _build(edge_identity_id="  ")
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="paper_id_invalid"):
        _build(paper_id=_LiarStr("paper-1"))
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="correlation_id_invalid"):
        _build(correlation_id="")
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="market_symbol_invalid"):
        _build(market_symbol=_LiarStr(_MARKET))


def test_control_character_id_raises() -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="edge_identity_id_invalid"):
        _build(edge_identity_id="edge\t1")


def test_malformed_metadata_raises() -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError, match="metadata_malformed"):
        _build(metadata={"ok": 1})


@pytest.mark.parametrize(
    "override",
    [
        {"edge_identity_id": "live-edge"},
        {"paper_id": "order-paper"},
        {"correlation_id": "shadow-corr"},
        {"metadata": {"path": "crypto_core.execution.paper_adapter"}},
        {"metadata": {"venue": "BIST"}},
        {"metadata": {"source": "time.time_ns"}},
        {"metadata": {"source": "datetime.now"}},
    ],
)
def test_forbidden_scope_and_clock_tokens_raise(override: dict[str, object]) -> None:
    with pytest.raises(PaperEdgeIdentityEvidenceError):
        _build(**override)


def test_metadata_is_copied_and_frozen() -> None:
    result = _build()
    payload = paper_edge_identity_evidence_to_dict(result)
    assert payload["metadata"] == [["purpose", "paper edge identity"]]
    with pytest.raises(FrozenInstanceError):
        result.metadata = ()  # type: ignore[misc]


# --- 9. Non-overclaim ---------------------------------------------------------------------------------------


def test_non_overclaim_flags_are_false_and_digest_bound() -> None:
    result = _build()
    payload = paper_edge_identity_evidence_to_dict(result)

    assert payload["paper_only"] is True
    assert payload["edge_identity_resolved"] is True
    assert payload["strategy_spec_identity_proven"] is True
    for flag in (
        "edge_proven",
        "profitability_proven",
        "same_edge_as_backtest_proven",
        "same_edge_comparison_ready",
        "comparison_ready",
        "paper_vs_backtest_comparison_ready",
        "stage4_comparator_invoked",
        "thirty_day_gate_satisfied",
        "prdv4_stage4_complete",
        "operational_readiness",
        "live_ready",
        "shadow_ready",
        "deribit_ready",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "private_api_ready",
        "real_wall_clock_used",
        "real_account_equity_used",
        "real_capital_used",
    ):
        assert payload[flag] is False
    for forbidden_key in ("compare_stage4", "Stage4PaperSummary", "Stage4BacktestBaseline", "backtest_sharpe"):
        assert forbidden_key not in payload


def test_rejected_does_not_resolve_identity() -> None:
    result = _build(market_symbol="SOL-PERPETUAL")
    assert result.edge_identity_resolved is False
    assert result.strategy_spec_identity_proven is False
    assert result.edge_proven is False
    assert result.same_edge_as_backtest_proven is False


# --- 10. AST forbidden surface ------------------------------------------------------------------------------


def test_source_has_no_forbidden_runtime_or_stage4_execution_surfaces() -> None:
    source = Path(edge_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "math",
        "numpy",
        "pandas",
        "time",
        "datetime",
        "random",
        "secrets",
        "uuid",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "threading",
        "asyncio",
        "multiprocessing",
        "subprocess",
        "os",
        "pathlib",
        "shutil",
        "sqlite3",
        "duckdb",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.session",
        "crypto_core.data",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
        "crypto_core.validation.paper_sharpe_evidence",
        "crypto_core.validation.paper_vs_backtest_methodology",
        "crypto_core.validation.paper_daily_return_series_evidence",
        "crypto_core.validation.paper_30day_evidence_gate_decision",
    )
    forbidden_call_names = {
        "open",
        "Path",
        "float",
        "compare_stage4",
        "Stage4PaperSummary",
        "Stage4BacktestBaseline",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == module or alias.name.startswith(f"{module}.") for module in forbidden_modules
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                node.module == module or node.module.startswith(f"{module}.") for module in forbidden_modules
            )
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names
