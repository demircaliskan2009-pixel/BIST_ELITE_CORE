from __future__ import annotations

"""
:mod:`bist_core.data` – veri okuma + registry için yüksek seviye API.

Şimdilik:
- read_csv  : local CSV'den DataFrame okur
- DatasetRegistry ve diğerleri : core'dan re-export edilir
"""

from .ingest.local_csv import read_csv
from .registry import (
    DatasetRegistry,
    get_default_registry,
    register_dataset,
    load_registered_dataset,
)

__all__ = [
    "read_csv",
    "DatasetRegistry",
    "register_dataset",
    "load_registered_dataset",
    "get_default_registry",
]
