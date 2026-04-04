from __future__ import annotations

import datetime as dt
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
import csv
import math

from .probe import probe_file, write_probe_report


class IdealFormatUnverifiedError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedBar:
    symbol: str
    timeframe: str
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def _u32le(b: bytes) -> int:
    return struct.unpack("<I", b)[0]


def _f32le(b: bytes) -> float:
    return struct.unpack("<f", b)[0]


def _symbol_from_filename(path: str | Path) -> str:
    name = Path(path).name
    if "'" in name:
        part = name.split("'")[-1]
    else:
        part = Path(path).stem
    return part.split(".")[0].upper()


def _timeframe_from_filename(path: str | Path) -> str:
    suffix = Path(path).suffix.lstrip(".").upper()
    return suffix or "G"


def _parse_dt(raw: str) -> str:
    raw = raw.strip()
    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%d.%m.%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y%m%d",
        "%Y%m%d %H:%M",
        "%Y%m%d%H%M",
    ]
    for fmt in patterns:
        try:
            dtv = dt.datetime.strptime(raw, fmt)
            if dtv.hour == 0 and dtv.minute == 0 and len(raw) <= 10:
                return dtv.strftime("%Y-%m-%d")
            return dtv.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    raise ValueError(f"Desteklenmeyen tarih formatı: {raw!r}")


def _pick_delimiter(sample: str) -> str | None:
    candidates = [";", "\t", ",", "|"]
    best = None
    best_score = -1
    lines = [ln for ln in sample.splitlines() if ln.strip()][:50]
    for delim in candidates:
        counts = [ln.count(delim) for ln in lines]
        score = sum(c > 0 for c in counts)
        if score > best_score:
            best = delim
            best_score = score
    return best if best_score > 0 else None


def _header_map(fieldnames: list[str]) -> dict[str, str]:
    norm = {f.lower().strip(): f for f in fieldnames}
    aliases = {
        "date": ["date", "tarih", "datetime", "zaman", "timestamp"],
        "open": ["open", "acilis", "açılış"],
        "high": ["high", "yuksek", "yüksek"],
        "low": ["low", "dusuk", "düşük"],
        "close": ["close", "kapanis", "kapanış"],
        "volume": ["volume", "hacim", "vol"],
    }
    out: dict[str, str] = {}
    for target, names in aliases.items():
        for n in names:
            if n in norm:
                out[target] = norm[n]
                break
    missing = [k for k in ("date", "open", "high", "low", "close", "volume") if k not in out]
    if missing:
        raise IdealFormatUnverifiedError(
            "Text parse mümkün ama zorunlu kolonlar eksik: " + ", ".join(missing)
        )
    return out


def _safe_date_from_ordinal(n: int):
    try:
        return dt.date.fromordinal(n)
    except Exception:
        return None


def _infer_binary_date_offset(raw_dates: list[int], anchor_date: dt.date) -> int:
    candidates = []
    for back in range(0, 120):
        target_last = anchor_date - dt.timedelta(days=back)
        offset = raw_dates[-1] - target_last.toordinal()
        mapped = [x - offset for x in raw_dates]
        if min(mapped) < 1:
            continue

        dates = []
        ok = True
        for m in mapped:
            d = _safe_date_from_ordinal(m)
            if d is None:
                ok = False
                break
            dates.append(d)
        if not ok:
            continue

        if len(dates) < 200:
            continue

        span_days = (dates[-1] - dates[0]).days
        if span_days < 365:
            continue

        diffs = [(b - a).days for a, b in zip(dates, dates[1:])]
        monotonic_ratio = sum(d >= 0 for d in diffs) / max(1, len(diffs))
        weekday_ratio = sum(d.weekday() < 5 for d in dates) / len(dates)
        gap_ratio = sum(d in (1, 3) for d in diffs) / max(1, len(diffs))

        last_weekday_bonus = 0.20 if dates[-1].weekday() < 5 else -0.35
        first_weekday_bonus = 0.02 if dates[0].weekday() < 5 else -0.02
        score = (
            weekday_ratio * 0.38
            + gap_ratio * 0.38
            + monotonic_ratio * 0.10
            + last_weekday_bonus
            + first_weekday_bonus
            - back * 0.0005
        )

        candidates.append(
            {
                "score": score,
                "offset": offset,
                "target_last": target_last,
                "mapped_first": dates[0],
                "mapped_last": dates[-1],
                "weekday_ratio": weekday_ratio,
                "gap_ratio": gap_ratio,
                "monotonic_ratio": monotonic_ratio,
            }
        )

    if not candidates:
        raise IdealFormatUnverifiedError("binary layout doğrulanamadı: tarih ofseti çıkarılamadı.")

    candidates.sort(
        key=lambda x: (
            x["mapped_last"].weekday() < 5,
            round(x["score"], 6),
            x["target_last"].toordinal(),
        ),
        reverse=True,
    )
    return int(candidates[0]["offset"])


class IdealGParser:
    def _parse_text(self, p: Path, probe_out_dir: str | Path | None = None) -> list[NormalizedBar]:
        raw = p.read_bytes()
        text = raw.decode("latin-1", errors="ignore")
        delim = _pick_delimiter(text[:10000])
        if not delim:
            report_path = None
            if probe_out_dir is not None:
                report_path = write_probe_report(p, probe_out_dir)
            raise IdealFormatUnverifiedError(
                f"Delimiter tespit edilemedi. Report={report_path or 'yok'}"
            )

        reader = csv.DictReader(text.splitlines(), delimiter=delim)
        if not reader.fieldnames:
            raise IdealFormatUnverifiedError("Header satırı okunamadı.")
        hmap = _header_map(reader.fieldnames)
        symbol = _symbol_from_filename(p)
        timeframe = _timeframe_from_filename(p)

        bars: list[NormalizedBar] = []
        for row in reader:
            if not any((v or "").strip() for v in row.values()):
                continue
            bars.append(
                NormalizedBar(
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=_parse_dt(row[hmap["date"]]),
                    open=float(str(row[hmap["open"]]).replace(",", ".")),
                    high=float(str(row[hmap["high"]]).replace(",", ".")),
                    low=float(str(row[hmap["low"]]).replace(",", ".")),
                    close=float(str(row[hmap["close"]]).replace(",", ".")),
                    volume=float(str(row[hmap["volume"]]).replace(",", ".")),
                )
            )

        if not bars:
            raise IdealFormatUnverifiedError("Hiç text bar parse edilemedi.")
        return bars

    def _parse_binary_g(
        self,
        p: Path,
        probe_out_dir: str | Path | None = None,
        last_date: dt.date | None = None,
    ) -> list[NormalizedBar]:
        data = p.read_bytes()
        if len(data) % 32 != 0:
            report_path = None
            if probe_out_dir is not None:
                report_path = write_probe_report(p, probe_out_dir)
            raise IdealFormatUnverifiedError(
                f"Binary .G için 32-byte record bekleniyordu ama dosya boyutu uymuyor. "
                f"len={len(data)} report={report_path or 'yok'}"
            )

        symbol = _symbol_from_filename(p)
        timeframe = _timeframe_from_filename(p)
        records = [data[i:i+32] for i in range(0, len(data), 32)]
        if not records:
            raise IdealFormatUnverifiedError("binary layout doğrulanamadı: boş kayıt dizisi")
        raw_dates = [_u32le(rec[0:4]) for rec in records]

        anchor = last_date or dt.datetime.fromtimestamp(p.stat().st_mtime).date()
        if last_date:

            offset = raw_dates[-1] - anchor.toordinal()

        else:

            try:

                offset = _infer_binary_date_offset(raw_dates, anchor)

            except IdealFormatUnverifiedError as exc:

                raise IdealFormatUnverifiedError(

                    f"binary layout doğrulanamadı: {exc}"

                ) from exc

        bars: list[NormalizedBar] = []
        skipped = 0

        for rec in records:
            date_code = _u32le(rec[0:4])
            o = _f32le(rec[4:8])
            h = _f32le(rec[8:12])
            l = _f32le(rec[12:16])
            c = _f32le(rec[16:20])
            v = _f32le(rec[20:24])
            _turnover = _f32le(rec[24:28])
            _reserved = _u32le(rec[28:32])

            if not all(math.isfinite(x) for x in (o, h, l, c, v)):
                skipped += 1
                continue

            if min(o, h, l, c) <= 0:
                skipped += 1
                continue

            if h < max(o, l, c) or l > min(o, h, c):
                skipped += 1
                continue

            mapped = date_code - offset
            d = _safe_date_from_ordinal(mapped)
            if d is None:
                skipped += 1
                continue

            bars.append(
                NormalizedBar(
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=d.isoformat(),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(v),
                )
            )

        if not bars:
            raise IdealFormatUnverifiedError(
                "Binary .G decode sonucunda geçerli OHLC bar çıkmadı."
            )

        bars.sort(key=lambda x: x.ts)

        if len(bars) >= 2:
            bad_order = sum(1 for a, b in zip(bars, bars[1:]) if a.ts > b.ts)
            if bad_order > 0:
                raise IdealFormatUnverifiedError("Decoded bar tarih sırası bozuk.")

        weekend_count = 0
        for b in bars:
            y, m, d = map(int, b.ts.split("-"))
            if dt.date(y, m, d).weekday() >= 5:
                weekend_count += 1
        weekend_ratio = weekend_count / max(1, len(bars))
        import os as _os
        _max_weekend = float(_os.environ.get("IDEAL_MAX_WEEKEND_RATIO", "0.35"))
        if weekend_ratio > _max_weekend:
            raise IdealFormatUnverifiedError(
                f"binary layout doğrulanamadı: weekend_ratio_too_high={weekend_ratio:.4f}"
            )

        return bars

    def parse(
        self,
        path: str | Path,
        probe_out_dir: str | Path | None = None,
        last_date: dt.date | None = None,
    ) -> list[NormalizedBar]:
        p = Path(path)
        probe = probe_file(p)

        if probe["likely_text_or_delimited"]:
            return self._parse_text(p, probe_out_dir=probe_out_dir)

        if _timeframe_from_filename(p) == "G":
            return self._parse_binary_g(p, probe_out_dir=probe_out_dir, last_date=last_date)

        report_path = None
        if probe_out_dir is not None:
            report_path = write_probe_report(p, probe_out_dir)
        raise IdealFormatUnverifiedError(
            f"Binary format sadece .G için doğrulandı; bu timeframe henüz desteklenmiyor. "
            f"Report={report_path or 'yok'}"
        )

    @staticmethod
    def to_rows(bars: Iterable[NormalizedBar]) -> list[dict]:
        return [asdict(b) for b in bars]




