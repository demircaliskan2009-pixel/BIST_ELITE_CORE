
from pathlib import Path
from typing import List, Dict
from bist_core.providers import LocalCSVProvider

class MarketData:
    """EOD verisini provider üstünden okur."""
    def __init__(self, base: Path = Path("data/eod/snapshots")) -> None:
        self._prov = LocalCSVProvider(base)

    def symbols(self, day: str) -> List[str]:
        return self._prov.symbols(day)

    def close_map(self, day: str) -> Dict[str, float]:
        return self._prov.close_map(day)
