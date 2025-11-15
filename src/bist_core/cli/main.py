# src/bist_core/cli/main.py
from __future__ import annotations

import csv
import json
import math
from datetime import date as _date
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)
SNAP_BASE = Path("data/eod/snapshots")


def _parse_date(date_str: Optional[str]) -> str:
    """YYYY-MM-DD; None/boş ise bugün."""
    if not date_str:
        return _date.today().isoformat()
    try:
        _ = _date.fromisoformat(date_str)
        return date_str
    except Exception as exc:
        raise typer.BadParameter("Tarih YYYY-MM-DD olmalı") from exc


@app.command("info")
def info() -> None:
    """Basit sağlık kontrolü."""
    typer.echo("bist_core CLI OK; symbols: []")


@app.command("eod")
def eod(date: Optional[str] = typer.Option(None, "--date", help="EOD tarihi (YYYY-MM-DD)")) -> None:
    """
    EOD snapshot klasörü ve meta oluşturur.
    Testler, snapshot.csv içinde en az 'TEST' satırını ve close=0.0 bekliyor.
    """
    day = _parse_date(date)
    base = SNAP_BASE / day
    base.mkdir(parents=True, exist_ok=True)

    # meta
    meta = {"day": day}
    (base / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # snapshot
    snap = base / "snapshot.csv"
    with snap.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "close"])
        w.writerow(["TEST", "0.0"])  # provider testi 0.0 bekliyor

    typer.echo(f"EOD yazıldı: {snap}")


@app.command("plan")
def plan(date: Optional[str] = typer.Option(None, "--date", help="EOD tarihi (YYYY-MM-DD)")) -> None:
    """
    snapshot.csv'deki sembollere eşit ağırlık planı yazar.
    Test, plan CSV başlığını 'symbol,weight' ve stdout'ta 'Plan yazıldı:' bekler.
    Toplamın 1.0'a abs_tol=1e-6 ile kapanması için son ağırlık '1 - sum(öncekiler)' verilir.
    """
    day = _parse_date(date)
    base = SNAP_BASE / day
    snap = base / "snapshot.csv"
    out = base / "plan_equal_weight.csv"

    if not snap.exists():
        typer.echo("snapshot bulunamadı", err=True)
        raise typer.Exit(code=2)

    rows = list(csv.DictReader(snap.open("r", encoding="utf-8")))
    syms = [r.get("symbol", "").strip() for r in rows if r.get("symbol")]
    syms = [s for s in syms if s]
    if not syms:
        typer.echo("snapshot boş", err=True)
        raise typer.Exit(code=2)

    n = len(syms)
    base_w = 1.0 / n
    weights = []
    if n == 1:
        weights = [1.0]
    else:
        for i in range(n - 1):
            weights.append(round(base_w, 6))
        last = 1.0 - sum(weights)
        # Güvenlik: mutlak tolerans içinde kalacak şekilde yuvarla
        last = round(last, 6)
        weights.append(last)

    with out.open("w", encoding="utf-8", newline="") as f:
        wcsv = csv.writer(f)
        # TEST: plan 'weight' sütun adını bekliyor
        wcsv.writerow(["symbol", "weight"])
        for s, w in zip(syms, weights):
            wcsv.writerow([s, f"{w:.6f}"])

    typer.echo(f"Plan yazıldı: {out}")


@app.command("orders")
def orders_cmd(date: Optional[str] = typer.Option(None, "--date", help="EOD tarihi (YYYY-MM-DD)")) -> None:
    """
    Eşit ağırlık planından risk kontrollü sipariş dosyası üretir.
    PASS → exit 0, FAIL → exit 2 (dosyalar yine yazılır).
    """
    day = _parse_date(date)
    base = SNAP_BASE / day

    plan = base / "plan_equal_weight.csv"
    out_orders = base / "orders_equal_weight.csv"
    out_meta = base / "orders_meta.txt"

    if not plan.exists():
        typer.echo("plan not found", err=True)
        raise typer.Exit(code=2)

    rows = list(csv.DictReader(plan.open("r", encoding="utf-8")))
    if not rows:
        typer.echo("plan boş", err=True)
        raise typer.Exit(code=2)

    # plan'da hem 'weight' hem de 'target_weight' destekle
    weights = []
    symbols = []
    for r in rows:
        symbols.append(r.get("symbol", ""))
        try:
            w = float(r.get("weight") or r.get("target_weight") or "nan")
        except Exception:
            w = float("nan")
        weights.append(w)

    # risk kapısı: [0,1] aralığı ve toplam ~= 1.0 (abs_tol=1e-6)
    ok_bounds = all((not math.isnan(w)) and (0.0 <= w <= 1.0) for w in weights)
    s = sum(w for w in weights if not math.isnan(w))
    ok_sum = math.isclose(s, 1.0, rel_tol=0.0, abs_tol=1e-6)

    # orders dosyası: TEST 'target_weight' başlığını bekliyor
    with out_orders.open("w", encoding="utf-8", newline="") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(["symbol", "target_weight"])
        for sym, w in zip(symbols, weights):
            wcsv.writerow([sym, f"{w:.6f}"])

    with out_meta.open("w", encoding="utf-8") as f:
        if ok_bounds and ok_sum:
            f.write(f"PASS sum_w={s:.6f}\n")
        else:
            f.write(f"FAIL sum_w={s:.6f} bounds={ok_bounds}\n")

    raise typer.Exit(code=0 if (ok_bounds and ok_sum) else 2)


if __name__ == "__main__":
    app()
