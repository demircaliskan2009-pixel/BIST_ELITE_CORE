# Release Process

Checklist and steps for releasing BIST_ELITE_CORE.

## Checklist

- [ ] Full tests pass (`python -m pytest -q tests/`)
- [ ] Alignment gate passes (`python scripts/verify_alignment.py`)
- [ ] Artifacts schema check passes (config/strategy.json, config/core.json valid)
- [ ] Release check passes (`python tools/release_check.py`)

## Steps

1. **From repo root**, run the release check:

   ```bash
   python tools/release_check.py
   ```

   This runs: full tests, alignment gate (docs/target_robot_alignment.md checklist), and artifacts schema (config JSON files present and valid).

2. If any step fails, fix before tagging. Exit code 0 = all pass, 2 = one or more failed.

3. Optional: run subsets for faster iteration:

   - `python tools/release_check.py --alignment-only` — alignment gate only
   - `python tools/release_check.py --schema-only` — artifacts schema only
   - `python tools/release_check.py --tests-only` — full tests only

4. Tag and push when the release check passes.

## Definition of Done

- `python tools/release_check.py` exits 0 when run from repo root.
- CI (or local) runs the release check before release; test `test_faz96_release_check` validates the script contract.
