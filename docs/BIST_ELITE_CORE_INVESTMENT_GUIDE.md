# BIST Elite Core – Investment Robot User Guide

A comprehensive guide to using the BIST Elite Core for end-of-day (EOD) trading workflows, including AI-powered advice generation.

---

## Overview

**BIST Elite Core** is a modular trading system for Borsa Istanbul (BIST) equities. It helps you generate investment advice, build order intents, and execute trades (paper or live) in a fail-closed, deterministic way.

### Main Components

| Component | Purpose |
|-----------|---------|
| **Data ingestion** | Load market snapshots (close prices, volumes), KAP events, instruments, and corporate actions from CSV, KAP HTML, or external APIs. |
| **Strategy** | Order strategies (e.g. `equal_weight`, `top_n_by_signal`) that convert advice into `orders_intent.json`. |
| **Advice** | Generate buy/sell/hold scores and reasons for each symbol. Uses either the built-in advisor or the **OpenAI model**. |
| **Orders** | Build `orders_intent.json` from advice + risk gates and rulespack (tick bands, restrictions). |
| **Execution** | Send orders via paper broker (simulation) or live broker (real trades). |

The pipeline is **fail-closed**: missing config, invalid data, or policy denials block execution.

---

## Setup

### Installation

```bash
# Core dependencies (pandas, requests)
pip install bist-elite-core

# Optional: OpenAI model for AI-powered advice
pip install bist-elite-core[openai]
# or
pip install openai
```

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| **OPENAI_API_KEY** | For `--model openai` | OpenAI API key; never hard-code in code. Obtain from [platform.openai.com](https://platform.openai.com). |
| **USE_OPENAI_MODEL** | Optional | Set to `1` to use OpenAIModel in pipeline advice (e.g. `eod run`) when no explicit model is passed. |
| **BIST_CORE_SNAPSHOT_DIR** | For `local_eod` provider | Root directory for EOD snapshots (e.g. `data/eod/snapshots`). |
| **BIST_CORE_ALLOW_NETWORK** | For HTTP fetches | Set to `1` or `true` to allow outbound HTTP (KAP, vendor APIs). Default is off (fail-closed). |
| **BIST_BROKER_CONFIG** | For live execution | Path to broker config JSON or inline JSON. Required for live mode. |
| **BIST_CORE_CONFIG** | For live mode | Path to core config JSON. Required when running with `--live`. |
| **BIST_RULESPACK_DIR** | For live | Path to BIST rulespack (tick bands, etc.). |
| **BIST_RESTRICTIONS_FILE** | For live | Path to restrictions file. |
| **BIST_INSTRUMENT_MASTER** | Optional | Path to instrument master CSV (symbol resolution). |

### Data Layout Example

```
data/
├── eod/
│   ├── snapshots/           # Market data (snapshot.csv per day)
│   │   └── 2025-01-15/
│   │       └── snapshot.csv
│   └── runs/                # Pipeline output
│       └── 2025-01-15/
│           ├── _pipeline_manifest.json
│           ├── advice/
│           │   └── advice_records.jsonl
│           ├── orders/
│           │   └── orders_intent.json
│           └── dossiers/
```

---

## Workflow

### Step-by-Step EOD Pipeline

#### 1. Generate a Snapshot (Market Data)

You need EOD data for a given date. Either:

- **From data registry:**
  ```bash
  python -m bist_core.cli data register --name eq_daily --path path/to/csvs --format csv --symbol-col symbol --date-col date
  python -m bist_core.cli data snapshot --name eq_daily --day 2025-01-15 --out data/eod/snapshots/2025-01-15/snapshot.csv
  ```
- **Or** place a `snapshot.csv` in `data/eod/snapshots/YYYY-MM-DD/` with columns: `symbol`, `date`, `close` (and optionally `high`, `low`, `volume`).

#### 2. Run the Full EOD Pipeline (Snapshot + Advice + Orders)

Single command for snapshot ingestion, advice, dossiers, and order intent:

```bash
python -m bist_core.cli eod run \
  --day 2025-01-15 \
  --outdir data/eod/runs/2025-01-15
```

With order generation:

```bash
python -m bist_core.cli eod run \
  --day 2025-01-15 \
  --outdir data/eod/runs/2025-01-15 \
  --emit-orders \
  --orders-strategy equal_weight \
  --orders-top-n 10
```

Artifacts:
- `advice/advice_records.jsonl` – scores and sides (BUY/SELL/HOLD)
- `orders/orders_intent.json` – when `--emit-orders`
- `dossiers/` – per-symbol dossiers
- `_pipeline_manifest.json` – pipeline metadata

#### 3. Advice: Default vs AI Model

**Default built-in advisor:**
- Uses `build_advice_for_symbol` (knowledge base, rules, etc.).
- No API key required.
- Used when `--model openai` is not passed and `USE_OPENAI_MODEL` is not set.

**Standalone advice (CLI):**
```bash
# Default advisor
python -m bist_core.cli eod advice --day 2025-01-15 --outdir data/out

# OpenAI model (requires OPENAI_API_KEY)
export OPENAI_API_KEY=sk-...
python -m bist_core.cli eod advice --day 2025-01-15 --outdir data/out --model openai
```

**In full pipeline (`eod run`):**
- Set `USE_OPENAI_MODEL=1` and `OPENAI_API_KEY` to use the AI model in the pipeline advice step.
- Alternatively, use `BIST_CORE_MODEL_PLUGIN=baseline` for the deterministic baseline model.

#### 4. Execute Orders (Paper vs Live)

**Paper execution (simulation):**
```bash
python -m bist_core.cli eod execute \
  --day 2025-01-15 \
  --outdir data/eod/runs/2025-01-15 \
  --execution paper \
  --dry-run
```
- `--dry-run` (default): simulates; no files written.
- Without `--dry-run`: paper provider writes `orders_sent.json`.

**Live execution (real trades):**
- Requires: `--config` (core config), `BIST_BROKER_CONFIG` or `--broker-config`, BIST rulespack, and manifest.

```bash
export BIST_BROKER_CONFIG=/path/to/broker.json
# Or: export BIST_BROKER_CONFIG='{"broker":"stub", ...}'

python -m bist_core.cli eod execute \
  --day 2025-01-15 \
  --outdir data/eod/runs/2025-01-15 \
  --execution live \
  --config /path/to/core_config.json \
  --broker-config /path/to/broker.json
```

The risk gate runs before execution; any denial blocks and returns exit 2.

---

## AI Integration (OpenAI Model)

### How It Works

- **OpenAIModel** implements the `ModelPlugin` interface (`predict(features) -> List[float]`).
- For each symbol and close price, it calls the OpenAI Chat API (GPT-3.5-turbo or GPT-4) with a short prompt.
- It expects a **numeric score** (positive = buy, negative = sell, 0 = hold) and optional reason.
- Parsing supports formats like `"score: 0.5, reason: ..."` or a bare number.
- On parse or API errors, that symbol gets `0.0` (hold).

### Considerations

| Topic | Details |
|-------|---------|
| **API costs** | Each symbol = one API call. Large universes increase cost. Use `--top-n` or limit symbols. |
| **Response time** | Sequential calls; many symbols can take minutes. Batch or async extensions would speed this up. |
| **API key** | Must be set via `OPENAI_API_KEY` env. Never commit keys to source. |
| **Fallback** | Parse failure or API error → score 0.0 for that symbol. |

### Usage

```bash
# Standalone advice with OpenAI
export OPENAI_API_KEY=sk-...
python -m bist_core.cli eod advice --day 2025-01-15 --outdir data/out --model openai

# Pipeline with OpenAI (via env)
export OPENAI_API_KEY=sk-...
export USE_OPENAI_MODEL=1
python -m bist_core.cli eod run --day 2025-01-15 --outdir data/eod/runs/2025-01-15 --emit-orders
```

---

## Best Practices

1. **Test in paper mode first**  
   Run `eod execute --execution paper` (or `--dry-run`) before live.

2. **Combine AI with built-in rules**  
   AI scores still go through risk gates, restrictions, and tick bands. Use rules to constrain and validate.

3. **Ensure data quality**  
   Snapshot columns (`symbol`, `date`, `close`) must be correct. Bad data leads to bad advice.

4. **Limit universe when using OpenAI**  
   Use `--top-n`, `--symbols`, or `--limit` to keep API calls and costs manageable.

5. **Review manifests**  
   Check `_pipeline_manifest.json` and `execution_result.json` for errors and blocked reasons.

6. **Use versioned configs**  
   Keep configs, rulespacks, and broker configs in version control for reproducibility.

---

## Extensibility

The system uses **plugin-style registries** so you can extend it without changing the core.

| Extension point | How |
|-----------------|-----|
| **New market data provider** | `register_market_data_provider(name, factory)` in `bist_core.market_data.registry`. Factory: `(*, snapshot_root, **kwargs) -> MarketDataProvider`. |
| **New execution provider** | `register_execution_provider(name, factory)` in `bist_core.execution.adapters.registry`. For live brokers. |
| **New AI model** | Implement `ModelPlugin` (`predict(features) -> List[float]`). Pass to `generate_advice(..., model_plugin=...)` or wire via CLI. |
| **New order strategy** | Add strategy to `bist_core.strategies.registry` and use `--orders-strategy NAME`. |

See `INTEGRATION_PLAYBOOK.md` for registry details and fail-closed rules.
