from __future__ import annotations

import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Optional

REC_SIZE = 32


@dataclass(frozen=True)
class IdealIntradayRecord:
    symbol: str
    period: str
    record_index: int
    ts_code_raw: int
    ts_iso: str | None
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover_tl: float
    reserved_u32: int
    source_file: str


def _u32le(b: bytes) -> int:
    return struct.unpack("<I", b)[0]


def _f32le(b: bytes) -> float:
    return struct.unpack("<f", b)[0]


def infer_symbol_from_filename(path: str | Path) -> str:
    name = Path(path).name
    if "'" in name:
        name = name.split("'")[-1]
    return name.split(".")[0].upper()


def infer_period_from_filename(path: str | Path) -> str:
    return Path(path).suffix.lstrip(".").upper()


def decode_ts_code_raw(ts_code_raw: int, period: str) -> str | None:
    s = str(int(ts_code_raw))
    period = str(period).upper()

    # günlük örnek: 778060 -> doğrudan çözülemiyor, şimdilik raw bırak
    if period == "G":
        return None

    # intraday örnekler:
    # 333618
    # 20017085
    # 20015645
    #
    # Tam format vendor tarafından belgelenmediği için burada
    # güvenli ve fail-closed yaklaşım kullanıyoruz.
    # Şimdilik yalnızca yüksek güvenli parçaları çıkarıyoruz.
    try:
        if len(s) == 8 and s.startswith("20"):
            # 20 017 085 gibi görünüyor -> tam takvim dönüşümü henüz net değil
            return None
        if len(s) == 6:
            return None
    except Exception:
        return None

    return None


def decode_record_bytes(
    rec: bytes,
    *,
    symbol: str,
    period: str,
    record_index: int,
    source_file: str,
) -> IdealIntradayRecord:
    if len(rec) != REC_SIZE:
        raise ValueError(f"invalid_record_size={len(rec)}")

    ts_code_raw = _u32le(rec[0:4])
    period_u = str(period).upper()

    return IdealIntradayRecord(
        symbol=symbol,
        period=period_u,
        record_index=record_index,
        ts_code_raw=ts_code_raw,
        ts_iso=decode_ts_code_raw(ts_code_raw, period_u),
        open=_f32le(rec[4:8]),
        high=_f32le(rec[8:12]),
        low=_f32le(rec[12:16]),
        close=_f32le(rec[16:20]),
        volume=_f32le(rec[20:24]),
        turnover_tl=_f32le(rec[24:28]),
        reserved_u32=_u32le(rec[28:32]),
        source_file=source_file,
    )


def record_is_plausible(rec: IdealIntradayRecord) -> bool:
    vals = [rec.open, rec.high, rec.low, rec.close, rec.volume, rec.turnover_tl]
    if not all(v == v and v not in (float("inf"), float("-inf")) for v in vals):
        return False
    if min(rec.open, rec.high, rec.low, rec.close) <= 0:
        return False
    if rec.high < max(rec.open, rec.low, rec.close):
        return False
    if rec.low > min(rec.open, rec.high, rec.close):
        return False
    if rec.volume < 0 or rec.turnover_tl < 0:
        return False
    return True


def iter_file_records(
    path: str | Path,
    *,
    symbol: Optional[str] = None,
    period: Optional[str] = None,
    tail: Optional[int] = None,
) -> Iterator[IdealIntradayRecord]:
    p = Path(path)
    st = p.stat()
    if st.st_size % REC_SIZE != 0:
        raise ValueError(f"file_size_not_multiple_of_32={p}")

    sym = (symbol or infer_symbol_from_filename(p)).upper()
    per = (period or infer_period_from_filename(p)).upper()
    total = st.st_size // REC_SIZE

    start_idx = 0
    if tail is not None and tail > 0:
        start_idx = max(0, total - int(tail))

    with p.open("rb") as f:
        f.seek(start_idx * REC_SIZE)
        for idx in range(start_idx, total):
            rec = f.read(REC_SIZE)
            if len(rec) != REC_SIZE:
                break
            yield decode_record_bytes(
                rec,
                symbol=sym,
                period=per,
                record_index=idx,
                source_file=str(p),
            )


def parse_file(
    path: str | Path,
    *,
    symbol: Optional[str] = None,
    period: Optional[str] = None,
    tail: Optional[int] = None,
) -> list[dict]:
    return [asdict(x) for x in iter_file_records(path, symbol=symbol, period=period, tail=tail)]


def file_record_count(path: str | Path) -> int:
    p = Path(path)
    st = p.stat()
    if st.st_size % REC_SIZE != 0:
        raise ValueError(f"file_size_not_multiple_of_32={p}")
    return st.st_size // REC_SIZE
