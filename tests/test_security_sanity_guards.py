"""Security and sanity guards — no unsafe patterns, whitelisted dynamic imports.

Enforces:
- No os.system (use subprocess with list args)
- No shell=True in subprocess
- Dynamic imports (importlib/__import__) only whitelisted modules
- No .NET/COM/clr/pythonnet/win32com
"""

from __future__ import annotations

import re
from pathlib import Path


def _src_root() -> Path:
    return Path(__file__).resolve().parents[1] / "src"


# Allowed modules for importlib.import_module() and __import__() in src/
DYNAMIC_IMPORT_WHITELIST = frozenset(
    {
        "openai",
        "pyautogui",
        "flask",
        "pywinauto",
    }
)


def _collect_py_files(root: Path) -> list[Path]:
    return list(root.rglob("*.py"))


def test_no_os_system_in_src() -> None:
    """src/ must not use os.system (injection risk)."""
    root = _src_root()
    for path in _collect_py_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "os.system" in text:
            # Exclude comments
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if "os.system" in stripped and not stripped.startswith("#"):
                    raise AssertionError(f"{path.relative_to(root.parent)}:{i}: os.system forbidden")


def test_no_shell_true_in_src() -> None:
    """src/ must not use subprocess with shell=True."""
    root = _src_root()
    for path in _collect_py_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "subprocess" in text and "shell" in text:
            for i, line in enumerate(text.splitlines(), 1):
                if "shell" in line and ("True" in line or "=1" in line) and not line.strip().startswith("#"):
                    raise AssertionError(f"{path.relative_to(root.parent)}:{i}: subprocess shell=True forbidden")


def test_no_dotnet_com_in_src() -> None:
    """src/ must not reference .NET, COM, clr, pythonnet, win32com."""
    root = _src_root()
    forbidden = re.compile(
        r"\b(clr|pythonnet|win32com|\.NET|System\.Runtime\.InteropServices)\b",
        re.IGNORECASE,
    )
    for path in _collect_py_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if not line.strip().startswith("#") and forbidden.search(line):
                raise AssertionError(f"{path.relative_to(root.parent)}:{i}: .NET/COM forbidden: {line.strip()[:60]}")


def test_dynamic_imports_whitelisted() -> None:
    """importlib.import_module and __import__ in src/ must use whitelisted modules only."""
    root = _src_root()
    import_module_re = re.compile(r'import_module\s*\(\s*["\']([^"\']+)["\']')
    dunder_import_re = re.compile(r'__import__\s*\(\s*["\']([^"\']+)["\']')

    for path in _collect_py_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in import_module_re.finditer(text):
            mod = match.group(1).split(".")[0]  # first segment
            if mod not in DYNAMIC_IMPORT_WHITELIST:
                raise AssertionError(f"{path.relative_to(root.parent)}: import_module('{mod}') not whitelisted")
        for match in dunder_import_re.finditer(text):
            mod = match.group(1).split(".")[0]
            if mod not in DYNAMIC_IMPORT_WHITELIST:
                raise AssertionError(f"{path.relative_to(root.parent)}: __import__('{mod}') not whitelisted")


def test_no_exec_eval_in_src() -> None:
    """src/ must not use exec() or eval() with variable input."""
    root = _src_root()
    for path in _collect_py_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"\bexec\s*\(", stripped) or re.search(r"\beval\s*\(", stripped):
                raise AssertionError(f"{path.relative_to(root.parent)}:{i}: exec/eval forbidden")


def test_ruff_check_if_available() -> None:
    """Run ruff check on src/ if ruff is installed (optional lint gate)."""
    pytest = __import__("pytest")
    pytest.importorskip("ruff", reason="ruff optional for lint gate")
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src/"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, f"ruff check failed:\n{r.stderr or r.stdout}"
