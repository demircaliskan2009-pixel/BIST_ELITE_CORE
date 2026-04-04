# Windows Bootstrap (FAZ575)

Reproducible Windows-first bootstrap for a new machine. No network required at runtime (install step may use pip).

## Quick start

From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\bootstrap_windows.ps1
```

Or from `tools/`:

```powershell
powershell -ExecutionPolicy Bypass -File .\bootstrap_windows.ps1
```

## What it does

1. **Creates `.venv`** if missing
2. **Installs dependencies**: `pip install -e .` (pyproject) + `requirements.txt`
3. **Runs sanity checks** (offline):
   - `python scripts/verify_alignment.py`
   - `python tools/release_check.py --hygiene-only`
4. **Runs smoke tests**: minimal fast pytest subset
5. **Prints ENV REPORT**: python, pip, OS, repo sha, active branch

## Copy-paste steps (manual)

If you prefer to run steps manually:

```powershell
# 1. Clone and enter repo
cd C:\path\to\BIST_ELITE_CORE

# 2. Create venv
python -m venv .venv

# 3. Activate venv
.\.venv\Scripts\Activate.ps1

# 4. Install deps
pip install -e .
pip install -r requirements.txt

# 5. Sanity checks
python scripts/verify_alignment.py
python tools/release_check.py --hygiene-only

# 6. Smoke tests
python -m pytest -q tests/test_faz107_proof_pack_script_exists.py tests/test_faz103_release_check_hygiene_only.py tests/test_faz2_localcsv_provider.py tests/test_faz100_core_complete_sentinel.py

# 7. Full proof pack (optional)
powershell -ExecutionPolicy Bypass -File .\tools\proof_pack.ps1
```

## Prerequisites

- **Python 3.8+** on PATH
- **Git** (for repo sha in ENV REPORT)
- **PowerShell** (Windows)

## Line endings (recommended)

See [DEV_SETUP_WINDOWS.md](DEV_SETUP_WINDOWS.md) for `core.autocrlf` / `core.eol` settings.
