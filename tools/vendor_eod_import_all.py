from __future__ import annotations

import argparse
import csv
from pathlib import Path
from datetime import date as _date

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    tr = str.maketrans({"ç":"c","ğ":"g","ı":"i","ö":"o","ş":"s","ü":"u"})
    s = s.translate(tr)
    s = s.replace(" ", "").replace("-", "").replace("_", "")
    return s

ALIASES = {
    "symbol": {"symbol","sembol","ticker","kod","code","hisse"},
    "date": {"date","tarih","day","gun"},
    "open": {"open","acilis","opening"},
    "high": {"high","yuksek","highest"},
    "low": {"low","dusuk","lowest"},
    "close": {"close","kapanis","last","settle"},
    "volume": {"volume","hacim","lot","adet","qty"},
    "turnover_tl": {"turnovertl","turnover","value","tutar","islemhacmi","tl"},
}

def _to_float(x):
    if x is None:
        return ""
    s = str(x).strip()
    if s == "":
        return ""
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1 else s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return ""

def _to_int(x):
    if x is None:
        return ""
    s = str(x).strip()
    if s == "":
        return ""
    s = s.replace(".", "").replace(",", ".")
    try:
        return int(float(s))
    except Exception:
        return ""

def _detect_delim(sample: str) -> str:
    if sample.count(";") > sample.count(","):
        return ";"
    if sample.count("\t") > sample.count(","):
        return "\t"
    return ","

def _map_headers(headers):
    mapped = {}
    for h in headers:
        n = _norm(h)
        for key, vals in ALIASES.items():
            if n in vals:
                mapped[key] = h
    return mapped

def _write_day(out_base: Path, day: str, rows: dict[str, dict]):
    day_dir = out_base / day
    day_dir.mkdir(parents=True, exist_ok=True)
    out_fp = day_dir / "snapshot.csv"
    syms = sorted(rows.keys())
    with out_fp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol","open","high","low","close","volume","turnover_tl"])
        w.writeheader()
        for s in syms:
            r = rows[s]
            w.writerow({
                "symbol": s,
                "open": r.get("open",""),
                "high": r.get("high",""),
                "low": r.get("low",""),
                "close": r.get("close",""),
                "volume": r.get("volume",""),
                "turnover_tl": r.get("turnover_tl",""),
            })
    return out_fp

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Vendor CSV (cok gun + cok sembol)")
    ap.add_argument("--out-base", default="data/eod/snapshots", help="snapshot base (YYYY-MM-DD/snapshot.csv)")
    ap.add_argument("--end-day", default="", help="YYYY-MM-DD (opsiyonel: bu gun ve oncesi)")
    args = ap.parse_args()

    in_fp = Path(args.input)
    out_base = Path(args.out_base)
    end_day = args.end_day.strip()
    end = _date.fromisoformat(end_day) if end_day else None

    txt = in_fp.read_text(encoding="utf-8", errors="replace")
    first = txt.splitlines()[0] if txt.splitlines() else ""
    delim = _detect_delim(first)

    by_day: dict[str, dict[str, dict]] = {}

    with in_fp.open("r", encoding="utf-8", errors="replace", newline="") as f:
        rdr = csv.DictReader(f, delimiter=delim)
        if not rdr.fieldnames:
            raise SystemExit("CSV header bulunamadi.")
        mapped = _map_headers(rdr.fieldnames)

        if "symbol" not in mapped:
            raise SystemExit(f"symbol kolonu bulunamadi. header={rdr.fieldnames}")
        if "date" not in mapped:
            raise SystemExit(f"date/tarih kolonu bulunamadi. header={rdr.fieldnames}")

        for r in rdr:
            sym = (r.get(mapped["symbol"]) or "").strip().upper()
            if not sym:
                continue

            d = (r.get(mapped["date"]) or "").strip()
            if not d:
                continue
            try:
                dd = _date.fromisoformat(d)
            except Exception:
                continue
            if end and dd > end:
                continue

            day = dd.isoformat()

            o = _to_float(r.get(mapped.get("open","")))
            h = _to_float(r.get(mapped.get("high","")))
            l = _to_float(r.get(mapped.get("low","")))
            c = _to_float(r.get(mapped.get("close","")))
            v = _to_int(r.get(mapped.get("volume","")))

            t = _to_int(r.get(mapped.get("turnover_tl","")))
            if t == "" and c != "" and v != "":
                try:
                    t = int(float(c) * int(v))
                except Exception:
                    t = ""

            by_day.setdefault(day, {})[sym] = {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
                "turnover_tl": t,
            }

    days = sorted(by_day.keys())
    if not days:
        raise SystemExit("Gecerli satir bulunamadi (day/symbol yok).")

    out_base.mkdir(parents=True, exist_ok=True)
    last_fp = None
    for day in days:
        last_fp = _write_day(out_base, day, by_day[day])

    print("WROTE_DAYS", len(days), "LAST", last_fp)

if __name__ == "__main__":
    main()
