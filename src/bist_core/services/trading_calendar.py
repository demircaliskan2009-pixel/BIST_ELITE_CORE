from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_calendar_file(calendar_file: Path | None) -> Dict[str, Any]:
    if calendar_file is None:
        return {"holidays": set(), "trading_days": None, "errors": [], "path": ""}
    if not calendar_file.exists():
        return {
            "holidays": set(),
            "trading_days": None,
            "errors": ["CalendarMissing"],
            "path": str(calendar_file),
        }
    try:
        payload = json.loads(calendar_file.read_text(encoding="utf-8"))
    except Exception:
        return {
            "holidays": set(),
            "trading_days": None,
            "errors": ["CalendarParseError"],
            "path": str(calendar_file),
        }
    holidays = set(payload.get("holidays", []))
    trading_days = payload.get("trading_days")
    if trading_days is not None:
        trading_days = set(trading_days)
    return {
        "holidays": holidays,
        "trading_days": trading_days,
        "errors": [],
        "path": str(calendar_file),
    }


def is_trading_day(day: str, calendar_file: Path | None = None) -> Tuple[bool, str, List[str], str]:
    errors: List[str] = []
    try:
        parsed = date.fromisoformat(day)
    except Exception:
        return False, "invalid_day", ["DayParseError"], ""

    config = load_calendar_file(calendar_file)
    errors.extend(config["errors"])
    if errors:
        return False, "calendar_error", errors, config.get("path", "")

    if day in config["holidays"]:
        return False, "holiday", [], config.get("path", "")

    trading_days = config["trading_days"]
    if trading_days is not None:
        return (day in trading_days), "trading_days_override", [], config.get("path", "")

    if parsed.weekday() >= 5:
        return False, "weekend", [], config.get("path", "")
    return True, "weekday", [], config.get("path", "")


def gate_day(day: str, calendar_file: Path | None = None) -> Dict[str, Any]:
    ok, reason, errors, path = is_trading_day(day, calendar_file)
    notes = [reason]
    if not ok and not errors:
        errors = ["NotTradingDay"]
    return {"day": day, "ok": ok, "errors": errors, "notes": notes, "path": path}
