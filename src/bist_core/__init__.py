from __future__ import annotations

"""
Public package surface for :mod:`bist_core`.

Faz-3 / Adım-1: Küçük ama net API:
- read_csv: local CSV okuma
- DatasetRegistry: veri seti registry tipi
"""

from .data import (
    read_csv,
    DatasetRegistry,
    register_dataset,
    load_registered_dataset,
    get_default_registry,
)

__all__ = [
    "read_csv",
    "DatasetRegistry",
    "register_dataset",
    "load_registered_dataset",
    "get_default_registry",
]
