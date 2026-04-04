from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Union
import requests

from bist_core.env import network_allowed


@dataclass
class VendorAPIConfig:
    """Vendor API konfigürasyonu."""

    eod_endpoint: str
    kap_endpoint: Optional[str]
    api_key: Optional[str]
    timeout: float = 5.0


class VendorAPIProvider:
    """
    Vendor API'den EOD verisini ve KAP haberlerini çeken provider.
    LocalCSVProvider ile uyumlu arayüze sahiptir.
    """

    def __init__(
        self,
        cfg: Optional[VendorAPIConfig] = None,
        session: Optional[requests.Session] = None,
        # Backward compatibility için eski parametreler
        api_key: Optional[str] = None,
        eod_url: Optional[str] = None,
        kap_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """
        Args:
            cfg: Vendor API konfigürasyonu (tercih edilen yöntem)
            session: Opsiyonel requests.Session (test için override edilebilir)
            api_key: Eski imza için API key (deprecated, cfg kullanın)
            eod_url: Eski imza için EOD endpoint (deprecated, cfg kullanın)
            kap_url: Eski imza için KAP endpoint (deprecated, cfg kullanın)
            timeout: Eski imza için timeout (deprecated, cfg kullanın)
        """
        # Backward compatibility: eski parametreler varsa cfg oluştur
        if cfg is None:
            if eod_url is None:
                raise ValueError("Either cfg or eod_url must be provided")
            cfg = VendorAPIConfig(
                eod_endpoint=eod_url,
                kap_endpoint=kap_url,
                api_key=api_key,
                timeout=timeout if timeout is not None else 5.0,
            )

        self._cfg = cfg
        self._session = session if session is not None else requests.Session()

        # API key varsa header'a ekle
        if cfg.api_key:
            self._session.headers.update({"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"})

    def _request(self, url: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        """
        HTTP GET isteği yapar ve JSON yanıtını döndürür.

        Args:
            url: İstek yapılacak URL
            params: Query parametreleri

        Returns:
            JSON decode edilmiş yanıt

        Raises:
            RuntimeError: İstek başarısız olursa veya network disabled
        """
        if not network_allowed():
            raise RuntimeError("NETWORK_DISABLED: set BIST_CORE_ALLOW_NETWORK=1")
        try:
            response = self._session.get(url, params=params, timeout=self._cfg.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"VendorAPIProvider request failed: {e}")

    def _date_param(self, day: Union[date, str]) -> str:
        """
        date objesini veya string'i API'nin beklediği string formatına çevirir.

        Args:
            day: Tarih objesi veya YYYY-MM-DD formatında string

        Returns:
            YYYY-MM-DD formatında string
        """
        if isinstance(day, str):
            return day
        return day.isoformat()

    def symbols(self, day: Union[date, str]) -> List[str]:
        """
        Belirtilen tarih için sembol listesini API'den alır.

        Args:
            day: Tarih

        Returns:
            Sıralı sembol listesi
        """
        date_str = self._date_param(day)
        data = self._request(self._cfg.eod_endpoint, params={"date": date_str})

        # API response formatına göre esnek parsing
        symbols: List[str] = []

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    sym = item.get("symbol")
                    if sym:
                        symbols.append(str(sym))
                else:
                    symbols.append(str(item))
        elif isinstance(data, dict):
            if "symbols" in data:
                symbols = [str(s) for s in data["symbols"]]
            elif "data" in data:
                for item in data["data"]:
                    if isinstance(item, dict):
                        sym = item.get("symbol")
                        if sym:
                            symbols.append(str(sym))
                    else:
                        symbols.append(str(item))

        return sorted(symbols)

    def close_map(self, day: Union[date, str]) -> Dict[str, float]:
        """
        Belirtilen tarih için sembol->close fiyat mapping'ini API'den alır.

        Args:
            day: Tarih

        Returns:
            {symbol: close_price} sözlüğü
        """
        date_str = self._date_param(day)
        data = self._request(self._cfg.eod_endpoint, params={"date": date_str})

        out: Dict[str, float] = {}

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    sym = item.get("symbol")
                    close = item.get("close")
                    if sym:
                        out[str(sym)] = float(close) if close is not None else float("nan")
        elif isinstance(data, dict):
            if "data" in data:
                for item in data["data"]:
                    if isinstance(item, dict):
                        sym = item.get("symbol")
                        close = item.get("close")
                        if sym:
                            out[str(sym)] = float(close) if close is not None else float("nan")

        return out

    def kap_events(self, day: Union[date, str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Belirtilen tarih için KAP haberlerini API'den alır.

        Args:
            day: Tarih

        Returns:
            {symbol: [event_dict, ...]} sözlüğü
        """
        if not self._cfg.kap_endpoint:
            return {}

        date_str = self._date_param(day)
        data = self._request(self._cfg.kap_endpoint, params={"date": date_str})

        # KAP event'lerini sembole göre grupla
        events_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    sym = item.get("symbol") or item.get("ticker")
                    if sym:
                        sym_str = str(sym)
                        event_dict = {"raw": item, "headline": item.get("headline") or item.get("title") or ""}
                        if sym_str not in events_by_symbol:
                            events_by_symbol[sym_str] = []
                        events_by_symbol[sym_str].append(event_dict)
        elif isinstance(data, dict):
            if "data" in data:
                for item in data["data"]:
                    if isinstance(item, dict):
                        sym = item.get("symbol") or item.get("ticker")
                        if sym:
                            sym_str = str(sym)
                            event_dict = {"raw": item, "headline": item.get("headline") or item.get("title") or ""}
                            if sym_str not in events_by_symbol:
                                events_by_symbol[sym_str] = []
                            events_by_symbol[sym_str].append(event_dict)

        return events_by_symbol
