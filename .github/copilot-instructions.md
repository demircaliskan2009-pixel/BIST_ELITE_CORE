# COPILOT LOCAL EXECUTION CONTRACT — PRODUCT VALUE MODE

## OPERATING BASELINE

- crypto_core is active implementation scope.
- BIST is historical-only context and must not drive new implementation work.
- ChatGPT is used for reasoning, prompt design, and audit framing.
- VS Code local Copilot Agent is the primary executor for edits, validation, and git operations.
- Model default is Auto.
- Product-value implementation is prioritized over premium request burn.
- Current repository state must be proven with terminal and GitHub CLI evidence before merge decisions.
- No live/private API changes, order routing changes, scheduler changes, or autonomous trading enablement.
- No cloud agent delegation, Copilot CLI, GitHub.com Chat workflow, plugin installation, or external MCP additions.
- B5 and human provenance gates cannot be bypassed.
- Deep Research is allowed only for external or current facts that are not provable from this repository.

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
