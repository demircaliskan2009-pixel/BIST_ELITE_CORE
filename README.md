![CI](https://github.com/<user>/<repo>/actions/workflows/ci.yml/badge.svg)
**Faz-3 / Adım-1: TAMAMLANDI** — local CSV ingest + dataset registry + smoke tests
# BIST_ELITE_CORE — Minimal Working Core
Runs offline on CSVs; plug-in ready for vendors and brokers.

**Windows / Git:** Use `git config core.autocrlf false` so line endings stay LF (see [docs/DEV_SETUP_WINDOWS.md](docs/DEV_SETUP_WINDOWS.md)).

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
