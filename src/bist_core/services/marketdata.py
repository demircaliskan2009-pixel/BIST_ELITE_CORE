
from pathlib import Path
from typing import List, Dict
from bist_core.providers import LocalCSVProvider, VendorAPIProvider, VendorAPIConfig
from bist_core import config

class MarketData:
    """EOD verisini provider üstünden okur."""
    def __init__(self, base: Path = Path("data/eod/snapshots")) -> None:
        if config.SOURCES["vendor_api"]["enabled"]:
            vendor_cfg = config.SOURCES["vendor_api"]
            cfg = VendorAPIConfig(
                eod_endpoint=vendor_cfg["eod_endpoint"],
                kap_endpoint=vendor_cfg.get("kap_endpoint"),
                api_key=vendor_cfg["auth"]["api_key"],
                timeout=vendor_cfg.get("timeout", 5.0)
            )
            self._prov = VendorAPIProvider(cfg=cfg)
        else:
            self._prov = LocalCSVProvider(base)

    def symbols(self, day: str) -> List[str]:
        return self._prov.symbols(day)

    def close_map(self, day: str) -> Dict[str, float]:
        return self._prov.close_map(day)

    def has_ohlcv(self, day: str) -> bool:
        if hasattr(self._prov, "has_ohlcv"):
            return self._prov.has_ohlcv(day)
        return False

    def ohlcv_map(self, day: str) -> Dict[str, Dict[str, float | int]]:
        if not hasattr(self._prov, "ohlcv_map"):
            raise ValueError("OHLCV not supported by provider")
        return self._prov.ohlcv_map(day)
