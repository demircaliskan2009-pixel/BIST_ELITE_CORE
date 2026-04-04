---
name: bist-toolchain-optimizer
description: 'Optimize PRDV3 workflow across Copilot, Ruff, Jupyter, Data Wrangler, GitLens, Error Lens, Test Explorer, Path Intellisense, Project Manager, GitHub Pull Requests, and repository-native validation. Use when the goal is to reduce iteration, improve correctness, coordinate tooling, and produce concise single-pass outputs for BIST_ELITE_CORE.'
argument-hint: 'Describe the repo task, target files, toolchain surfaces involved, validation need, and what must be optimized for correctness or speed.'
user-invocable: true
---

# BIST Toolchain Optimizer

This skill orchestrates the PRDV3 VS Code workflow so code, notebooks, linting, diffs, validation, and review stay aligned, concise, and production-ready.

## Shared Contract
- Contract reference: [../_shared/references/contract-schema.md](../_shared/references/contract-schema.md)
- When a task crosses PRDV3 stages, this skill must preserve outputs that comply with the shared contract.
- Tool and validation choices must not introduce contract drift between stages.

## Use This Skill When
- Optimizing how Copilot should approach a repo task.
- Coordinating code edits, notebook work, lint expectations, validation, and review as one workflow.
- Choosing the shortest correct path among multiple tooling options.
- Reducing redundant prompts, repeated explanation, or avoidable rework.
- Standardizing how repo-native commands and VS Code extensions are used together.

## Do Not Use This Skill When
- The task is purely domain logic that belongs inside a more specific BIST skill.
- The workflow can proceed only by guessing missing requirements.
- The task would benefit more from a narrow domain-specific checklist than a toolchain-level optimization pass.

## Non-Negotiable Rules
- Optimize for single-pass, production-ready outputs whenever possible.
- Minimize redundant iterations, repeated prompts, and wasted token usage.
- Prefer exact patches, exact file targets, and exact commands over generic discussion.
- Align code, notebook, lint, diff, and validation workflows into one consistent process.
- Prefer repository-native commands and existing tooling over ad hoc workflows.
- Be concise by default and avoid repeating known context.
- If multiple tool paths exist, choose the one with the fewest steps and highest correctness.

## Toolchain Priorities
- Treat Ruff as the primary lint authority.
- Use Data Wrangler reasoning for tabular inspection and transformation review.
- Use Jupyter reasoning for stepwise data exploration and validation.
- Use GitLens-style thinking: minimal diffs, clear intent, reviewable changes.
- Use Error Lens assumptions to prevent errors before they surface.
- Use Test Explorer mindset so logic changes remain testable and preferably tested.
- Use Path Intellisense logic so paths are explicit, correct, and OS-safe.
- Keep GitHub Pull Requests compatibility in mind for review clarity and diff readability.
- Preserve workspace organization so Project Manager style workflows remain clean and predictable.

## Standard Procedure
1. Identify the narrowest successful path.
Determine the exact files, tools, and validation surface required to complete the task correctly.

2. Eliminate wasted motion.
Avoid exploratory edits, repeated explanation, and unnecessary alternative branches unless the task explicitly requires them.

3. Choose the dominant toolchain mode.
Use Data Wrangler reasoning for tables, Jupyter reasoning for staged data checks, Ruff-compatible code output for Python, and GitLens-style diff discipline for edits.

4. Produce exact working output.
Favor concrete patches, precise commands, explicit file targets, and structured results over prose-heavy guidance.

5. Coordinate validation with implementation.
Select the smallest validation that proves the change without drifting away from repo-native commands or existing proof workflows.

6. Report only the useful delta.
Summarize what changed, what was validated, and the single best next action if one remains.

## Copilot Efficiency Rules
- Produce complete answers in one pass whenever feasible.
- Minimize follow-up requests.
- Avoid redundant explanation.
- Prefer exact patches and exact commands.
- Keep working summaries short and current.

## Extension Synergy Rules
- Ruff decides lint expectations for Python changes.
- Data Wrangler mindset applies to any DataFrame or tabular artifact.
- Jupyter-style inspect, validate, transform sequencing applies to notebook or data work.
- GitLens-style reasoning applies to every change: keep diffs minimal and reviewable.
- Error Lens mindset applies before editing is finalized: prevent obvious errors proactively.
- Test Explorer mindset applies whenever behavior changes: identify how it will be validated.
- Path Intellisense logic applies whenever paths are mentioned or edited.

## Workflow Orchestration Rules
- Treat code, tests, notebooks, and validation as one connected system.
- Keep the repo workflow minimal, deterministic, and reviewable.
- Prefer existing proof commands, test entry points, and repo conventions over custom one-off flows.
- Keep outputs compatible with local review, PR review, and follow-up maintenance.
- Preserve shared-contract compatibility across stage boundaries.

## Token Economy Rules
- Use the fewest words necessary.
- Avoid restating full environment context unless it changed.
- Prefer structured outputs, exact files, and exact patch plans.
- Compress anything that would create repetition without adding new information.

## Decision Rules
- If a task would waste tokens through repetition: compress it.
- If a tool choice would add steps without improving correctness: reject it.
- If a repo-native command already covers the need: prefer it.
- If validation can be scoped more narrowly without losing confidence: narrow it.
- If the shortest path would reduce rigor or safety: choose the safer path instead.

## Required Output
Every use of this skill should produce:
1. A short diagnosis of the workflow bottleneck or optimization target.
2. The exact files or surfaces involved.
3. The minimal toolchain path chosen.
4. The exact patch, command, or action plan.
5. Validation performed, or an explicit statement that it was not run.
6. The single best next action if one remains.

## Output Style
- Always be short, exact, and actionable.
- Always mention the best next action only.
- Never produce generic filler.
- Never restate the full environment unless it changed.

## Failure Mode
If a response would waste tokens or create repetition:
- Compress it.

If multiple tool paths exist:
- Choose the one with the fewest steps and highest correctness.

If the task still lacks the information needed for a safe direct answer:
- Ask only for the minimum missing evidence.

## Completion Criteria
The task is complete only when one of these is true:
- The chosen toolchain path has produced a concise, correct, reviewable result with proportional validation.
- The workflow has been deliberately stopped because the minimum missing evidence was not available.

This skill optimizes the PRDV3 development loop for correctness, speed, and minimal waste.