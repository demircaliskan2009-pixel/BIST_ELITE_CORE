from pathlib import Path
import re

ROOT = Path(r".")
APP_FILE = ROOT / r"src\bist_core\gateway\app.py"

if not APP_FILE.exists():
    raise SystemExit(f"GATEWAY_APP_NOT_FOUND: {APP_FILE}")

txt = APP_FILE.read_text(encoding="utf-8")
original = txt

import_line = "from bist_core.live_test.gateway_middleware import LiveTestChatLoggingMiddleware"
if import_line not in txt:
    lines = txt.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            insert_at = i + 1
            continue
        if s == "":
            continue
        break
    lines.insert(insert_at, import_line)
    txt = "\n".join(lines) + "\n"

if "add_middleware(LiveTestChatLoggingMiddleware)" not in txt:
    m = re.search(r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*FastAPI\(", txt)
    if not m:
        raise SystemExit("FASTAPI_CONSTRUCTOR_NOT_FOUND_IN_GATEWAY_APP")

    app_var = m.group("var")
    start = m.end() - 1
    depth = 0
    end = None

    for i in range(start, len(txt)):
        ch = txt[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end is None:
        raise SystemExit("FASTAPI_CONSTRUCTOR_END_NOT_FOUND_IN_GATEWAY_APP")

    line_end = txt.find("\n", end)
    if line_end == -1:
        line_end = len(txt)

    inject = f"\n{app_var}.add_middleware(LiveTestChatLoggingMiddleware)\n"
    txt = txt[:line_end+1] + inject + txt[line_end+1:]

if txt != original:
    APP_FILE.write_text(txt, encoding="utf-8", newline="\n")

out = ROOT / ".gateway_app_path.txt"
out.write_text(str(APP_FILE), encoding="utf-8")
print(f"PATCHED_GATEWAY_APP={APP_FILE}")
