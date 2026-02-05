"""FAZ101: Core API import stability — bist_core.core exports and __all__."""
from __future__ import annotations

import pytest


def test_faz101_import_bist_core_core_no_error() -> None:
    """import bist_core.core must work (no ImportError)."""
    import bist_core.core  # noqa: F401
    assert bist_core.core is not None


def test_faz101_core_all_includes_required() -> None:
    """core.__all__ must include DatasetRegistry, register_dataset, load_registered_dataset, get_default_registry."""
    import bist_core.core as core

    required = {"DatasetRegistry", "register_dataset", "load_registered_dataset", "get_default_registry"}
    core_all = set(core.__all__)
    missing = required - core_all
    assert not missing, f"core.__all__ missing: {sorted(missing)}"
