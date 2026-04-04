# Release Policy

Branch model and promotion rules for the 6‑month live test.

## Branch model

| Branch | Purpose |
|--------|---------|
| `main` | Development. New features, refactors, experiments. |
| `release/live-test-v1` | Frozen baseline for live test. Only hotfixes via cherry-pick. |

## Tags

- **faz###** — Always point to `main` commits. Do not move or rewrite.
- **Release tags** — Optional (e.g. `live-test-v1.0`). May point to `release/live-test-v1`.

**Rule:** Do not rewrite tags. Once pushed, tags are immutable.

## Hotfix promotion

Only cherry-pick into `release/live-test-v1` when:

- **Bugs** — Fixes that correct incorrect behavior.
- **Determinism** — Fixes that restore deterministic outputs.
- **Docs** — Clarifications, runbooks, policy updates.
- **Ops scripts** — Validation, gates, tooling (no strategy logic).

**Do not cherry-pick:**

- Strategy logic changes.
- New advisory/scan behavior.
- Breaking changes to data contracts.

## Cherry-pick flow

```powershell
git checkout release/live-test-v1
git cherry-pick <sha>
.\tools\proof_pack.ps1
git push origin release/live-test-v1
```

If proof_pack fails, resolve before pushing.
