from __future__ import annotations

from pathlib import Path
from typing import Any

from bist_core.vendors.ideal_g32_export import export_g32_valid_rows_to_csv


def sync_ideal_g_folder_to_canonical(
    src_dir: str | Path,
    out_dir: str | Path,
    *,
    glob_pattern: str = "*.G",
    max_anomaly_ratio: float = 0.10,
    min_valid_rows: int = 200,
    limit: int | None = None,
) -> dict[str, Any]:
    src = Path(src_dir)
    out = Path(out_dir)

    if not src.exists():
        raise FileNotFoundError(f"Source folder not found: {src}")

    files = sorted(src.glob(glob_pattern))
    if limit is not None:
        files = files[:limit]

    out.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    exported = 0
    rejected = 0

    for f in files:
        out_csv = out / (f.stem.replace("'", "_") + ".csv")
        try:
            meta = export_g32_valid_rows_to_csv(
                f,
                out_csv,
                max_anomaly_ratio=max_anomaly_ratio,
                min_valid_rows=min_valid_rows,
            )
            meta["status"] = "exported"
            exported += 1
        except Exception as exc:
            meta = {
                "symbol": f.stem.split("'", 1)[1] if "'" in f.stem else f.stem,
                "source_file": f.name,
                "out_csv": str(out_csv),
                "status": "rejected",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
            rejected += 1
        results.append(meta)

    return {
        "src_dir": str(src),
        "out_dir": str(out),
        "glob_pattern": glob_pattern,
        "max_anomaly_ratio": max_anomaly_ratio,
        "min_valid_rows": min_valid_rows,
        "file_count_seen": len(files),
        "exported_count": exported,
        "rejected_count": rejected,
        "results": results,
    }
