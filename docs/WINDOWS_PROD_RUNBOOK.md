# Windows Production Runbook

Step-by-step guide for running BIST Elite Core in production on Windows.

---

## 1. Venv Setup

From the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## 2. Optional Dependencies

**OpenAI (for AI-powered advice):**
```powershell
pip install openai
# or: pip install bist-elite-core[openai]
```

**Terminal automation / order bridge UI:**
- See `bist_core.connectors.order_bridge_interface` for the Flask-based order bridge.
- Requires `flask` if using the UI.

---

## 3. Environment Variables

**Current session (PowerShell):**
```powershell
$env:OPENAI_API_KEY="sk-..."
$env:BIST_CORE_ALLOW_NETWORK="1"
$env:BIST_CORE_SNAPSHOT_DIR="C:\path\to\data\eod\snapshots"
```

**Persistent (new sessions):**
```cmd
setx OPENAI_API_KEY "sk-..."
setx BIST_CORE_ALLOW_NETWORK "1"
```

> **Important:** `setx` only affects new processes. Open a new PowerShell window or run `$env:VAR="..."` again in the current session.

---

## 4. Production Run Sequence

From repo root, in order:

### Step 1: Doctor (preflight)
```powershell
python -m bist_core.cli.main doctor
# or: python -m bist_core.cli doctor
```

If `--mode openai` is needed: `python -m bist_core.cli.main doctor --mode openai`.

### Step 2: Proof pack
```powershell
.\tools\proof_pack.ps1
# or: . .\tools\aliases.ps1; run_proof
```

### Step 3: EOD pipeline
```powershell
python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data\eod\runs\YYYY-MM-DD --emit-orders
```

### Step 4 (optional): Order bridge UI

If using the order bridge for manual approval:
- Start the Flask app (see `order_bridge_interface`).
- Use the UI to review and send pending orders.

---

## 5. Do Not Commit Keys

**Never commit API keys, secrets, or credentials to git.**

- Use `$env:OPENAI_API_KEY` or `setx` for local/dev.
- For CI: use secrets or a secret manager; never hard-code.
- Add `.env` (if used) to `.gitignore` and keep keys out of config files committed to the repo.

---

## Quick Reference

| Task              | Command                                      |
|-------------------|----------------------------------------------|
| Doctor            | `python -m bist_core.cli.main doctor`        |
| Proof pack        | `.\tools\proof_pack.ps1`                     |
| Clean + proof     | `. .\tools\aliases.ps1` then `run_proof`     |
| EOD run           | `python -m bist_core.cli eod run --day ...`  |
