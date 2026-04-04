"""Edge distribution adjustments — deterministic cross-symbol spread (no network)."""

from __future__ import annotations

from bist_core.features.edge_features_v2 import FeatureEngineV2
from bist_core.live.edge_distribution_fix import apply_edge_distribution_adjustments
from bist_core.models.ohlcv import OHLCVBar


def _bars(sym: str, *, slope: float) -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    p = 100.0
    for i in range(50):
        p += slope
        o = p - 0.1
        h = p + 0.2
        l = p - 0.2
        out.append(
            OHLCVBar(
                timestamp=i,
                symbol=sym,
                open=o,
                high=h,
                low=l,
                close=p,
                volume=1_000_000.0 + float(i) * 100.0,
            )
        )
    return out


def test_apply_edge_distribution_spreads_multi_symbol() -> None:
    fe = FeatureEngineV2()
    per_symbol = {
        "ASELS": {
            "decision": {
                "action": "enter_long",
                "confidence": 0.55,
                "edge_score": 0.22,
                "edge": 0.22,
            },
            "bars": _bars("ASELS", slope=0.02),
        },
        "THYAO": {
            "decision": {
                "action": "enter_short",
                "confidence": 0.55,
                "edge_score": 0.58,
                "edge": 0.58,
            },
            "bars": _bars("THYAO", slope=-0.02),
        },
    }
    # Distinct inputs so cross-symbol std passes gate without artificial spreading.
    edge_scores = {"ASELS": 0.22, "THYAO": 0.58}
    out, dbg = apply_edge_distribution_adjustments(
        edge_scores, per_symbol, fe, "TRENDING"
    )
    assert len(out) == 2
    assert dbg.get("EDGE_STD", dbg.get("edge_std", 0)) >= 0.05 - 1e-9


def test_apply_edge_distribution_single_symbol_no_std_gate() -> None:
    fe = FeatureEngineV2()
    per_symbol = {
        "ASELS": {
            "decision": {
                "action": "enter",
                "confidence": 0.5,
                "edge_score": 0.4,
                "edge": 0.4,
            },
            "bars": _bars("ASELS", slope=0.01),
        },
    }
    out, _ = apply_edge_distribution_adjustments(
        {"ASELS": 0.4}, per_symbol, fe, "MIXED"
    )
    assert list(out.keys()) == ["ASELS"]
    assert 0.0 <= out["ASELS"] <= 1.0
