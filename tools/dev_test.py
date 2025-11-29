# tools/dev_test.py
"""
Basit geliştirme testi script'i.

Kullanım:
    python tools/dev_test.py

Yaptığı:
    - pytest'i sessiz modda çalıştırır (-q)
    - Çıkış kodunu aynen döner
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(f"[dev_test] Repo root: {root}")
    cmd = [sys.executable, "-m", "pytest", "-q"]
    print("[dev_test] Running:", " ".join(cmd))

    proc = subprocess.run(cmd, cwd=root)
    if proc.returncode == 0:
        print("[dev_test] ✅ Tests passed")
    else:
        print(f"[dev_test] ❌ Tests failed (exit code={proc.returncode})")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
