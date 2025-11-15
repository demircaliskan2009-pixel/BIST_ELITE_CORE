from pathlib import Path

# src/bist_core/paths.py -> parents[2] repo kökü (…/src/..)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
EOD_SNAPSHOTS = DATA_ROOT / "eod" / "snapshots"

for p in (DATA_ROOT, EOD_SNAPSHOTS):
    p.mkdir(parents=True, exist_ok=True)
