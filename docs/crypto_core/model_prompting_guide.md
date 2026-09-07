# crypto_core Model Prompting Guide

<!-- CONTROL_PLANE_ROLE: AUTHORING_GUIDE -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> **Authoring guide, not authority.** This file describes HOW to write a good prompt for a lane that
> canonical routing has ALREADY selected. It does not classify tasks into families, does not pick an
> effort, does not restate the routing matrix, and does not define PR sizing or merge authority. All
> of that lives in `docs/crypto_core/agent_os_v2.md`. If this guide and the canonical control plane
> ever appear to disagree, the canonical control plane wins.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.
> The single top-level prompt template is `PROMPT_COMPILER_V2_1`, canonical section 5. There is no
> competing top-level template, and nothing below introduces one.

## 1. Order of operations

1. The controller determines `TASK_INTENT` and reads the canonical routing matrix. That fixes the
   class, the lane and the effort. This guide has no say in it.
2. The controller compiles the twelve `PROMPT_COMPILER_V2_1` top-level fields for the task delta.
3. This guide supplies the SUBORDINATE profile: tone, context shape, decision latitude, testing
   budget, subagent policy and report shape appropriate to the selected lane.

Never invert that order. A prompt that argues for its own class is a prompt that has already escaped
the control plane.

## 2. What every serious prompt carries

The twelve canonical fields, in canonical order, and nothing bolted on top of them. Beyond the fields
themselves, three authoring rules matter most:

- **Task delta only.** Stable doctrine is loaded from the repository by the receiving agent. Do not
  paste doctrine into a prompt when the agent can read the committed file. A prompt that restates
  doctrine both wastes context and creates a second, divergent copy of it.
- **Exact over adjectival.** Exact paths, exact commands, exact invariants, exact stop conditions.
  "Be careful with the digest" is not a specification; "recompute the upstream digest through the
  public serializer and reject a mismatch before ACCEPTED" is.
- **Authority is stated, never implied.** Say precisely what the task may mutate and what it may not.
  Silence is not permission.

## 3. Forbidden in any compiled prompt

- Any request for hidden chain of thought.
- Any authority-widening instruction or its semantic equivalent: continue until done; keep fixing
  forever; retry until green; do everything automatically; approve your own work; merge when ready;
  ignore scope if necessary.
- Any instruction that would make an agent claim a gate it did not run, a model it did not use, or a
  state it did not prove.
- Credentials, tokens, exchange keys, private machine configuration, or live-trading and real-order
  instructions.

## 4. Subordinate profiles

These describe execution STYLE for an already-selected lane. None of them changes a family or an
effort.

### 4.1 Frontier reasoning profile (GPT-6 Astra)

Astra is instruction-sensitive: it follows what the prompt actually says, so vagueness costs more here
than elsewhere. Give the explicit outcome, the exact authority, the exact sources and the exact stop
condition. Say what "done" looks like.

- Routine reversible decisions inside the authorized scope: proceed without asking. Consequential
  authority or trust-boundary ambiguity: stop or ask the controller. State which is which.
- State the testing and verification budget explicitly, rather than leaving it to be inferred.
- State the subagent policy explicitly. Default 0.
- Do NOT instruct it to load the whole repository merely because the context window is large. Name the
  read set; allow progressive disclosure on an unresolved reference, a cross-module invariant, a
  test-exposed dependency, or architecture that cannot be proven locally.
- For protected independent audit work, supply the controller-prepared narrow evidence packet: pinned
  base and head, exact changes, direct dependencies, the contract and its invariants, the protected
  risks, and the adversarial questions. Never supply the implementer's conclusions as audit premises.

### 4.2 Heavy local implementation profile (Claude Opus 5)

One strong prompt closes one entire coherent implementation contract, end to end.

- Give the COMPLETE dependency closure and the negative cases up front. A heavy lane wastes its
  advantage if it has to stop and ask for the second half of the contract.
- One writer. Default 0 subagents. No ceremonial self-review loops and no "check it again" language —
  name the deterministic gates instead.
- Say explicitly that a local self-check is implementation QA and never an independent audit.
- Give the exact validation ladder and the exact stop conditions, including the authorization gate the
  task must stop at.

### 4.3 Bounded implementation and ordinary review profile (Terra, Claude Sonnet 5)

- Concise, mechanically explicit, low-context, command-oriented, deterministic.
- Exact files, exact tests, explicit escalation triggers, and an explicit no-scope-expansion rule.
- Do not burden these prompts with architecture speculation, repository archaeology, broad alternative
  analysis or long report formats.
- Name the conditions that must send the task back to the controller rather than being absorbed.

### 4.4 Mechanical profile (Luna)

- Exact commands and exact expected output shapes. Status, polling, metadata, and already-authorized
  execution only.
- No semantic readiness judgement, no architecture decision, no design latitude.
- Terminal states only: the answer is the proven state, or `UNKNOWN`.

### 4.4a Host selector and capacity

Two rules govern how heavy a frontier setting to ask for, and both are about honesty and capacity
rather than taste.

Record the operator UI choice VERBATIM as `HOST_SETTING_RAW`. Do not map a UI label onto the
reasoning-effort enum unless that mapping is officially and provably established; where it is not,
the effort field stays `UNKNOWN` rather than guessed.

Ask for the LOWEST host reasoning level that safely proves the task (`LOWEST_SAFE_HOST_SETTING`,
canonical section 4.4): a lower setting for a bounded read or narrow review; High or Extra High for
serious broad review or architecture, chosen from actual complexity rather than from the subject
sounding important; Extra High as the normal strong default for a protected whole-contract audit.
Ultra only under canonical section 4.3, and never as the default for every protected audit — it
spends shared pool capacity that later audits need.

### 4.5 Preparation profile (Work)

- Read-only preparation, research and synthesis, under canonical section 7. Work draws on the SAME
  shared provider pool as Codex and the protected frontier lane, so `WORK_ENVIRONMENT_VALUE` must
  justify `SHARED_OPENAI_POOL_COST`: dispatch it for a persistent workspace, the cloud browser, large
  source synthesis, artifact creation or multi-source current research — never for a simple status
  question, a single-source question or a mechanical task.
- Require the Work return contract verbatim, including the claim-to-source map and the explicit
  separation of verified, inferred and unknown.
- State plainly in the prompt that a prepared packet is `WORK_PREPARED_NOT_AUTHORIZED`: it opens no
  PR, creates no second writer and inherits no authorization.
- Require source revisions to be pinned. A snapshot is never current remote state.

### 4.6 Research profile (Deep Research)

- One narrow current-fact question at a time, primary and official sources first.
- Require every claim to be labelled as verified external evidence, verified repository evidence,
  inference, or `UNKNOWN`.
- State that the result is advisory: it mutates nothing, approves no governance value, replaces no
  audit and waives no gate.
- Full protocol: `docs/crypto_core/deep_research_protocol.md`.

## 5. Independent audit prompts

An audit prompt is written for a FRESH context at a pinned head. It carries the exact changes, the
direct dependencies, the contract and its invariants, the protected-risk classification, the
adversarial questions, and the required report shape — and it never carries the implementer's
conclusions as premises.

Two rules are absolute. An implementation context never satisfies its own independent audit, and a
same-model second pass is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`. Protected Class-C work always goes to
the protected frontier lane named in canonical section 3.3; if that lane cannot run, the correct
output is `ASTRA_REQUIRED_BUT_UNAVAILABLE` and a stop — never a quieter substitute.

## 6. Report shape

Every serious prompt names the report fields it expects back, and those fields always include: the
result; the actual runtime identity and effort with an honest evidence class; the setup files actually
read and any gaps; the proven state; the exact changed files; validation results; PR, check and thread
state; blockers; and exactly one next safe action. Missing facts are `UNKNOWN`. Failure tails only,
never full success logs. No uncited repository claim.

## 7. Non-regression

Nothing in this guide narrows, renames, renumbers or absorbs a canonical lane; grants any authority;
weakens a gate; or introduces a second top-level prompt template. Temporary availability, quota or
billing state for any vendor is transient operational information recorded in a handoff for that task
only — it is never written into this guide and never changes a durable role.
