
from dataclasses import dataclass
from pathlib import Path
import csv
from typing import List
from bist_core.services import MarketData

@dataclass
class EqualWeightPlan:
    day: str
    symbols: List[str]

    def write_csv(self, root: Path) -> Path:
        target_dir = root / self.day
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / "plan_equal_weight.csv"
        w = 1.0 / max(len(self.symbols), 1)
        with path.open("w", encoding="utf-8", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["symbol", "weight"])
            for s in self.symbols:
                wr.writerow([s, f"{w:.6f}"])
        return path

def build_equal_weight_plan(day: str, base: Path = Path("data/eod/snapshots")) -> Path:
    md = MarketData(base)
    syms = md.symbols(day)
    plan = EqualWeightPlan(day=day, symbols=syms)
    return plan.write_csv(base)
