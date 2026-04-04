# Windows Dev Setup (Line Endings & Git)

This repo enforces LF for source text via `.gitattributes` / `.editorconfig`.

## One-time (recommended)

Run:

~~~powershell
git config --global core.autocrlf false
git config --global core.eol lf
~~~

## Per-repo (safe)

Run inside repo root:

~~~powershell
git config --local core.autocrlf false
git config --local core.eol lf
~~~

## If you ever see LF/CRLF warnings

Inside repo root:

~~~powershell
git add --renormalize .
git status --porcelain
git diff --stat
~~~

## PowerShell vs Bash

- **Chaining commands:** Use `;` (e.g. `cd repo; python -m pytest -q`). Do not use `&&` — it can cause InvalidEndOfLine in PowerShell.
- **Redirection:** Do not use bash-style `2>&1` in suggested commands; PowerShell has different redirection.
- **grep / ripgrep:** Exit code 1 usually means "no matches". When the goal is "ensure no matches", treat exit 1 as success (e.g. "no bad pattern found").
