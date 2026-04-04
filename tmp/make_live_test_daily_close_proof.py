import json
from pathlib import Path

proof = Path(r"tmp/live_test_daily_close_proof")
snap = proof / "snapshots"

def write_day(day: str, rows):
    day_dir = snap / day
    day_dir.mkdir(parents=True, exist_ok=True)
    lines = ["date,symbol,open,high,low,close,volume,turnover_tl"]
    for symbol, o, h, l, c in rows:
        lines.append(f"{day},{symbol},{o},{h},{l},{c},1000,100000")
    (day_dir / "snapshot.csv").write_text("\n".join(lines), encoding="utf-8")

write_day("2026-02-27", [("AKBNK", 100, 102, 99, 101), ("AKFIS", 50, 51, 49, 50.5)])
write_day("2026-03-02", [("AKBNK", 103, 111, 103, 110), ("AKFIS", 50, 50.5, 49.5, 50)])

(proof / "meta_ask.json").write_text(
    json.dumps({"message": "AKBNK için kısa vade senaryo üret"}, ensure_ascii=False),
    encoding="utf-8",
)
(proof / "meta_scan.json").write_text(
    json.dumps({"message": "scan top 3", "top_n": 3}, ensure_ascii=False),
    encoding="utf-8",
)
print("OK_DAILY_CLOSE_PROOF_FILES")
