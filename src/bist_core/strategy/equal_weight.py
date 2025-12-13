
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


def generate_equal_weight_orders(day: str, base: Path = Path("data/eod/snapshots")) -> Path | None:
    """Verilen gün için eşit ağırlık stratejisi siparişlerini üretir.
       Risk limitini aşarsa None döner (FAIL), aşmazsa orders dosya yolunu döner (PASS)."""
    # Plan dosyasını oku
    plan_path = base / day / "plan_equal_weight.csv"
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan not found: {plan_path}")
    
    rows = list(csv.DictReader(plan_path.open(encoding="utf-8")))
    if not rows:
        raise FileNotFoundError(f"Plan file is empty: {plan_path}")
    
    # Risk kontrolü: herhangi bir sembol ağırlığı 0.5'ten büyük mü?
    risk_flag = False
    for row in rows:
        w = float(row["weight"])
        if w > 0.5:
            risk_flag = True
            break
    
    # Meta dosyası yolu
    meta_path = base / day / "orders_meta.txt"
    orders_dir = base / day
    
    if risk_flag:
        # Risk eşiği aşıldı, sipariş oluşturulmayacak
        # Meta dosyasına FAIL yaz
        meta_path.write_text("FAIL", encoding="utf-8")
        # Eğer orders dosyası varsa sil (temiz durum için)
        orders_path = orders_dir / "orders_equal_weight.csv"
        if orders_path.exists():
            orders_path.unlink()
        return None
    
    # Risk geçildi, orders dosyasını yaz
    orders_dir.mkdir(parents=True, exist_ok=True)
    orders_path = orders_dir / "orders_equal_weight.csv"
    with orders_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "target_weight"])
        for row in rows:
            # plan ağırlığını target_weight olarak yaz
            w = float(row["weight"])
            writer.writerow([row["symbol"], f"{w:.6f}"])
    
    # Meta dosyasına PASS yaz
    meta_path.write_text("PASS", encoding="utf-8")
    return orders_path