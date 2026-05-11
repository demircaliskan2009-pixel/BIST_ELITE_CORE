"""Phase 18K tests — Stage4 baseline storage on sleeve state.

Validates:
- stage4_backtest_baseline_from_dict / stage4_backtest_baseline_to_dict roundtrip.
- stage4_backtest_baseline_from_dict rejects malformed payloads.
- build_sleeve_with_stage4_baseline stores computed baseline on sleeve.
- build_sleeve_with_stage4_comparison uses sleeve.stage4_backtest_baseline when explicit baseline is None.
- Explicit baseline arg overrides sleeve baseline.
- stage4_backtest_baseline survives crypto_sleeve_state_to_dict / from_dict roundtrip.
- Existing Phase 18J stage4_comparison_result and stage4_comparison_required roundtrips preserved.
- Full Stage4 chain: attach baseline → attach PASS comparison → gate clears.
- Full Stage4 chain: attach baseline → REJECT comparison → gate fires.
"""

from __future__ import annotations

import pytest

import crypto_core.validation as validation
from crypto_core.service import sleeve_portfolio as portfolio

_DAY_NS = 86400 * 1_000_000_000


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _windows(*, count: int = 3, oos_sharpe: float = 2.0, oos_hit_rate: float = 0.60) -> tuple:
    return tuple(
        validation.WalkForwardWindow(
            window_id=f"wf-{i:03d}",
            in_sample_sharpe=2.5,
            out_of_sample_sharpe=oos_sharpe,
            oos_expectancy=0.1,
            in_sample_hit_rate=0.65,
            out_of_sample_hit_rate=oos_hit_rate,
            trade_count=50,
            evidence_count=50,
            in_sample_max_drawdown=0.05,
            oos_max_drawdown=0.06,
            oos_profit_factor=1.4,
        )
        for i in range(1, count + 1)
    )


def _baseline() -> validation.Stage4BacktestBaseline:
    return validation.build_stage4_backtest_baseline(
        baseline_id="baseline-001",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
        backtest_slippage_bps=5.0,
        backtest_fill_rate=0.95,
        source_window_ids=("wf-001", "wf-002", "wf-003"),
    )


def _paper(**overrides) -> validation.Stage4PaperSummary:
    values = {
        "paper_id": "paper-001",
        "edge_id": "edge-alpha",
        "started_at_ns": 1,
        "stopped_at_ns": 31 * _DAY_NS + 1,
        "paper_sharpe": 1.2,
        "paper_hit_rate": 0.58,
        "paper_slippage_bps": 4.0,
        "paper_fill_rate": 0.97,
        "paper_trade_count": 42,
    }
    values.update(overrides)
    return validation.Stage4PaperSummary(**values)


def _pipeline(*, ready: bool) -> validation.ValidationPipelineResult:
    from dataclasses import replace as dc_replace

    stage = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=ready,
        skipped=False,
        rejection_reasons=(),
    )
    return validation.ValidationPipelineResult(
        validation_ready=ready,
        stage2_status=dc_replace(stage, stage="stage2_walk_forward"),
        pbo_status=dc_replace(stage, stage="pbo"),
        stage3_status=dc_replace(stage, stage="stage3_stress"),
        pbo_allocation_cap=None,
        rejection_reasons=(),
        missing_stages=() if ready else ("stage2_walk_forward",),
    )


def _sleeve(
    *,
    stage4_baseline: validation.Stage4BacktestBaseline | None = None,
    stage4_result: validation.Stage4ComparisonResult | None = None,
    stage4_required: bool = False,
    validation_pipeline_result: validation.ValidationPipelineResult | None = None,
) -> portfolio.CryptoSleeveState:
    return portfolio.CryptoSleeveState(
        sleeve_id="sleeve-microstructure",
        sleeve_type=portfolio.CryptoSleeveType.MICROSTRUCTURE,
        status=portfolio.CryptoSleeveStatus.DEFINED,
        validation_pipeline_result=validation_pipeline_result,
        stage4_comparison_result=stage4_result,
        stage4_comparison_required=stage4_required,
        stage4_backtest_baseline=stage4_baseline,
    )


def _roundtrip(sleeve: portfolio.CryptoSleeveState) -> portfolio.CryptoSleeveState:
    return portfolio.crypto_sleeve_state_from_dict(portfolio.crypto_sleeve_state_to_dict(sleeve))


# ---------------------------------------------------------------------------
# A.1 — stage4_backtest_baseline_to_dict / from_dict roundtrip
# ---------------------------------------------------------------------------


def test_stage4_backtest_baseline_dict_roundtrip():
    original = _baseline()
    restored = validation.stage4_backtest_baseline_from_dict(validation.stage4_backtest_baseline_to_dict(original))
    assert restored == original
    assert restored.baseline_id == "baseline-001"
    assert restored.edge_id == "edge-alpha"
    assert restored.as_of_ns == 31 * _DAY_NS
    assert restored.backtest_sharpe == 2.0
    assert restored.backtest_hit_rate == 0.60
    assert restored.backtest_slippage_bps == 5.0
    assert restored.backtest_fill_rate == 0.95
    assert restored.source_window_ids == ("wf-001", "wf-002", "wf-003")


def test_stage4_backtest_baseline_dict_roundtrip_optional_none():
    original = validation.build_stage4_backtest_baseline(
        baseline_id="b-002",
        edge_id="edge-beta",
        as_of_ns=_DAY_NS,
        backtest_sharpe=1.5,
        backtest_hit_rate=0.55,
        backtest_slippage_bps=None,
        backtest_fill_rate=None,
        source_window_ids=(),
    )
    restored = validation.stage4_backtest_baseline_from_dict(validation.stage4_backtest_baseline_to_dict(original))
    assert restored == original
    assert restored.backtest_slippage_bps is None
    assert restored.backtest_fill_rate is None
    assert restored.source_window_ids == ()


# ---------------------------------------------------------------------------
# A.2 — stage4_backtest_baseline_from_dict rejects malformed payloads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override,expected_fragment",
    [
        ({"baseline_id": ""}, "baseline_id"),
        ({"baseline_id": None}, "baseline_id"),
        ({"edge_id": ""}, "edge_id"),
        ({"as_of_ns": 0}, "as_of_ns"),
        ({"as_of_ns": -1}, "as_of_ns"),
        ({"as_of_ns": "not-an-int"}, "as_of_ns"),
        ({"backtest_sharpe": float("inf")}, "backtest_sharpe"),
        ({"backtest_sharpe": float("nan")}, "backtest_sharpe"),
        ({"backtest_sharpe": None}, "backtest_sharpe"),
        ({"backtest_hit_rate": float("nan")}, "backtest_hit_rate"),
        ({"backtest_slippage_bps": -1.0}, "backtest_slippage_bps"),
        ({"backtest_fill_rate": 1.5}, "backtest_fill_rate"),
        ({"source_window_ids": "not-a-list"}, "source_window_ids"),
        ({"source_window_ids": ["", "wf-001"]}, "source_window_ids"),
    ],
)
def test_stage4_backtest_baseline_from_dict_rejects_malformed(override, expected_fragment):
    valid = {
        "baseline_id": "b-001",
        "edge_id": "edge-alpha",
        "as_of_ns": _DAY_NS,
        "backtest_sharpe": 2.0,
        "backtest_hit_rate": 0.60,
        "backtest_slippage_bps": 5.0,
        "backtest_fill_rate": 0.95,
        "source_window_ids": ["wf-001"],
    }
    valid.update(override)
    with pytest.raises(ValueError, match=expected_fragment):
        validation.stage4_backtest_baseline_from_dict(valid)


def test_stage4_backtest_baseline_from_dict_rejects_non_dict():
    with pytest.raises(ValueError, match="mapping"):
        validation.stage4_backtest_baseline_from_dict("not-a-dict")


# ---------------------------------------------------------------------------
# B.3 — build_sleeve_with_stage4_baseline stores baseline
# ---------------------------------------------------------------------------


def test_build_sleeve_with_stage4_baseline_stores_baseline():
    windows = _windows()
    sleeve = _sleeve()
    updated = portfolio.build_sleeve_with_stage4_baseline(
        sleeve,
        windows,
        baseline_id="baseline-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )
    assert updated.stage4_backtest_baseline is not None
    assert updated.stage4_backtest_baseline.baseline_id == "baseline-wf"
    assert updated.stage4_backtest_baseline.edge_id == "edge-alpha"
    assert len(updated.stage4_backtest_baseline.source_window_ids) == 3
    assert updated.stage4_comparison_result is None  # not set yet


def test_build_sleeve_with_stage4_baseline_preserves_source_window_ids():
    windows = _windows(count=2)
    sleeve = _sleeve()
    updated = portfolio.build_sleeve_with_stage4_baseline(
        sleeve,
        windows,
        baseline_id="b-wf",
        edge_id="edge-alpha",
        as_of_ns=_DAY_NS,
    )
    assert updated.stage4_backtest_baseline.source_window_ids == ("wf-001", "wf-002")


def test_build_sleeve_with_stage4_baseline_with_optional_fields():
    windows = _windows(count=1)
    sleeve = _sleeve()
    updated = portfolio.build_sleeve_with_stage4_baseline(
        sleeve,
        windows,
        baseline_id="b-opt",
        edge_id="edge-alpha",
        as_of_ns=_DAY_NS,
        backtest_slippage_bps=3.0,
        backtest_fill_rate=0.92,
    )
    assert updated.stage4_backtest_baseline.backtest_slippage_bps == 3.0
    assert updated.stage4_backtest_baseline.backtest_fill_rate == 0.92


# ---------------------------------------------------------------------------
# B.4 — build_sleeve_with_stage4_comparison uses sleeve baseline when explicit baseline is None
# ---------------------------------------------------------------------------


def test_build_sleeve_with_stage4_comparison_uses_sleeve_baseline_when_explicit_none():
    sleeve = _sleeve(stage4_baseline=_baseline())
    updated = portfolio.build_sleeve_with_stage4_comparison(sleeve, None, _paper())
    result = updated.stage4_comparison_result
    assert result is not None
    assert result.status == "PASS"
    assert result.passed is True
    assert result.baseline_id == "baseline-001"


def test_build_sleeve_with_stage4_comparison_none_baseline_none_sleeve_baseline():
    sleeve = _sleeve(stage4_baseline=None)
    updated = portfolio.build_sleeve_with_stage4_comparison(sleeve, None, _paper())
    result = updated.stage4_comparison_result
    assert result is not None
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "stage4:backtest_baseline_missing" in result.rejection_reasons


# ---------------------------------------------------------------------------
# B.5 — Explicit baseline overrides sleeve baseline
# ---------------------------------------------------------------------------


def test_build_sleeve_with_stage4_comparison_explicit_baseline_overrides_sleeve_baseline():
    sleeve_baseline = validation.build_stage4_backtest_baseline(
        baseline_id="sleeve-baseline",
        edge_id="edge-DIFFERENT",  # different edge — would cause edge_id_mismatch with default paper
        as_of_ns=_DAY_NS,
        backtest_sharpe=2.0,
        backtest_hit_rate=0.60,
    )
    explicit_baseline = _baseline()  # edge_id="edge-alpha" matches paper
    sleeve = _sleeve(stage4_baseline=sleeve_baseline)
    updated = portfolio.build_sleeve_with_stage4_comparison(sleeve, explicit_baseline, _paper())
    result = updated.stage4_comparison_result
    assert result is not None
    assert result.baseline_id == "baseline-001"  # explicit baseline used
    assert result.status == "PASS"


# ---------------------------------------------------------------------------
# B.6 — stage4_backtest_baseline survives sleeve state roundtrip
# ---------------------------------------------------------------------------


def test_sleeve_stage4_backtest_baseline_survives_state_roundtrip():
    sleeve = _sleeve(stage4_baseline=_baseline())
    restored = _roundtrip(sleeve)
    assert restored.stage4_backtest_baseline is not None
    assert restored.stage4_backtest_baseline == _baseline()


def test_sleeve_stage4_backtest_baseline_none_survives_state_roundtrip():
    sleeve = _sleeve(stage4_baseline=None)
    restored = _roundtrip(sleeve)
    assert restored.stage4_backtest_baseline is None


def test_sleeve_stage4_backtest_baseline_missing_key_treated_as_none():
    sleeve = _sleeve(stage4_baseline=_baseline())
    d = portfolio.crypto_sleeve_state_to_dict(sleeve)
    d.pop("stage4_backtest_baseline")
    restored = portfolio.crypto_sleeve_state_from_dict(d)
    assert restored.stage4_backtest_baseline is None


# ---------------------------------------------------------------------------
# B.7 — Phase 18J stage4_comparison_result roundtrip still preserved
# ---------------------------------------------------------------------------


def test_sleeve_stage4_comparison_result_survives_state_roundtrip():
    result = validation.compare_stage4(_baseline(), _paper())
    sleeve = _sleeve(stage4_result=result)
    restored = _roundtrip(sleeve)
    assert restored.stage4_comparison_result is not None
    assert restored.stage4_comparison_result.passed is True
    assert restored.stage4_comparison_result.baseline_id == "baseline-001"


# ---------------------------------------------------------------------------
# B.8 — stage4_comparison_required survives roundtrip
# ---------------------------------------------------------------------------


def test_sleeve_stage4_required_true_survives_state_roundtrip():
    sleeve = _sleeve(stage4_required=True)
    restored = _roundtrip(sleeve)
    assert restored.stage4_comparison_required is True


def test_sleeve_stage4_required_false_survives_state_roundtrip():
    sleeve = _sleeve(stage4_required=False)
    restored = _roundtrip(sleeve)
    assert restored.stage4_comparison_required is False


# ---------------------------------------------------------------------------
# B.9 — Validation-ready derived required behavior preserved from Phase 18J
# ---------------------------------------------------------------------------


def test_validation_ready_derived_required_survives_to_dict():
    sleeve = _sleeve(
        validation_pipeline_result=_pipeline(ready=True),
        stage4_required=False,
        stage4_result=None,
    )
    restored = _roundtrip(sleeve)
    # validation_pipeline_result NOT serialized into dict (by design per Phase 18J)
    assert restored.validation_pipeline_result is None
    # effective required stored as True since validation_ready=True
    assert restored.stage4_comparison_required is True


# ---------------------------------------------------------------------------
# B.10 — Full Stage4 chain: baseline → comparison PASS → gate clears
# ---------------------------------------------------------------------------


def test_full_stage4_chain_baseline_then_comparison_pass_clears_gate():
    windows = _windows(oos_sharpe=2.0, oos_hit_rate=0.60)
    sleeve = _sleeve(validation_pipeline_result=_pipeline(ready=True))

    # Stage 2: attach baseline
    sleeve = portfolio.build_sleeve_with_stage4_baseline(
        sleeve,
        windows,
        baseline_id="baseline-chain",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
        backtest_slippage_bps=5.0,
        backtest_fill_rate=0.95,
    )

    # Stage 4: attach paper comparison (PASS)
    sleeve = portfolio.build_sleeve_with_stage4_comparison(sleeve, None, _paper())

    assert sleeve.stage4_comparison_result is not None
    assert sleeve.stage4_comparison_result.passed is True

    candidate = portfolio._build_sleeve_promotion_candidate_result(sleeve)
    stage4_blockers = [e for e in candidate.missing_evidence if e.startswith("stage4:")]
    assert not stage4_blockers, f"Unexpected stage4 blockers: {stage4_blockers}"


# ---------------------------------------------------------------------------
# B.11 — Full Stage4 chain: low paper Sharpe → gate fires
# ---------------------------------------------------------------------------


def test_full_stage4_chain_low_paper_sharpe_blocks_gate():
    windows = _windows(oos_sharpe=2.0, oos_hit_rate=0.60)
    sleeve = _sleeve(validation_pipeline_result=_pipeline(ready=True))

    sleeve = portfolio.build_sleeve_with_stage4_baseline(
        sleeve,
        windows,
        baseline_id="baseline-chain-reject",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    # Paper Sharpe = 0.5, which is < 50% of backtest Sharpe (2.0), min required = 1.0
    sleeve = portfolio.build_sleeve_with_stage4_comparison(sleeve, None, _paper(paper_sharpe=0.5))

    assert sleeve.stage4_comparison_result is not None
    assert sleeve.stage4_comparison_result.passed is False

    candidate = portfolio._build_sleeve_promotion_candidate_result(sleeve)
    assert "stage4:paper_sharpe_below_backtest_threshold" in candidate.missing_evidence
