from __future__ import annotations

"""
:mod:`bist_core.core` – Dataset registry çekirdeği.

Faz-3 / Adım-1: Registry implementasyonu ve yardımcı fonksiyonlar.
"""

from .data_registry import (
    DatasetRegistry,
    register_dataset,
    load_registered_dataset,
    get_default_registry,
)

__all__ = [
    "DatasetRegistry",
    "register_dataset",
    "load_registered_dataset",
    "get_default_registry",
]

