# tools/ci_commit.py
"""
Geliştirici için hızlı akış:
    1) pytest çalıştır
    2) Geçerse git status göster
    3) Onay al
    4) git add -A + git commit + git push

Kullanım:
    python tools/ci_commit.py -m "Faz-3 Step-2: registry + CLI"

Gereksinimler:
    - git kurulmuş olmalı
    - repo bir git reposu olmalı (BIST_ELITE_CORE)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> int:
    print("[ci_commit] Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run tests, then git commit+push if tests pass.")
    parser.add_argument(
        "-m",
        "--message",
        required=True,
        help="Commit message",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Do not ask for interactive confirmation before commit/push.",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    print(f"[ci_commit] Repo root: {root}")

    # 1) pytest
    test_cmd = [sys.executable, "-m", "pytest", "-q"]
    print("[ci_commit] Step 1/4: pytest")
    rc = run(test_cmd, root)
    if rc != 0:
        print(f"[ci_commit] ❌ Tests failed (exit code={rc}), aborting commit.")
        return rc

    print("[ci_commit] ✅ Tests passed")

    # 2) git status
    print("[ci_commit] Step 2/4: git status --short")
    rc = run(["git", "status", "--short"], root)
    if rc != 0:
        print("[ci_commit] ❌ git status failed, aborting.")
        return rc

    # 3) confirm
    if not args.yes:
        answer = input(
            "[ci_commit] Stage ALL changes and commit+push with this message?\n"
            f"    {args.message!r}\n"
            "Type 'yes' to confirm: "
        ).strip()
        if answer.lower() != "yes":
            print("[ci_commit] Aborted by user.")
            return 1

    # 4) git add -A
    print("[ci_commit] Step 3/4: git add -A")
    rc = run(["git", "add", "-A"], root)
    if rc != 0:
        print("[ci_commit] ❌ git add failed, aborting.")
        return rc

    # 5) git commit
    print("[ci_commit] Step 4/4: git commit")
    rc = run(["git", "commit", "-m", args.message], root)
    if rc != 0:
        print("[ci_commit] ❌ git commit failed, aborting.")
        return rc

    # 6) git push
    print("[ci_commit] Step 5/4: git push (extra step)")
    rc = run(["git", "push"], root)
    if rc != 0:
        print("[ci_commit] ❌ git push failed.")
        return rc

    print("[ci_commit] ✅ All done: tests + commit + push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
