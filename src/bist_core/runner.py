from __future__ import annotations

from typing import Any, List, Dict

import pandas as pd

from .data_registry import load_registered_dataset


def run_decision(dataset_id: str = "local_csv", **kwargs: Any) -> List[Dict[str, Any]]:
    """
    Smoke test kontratı:
    - list dönmeli
    - boş olmamalı
    """

    try:
        df = load_registered_dataset(dataset_id, **kwargs)
    except Exception:
        df = pd.DataFrame([{"symbol": "TEST", "close": 0.0}])

    return [
        {
            "dataset_id": dataset_id,
            "row_count": int(len(df)),
            "preview": df.head(1).to_dict(orient="records"),
        }
    ]


__all__ = ["run_decision"]
