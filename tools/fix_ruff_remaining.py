"""
tools/fix_ruff_remaining.py (v2)

Best-effort autopatcher for common Ruff leftovers in this repo.
Focus:
- E402: module imports not at top (add file-level ruff noqa where intentional)
- E741: ambiguous variable name `l` (rename in a few known files)
- F821: pd/hashlib/payload/result undefined (fix the common broken edits)
- remove broken tmp_main_head.py (null bytes / non-utf8) if present
- trailing whitespace cleanup
"""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _backup_once(path: Path) -> None:
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        bak.write_text(_read(path), encoding="utf-8")


def _strip_trailing_ws(text: str) -> str:
    lines = text.splitlines()
    out = [ln.rstrip(" \t") for ln in lines]
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _replace_regex(text: str, pattern: str, repl: str, *, flags: int = 0, count: int = 0) -> tuple[str, bool]:
    new = re.sub(pattern, repl, text, flags=flags, count=count)
    return new, new != text


def _insert_after_header(lines: list[str], insert_line: str) -> list[str]:
    """
    Insert after shebang/encoding and after module docstring (if present).
    """
    if any(ln.strip() == insert_line for ln in lines[:20]):
        return lines

    i = 0
    # shebang
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    # encoding
    if i < len(lines) and re.search(r"coding[:=]\s*utf-8", lines[i]):
        i += 1

    # skip empty/comment lines
    while i < len(lines) and (lines[i].strip() == "" or lines[i].lstrip().startswith("#")):
        i += 1

    # module docstring
    if i < len(lines) and re.match(r'^[uU]?[rR]?("""|\'\'\')', lines[i].lstrip()):
        quote = '"""' if '"""' in lines[i] else "'''"
        i += 1
        while i < len(lines) and quote not in lines[i]:
            i += 1
        if i < len(lines):
            i += 1  # include closing docstring line
        # allow a blank line after docstring
        if i < len(lines) and lines[i].strip() == "":
            i += 1

    lines.insert(i, insert_line)
    return lines


def _ensure_file_level_noqa(path: Path, code: str) -> bool:
    """
    Add: # ruff: noqa: <code>
    """
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    lines = text.splitlines()

    # if already has ruff: noqa with code
    if any(re.search(rf"^#\s*ruff:\s*noqa:.*\b{re.escape(code)}\b", ln) for ln in lines[:25]):
        if text != original:
            _backup_once(path)
            _write(path, text)
            return True
        return False

    insert = f"# ruff: noqa: {code}"
    new_lines = _insert_after_header(lines, insert)
    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    if new_text != text or text != original:
        _backup_once(path)
        _write(path, new_text)
        return True
    return False


def _delete_broken_tmp_files() -> list[Path]:
    removed: list[Path] = []
    candidates = [ROOT / "tmp_main_head.py"]
    for p in candidates:
        if not p.exists():
            continue
        try:
            b = p.read_bytes()
        except Exception:
            continue
        # null byte or not utf-8 => delete
        if b"\x00" in b:
            p.unlink(missing_ok=True)
            removed.append(p)
            continue
        try:
            b.decode("utf-8")
        except Exception:
            p.unlink(missing_ok=True)
            removed.append(p)
    return removed


def _patch_payload_in_test_faz36(path: Path) -> bool:
    """
    Fix: payload referenced but assignment replaced by `_ = json.loads(...)`.
    """
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    if ("assert payload" in text or "payload[" in text or "payload.get(" in text) and not re.search(
        r"(?m)^\s*payload\s*=\s*json\.loads\(", text
    ):
        # replace first occurrence of `_ = json.loads(orders_path.read_text(...))` with `payload = ...`
        text2, ch = _replace_regex(
            text,
            r"(?m)^(\s*)_\s*=\s*json\.loads\((\s*orders_path\.read_text\([^)]+\)\s*)\)\s*$",
            r"\1payload = json.loads(\2)",
            count=1,
        )
        text, changed = text2, (changed or ch)

    # also handle the specific lines you showed (where `_ = json.loads(orders_path.read_text...)` exists but payload used)
    text2, ch = _replace_regex(
        text,
        r"(?m)^(\s*)_\s*=\s*json\.loads\(\s*orders_path\.read_text\([^)]+\)\s*\)\s*$",
        r'\1payload = json.loads(orders_path.read_text(encoding="utf-8"))',
        count=1,
    )
    # Only apply that aggressive rewrite if payload is referenced later
    if ch and ("payload[" in text2 or "payload.get(" in text2):
        text, changed = text2, True

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_result_in_theta3(path: Path) -> bool:
    """
    Fix: result referenced but `_ = _run_cli(...)` used.
    """
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    if "result." in text or "assert result" in text:
        # replace all `_ = _run_cli(` with `result = _run_cli(`
        text2, ch = _replace_regex(text, r"(?m)^(\s*)_\s*=\s*_run_cli\(", r"\1result = _run_cli(")
        text, changed = text2, (changed or ch)

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_faz73_memory_link_graph(path: Path) -> bool:
    """
    Fix the broken refactor you currently have:
      doc_to_evidence = [l for link in links ...]  -> [link for link in links ...]
    and fix all() generator variable names to avoid E741.
    """
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    # list comps
    text2, ch = _replace_regex(
        text,
        r"(?m)^\s*doc_to_evidence\s*=\s*\[l\s+for\s+link\s+in\s+links\s+if\s+link\[(\"|')type\1\]\s*==\s*(\"|')doc_to_evidence\2\]\s*$",
        '    doc_to_evidence = [link for link in links if link["type"] == "doc_to_evidence"]',
    )
    text, changed = text2, (changed or ch)

    text2, ch = _replace_regex(
        text,
        r"(?m)^\s*advice_to_evidence\s*=\s*\[l\s+for\s+link\s+in\s+links\s+if\s+link\[(\"|')type\1\]\s*==\s*(\"|')advice_to_evidence\2\]\s*$",
        '    advice_to_evidence = [link for link in links if link["type"] == "advice_to_evidence"]',
    )
    text, changed = text2, (changed or ch)

    text2, ch = _replace_regex(
        text,
        r"(?m)^\s*evidence_in_dossier\s*=\s*\[l\s+for\s+link\s+in\s+links\s+if\s+link\[(\"|')type\1\]\s*==\s*(\"|')evidence_in_dossier\2\]\s*$",
        '    evidence_in_dossier = [link for link in links if link["type"] == "evidence_in_dossier"]',
    )
    text, changed = text2, (changed or ch)

    # all() assertions
    text2, ch = _replace_regex(
        text,
        r'(?m)^\s*assert\s+all\(\s*link\["to"\]\s*==\s*"research_path"\s+for\s+l\s+in\s+doc_to_evidence\s*\)\s*$',
        '    assert all(item["to"] == "research_path" for item in doc_to_evidence)',
    )
    text, changed = text2, (changed or ch)

    text2, ch = _replace_regex(
        text,
        r'(?m)^\s*assert\s+all\(\s*link\["to"\]\s*==\s*"advice_path"\s+for\s+l\s+in\s+advice_to_evidence\s*\)\s*$',
        '    assert all(item["to"] == "advice_path" for item in advice_to_evidence)',
    )
    text, changed = text2, (changed or ch)

    text2, ch = _replace_regex(
        text,
        r"(?m)^\s*assert\s+all\(\s*link\[\s*\"to\"\s*\]\s*==\s*NODE_DOSSIER\s+for\s+l\s+in\s+evidence_in_dossier\s*\)\s*$",
        '    assert all(item["to"] == NODE_DOSSIER for item in evidence_in_dossier)',
    )
    text, changed = text2, (changed or ch)

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_budget_check_e741(path: Path) -> bool:
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    # replace loc = len([l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")])
    text2, ch = _replace_regex(
        text,
        r"(?m)^(\s*)loc\s*=\s*len\(\[l\s+for\s+l\s+in\s+src\.splitlines\(\)\s+if\s+l\.strip\(\)\s+and\s+not\s+l\.strip\(\)\.startswith\(\"#\"\)\]\)\s*$",
        r"\1loc = len([line for line in src.splitlines() if line.strip() and not line.strip().startswith(\"#\")])",
    )
    text, changed = text2, (changed or ch)

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_observability_healthcheck_e741(path: Path) -> bool:
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    text2, ch = _replace_regex(
        text,
        r"(?m)^(\s*)lines\s*=\s*\[l\s+for\s+l\s+in\s+err\.split\(\"\\n\"\)\s+if\s+l\.strip\(\)\s+and\s+l\.strip\(\)\.startswith\(\"{\"\)\]\s*$",
        r'\1lines = [line for line in err.split("\\n") if line.strip() and line.strip().startswith("{")]',
    )
    text, changed = text2, (changed or ch)

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_test_faz597_e741(path: Path) -> bool:
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    # total_qty = sum(l.qty_remaining for l in lots_aaa) -> lot
    text2, ch = _replace_regex(
        text,
        r"(?m)^\s*total_qty\s*=\s*sum\(l\.qty_remaining\s+for\s+l\s+in\s+lots_aaa\)\s*$",
        "    total_qty = sum(lot.qty_remaining for lot in lots_aaa)",
    )
    text, changed = text2, (changed or ch)

    # total_cost = sum(Decimal(l.qty_remaining) * l.price for l in lots_aaa) -> lot
    text2, ch = _replace_regex(
        text,
        r"(?m)^\s*total_cost\s*=\s*sum\(Decimal\(l\.qty_remaining\)\s*\*\s*l\.price\s+for\s+l\s+in\s+lots_aaa\)\s*$",
        "    total_cost = sum(Decimal(lot.qty_remaining) * lot.price for lot in lots_aaa)",
    )
    text, changed = text2, (changed or ch)

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_src_execution_fifo_e741(path: Path) -> bool:
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    # lots_by_symbol[sym] = [l for l in lots if l.qty_remaining > 0]
    text2, ch = _replace_regex(
        text,
        r"(?m)^(\\s*)lots_by_symbol\\[sym\\]\\s*=\\s*\\[l\\s+for\\s+l\\s+in\\s+lots\\s+if\\s+l\\.qty_remaining\\s*>\\s*0\\]\\s*$",
        r"\1lots_by_symbol[sym] = [lot for lot in lots if lot.qty_remaining > 0]",
    )
    text, changed = text2, (changed or ch)

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_src_execution_reporting_e741(path: Path) -> bool:
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    text2, ch = _replace_regex(
        text,
        r"(?m)^(\\s*)total_qty\\s*=\\s*sum\\(l\\.qty_remaining\\s+for\\s+l\\s+in\\s+lots\\)\\s*$",
        r"\1total_qty = sum(lot.qty_remaining for lot in lots)",
    )
    text, changed = text2, (changed or ch)

    text2, ch = _replace_regex(
        text,
        r"(?m)^(\\s*)total_cost\\s*=\\s*sum\\(Decimal\\(l\\.qty_remaining\\)\\s*\\*\\s*l\\.price\\s+for\\s+l\\s+in\\s+lots\\)\\s*$",
        r"\1total_cost = sum(Decimal(lot.qty_remaining) * lot.price for lot in lots)",
    )
    text, changed = text2, (changed or ch)

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _patch_advisory_outcome_l(path: Path) -> bool:
    """
    Rename `l = row.get("low")` to `low_val = ...` and rewrite immediate uses.
    """
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    lines = text.splitlines()
    changed = False

    for i, ln in enumerate(lines):
        if re.match(r"^\s*l\s*=\s*row\.get\(\"low\"\)\s*$", ln):
            indent = re.match(r"^(\s*)", ln).group(1)
            lines[i] = indent + 'low_val = row.get("low")'
            # patch next ~25 lines: \bl\b -> low_val (local, safest)
            for j in range(i + 1, min(i + 26, len(lines))):
                lines[j] = re.sub(r"\bl\b", "low_val", lines[j])
            changed = True
            break

    if changed:
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        if new_text != original:
            _backup_once(path)
            _write(path, new_text)
            return True
    return False


def _ensure_type_checking_pd(path: Path) -> bool:
    """
    Fix F821 pd in annotations by defining pd under TYPE_CHECKING.
    """
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    changed = False

    if '"pd.DataFrame"' not in text and "pd.DataFrame" not in text:
        return False

    # ensure TYPE_CHECKING import
    if "TYPE_CHECKING" not in text:
        # add to typing import line if present; else add a new import
        if re.search(r"(?m)^from typing import ", text):
            text2, ch = _replace_regex(
                text,
                r"(?m)^from typing import ([^\n]+)$",
                lambda m: (
                    m.group(0) if "TYPE_CHECKING" in m.group(1) else f"from typing import {m.group(1)}, TYPE_CHECKING"
                ),
                count=1,
            )
            text, changed = text2, (changed or ch)
        else:
            # insert near top after __future__ or first imports
            lines = text.splitlines()
            insert_at = 0
            for i, ln in enumerate(lines[:60]):
                if ln.startswith("from __future__ import"):
                    insert_at = i + 1
            lines.insert(insert_at, "from typing import TYPE_CHECKING")
            text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            changed = True

    # ensure TYPE_CHECKING block defines pd
    if "if TYPE_CHECKING:" not in text or "import pandas as pd" not in text:
        lines = text.splitlines()
        # place block after imports (simple heuristic: after last import in first 80 lines)
        last_import = -1
        for i, ln in enumerate(lines[:120]):
            if ln.startswith("import ") or ln.startswith("from "):
                last_import = i
        block = ["", "if TYPE_CHECKING:", "    import pandas as pd", ""]
        if last_import >= 0:
            # if already has TYPE_CHECKING but not block, insert after last import
            if "if TYPE_CHECKING:" not in text:
                for k, b in enumerate(block):
                    lines.insert(last_import + 1 + k, b)
                text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
                changed = True
            else:
                # has block but no pandas import -> patch inside existing block
                # naive: add next line after 'if TYPE_CHECKING:'
                for i, ln in enumerate(lines):
                    if ln.strip() == "if TYPE_CHECKING:":
                        # check next few lines
                        window = "\n".join(lines[i : i + 6])
                        if "import pandas as pd" not in window:
                            lines.insert(i + 1, "    import pandas as pd")
                            changed = True
                        break
                text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        else:
            # no imports? just prepend
            text = "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import pandas as pd\n\n" + text
            changed = True

    if changed or text != original:
        _backup_once(path)
        _write(path, text)
        return True
    return False


def _ensure_import_hashlib(path: Path) -> bool:
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    if "hashlib" in text and re.search(r"(?m)^import hashlib$", text):
        return False

    if "hashlib.sha256" not in text:
        return False

    # insert import hashlib after other imports
    lines = text.splitlines()
    if any(ln.strip() == "import hashlib" for ln in lines[:80]):
        return False

    last_import = -1
    for i, ln in enumerate(lines[:120]):
        if ln.startswith("import ") or ln.startswith("from "):
            last_import = i
    if last_import >= 0:
        lines.insert(last_import + 1, "import hashlib")
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        _backup_once(path)
        _write(path, new_text)
        return True
    return False


def _execution_adapters_export_executionprovider(path: Path) -> bool:
    """
    Fix F401 by adding ExecutionProvider to __all__ in src/bist_core/execution/adapters/__init__.py
    """
    if not path.exists():
        return False
    original = _read(path)
    text = _strip_trailing_ws(original)
    if "ExecutionProvider" not in text:
        return False

    # if __all__ exists, append if missing
    if "__all__" in text:
        if re.search(r"(?m)^__all__\s*=\s*\[", text):
            if re.search(r"ExecutionProvider", re.search(r"(?s)__all__\s*=\s*\[.*?\]", text).group(0)):
                return False
            # append before closing ]
            text2, ch = _replace_regex(
                text,
                r"(?s)(__all__\s*=\s*\[.*?)(\]\s*)",
                r'\1    "ExecutionProvider",\n\2',
                count=1,
            )
            if ch:
                _backup_once(path)
                _write(path, text2)
                return True
            return False

    # no __all__: add minimal
    lines = text.splitlines()
    lines.append("")
    lines.append('__all__ = ["ExecutionProvider", "StubExecutionProvider", "get_execution_provider"]')
    new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    _backup_once(path)
    _write(path, new_text)
    return True


def _strip_ws_everywhere() -> int:
    count = 0
    for folder in ("tests", "src", "tools", "scripts"):
        d = ROOT / folder
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            try:
                original = _read(p)
            except Exception:
                continue
            text = _strip_trailing_ws(original)
            if text != original:
                _backup_once(p)
                _write(p, text)
                count += 1
    return count


def main() -> int:
    touched: list[Path] = []

    removed = _delete_broken_tmp_files()
    for p in removed:
        print(f"[fix_ruff v2] removed broken file: {p.relative_to(ROOT)}")

    ws = _strip_ws_everywhere()
    if ws:
        print(f"[fix_ruff v2] stripped trailing whitespace in {ws} files")

    # E402: these files intentionally modify sys.path or do late imports; silence E402 at file level
    e402_files = [
        ROOT / "scripts" / "verify_alignment.py",
        ROOT / "tools" / "live_snapshot_prepare.py",
        ROOT / "tests" / "test_broker_adapter_contract_harness.py",
        ROOT / "tests" / "test_faz576_live_manifest.py",
        ROOT / "tests" / "test_faz577_live_weekly.py",
        ROOT / "tests" / "test_faz597_fills_fifo.py",
        ROOT / "tests" / "test_live_daily_runner.py",
        ROOT / "tests" / "test_live_ops_pack.py",
        # package init / registry-style modules (quick fix; later we can refactor)
        ROOT / "src" / "bist_core" / "__init__.py",
        ROOT / "src" / "bist_core" / "core" / "__init__.py",
        ROOT / "src" / "bist_core" / "data" / "__init__.py",
        ROOT / "src" / "bist_core" / "orders" / "strategies" / "__init__.py",
        ROOT / "src" / "bist_core" / "cli" / "main.py",
        ROOT / "src" / "bist_core" / "connectors" / "order_bridge_dll.py",
    ]
    for f in e402_files:
        if _ensure_file_level_noqa(f, "E402"):
            touched.append(f)

    # F821 payload/result fixes
    if _patch_payload_in_test_faz36(ROOT / "tests" / "test_faz36_risk_engine.py"):
        touched.append(ROOT / "tests" / "test_faz36_risk_engine.py")

    if _patch_result_in_theta3(ROOT / "tests" / "test_theta3_security_guardrails.py"):
        touched.append(ROOT / "tests" / "test_theta3_security_guardrails.py")

    # E741 fixes
    if _patch_faz73_memory_link_graph(ROOT / "tests" / "test_faz73_memory_link_graph.py"):
        touched.append(ROOT / "tests" / "test_faz73_memory_link_graph.py")

    if _patch_budget_check_e741(ROOT / "tools" / "budget_check.py"):
        touched.append(ROOT / "tools" / "budget_check.py")

    if _patch_observability_healthcheck_e741(ROOT / "tests" / "test_faz64_observability_healthcheck.py"):
        touched.append(ROOT / "tests" / "test_faz64_observability_healthcheck.py")

    if _patch_test_faz597_e741(ROOT / "tests" / "test_faz597_fills_fifo.py"):
        touched.append(ROOT / "tests" / "test_faz597_fills_fifo.py")

    if _patch_src_execution_fifo_e741(ROOT / "src" / "bist_core" / "execution" / "fifo.py"):
        touched.append(ROOT / "src" / "bist_core" / "execution" / "fifo.py")

    if _patch_src_execution_reporting_e741(ROOT / "src" / "bist_core" / "execution" / "reporting.py"):
        touched.append(ROOT / "src" / "bist_core" / "execution" / "reporting.py")

    if _patch_advisory_outcome_l(ROOT / "src" / "bist_core" / "advisory" / "outcome.py"):
        touched.append(ROOT / "src" / "bist_core" / "advisory" / "outcome.py")

    # F821 pd in annotations
    for f in [
        ROOT / "src" / "bist_core" / "data" / "registry.py",
        ROOT / "src" / "bist_core" / "data_registry.py",
    ]:
        if _ensure_type_checking_pd(f):
            touched.append(f)

    # F821 hashlib in backtest
    if _ensure_import_hashlib(ROOT / "src" / "bist_core" / "services" / "backtest.py"):
        touched.append(ROOT / "src" / "bist_core" / "services" / "backtest.py")

    # F401 ExecutionProvider exported
    if _execution_adapters_export_executionprovider(
        ROOT / "src" / "bist_core" / "execution" / "adapters" / "__init__.py"
    ):
        touched.append(ROOT / "src" / "bist_core" / "execution" / "adapters" / "__init__.py")

    uniq = sorted({p for p in touched if p.exists()})

    if uniq:
        print("[fix_ruff v2] touched files:")
        for p in uniq:
            print(f"  - {p.relative_to(ROOT)}")
    else:
        print("[fix_ruff v2] no changes applied (or files missing)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
