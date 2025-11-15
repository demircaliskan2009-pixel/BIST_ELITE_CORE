from __future__ import annotations
from pathlib import Path
import os
from typing import Dict, Any

# ---- Proje kökleri / data yolları ----
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("BIST_DATA_DIR", REPO_ROOT / "data"))
SAMPLES_DIR = Path(os.getenv("BIST_SAMPLES_DIR", DATA_DIR / "samples"))
EOD_SNAPSHOT_DIR = Path(os.getenv("BIST_EOD_SNAPSHOT_DIR", DATA_DIR / "eod_snapshots"))

# Repositories/local_csv.py beklediği anahtarlar
SOURCES: Dict[str, Dict[str, Any]] = {
    "local_csv": {
        "root_dir": str(SAMPLES_DIR),   # tests/local_csv bu anahtarı okuyor
    }
}

def load_config() -> Dict[str, Any]:
    """
    CLI ve testler için minimal runtime config döndürür.
    Ayrıca gerekli klasörleri oluşturur (idempotent).
    """
    cfg = {
        "repo_root": str(REPO_ROOT),
        "data_dir": str(DATA_DIR),
        "samples_dir": str(SAMPLES_DIR),
        "eod_snapshot_dir": str(EOD_SNAPSHOT_DIR),
        "sources": SOURCES,
    }
    for p in (DATA_DIR, SAMPLES_DIR, EOD_SNAPSHOT_DIR, Path(SOURCES["local_csv"]["root_dir"])):
        Path(p).mkdir(parents=True, exist_ok=True)
    return cfg

__all__ = [
    "REPO_ROOT", "DATA_DIR", "SAMPLES_DIR", "EOD_SNAPSHOT_DIR",
    "SOURCES", "load_config",
]
