from __future__ import annotations
from pathlib import Path
import os
import json
from typing import Dict, Any

# ---- Proje kökleri / data yolları ----
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("BIST_DATA_DIR", REPO_ROOT / "data"))
SAMPLES_DIR = Path(os.getenv("BIST_SAMPLES_DIR", DATA_DIR / "samples"))
EOD_SNAPSHOT_DIR = Path(os.getenv("BIST_EOD_SNAPSHOT_DIR", DATA_DIR / "eod_snapshots"))

def _load_json_config(rel_path: str) -> Dict[str, Any]:
    """Config JSON dosyasını yükler."""
    config_path = REPO_ROOT / rel_path
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)

# Config dosyalarını yükle
CORE = _load_json_config("config/core.json")
SOURCES_RAW = _load_json_config("config/sources.json")

# SOURCES dict'ini oluştur, local_csv root_dir'i override et
SOURCES: Dict[str, Dict[str, Any]] = SOURCES_RAW.copy()
if "local_csv" in SOURCES:
    # local_csv root_dir'i SAMPLES_DIR ile override et (tests için)
    SOURCES["local_csv"] = SOURCES["local_csv"].copy()
    SOURCES["local_csv"]["root_dir"] = str(SAMPLES_DIR)

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
    dirs_to_create = [DATA_DIR, SAMPLES_DIR, EOD_SNAPSHOT_DIR]
    if "local_csv" in SOURCES and "root_dir" in SOURCES["local_csv"]:
        dirs_to_create.append(Path(SOURCES["local_csv"]["root_dir"]))
    for p in dirs_to_create:
        Path(p).mkdir(parents=True, exist_ok=True)
    return cfg

__all__ = [
    "REPO_ROOT", "DATA_DIR", "SAMPLES_DIR", "EOD_SNAPSHOT_DIR",
    "SOURCES", "CORE", "load_config",
]
