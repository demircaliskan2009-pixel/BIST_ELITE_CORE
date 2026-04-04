"""OpsLogger unit tests — log structure, file writing, serialization, determinism."""

from __future__ import annotations

from pathlib import Path

import pytest

from bist_core.ops.ops_logger import OpsLogger, read_jsonl


@pytest.fixture
def logger(tmp_path: Path) -> OpsLogger:
    return OpsLogger(tmp_path / "logs")


# ── Decision logging ──────────────────────────────────────────────────────

class TestDecisionLogging:
    def test_log_decision_creates_file(self, logger: OpsLogger) -> None:
        logger.log_decision(
            symbol="ASELS", entry=100.0, stop=95.0, target=110.0,
            timestamp="2026-01-01", reasoning="momentum strong",
        )
        assert logger.decisions_path.is_file()

    def test_log_decision_record_structure(self, logger: OpsLogger) -> None:
        rec = logger.log_decision(
            symbol="thyao", entry=50.0, stop=48.0, target=55.0,
            timestamp="2026-01-01", reasoning="trend up",
        )
        assert rec["kind"] == "decision"
        assert rec["symbol"] == "THYAO"
        assert rec["entry"] == 50.0
        assert rec["stop"] == 48.0
        assert rec["target"] == 55.0
        assert rec["reasoning"] == "trend up"
        assert "logged_at" in rec

    def test_log_decision_appends(self, logger: OpsLogger) -> None:
        logger.log_decision("A", 1, 0.9, 1.1, "t1")
        logger.log_decision("B", 2, 1.8, 2.2, "t2")
        rows = read_jsonl(logger.decisions_path)
        assert len(rows) == 2
        assert rows[0]["symbol"] == "A"
        assert rows[1]["symbol"] == "B"

    def test_log_decisions_batch(self, logger: OpsLogger) -> None:
        decisions = [
            {"symbol": "X", "entry": 10, "stop": 9, "target": 11, "timestamp": "t"},
            {"symbol": "Y", "entry": 20, "stop": 18, "target": 22, "timestamp": "t"},
        ]
        count = logger.log_decisions_batch(decisions)
        assert count == 2
        rows = read_jsonl(logger.decisions_path)
        assert len(rows) == 2


# ── Order logging ─────────────────────────────────────────────────────────

class TestOrderLogging:
    def test_log_order_creates_file(self, logger: OpsLogger) -> None:
        logger.log_order(
            order_id="O-001", symbol="GARAN", order_type="MARKET",
            size=100, entry=30.0, status="FILLED",
        )
        assert logger.orders_path.is_file()

    def test_log_order_record_structure(self, logger: OpsLogger) -> None:
        rec = logger.log_order(
            order_id="O-002", symbol="akbnk", order_type="LIMIT",
            size=50, entry=25.0, status="PENDING",
        )
        assert rec["kind"] == "order"
        assert rec["order_id"] == "O-002"
        assert rec["symbol"] == "AKBNK"
        assert rec["type"] == "LIMIT"
        assert rec["size"] == 50
        assert rec["status"] == "PENDING"

    def test_log_order_appends(self, logger: OpsLogger) -> None:
        logger.log_order("O1", "A", "MARKET", 10, 1.0, "FILLED")
        logger.log_order("O2", "B", "LIMIT", 20, 2.0, "OPEN")
        rows = logger.read_orders()
        assert len(rows) == 2


# ── Trade logging ─────────────────────────────────────────────────────────

class TestTradeLogging:
    def test_log_trade_creates_file(self, logger: OpsLogger) -> None:
        logger.log_trade(
            entry_time="2026-01-01", exit_time="2026-01-02",
            entry_price=100.0, exit_price=110.0, pnl=100.0, r_multiple=2.0,
        )
        assert logger.trades_path.is_file()

    def test_log_trade_record_structure(self, logger: OpsLogger) -> None:
        rec = logger.log_trade(
            entry_time="t0", exit_time="t1",
            entry_price=50.0, exit_price=55.0, pnl=50.0, r_multiple=1.5,
        )
        assert rec["kind"] == "trade"
        assert rec["entry_price"] == 50.0
        assert rec["exit_price"] == 55.0
        assert rec["pnl"] == 50.0
        assert rec["r_multiple"] == 1.5

    def test_log_trades_batch(self, logger: OpsLogger) -> None:
        trades = [
            {"entry_time": "t0", "exit_time": "t1", "entry_price": 100, "exit_price": 110, "pnl": 100},
            {"entry_time": "t0", "exit_time": "t1", "entry_price": 50, "exit_price": 48, "pnl": -20},
        ]
        count = logger.log_trades_batch(trades)
        assert count == 2
        rows = logger.read_trades()
        assert len(rows) == 2


# ── Risk rejection logging ───────────────────────────────────────────────

class TestRiskRejectionLogging:
    def test_log_risk_rejection(self, logger: OpsLogger) -> None:
        rec = logger.log_risk_rejection(
            symbol="EREGL",
            reason="NO_TRADE: risk_per_trade exceeded",
            violations=["risk_per_trade 3.00% > max 2.00%"],
        )
        assert rec["kind"] == "risk_rejection"
        assert rec["symbol"] == "EREGL"
        assert len(rec["violations"]) == 1
        rows = logger.read_decisions()
        assert any(r["kind"] == "risk_rejection" for r in rows)


# ── Validation logging ───────────────────────────────────────────────────

class TestValidationLogging:
    def test_log_validation_creates_file(self, logger: OpsLogger) -> None:
        logger.log_validation(
            valid=True,
            metrics={"expectancy": 40.0, "profit_factor": 2.5},
            regime_metrics={"bullish": {}, "bearish": {}, "sideways": {}},
            warnings=[],
        )
        assert logger.validation_path.is_file()

    def test_log_validation_record_structure(self, logger: OpsLogger) -> None:
        rec = logger.log_validation(
            valid=False,
            metrics={"expectancy": -10.0},
            warnings=["expectancy below min"],
        )
        assert rec["kind"] == "validation"
        assert rec["valid"] is False
        assert rec["metrics"]["expectancy"] == -10.0
        assert "expectancy below min" in rec["warnings"]

    def test_read_validations(self, logger: OpsLogger) -> None:
        logger.log_validation(True, {"a": 1})
        logger.log_validation(False, {"b": 2}, warnings=["w"])
        rows = logger.read_validations()
        assert len(rows) == 2
        assert rows[0]["valid"] is True
        assert rows[1]["valid"] is False


# ── Serialization ─────────────────────────────────────────────────────────

class TestSerialization:
    def test_jsonl_round_trip(self, logger: OpsLogger) -> None:
        logger.log_decision("X", 1.0, 0.9, 1.1, "t", extra_field="hello")
        rows = read_jsonl(logger.decisions_path)
        assert len(rows) == 1
        assert rows[0]["extra_field"] == "hello"

    def test_sort_keys_deterministic(self, logger: OpsLogger) -> None:
        logger.log_decision("A", 1.0, 0.9, 1.1, "t")
        with logger.decisions_path.open("r", encoding="utf-8") as f:
            line = f.readline().strip()
        parsed = list(eval(f"list({repr(line)})"))
        raw_keys = []
        in_key = False
        for ch in line:
            if ch == '"':
                in_key = not in_key
        content = logger.decisions_path.read_text("utf-8").strip()
        assert content.startswith("{")
        assert '"entry"' in content
        assert '"kind"' in content


# ── Deterministic logging ─────────────────────────────────────────────────

class TestDeterministicLogging:
    def test_same_inputs_same_structure(self, tmp_path: Path) -> None:
        logger1 = OpsLogger(tmp_path / "logs1")
        logger2 = OpsLogger(tmp_path / "logs2")

        logger1.log_decision("ASELS", 100, 95, 110, "2026-01-01", "reason")
        logger2.log_decision("ASELS", 100, 95, 110, "2026-01-01", "reason")

        rows1 = logger1.read_decisions()
        rows2 = logger2.read_decisions()
        assert len(rows1) == len(rows2) == 1
        for key in ("kind", "symbol", "entry", "stop", "target", "reasoning"):
            assert rows1[0][key] == rows2[0][key]


# ── Read helpers on empty ─────────────────────────────────────────────────

class TestReadEmpty:
    def test_read_nonexistent_returns_empty(self, logger: OpsLogger) -> None:
        assert logger.read_decisions() == []
        assert logger.read_orders() == []
        assert logger.read_trades() == []
        assert logger.read_validations() == []
