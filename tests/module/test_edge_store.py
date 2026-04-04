"""EdgeStore — load/get."""

from __future__ import annotations

from bist_core.edge.edge_store import EdgeStore


def test_load_and_get() -> None:
    st = EdgeStore()
    k = (0, 10, 1, 0, "mv_flat", 0)
    st.load({k: {"exp": 0.03, "count": 40}})
    assert st.get(k) == {"exp": 0.03, "count": 40}
    assert st.get((0.0,)) is None


def test_load_by_tf() -> None:
    st = EdgeStore()
    k = (0, 10, 0, 0, "mv_flat", 0)
    st.load_by_tf({"1m": {k: {"exp": 0.01, "count": 9}}})
    assert st.get_tf("1m", k) == {"exp": 0.01, "count": 9}
    assert st.get_tf("5m", k) is None


def test_live_edges_override_historical() -> None:
    st = EdgeStore()
    k = (0, 10, 0, 0, "mv_flat", 0)
    st.load({k: {"exp": 0.01, "count": 100, "confidence": 0.5}})
    st.load_live({k: {"exp": 0.08, "count": 40, "confidence": 0.9}}, loaded_cycle=50)
    assert st.get(k)["exp"] == 0.08
    g = st.get(k, edge_cycle=50)
    assert g is not None and abs(float(g["exp"]) - 0.08) < 1e-12


def test_load_live_prunes_to_max_edges() -> None:
    st = EdgeStore()
    keys = [((i, 10, 0, 0, "mv_flat", 0), {"exp": float(i) * 0.01, "count": 10}) for i in range(20)]
    st.load_live(dict(keys), loaded_cycle=0, max_edges=5)
    assert len(st.live_edges) == 5


def test_live_edge_decay_when_stale_cycle() -> None:
    st = EdgeStore()
    k = (0, 10, 0, 0, "mv_flat", 0)
    st.load_live({k: {"exp": 0.10, "count": 40, "confidence": 0.8}}, loaded_cycle=0)
    g = st.get(k, edge_cycle=100)
    assert g is not None
    assert float(g["exp"]) < 0.10
