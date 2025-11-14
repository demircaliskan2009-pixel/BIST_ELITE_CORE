from src.bist_core.runner import run_decision
def test_smoke():
    res = run_decision()
    assert isinstance(res, list) and len(res)>0
