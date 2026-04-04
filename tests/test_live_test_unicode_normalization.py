import json
import unicodedata
from pathlib import Path

from bist_core.live_test.store import append_recommendation, load_recommendations


def test_live_test_store_normalizes_metadata_to_nfc(tmp_path: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "AKBNK için kısa vade senaryo üret")
    assert decomposed != "AKBNK için kısa vade senaryo üret"

    append_recommendation(
        root=tmp_path,
        source="gateway_chat",
        symbol="AKBNK",
        day="2026-02-27",
        decision="WATCH",
        metadata={"message": decomposed},
    )

    items = load_recommendations(tmp_path)
    assert len(items) == 1
    assert items[0].metadata["message"] == "AKBNK için kısa vade senaryo üret"

    raw = (Path(tmp_path) / "recommendations.jsonl").read_text(encoding="utf-8")
    payload = json.loads(raw.strip())
    assert payload["metadata"]["message"] == "AKBNK için kısa vade senaryo üret"
