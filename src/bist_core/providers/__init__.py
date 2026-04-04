from __future__ import annotations

import importlib
import re
from pathlib import Path

from .base import FailClosedError, ProviderConfigError, ProviderDescriptor, ProviderError
from .config import ProviderConfig
from .factory import build_disclosures_provider, build_market_data_provider

__all__ = [
    "FailClosedError",
    "ProviderConfig",
    "ProviderConfigError",
    "ProviderDescriptor",
    "ProviderError",
    "build_disclosures_provider",
    "build_market_data_provider",
]

_PKG_DIR = Path(__file__).resolve().parent


def _discover_legacy_symbol(symbol: str) -> None:
    """
    Backward-compat layer:
    older code imports LocalCSVProvider / VendorAPIProvider / VendorAPIConfig
    from bist_core.providers directly. Keep that working while new provider
    architecture coexists.
    """
    candidates: list[str] = []

    for py in _PKG_DIR.glob("*.py"):
        if py.name == "__init__.py":
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue

        has_symbol = (
            re.search(rf"(?m)^class\s+{re.escape(symbol)}\b", text) is not None
            or re.search(rf"(?m)^{re.escape(symbol)}\s*=", text) is not None
            or symbol in text
        )
        if has_symbol:
            candidates.append(py.stem)

    for stem in candidates:
        try:
            module = importlib.import_module(f"{__name__}.{stem}")
        except Exception:
            continue
        if hasattr(module, symbol):
            globals()[symbol] = getattr(module, symbol)
            if symbol not in __all__:
                __all__.append(symbol)
            return


for _legacy_name in ["LocalCSVProvider", "VendorAPIProvider", "VendorAPIConfig"]:
    _discover_legacy_symbol(_legacy_name)
