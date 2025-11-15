from pathlib import Path
from datetime import date
from ..config import load_config
from ..paths import EOD_SNAPSHOTS
from ..providers.dummy import DummyProvider

def run_eod(run_date: str | None = None, outdir: str | None = None) -> Path:
    cfg = load_config()
    dt = date.fromisoformat(run_date) if run_date else date.today()
    out_dir = Path(outdir) if outdir else (EOD_SNAPSHOTS / dt.isoformat())
    out_dir.mkdir(parents=True, exist_ok=True)

    df = DummyProvider().prices(cfg.symbols, dt)

    for sym, g in df.groupby("symbol"):
        g.to_csv(out_dir / f"{sym}.csv", index=False)

    (out_dir / "_index.json").write_text(
        df.to_json(orient="records", force_ascii=False)
    )
    return out_dir
