# Optional AI (OpenAI) Installation

The OpenAI model is **optional**. Core BIST Elite Core works without it. Install only when using `--model openai` for advice generation.

## Install

```bash
pip install openai
```

Or via the optional extra:

```bash
pip install bist-elite-core[openai]
```

## Requirements

- **OPENAI_API_KEY** — Required when using the OpenAI model.
  - **PowerShell:** `$env:OPENAI_API_KEY="sk-..."`
  - **CMD (persistent):** `setx OPENAI_API_KEY "sk-..."`
- **BIST_CORE_ALLOW_NETWORK** — Must be `1` or `true` to allow outbound API calls. Default is off (fail-closed).

## Usage

```bash
# Standalone advice with OpenAI
$env:OPENAI_API_KEY="sk-..."
$env:BIST_CORE_ALLOW_NETWORK="1"
python -m bist_core.cli eod advice --day 2025-01-15 --outdir data/out --model openai

# Pipeline with OpenAI (env)
$env:USE_OPENAI_MODEL="1"
$env:OPENAI_API_KEY="sk-..."
$env:BIST_CORE_ALLOW_NETWORK="1"
python -m bist_core.cli eod run --day 2025-01-15 --outdir data/eod/runs/2025-01-15 --emit-orders
```

## Fail-Closed Behavior

- Missing **OPENAI_API_KEY** → CLI exits with code 2, "blocked:" message.
- **BIST_CORE_ALLOW_NETWORK** not set → CLI exits with code 2, "blocked: NETWORK_DISABLED".
- OpenAI package not installed → "blocked: openai package required (pip install openai)".

## Caching

When using `--model openai`, responses are cached under `outdir/_cache/openai/`. Repeated runs with the same inputs use the cache (no API call).
