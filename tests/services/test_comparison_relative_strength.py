from bist_core.services.relative_strength import compute_relative_strength

def test_relative_strength_ratio_gt_one():
    rs = compute_relative_strength("AAA","BBB",200,100)
    assert rs["ratio"] == 2
    assert rs["outperformer"] == "AAA"

def test_relative_strength_ratio_lt_one():
    rs = compute_relative_strength("AAA","BBB",50,100)
    assert rs["ratio"] == 0.5
    assert rs["outperformer"] == "BBB"

def test_relative_strength_ratio_eq_one():
    rs = compute_relative_strength("AAA","BBB",100,100)
    assert rs["ratio"] == 1
    assert rs["outperformer"] == "BBB"
