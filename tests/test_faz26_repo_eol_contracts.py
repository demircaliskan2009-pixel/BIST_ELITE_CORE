from __future__ import annotations

from pathlib import Path


def test_repo_has_eol_contracts() -> None:
    ga = Path(".gitattributes").read_text(encoding="utf-8", errors="replace")
    ec = Path(".editorconfig").read_text(encoding="utf-8", errors="replace")
    assert "eol=lf" in ga
    assert "end_of_line = lf" in ec
