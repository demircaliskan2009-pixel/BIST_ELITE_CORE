from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IdealBinaryProbe:
    path: str
    size: int
    sha256: str
    head_hex: str
    tail_hex: str
    zero_ratio: float
    ascii_ratio: float
    candidate_record_layouts: list[dict[str, int]]


def _ratio_zero(buf: bytes) -> float:
    if not buf:
        return 0.0
    return round(sum(1 for b in buf if b == 0) / len(buf), 4)


def _ratio_ascii(buf: bytes) -> float:
    if not buf:
        return 0.0
    good = 0
    for b in buf:
        if b in (9, 10, 13) or 32 <= b <= 126:
            good += 1
    return round(good / len(buf), 4)


def _candidate_record_layouts(size: int) -> list[dict[str, int]]:
    headers = [0, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 256, 320, 384, 512]
    record_sizes = [16, 20, 24, 28, 32, 36, 40, 48, 56, 64, 72, 80, 96, 112, 120, 128, 144, 160, 192, 224, 256]
    out: list[dict[str, int]] = []
    for header in headers:
        if size <= header:
            continue
        payload = size - header
        for rec in record_sizes:
            if payload % rec == 0:
                out.append(
                    {
                        "header_bytes": header,
                        "record_bytes": rec,
                        "record_count": payload // rec,
                    }
                )
    return out


def inspect_ideal_file(path: str | Path, head: int = 128, tail: int = 128) -> dict[str, Any]:
    p = Path(path)
    raw = p.read_bytes()
    return asdict(
        IdealBinaryProbe(
            path=str(p),
            size=len(raw),
            sha256=sha256(raw).hexdigest(),
            head_hex=raw[:head].hex(),
            tail_hex=raw[-tail:].hex() if raw else "",
            zero_ratio=_ratio_zero(raw),
            ascii_ratio=_ratio_ascii(raw),
            candidate_record_layouts=_candidate_record_layouts(len(raw)),
        )
    )
