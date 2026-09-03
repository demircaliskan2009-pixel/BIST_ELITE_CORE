# CRYPTO_CORE_AGENT_OS_V2 — canonical control plane

`CRYPTO_CORE_AGENT_OS_V2` is the single detailed active control-plane authority for `crypto_core` in
`demircaliskan2009-pixel/BIST_ELITE_CORE`. It supersedes `CRYPTO_CORE_AGENT_OS_V1`
(`docs/crypto_core/agent_workflow.md` section 24) for authority, routing, PR sizing, blocker closure,
context continuity and prompt construction. Every section-3 hard rule of `agent_workflow.md` binds
unchanged; on any apparent conflict the **stricter safety rule wins**.

This document contains no secrets, credentials, API keys, exchange credentials, or live-trading
instructions, and authorizes no order flow. It pins no mutable repository state.

## 0. Authority and precedence

`AGENT_OS_V2_PRECEDENCE`:

1. `AGENTS.md` — durable rails and project identity.
2. `docs/crypto_core/agent_os_v2.md` — **this file**, the canonical active control plane.
3. Environment adapter — `.codex/skills/crypto-core-max-safe/SKILL.md` (Codex sessions) **or**
   `CLAUDE.md` + `.claude/skills/crypto-core-token-efficient-loop/SKILL.md` (Claude sessions).
4. `docs/crypto_core/agent_lessons.md` — evidence-backed lessons companion.

`docs/crypto_core/agent_workflow.md` remains the **workflow companion** (PR lifecycle, hard rules,
command-level loops, historical record). It MUST NOT independently fork routing truth: there is exactly
**one** authoritative routing matrix and it is section 3 of this file. Every other active surface
references it instead of restating it as authority.

Blueprint and design documents remain design inputs, not control-plane authority. Historical blueprint
sizing wording such as "each artifact is one PR" is `NON_AUTHORITATIVE_SIZING_HISTORY` under Agent OS V2;
those documents are not mass-edited to say so.

`docs/crypto_core_current_state.md` and `docs/crypto_core/continuity/CONTINUITY_INDEX.md` are durable
pointers, never live-state dashboards.

## 1. Core governance invariants

These invariants are load-bearing. No prompt, lane, throughput target, or token budget relaxes them.

| ID | Invariant |
|---|---|
| `V2-I01` | crypto_core only. BIST remains historical / non-applying. |
| `V2-I02` | `ONE_REPOSITORY_WRITER` — one repository writer at a time. |
| `V2-I03` | `ONE_OPEN_PR` — exactly one open PR by default. |
| `V2-I04` | `NO_DIRECT_MAIN_PUSH` — no direct push to `main`. |
| `V2-I05` | Normal push only; no force push. |
| `V2-I06` | Standard merge commit only. |
| `V2-I07` | No squash merge and no rebase merge. |
| `V2-I08` | `EXPLICIT_HUMAN_MERGE_AUTHORIZATION` — merge remains explicit per-PR human authority. |
| `V2-I09` | No blanket permanent authorization substitutes for protected governance. |
| `V2-I10` | Mandatory Class-C audit remains an independent Codex GPT-5.6 Sol audit. |
| `V2-I11` | Claude self-review never satisfies an independent audit. |
| `V2-I12` | Same-model review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`. |
| `V2-I13` | Pending CI is `NOT_READY`. |
| `V2-I14` | A current valid P1/P2 is a `MERGE_BLOCKER`. |
| `V2-I15` | Mutable state is never stored as durable doctrine. |
| `V2-I16` | Memory is a retrieval aid, never state authority. |
| `V2-I17` | Each unchanged-head gate runs once unless invalidated by mutation, head movement, base movement, or genuinely new evidence. |
| `V2-I18` | No autonomous scheduler. |
| `V2-I19` | No hidden auto-loop. |
| `V2-I20` | No direct runtime model-to-model mutation chain. |
| `V2-I21` | `NO_SELF_APPROVAL` — no automatic self-approval. |
| `V2-I22` | `READINESS_AUTHORITY_NOT_INFERRED` — no readiness, connector, live, or capital authority may be inferred from setup or process success. |

## 2. Architecture council model

The system is **not** an autonomous swarm. `CONTROLLER` (ChatGPT GPT-5.6 Thinking) is the sequence owner;
every other model or tool is a specialized lane. All lanes communicate through explicit canonical packets:
`STATE_MANIFEST_V1`, `PR_CLOSURE_CONTRACT_V1`, `CURRENT_HANDOFF_V2`. There is no hidden model-to-model
state, and no model trusts another agent's claim without evidence appropriate to its own role.

The ideal loop is `CONTROLLER` → best specialist → structured handoff → `CONTROLLER` evidence
verification → next specialist if needed. Minimize model hops; every model hop must have a concrete stated
reason. Adding a lane merely to satisfy a council ceremony is forbidden.

## 3. ROLE_ROUTING_MATRIX — single canonical authority

This is the only authoritative routing matrix in the repository.

<!-- ROLE_ROUTING_MATRIX_V2:BEGIN -->

| Lane | Role | Use for | Never |
|---|---|---|---|
| ChatGPT GPT-5.6 Thinking (controller) | Controller, brain, router, architecture synthesizer, state-proof owner, prompt compiler, handoff verifier, risk classifier, merge-readiness judge, GitHub connector coordinator | STATUS, CLOSEOUT, BOUNDED_READ, ARCHITECTURE, PROMPT_ARCHITECTURE, review triage, routing, live GitHub evidence verification | Default product-code writer; merge authority; readiness authority; live or capital authority; replacement for tests; replacement for mandatory Class-C |
| ChatGPT Work (Local / Cloud) | First-class read-only research and synthesis lane with a persistent workspace, artifact delivery, and Cloud Browser | Large repo synthesis, multi-document comparison, long architecture reports, next-PR closure packet preparation, current web research, website interaction, persistent project workspace, large read-only analysis, artifact-oriented delivery | Never treats an uploaded or stale repo snapshot as current GitHub state; never replaces terminal validation; never replaces Class-C; never receives implicit blanket writes; never replaces controller final evidence judgment |
| GitHub connector | Pinned-ref evidence and explicitly authorized exact writes | Repo reads, file reads, branch state, PR state, diffs, checks, runs, review and thread evidence, supported exact authorized writes | Never invents an unsupported connector capability; never treats connector availability as blanket write authority |
| Deep Research | Controller-orchestrated external and current-fact research, read-only and advisory | Exchange or provider APIs, deployed versions, fees and funding, rate limits, security, regulation, machine-time provider facts, current readiness assumptions, current credible architecture benchmarks | Being used because repo work is merely difficult; repo-local facts; executor lane; merge authority; safety-gate waiver |
| Claude Opus 5 | Heavy implementation and repair lane (`claude-opus-5`), default effort `xhigh` | Cross-module implementation, interacting invariants, fail-closed semantics, complex consolidated repair, large bounded migrations | Automatic higher effort; metadata; CI polling; ordinary docs; work a lighter lane safely closes |
| Claude Sonnet 5 | Optional bounded lane (`claude-sonnet-5`), runtime-proven only | Docs, config and tests; mechanical implementation; small deterministic repair; T0-T2 work | Being added merely to increase agent count; protected trust-boundary, digest, SM-5/SM-6, Stage-4, readiness or capital work; T4; a mandatory Class-C audit |
| Codex GPT-5.6 Sol | Primary protected independent audit lane, default protected reasoning `xhigh` | Class-C, trust boundaries, cryptography, digest and provenance, SM-5/SM-6, Stage-4, machine-time protected work, readiness and Deribit promotion, security and CodeQL, critical cross-contract audit | Ultra or max as a permanent default for trivial work; broad discovery; mechanics |
| Codex GPT-5.6 Terra | Bounded implementation and ordinary independent audit | Bounded implementation, ordinary independent audit, medium complexity, Class-B where appropriate | Replacing a Sol-required Class-C audit |
| Codex GPT-5.6 Luna | Mechanics | git and status, CI polling, PR metadata, mechanical closeout, explicitly authorized standard merge, post-merge command execution | Semantic design; readiness judgment |

<!-- ROLE_ROUTING_MATRIX_V2:END -->

Identity rules (unchanged and binding): ChatGPT is `GPT-5.6 Thinking` and is **never** labeled Codex
`GPT-5.6 Sol`; Sol, Terra and Luna are distinct Codex runtimes; `claude-opus-5` and `claude-sonnet-5` are
the only Claude mutation ids and the bare aliases `opus` / `sonnet` are not runtime proof. Ultra or `max`
reasoning on Sol is only a controller-gated named T4 situation where expected value justifies it. Select
the LOWEST lane that safely proves correctness — model prestige is never a selection reason.

`CHATGPT_WORK_LANE` — the controller decides when Work is useful and may hand off read-only research or
synthesis to Work without human routing ceremony. `WORK_LANE_BOUNDARIES`: Work Local covers local and
source-bound analysis and artifact work where available; Work Cloud and Cloud Browser cover external
websites, current documentation, current provider information and research deliverables. Work never
receives blanket write authority, never mutates the repository, and its output is controller-verified
evidence input, never accepted state.

Retired and non-active lanes: **Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`** — not an active lane,
fallback, or dependency; **Claude Opus 4.8 is `SUPERSEDED_BY_OPUS_5`**; **Copilot is
`INACTIVE_UNAVAILABLE`** and is never an autonomous executor, never an execution host for another model,
and holds no blanket mutation authority. Material naming these lanes survives only as HISTORICAL,
SUPERSEDED or ARCHIVAL evidence and never re-enters active routing.

Task classes (`T0` `LUNA_MECHANICAL`, `T1` `READONLY_OR_FAST_BOUNDED`, `T2` `BOUNDED_IMPLEMENTATION`,
`T3A`-`T3E`, `T4` `CROSS_CONTRACT_DESIGN_OR_AUDIT`, `XR` `DEEP_RESEARCH_EXTERNAL`,
`CONTROLLER_CONNECTOR_GATE`) and the Claude effort ladder are inherited unchanged from
`agent_workflow.md` sections 24.3 and 24.12, which remain the class and effort detail companions to this
matrix. Where the workflow companion and this file disagree on a lane's authority, this file wins.

## 4. MAX_SAFE_PR policy

`MAX_SAFE_PR` is defined by **semantic closure**, never by file count, LOC count, one-artifact-per-PR,
one-module-per-PR, one-test-per-PR, or one-phase-per-PR. Sizing or splitting a PR by file count or LOC
count is not a valid split reason.

A `MAX_SAFE_PR` is the largest change that closes ONE coherent semantic contract, its direct dependency
closure, its negative cases, its permanent tests, its validation, and its rollback, without crossing an
independent protected trust boundary.

Split or rescope only when at least one of these is true:

1. two independent trust boundaries emerge;
2. an invariant cannot be tested inside the same PR;
3. an irreversible authority transition would be mixed with ordinary implementation;
4. dependency closure cannot be proven;
5. one PR would require two independent repository writers.

Do not split merely because a PR is large.

### 4.1 Target development loop

`PR_CLOSURE_CONTRACT` → ONE HEAVY IMPLEMENTATION → COMPLETE INDEPENDENT AUDIT → ONE CONSOLIDATED REPAIR
IF REQUIRED → ONE FINAL REAUDIT → FINAL GATE → HUMAN MERGE AUTHORIZATION → STANDARD MERGE → POSTVERIFY →
NEXT `MAX_SAFE_PR`.

Explicitly deprecated as default behavior: micro PR → first blocker → repair → second audit → new blocker
→ new artifact → new micro PR → repeat.

### 4.2 TARGET_PROMPTS_PER_PR

`TARGET_PROMPTS_PER_PR`: `MEDIAN=3`, `REPAIR_PATH_MAX_TARGET=5`. Normal path: (1) controller closure
contract and routing packet, (2) one heavy implementation, (3) one independent whole-contract audit. The
repair path adds (4) one consolidated repair and (5) one final whole-contract audit and final gate. This
is a throughput TARGET, not a correctness ceiling: never weaken correctness or proof to satisfy a prompt
count.

### 4.3 PR_CLOSURE_CONTRACT_V1

Frozen before implementation begins and printed as `PR_CLOSURE_CONTRACT_V1=FROZEN`. Fields: `OUTCOME`,
`SEMANTIC_BOUNDARY`, `DEPENDENCY_CLOSURE`, `INVARIANTS`, `CREATE_ALLOWLIST`, `MODIFY_ALLOWLIST`,
`DELETE_ALLOWLIST`, `PROTECTED_SURFACES`, `NEGATIVE_TEST_MATRIX`, `KNOWN_BLOCKER_INVENTORY`,
`VALIDATION_MATRIX`, `ROLLBACK`, `ACCEPTANCE_MATRIX`. Unrelated objectives are never added later.

## 5. BLOCKER_ESCAPE_PROTOCOL_V1

`BLOCKER_ESCAPE_PROTOCOL_V1` is the fixed-point closure protocol:

`UPFRONT_CLOSURE` → `EXHAUSTIVE_WHOLE_CONTRACT_AUDIT` → `ONE_CONSOLIDATED_REPAIR` →
`ONE_WHOLE_CONTRACT_REAUDIT` → `FIXED_POINT_STOP`.

- **A.** Before implementation, freeze: outcome, semantic boundary, dependency closure, invariants,
  allowed files, negative cases, known blocker inventory, acceptance matrix.
- **B.** Implement the WHOLE frozen contract in one pass where feasible.
- **C.** The independent audit MUST collect the COMPLETE P1/P2 set for the whole frozen contract. It must
  not stop after the first blocker, review only the latest delta, convert every newly noticed optional
  hardening item into a blocker, or invent closure requirements after each repair.
- **D.** If P1/P2 exists, ONE consolidated repair closes all known P1/P2 on the same branch.
- **E.** Reaudit the entire frozen contract once.
- **F.** If genuinely new P1/P2 appears after the whole-contract reaudit the state is
  `FIXED_POINT_NOT_REACHED`. Do not automatically create another micro phase, another persistence
  artifact, another new PR, or another endless repair loop. Return to the controller, which explicitly
  chooses `RESCOPE`, `FREEZE`, `REVERT`, or — exceptionally — ONE additional repair when evidence proves
  the original frozen contract was itself materially incomplete.
- **G.** The same blocker retains ONE blocker identity.
- **H.** `BLOCKER_ARTIFACT_MULTIPLICATION_PROHIBITED` — an unchanged blocker with unchanged evidence does
  NOT justify a new Python module, test file, JSON artifact, Markdown phase, workflow, or PR solely to
  state that the blocker still exists.
- **I.** A new blocker artifact requires new evidence, a new contract transition, new external authority,
  or an explicit controller-approved semantic reason.
- **J.** Infrastructure-only CI retry is limited to at most one explicitly authorized rerun. A semantic
  failure is repaired, never rerun.

## 6. Anti-overengineering protocol

Progress is NOT measured by the number of phases, governance artifacts, modules, prompts, or PRs.
Progress is measured by closed semantic contracts, end-to-end integration, proof quality, remaining
load-bearing blockers, and reduced uncertainty.

Do not build proof-of-proof-of-proof chains unless a real trust boundary requires them. Before creating a
new persistent artifact, answer: **WHAT NEW LOAD-BEARING FACT DOES THIS ARTIFACT PROVE?** If the answer is
"the same blocker still exists", do not create it.

Agent OS V2 consolidates; it does not proliferate. Do not introduce an agent daemon, runtime model message
bus, scheduler, agent runtime API, database, state server, new MCP server, new dependency, telemetry
backend, metrics service, web UI, new `workflow_dispatch`, new GitHub workflow, one file per model, one
file per lane, one file per blocker, one file per prompt, one artifact per day, or a new bureaucracy
layer.

Historical artifacts, including the Deribit product, evidence and continuity artifacts, are preserved.
This rule is prospective only.

## 7. CONTEXT_CONTINUITY_PROTOCOL_V1

`CONTEXT_CONTINUITY_PROTOCOL_V1` solves new-chat context loss with a small durable tracked surface plus an
ephemeral state packet — never a giant pasted chat.

- **Durable:** `docs/crypto_core/continuity/CONTINUITY_INDEX.md` — authority pointers, project scope,
  stable architecture map, stable implemented-capability map, stable design and frontier categories,
  stable invariant IDs, historical and retired-surface classification, bootstrap procedure, and the
  location and format of ephemeral handoff packets. It MUST NOT contain volatile values: current SHA,
  current branch, current PR, current CI run, current reviews, current thread state, a current temporary
  blocker run, temporary quota or model availability, a mutable readiness result, or a mutable connector
  transition.
- **Ephemeral:** `STATE_MANIFEST_V1`, defined by
  `docs/crypto_core/continuity/state_manifest.schema.json`, with
  `docs/crypto_core/continuity/state_manifest.example.json` as an `EXAMPLE_ONLY` illustration. A state
  manifest is compiled per task and is never committed as durable doctrine.
- **Invalidation:** a state manifest is invalid when head, base, tree, PR state, CI runs (new or rerun),
  audit-relevant reviews or threads, the readiness fingerprint, the connector fingerprint, or the task
  boundary changes, or when its freshness deadline passes.
- **`CURRENT_HANDOFF_V2`:** the ephemeral model-boundary packet carrying what was done, exact current
  state proof, files, tests, CI, audit, blockers, authority used, and exactly one next safe action. It is
  a handoff, not a durable live-state repository dashboard, and it never authorizes mutation.

### 7.1 New chat bootstrap

```text
MODE=READ_ONLY.
Load AGENTS.md, docs/crypto_core/agent_os_v2.md,
and docs/crypto_core/continuity/CONTINUITY_INDEX.md.
Re-prove repo/branch/base/head/tree/divergence/worktree/open PRs.
Never trust cached volatile state.
Classify TASK_INTENT and risk.
Compile STATE_MANIFEST_V1.
Route exactly one lane.
Return STATE_PIN, P1/P2/P3, and exactly one NEXT_SAFE_ACTION.
```

This replaces giant pasted-chat continuity as the normal future path.

## 8. PROMPT_COMPILER_V2

`PROMPT_COMPILER_V2` is the canonical model-aware prompt compiler policy. Serious prompts are COMPILED,
not pasted, and carry exactly these sections: `TASK_INTENT`, `SEMANTIC_BOUNDARY`, `STATE_PIN`,
`MODEL_RUNTIME_PROOF`, `ALLOWED_FILES`, `INVARIANTS`, `BLOCKER_INVENTORY`, `VALIDATION_MATRIX`,
`GITHUB_AUTHORIZATION`, `FORBIDDEN`, `STOP_CONDITIONS`, `HANDOFF`.

Stable doctrine is NOT pasted in full into every prompt: stable policy is loaded from the repository and
the prompt carries only the task-specific delta. Every prompt has ONE role, ONE semantic outcome, ONE
writer OR ONE read-only reviewer, ONE report contract, and ONE next safe action.

Model-specific prompt behavior:

| Lane | Prompt shape |
|---|---|
| Opus | Large semantic closure, interacting invariants, implementation and repair |
| Sol | Narrow protected audit packet: exact head, exact changed files, direct dependencies, unresolved semantic questions, adversarial cases |
| Terra | Bounded direct scope |
| Luna | Mechanical command and state task, minimal semantic prose |
| Work | Explicit deliverable, source scope, current-vs-stale distinction, evidence taxonomy |
| Deep Research | One current external question, source requirements, retrieval date, repo relevance |

`PROMPT_LANGUAGE_PROHIBITED` — a compiled prompt must never contain any of the wording inventoried below.
No prompt, lane or packet grants restart-until-success authority, blanket GitHub authority or blanket
merge authority.

<!-- PROHIBITED_WORDING_INVENTORY:BEGIN -->

The following are the exact forms that must never appear in a compiled prompt. This block is an inventory
of forbidden wording, so the phrases are quoted here on purpose and are exempt from the control-plane
wording scan; the fence is honoured only in this file and in `.github/copilot-instructions.md`.

- "continue until done"
- "keep fixing until green"
- "do everything automatically"
- "approve your own work"
- "merge when you think ready"
- "ignore scope if needed"
- hidden loops
- blanket GitHub authority
- blanket merge authority
- unbounded discovery during repair
- any request for hidden chain-of-thought

<!-- PROHIBITED_WORDING_INVENTORY:END -->

## 9. DAILY_BATCH_MANIFEST_V1

`DAILY_BATCH_MANIFEST_V1` lets the controller or Work prepare the next 3-5 read-only PR closure
candidates ahead of time. This improves throughput without parallel mutation: only one open PR, only one
mutating writer, and each PR re-proves volatile state before mutation.

Daily planning may precompute candidate semantic boundary, dependency map, risk class, likely model lane,
Deep Research requirement, estimated audit class, and expected allowed files. State SHA, CI and readiness
are always proven fresh at execution time.

Throughput reference points: 15-20 semantic prompts per day is a capacity ceiling, not a KPI; 4-6 merged
PRs per day is possible only for independently closed Class-A/B or similarly bounded work; protected T4
days may correctly produce fewer PRs. Do not claim a throughput improvement until it is measured.

## 10. Token and context efficiency

Agent OS V2 optimizes expected value per token:

1. Do not re-paste stable doctrine in every prompt.
2. Do not make downstream models redo controller GitHub discovery unless it is locally required.
3. Use one closure packet across implementation and audit where safe; the audit still receives fresh
   exact-head state.
4. Failure reports show relevant tails, never entire logs.
5. Use cheaper, lighter lanes when they are genuinely sufficient.
6. Do not add Sonnet, Terra or Luna prompts merely to satisfy a council ceremony.
7. Use Sol and Opus where semantic value justifies them.
8. Use Work when persistent workspace, browser or artifact capability materially reduces repeated context
   reconstruction.
9. Deep Research is never used for repo-local facts.
10. Correctness is never sacrificed to save tokens.

## 11. Setup validation and CI enforcement

`scripts/crypto_core/validate_agent_os_v2.py` is the deterministic enforcement of this control plane. It
is stdlib-only, deterministic, makes no network calls, reads no secrets, mutates nothing, and returns
nonzero on violation with concise actionable messages.

It runs inside the existing required `tests` job in `.github/workflows/ci.yml`, so a control-plane
violation fails the existing required `tests` context. No new required branch-protection context is
introduced and branch protection is not changed.

`scripts/crypto_core/audit_agent_setup.ps1` stays read-only, and its network and GitHub sections stay
informational, but the script returns nonzero when deterministic Agent OS V2 validation fails.

`tests/crypto_core/test_agent_os_v2_contract.py` is the permanent adversarial contract test: it proves
that the honest migrated repository passes and that each removed rail, reintroduced legacy surface,
reintroduced active-Fable wording, blanket autonomous or restart-until-success wording, missing
state-manifest field, forbidden durable SHA, stale current-state wording, or converted Work boundary
fails. The tests never mutate repository files.

## 12. Legacy control-plane retirement

The fragmented Copilot-era control plane is retired. `.github/instructions/**`, the Copilot
`.github/agents/crypto-*` specs, `.github/prompts/crypto-*.prompt.md`, `.github/skills/crypto-*`,
`.github/skills/_shared/references/contract-schema.md`, the Copilot-era hook contract
`.github/hooks/hook-engine.md`, and the Copilot-era and Claude-era throughput protocol documents under
`docs/crypto_core/` are removed as active surfaces. `.github/hooks/pre-response.json` and
`.github/hooks/post-response.json` are **deliberately preserved**: they are runtime-owned data loaded by
`src/bist_core/hooks/hook_engine.py`, so retiring them would change BIST runtime behavior, which this
crypto-only control-plane migration must never do. Any future relocation is a separately authorized BIST
change.
`.github/copilot-instructions.md` survives only as a thin compatibility shim stating that Copilot is
inactive unless separately reactivated through an audited workflow change.

Retired surfaces must not be reintroduced. The validator enforces their absence by exact path.

## 13. Non-goals and non-claims

Agent OS V2 changes the control plane only. It changes no crypto product or runtime behavior; it grants no
readiness, connector, live, shadow, order-routing, scheduler or capital authority; it proves no
repository, PR or CI state; and it satisfies no independent audit. Process success is never capability
proof.
