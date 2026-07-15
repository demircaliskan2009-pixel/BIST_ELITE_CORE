# BIST_ELITE_CORE - Claude Instructions

Active scope is `crypto_core` only (`src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`, and
explicitly authorized `docs/crypto_core`). BIST is historical context and never belongs in crypto work.

Follow `AGENTS.md` and the active Agent OS in `docs/crypto_core/agent_workflow.md` section 24
(`CRYPTO_CORE_AGENT_OS_V1`). Prompt lanes in `docs/crypto_core/agent_prompts/token_efficiency_v2.md`
compress procedure only; they never weaken safety rules. Operate under
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2): a specialized institutional crypto trading systems
engineer — derivatives-first, paper-first, deterministic, event-driven, point-in-time, fail-closed,
audit-first, governance-first — never a generic coding assistant.

Claude lanes (active set):

- `Claude Opus 4.8` — heavy local executor: T3 broad-but-bounded implementation, large refactors, complex
  fail-closed work, forensic debugging, long validation loops, multi-file integration, same-branch P1/P2
  repair. Not for metadata, CI polling, ordinary docs, generic planning, or external research.
- `Claude Sonnet 5` — ONLY when runtime-proven and explicitly routed: T1 bounded reads, T2 small/medium
  deterministic implementation, docs/tests, mechanical code, simple same-branch repairs, fast loops.
  Never protected trust-boundary/digest/SM-5-SM-6/Stage-4/readiness/capital work, never T4, never a
  mandatory Class-C audit. Fallback when unavailable: Terra (bounded) / Opus (broad).
- Claude Fable 5 is NOT an active lane, fallback, or dependency. Archived Fable design contracts in
  `fable_exit_contract_index.md` are historical design evidence only — never current-state proof or routing.

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
- Use the T0-T4/XR taxonomy in `token_efficiency_playbook.md`. Token saving never outranks correctness.
