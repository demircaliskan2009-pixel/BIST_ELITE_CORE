# ruff: noqa: E402
from __future__ import annotations

"""
:mod:`bist_core.core` – Dataset registry çekirdeği.

Faz-3 / Adım-1: Registry implementasyonu ve yardımcı fonksiyonlar.
"""

from .data_registry import (
    DatasetRegistry,
    get_default_registry,
    load_registered_dataset,
    register_dataset,
)

__all__ = [
    "DatasetRegistry",
    "register_dataset",
    "load_registered_dataset",
    "get_default_registry",
]
