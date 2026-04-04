from pathlib import Path
import re
import sys

ROOT = Path(r".")
SRC = ROOT / "src"

def find_gateway_app_file() -> Path:
    candidates = []
    for p in SRC.rglob("*.py"):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if "FastAPI(" in txt:
            candidates.append((p, txt))

    if not candidates:
        raise SystemExit("NO_FASTAPI_APP_FILE_FOUND")

    preferred = []
    for p, txt in candidates:
        if "/v1/chat" in txt or '"/chat"' in txt or "include_router" in txt:
            preferred.append((p, txt))

    chosen = preferred if preferred else candidates

    if len(chosen) != 1:
        print("FASTAPI_APP_CANDIDATES:")
        for p, _ in chosen:
            print(" -", p)
        raise SystemExit("AMBIGUOUS_FASTAPI_APP_FILE")

    return chosen[0][0]

def insert_import(txt: str) -> str:
    needle = "from bist_core.live_test.gateway_middleware import LiveTestChatLoggingMiddleware"
    if needle in txt:
        return txt

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

    lines.insert(insert_at, needle)
    return "\n".join(lines) + "\n"

def insert_middleware_registration(txt: str) -> str:
    if "add_middleware(LiveTestChatLoggingMiddleware)" in txt:
        return txt

    m = re.search(r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*FastAPI\(", txt)
    if not m:
        raise SystemExit("FASTAPI_CONSTRUCTOR_NOT_FOUND")

    app_var = m.group("var")
    start = m.end() - 1  # points to '('
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
        raise SystemExit("FASTAPI_CONSTRUCTOR_END_NOT_FOUND")

    line_end = txt.find("\n", end)
    if line_end == -1:
        line_end = len(txt)

    inject = f"\n{app_var}.add_middleware(LiveTestChatLoggingMiddleware)\n"
    return txt[:line_end+1] + inject + txt[line_end+1:]

def main() -> int:
    app_file = find_gateway_app_file()
    txt = app_file.read_text(encoding="utf-8")
    original = txt

    txt = insert_import(txt)
    txt = insert_middleware_registration(txt)

    if txt != original:
        app_file.write_text(txt, encoding="utf-8", newline="\n")

    out = ROOT / ".gateway_app_path.txt"
    out.write_text(str(app_file), encoding="utf-8")
    print(f"PATCHED_GATEWAY_APP={app_file}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
