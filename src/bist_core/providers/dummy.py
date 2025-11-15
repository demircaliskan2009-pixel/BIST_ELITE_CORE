from dataclasses import dataclass
from datetime import date
from random import Random
import pandas as pd

@dataclass
class DummyProvider:
    seed: int = 42

    def prices(self, symbols: list[str], for_date: date) -> pd.DataFrame:
        rnd = Random(int(for_date.strftime("%Y%m%d")) + self.seed)
        rows = []
        for s in symbols:
            open_ = rnd.uniform(10, 100)
            close = open_ * rnd.uniform(0.95, 1.05)
            high = max(open_, close) * rnd.uniform(1.00, 1.02)
            low = min(open_, close) * rnd.uniform(0.98, 1.00)
            rows.append({
                "symbol": s,
                "date": for_date.isoformat(),
                "open": round(open_, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": int(rnd.uniform(1e5, 1e6)),
            })
        return pd.DataFrame(rows)
