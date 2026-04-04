"""AuditLogger + HealthMonitor — deterministic, no crash."""

from __future__ import annotations

from bist_core.live.paper_trader import PaperTrader
from bist_core.monitoring.audit_logger import AuditLogger
from bist_core.monitoring.health_monitor import HealthMonitor


def test_audit_logger_appends_and_timestamp() -> None:
    a = AuditLogger()
    a.log({"event": "decision", "symbol": "X", "data": {"a": 1}})
    logs = a.get_logs()
    assert len(logs) == 1
    assert logs[0]["event"] == "decision"
    assert "timestamp" in logs[0]
    assert logs[0]["data"]["a"] == 1


def test_audit_logger_json_safe_non_serializable() -> None:
    a = AuditLogger()
    a.log({"event": "risk", "symbol": "Y", "data": {"x": object()}})
    logs = a.get_logs()
    assert len(logs) == 1


def test_health_record_trade_and_snapshot() -> None:
    h = HealthMonitor()
    h.record_trade(0.05)
    h.record_trade(-0.02)
    h.record_trade(0.0)
    s = h.snapshot()
    assert s["total_trades"] == 3
    assert s["wins"] == 1
    assert s["losses"] == 1


def test_health_record_error() -> None:
    h = HealthMonitor()
    h.record_error("boom")
    assert h.snapshot()["last_error"] == "boom"


def test_paper_trader_audit_and_health_no_crash() -> None:
    import bist_core.live.paper_trader as pt_mod

    orig = pt_mod.get_current_price
    pt_mod.get_current_price = lambda s: 100.0 if s == "GARAN" else None
    try:

        class _B:
            def is_price_valid(self, p):
                return True

            def is_liquid(self, b):
                return True

            def is_trade_allowed(self, p, pc):
                return True

        class DE:
            def evaluate_symbol(self, ctx):
                return {"action": "hold", "reason": "t", "score": 0.5, "risk": {"stop_price": 95.0}}

        aud = AuditLogger()
        hlth = HealthMonitor()
        trader = PaperTrader(["GARAN"], bist_rules=_B(), audit_logger=aud, health_monitor=hlth)
        trader.decision_engine = DE()
        trader._positions["GARAN"] = {"entry_price": 100.0, "size": 1, "ts": 0}
        r = trader.run_once()
        assert r.get("status") == "ok"
        assert len(trader.get_audit_logs()) >= 1
        assert isinstance(trader.get_system_health(), dict)
    finally:
        pt_mod.get_current_price = orig
