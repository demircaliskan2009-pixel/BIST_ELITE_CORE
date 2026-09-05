# crypto_core Agent Lessons Ledger

<!-- CONTROL_PLANE_ROLE: LESSONS_COMPANION -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> Durable, evidence-backed lessons distilled from real `crypto_core` failures and repairs. This file
> is a COMPANION: it defines no routing, task family, effort, PR sizing or merge authority, and it is
> MODEL-AGNOSTIC in its active region — a lesson that only holds for one vendor's tooling is not a
> durable lesson. The canonical authority is `docs/crypto_core/agent_os_v2.md`.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.
>
> The dated evidence ledger — with its exact PR, commit and failure-mode citations — lives in the
> bounded historical record at the end of this file. Those citations are point-in-time evidence, not
> current state, which is why they are structurally separated from the durable rules above them.
> No secrets, credentials, API keys or live-trading instructions. crypto_core only.

## How this ledger is maintained

1. **Emit.** Each real P1/P2 — an independent-review finding, a CI failure, or a post-merge defect —
   emits a `LESSON_CANDIDATE` in the task's handoff block, with evidence: the PR, the commit, and the
   exact failure mode or asserting test.
2. **Triage.** The controller decides whether the candidate is durable, generalizable and proven, and
   whether it survives being restated without naming any tool. Transient branch, CI or commit state
   is never a durable lesson.
3. **Persist.** An accepted lesson is added here ONLY in a separate setup PR on a `chore/<scope>-prN`
   branch, never mixed into a feature PR. The durable rule goes in the active region; its dated
   citation goes in the historical record.
4. **Constrain.** No lesson may weaken a safety gate. No automatic self-modification during a feature
   PR. Stale or conflicting instructions are removed or repointed to canonical doctrine.

`LESSON_CANDIDATE` shape, emitted in the handoff block:

```
LESSON_CANDIDATE: <one-line lesson>
EVIDENCE: <PR> | <commit> | <failure mode / asserting test>
GENERALIZABLE: yes|no - <why>
```

## Durable rules

### Digest and provenance

- **One canonical snapshot per digest-bound consumer.** Serialize the upstream object exactly once
  through the public serializer, round-trip it through canonical JSON into exact plain primitives, and
  take every bound field, the digest recompute and every identity or dedup read from that single
  snapshot.
- **No second read after the snapshot.** Re-reading the source for digest, identity or totals opens a
  time-of-check/time-of-use window in which a stateful or mutable source diverges between reads.
  Recompute the digest FROM the snapshot, never via a second read and never via the public digest
  helper.
- **An expected digest is a trust anchor, not independent economic proof.** A caller-supplied expected
  digest proves the caller's intent and provenance; it does not make the consumer an independent
  tamper-proof of upstream economics. Record it, bind it into the consumer digest, and say so
  explicitly.
- **Claim only what is actually recomputed.** Never claim full-payload equality unless an independent
  expected payload exists to compare against.
- **Canonicalize primitive identity before hashing or set membership.** Normalize identity fields to
  exact plain strings, round-tripped through canonical JSON, before any set or tuple dedup.
- **Defend against subclass and custom-hash bypass.** Content-equal but hash-divergent string
  subclasses must not slip duplicates past dedup. Where primitive identity matters, test the exact
  type rather than an instance check.
- **Finite, canonical decimal validation before READY.** Reject NaN, infinity, scientific and empty or
  non-canonical decimal strings; preserve canonical zero; never normalize away scale; use span-aware
  precision for exact sums.
- **Reject malformed or lossy containers before the snapshot.** A blind list conversion over metadata,
  reason codes or a provenance container silently collapses malformed input into valid-looking,
  collision-prone payloads. Enforce the exact shape and raise BEFORE any snapshot or digest.
- **Two different hidden values must never collapse into one digest.** Prove that both fail closed, or
  that both produce distinct artifacts.
- **Adversarial tests are mandatory for a digest-bound consumer.** Beyond the happy path: a tampered
  field, a resealed but inconsistent artifact, a stateful or mutable source, and a hash-bypass
  subclass.

### Process and workflow

- **Diagnose a CI no-register event before any empty re-trigger.** When no run is created for a fresh
  head, prove it from the run list or the commit check-runs and classify infrastructure delay against
  a trigger, path or ref problem. At most ONE empty re-trigger commit, and only with explicit
  authorization. Never loop no-op commits.
- **Setup doctrine changes happen only in setup PRs.** Feature PRs change product code; setup PRs
  change docs and configuration. Mixing them makes independent review harder and hides scope.
- **One open PR, one repository writer, no direct `main` push, standard merge only, and no merge
  without explicit per-PR human authorization.** Restated here so no lesson erodes it.
- **Enforce a process invariant in configuration, not only in prose.** Repeating a rule in prompts
  does not stop an automated agent from breaking it. When scheduled dependency-update automation
  opened concurrent PRs during an active governed feature PR, the durable repair was a configuration
  change that disables scheduled version-update PR generation while retaining alerts and
  security-update PRs — not another paragraph of instruction. Dependency maintenance now happens only
  in a dedicated window with zero pre-existing open PRs; an automatically generated security-update PR
  still requires triage but never silently waives the one-open-PR invariant.
- **Research guides sequencing; it never bypasses a local proof gate.** External and current-fact
  research is high leverage for architecture, benchmarks and venue facts, and worthless as a substitute
  for local repository, PR or CI state. It is strictly read-only: it never mutates repository or GitHub
  state even when the underlying work is authorized, it never replaces an independent audit, and it
  never waives a safety gate. It separates proven repository evidence, proven external evidence,
  inference and `UNKNOWN`, and never infers live state without live evidence.
- **A deterministic validator proves structure, not meaning.** When a structural gate starts growing
  synonym patterns to chase natural-language paraphrase, that is the signal to fix the abstraction —
  make the contract machine-readable and singular — and to leave arbitrary semantic contradiction to
  the independent audit. Chasing paraphrase with more patterns is the failure mode, not the fix.
- **A fail-open gate is worse than no gate.** A checker that silently skips its subject when a heading
  is renamed, or that always exits zero, converts a real gate into decoration. Region boundaries are
  explicit structural markers, an unterminated region fails closed, and a deterministic contract
  failure exits non-zero.
- **A blocker keeps its identity across renames.** Restating a blocker in different words, or opening a
  nominally new but equivalently scoped phase, does not reset its repair counter and does not grant a
  fresh repair budget.
- **A restriction that belongs to one case must never be written as a restriction on the mechanism.**
  A rule scoped to one task family, restated as a rule about the effort level itself, silently made
  three documented escalation branches unreachable. Scope the restriction where it belongs and make
  the per-case table the authority.
- **What a host DISCOVERS beats what a registry DECLARES.** A registry decides authority; it does not
  decide what gets loaded. A file in a conventional auto-discovery directory is loaded whatever the
  registry says, so "unregistered therefore inert" is false. Such a path must be registered with a
  safe role or absent, and a wrapper on a discoverable path is still discoverable.
- **An oracle cannot be its own only anchor.** When the independent check is itself listed in the
  mutable registry it validates, deleting both together leaves a self-consistent system with nothing
  checking it. Anchor the requirement from outside the registry.
- **A lexical co-occurrence check is not an enforcement gate.** Accepting a command because its path
  appears somewhere admits an echoed command, an appended fallback, a comment and a disabled job -
  each contains the path and enforces nothing. Require one dedicated step whose executable content is
  exactly the command, rather than trying to understand shell.
- **A shared depth counter cannot parse typed regions.** With one counter an opener of one type can be
  closed by a closer of another, leaving the rest of a file silently exempt. Carry the exact type on a
  stack and require the closer to match.
- **Topology is not semantics.** Proving that an evidence companion EXISTS does not prove the pair
  means anything: a value with UNKNOWN evidence, a null with PROVEN, or a continuation mode chosen
  while the capacity it depends on was never proven all satisfy a structural check and are all false.
  Enforce the relation, not the shape.

<!-- HISTORICAL_RECORD_BEGIN -->

## Dated evidence ledger

Point-in-time evidence for the durable rules above. Every citation below was true at its own date and
is preserved verbatim. Nothing here is current state, current routing or current authority, and the
tooling named in a citation is named as it was at that time.

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

<!-- HISTORICAL_RECORD_END -->
