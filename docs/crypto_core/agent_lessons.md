# crypto_core Agent Lessons Ledger

> Durable, evidence-backed lessons distilled from real `crypto_core` PR failures and repairs. Canonical
> doctrine is `AGENTS.md` + `docs/crypto_core/agent_workflow.md` + `.codex/skills/crypto-core-max-safe/SKILL.md`;
> this file is the **lessons companion** they reference. Every lesson cites the PR / commit / failure mode
> that proves it. No secrets, credentials, API keys, or live-trading instructions. crypto_core only — BIST is
> historical context.

## How this ledger is maintained (controlled self-improvement loop)

1. **Emit.** Each real P1/P2 (Codex finding, CI failure, or post-merge defect) emits a `LESSON_CANDIDATE`
   in the task's ChatGPT handoff block, with evidence: `PR #<n>`, `commit <sha>`, and the exact failure mode
   / asserting test.
2. **Triage.** The ChatGPT controller decides whether the candidate is **durable, generalizable, and
   proven** (not a one-off). Transient branch/CI/commit state is never a durable lesson.
3. **Persist.** Accepted lessons are added here **only in a separate setup PR** (branch `chore/<scope>-prN`),
   never mixed into a feature PR.
4. **Constraints.** No lesson may weaken a safety gate (§ Hard Rules in `agent_workflow.md`). Stale or
   conflicting instructions are removed or repointed to canonical doctrine. No automatic self-modification
   during feature PRs.

`LESSON_CANDIDATE` shape (emit in the handoff block):

```
LESSON_CANDIDATE: <one-line lesson>
EVIDENCE: PR #<n> · commit <sha> · <failure mode / asserting test>
GENERALIZABLE: yes|no — <why>
```

## Digest / provenance lessons (PR #287, PR #288)

Evidence: PR #287 (paper session realized-PnL aggregate) and PR #288 (paper PnL evidence manifest, merge
commit `1890d2b`; repair commits `1cd2799` scope-binding, `ec95c4e` lossy-container).

- **Single canonical snapshot for digest-bound consumers.** A consumer of a digest-carrying artifact
  serializes the upstream object **exactly once** via the public serializer and round-trips it through
  canonical JSON into exact plain primitives; every bound field, the digest recompute, and identity/dedup
  reads come from that one snapshot. (PR #288 single-snapshot manifest.)
- **No double serialization / re-read after snapshot capture.** Re-reading the source object (for digest vs
  identity vs totals) opens a TOCTOU window where a stateful/mutable source diverges between reads. Recompute
  the digest **from the snapshot**, never via a second read or the public digest helper. (PR #287 stateful
  rollup/event TOCTOU; PR #288 AST guard that the manifest never imports/calls the public aggregate digest
  helper.)
- **Expected digest is a trust anchor, not independent economic proof.** A caller-supplied
  `expected_aggregate_digest` proves the caller's intent/provenance; it does **not** make the consumer an
  independent tamper-proof of upstream economics. Record it, bind it into the consumer digest, and say so
  explicitly. (PR #288 `expected_aggregate_digest` output binding + trust-boundary docstring.)
- **Do not overclaim full-payload equality** unless an independent expected payload exists. Claim only what
  is actually recomputed/compared. (PR #288 docstring correction.)
- **Canonical primitive identity before hashing / set membership.** Normalize identity fields to exact plain
  `str` (round-trip through canonical JSON) before set/tuple dedup. (PR #287 `_SplitHashStr` custom-hash
  bypass.)
- **Defend against `str`-subclass / custom-hash bypass.** Content-equal but hash-divergent `str` subclasses
  must not slip duplicates past dedup; use `type(x) is str`, not `isinstance`, where primitive identity
  matters. (PR #287.)
- **Finite, canonical Decimal validation before READY.** Reject NaN/Infinity/scientific/empty/non-canonical
  decimal strings; preserve canonical zero `"0"`; never `Decimal.normalize()`; span-aware precision for exact
  sums. (PR #287/#288 totals.)
- **Aggregate / provenance serializers must reject malformed or lossy containers before snapshot/digest.**
  A blind `list(...)` over `metadata` / `reason_codes` / provenance containers silently collapses malformed
  input into valid-looking, collision-prone payloads. Enforce exact shape (e.g. `metadata` = tuple/list of
  exactly-two-item `[str,str]` pairs with unique keys; `reason_codes` = canonical empty sequence) and raise
  **before** any snapshot/digest. (PR #288 `ec95c4e`: `metadata={"li":"scheduler"}` → `["l","i"]` lost the
  value; `reason_codes=""`/`{}`/`set()` → `[]`.)
- **No blind `list(...)` on `metadata` / `reason_codes` / provenance containers** anywhere a digest is
  derived. (PR #288 `ec95c4e`.)
- **Hidden malformed values must not collapse into identical digest snapshots.** Two different hidden values
  must never produce the same snapshot/digest; prove both fail closed (or both produce distinct artifacts).
  (PR #288 collision-prevention tests.)
- **TOCTOU / manual adversarial tests are required for digest-bound consumers.** Beyond happy-path: a
  tampered field, a resealed-but-inconsistent artifact, a stateful/mutable source, and a `str`-subclass hash
  bypass. (PR #287/#288 adversarial test suites.)

## Process / workflow lessons

- **CI no-register events require diagnosis before any empty re-trigger.** When GitHub Actions creates no
  run for a fresh head, first prove it via `gh run list` / commit `check-runs` (classify
  `ACTIONS_DELAY_OR_GITHUB_INFRA` vs trigger/path/ref issue). Only **one** empty re-trigger commit
  (`chore(crypto-core): retrigger …`), and **only** with explicit user/controller authorization; never a
  loop of no-op commits. (PR #287 and PR #288 `ec95c4e` → `31c9ca8` re-trigger.)
- **Setup doctrine updates happen only in setup PRs, never mixed into feature PRs.** Feature PRs change
  `src/`/`tests/` product code; setup PRs change docs/config only. (This ledger was created in a dedicated
  `chore/crypto-core-agent-workflow-*` PR.)
- **One open PR at a time; no direct main push; standard merge only; no merge without explicit per-PR
  authorization.** Unchanged hard rails — restated so lessons never erode them.
- **Repository process invariants must be enforced by configuration where possible, not merely repeated in
  prompts.** While governed feature PR #342 was active, Dependabot automatically opened scheduled
  version-update PRs #343 (github-actions, `actions/setup-python` 5→7) and #344 (pip, `typer` bump in the
  `python-version-updates` group), producing concurrently open PRs that violated the one-open-PR operating
  invariant; both were closed without merge to restore it. This was a **configuration/process collision**,
  not a Dependabot policy breach or a dismissed security finding. Durable repair: `open-pull-requests-limit:
  0` on both configured ecosystems in `.github/dependabot.yml`, which disables scheduled **version-update**
  PR generation while **retaining Dependabot alerts and security-update PRs**. Dependency version maintenance
  now occurs only in a dedicated controller-selected maintenance window with zero pre-existing open PRs; an
  automatically generated security-update PR still requires immediate controller triage but never silently
  waives one-open-PR. (PR #342 active feature PR · PR #343/#344 scheduled version updates closed without
  merge · `.github/dependabot.yml` `open-pull-requests-limit: 0` · `agent_workflow.md` §3 "Dependabot
  collision prevention".)
- **Deep Research is a high-leverage architecture/benchmark/current-fact tool — especially paired with
  GitHub-connector repo evidence — but it guides bounded PR sequencing; it never bypasses local proof
  gates.** Use it for external/current facts (exchange/API/funding/fees/limits/microstructure/custody/
  regulation/security, Deribit/readiness/live/shadow), PRD/roadmap-vs-external-benchmark questions, and
  overengineering detection; not for local repo/PR/CI state, merge authority, local repair, or to
  replace Codex review. In connector chat it must separate `REPO_EVIDENCE` / `EXTERNAL_EVIDENCE` /
  `INFERENCE` / `UNKNOWN` and never infer live repo state without GitHub evidence. **Strictly read-only /
  advisory: it never executes a repo/GitHub mutation (branch/file/commit/push/PR/comment/thread-resolve/
  workflow-rerun/merge/auto-merge), even when the underlying work is authorized — it may only recommend a
  mutation task, and the controller routes any authorized mutation to Claude/`gh`, the connector, or
  Codex.** Never an executor lane, never a merge or safety-gate waiver. Full protocol:
  `docs/crypto_core/deep_research_protocol.md`
  (`agent_workflow.md` §19).
