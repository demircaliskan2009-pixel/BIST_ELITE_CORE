from bist_core.execution.engine import ExecutionEngine, OrderState, Order


def test_submit_valid_order():
    eng = ExecutionEngine(slippage_pct=0.0005)
    o = eng.submit("GARAN", entry=100.0, stop=98.0, target=104.0, size=10.0)
    assert o.state == OrderState.FILLED
    assert o.fill_price > 100.0
    assert "GARAN" in eng.open_positions()


def test_submit_invalid_stop():
    eng = ExecutionEngine()
    o = eng.submit("X", entry=98.0, stop=100.0, target=104.0, size=10.0)
    assert o.state == OrderState.REJECTED
    assert o.reject_reason == "stop_gte_entry"


def test_submit_duplicate_rejected():
    eng = ExecutionEngine()
    eng.submit("GARAN", 100.0, 98.0, 104.0, 10.0)
    o2 = eng.submit("GARAN", 100.0, 98.0, 104.0, 10.0)
    assert o2.state == OrderState.REJECTED
    assert o2.reject_reason == "duplicate_symbol"


def test_update_hits_target():
    eng = ExecutionEngine(slippage_pct=0.0)
    eng.submit("GARAN", entry=100.0, stop=98.0, target=104.0, size=10.0)
    closed = eng.update("GARAN", current_price=104.0)
    assert closed is not None
    assert closed.state == OrderState.CLOSED
    assert closed.net_pnl > 0
    assert "GARAN" not in eng.open_positions()


def test_update_hits_stop():
    eng = ExecutionEngine(slippage_pct=0.0)
    eng.submit("GARAN", entry=100.0, stop=98.0, target=104.0, size=10.0)
    closed = eng.update("GARAN", current_price=97.5)
    assert closed is not None
    assert closed.state == OrderState.CLOSED
    assert closed.net_pnl < 0


def test_update_no_trigger():
    eng = ExecutionEngine()
    eng.submit("GARAN", entry=100.0, stop=98.0, target=104.0, size=10.0)
    result = eng.update("GARAN", current_price=101.0)
    assert result is None
    assert "GARAN" in eng.open_positions()


def test_force_close():
    eng = ExecutionEngine(slippage_pct=0.0)
    eng.submit("GARAN", entry=100.0, stop=98.0, target=104.0, size=10.0)
    o = eng.force_close("GARAN", current_price=102.0)
    assert o is not None
    assert o.state == OrderState.CLOSED
    assert "GARAN" not in eng.open_positions()


def test_invalid_inputs_rejected():
    eng = ExecutionEngine()
    assert eng.submit("X", 0, 98, 104, 10).state == OrderState.REJECTED
    assert eng.submit("X", 100, 98, 104, 0).state == OrderState.REJECTED
