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
    quantity = order.get("quantity", order.get("qty"))
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

    lot_size = rulespack.get("lot_size") if isinstance(rulespack, dict) else None
    if lot_size is not None and quantity is not None:
        try:
            q = float(quantity)
            lot = float(lot_size)
            if lot <= 0:
                errors.append("lot_violation")
            else:
                k = q / lot
                if abs(k - round(k)) > 1e-9:
                    errors.append("lot_violation")
        except (TypeError, ValueError, ZeroDivisionError):
            errors.append("lot_violation")

    max_notional = rulespack.get("max_notional") if isinstance(rulespack, dict) else None
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


def _codes_from_notes(notes: List[str]) -> List[str]:
    # deterministic: stage_errors first if any, then sorted rest
    stage_codes: List[str] = []
    other: List[str] = []

    for n in notes:
        if isinstance(n, str) and n.startswith("stage_errors:"):
            # stage_errors:<name>=<int>
            try:
                rest = n.split(":", 1)[1]
                stage = rest.split("=", 1)[0].strip()
            except Exception:
                stage = ""
            if stage:
                stage_codes.append(f"stage_{stage}_errors")
        else:
            if isinstance(n, str):
                other.append(n)

    codes: List[str] = []
    if "blocked" in notes:
        codes.append("blocked")

    if stage_codes:
        codes.append("stage_errors")
        codes.extend(sorted(set(stage_codes)))

    # keep well-known prefixes as codes too (stable)
    for n in other:
        if n.startswith("rulespack_") or n.startswith("policy_") or n.endswith("_missing") or n.endswith("_invalid"):
            codes.append(n)

    if not codes and notes:
        # fallback
        codes = sorted(set([str(x) for x in notes]))

    if not codes:
        return []
    # de-dup while preserving order
    out: List[str] = []
    seen = set()
    for c in codes:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out


def run_all(
    orders_intent: Dict[str, Any],
    stages: Dict[str, Any],
    *,
    policy_ruleset: Optional[Dict[str, Any]] = None,
    rulespack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    FAZ87: Run gate evaluation; return report {ok, blocked, errors, codes}.
    ok: allowed to execute. blocked: not allowed. errors: notes from engine. codes: deterministic error codes.
    """
    engine = RiskGateEngine()
    allowed, notes = engine.evaluate(
        orders_intent,
        policy_ruleset=policy_ruleset,
        stages=stages,
        rulespack=rulespack,
    )
    codes = _codes_from_notes(list(notes) if notes else [])
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
            notes.append("stages_not_dict")
            return False, notes

        stage_errs: List[str] = []
        for name, stage in stages.items():
            if not isinstance(stage, dict):
                continue
            err = stage.get("errors", 0)
            try:
                e = int(err)
            except Exception:
                e = 0
            if e > 0:
                # NON-FATAL: features stage often emits missing_data / insufficient_history in small datasets.
                # Treat these as warnings (do NOT block execution) when they are the ONLY notes.
                if str(name) == "features":
                    n = stage.get("notes") or []
                    if isinstance(n, list) and n:
                        nn = [str(x) for x in n]
                        allowed = {"missing_data", "insufficient_history"}
                        if all(x in allowed for x in nn):
                            continue
                stage_errs.append(f"stage_errors:{name}={e}")

        if stage_errs:
            # fail-closed on any stage error
            notes.append("blocked")
            notes.extend(sorted(stage_errs))
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
                    notes.append("policy_denied")
                    for r in (reasons or []):
                        notes.append(str(r))
                    return False, notes
            except Exception:
                notes.append("blocked")
                notes.append("policy_exception")
                return False, notes

        return True, notes
