---
name: repo-hygiene-ci-guardian
description: 'Use when repository hygiene, commit readiness, generated artifact cleanup, CI triage, warning or skip investigation, PR-based delivery, or atomic commit discipline is required. Covers git status and diff inspection before commit, untracking runtime artifacts, treating unexpected skips or warnings as defects, and switching to PR workflow automatically when branch protection blocks direct push.'
argument-hint: 'Describe the repo hygiene or CI issue, target files, current git state, validation output, and whether commit or PR flow is involved.'
user-invocable: true
---

# Repo Hygiene + CI Guardian

This skill hardens repository state before commit or push and keeps CI behavior deterministic, auditable, and clean.

## Use This Skill When
- Preparing a commit or push.
- Investigating CI failures, warnings, skips, xfails, leaks, or hangs.
- Cleaning generated or runtime artifacts from the working tree.
- Converting a direct-push path into a PR workflow because of branch protection.
- Verifying that a change is atomic, minimal, and relevant.

## Non-Negotiable Rules
- Never commit tracked generated, runtime, log, cache, or temporary artifacts.
- Before commit, inspect both git status and git diff.
- Treat unexpected `SKIP`, `XFAIL`, warnings, file-handle leaks, and slow hangs as defects unless a test contract explicitly justifies them.
- If pytest shows `SKIP`, `XFAIL`, or warnings, investigate and explain the cause before proceeding.
- Untrack runtime artifacts before commit instead of hiding the problem.
- If the diff is large, mixed-purpose, or unclear, stop instead of committing.
- If branch protection blocks direct push, switch to PR workflow automatically.
- If CI fails, keep fixing and retrying until green or until explicit missing evidence blocks further action.
- Commit only atomic, minimal, relevant changes.
- If validation is noisy or ambiguous, fail closed, explain why, and keep investigating.

## Standard Procedure
1. Inspect git status.
2. Inspect the exact diff to be committed.
3. Remove or untrack generated and runtime artifacts.
4. Reproduce the first CI or test failure locally.
5. Investigate warnings, skips, leaks, and hangs as first-class defects.
6. Validate with the smallest command that proves the fix, then run broader proof if commit readiness requires it.
7. Recheck CI until status is green or a concrete blocker is identified.
8. Stage only the minimal relevant files.
9. If direct push is blocked, continue through a PR branch and recheck status checks.

## Required Output
1. Current hygiene or CI problem.
2. Exact files involved.
3. Why the state is unsafe or not commit-ready.
4. Minimal corrective action.
5. Validation run.
6. Remaining risk, if any.

## Completion Criteria
- No generated or runtime artifacts are being committed.
- The staged diff is atomic and relevant.
- Validation output is clean or explicitly justified.
- CI is green or blocked by explicit evidence that has been reported.
- The branch is ready for automated PR-based CI flow.
