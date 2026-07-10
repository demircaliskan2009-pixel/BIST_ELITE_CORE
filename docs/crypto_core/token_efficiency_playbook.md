# Token Efficiency Playbook (crypto_core agents)

Purpose: use the lowest capable lane without weakening proof, audit depth, deterministic behavior, or merge
discipline. Token savings are never evidence.

## 1. Common task classes and context budgets

| Class | Task type | Active lane | Context budget |
|---|---|---|---|
| T0 `LUNA_MECHANICAL` | git/gh state, CI polling, PR metadata, thread status, postverify runner | GPT-5.6 Luna, `none`/`low` | Exact commands; no design inference or source scan unless necessary for stated proof |
| T1 `LUNA_OR_TERRA_READONLY` | ordinary docs, bounded read-only audit, setup proof | Luna low or Terra high | Named docs and direct dependencies only |
| T2 `TERRA_BOUNDED_CODE` | exact-file implementation, tests/docs, small deterministic slice | GPT-5.6 Terra high | Named files first; targeted validation; one PR |
| T3 `TERRA_REPAIR_OR_OPUS_HEAVY` | current P1/P2 repair, fail-closed contract work, forensic debug | Terra xhigh; Opus 4.8 xhigh if broad or long-loop | Explicit invariants and regression proof; no token shortcut |
| T4 `SOL_CROSS_CONTRACT` | trust boundary, governance, SM-5/SM-6 design, readiness provenance | GPT-5.6 Sol xhigh; `max` only controller-gated | Compact evidence pack and independent audit decision |
| XR `DEEP_RESEARCH_EXTERNAL` | external/current facts | Deep Research, advisory only | Citations required; unverifiable facts stay `UNPROVEN` |
| `CONTROLLER_CONNECTOR_GATE` | final evidence comparison and merge authority | ChatGPT plus connector/`gh` | Fresh head/files/checks/threads proof |

## 2. Context intake protocol

1. Prove repo state first with one `git`/`gh` snapshot; never from memory.
2. Name the intended read set before reading and justify any expansion.
3. Read changed files and symbols before whole repositories; build one source surface map.
4. Do not reread unchanged docs after a stable head proof.
5. Stop with proof rather than broadening a scan to compensate for missing information.

## 3. Report compression

Use fixed fields, verdict first, and failure tails only. State repo facts only with fresh proof. Report
`MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`, `REASONING_ACTUAL`,
`EXACT_MODEL_REQUIRED`, fallback, scope, validation, PR/check/thread state, blockers, and next action.

## 4. Prompt reuse and model proof

Stable procedure lives in `AGENTS.md`, `agent_workflow.md` section 23, and named lanes. Prompts carry task
deltas, exact files, invariants, validation, stops, and model-actual fields. Historical Fable contracts are
archived in `fable_exit_contract_index.md`; they are never active routing.

If `EXACT_MODEL_REQUIRED=true`, requested/actual mismatch stops. Otherwise use declared fallback and never
claim unavailable-model quality. Model selection does not prove safety, repo state, or results.

## 5. Lane boundaries

- Luna owns mechanics. Explicitly authorized metadata writes remain T0 and cannot change code.
- Terra is the bounded Codex workhorse. A Terra implementation cannot self-satisfy independent audit in the
  same context; independent audit is fresh-context and pinned-head.
- Sol is scarce. Do not spend it on polling, merge mechanics, broad local refactors, or routine docs.
- Opus 4.8 preserves Codex usage for broad local implementation and long validation loops.
- Codex Pursue Goal is a bounded terminal loop, never broad repo pursuit, unscoped design, or unscoped patch.
- Deep Research is external/current facts only and stays advisory.
- Bounded CI snapshots only; pending/queued/in-progress/no checks = `NOT_READY`.

## 6. Anti-patterns

- Full-file reads where a symbol search answers the question.
- Sol/Opus status polling, Terra self-review, or unavailable-model claims.
- Prompts that reuse the same T labels for unrelated template categories.
- Broad scans, full logs, duplicate doctrine, or `product/*` branch templates.

## 7. Non-regression checks

One open PR; no direct `main` push; standard merge only; no merge without explicit human authorization;
pending CI = `NOT_READY`; current valid P1/P2 threads block; independent design and implementation audits
where required; connector final gate never waived; postmerge verification before next work; crypto_core-only;
no BIST, live/private API, orders, scheduler, readiness transition, shadow/live, or capital mutation.

## 8. No-overclaim

Nothing in this playbook proves repo/PR/CI state, Stage-4 completion, machine-time origin, secondary-metrics
enforcement, readiness, or edge/profitability. Compact reports retain identical proof density.