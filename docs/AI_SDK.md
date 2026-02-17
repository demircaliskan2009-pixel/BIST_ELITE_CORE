# BIST Elite Core — SDK for AI/Chat Integration

**Version:** 1  
**Schema:** All JSON responses include `schema_version` where applicable.

## Overview

BIST Elite Core exposes CLI commands and JSON API endpoints for BIST equity advisory. Use these as tool definitions for ChatGPT, Claude, or custom chat agents.

---

## CLI as SDK Functions

### 1. `ask` — Single-symbol advice

**CLI:** `python -m bist_core.cli ask <SYMBOL> --day YYYY-MM-DD --json`

**API:** `POST /ask`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| symbol | str | yes | BIST symbol (2–6 chars, uppercase) |
| day | str | no | YYYY-MM-DD; default: latest snapshot |
| horizon | str | no | short \| mid \| long |
| risk | str | no | low \| med \| high |
| capital | float | no | Portfolio capital (TL) |
| max_loss_tl | float | no | Max loss per trade (TL) |

**Response:** `{ symbol, day, decision_raw, score, text }`

---

### 2. `scan` — Ranked symbol list

**CLI:** `python -m bist_core.cli scan --day YYYY-MM-DD --top-n N --json`

**API:** `POST /scan`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| day | str | no | YYYY-MM-DD; default: latest snapshot |
| top_n | int | no | Default 10, max 100 |
| horizon | str | no | short \| mid \| long |
| risk | str | no | low \| med \| high |
| capital | float | no | Portfolio capital (TL) |
| max_loss_tl | float | no | Max loss per trade (TL) |
| exclusions | str | no | Comma-separated symbols to exclude |

**Response:** `{ schema_version, day, generated_at, ranked: [{ symbol, score, rationale }] }`

---

### 3. `plan` — Equal-weight plan

**CLI:** `python -m bist_core.cli plan --date YYYY-MM-DD`

**Output:** Writes `plan_equal_weight.csv` under snapshot root.

| Param | Type | Required |
|-------|------|----------|
| date | str | yes | YYYY-MM-DD |

---

### 4. `orders` — Risk-gated orders

**CLI:** `python -m bist_core.cli orders --date YYYY-MM-DD [--out DIR]`

**Output:** Writes `orders_equal_weight.csv`, `orders_meta.txt` (PASS/FAIL).

| Param | Type | Required |
|-------|------|----------|
| date | str | yes | YYYY-MM-DD |
| out | str | no | Output directory |

---

### 5. `healthcheck` — Environment validation

**CLI:** `python -m bist_core.cli healthcheck`

**API:** `GET /health`

**Response:** `{ status: "ok" }` or health checks JSON.

---

### 6. `market-data validate` — Snapshot validation

**CLI:** `python -m bist_core.cli market-data validate --day YYYY-MM-DD [--snapshot-root PATH]`

**Response:** `ok: <message>` or error.

---

## JSON API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Liveness |
| GET | /version | API version and schema_version |
| POST | /ask | Single-symbol advice |
| POST | /scan | Ranked scan |

**Base URL:** `http://localhost:8000` (uvicorn)

**Constraints:**
- Offline only: `BIST_CORE_ALLOW_NETWORK` must not be set
- BIST symbols only: 2–6 uppercase alphanumeric
- `BIST_CORE_SNAPSHOT_DIR`: snapshot root

---

## Environment Variables

| Variable | Purpose |
|---------|---------|
| BIST_CORE_SNAPSHOT_DIR | Snapshot root (default: data/eod/snapshots) |
| BIST_CORE_REGISTRY_PATH | Dataset registry path |
| BIST_CORE_ALLOW_NETWORK | Must be unset for API (offline only) |
