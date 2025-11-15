
from pathlib import Path
from subprocess import run, PIPE
import csv

ROOT = Path(__file__).resolve().parents[1]

def _run(mod: str, *args: str) -> str:
    r = run(["python", "-m", mod, *args], stdout=PIPE, stderr=PIPE, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout

def test_plan_cli_equal_weight(tmp_path: Path):
    day = "2025-01-15"
    # 1) snapshot üret (deterministik smoke)
    out = _run("bist_core.cli.main", "eod", "--date", day)
    assert "snapshot" in out.lower()
    # 2) plan üret
    out = _run("bist_core.cli.main", "plan", "--date", day)
    assert "Plan yazıldı:" in out
    plan = ROOT / f"data/eod/snapshots/{day}/plan_equal_weight.csv"
    assert plan.exists(), "Plan CSV yazılmadı"
    rows = list(csv.DictReader(plan.open(encoding="utf-8")))
    assert len(rows) >= 1
    if len(rows) == 1 and rows[0]["symbol"] == "TEST":
        assert abs(float(rows[0]["weight"]) - 1.0) < 1e-9
