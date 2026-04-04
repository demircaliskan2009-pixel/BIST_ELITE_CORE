# ruff: noqa: E402
from __future__ import annotations

"""
:mod:`bist_core.data` – veri okuma + registry için yüksek seviye API.

Şimdilik:
- read_csv  : local CSV'den DataFrame okur
- DatasetRegistry ve diğerleri : core'dan re-export edilir
"""

from .ideal_binary_parser import (
    OHLCVRecord,
    decode_ideal_binary_bytes,
    parse_ideal_binary,
    parse_ideal_binary_bytes,
    validate_numpy_ohlc_or_raise,
    validate_records,
)
from .ingest import read_csv
from .ideal_dataset import load_ideal_dataset, resolve_ideal_symbol_path
from .ideal_timestamp_codec import decode_ideal_struct_timestamp
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
    "OHLCVRecord",
    "decode_ideal_binary_bytes",
    "parse_ideal_binary",
    "parse_ideal_binary_bytes",
    "validate_numpy_ohlc_or_raise",
    "validate_records",
    "load_ideal_dataset",
    "resolve_ideal_symbol_path",
    "decode_ideal_struct_timestamp",
]
