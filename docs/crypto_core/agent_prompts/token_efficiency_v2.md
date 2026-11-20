# Token Efficiency V2 - Agent OS named lanes and compact prompts

Use `agent_workflow.md` §§24.3–24.8 and 24.12 for routing, prompts, proof and handoffs. The procedure
references below supply details inside the canonical twelve fields.

## 1. Shared lanes

`LANE:ENV-STD` - set noninteractive pager/color variables.

`LANE:PRECHECK-STD(expect_main_at=<sha>)` - prove repo, clean main, expected HEAD, and open PR count. Stop
on dirty state, head mismatch, open-PR conflict, or unavailable GitHub proof.

`LANE:VALIDATE-STD(files=<paths>)` - one command at a time: scoped Ruff/format where code exists, targeted
validation, logged full suite when required, `git diff --check`, exact changed-file proof.

`LANE:PR-STD(branch=<feature|chore path>, title=<title>)` - exact scope gate, scoped add, commit/push, one
PR, bounded CI/thread snapshots, no merge.

`LANE:HANDOFF-STD` - end with an `AGENT_OS_HANDOFF_V1` packet: result, actual model, setup fields, state
proof, files, validation, PR/check/thread state, audit class, blockers, exactly one next safe action;
failure tails only.

## 2. Controller procedures

`LANE:CONTROLLER_STATE_PROOF` - pin main/PR/head/files/checks/threads/open-PR count from live connector
evidence; never memory; output pinned state for downstream packets.

`LANE:CONTROLLER_DESIGN_SYNTHESIS` - map surfaces/symbols/contracts from pinned evidence; define invariants,
fail-closed matrix, raise-vs-REJECTED boundaries, allowed files, negative-path tests, validation ladder,
stops; emit one bounded PR contract; decide whether Deep Research is required. No implementation.

`LANE:CONTROLLER_TO_IMPLEMENTER` - issue the implementation packet: pinned state, exact read set, symbol
map, exact allowed files, invariants, forbidden surfaces, protected-risk class, exact tests, validation
ladder, branch/commit/PR contract, stop conditions.

`LANE:CONTROLLER_PRE_CODEX_TRIAGE` - verify PR/base/head/files/patches/dependencies/CI/threads; run the
protected-trigger matrix; strip questions already proven; emit the narrow Codex packet (pinned head, exact
changes, direct dependencies, unresolved semantic questions, adversarial cases, report contract).

`LANE:CONTROLLER_REPORT_VERIFY` - check every executor claim against live PR metadata, pinned head/base,
exact files, commits, runs/jobs, tests, CodeQL, reviews, threads, open-PR count, merge state, pinned file
contents. No report is self-authenticating; unverified claims stay UNKNOWN/UNPROVEN. Output
HANDOFF_ACCEPTED / HANDOFF_REPAIR_REQUIRED / HANDOFF_REJECTED / HANDOFF_UNKNOWN.

Controller preflight may flag a scope or authority conflict for the independent auditor under §24.4.

`LANE:CONTROLLER_FINAL_GATE` - read-only merge-readiness verification: PR open/non-draft, base main, pinned
head unchanged, exact files, required checks terminal success (accepted skips only), CodeQL clean, no
current valid unresolved P1/P2, exactly one open PR, no forbidden scope, correct audit class completed.
Output READY_FOR_MERGE_AUTHORIZATION | NOT_READY | UNKNOWN. Never merges.

`LANE:CONTROLLER_AUTHORIZED_ACTION` - execute ONLY an explicitly human-named GitHub action (standard merge,
metadata, label, reviewer, draft/ready, comment, guarded thread closeout, bounded workflow rerun): re-prove
state immediately before, perform only the named action, re-read the result, report proof. Never direct main
push, force push, squash/rebase, self-approval, blind retry, or opportunistic adjacent mutation.

## 3. Handoffs

`LANE:IMPLEMENTER_HANDOFF` - close any implementation turn: actual files/head/commits, local tests,
logged-full-suite result, CI snapshot, unresolved issues, no self-audit claim, one next safe action, in
`AGENT_OS_HANDOFF_V1` form.

`LANE:POST_MERGE_HANDOFF` - after an authorized merge: PR, merge commit, local/origin main equality, Ruff,
format, full suite, setup audit, diff check, open PRs, clean tree, residual blockers, one next action.

## 4. Research lanes (controller-orchestrated; read-only)

`LANE:DEEP_RESEARCH_FACT_CHECK` - XR_FACT_CHECK: one narrow current external question; official/primary
sources first; retrieval date + source version; unresolved facts stay UNKNOWN; no implementation.

`LANE:DEEP_RESEARCH_ARCHITECTURE_BENCHMARK` - XR_ARCHITECTURE_BENCHMARK: compare against Hummingbot /
Freqtrade / NautilusTrader / QuantConnect LEAN / credible institutional systems on capabilities and
evidence (never stars/marketing); architectural intent vs implemented proof; bounded repo-relevant
recommendations; no blind copy; license/IP respected.

`LANE:DEEP_RESEARCH_PHASE_GATE` - XR_PHASE_GATE_REVIEW: mandatory before material phase transitions with
external/current assumptions (paper-DONE claims, machine-time, first connector/readiness, Deribit,
shadow/live, custody/security/regulatory, resilience); also after major phase bundles, before roadmap
changes on external assumptions, on stale prior evidence.

`LANE:DEEP_RESEARCH_OVERENGINEERING` - XR_OVERENGINEERING_AUDIT: artifact proliferation vs end-to-end
wiring; duplicates/unused modules/excess governance layers; freeze/consolidate/integrate recommendations;
underbuilding check; tests-verify-composition check. Advisory until controller triage.

All research lanes: connector-bound packet in (pinned repo state, exact files, benchmark set, source-quality
requirements), `DEEP_RESEARCH_TO_CONTROLLER` packet out (research date, pinned state, source quality,
REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN, stale findings, bounded recommendations, exact next
PR proposal, refresh trigger). Never mutation, never merge authority, never a gate waiver.

## 6. Invariants

One open PR; one repository writer at a time; no direct main push; standard merge only; explicit human merge
authorization; pending CI is NOT_READY; current valid P1/P2 block; Class-C Codex audit never replaceable;
connector final gate never waived; postmerge verification before next work; research never mutates;
crypto_core-only. Apply §24.4 for audit independence and the protected triggers. No BIST, live/private API,
orders, scheduler, readiness, shadow/live or capital work. No autonomous loop or direct model-to-model runtime messaging.
