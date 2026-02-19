# BIST_ELITE_CORE — Minimal Working Core

Runs offline on CSVs; plug-in ready for vendors and brokers. BIST-only advisory, equal-weight plan/orders, EOD pipeline.

**Before merge:** Run `.\proof_pack.ps1` — must pass (alignment, hygiene, full pytest).

---

## Quick Start

```powershell
# 1. Clone and install
git clone <repo>
cd BIST_ELITE_CORE
.\install.ps1

# 2. Validate environment
.\run.ps1 doctor

# 3. Run proof pack (alignment + hygiene + all tests)
.\proof_pack.ps1
```

**Windows / Git:** Use `git config core.autocrlf false` so line endings stay LF (see [docs/DEV_SETUP_WINDOWS.md](docs/DEV_SETUP_WINDOWS.md)).

### Scripts
| Script | Purpose |
|--------|---------|
| `.\install.ps1` | Editable install; `-Dev` for dev deps |
| `.\run.ps1 <cmd>` | Run CLI (e.g. `.\run.ps1 ask ASELS --day 2025-01-15 --json`) |
| `.\proof_pack.ps1` | Alignment gate + hygiene + full pytest |

### Faz-2: CLI akışı (eod → plan → orders)

```bash
# 1) EOD (snapshot) üretir → data/eod/snapshots/YYYY-MM-DD/snapshot.csv
python -m bist_core.cli.main eod    --date 2025-01-15

# 2) Eşit ağırlık planı → plan_equal_weight.csv  (header: symbol,weight)
python -m bist_core.cli.main plan   --date 2025-01-15

# 3) Risk kapılı siparişler → orders_equal_weight.csv (header: symbol,target_weight)
#    Meta PASS/FAIL: orders_meta.txt    Exit code: PASS=0, FAIL=2
python -m bist_core.cli.main orders --date 2025-01-15
```

### Snapshot CSV kontratı (CLI ask)
- Legacy (kabul): `symbol,close`
- New (kabul): `symbol,close,date`
- Optional kolonlar: `open,high,low,volume,turnover`
- Bozuk header: fail-closed (nonzero exit + mesaj)

```bash
python -m bist_core.cli ask ASELS --day 2099-01-01
python -m bist_core.cli ask ASELS --day 2099-01-01 --json
```

### EOD pipeline (snapshot → advice → dossier)
Snapshot kontratı için yukarıdaki bölüme bakın.

```bash
python -m bist_core.cli eod run --day 2099-01-01 --outdir data/eod/runs/2099-01-01
```

### Events (KAP) sözleşmesi ve ingest
Event kayıtları `symbol, ts, kind, title` alanlarını içerir. (Kısa JSONL veya JSON array.)

```bash
python -m bist_core.cli events pull --day 2099-01-01 --provider offline_file --input sample_events.jsonl --outdir data/eod/events/2099-01-01
python -m bist_core.cli events ingest --day 2099-01-01 --input data/eod/events/2099-01-01/events.jsonl
python -m bist_core.cli events pull --day 2099-01-01 --provider kap_html --url-template "/kap_sample.html" --outdir data/eod/events/2099-01-01
```

### Instruments (master v1)
Instrument kayıtları `symbol, isin, name, status, listing_start, listing_end, market, source, ts` alanlarını içerir.

```bash
python -m bist_core.cli instruments pull --day 2099-01-01 --provider offline_file --input sample_instruments.jsonl --outdir data/eod/instruments/2099-01-01
python -m bist_core.cli instruments ingest --day 2099-01-01 --input data/eod/instruments/2099-01-01/instruments.jsonl
```

### Universe / instrument timeline
```bash
python -m bist_core.cli corporate-actions pull --day 2099-01-01 --provider offline_file --input sample_actions.jsonl --outdir data/eod/corporate_actions/2099-01-01
python -m bist_core.cli instruments timeline --day 2099-01-01 --instruments-dir data/eod/instruments/2099-01-01 --ca-dir data/eod/corporate_actions/2099-01-01 --outdir data/eod/universe/2099-01-01
python -m bist_core.cli eod run --day 2099-01-01 --outdir data/eod/runs/2099-01-01 --instruments-provider offline_file --instruments-input sample_instruments.jsonl --ca-provider offline_file --ca-input sample_actions.jsonl
```

### Advisory Quickstart (BIST-only)

Minimal akış: snapshot → advice → ask → top N.

1. **Snapshot üretimi** — `data/eod/snapshots/YYYY-MM-DD/snapshot.csv` (symbol, close, date; opsiyonel: open, high, low, volume)
   ```bash
   python -m bist_core.cli data snapshot --name eq_daily --day YYYY-MM-DD --out data/eod/snapshots/YYYY-MM-DD/snapshot.csv
   ```
   veya CSV’yi elle yerleştirin.

2. **EOD run** — Snapshot + advice + dossiers
   ```bash
   python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD
   ```

3. **Ask (interaktif)** — Tek sembol danışma; eksik parametreler sorulur
   ```bash
   python -m bist_core.cli ask ASELS --day YYYY-MM-DD --interactive
   ```
   Parametreler: `--horizon`, `--risk`, `--capital`, `--max-loss-tl`

4. **Top N (en mantıklı hisseler)** — Skor sıralı ilk N
   ```bash
   python -m bist_core.cli eod advice --day YYYY-MM-DD --outdir data/out --top-n 10
   ```

5. **Çıktı yapısı (outdir)**
   ```
   data/eod/runs/YYYY-MM-DD/
   ├── _pipeline_manifest.json
   ├── advice/
   │   └── YYYY-MM-DD/
   │       └── advice_records.jsonl
   ├── dossier/
   │   └── YYYY-MM-DD/
   │       └── dossier.json
   ├── dossiers/
   │   └── *.json (sembol bazlı)
   └── orders/
       └── YYYY-MM-DD/
           └── orders_intent.json  (--emit-orders ile)
   ```

### Strategy registry and performance (faz561–faz563)

Each `ask` and `scan` appends a record to the strategy log. Outcomes are evaluated against snapshot data; a performance report summarizes win-rate, avg R, and max drawdown.

| Path / Env | Purpose |
|------------|---------|
| `data/log/strategies.jsonl` | Strategy log (symbol, day, params, plan). Override: `BIST_CORE_STRATEGY_LOG` |
| `data/log/strategy_outcomes.jsonl` | Evaluated outcomes (win/loss/timeout, R-multiple). Override: `BIST_CORE_STRATEGY_OUTCOMES` |
| `BIST_CORE_OUTCOME_MAX_HOLD_DAYS` | Max holding period before timeout (default: 30) |

```bash
# Evaluate logged strategies against snapshots
python -m bist_core.cli evaluate-outcomes --strategies data/log/strategies.jsonl --snapshot-root data/eod/snapshots

# Generate performance summary (win-rate, avg R, max DD, equity curve)
python -m bist_core.cli performance-report --outcomes data/log/strategy_outcomes.jsonl --out data/log/performance.json
python -m bist_core.cli performance-report --outcomes data/log/strategy_outcomes.jsonl --out report.csv --csv
```

### Live test v1 (faz566)

Single-command daily runner for offline manual workflow: scan → ask → evaluate → report.

```powershell
.\tools\live_daily.ps1 -Day 2025-01-15 -TopN 5 -OutRoot "data/log" -SnapshotRoot "data/eod/snapshots"
```

**Outputs** (under `data/log/` or `-OutRoot`):

| Path | Contents |
|------|----------|
| `daily_scan/<DAY>/scan.json` | TOP-N ranked symbols |
| `daily_scan/<DAY>/strategies.jsonl` | Logged strategies |
| `ask/<DAY>/<SYMBOL>.json` | Ask artifacts per symbol |
| `outcomes/<DAY>/strategy_outcomes.jsonl` | Evaluated outcomes |
| `reports/<DAY>/performance.json` | Win-rate, avg R, max DD |
| `reports/<DAY>/performance.csv` | Same metrics in CSV |

**Workflow:** Run the script → read TOP5 from stdout or `scan.json` → pick a symbol → open `ask/<DAY>/<SYMBOL>.json` for plan. Offline, manual execution only.

**Ops pack (faz567):** Validate before run (`.\tools\live_validate.ps1`), today runner (`.\tools\live_today.ps1`), trade journal report. See [docs/LIVE_TEST_PLAYBOOK.md](docs/LIVE_TEST_PLAYBOOK.md).

### Live Test Release Branch (faz568)

During the 6‑month live test, use **`release/live-test-v1`** for daily runs. `main` can evolve; only cherry-pick hotfixes into the release branch.

```powershell
# Cherry-pick a hotfix from main
git checkout release/live-test-v1
git cherry-pick <sha>
.\tools\proof_pack.ps1
git push origin release/live-test-v1
```

**Pre-push gate:** Run `.\tools\pre_push_gate.ps1` before pushing. See [docs/RELEASE_POLICY.md](docs/RELEASE_POLICY.md).

---

## Docs

| Doc | Purpose |
|-----|---------|
| [docs/AI_SDK.md](docs/AI_SDK.md) | SDK for ChatGPT/AI integration (ask, scan, version) |
| [docs/CHAT_AGENT_FLOW.md](docs/CHAT_AGENT_FLOW.md) | Chat agent pseudo-code and tool definitions |
| [docs/DEV_SETUP_WINDOWS.md](docs/DEV_SETUP_WINDOWS.md) | Line endings, Git config |
| [docs/WINDOWS_PROD_RUNBOOK.md](docs/WINDOWS_PROD_RUNBOOK.md) | Production runbook |
| [docs/LIVE_TEST_PLAYBOOK.md](docs/LIVE_TEST_PLAYBOOK.md) | Live test ops pack, daily routine |
| [docs/RELEASE_POLICY.md](docs/RELEASE_POLICY.md) | Branch model, tags, hotfix promotion rules |
| [docs/TAGGING.md](docs/TAGGING.md) | Safe tag push (no clobber) |
| [docs/INTEGRATION_READY.md](docs/INTEGRATION_READY.md) | Broker adapter contract, dry-run, integration readiness |
