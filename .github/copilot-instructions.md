# COPILOT LOCAL EXECUTION CONTRACT — PRODUCT VALUE MODE

## OPERATING BASELINE

- crypto_core is active implementation scope.
- BIST is historical-only context and must not drive new implementation work.
- The VS Code local Copilot Agent is an EXECUTION HOST inside `CRYPTO_CORE_AGENT_OS_V1`
  (`docs/crypto_core/agent_workflow.md` section 24), never an independently trusted model identity.
  Load `AGENTS.md` plus the exact controller packet before serious work (`SETUP_LOAD_CONTRACT_V1`) and obey
  the CONTROLLER_TO_IMPLEMENTER packet: exact allowed files, invariants, validation ladder, stop conditions.
- ChatGPT GPT-5.6 Thinking is the controller (evidence comparison, design synthesis, audit framing, merge
  gate). It is not a Codex runtime. Claude Fable 5 exists only as a runtime-proven premium surge lane
  (workflow section 24.10): this host may route to Fable ONLY when the controller packet explicitly
  authorizes it with a passed `FABLE5_JUSTIFICATION_GATE`; never automatic Fable selection, and never Fable
  for cheap/bounded work.
- Model default is Auto. Auto is a routing host: report `MODEL_ACTUAL` where the runtime exposes it; never
  claim a specific model without runtime proof; state the token justification for any premium lane.
- Bounded implementation only: one named slice, exact files — no generic repo-wide improvement passes.
- Product-value implementation is prioritized over premium request burn.
- Current repository state must be proven with terminal and GitHub CLI evidence before merge decisions.
- No live/private API changes, order routing changes, scheduler changes, or autonomous trading enablement.
- No cloud agent delegation, Copilot CLI, GitHub.com Chat workflow, plugin installation, or external MCP additions.
- B5 and human provenance gates cannot be bypassed.
- Deep Research is allowed only for external or current facts that are not provable from this repository,
  and only controller-orchestrated.

## CANONICAL DOCTRINE & SCOPE

- Canonical operating doctrine (precedence) is `AGENTS.md` -> `docs/crypto_core/agent_workflow.md` ->
  `.codex/skills/crypto-core-max-safe/SKILL.md` -> `CLAUDE.md`; lessons in `docs/crypto_core/agent_lessons.md`.
  This file and any `.github/prompts`, `.github/skills`, `.github/instructions`, `.github/agents`, or
  `.cursor/rules` content is secondary and is **overridden by that canonical doctrine wherever they conflict**.
- Legacy skill/prompt names that imply scheduler/deployment/live/order-routing do NOT authorize such behavior:
  crypto_core is paper-first, no scheduler/auto-loop, no live/order routing.
- Branch naming: feature slices `feature/<crypto-core-scope>-prN`; setup/docs `chore/<crypto-core-scope>-prN`;
  same-PR repair on the same branch. Setup/doctrine changes never mix into a feature PR.
- Codex Pursue Goal is for bounded single-goal GitHub/CI loops only (CI polling, repo/branch sync, PR
  closeout/status, authorized merge/post-merge verify) — never complex implementation, design, or
  digest/provenance architecture. MCP is opt-in/manual; none is enabled by default.
- Deep Research is the external/current-fact + architecture-benchmark tool (and, in the GitHub
  connector chat, combined repo+external review): use it for exchange/API/funding/fees/limits/
  microstructure/custody/regulation/security facts, Deribit/readiness/live/shadow decisions, PRD/
  roadmap-vs-external-benchmark questions, overengineering detection, and paper/shadow/live DONE gates;
  not for local repo state, CI polling, merge/readiness source-of-truth, local repair, or replacing
  Codex review. It is strictly read-only / advisory, never an executor lane, never merge authority,
  never a safety-gate waiver: it never mutates repo or GitHub state (branch/file/commit/push/PR/comment/
  thread-resolve/workflow-rerun/merge/auto-merge), even when the underlying work is authorized; it may
  recommend a mutation task but the controller routes any authorized mutation to Claude/gh, the GitHub
  connector, or Codex. In connector chat it separates REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE /
  UNKNOWN and never infers live repo state without GitHub evidence. Full protocol:
  `docs/crypto_core/deep_research_protocol.md` (`docs/crypto_core/agent_workflow.md` section 19).

## AUTO MODEL FITNESS RULE

- If Auto output appears weak, confused, or misses setup constraints, stop immediately with `MODEL_FIT_WEAK` and exact evidence.

## AGENT ROUTING POLICY

- Crypto Product Auditor: read-only product-layer audit.
- Crypto Core Engineer: bounded implementation or setup patch executor with full validation.
- Crypto Throughput Commander: legacy closeout-only mechanical follow-through.
- forensic-debugger: read-only root-cause analysis first.
- PRD Compliance Auditor: setup, scope, and governance compliance audit.

## EXECUTION RULES

- Use one bounded implementation slice at a time.
- Perform a read-only product-layer audit before code implementation when scope is unclear.
- Fail closed: if evidence is missing, return INSUFFICIENT EVIDENCE.
- Do not claim tool capability unless it is callable and proven in this workspace.
- `rg`/ripgrep is optional. If unavailable, use PowerShell `Get-ChildItem` + `Select-String` or Python file walks.

## VALIDATION BASELINE

- ruff check --fix on changed files
- ruff format on changed files
- ruff format --check on changed files
- ruff check on changed files
- targeted pytest for changed behavior
- full tests/crypto_core when behavior changes
- readiness and connector probes when relevant
- git diff --check before commit

## MERGE RULES

- Standard merge only.
- No direct push to main.
- No squash, no rebase, no admin merge.
- PR and CI closeout must use JSON/API polling only.
- Forbidden: `gh pr checks --watch`, `gh run watch`, `gh pr review --approve`, and any self-approval flow.
