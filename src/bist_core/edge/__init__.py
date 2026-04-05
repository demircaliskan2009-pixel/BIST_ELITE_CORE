"""Edge detection and statistical edge engines."""

from bist_core.edge.bucket_key import edge_bucket_key, regime_from_feat
from bist_core.edge.edge_engine_v2 import EdgeEngineV2
from bist_core.edge.edge_fusion import EdgeFusion
from bist_core.edge.registry import (
    EdgeCondition,
    EdgeDefinition,
    EdgeLogic,
    EdgeRegistry,
    EdgeRequiredData,
    EdgeRiskProfile,
    EdgeValidationResult,
    build_builtin_edge_registry,
    builtin_bist_edges,
    validate_edge_definition,
)
from bist_core.edge.edge_store import EdgeStore
from bist_core.edge.live_edge_buffer import LiveEdgeBuffer
from bist_core.edge.live_edge_engine import LiveEdgeEngine
from bist_core.edge.multi_tf_edge import MultiTFEdge

__all__ = [
    "EdgeEngineV2",
    "EdgeFusion",
    "EdgeCondition",
    "EdgeDefinition",
    "EdgeLogic",
    "EdgeRegistry",
    "EdgeRequiredData",
    "EdgeRiskProfile",
    "EdgeStore",
    "EdgeValidationResult",
    "LiveEdgeBuffer",
    "LiveEdgeEngine",
    "MultiTFEdge",
    "build_builtin_edge_registry",
    "builtin_bist_edges",
    "edge_bucket_key",
    "regime_from_feat",
    "validate_edge_definition",
]
