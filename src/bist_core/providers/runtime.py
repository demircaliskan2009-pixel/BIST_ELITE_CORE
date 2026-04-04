from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .base import FailClosedError, ProviderConfigError
from .config import ProviderConfig
from .factory import build_disclosures_provider, build_market_data_provider


@dataclass(frozen=True)
class ProviderRuntimeStatus:
    market_data_provider: str
    disclosures_provider: str
    datastore_normalized_csv: str | None
    market_data_state: str
    disclosures_state: str
    latest_trading_day: str | None = None
    universe_count_on_latest_day: int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_runtime(
    env: dict[str, str] | None = None,
    must_exist: bool = False,
) -> ProviderRuntimeStatus:
    notes: list[str] = []

    try:
        cfg = ProviderConfig.from_env(env).validate(must_exist=must_exist)
    except ProviderConfigError as exc:
        return ProviderRuntimeStatus(
            market_data_provider=str((env or {}).get("BIST_MARKET_DATA_PROVIDER", "datastore_file")).lower(),
            disclosures_provider=str((env or {}).get("BIST_DISCLOSURES_PROVIDER", "none")).lower(),
            datastore_normalized_csv=(env or {}).get("BIST_DATASTORE_NORMALIZED_CSV"),
            market_data_state="config_error",
            disclosures_state="config_error",
            notes=[str(exc)],
        )

    market_state = "unknown"
    disclosures_state = "unknown"
    latest_trading_day: str | None = None
    universe_count: int | None = None

    market_provider = build_market_data_provider(cfg)

    if cfg.market_data_provider == "none":
        market_state = "disabled"
    else:
        try:
            latest_trading_day = market_provider.latest_trading_day()
            if hasattr(market_provider, "universe_on_day") and latest_trading_day:
                universe = getattr(market_provider, "universe_on_day")(latest_trading_day)
                universe_count = len(universe)
            market_state = "ready"
        except FailClosedError as exc:
            market_state = "deferred" if cfg.market_data_provider != "datastore_file" else "fail_closed"
            notes.append(str(exc))

    disclosure_provider = build_disclosures_provider(cfg)
    if cfg.disclosures_provider == "none":
        disclosures_state = "disabled"
    else:
        try:
            disclosure_provider.recent(limit=1)
            disclosures_state = "ready"
        except FailClosedError as exc:
            disclosures_state = "deferred"
            notes.append(str(exc))

    return ProviderRuntimeStatus(
        market_data_provider=cfg.market_data_provider,
        disclosures_provider=cfg.disclosures_provider,
        datastore_normalized_csv=cfg.datastore_normalized_csv,
        market_data_state=market_state,
        disclosures_state=disclosures_state,
        latest_trading_day=latest_trading_day,
        universe_count_on_latest_day=universe_count,
        notes=notes,
    )
