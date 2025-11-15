from __future__ import annotations

from pathlib import Path
from typing import Optional, Annotated
import datetime as dt
import json
import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)

@app.command()
def info() -> None:
    """Basit sağlık kontrolü. Test 'symbols:' ifadesini arar."""
    typer.echo("bist_core CLI OK\nsymbols: []")

def _parse_date(date_str: Optional[str]) -> str:
    """--date için YYYY-MM-DD doğrulaması; boşsa bugün."""
    if not date_str:
        return dt.date.today().isoformat()
    try:
        d = dt.date.fromisoformat(date_str)
    except ValueError as exc:
        raise typer.BadParameter("Tarih YYYY-MM-DD olmalı") from exc
    return d.isoformat()

@app.command()
def eod(
    date: Annotated[
        Optional[str],
        typer.Option("--date", help="EOD tarihi (YYYY-MM-DD). Opsiyonel.")
    ] = None
) -> None:
    """
    data/eod/snapshots/<YYYY-MM-DD> altında bir anlık görüntü (snapshot)
    klasörü ve basit bir meta dosyası oluşturur.
    """
    day = _parse_date(date)
    target = Path.cwd() / "data" / "eod" / "snapshots" / day
    target.mkdir(parents=True, exist_ok=True)
    (target / "meta.json").write_text(json.dumps({"day": day}), encoding="utf-8")
    (target / "snapshot.csv").write_text("symbol,close\nTEST,0\n", encoding="utf-8")
    typer.echo(f"EOD snapshot created at {target}")

def main() -> None:
    app()

if __name__ == "__main__":
    main()
