# Core Golden Path

## EOD run (single day)
Run:
```
python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD
python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD --policy-file path/to/rules.json
python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD --emit-orders --orders-strategy equal_weight --orders-top-n 10
```
Artifacts land under `data/eod/runs/YYYY-MM-DD/`:
- `_pipeline_manifest.json`
- `advice.jsonl` (or `advice.json` if `--no-jsonl`)
- `dossiers/` with per-symbol JSON + `_manifest.json`
- `orders/orders_intent.json` when `--emit-orders`

## Strategy selection (orders intent)
Use `--orders-strategy NAME` (default `equal_weight`). For top-N limiting, use `--orders-top-n N`.

## EOD batch (date range)
Run:
```
python -m bist_core.cli eod batch --from YYYY-MM-DD --to YYYY-MM-DD --outdir data/eod/batch/YYYY-MM-DD_to_YYYY-MM-DD
```
Artifacts land under the batch outdir:
- `_index_manifest.json`
- per-day folders (`YYYY-MM-DD/`) with pipeline outputs

## Audit
Run:
```
python -m bist_core.cli eod batch --audit --outdir <batch_outdir>
python -m bist_core.cli eod batch --deep-audit --outdir <batch_outdir>
```
Audit writes `_audit_manifest.json` in the batch outdir and reports errors deterministically.

## Replay (offline backtest)
Run:
```
python -m bist_core.cli eod replay --from YYYY-MM-DD --to YYYY-MM-DD --outdir data/eod/replay/YYYY-MM-DD_to_YYYY-MM-DD --snapshot-root data/eod/snapshots
python -m bist_core.cli eod replay --from YYYY-MM-DD --to YYYY-MM-DD --outdir data/eod/replay/YYYY-MM-DD_to_YYYY-MM-DD --emit-orders --orders-strategy equal_weight --orders-top-n 10
```
Replay writes:
- `_replay_manifest.json` in the replay outdir
- `metrics.json` (unless `--no-metrics`)
- `scorecard.json` (unless `--no-scorecard`)
- per-day folders (`YYYY-MM-DD/`) with pipeline outputs

## Data registry and snapshot

Run:

~~~bash
python -m bist_core.cli data register --name eq_daily --path path/to/csvs --format csv --symbol-col symbol --date-col date
python -m bist_core.cli data list --json
python -m bist_core.cli data load --name eq_daily --json
python -m bist_core.cli data snapshot --name eq_daily --day YYYY-MM-DD --out data/eod/snapshots/eq_daily_YYYY-MM-DD.csv
~~~

## Rules validation and explanation

Run:

```bash
python -m bist_core.cli rules validate --file path/to/rules.json
python -m bist_core.cli rules validate --file src/bist_core/policy/bist_ruleset.example.json
python -m bist_core.cli rules explain --file path/to/rules.json --symbol AAA --price 10 --side BUY --qty 100 --day YYYY-MM-DD
```

## Expected artifacts (when enabled)
- `dossiers/` per-symbol outputs with `_manifest.json`
- `orders/orders_intent.json` when `--emit-orders`
- `scorecard.json` in replay outdir when `--scorecard`

## Strict behavior
- `--strict` returns exit code `2` on any gate or validation error.
- Manifests include error lists and notes to diagnose failures.

## Determinism / fail-closed expectations
- Outputs are deterministic for the same inputs (sorted symbols, stable notes).
- Policy validation is fail-closed under `--strict`.
- Orders intent is blocked when policy denies trading, with notes indicating the block.
