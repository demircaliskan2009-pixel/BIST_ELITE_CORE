from __future__ import annotations
import csv
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Sequence


def _num_cast(s: str) -> Any:
    if s is None:
        return None
    v = s.strip()
    if v == "":
        return v
    v = v.replace(",", ".")
    try:
        if "." in v:
            return float(v)
        return int(v)
    except Exception:
        return s


def _kind(t: Any) -> str | None:
    if t in (float, int, str, bool):
        return t.__name__
    if isinstance(t, str):
        return t.lower()
    return None


def read_csv(
    path: str | Path,
    *,
    required_columns: Sequence[str],
    schema: Mapping[str, type] | Mapping[str, str] | None = None,
    date_field: str = "date",
) -> Iterator[Dict[str, Any]]:
    schema = schema or {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")

        cols = set(reader.fieldnames)
        missing = [c for c in required_columns if c not in cols]
        if missing:
            raise ValueError(f"missing required columns: {missing}")

        for row in reader:
            out: Dict[str, Any] = {}
            for k, v in row.items():
                if k == date_field:
                    out[k] = v
                    continue
                kind = _kind(schema.get(k))
                if v is None or v == "":
                    out[k] = v
                elif kind == "float":
                    try:
                        out[k] = float(str(v).replace(",", "."))
                    except Exception:
                        out[k] = _num_cast(str(v))
                elif kind == "int":
                    try:
                        vv = str(v).replace(",", ".")
                        out[k] = int(float(vv))
                    except Exception:
                        out[k] = _num_cast(str(v))
                else:
                    out[k] = _num_cast(str(v))
            yield out


def register_dataset(name: str, spec: Dict[str, Any], *, base_dir: Path | str) -> None:
    """Dataset şemasını/metadata'sını base_dir altında JSON olarak kaydeder."""
    import json

    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)

    jspec = dict(spec)
    if "schema" in jspec and isinstance(jspec["schema"], dict):
        sch = {}
        for k, t in jspec["schema"].items():
            sch[k] = _kind(t) or str(t)
        jspec["schema"] = sch

    # path verilmemişse eod/<name>.csv yaz
    if "path" not in jspec:
        jspec["path"] = f"eod/{name}.csv"

    (base / f"{name}.json").write_text(json.dumps(jspec, indent=2), encoding="utf-8")


def load_registered_dataset(name: str, *, base_dir: Path | str) -> List[Dict[str, Any]]:
    """Kayıtlı dataset'i (şema + path) okuyup CSV'yi yükler.
    Önce base_dir altında arar; bulunamazsa base_dir'in ebeveyninde aynı relatif yolu dener.
    """
    import json

    base = Path(base_dir)
    spec = json.loads((base / f"{name}.json").read_text(encoding="utf-8"))

    rel = spec.get("path", f"eod/{name}.csv")
    primary = base / rel
    fallback = base.parent / rel

    if primary.exists():
        csv_path = primary
    elif fallback.exists():
        csv_path = fallback
    else:
        tried = [str(primary), str(fallback)]
        raise FileNotFoundError(f"CSV not found; tried: {tried}")

    return list(
        read_csv(
            csv_path,
            required_columns=spec.get("required_columns", []),
            schema=spec.get("schema", {}),
            date_field=spec.get("date_field", "date"),
        )
    )
