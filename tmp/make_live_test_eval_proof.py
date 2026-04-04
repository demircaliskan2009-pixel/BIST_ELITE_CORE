from pathlib import Path

proof = Path(r"tmp/live_test_eval_proof")
snap = proof / "snapshots"

def write_day(day: str, rows: list[tuple[str, float, float, float, float]]) -> None:
    day_dir = snap / day
    day_dir.mkdir(parents=True, exist_ok=True)
    lines = ["date,symbol,open,high,low,close,volume,turnover_tl"]
    for symbol, o, h, l, c in rows:
        lines.append(f"{day},{symbol},{o},{h},{l},{c},1000,100000")
    (day_dir / "snapshot.csv").write_text("\n".join(lines), encoding="utf-8")

write_day("2026-02-27", [("AKBNK", 100, 102, 99, 101), ("AKFIS", 50, 51, 49, 50.5)])
write_day("2026-03-02", [("AKBNK", 103, 111, 103, 110), ("AKFIS", 50, 50.5, 49.5, 50)])
print("OK_PROOF_SNAPSHOTS")
