from __future__ import annotations

from pathlib import Path


def test_core_golden_path_fences_are_ok() -> None:
    text = Path("docs/CORE_GOLDEN_PATH.md").read_text(encoding="utf-8")
    assert text.count("```") % 2 == 0
    assert "Run:```" not in text
    assert "jsonpython -m" not in text
