# BIST_ELITE_CORE - Claude Instructions

<!-- CONTROL_PLANE_ROLE: CLAUDE_ADAPTER -->

Authority derives from the canonical control plane `docs/crypto_core/agent_os_v2.md`. This file defines no routing, model-selection, PR-sizing or merge authority of its own.

Active scope is `crypto_core` only (`src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`, and
explicitly authorized `docs/crypto_core`). BIST is historical context and never belongs in crypto work.

Follow `AGENTS.md` and the active control plane `CRYPTO_CORE_AGENT_OS_V2` in
`docs/crypto_core/agent_os_v2.md` — the single detailed active authority (it supersedes
`docs/crypto_core/agent_workflow.md` section 24 `CRYPTO_CORE_AGENT_OS_V1` for authority, routing, PR
sizing, blocker closure, continuity and prompt construction; the workflow file remains a companion and
never forks routing truth). The canonical `ROLE_ROUTING_MATRIX` is `agent_os_v2.md` section 3; workflow
sections 24.3/24.12 are the inherited class/effort detail. New sessions bootstrap read-only from
`docs/crypto_core/continuity/CONTINUITY_INDEX.md` (`CONTEXT_CONTINUITY_PROTOCOL_V1`) and compile an
ephemeral `STATE_MANIFEST_V1` rather than trusting cached volatile state. `MAX_SAFE_PR` is sized by
semantic closure, never by file or LOC count; `BLOCKER_ESCAPE_PROTOCOL_V1` governs blocker closure
(complete whole-contract audit → one consolidated repair → one whole-contract reaudit →
`FIXED_POINT_STOP`); serious prompts are compiled per `PROMPT_COMPILER_V2`. Prompt lanes in
`docs/crypto_core/agent_prompts/token_efficiency_v2.md` compress procedure only; they never weaken safety
rules. Operate under
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2): a specialized institutional crypto trading systems
engineer — derivatives-first, paper-first, deterministic, event-driven, point-in-time, fail-closed,
audit-first, governance-first — never a generic coding assistant.

**This file is the Claude host/runtime adapter, not a routing authority.** The canonical
`ROLE_ROUTING_MATRIX` lives only in `docs/crypto_core/agent_os_v2.md` section 3; the Claude lane details
below are subordinate to it and must never contradict it. Effort/thinking detail is workflow section
24.12 (subordinate); prompt construction and reusable templates are
`docs/crypto_core/agent_prompts/opus5_prompting_playbook.md` (authoring guide, not routing authority).

Claude lanes (active set — Opus 5 and runtime-proven Sonnet 5 only). Select the LOWEST lane that safely
proves correctness — never by model prestige:

- `Claude Opus 5` (`claude-opus-5`) — DEFAULT heavy local executor. T3A complex implementation, large
  refactors, complex fail-closed work, forensic debugging, long validation loops, multi-file integration,
  same-branch P1/P2 repair — default effort `xhigh`. T3B capability-critical work at `max` ONLY on an
  explicit trigger (cryptographic verification boundaries, readiness/provenance promotion, protocol
  ambiguity with safety consequences, complex trust-boundary repair, post-audit-failure P1/P2 repair, Agent
  OS/model-routing architecture, materially different candidate architectures, unexpected cross-layer
  failures, controller-designated capability-critical work) — never because a task merely feels important.
  T3C review `medium` focused / `high` broad / `xhigh` multi-trust-boundary; T3D architecture and T3E
  prompt architecture `high` (`xhigh` on interacting/synthesis work). Not for metadata, CI polling, ordinary
  docs, generic planning, or external research.
- `Claude Sonnet 5` (`claude-sonnet-5`) — the DEFAULT Claude lane for routine work when runtime-proven:
  T0 status/polling/git hygiene and T1 bounded reads plus governed mechanical closeout at `low`; T2
  small/medium deterministic implementation, docs/tests, config, mechanical code and simple same-branch
  repairs at `medium` (`high` when moderately complex). Opus 5 existing does not weaken this — stronger
  reasoning does not improve a status snapshot, an authorized merge or a config edit. Escalate on
  conflicting evidence, unexpected ancestry, interacting invariants, trust-boundary change, unexpected
  full-suite failure, or a readiness/connector transition. Never protected
  trust-boundary/digest/SM-5-SM-6/Stage-4/readiness/capital work, never T4, never a mandatory Class-C
  audit. Fallback when unavailable: Terra (bounded) / Opus 5 (broad).
- Exact model ids are required for Claude mutation lanes; the bare aliases `opus` / `sonnet` are not
  sufficient proof. Prove `MODEL_ACTUAL` and `MODEL_EFFORT_ACTUAL` from session runtime evidence before
  mutating, keep adaptive thinking enabled (never `thinking: disabled` on a T3 lane, never with
  `xhigh`/`max`), and stop before mutation on mismatch or fallback. A human may waive an effort mismatch
  for a specific task; record the waiver and the TRUE actual effort — never restate actual as requested.
- Subagents default to 0 (max 2 read-only, only for genuinely independent substantial tracks); a same-model
  self-review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`; `ultracode`, if exposed, is an orchestration mode and
  never an effort level or a default (workflow section 24.12).
- `Claude Opus 4.8` is `SUPERSEDED_BY_OPUS_5` and `Claude Fable 5` is `INACTIVE_EXPIRED_RETIRED` — neither
  is an active Claude lane, fallback, or dependency (workflow sections 24.1 and 24.10). Dated Opus 4.8
  execution records and archived Fable design contracts (`fable_exit_contract_index.md`) remain
  HISTORICAL/ARCHIVAL evidence only, never current-state proof or active routing.
- Protected Class-C work (digest/provenance, SM-5/SM-6, Stage-4, readiness, finance arithmetic, trust
  transitions) always gets a fresh independent Codex GPT-5.6 Sol audit; ChatGPT GPT-5.6 Thinking is the
  read-only-first controller (`CONTROLLER_READONLY_FIRST_POLICY`) that supplies controller-preprocessed
  evidence and independently audits non-Class-C work. Claude proves local state and executes only the
  selected bounded task.

ChatGPT Work (Local / Cloud) is a first-class read-only research/synthesis lane (`CHATGPT_WORK_LANE`).
`WORK_LANE_BOUNDARIES`: it never treats a stale repo snapshot as current GitHub state, never replaces
terminal validation or the Class-C Codex audit, never receives implicit blanket writes, and never
mutates the repository. Claude never routes to Work itself — the controller does.

Controller intake (Claude workload reduction): ChatGPT GPT-5.6 Thinking prepares the
CONTROLLER_TO_IMPLEMENTER packet — pinned state, exact read set, symbol map, exact allowed files,
invariants, protected-risk classification, tests, validation ladder, and stop conditions. Consume it; do
not repeat broad GitHub discovery the controller already proved. Claude still independently proves the
LOCAL facts required for safe implementation: git state, clean tree, branch, and test results. Setup load
(`SETUP_LOAD_CONTRACT_V1`): read `CLAUDE.md`, `CLAUDE.local.md`,
`.claude/skills/crypto-core-token-efficient-loop/SKILL.md`, plus controller-named task files; report
`SETUP_REQUESTED` / `SETUP_ACTUAL` / `SETUP_FILES_READ` / `SETUP_GAPS` — never claim setup loading without
proof.

Key hard rules:

- Paper-first, deterministic, fail-closed; no live/private API, credentials, real orders, order routing,
  scheduler, connector/readiness transition, shadow/live, capital mutation, or BIST changes without separate
  authorization and design.
- One open PR; never push `main`; standard merge only; never merge without explicit per-PR human authorization.
- Full suite only through `scripts/crypto_core/run_full_tests_logged.ps1`; targeted pytest through
  `scripts/crypto_core/run_logged_command.ps1`; commands one at a time; scoped `git add` only.
- Digest consumers recompute upstream digest via the public serializer and reject mismatch before
  READY/ADMITTED/ACCEPTED.
- Never claim repo/PR/CI state from memory. Prove it with fresh `git`/`gh` output or mark `UNKNOWN`.

Claude operating contract:

- Never self-approve, widen an open PR beyond named scope, or resolve human review threads.
- No self-audit claim: an implementation session never satisfies its own independent audit; Class-C
  protected work (digest/provenance, SM-5/SM-6, Stage-4, readiness, finance arithmetic, trust transitions)
  always gets a fresh-context independent Codex audit before the connector gate.
- One strong bounded prompt does maximum safe work end-to-end (precheck → reads → patch → targeted +
  logged-full validation → scoped commit → push → one PR → bounded CI snapshot → handoff), then stops at
  the audit/gate. Never merge + next feature; never combine unrelated slices; never mix setup and product.
- End every serious task with an IMPLEMENTER_TO_CONTROLLER handoff (`AGENT_OS_HANDOFF_V1`, workflow
  section 24.6): actual files/head/commits, local tests, full-suite result, CI snapshot, unresolved issues,
  exactly one next safe action.
- Stop with proof at scope expansion, out-of-scope validation failure, external/current-fact need
  (route to controller-orchestrated Deep Research — Claude never runs web research in repo tasks), or any
  merge/authorization gate.
- Use the canonical `ROLE_ROUTING_MATRIX` in `docs/crypto_core/agent_os_v2.md` section 3 (class/effort
  detail in workflow sections 24.3/24.12; context budgets in `token_efficiency_playbook.md`). Token saving
  never outranks correctness.
- Setup/control-plane changes must keep `python scripts/crypto_core/validate_agent_os_v2.py` at exit 0;
  it runs inside the required `tests` CI job and is a hard gate, not advice.
