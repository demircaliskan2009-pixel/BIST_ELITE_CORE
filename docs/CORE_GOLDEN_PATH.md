# Core Golden Path

## EOD run (single day)
Run:
```
python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD
```
Artifacts land under `data/eod/runs/YYYY-MM-DD/`:
- `_pipeline_manifest.json`
- `advice.jsonl` (or `advice.json` if `--no-jsonl`)
- `dossiers/` with per-symbol JSON + `_manifest.json`

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

## Strict behavior
- `--strict` returns exit code `2` on any gate or validation error.
- Manifests include error lists and notes to diagnose failures.
