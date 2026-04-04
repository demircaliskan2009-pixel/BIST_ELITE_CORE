from pathlib import Path

p = Path(r"src\bist_core\live_test\chat_logging.py")
txt = p.read_text(encoding="utf-8")

old = 'return json.loads(Path(path).read_text(encoding="utf-8"))'
new = 'return json.loads(Path(path).read_text(encoding="utf-8-sig"))'

if old not in txt:
    raise SystemExit("TARGET_SNIPPET_NOT_FOUND")

txt = txt.replace(old, new, 1)
p.write_text(txt, encoding="utf-8", newline="\n")
print("PATCHED", p)
