from __future__ import annotations
from pathlib import Path
import os
import json
from typing import Any, Dict, Optional, Tuple

# ---- Proje kökleri / data yolları ----
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("BIST_DATA_DIR", REPO_ROOT / "data"))
SAMPLES_DIR = Path(os.getenv("BIST_SAMPLES_DIR", DATA_DIR / "samples"))
EOD_SNAPSHOT_DIR = Path(os.getenv("BIST_EOD_SNAPSHOT_DIR", DATA_DIR / "eod_snapshots"))

# ---- FAZ66: Strict core config schema v1 (production-grade loader) ----
CORE_SCHEMA_V1_REQUIRED: Dict[str, Any] = {
    "timezone": str,
    "default_spread_bps_max": (int, float),
    "default_adv_tl_min": (int, float),
    "default_auction_ratio_max": (int, float),
    "default_price_band_pct": (int, float),
    "risk_per_trade": (int, float),
}


def resolve_core_config_path(config_arg: Optional[str], repo_root: Path) -> Optional[Path]:
    """Resolve core config path: --config > BIST_CORE_CONFIG env > repo_root/config/core.json."""
    if config_arg:
        return Path(config_arg)
    env_path = os.environ.get("BIST_CORE_CONFIG")
    if env_path:
        return Path(env_path)
    return repo_root / "config" / "core.json"


def _validate_core_schema_v1(data: Dict[str, Any]) -> Optional[str]:
    """Validate data against CORE_SCHEMA_V1. Returns None if valid, else error code string."""
    if not isinstance(data, dict):
        return "CONFIG_INVALID"
    for key, allowed in CORE_SCHEMA_V1_REQUIRED.items():
        if key not in data:
            return "CONFIG_INVALID"
        val = data[key]
        if isinstance(allowed, tuple):
            if type(val) not in allowed:
                return "CONFIG_INVALID"
        elif type(val) is not allowed:
            return "CONFIG_INVALID"
    return None


def load_core_config_strict(path: Optional[Path]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Load, migrate (v1->v2...), and validate core config. Missing/invalid config returns (None, error_code).
    error_code: CONFIG_MISSING (file missing), CONFIG_INVALID (bad JSON or schema).
    """
    if path is None or not path.is_file():
        return None, "CONFIG_MISSING"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, "CONFIG_INVALID"
    from bist_core.config_migrate import migrate_core_config
    data = migrate_core_config(data)
    err = _validate_core_schema_v1(data)
    if err:
        return None, err
    return data, None


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


# ---- FAZ80: Broker config loader (BIST_BROKER_CONFIG: file path OR inline JSON) ----
def load_broker_config(raw: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Load broker config from BIST_BROKER_CONFIG value: file path (existing file) OR inline JSON.
    Returns (config_dict, None) on success, (None, error_code) on failure.
    error_code: broker_config_missing (empty/not set), broker_config_invalid (bad JSON or not a dict).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "broker_config_missing"
    s = raw.strip()
    path = Path(s)
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None, "broker_config_invalid"
        if not isinstance(data, dict):
            return None, "broker_config_invalid"
        return data, None
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None, "broker_config_invalid"
    if not isinstance(data, dict):
        return None, "broker_config_invalid"
    return data, None


__all__ = [
    "REPO_ROOT", "DATA_DIR", "SAMPLES_DIR", "EOD_SNAPSHOT_DIR",
    "SOURCES", "CORE", "load_config",
    "resolve_core_config_path", "load_core_config_strict", "CORE_SCHEMA_V1_REQUIRED",
    "load_broker_config",
]
