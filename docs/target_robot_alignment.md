# Target / Robot Alignment

Checklist and Definition of Done for release and automation alignment.

## Checklist

- [x] Core EOD pipeline (run, batch, replay) documented and gated
- [x] Live execute path fail-closed (config, broker, BIST rules, manifest, orders_intent)
- [x] Execution result and dossier evidence written on all exit paths
- [x] Alignment verification script runs in CI (`scripts/verify_alignment.py`)

## Definition of Done (DoD)

- All checklist items above are checked.
- `python scripts/verify_alignment.py` exits 0 when run from repo root.
- CI runs the alignment gate (pytest `test_faz83_alignment_gate` and/or verify script).
