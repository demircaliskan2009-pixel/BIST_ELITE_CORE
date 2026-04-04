from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    printable = 0
    for b in data:
        if b in (9, 10, 13) or 32 <= b <= 126:
            printable += 1
    return printable / len(data)


def _zero_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    return data.count(0) / len(data)


def _byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    ent = 0.0
    for count in counts.values():
        p = count / total
        ent -= p * math.log2(p)
    return ent


def _hex_head(data: bytes, limit: int = 256) -> str:
    head = data[:limit]
    return " ".join(f"{b:02x}" for b in head)


def _ascii_runs(data: bytes, min_len: int = 4, limit: int = 30) -> list[str]:
    runs: list[str] = []
    buf: list[int] = []
    for b in data:
        if b in (9, 10, 13) or 32 <= b <= 126:
            buf.append(b)
        else:
            if len(buf) >= min_len:
                runs.append(bytes(buf).decode("latin-1", errors="ignore"))
                if len(runs) >= limit:
                    break
            buf = []
    if len(buf) >= min_len and len(runs) < limit:
        runs.append(bytes(buf).decode("latin-1", errors="ignore"))
    return runs


def _candidate_record_sizes(data_len: int) -> list[dict[str, Any]]:
    candidates = [8, 12, 16, 20, 24, 28, 32, 36, 40, 48, 56, 64, 72, 80, 96, 112, 128]
    out: list[dict[str, Any]] = []
    for size in candidates:
        if data_len < size * 10:
            continue
        remainder = data_len % size
        header_guess = remainder if remainder <= min(4096, size * 4) else None
        if remainder == 0 or header_guess is not None:
            out.append(
                {
                    "record_size": size,
                    "remainder": remainder,
                    "possible_header_bytes": header_guess,
                    "estimated_records": (data_len - (header_guess or 0)) // size,
                }
            )
    return out


def _line_stats(data: bytes) -> dict[str, Any]:
    text = data.decode("latin-1", errors="ignore")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {"line_count": 0, "median_len": 0, "delim_hits": {}}
    lens = [len(x) for x in lines[:2000]]
    delim_hits = {
        ";": sum(";" in x for x in lines[:2000]),
        ",": sum("," in x for x in lines[:2000]),
        "\t": sum("\t" in x for x in lines[:2000]),
        "|": sum("|" in x for x in lines[:2000]),
    }
    return {
        "line_count": len(lines),
        "median_len": int(statistics.median(lens)),
        "delim_hits": delim_hits,
    }


def probe_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    size = len(data)
    printable_ratio = _printable_ratio(data)
    zero_ratio = _zero_ratio(data)
    entropy = _byte_entropy(data)
    line_stats = _line_stats(data[: min(len(data), 1_000_000)])
    delim_hits = line_stats["delim_hits"]
    likely_text = printable_ratio >= 0.85 and (
        line_stats["line_count"] > 1 or any(v > 0 for v in delim_hits.values())
    )

    return {
        "path": str(p),
        "filename": p.name,
        "size_bytes": size,
        "sha256": _sha256_bytes(data),
        "printable_ratio": round(printable_ratio, 6),
        "zero_ratio": round(zero_ratio, 6),
        "byte_entropy": round(entropy, 6),
        "likely_text_or_delimited": likely_text,
        "line_stats": line_stats,
        "head_hex_256": _hex_head(data, 256),
        "ascii_runs": _ascii_runs(data),
        "candidate_record_sizes": _candidate_record_sizes(size),
    }


def write_probe_report(path: str | Path, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = probe_file(path)
    target = out / f"{Path(path).name}.probe.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
