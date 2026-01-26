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
