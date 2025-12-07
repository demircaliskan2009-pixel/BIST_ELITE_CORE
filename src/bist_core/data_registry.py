"""
Uyumluluk katmanı.

Eski kodlar `bist_core.data_registry` import ediyorsa bozulmasın diye
her şeyi `bist_core.data.registry`'ye forward ediyoruz.
Yeni kod doğrudan `bist_core.data.registry` kullanmalı.
"""

from .data.registry import (
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
