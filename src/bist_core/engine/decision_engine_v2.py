"""Re-export canonical decision engine (implementation lives in ``bist_core.decision``)."""

from bist_core.decision.decision_engine_v2 import (
    DecisionEngineV2,
    _brain_test,
    edge_bucket_key,
    generate_dummy_bars,
    run_decision,
    run_sample_test,
)

__all__ = [
    "DecisionEngineV2",
    "edge_bucket_key",
    "run_sample_test",
    "run_decision",
    "generate_dummy_bars",
    "_brain_test",
]
