"""RiskGateEngine: fail-closed gate for execution (stage errors or policy invalid => deny)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def preflight_bist_rules_for_live(
    rulespack_dir: Optional[Path] = None,
    restrictions_path: Optional[Path] = None,
) -> Tuple[bool, List[str]]:
    """Preflight BIST rule data for live execution. Fail-closed when tick/bands/vbts missing. Returns (ok, errors)."""
    from bist_core.rules.validator import validate_rulespack
    return validate_rulespack(rulespack_dir=rulespack_dir, restrictions_path=restrictions_path)


def gate_order_rules(
    order: Dict[str, Any],
    rulespack: Dict[str, Any],
    ref_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Pre-execution order validation: tick, band, lot, notional. Fail-closed.
    Returns {ok: bool, errors: list, notes: list}. Deterministic: errors sorted.
    ref_price: used for band check; if None, use order.get("ref_price").
    """
    errors: List[str] = []
    notes: List[str] = []
    price = order.get("price")
    quantity = order.get("quantity")
    ref = ref_price if ref_price is not None else order.get("ref_price")

    if price is not None:
        try:
            p = float(price)
        except (TypeError, ValueError):
            errors.append("price_invalid")
        else:
            from bist_core.risk.rulespack import validate_price_tick, validate_price_band
            ok_tick, _ = validate_price_tick(rulespack, p)
            if not ok_tick:
                errors.append("tick_violation")
            if ref is not None:
                try:
                    ref_p = float(ref)
                except (TypeError, ValueError):
                    pass
                else:
                    market = order.get("market")
                    ok_band, _ = validate_price_band(rulespack, ref_p, p, market)
                    if not ok_band:
                        errors.append("band_violation")

    lot_size = rulespack.get("lot_size")
    if lot_size is not None and quantity is not None:
        try:
            q = int(quantity) if isinstance(quantity, (int, float)) and quantity == int(quantity) else float(quantity)
            lot = float(lot_size)
            if lot <= 0 or (q / lot) != int(q / lot):
                errors.append("lot_violation")
        except (TypeError, ValueError, ZeroDivisionError):
            errors.append("lot_violation")

    max_notional = rulespack.get("max_notional")
    if max_notional is not None and price is not None and quantity is not None:
        try:
            p = float(price)
            q = float(quantity)
            if p * q > float(max_notional):
                errors.append("notional_exceeded")
        except (TypeError, ValueError):
            errors.append("notional_exceeded")

    errors_sorted = sorted(errors)
    return {"ok": len(errors_sorted) == 0, "errors": errors_sorted, "notes": notes}


def gate_restrictions(
    orders_intent: Dict[str, Any],
    restrictions_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Restriction gate: delegate to restrictions.gate_restrictions."""
    from bist_core.risk.restrictions import gate_restrictions as _gate_restrictions
    return _gate_restrictions(orders_intent, restrictions_state)


def run_all(
    orders_intent: Dict[str, Any],
    stages: Dict[str, Any],
    *,
    policy_ruleset: Optional[Dict[str, Any]] = None,
    rulespack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    FAZ87: Run gate evaluation; return report {ok, blocked, errors, codes}.
    ok: allowed to execute. blocked: not allowed. errors: notes from engine. codes: sorted error codes (deterministic).
    """
    engine = RiskGateEngine()
    allowed, notes = engine.evaluate(
        orders_intent,
        policy_ruleset=policy_ruleset,
        stages=stages,
        rulespack=rulespack,
    )
    codes = sorted(notes) if notes else []
    return {
        "ok": allowed,
        "blocked": not allowed,
        "errors": list(notes),
        "codes": codes,
    }


class RiskGateEngine:
    """Evaluate whether orders_intent is allowed for execution. Fail-closed: default deny if any stage errors >0 or policy invalid."""

    def evaluate(
        self,
        orders_intent: Dict[str, Any],
        *,
        policy_ruleset: Optional[Dict[str, Any]] = None,
        stages: Dict[str, Any],
        rulespack: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, List[str]]:
        notes: List[str] = []
        if not isinstance(stages, dict):
            notes.append("blocked")
            return False, notes
        for name, stage in stages.items():
            if not isinstance(stage, dict):
                continue
            err = stage.get("errors", 0)
            if err is not None and int(err) > 0:
                notes.append("blocked")
                return False, notes
        if rulespack:
            from bist_core.risk.rulespack import validate_price_tick, validate_price_band
            actions = orders_intent.get("actions") or []
            for a in actions:
                if not isinstance(a, dict):
                    continue
                price = a.get("price")
                if price is None:
                    continue
                try:
                    p = float(price)
                except (TypeError, ValueError):
                    notes.append("rulespack_price_invalid")
                    return False, notes
                ok_tick, _ = validate_price_tick(rulespack, p)
                if not ok_tick:
                    notes.append("rulespack_tick_violation")
                    return False, notes
                ref = a.get("ref_price")
                if ref is not None:
                    try:
                        ref_p = float(ref)
                    except (TypeError, ValueError):
                        continue
                    market = a.get("market")
                    ok_band, _ = validate_price_band(rulespack, ref_p, p, market)
                    if not ok_band:
                        notes.append("rulespack_band_violation")
                        return False, notes
        if policy_ruleset is not None:
            try:
                from bist_core.policy.rules_engine import evaluate as policy_evaluate
                allowed, reasons = policy_evaluate(
                    policy_ruleset,
                    trading_context={"day": orders_intent.get("day", "")},
                )
                if not allowed:
                    notes.append("blocked")
                    notes.extend(reasons)
                    return False, notes
            except Exception:
                notes.append("blocked")
                return False, notes
        return True, notes
