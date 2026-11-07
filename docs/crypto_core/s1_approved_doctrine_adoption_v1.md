# S1 Approved Doctrine Adoption V1

> **ADOPTION CHANGE · PARTIAL HUMAN GOVERNANCE DECISION · NO IMPLEMENTATION · NO PAPER ACTIVATION**
>
> Contract `S1_APPROVED_DOCTRINE_ADOPTION_V1`. With the matching change of `docs/PRDV4_MULTI_MARKET_CRYPTO.md`, this
> record installs exactly the doctrine that the human approved in the partial governance decision
> `S1_UNIFIED_DOCTRINE_PARTIAL_DECISION_V1` revision r1 (section 11). Both files take effect together, only through
> the adoption merge defined in section 0.1. An approved item then binds as written, read with section 0.4; every other
> item stays `PENDING_HUMAN_DECISION`, with no force and no default. This record approves no new number, and it
> authorizes no implementation, policy-artifact or approval-table entry, paper activation, order, capital, scheduler,
> readiness, connector, shadow or live step.

## 0. Status, source and reading rules

### 0.1 Status and effect

- **Adoption merge.** This record and the PRDV4 change take effect together, and only when four things hold: this
  change has passed its own protected T4 `CLASS_C_CROSS_CONTRACT` audit (GPT-6.1 Sol) with exact-head CI; the human has
  authorized its standard merge by naming the pull request, its exact head and the merge command
  (`docs/crypto_core/agent_workflow.md` section 24.5); that merge is done; and post-merge verification proves that
  `main` holds both files byte for byte as at that head, with PRDV4 equal to the blob of section 13.1. Until then
  neither file has force, and the PRDV4 of `main` binds as written.
- **Role.** PRDV4 holds the normative text of the approved amendments D1–D11 and D13–D15. This record holds what PRDV4
  does not: the governance decision record (section 11), the approved companion contracts (sections 3.3, 4, 5, 6 and
  8.2) and the adoption rules of this section. In the same way the LIMITED_S1_PAPER_V1 record keeps its method
  readings in `docs/crypto_core/edge_factory_design.md` section 1a, it adds no doctrine beyond the approved items.
  Between this record and PRDV4, PRDV4 governs, and between two safety rules the stricter one applies.
- **Tiers.** I constitutional: D1–D6. II doctrine: D7–D11 and D13–D15. III methodology: the approved contracts, and the
  pending methods and parameters. IV implementation: not authorized (section 0.7).
- **Standing rules** (`docs/crypto_core/governance_decision_framework.md` section 8): a model proposes and only a human
  approves a number; every approved number lives in exactly one digest-bound policy artifact; changing a number is a
  new version and a new digest; an unapproved value rejects and never defaults.

### 0.2 Source binding

| Field | Value |
|---|---|
| Source pull request | #432, `CLOSED` and not merged (closed 2026-11-07T07:53:48Z); historical evidence only |
| Source head | `81058e84a0f70446509eef8dc0e77f3b3c5f30f1`, tree `f635649f5b63107452c5ccc02b9cf49dd7dfc4d9` |
| Source base | `main` `afd6a3fc846dbcae0f64734fcbda3eecb7355970`, tree `84ed70edf439a153fcfde214760ae0a868b938f5` |
| Source PRDV4 | Blob `743a27174ff07a7f2d8a1362f3616ce0465fdf8c`, built on `main`'s blob `6511639a2837d4df70fe166693b60e24c9079b33` |
| Source proposal | `docs/crypto_core/s1_unified_doctrine_governance_proposal.md` at the source head, blob `3227065a1858a16fe6737d9083886761b6809f28` |
| Source CI | Run 42288109552, success, on the source head |
| Source audit | GPT-6.1 Sol, Ultra, protected T4 `CLASS_C_CROSS_CONTRACT`: ACCEPT, no P1, no P2 (controller-reported) |

The source text has no authority of its own: a closed unmerged pull request, its branch and its text never become
canonical state (`docs/crypto_core/continuity/CONTINUITY_INDEX.md`). By the human's explicit decision (section 11.1,
clause B) the human-selected text was reconstructed from the two source blobs on a new branch from accepted `main`,
and it becomes doctrine only as the content of this change, through the adoption merge. This change does not merge,
cherry-pick or rebase onto a commit of the source pull request, does not reuse its branch, and inherits none of its
audit verdicts or CI results.

### 0.3 Reading rules

- Sections 1–10 reproduce the source proposal under its own numbering, so that every cross-reference holds;
  sections 0, 11, 12 and 13 are new. Section 10.1 is rewritten for this change and keeps T-DOC-03 with its table. The
  source banner and source sections 0, 10.8, 11 and 12 are not reproduced (section 13.1).
- Every reproduced heading carries one status block:
  - **APPROVED** — binding from the adoption merge, as written and read with section 0.4; reproduced byte for byte.
  - **PENDING_HUMAN_DECISION** — non-normative reference, reproduced only because approved text refers to it. It has
    no force: no value, method, state or permission may be read, defaulted, implemented or admitted from it.
  - **REFERENCE** — supporting index, analysis or acceptance criteria. It adds no rule and binds only through the
    approved items it explains.
  - **MIXED** — a heading whose subsections differ; each subsection carries its own status.
- A number in a pending passage is a proposal, never a value. A pending item becomes doctrine only through a later
  human decision and a separate adoption change.
- Missing, unproven or unknown evidence stays BLOCKED or HOLD. No status block, quotation or verification row of this
  record is a permission.

### 0.4 Protective method separation

The human approved PROTECTIVE_OBLIGATION_LEDGER_V2 (section 6) without its two HC-labelled methods: the target path
(HC-11c) and the impact measure (HC-11f), each stated in one bullet of section 6.4. Both stay
`PENDING_HUMAN_DECISION`, and section 6.4 quotes both bullets as non-normative reference. Until a later human decision
approves a method and a separate change adopts it:

1. **No target path.** TARGET(t) is undefined. No value of it is computed, recorded or bound, including the TARGET(t)
   that a `MERGED` event would bind (section 6.3), and DEMAND(t) of a nonurgent obligation is undefined, at or after
   D_eff included.
2. **No impact measure.** The §1.19 pause (market impact above 1% pauses the closure for 5 minutes) stands as written,
   but its measure is undefined, so no child can be proven to lie outside an impact pause.
3. **No nonurgent child.** Each undefined bound is handled as an unproven cap (section 6.4): no nonurgent v2 child is
   derived or sent, the ledger records `CAP_UNPROVEN`, and a deadline that passes with Rem(t) > 0 appends
   `UNFULFILLED_PROTECTIVE_OBLIGATION_V1` with that reason. The obligation stays open, the schedule anchor and every
   deadline stay unchanged, and entries stay refused (section 6.1). The same holds while the participation method
   (HD-04, section 7) or its sources are unapproved (`CAP_UNPROVEN`) and while DEC-1 close-only authority is absent
   (`AUTHORITY_UNPROVEN`).
4. **Adopted as written.** The immutable position schedule anchor, the unique obligation identity, the deterministic
   event order, attributed fills counted once, the earliest applicable deadline, one child in flight, v1 STOP and
   MAX_HOLD precedence, the authenticated position and book, no invented fill, no zero crossing, permanent unfulfilled
   obligations, the integrity-class rules IR-1..IR-6 and the digest-chained replay (sections 6.1–6.7).
5. **Integrity class.** DEMAND(t) = Rem(t) under IR-5 reads neither pending method. A child still needs DEC-1
   authority valid at its instant, a trigger proven under IR-2 and a book authenticated under IR-4 (sections 6.1 and
   6.5), and the PR-B engine (section 6.7). No DEC-1 authority is approved and no PR-B engine exists, so no such child
   can be sent today. IR-2 names the operator raise channel by its decision id: its scope is HC-05d,
   `PENDING_HUMAN_DECISION`, and no scope is assumed.
6. **Unchanged.** The accepted v1 protective lifecycle stays byte-identical and keeps its precedence, and no deadline,
   cap or risk limit of PRDV4 is removed.

This section qualifies, and only to this extent: the impact measure id of the `caps` field and the target path of
section 6.2; the `PAUSED` event, the TARGET(t) binding of `MERGED` and the `IMPACT_PAUSE` reason of section 6.3; the
child-demand and impact-pause terms of section 6.4; the paced target of section 6.6; and the rows of section 10.5
named in its status block.

### 0.5 Fail-closed eligibility after adoption

Derived from the approved text and the pending decisions; the cited sections govern.

| Mechanism | Reachable result | Reason |
|---|---|---|
| `COLD_START_EXCEPTED` (D1–D8, U1–U5) | Never: an undefined covered reading stays BLOCKED and the entry HOLD | It needs an ACTIVE PAPER_INCUBATION_V1 record; the record schema (item 1.7), A_max, T_max, W_INC and every record approval are pending, and no approval table admits one |
| U5 Kelly coverage | Never | As above; after the first closed trade U5 never covers (section 8.2) |
| Allocation membership (section 4.1) | UNKNOWN, so every weight is BLOCKED | A_e cannot be proven, because no paper fill-rate or exchange-health proof exists (`docs/crypto_core/paper_trading_phase_map.md` lines 462–463), and EHS and Sharpe_30d cannot be proven while their methods (FCD-13) are pending |
| ENVELOPE_FIT (section 4.6) | BLOCKED or FAIL, never PASS | No MEMBER can be proven |
| SCALE-1 under A9′ (section 4.7) | BLOCKED or FAIL, never PASS | ENVELOPE_FIT cannot PASS; §1.24 calibration (HD-07) and the Kelly fit (items 5.1 and 5.2) are unproven |
| CTR depth cap (section 5) | BLOCKED; FAIL at or above 2% of the unadjusted depth | No source is qualified (X-M1-C) |
| Nonurgent v2 protective child | None | Section 0.4 |
| Integrity-class v2 protective child | None | No DEC-1 authority is approved and the PR-B engine does not exist (section 0.4) |
| v1 STOP and MAX_HOLD | Unchanged | Not touched (section 0.7) |
| Governed S1 entry | Refused, as before | Entry-safety rule set v7 is unchanged (section 0.7) |

### 0.6 FCD-07 and FCD-11

FCD-01..FCD-17 are the proposed register of the S1 final construction decision, kept outside this repository. This
record decides two of them, and only in the approved scope:

- **FCD-07 (SCALE-1).** The construction decision CL2-11 (`docs/crypto_core/paper_trading_phase_map.md` lines 451–453
  and 477) requires every allocation multiplier, the meta-layer weight included, to be proven exactly 1, and
  entry-safety rule set v7 implements it fail-closed (`governed_paper_entry_safety.py:1345` and `:1838`).
  A9′ (section 4.7, item 2.3) is approved as the amended reading for a later, separately authorized rule set: it
  replaces only the meta-layer term by ENVELOPE_FIT, and it keeps fixed-unit admission and every state-triggered
  multiplier, §1.24 calibration included. Until such a rule set is authorized, implemented, audited and merged, rule
  set v7 stays byte-identical and refuses everything A9′ would refuse; no evidence produced under rule sets v1–v7 is
  re-read under A9′.
- **FCD-11 (protective actions).** Approved as PROTECTIVE_OBLIGATION_LEDGER_V2 (section 6, item 4.2) with the
  separation of section 0.4. The engine executes only the v1 lifecycle, and KS and SS actions stay
  `BLOCKED_UNREPRESENTABLE` (`governed_paper_system_state.py:48`). The ledger is a specification; executing it needs the
  separately authorized PR-B engine contract (section 6.7).

Every other FCD decision, and every HC choice, stays pending (section 12.1).

### 0.7 Unchanged implementation

This change touches no code, test, rule set, seal, policy artifact, approval table or evidence:

- entry-safety rule set v7 stays byte-identical: `_ADMITTING` holds only PASS and PROVEN_NOT_APPLICABLE
  (`governed_paper_entry_safety.py:458`), SCALE-1 never passes (`:1345`, `:1838`), and every S1 entry is still refused
  (`docs/crypto_core/paper_trading_phase_map.md` line 500);
- the engine keeps one net position that never crosses zero (`historical_execution_economics.py:1235`), whole-position
  v1 STOP and MAX_HOLD attempts (`:162`, `:168`), `REDUCE` (`:1245`) and partial fills whose remainder is cancelled
  (`:2294`);
- KS and SS position, order and engine actions stay `BLOCKED_UNREPRESENTABLE` (`governed_paper_system_state.py:48`);
- no approval table gains an entry; the regime production table, for example, admits none
  (`governed_paper_regime_state.py:392`; `docs/crypto_core/paper_trading_phase_map.md` line 464).

Each of these is a separate, separately authorized contract, and none is implemented: the `COLD_START_EXCEPTED`
evaluator and the incubation record verifier; ENVELOPE_FIT and the bounded projection; A9′ (a new entry-safety rule set
and seal); the CTR qualification consumer; the v2 ledger and child scheduler (PR-B); and the participation method. No
DEC-1 protective authority (`docs/crypto_core/paper_trading_phase_map.md` line 351) is approved for the v2 ledger, and
no approval-table or policy-artifact entry is made.

## 1. Amendment index and deviations

> **Status: REFERENCE** — index of the approved PRDV4 amendments and their deviations; PRDV4 holds their text.

| Item | PRDV4 location | Change | Tier |
|---|---|---|---|
| D1 | §0.3 lead sentence | Names the single scoped exception | I |
| D2 | §0.3, after the invariant table | Scoped cold-start exception to INV-002 and INV-006 | I |
| D3 | §3 INV-002, Enforcement | Points to §0.3 | I |
| D4 | §3 INV-006, Enforcement | Points to §0.3 | I |
| D5 | §3 INV-EXEC-001, Statement | Incubation basis may carry `COLD_START_EXCEPTED`, never PASS | I |
| D6 | §8.6 | Points to §0.3; market-state gaps stay HOLD | I |
| D7 | §1.21 Enforcement, NO OVERRIDE | Names the record; it is not an override | II |
| D8 | §1.21, new PAPER_INCUBATION_V1 Exception Record | Scope, closed list, bounds, finality | II |
| D9 | §1.7, renormalization bullet and new Bounded Allocation | Joint floor, cap and total; residual unallocated for n ≤ 2 | II |
| D10 | §1.19 KS-4 action | Integrity-proven position and book; open remainder | II |
| D11 | §1.19 Position Closure Protocol, item 5 | Unfulfilled obligation; no child while the cap is unproven | II |
| D13 | §1.29 CRISIS (SS-3) rule | The earlier MICRO and INTRADAY deadline binds; joint constraints with KS-3; SWING untouched | II |
| D14 | §1.29 HALT (SS-4) rule | The D10 integrity rule | II |
| D15 | §1.2 A.4 | Qualified CTR source; L2 and model proxies rejected | II |

D12, the optional SS-3 table wording of the previous handoff, is folded into D13 and is not proposed.

Deviations from current doctrine, each needing the explicit approval named in section 11:

| Id | Deviation | Items |
|---|---|---|
| R1 | Constitutional cold-start exception to INV-002, INV-006, INV-EXEC-001, the §1.21 NO OVERRIDE rule and §8.6 | D1–D8 |
| R2 | When a deadline and a cap cannot both hold, the cap binds and the deadline becomes a recorded unfulfilled obligation | D11, D13 |
| R3 | An "immediate" KS-4 or SS-4 flatten waits for an integrity proof of the position and the book instead of acting on unproven state | D10, D14 |
| R4 | The one-pass floor/cap/renormalize rule becomes one joint projection; for n ≤ 2 the weights sum below 1.0; BOOST keeps its place before renormalization while the floor and the cap move to the joint final step; state reductions act after the projection and are never undone by the floor | D9 |
| R5 | The approved construction decision CL2-11 (SCALE-1) replaces its meta-layer term by ENVELOPE_FIT; this is not doctrine | A9′, section 4.7 |

Everything else tightens or clarifies: D15 and the CAP_UNPROVEN clause of D11 tighten. No data, risk, margin,
liquidation, regime, exchange-health, position-limit or protective limit is relaxed (section 10.1).

## 2. HID-1 — constitutional cold-start exception (D1–D6)

> **Status: REFERENCE** — rationale and scope proof of the approved D1–D6 (item 0.1); PRDV4 holds their text.

### 2.1 Conflict with current authority

> **Status: REFERENCE** — why the cold-start exception needs approved doctrine edits (item 0.1).

Current text: §0.3 ("No subsystem, edge, strategy, or operational decision may violate these"); INV-002 ("missing or
invalid data produces HOLD"); INV-006 ("all unknown states resolve to HOLD"); §3 INV-EXEC-001 ("All orders pass NT
conditions before submission"); §1.21 Enforcement ("NO OVERRIDE mechanism"); §8.6 ("Any data gap, unrecognizable
state, or unclassifiable condition → HOLD"). At cold start the edge's own Sharpe, fill-rate and Kelly readings are
undefined, so every governed S1 entry is HOLD under current doctrine. PRDV4 has no amendment clause, so legality
needs approved edits of these clauses; a reading of them never suffices.

§1.22 INCUBATION is no precedent: its candidate "passes ALL stages of §1.13 validation pipeline" first. The
doctrine's own cold-start tension is §1.13 Stage 4 ("Minimum 30 days live paper trading") against these clauses, and
LIMITED_S1_PAPER_V1 grants nothing for Stages 4–5 (§1.20).

### 2.2 Scope proof

> **Status: REFERENCE** — scope proof of item 0.1; its record-level rows rest on the pending item 1.7.

| Property | Rule | Matrix |
|---|---|---|
| S1 closed list | `COLD_START_EXCEPTED` is emitted only for U1..U5 (section 3.3); any other reading id is a construction error | T-INC-07 |
| S2 explicit absence | Covered only while the own count is below the window; σ = 0, an estimator singularity, an unapproved method choice or missing market data is never absence | T-INC-12, T-INC-13 |
| S3 never PASS | Outside the ordinary admitting set (`_ADMITTING`, `governed_paper_entry_safety.py:458`); readiness, Stage-4 and health consumers refuse an incubation-basis decision as evidence | T-INC-14 |
| S4 proven FAIL dominates | Evaluation order of section 3.4 | T-INC-08 |
| S5 non-history components stay ordinary | S_hitrate (N < 10 gives 0.5), S_drawdown, S_stability, the §1.5 latency and API legs, every other SCALE-1 multiplier | T-INC-09 |
| S6 never covered | Exclusion list of section 3.3 | T-INC-09..11 |
| S7 bounded | A_max, T_max and X; final states | T-INC-04..06, T-INC-17 |
| S8 path | Governed paper entries of one LIMITED_S1_PAPER_V1 lineage only | T-INC-16 |
| S9 separately authorized | Human approval of the exact record digest before S; the production approval table holds none today; a TEST_ONLY_SYNTHETIC approval is refused | T-INC-01..03 |

### 2.3 Five tiers

> **Status: REFERENCE** — the evidence tiers; tier 2 needs an ACTIVE record, which the pending item 1.7 prevents.

1. **Offline deterministic simulation**: EF-5..EF-8, FCD-12 replay, archive economics. Validation evidence only; it
   never fills an own-history window.
2. **Paper-incubation observation**: governed paper entries on the PAPER_INCUBATION basis under an ACTIVE record.
3. **Governed paper entry, ordinary basis**: every check PASS or proven not applicable.
4. **PRDV4 §1.13 Stage 4**: separate. Tiers 2 and 3 neither start, satisfy nor shorten it.
5. **Live execution**: forbidden and unreachable; INV-EDGE-004 requires all five §1.13 stages first.

§1.22 INCUBATION ("14-day shadow execution") is a post-§1.13 meta-layer stage. It is not tier 2, and nothing in this
record authorizes governed S1 admission through it.

## 3. PAPER_INCUBATION_RECORD_V1 (D8)

> **Status: MIXED** — 3.3 is APPROVED (item 1.2); 3.1, 3.2 and 3.4–3.7 are PENDING_HUMAN_DECISION (item 1.7).

### 3.1 Fields

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 1.7, section 11).

Canonical JSON through the public serializer. The record digest is the SHA-256 of the canonical bytes of the supplied
fields below; the derived end and the separate approval are not part of it. A consumer recomputes the digest and
rejects a mismatch before any admission.

| Field | Content | Verification |
|---|---|---|
| `schema` | `PAPER_INCUBATION_RECORD_V1` | Exact |
| `lineage` | Genesis id and digest G; `admission_scope` `LIMITED_S1_PAPER_V1`; bootstrap horizon H (C2) | Recomputed from the sealed genesis |
| `edge` | Edge id, strategy-spec digest, parameter digest | Equal to the executed strategy (validated == executed, FCD-12) |
| `validation` | EF-5 sealed preregistration digest, sealed before the result; EF-7 v2 PASS decision digest; trial-count chain head and its currentness proof | Each digest recomputed by its public serializer; currentness re-proved at every decision |
| `covered` | Nonempty subset of U1..U5 | Every id in U |
| `attempt_bound` | A_max | Approved integer ≥ 1; never defaulted |
| `duration_bound` | T_max in UTC days | Approved; never defaulted |
| `start` | S, a UTC instant | Approval instant ≤ S; S + T_max ≤ G + H |
| `end` | X = min(S + T_max, G + H) | Derived by the verifier; never supplied and not digested |

**Approval.** A separate human approval artifact (approver identity, channel `HUMAN_GOVERNANCE`, approval instant,
digest of the signed decision record) names this exact record digest and is entered in the production approval
table. It is not a field of the record, so the digest it approves never covers it.

### 3.2 States

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 1.7, section 11).

| State | Condition | Incubation basis |
|---|---|---|
| NOT_ESTABLISHED | No verified record, or t < S | None |
| ACTIVE | Verified, S ≤ t < X, attempts < A_max, not revoked | Allowed |
| GRADUATED (final) | The coverage of every covered reading ended (section 3.5) before the end | None; ordinary basis only |
| EXPIRED_HOLD (final) | t ≥ X, or the A_max-th attempt was admitted, while the coverage of a covered reading has not ended | None |
| REVOKED (final) | An approved human revocation record | None |
| TERMINATED (final) | Failed verification: digest, approval, validation currentness, lineage, a duplicate record or a duplicate observation | None |

Outside ACTIVE, a covered reading that is still undefined is BLOCKED and the entry decision is HOLD. A reading whose
coverage ended is an ordinary reading in every state: defined, it has its ordinary status; undefined, it is BLOCKED
(for U5, section 8.2). A final state is never left. No state change closes a position by itself; the protective rules
keep running.

### 3.3 Covered classes U and exclusions

> **Status: APPROVED** — binding from the adoption merge (item 1.2, section 11).

| Id | Reading | Window | Own history of | Feeds |
|---|---|---|---|---|
| U1 | Sharpe_30d (§1.6 Component 1) | 30 UTC days of returns | The edge | S_sharpe, EHS, NT-E01, NT-E02, NT-E04, α_edge, E_active, the BOOST condition |
| U2 | Sharpe_90d and DECAY_ALERT (§1.6) | 90 UTC days | The edge | §1.7 DE-WEIGHT and the BOOST condition |
| U3 | Fill rate of the last 10 orders (NT-X02) | 10 orders | The lineage, per exchange | NT-X02 |
| U4 | Fill rate of the last 20 orders (§1.5 Execution Conditions) | 20 orders | The lineage, per exchange | The §1.5 fill-rate leg, A_e, FB-ACTIVATION |
| U5 | Kelly estimate (§1.28) | Zero closed trades only; coverage ends at the first closed trade (section 8.2) | The edge | p, b, f\*, G(f), the Kelly fit of SCALE-1 |

Never covered: §1.24 calibration (HD-07); exchange health, meaning the §1.5 latency and API-error legs, NT-X01, NT-X04
and KS triggers #7 and #9 (X-H1); CTR and depth (section 5); CVaR (NT-R05); every NT-D, NT-R and NT-M check; NT-E03;
NT-X03; every NT-T check; every FB check except the U4 leg of FB-ACTIVATION; system state; KS and SS levels; open
protective obligations; margin, liquidation and DTL; capacity; ENVELOPE_FIT; Σf ≤ 0.04 on actual risk at stop; any
reading proven to fail.

### 3.4 Evaluation of a check with a covered reading

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 1.7, section 11).

1. Reading defined: the ordinary status.
2. Reading undefined, and the check refuses under every completion of the missing own history: FAIL. A completion is
   any value the missing observations could take. Completions can prove FAIL, never PASS.
3. Reading undefined only for missing own history, record ACTIVE, reading id in the record's covered list, and every
   non-history component of the check PASS: `COLD_START_EXCEPTED`.
4. Otherwise: BLOCKED.

Examples. NT-E02: S_drawdown is a non-history component read from the paper equity path, so DD ≥ the edge's maximum
gives DISABLED and FAIL whatever Sharpe_30d becomes. NT-E01 can never fail by completion: the maximal Sharpe
completion (S_sharpe = 1) contributes 0.30 on its own, so at cold start NT-E01 is `COLD_START_EXCEPTED` or BLOCKED.
α_edge = 1 needs EHS ≥ 0.70; with S_sharpe = 1, EHS is at most 0.30 + 0.25·S_hitrate + 0.25·S_drawdown +
0.20·S_stability, and if that maximum stays below 0.70 the α_edge reading is FAIL and SCALE-1 refuses.

An entry is admitted on the PAPER_INCUBATION basis only when the record is ACTIVE, at least one check is
`COLD_START_EXCEPTED`, each such check owes that status to covered readings only, and every other check is PASS or
PROVEN_NOT_APPLICABLE. The decision records the basis and the record digest.

### 3.5 Attempts, uniqueness, own history and negative evidence

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 1.7, section 11).

- **Attempt.** An entry decision admitted on the incubation basis, counted at admission whether or not it fills.
  Exits, protective closes and refused entries are never attempts.
- **Uniqueness.** At most one record per (G, edge), ever. A second approved record for the same key terminates both.
- **Own history.** Governed-paper observations of this lineage, keyed by (lineage, sequence), counted only from the
  sealed digest-chained lineage by the public verifier. A replay of the lineage reproduces the same counts and adds
  none. A duplicate or out-of-order observation id terminates the record. Tier-1 simulation, other lineages, archive
  economics, backtests and any fill not authenticated as a governed-paper observation never count.
- **Graduation.** Per reading and irreversible: once a window holds enough own observations (for U5, one closed
  trade), the coverage of that reading ends. The reading is ordinary for good, whether or not it is defined, and is
  never covered again.
- **Negative evidence.** Every observation stays in the lineage. A proven failure stays a failure through graduation,
  expiry, revocation and termination. A record never erases, discounts or restarts history, and an edge that ended
  in EXPIRED_HOLD, REVOKED or TERMINATED is never incubated again in that lineage.

### 3.6 Parameters: proposals only, never defaults

> **Status: PENDING_HUMAN_DECISION** — the proposals below are not values: no force, no default (items 1.4–1.7, section 11).

| Parameter | Proposal | Basis | Status |
|---|---|---|---|
| A_max | 20 entry attempts | The largest covered order window (U4); fewer if HC-14a counts exits as orders | PENDING_HUMAN_DECISION |
| T_max | 90 UTC days | The largest covered day window (U2); a shorter bound expires before U2 can graduate | PENDING_HUMAN_DECISION |
| T_max against C2's H | The record is refused unless S + T_max ≤ G + H (`INCUBATION_HORIZON_EXCEEDS_LINEAGE`); X = min(S + T_max, G + H) stays as a backstop | C2 sets H ≥ 30 UTC days; with T_max = 90 the lineage needs H ≥ (S − G) + 90 days | PENDING_HUMAN_DECISION; H itself is pending under C2 |
| W_INC | 0.40, the hard cap | Section 4.6 | PENDING_HUMAN_DECISION |
| Covered list | Any nonempty subset of U | Section 3.3 | PENDING_HUMAN_DECISION |
| Kelly coverage after the first closed trade (HD-K1) | Not offered | U5 ends at the first closed trade (section 8.2); an extension would be a separate change | NOT_OFFERED |

No new risk constant is proposed. One attempt risks at most the §1.27 INTRADAY single-position limit (8% of NAV)
times its 1.5% stop, about 0.12% of NAV plus fees, excluding gaps through the stop.

### 3.7 Reachability (not a safety property)

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (items 1.7 and 1.8, section 11).

Incubation admits nothing until all of these hold: HD-07 decides calibration, which is never covered; X-H1 qualifies
exchange health; every non-covered check is PASS-capable (FCD-01..17 approvals and the X-* sources); the protective
engine of section 6 exists; DEC-1 authority covers the FB-MAX-HOLD horizon; and C1–C9 carry approved values. Two
viability limits remain: under strict Kelly no entry is admitted after the edge's first closed trade (F-3,
section 8.2), and a 30-day window of zero returns leaves Sharpe_30d undefined (σ = 0, F-4) until HC-13a sets a
convention.

## 4. ALLOCATION_ENVELOPE_V1 (D9; FCD-07)

> **Status: APPROVED** — binding from the adoption merge (items 2.2 and 2.3, section 11).

### 4.1 Eligibility at each rebalance

> **Status: APPROVED** — binding from the adoption merge (item 2.2, section 11).

Rebalances run at 00:00 UTC and on every edge state transition (§1.7).

- **MEMBER**: A_e = PASS and EHS ≥ 0.30, both defined and proven at the rebalance instant.
- **NON_MEMBER**: A_e proven FAIL, EHS defined and below 0.30 (DISABLE), or proven outside the top five.
- **UNKNOWN**: anything else. One UNKNOWN candidate leaves n and every weight unproven, so every weight is BLOCKED.
- **INCUBATION_MEMBER** (only if D1–D8 are adopted and a record is ACTIVE): exactly one candidate; the only non-PASS
  leg of A_e is U4 and the only undefined EHS input is U1, each `COLD_START_EXCEPTED` and neither FAIL.
- **Selection** (n > 5): top five by EHS × Sharpe_30d; ties broken by the higher EHS, then by the ascending edge id
  compared as UTF-8 bytes.

### 4.2 Share vector

> **Status: APPROVED** — binding from the adoption merge (item 2.2, section 11).

- v_i = max(EHS_i × Sharpe_30d,i, 0), as §1.7 writes it; r_i = v_i / Σv, or 1/n when every numerator is 0.
- BOOST β_i = 1.2 when "Sharpe_30d > 1.5 AND EHS > 0.80 AND no DECAY_ALERT" is proven true and 1 when it is proven
  false. When it is unknown (DECAY_ALERT undefined), the weights are computed with and without the boost; if they are
  identical the result stands, otherwise every weight is BLOCKED.
- t = (r ⊙ β) / Σ(r ⊙ β), so BOOST keeps its doctrinal place before renormalization.

### 4.3 Bounded projection

> **Status: APPROVED** — binding from the adoption merge (item 2.2, section 11).

- **3 ≤ n ≤ 5.** w is the minimizer of Σ(w_i − t_i)² subject to Σw_i = 1 and 0.05 ≤ w_i ≤ 0.40.
  - *Feasibility*: the set is nonempty iff 0.05·n ≤ 1 ≤ 0.40·n, i.e. 2.5 ≤ n ≤ 20, which holds for n = 3, 4, 5.
  - *Uniqueness*: a strictly convex objective over a nonempty compact convex set has exactly one minimizer.
  - *Form* (KKT): w_i = min(0.40, max(0.05, t_i + λ)) with λ chosen so that Σw = 1.
  - *Computation*: exact rational arithmetic. Sort the breakpoints {0.05 − t_i} ∪ {0.40 − t_i}. The function
    g(λ) = Σ min(0.40, max(0.05, t_i + λ)) is continuous, nondecreasing and piecewise linear, with g = 0.05·n ≤ 1 at
    the lowest breakpoint and g = 0.40·n ≥ 1 at the highest. On the segment where g crosses 1 the set I of unclipped
    coordinates is fixed, and λ = (1 − Σ_{clipped} bound − Σ_{i∈I} t_i) / |I|. When I is empty every λ in the segment
    gives the same w. The inputs are the exact decimal values of the approved EHS and Sharpe methods (FCD-13).
- **n ∈ {1, 2}.** Σw = 1 is infeasible under the cap, so w_i = min(0.40, max(0.05, t_i)); the residual 1 − Σw stays
  unallocated and is never redistributed.
- **n = 0.** No allocation.

Properties:

| Id | Property |
|---|---|
| P1 | 0.05 ≤ w_i ≤ 0.40 for every member, for every n ≥ 1 |
| P2 | Σw = 1 for 3 ≤ n ≤ 5; 0.45 ≤ Σw ≤ 0.80 for n = 2; Σw = 0.40 for n = 1 |
| P3 | For n ≥ 3, if t already lies in the box then w = t: the current rule's result wherever that rule is consistent |
| P4 | Order-preserving: t_i ≤ t_j implies w_i ≤ w_j |
| P5 | Deterministic and exact; the minimizer is unique, so no tie in w can arise |
| P6 | Only proven members enter; no unknown is normalized into a weight |

P1 concerns the weight. A proven state reduction (DE-WEIGHT, correlation halving, combined-drawdown reduction)
multiplies the edge's allocation limit after the projection and may take that limit below 0.05; it is a risk
reduction, never a weight, and the floor never undoes it.

The current one-pass rule (clip, then divide by the sum) breaks the cap when the clipped sum is below 1 and the floor
when it is above 1; section 4.4 lists both cases.

### 4.4 Worked examples (exact)

> **Status: APPROVED** — binding from the adoption merge (item 2.2, section 11).

| Case | t | D9 weights w | Σw | One-pass result |
|---|---|---|---|---|
| n = 0 | none | none | 0 | none |
| n = 1 | 1 | 0.40 | 0.40 | 1.00 (cap broken) |
| n = 2 | 0.70, 0.30 | 0.40, 0.30 | 0.70 | 0.571, 0.429 (cap broken) |
| n = 2 | 0.50, 0.50 | 0.40, 0.40 | 0.80 | 0.50, 0.50 (cap broken) |
| n = 2 | 0.97, 0.03 | 0.40, 0.05 | 0.45 | 0.889, 0.111 (cap broken) |
| n = 3 | 0.50, 0.30, 0.20 | 0.40, 0.35, 0.25 | 1 | 0.444, 0.333, 0.222 (cap broken) |
| n = 3, two caps | 0.45, 0.45, 0.10 | 0.40, 0.40, 0.20 | 1 | 0.444, 0.444, 0.111 (cap broken) |
| n = 3, numerators 1, 0, −2 | 1, 0, 0 | 0.40, 0.30, 0.30 | 1 | 0.80, 0.10, 0.10 (cap broken) |
| n = 3, all numerators ≤ 0 | 1/3 each | 1/3 each | 1 | unchanged |
| n = 4 | 0.55, 0.25, 0.15, 0.05 | 0.40, 0.30, 0.20, 0.10 | 1 | 0.471, 0.294, 0.176, 0.059 (cap broken) |
| n = 4, floor collision | 0.40, 0.40, 0.19, 0.01 | 29/75, 29/75, 53/300, 0.05 | 1 | 0.385, 0.385, 0.183, 0.0481 (floor broken) |
| n = 5, floor collision | 0.40, 0.40, 0.15, 0.04, 0.01 | 23/60, 23/60, 2/15, 0.05, 0.05 | 1 | 0.381, 0.381, 0.143, 0.0476, 0.0476 (floor broken) |
| n = 5, cap pressure | 0.90, 0.025 × 4 | 0.40, 0.15 × 4 | 1 | 0.667, 0.083 × 4 (cap broken) |
| n = 5, equal | 0.20 each | 0.20 each | 1 | unchanged |
| BOOST at the cap, r = 0.40, 0.30, 0.30 | 4/9, 5/18, 5/18 | 0.40, 0.30, 0.30 | 1 | current pipeline gives 4/9 ≈ 0.444 (cap broken) |
| BOOST inside, r = 0.30, 0.35, 0.35 | 18/53, 35/106, 35/106 | equal to t | 1 | unchanged |

Further cases:

- **Missing EHS or Sharpe_30d.** The candidate is UNKNOWN, so every weight is BLOCKED. With D1–D8 adopted and n = 1
  under an ACTIVE record, it may be INCUBATION_MEMBER (section 4.6).
- **DE-WEIGHT.** In the n = 3 case above, a DECAY_ALERT on the second edge halves its allocation limit from 0.35 to
  0.175 after the projection. The 0.175 residual stays unallocated, and SCALE-1 is FAIL for that edge's entries
  (section 4.7).
- **Disabled edge.** EHS below 0.30 makes the edge NON_MEMBER; the emergency rebalance re-projects the rest.
- **Fixed-unit excess.** With B = 100,000 and a floored weight 0.05, the envelope is 5,000. An S1 entry reservation
  u·L_k = 8,000 makes ENVELOPE_FIT FAIL. u is never resized.

### 4.5 Capital quantities

> **Status: APPROVED** — binding from the adoption merge (item 2.2, section 11).

| Symbol | Quantity | Source | Relation |
|---|---|---|---|
| E0 | Economics `initial_equity` | Accepted EF-6 economics (C1) | Equity origin: NAV(G) = E0 |
| R | C5 equity-basis reference notional | `governance_decision_framework.md` C5; `multi_sleeve_risk_governance_design.md` | R == E0 exactly, re-proven at genesis; a difference is a structural block |
| K | RG-2 `max_paper_risk_budget` | RG-2 | Bounds the RG-7 admission cap: u·L_k ≤ `admission_cap_fraction` × K; no doctrine relation to E0 |
| B(t) | Publication-visible NAV | The engine's equity on the same publication-visible snapshot as every other admission check | The envelope base; missing gives BLOCKED |

The envelope introduces no capital quantity and no capital commitment. "Committed paper capital" is not a repository
artifact and is not used.

### 4.6 ENVELOPE_FIT

> **Status: APPROVED** — binding from the adoption merge (item 2.2, section 11).

Checked at the decision instant t and again at the fill instant t_f, for exposure-increasing entries only; never for
exits or protective actions.

- usage_dec = abs(q_pre) · mark(t) + u · L_k, where q_pre is the edge's open position and u · L_k bounds the filled
  notional (`historical_execution_economics.py` rejects a fill whose filled × price exceeds requested × L_k).
- usage_fill = abs(q_post) · mark(t_f).
- w is the edge's weight from the latest rebalance at or before the instant.

| Status | Condition |
|---|---|
| PASS | MEMBER and usage ≤ w · B |
| COLD_START_EXCEPTED | INCUBATION_MEMBER and usage ≤ W_INC · B |
| FAIL | MEMBER and usage > w · B; INCUBATION_MEMBER and usage > W_INC · B; NON_MEMBER and usage > 0; or usage > 0.40 · B for any eligibility, UNKNOWN included |
| BLOCKED | Anything else, including UNKNOWN eligibility with usage ≤ 0.40 · B and an unproven B or usage |

A fill-time FAIL refuses the fill and leaves the position unchanged, as the engine already does for a fill above its
price ceiling (`governed_paper_price_ceiling_exceeded`); it is never a partial resize. For S1 the §1.27 INTRADAY
single-position limit (8% of NAV) is the tighter bound whenever the weight is at least 0.08, so the envelope's main
role there is the eligibility gate.

### 4.7 SCALE-1 under A9′ (amends CL2-11; FCD-07)

> **Status: APPROVED** — binding from the adoption merge as the CL2-11 reading of a later, separately authorized
> rule set; entry-safety rule set v7 stays unchanged until then (item 2.3, sections 0.6 and 11).

CL2-11 today requires every allocation multiplier, the meta-layer weight included, to be proven exactly 1, so SCALE-1
can never PASS (`governed_paper_entry_safety.py:1345` and `:1838`). Since a weight is at most 0.40, the meta-layer
term can never equal 1. A9′ replaces that term by ENVELOPE_FIT and keeps every other term:

| Status | Condition |
|---|---|
| PASS | ENVELOPE_FIT PASS, every state-triggered multiplier proven exactly 1, and the Kelly fit proven |
| FAIL | Any multiplier proven below 1, f\* ≤ 0 proven, or ENVELOPE_FIT FAIL |
| COLD_START_EXCEPTED | Incubation basis, every non-PASS component a covered reading resolving `COLD_START_EXCEPTED`, all others PASS |
| BLOCKED | Anything else |

State-triggered multipliers: α_edge (§1.6); DE-WEIGHT, correlation halving and combined-drawdown reduction (§1.7); the
KS level (§9.2); latency against twice the tier budget (§1.16); the system state (§1.29); crowding (§1.11); capacity
tier (§1.15); regime dimensions and leverage (§1.17, §0.2); §1.24 calibration, which the current unproven list omits
(F-1); margin and DTL bands (§1.26). The engine cannot downsize a fixed unit, so a proven multiplier below 1 refuses the
entry; it never admits it at full size.

## 5. CTR_SOURCE_QUALIFICATION_V1 (D15; HAD-3)

> **Status: APPROVED** — binding from the adoption merge (item 3.2, section 11); it qualifies no source.

The CTR (§1.2 A.4) is N_cancels / N_trades over the 60 seconds before the reading instant. α_CTR = 1 when CTR ≤ 5.0,
and 1 / (1 + 0.2 × (CTR − 5.0)) above. The depth cap (§1.12 Mechanism 2, §7.2) applies the stricter wording: order
size strictly below 2% of the visible depth within 5 bps of mid, scaled by α_CTR.

| Field | Requirement |
|---|---|
| Source identity | Provider, dataset or channel, venue, exact instrument, version |
| Source class | `ORDER_LEVEL_EVENTS` (authenticated per-order add, cancel and trade events) or `VENUE_PUBLISHED_COUNTS` (venue-published cancellation and trade counts) |
| Rights | Licence or terms reference and digest, permitted uses, and confirmation that the source may be processed by this system |
| Definitions | What counts as a cancel (full, partial reduction, amend) and as a trade (per match or aggregated), consistent with A.4 |
| Point in time | Publication instant and authenticated receipt instant per event; an event counts at a reading instant only if received at or before it |
| Sequencing | Monotone sequence ids; a gap, duplicate or reorder inside the window makes the reading BLOCKED |
| Coverage | The whole 60-second window is covered, proven by sequence continuity or venue heartbeats |
| Qualification | Version, digest, human approver, approval instant; supersession and revocation apply from their instant |
| Proof instants | A reading at the decision instant and another at the fill instant |

Evaluation, with q the order quantity and D the visible depth within 5 bps:

| Status | Condition |
|---|---|
| FAIL | abs(q) ≥ 0.02 · D, with no CTR needed, because α_CTR ≤ 1 |
| PASS | abs(q) < 0.02 · α_CTR · D, where CTR comes from a qualified source with full coverage at that instant |
| BLOCKED | Anything else, including no qualified source, incomplete coverage, N_trades = 0, or counts inferred from L2 changes or a model |

The fill model's own depth cap is unchanged. Whether any provider meets this qualification is UNKNOWN (X-M1-C); this
record asserts no provider.

## 6. PROTECTIVE_OBLIGATION_LEDGER_V2 (D10, D11, D13, D14; FCD-11)

> **Status: APPROVED, read with section 0.4** — item 4.2 (section 11); the HC-11c and HC-11f bullets of section 6.4 are pending.

### 6.1 Scope and precedence

> **Status: APPROVED** — binding from the adoption merge, read with section 0.4 (item 4.2, section 11).

- The ledger covers the KS-3 orderly closure, the SS-3 per-horizon exits, the proven KS-4 flatten and the proven SS-4
  flatten.
- The accepted v1 STOP and MAX_HOLD obligations stay byte-identical, keep precedence and are never subject to v2
  caps. A v1 exit that closes the position discharges every v2 obligation on it.
- At most one close-only attempt per position is in flight. A child never exceeds the remaining position and never
  crosses zero (`historical_execution_economics.py:1235` rejects a zero crossing).
- Every child needs DEC-1 close-only authority valid at its instant; without it no child is sent and the ledger
  records `AUTHORITY_UNPROVEN`.
- While any obligation is open, entries are refused.

### 6.2 Obligation record and position schedule

> **Status: APPROVED** — binding from the adoption merge, read with section 0.4 (item 4.2, section 11).

Each proven trigger opens one obligation record. Every v2 obligation on one open position belongs to one position
schedule, whose anchor is fixed by the first of them; all quantities and the target path live on the schedule.

| Obligation field | Content |
|---|---|
| `obligation_id` | SHA-256 of the canonical (lineage, position id, trigger kind, trigger proof digest, opened instant) |
| `trigger_kind` | `KS3_CLOSE`, `SS3_CLOSE`, `KS4_FLATTEN` or `SS4_FLATTEN` |
| `trigger_proof` | Digest of the verifier's proof of the level at the opened instant |
| `integrity_class` | True exactly for `KS4_FLATTEN` and `SS4_FLATTEN` |
| `opened` | τ_k, the injected PIT instant at which this trigger became known |
| `deadline` | The absolute deadline D_k. KS-3: τ_k + 30 min. SS-3: MICRO τ_k and INTRADAY τ_k + 15 min; SWING follows the §1.29 rule (close unless DTL > 15% and EHS > 0.70, an unproven condition closing), its deadline is not set by doctrine and it is outside S1. KS-4 and SS-4: τ_k |
| `position_at_trigger` | abs(q_k), the verifier's position at τ_k; a record only, it never resizes the schedule |
| `caps` | Participation method id and digest or `CAP_UNPROVEN`; impact measure id (HC-11f); liquidity-regime halving; the fill model's depth cap |

| Schedule field | Content |
|---|---|
| `schedule_id` | SHA-256 of the canonical (lineage, position id, obligation id of the first v2 obligation) |
| `anchor_opened` | ANCHOR_OPENED = τ0, the opened instant of the first v2 obligation on the open position |
| `anchor_q0` | ANCHOR_Q0 = abs(q0), the verifier's position at τ0 after every event that precedes the trigger at τ0 (section 6.6). Both anchor values are re-derived from the sealed position and trigger history; neither is ever supplied or read from executor state |
| `anchor_digest` | SHA-256 of the canonical (schedule id, ANCHOR_OPENED, ANCHOR_Q0, first trigger proof digest, digest of the verifier's position proof) |
| `effective_deadline` | D_eff(t), the minimum of D_k over the open nonurgent obligations of the schedule at t |
| `closed` | C(t), the sum of the verified close-only fill quantities on the position since ANCHOR_OPENED, each fill id counted once, from every source: v2 children and v1 STOP or MAX_HOLD attempts |
| `remaining` | Rem(t) = min(ANCHOR_Q0 − C(t), abs(the verified position at t)); a difference between the two terms is a history inconsistency (section 6.4) |
| `children` | Child id, decision instant, requested quantity, attributed fill ids, filled quantity, VWAP |

The anchor is fixed when the schedule opens and never changes: a joining trigger, a later fill, a replay or a restart
neither moves ANCHOR_OPENED nor resizes ANCHOR_Q0. While any obligation is open no exposure-increasing fill is
admitted (section 6.1), so the position only falls after τ0, and a merge never creates exposure. The schedule ends
only at `DISCHARGED`; a later position on the same instrument gets a new schedule.

### 6.3 Lifecycle

> **Status: APPROVED** — binding from the adoption merge, read with section 0.4 (item 4.2, section 11).

Events are append-only and digest-chained per schedule, each carrying the digest of the previous event:

`OPENED`, `CHILD_SENT`, `CHILD_FILLED`, `PAUSED` (impact), `CAP_UNPROVEN`, `AUTHORITY_UNPROVEN`, `BOOK_UNAVAILABLE`,
`POSITION_UNPROVEN`, `INTEGRITY_UNPROVEN`, `MERGED`, `DEADLINE_MISSED`, `DISCHARGED`.

- `OPENED` records the first obligation and the schedule anchor (`anchor_digest`).
- `MERGED` records a joining obligation and binds: the anchor digest; the joining obligation id and trigger proof
  digest; D_eff before and after; the cumulative fill proof (the ordered attributed fill ids and quantities, and
  C(t)); the id and requested quantity of any child or v1 attempt in flight, which is not counted as closed; the
  effective caps (participation method ids and digests or `CAP_UNPROVEN`, impact measure, liquidity-regime halving)
  and the DEC-1 authority digest; and TARGET(t) recomputed exactly (section 6.4). It changes no earlier event.
- At a deadline with Rem(t) > 0, the ledger appends `UNFULFILLED_PROTECTIVE_OBLIGATION_V1`: obligation id,
  deadline, remaining exposure, and a reason from `CAP_BINDING`, `CAP_UNPROVEN`, `IMPACT_PAUSE`, `BOOK_UNAVAILABLE`,
  `POSITION_UNPROVEN`, `INTEGRITY_UNPROVEN`, `AUTHORITY_UNPROVEN`, `V1_PRECEDENCE` or `ENGINE_UNREPRESENTABLE`. The
  obligation stays open and closing continues under the same caps. The record never asserts that the position closed.
- `DISCHARGED` only when the verifier proves the position is zero from the sealed ledger.
- Fills are attributed only from the accepted paper fill model on an authenticated PIT book (C-MODEL evidence). No fill
  is manufactured, inferred or carried from an unauthenticated book.

### 6.4 Deadlines, caps and child derivation

> **Status: APPROVED, except the two quoted bullets** — those (HC-11c, HC-11f) are PENDING_HUMAN_DECISION, and the
> child-demand and impact-pause terms are read with section 0.4 (item 4.2, section 11).

- **Effective deadline.** The earliest applicable deadline binds: D_eff(t) = min D_k over the open nonurgent
  obligations of the schedule. Obligations stay open until `DISCHARGED`, so D_eff never increases. A joining trigger
  keeps or advances it; a later, less urgent trigger changes nothing. Every applicable proven cap binds, so the
  strictest one binds.

> **PENDING_HUMAN_DECISION (HC-11c, item 4.4): non-normative reference, not adopted (section 0.4).**
>
> - **Target path (HC-11c proposal).** One cumulative position-level target on the schedule anchor, defined while the
>   schedule holds a nonurgent obligation (otherwise only the integrity-class rule below applies), for t ≥ τ0:
>   TARGET(t) = ANCHOR_Q0 · min(1, max(0, (t − τ0) / (D_eff(t) − τ0))) when D_eff(t) > τ0, and TARGET(t) = ANCHOR_Q0
>   when D_eff(t) ≤ τ0. A joining trigger never restarts the clock and never raises the owed quantity: TARGET never
>   exceeds ANCHOR_Q0 and never decreases, and a smaller D_eff only raises it.

- **Child demand and size.** DEMAND(t) = max(0, TARGET(t) − C(t)). A child is derived only when no child and no v1
  attempt is in flight on the position: child = min(DEMAND(t), Rem(t), R(t), the depth cap), where R(t) is the shared
  participation allowance of section 7 after the liquidity-regime halving, and every cap of every open obligation of
  the schedule applies (D13). It is sent only at an admissible authenticated book instant, with DEC-1 authority,
  outside an impact pause, and only when positive. Its quantity is truncated toward zero at the canonical decimal
  scale, never rounded up; Rem(t) is exact, so at or after D_eff the whole remainder is demanded. A binding cap is
  recorded `CAP_BINDING`; an unproven cap sends nothing (`CAP_UNPROVEN`). There is no fixed grid; a minimum spacing
  would be a performance choice.
- **No double counting.** C(t) counts attributed fills, never requests. A child or v1 attempt in flight adds nothing
  to C(t) until its fill is attributed, and no other child is derived while it is in flight. A fill id counts once,
  whichever obligation the child served, and an earlier fill is never re-attributed or rewritten by a merge.
- **History inconsistency.** If ANCHOR_Q0 − C(t) differs from the verified position, or the anchor, a trigger proof or
  the cumulative fill proof does not recompute from the sealed history (a broken digest chain, a missing or
  duplicated fill), the ledger records `POSITION_UNPROVEN` and sends no child. The schedule is never re-anchored at a
  later instant, and v1 STOP and MAX_HOLD exits are unaffected.
- **Integrity class.** While a proven KS-4 or SS-4 obligation is open, DEMAND(t) = Rem(t) under IR-5, without pacing,
  participation or impact pause, bounded by the independently authenticated book and the fill model. The anchor,
  C(t) and every event are kept.
- **v1 precedence.** A v1 STOP or MAX_HOLD attempt is the whole open position and keeps precedence (section 6.1).
  While a v1 obligation is outstanding its attempts hold the in-flight slot and no v2 child is derived; every v1 fill
  counts in C(t); a v2 deadline that passes meanwhile with Rem(t) > 0 is recorded with reason `V1_PRECEDENCE`. A v1
  trigger that arrives while a v2 child is in flight waits only for that child's outcome, as a v1 attempt already
  waits for an in-flight decision intent (`historical_execution_economics.py:168`), and then goes before any further
  v2 child.

> **PENDING_HUMAN_DECISION (HC-11f, item 4.5): non-normative reference, not adopted (section 0.4).**
>
> - **Impact pause (HC-11f proposal).** For each child, m = abs(fill VWAP − mid) / mid, with the mid taken at the
>   child's decision instant from the same authenticated book. If m > 1%, no child is sent for 5 minutes of injected
>   time after that fill.

- **Retry.** When no admissible authenticated book exists, or exchange unavailability is proven, the next attempt is at
  the first admissible instant at least 30 seconds later (§1.19 item 4).
- **Largest first.** With several positions, the highest notional at τ0 closes first; ties go by ascending position id.

### 6.5 Integrity-class rules (KS-4 is "System integrity threat", SS-4 is "System integrity compromised")

> **Status: APPROVED** — binding from the adoption merge, read with section 0.4 (item 4.2, section 11).

| Id | Rule |
|---|---|
| IR-1 | Every KS-4 and SS-4 obligation is integrity-class |
| IR-2 | The trigger is proven only by the independent verifier, from raw sealed inputs against anchors outside the lineage, or through the operator raise channel (HC-05d). The executor's self-report never proves or clears it |
| IR-3 | The target is the position the verifier re-derives from the sealed digest-chained ledger. A ledger that fails verification gives `POSITION_UNPROVEN` and no fill |
| IR-4 | Fills only from a book authenticated independently of the threatened component. A threatened feed or an unknown threat scope gives `INTEGRITY_UNPROVEN`, no fill, and never a stale book |
| IR-5 | The urgent walk is exempt from pacing, participation and the impact pause (§1.29 HALT: "urgency overrides impact"), but bounded by the authenticated book and the fill model. The remainder stays an open obligation; disabling the engines and the manual restart never discharge it, and entries stay refused until it is discharged |
| IR-6 | No fabricated fill, no zero crossing, no inferred higher level |

### 6.6 Concurrency, equal instants, replay and history

> **Status: APPROVED** — binding from the adoption merge, read with section 0.4 (item 4.2, section 11).

- Obligations on one position share one schedule (section 6.2): the earliest deadline, every cap, one child in
  flight. A proven integrity-class obligation supersedes the paced target (section 6.4). Each original record stays;
  a joining obligation appends `MERGED`.
- A trigger of a kind that already has an open obligation on the position, including a byte-identical repeat of a
  recorded trigger, opens nothing and appends nothing: its deadline is not earlier, so it cannot bind.
- **Equal instants.** Events at one injected instant apply in this fixed order:
  1. the outcome of every child or v1 attempt whose fill instant it is, so C(t) and Rem(t) include it;
  2. v1 STOP and MAX_HOLD triggers and attempts;
  3. newly proven KS and SS triggers in the order `KS4_FLATTEN`, `SS4_FLATTEN`, `KS3_CLOSE`, `SS3_CLOSE`, then by
     ascending trigger proof digest, each opening the schedule or appending `MERGED`;
  4. at most one child derivation, only when nothing is in flight;
  5. entry decisions, refused while any obligation is open.

  ANCHOR_Q0 is therefore the position after step 1 at τ0, and a `MERGED` event already counts a fill that lands at
  its own instant.
- The participation allowance is shared per (venue, instrument) across every open obligation (section 7.3).
- Deterministic replay from sealed inputs and injected instants reproduces the ledger byte for byte, using exact
  rational arithmetic. There is no autonomous loop: every instant is injected, and a deadline is evaluated at the
  first injected instant at or after it.
- History is permanent: no event is deleted or rewritten, fills recorded before a merge keep their records and
  quantities, and v1 histories verify under their original digests.

### 6.7 FCD-11 execution boundary

> **Status: APPROVED** — binding from the adoption merge, read with section 0.4 (item 4.2, section 11).

- **Engine today.** One net position that never crosses zero (`historical_execution_economics.py:1235`). A fill may be
  partial (`PARTIALLY_FILLED`, remainder cancelled, `historical_execution_economics.py:2294`), and a close smaller
  than the position is a `REDUCE` transition (`historical_execution_economics.py:1245`). A v1 STOP or MAX_HOLD attempt
  is the whole open position, close-only, one in flight, and a rejected or partial fill is re-attempted at its own
  instant (`historical_execution_economics.py:162`). There is no TWAP, no paced target, no KS or SS child scheduler
  and no v2 obligation ledger; KS and SS actions are `BLOCKED_UNREPRESENTABLE` (`governed_paper_system_state.py:48`).
  This ledger is a specification. Executing it needs a separately authorized engine contract (PR-B): v2 close-only
  children sized below the open position, the obligation ledger and position schedule, and child derivation at
  injected instants.
- **Outside this version.** The reductions of KS-1 (tighten stops by 25%), KS-2 (reduce positions to 50%), SS-1
  (reduce allocation by 30%) and SS-2 (tighten stops, reduce MICRO and INTRADAY positions) stay BLOCKED until HC-11a
  (trailing semantics) and HC-11b (the SS-2 target) are approved and the engine can represent them. Entries are
  refused meanwhile (NT-R01 and SCALE-1). The protective exit order type stays HC-11e.

## 7. Participation method (PARTICIPATION_METHOD_V1, pending)

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 4.3, section 11).

### 7.1 Status

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 4.3, section 11).

PRDV4 states several participation caps without one shared denominator. No formula is established doctrine. The
earlier daily-rate formula A(τ) = 0.02 · ADV · (τ − τ0) / 86,400 s is one candidate reading, not a verified rule.
Until a human approves a complete method and its sources are qualified, every participation cap that applies is
`CAP_UNPROVEN`: no KS-3 child is sent (D11), and v1 STOP and MAX_HOLD exits are unaffected. The open position then
stays bounded by its v1 stop and maximum hold, and entries stay refused (NT-R01).

### 7.2 Doctrine reconciliation

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 4.3, section 11).

| Rule | Text | Applies to | Volume measure | Reading here |
|---|---|---|---|---|
| §1.12 M2, §7.2 | Order below 2% of visible depth at 5 bps (hard cap) | Every order | Displayed depth | Fill-model cap; CTR per section 5 |
| §1.14, §7.8 | Orders above 5% ADV: split into children, max participation 2% of real-time volume | Orders above 5% ADV | Real-time traded volume | Applies only above 5% ADV; proving an order is at most 5% ADV needs ADV, otherwise `CAP_UNPROVEN` |
| §1.15 | PR_max = 2% of ADV of the asset class | Capacity K_max | ADV | Capacity model, not an execution rule |
| §1.17, §9.3 | CRISIS liquidity halves the maximum participation rate | Every participation cap | — | Halving; an unknown liquidity regime applies the halved rate |
| §1.19 item 2 | TWAP over 30 minutes with 2% ADV participation cap | KS-3 closure | ADV, reading pending | `CAP_UNPROVEN` until approved |
| §1.19 item 3 | Impact above 1% pauses 5 minutes | KS-3 closure | Impact measure (HC-11f) | Pending |
| §1.29 SS-3 | MICRO immediately; INTRADAY 15-minute TWAP | SS-3 | None stated | Deadline and target path only; §1.14 and §7.8 still apply above 5% ADV; D13 adds the KS-3 caps when KS-3 also applies |
| §1.29 SS-4, §1.19 KS-4 | Market orders, no TWAP | Integrity-class | Exempt (urgency) | IR-1..IR-6 |

### 7.3 Required method content

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 4.3, section 11).

An approvable method fixes, with a version and digest:

- **Denominator.** `ADV_RATE` or `REAL_TIME_VOLUME`, with exact units (base quantity or USD notional).
- **ADV.** Venue and exact instrument, or the asset class as §1.15 says, chosen and justified; trailing window of N
  complete UTC days; arithmetic mean of daily sums. Point in time: only days whose data was authenticated and
  received before τ0 count, and the value is frozen at τ0 for the obligation.
- **Real-time volume.** An authenticated, sequenced trade feed (X-M1-A); the cumulative window [τ0, τ) or a rolling
  window of W seconds; a gap makes the cap `CAP_UNPROVEN`.
- **Allowance.** A(τ), consumption F(τ) = every protective child fill on that venue and instrument since the earliest
  open obligation's τ0, and remaining R(τ) = A(τ) − F(τ). Concurrent obligations share one allowance.
- **Constraints.** Liquidity-regime halving; the impact pause (HC-11f); the depth cap.
- **Proof.** Each child carries the digests of its allowance inputs, so a replay recomputes the same allowance.

### 7.4 Candidate readings of the §1.19 "2% ADV participation cap"

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (item 4.3, section 11).

| Id | A(τ) | Assessment |
|---|---|---|
| P-A | 0.02 · ADV · (τ − τ0) / 86,400 s | Rate on ADV. Over 30 minutes it allows 1/2,400 of ADV. Needs ADV (X-D1-D) and its definition |
| P-B | 0.02 · V_market[τ0, τ) | Closest to the §1.14 "real-time volume" wording. Needs a qualified trade feed (X-M1-A) |
| P-C | 0.02 · ADV over the whole closure | Permits 24/25 (96%) of an average 30-minute volume, which is barely a cap; recommended for rejection |

No reading is adopted. The choice is HD-04, `PENDING_HUMAN_DECISION`.

## 8. Kelly undefined cases (§1.28)

> **Status: MIXED** — 8.2 is APPROVED (item 1.3); 8.1 is PENDING_HUMAN_DECISION (items 5.1 and 5.2).

### 8.1 Cases

> **Status: PENDING_HUMAN_DECISION** — non-normative reference: no force, no default (items 5.1 and 5.2, section 11).

Doctrine: f\* = (p·b − q)/b; p is the EWMA-weighted win rate over at most 100 trades (α = 0.05); b is average win over
average loss in the same window; f\* ≤ 0 gives no allocation; below 100 trades, quarter-Kelly; Σf ≤ 0.04; G(f) > 0;
Kelly is an upper bound and never overrides risk limits.

| Case | Reading | Status |
|---|---|---|
| K0: no closed trade | p, b and f\* undefined | Ordinary BLOCKED; under incubation U5 gives `COLD_START_EXCEPTED` |
| K1: closed trades, no win | Average win over an empty set: b undefined | BLOCKED, never FAIL. No completion can hold p fixed, because the win that would define b also changes p. Never covered (section 8.2) |
| K2: closed trades, no loss | b undefined | BLOCKED; "wins only gives f\* = 1" is rejected. Never covered (section 8.2) |
| K3: at least one win and one loss | b defined; p needs the EWMA normalization (HC-16b) | BLOCKED until HC-16b is approved; then f\* ≤ 0 is FAIL, otherwise f = 0.25·f\* below 100 trades; G(f) needs at least 2 trades |

No finite b is ever assumed. Σf ≤ 0.04 on actual risk at stop is never excepted. Throughout, an incubation stays
bounded by A_max, T_max, the KS triggers and the §1.6 drawdown rule (DD ≥ the edge's maximum disables the edge),
proven failures that are never covered.

### 8.2 U5 coverage boundary

> **Status: APPROVED** — binding from the adoption merge (item 1.3, section 11).

- **Scope.** U5 covers the Kelly reading only while the edge has zero closed governed-paper trades (case K0), and
  only under an ACTIVE record whose covered list holds U5.
- **Closed-trade count.** The number of the edge's governed-paper trades whose closing fill is in the sealed lineage
  at or before the decision instant, recomputed by the verifier. At one instant a closing fill is ordered before an
  entry decision, so an entry evaluated at the instant of the first closing fill already counts it. A close whose
  outcome at the decision instant is not yet proven leaves the count unproven; an unproven count is never zero, so
  U5 does not cover and the reading is BLOCKED (`KELLY_TRADE_COUNT_UNPROVEN`).
- **After the first closed trade.** U5 never covers the reading again. A loss alone (K1) or a win alone (K2) leaves b
  undefined: BLOCKED (`KELLY_RATIO_UNDEFINED`), never PASS, never FAIL and never `COLD_START_EXCEPTED`, and no
  positive f\* is assumed or fabricated. With both classes and HC-16b approved the reading is defined (K3): f\* ≤ 0
  is FAIL (`KELLY_NON_POSITIVE`), and no completion applies because coverage has ended. The §1.28 rules (no
  allocation at f\* ≤ 0, quarter-Kelly below 100 trades, Σf ≤ 0.04, G(f) > 0) stay exactly as written.
- **No reset.** Replay, revocation, expiry, termination and a new record never lower the count or restore coverage.
  The uniqueness rule (section 3.5) refuses a second record for the same (G, edge), and a lineage–edge pair is never
  incubated twice.
- **Consequence (F-3).** Every entry needs the Kelly fit of SCALE-1, so after the first closed trade no entry is
  admitted on either basis until the Kelly reading is defined. Positions already open stay under their protective
  rules.
- **Not offered.** Covering Kelly after the first closed trade (formerly offered as HD-K1) would relax §1.28 further.
  It would be a separate, unapproved constitutional and methodology change needing its own exact text, authorization
  and evidence. This record neither proposes nor implements it.

## 9. Trust boundaries, refusal vocabulary and versioning

> **Status: REFERENCE** — trust boundaries, refusal vocabulary and versioning of the contracts.

### 9.1 Trust boundaries

> **Status: REFERENCE** — the trust boundaries that the approved contracts state; it adds none.

| Boundary | Trusted side | Never trusted |
|---|---|---|
| Approval | A human approval of an exact digest through `HUMAN_GOVERNANCE`, entered in the production approval table | Model output, TEST_ONLY_SYNTHETIC approvals, caller text, unsigned records |
| Verification | The public verifier recomputing digests from sealed inputs | The executor's own state, self-reports and cached results |
| Market data | Authenticated, sequenced PIT ingress | L2-inferred or model-inferred counts, unauthenticated or stale books |
| History | The sealed digest-chained lineage | Offline simulation, replays counted as new observations, other lineages |
| External facts | Sources qualified by a human-approved record | Any provider claim without qualification (X-*) |

### 9.2 Refusal vocabulary (fixed codes, never caller text)

> **Status: REFERENCE** — the refusal codes of every contract; a code used only by a pending section is reserved, not active.

`INCUBATION_RECORD_ABSENT`, `INCUBATION_RECORD_DIGEST_MISMATCH`, `INCUBATION_AUTHORITY_NOT_HUMAN`,
`INCUBATION_NOT_STARTED`, `INCUBATION_EXPIRED`, `INCUBATION_ATTEMPTS_EXHAUSTED`, `INCUBATION_REVOKED`,
`INCUBATION_TERMINATED`, `INCUBATION_DUPLICATE_RECORD`, `INCUBATION_CLASS_NOT_COVERED`,
`INCUBATION_HORIZON_EXCEEDS_LINEAGE`, `OWN_HISTORY_DUPLICATE_OBSERVATION`, `ALLOCATION_MEMBERSHIP_UNPROVEN`,
`ALLOCATION_BOOST_UNPROVEN`, `ENVELOPE_EXCEEDED`, `ENVELOPE_NON_MEMBER`, `CTR_SOURCE_UNQUALIFIED`,
`CTR_COVERAGE_INCOMPLETE`, `CTR_NO_TRADES`, `DEPTH_CAP_EXCEEDED`, `CAP_UNPROVEN`, `CAP_BINDING`, `IMPACT_PAUSE`,
`BOOK_UNAVAILABLE`, `POSITION_UNPROVEN`, `INTEGRITY_UNPROVEN`, `AUTHORITY_UNPROVEN`, `V1_PRECEDENCE`,
`ENGINE_UNREPRESENTABLE`, `KELLY_TRADE_COUNT_UNPROVEN`, `KELLY_RATIO_UNDEFINED`, `KELLY_METHOD_UNAPPROVED`,
`KELLY_NON_POSITIVE`.

### 9.3 Versioning

> **Status: REFERENCE** — contract versioning; PAPER_INCUBATION_RECORD_V1 and PARTICIPATION_METHOD_V1 stay pending.

- Contracts: `PAPER_INCUBATION_RECORD_V1`, `ALLOCATION_ENVELOPE_V1`, `CTR_SOURCE_QUALIFICATION_V1`,
  `PROTECTIVE_OBLIGATION_LEDGER_V2`, `UNFULFILLED_PROTECTIVE_OBLIGATION_V1` and `PARTICIPATION_METHOD_V1` (pending).
  Each carries a schema id and a digest through the public serializer.
- A later implementation is opt-in and separately authorized: a new entry-safety rule set (v8) adding
  `COLD_START_EXCEPTED`, ENVELOPE_FIT and A9′, a new seal version, and a v2 protective ledger. Rule sets v1–v7, the
  v1 protective lifecycle and every historical evidence digest stay byte-identical.
- Every approved number lives in exactly one policy artifact. Changing it is a new version and a new digest; old
  evidence stays historical under its old digest.

## 10. Verification matrix (acceptance criteria for later implementation)

> **Status: REFERENCE** — acceptance criteria for a later, separately authorized implementation; no row is a permission.

### 10.1 Doctrine consistency

> **Status: REFERENCE** — rewritten for this change; T-DOC-03 and its table are reproduced from the source.

- **T-DOC-A1.** The PRDV4 of this change equals the source PRDV4 without its pending notice, without the bullet that
  D9 replaces and without its proposal tags (section 13.1). Against the PRDV4 of `main` it removes exactly that bullet
  and inserts the thirteen approved passages, so no other doctrine text changes.
- **T-DOC-A2.** No `[UNAPPROVED PROPOSAL Dn]` tag and no pending notice remains in PRDV4.
- **T-DOC-03.** Clause review: every affected PRDV4 clause, and whether a hard rail is relaxed.

| PRDV4 clause | Items | Effect | Hard rail relaxed? |
|---|---|---|---|
| §0.3 INV-002, INV-006 | D1, D2 | Scoped exception, closed list, never PASS | R1 only, by design |
| §0.3 INV-001, INV-003, INV-004, INV-005 | None | — | No |
| §3 INV-002, INV-006, INV-EXEC-001 | D3–D5 | Pointers to §0.3 | R1 only |
| §3 INV-EDGE-004, §1.13, §1.20, §1.22 | D8 grants nothing | Stage 4, Stage 5, live and §1.22 untouched | No |
| §8.6 | D6 | Market-state gaps stay HOLD | R1 only |
| §1.21 NT-D, NT-R, NT-M, NT-E03, NT-X01, NT-X03, NT-X04, NT-T | D7, D8 exclusions | Never covered | No |
| §1.21 NT-E01, NT-E02, NT-E04, NT-X02 | D8 | Covered only while own history is short; FAIL dominates | R1 only |
| §1.5 Execution Conditions | D8 | Fill-rate leg only; latency and API legs never | R1 only |
| §1.6 EHS and FSM | D8 | Sharpe windows only; S_hitrate, S_drawdown, S_stability, DISABLED and QUARANTINE unchanged | R1 only |
| §1.7 | D9 | Floor and cap hold exactly; n ≤ 2 leaves a residual | R4: the cap is enforced, the sum is not forced |
| §1.2 A.4, §1.12 M2, §7.2 | D15 | Qualified CTR; L2 and model proxies rejected | No (tightening) |
| §1.19 KS-0..KS-3, triggers, escalation, cool-downs | None | — | No |
| §1.19 KS-4 | D10 | Integrity-proven flatten | R3 |
| §1.19 Position Closure Protocol | D11 | Unfulfilled obligation; `CAP_UNPROVEN` | R2 |
| §1.24, §1.27, §1.28 | None | Calibration never covered; Σf ≤ 0.04 never excepted | No |
| §1.29 SS-3, SS-4 | D13, D14 | Joint constraints; integrity rule | R2, R3 |
| §1.14, §7.8, §1.15, §9.3 | None | Reconciled in section 7 | No |

### 10.2 Allocation

> **Status: REFERENCE** — acceptance criteria of the approved D9 and ALLOCATION_ENVELOPE_V1 (items 2.1–2.3).

| Id | Condition | Required result |
|---|---|---|
| T-ALLOC-01 | n = 0 proven | No allocation; an exposure-increasing entry fails ENVELOPE_FIT; n unproven gives BLOCKED |
| T-ALLOC-02 | n = 1 | w = 0.40, residual 0.60 |
| T-ALLOC-03 | n = 2 | The three n = 2 rows of section 4.4 |
| T-ALLOC-04 | n = 3 | 0.40, 0.35, 0.25 |
| T-ALLOC-05 | n = 4 | 0.40, 0.30, 0.20, 0.10 |
| T-ALLOC-06 | n = 5 | 0.40 and 0.15 × 4; equal shares stay 0.20 |
| T-ALLOC-07 | Missing EHS | UNKNOWN; every weight BLOCKED |
| T-ALLOC-08 | Missing Sharpe_30d | UNKNOWN; every weight BLOCKED |
| T-ALLOC-09 | Zero or negative numerators | v = max(·, 0); all zero gives 1/n; 1, 0, −2 gives 0.40, 0.30, 0.30 |
| T-ALLOC-10 | Floor collisions | The n = 4 and n = 5 floor rows; the floor holds exactly |
| T-ALLOC-11 | Several capped edges | 0.40, 0.40, 0.20 |
| T-ALLOC-12 | BOOST at the cap | Absorbed by the cap; never above 0.40 |
| T-ALLOC-13 | BOOST condition unknown | BLOCKED unless the weights are identical with and without the boost |
| T-ALLOC-14 | DE-WEIGHT | Allocation limit halved after the projection; residual unallocated; SCALE-1 FAIL |
| T-ALLOC-15 | Disabled edge | Removed; the rest re-projected |
| T-ALLOC-16 | Fixed-unit excess | ENVELOPE_FIT FAIL; u never resized |
| T-ALLOC-17 | Fill-time usage above w · B | Fill refused; position unchanged |
| T-ALLOC-18 | Regression | No output of the one-pass rule that breaks a bound (section 4.4) is ever produced |
| T-ALLOC-19 | Tie at the fifth place | Higher EHS, then ascending edge id |
| T-ALLOC-20 | Rendering | Truncation at two or more places never crosses a bound |

### 10.3 Incubation security

> **Status: REFERENCE** — acceptance criteria of the pending item 1.7; they apply only once it is approved.

| Id | Condition | Required result |
|---|---|---|
| T-INC-01 | No record | Covered readings BLOCKED; HOLD |
| T-INC-02 | Wrong authority (TEST_ONLY_SYNTHETIC, model or unknown approver) | HOLD |
| T-INC-03 | Wrong digest | TERMINATED; HOLD |
| T-INC-04 | t ≥ X | EXPIRED_HOLD; HOLD |
| T-INC-05 | A_max attempts admitted | EXPIRED_HOLD; HOLD |
| T-INC-06 | Revoked record | HOLD |
| T-INC-07 | A reading outside the record's list or outside U | BLOCKED; HOLD |
| T-INC-08 | A proven hard-limit failure (for example NT-R03, NT-R04, NT-R05) | FAIL dominates every exception |
| T-INC-09 | Exchange health missing (X-H1) | BLOCKED |
| T-INC-10 | Calibration missing (HD-07) | BLOCKED |
| T-INC-11 | CTR missing | Depth BLOCKED; FAIL at or above 2% of unadjusted depth |
| T-INC-12 | σ = 0 in a Sharpe window | Not absence; BLOCKED |
| T-INC-13 | Missing market data inside a window | Not absence; BLOCKED |
| T-INC-14 | An incubation-basis decision offered as readiness, Stage-4 or health evidence | Refused |
| T-INC-15 | A second record for the same (G, edge) | Both TERMINATED; HOLD |
| T-INC-16 | Offline, archive or replayed observations; a duplicate observation id | Never counted; a duplicate terminates the record |
| T-INC-17 | An incubation-basis entry at or after X | Refused; no permission survives the end |
| T-INC-18 | A defined reading | Never `COLD_START_EXCEPTED` again |
| T-INC-19 | A proven failure before the end | Still FAIL after graduation or expiry |
| T-INC-20 | S + T_max > G + H | Record refused |
| T-INC-21 | First closed trade under an ACTIVE record, a loss or a win | U5 coverage ends; Kelly BLOCKED; HOLD (T-KELLY-07..12) |
| T-INC-22 | Exits and protective attempts | Never counted as attempts |

### 10.4 CTR

> **Status: REFERENCE** — acceptance criteria of the approved D15 and CTR_SOURCE_QUALIFICATION_V1 (items 3.1 and 3.2).

| Id | Condition | Required result |
|---|---|---|
| T-CTR-01 | No qualified source | Depth never PASS (BLOCKED) |
| T-CTR-02 | abs(q) ≥ 0.02 · D | FAIL without CTR |
| T-CTR-03 | Counts inferred from L2 changes or a model | Rejected |
| T-CTR-04 | Sequence gap, duplicate or reorder in the window | BLOCKED |
| T-CTR-05 | Window not fully covered | BLOCKED |
| T-CTR-06 | N_trades = 0 | BLOCKED |
| T-CTR-07 | Qualification revoked or superseded | BLOCKED from that instant |
| T-CTR-08 | CTR at or below 5.0, and above it | α_CTR = 1, and the exact §1.2 A.4 formula |
| T-CTR-09 | Decision PASS but fill-time reading fails | Fill refused |
| T-CTR-10 | An event received after the reading instant | Excluded |

### 10.5 Protective safety

> **Status: REFERENCE** — acceptance criteria of the approved ledger (items 4.1 and 4.2). The TARGET(t) and
> nonurgent DEMAND(t) results of T-PROT-18 to T-PROT-24, T-PROT-26, T-PROT-28, T-PROT-29, T-PROT-31 and T-PROT-32,
> and the impact pause of T-PROT-04, test the pending HC-11c and HC-11f methods: until both are approved those
> results do not apply and no nonurgent child is derived (`CAP_UNPROVEN`, section 0.4). T-PROT-05 and T-PROT-28
> also need the pending participation method (HD-04).

| Id | Condition | Required result |
|---|---|---|
| T-PROT-01 | Missing book | No child; `BOOK_UNAVAILABLE`; retry at least 30 s later |
| T-PROT-02 | Corrupted ledger (broken digest chain) | `POSITION_UNPROVEN`; no child |
| T-PROT-03 | Executor position differs from the verifier's | The verifier's value; the mismatch recorded |
| T-PROT-04 | Impact above 1% | No child for 5 minutes |
| T-PROT-05 | Insufficient participation allowance | Child at most R(τ); none when R(τ) ≤ 0 |
| T-PROT-06 | Missed deadline | `UNFULFILLED_PROTECTIVE_OBLIGATION_V1`; obligation stays open and continues |
| T-PROT-07 | Partial fill | Remaining reduced; no zero crossing |
| T-PROT-08 | KS-3 and SS-3 at once | One schedule: earliest deadline, every cap, one child in flight |
| T-PROT-09 | Proven KS-4 or SS-4 | Urgent walk without pacing, participation or pause, bounded by the authenticated book |
| T-PROT-10 | Failed independent integrity proof | `INTEGRITY_UNPROVEN`; no fill; obligation open |
| T-PROT-11 | Legacy history | v1 STOP and MAX_HOLD bytes and digests unchanged |
| T-PROT-12 | Cap unproven | No KS-3 child; v1 exits unaffected |
| T-PROT-13 | DEC-1 authority absent | No child; `AUTHORITY_UNPROVEN` |
| T-PROT-14 | Manual restart | Never discharges an open obligation |
| T-PROT-15 | Entry while an obligation is open | Refused |
| T-PROT-16 | Replay | Byte-identical ledger |
| T-PROT-17 | Executor self-report clearing KS-4 | Ignored |

Merged schedules (sections 6.2, 6.4 and 6.6). Unless stated, KS-3 opens at minute 0 on a position of 10 (deadline
minute 30), books are authenticated, DEC-1 authority holds, the allowance is not binding, and the only injected
instants with child activity are those named. An actual child always still needs a valid book, authority and caps.

| Id | Condition | Required result |
|---|---|---|
| T-PROT-18 | SS-3 INTRADAY joins at minute 10 (deadline 25) | Anchor kept (minute 0, ANCHOR_Q0 = 10); D_eff = 25; TARGET(10) = 4; DEMAND 4, 2 and 0 for C = 0, 2 and 4 |
| T-PROT-19 | Second trigger before the first fill | DEMAND = TARGET; nothing counted as closed |
| T-PROT-20 | Second trigger after a partial fill (child of 2 at minute 6 fills 1 at minute 7; join at minute 10) | C = 1; DEMAND = 3; the earlier fill unchanged |
| T-PROT-21 | Duplicate trigger (a second KS-3 proof at minute 5, or a repeat of the recorded one) | Nothing opened or appended; TARGET(10) = 10/3 |
| T-PROT-22 | Later, less urgent trigger (SS-3 at minute 20, deadline 35) | D_eff stays 30; TARGET(20) = 20/3 |
| T-PROT-23 | Immediate deadline (SS-3 MICRO joins at minute 10) | D_eff = 10; TARGET = 10; DEMAND = Rem |
| T-PROT-24 | First trigger due at its own instant (SS-3 MICRO at minute 0) | TARGET = ANCHOR_Q0 from minute 0 |
| T-PROT-25 | v1 STOP while v2 is open (a v2 child of 2 at minute 6 fills 2 at minute 7; the v1 attempt at minute 12 fills 3 at minute 13) | C = 5; Rem = 5; no v2 child while the v1 obligation is outstanding; a passed v2 deadline records `V1_PRECEDENCE`; a v1 close to zero discharges every v2 obligation |
| T-PROT-26 | Equal instant: a child of 2 in flight fills at minute 10 as SS-3 joins | Fill first (C = 2), then `MERGED` (TARGET 4), then one derivation (DEMAND 2); never 4 with a child in flight |
| T-PROT-27 | Child still in flight at the merge | `MERGED` records it, not as closed; no derivation until its outcome |
| T-PROT-28 | Allowance R = 1 at minute 10; unproven cap | Child of 1 with `CAP_BINDING`; no child with `CAP_UNPROVEN` |
| T-PROT-29 | Missing book at minute 10 | No child; `BOOK_UNAVAILABLE`; TARGET keeps rising; retry at least 30 s later |
| T-PROT-30 | Corrupted source history: the anchor or the fill proof does not recompute, or ANCHOR_Q0 − C differs from the verified position | `POSITION_UNPROVEN`; no child; never re-anchored; v1 exits unaffected |
| T-PROT-31 | Replay of a merged schedule | Byte-identical events, anchor, D_eff, C and TARGET |
| T-PROT-32 | Any trigger and fill sequence | D_eff never increases; TARGET never decreases and never exceeds ANCHOR_Q0; C ≤ ANCHOR_Q0; no child exceeds Rem; the position never rises or crosses zero |

### 10.6 Participation

> **Status: REFERENCE** — acceptance criteria of the pending participation method (item 4.3); they apply only once it is approved.

| Id | Condition | Required result |
|---|---|---|
| T-PART-01 | No approved method | `CAP_UNPROVEN` |
| T-PART-02 | ADV unavailable or not point-in-time | `CAP_UNPROVEN` |
| T-PART-03 | Concurrent obligations | One shared allowance |
| T-PART-04 | Liquidity CRISIS, or an unknown liquidity regime | Halved rate |
| T-PART-05 | Order above 5% ADV, or not proven at most 5% ADV | Real-time volume cap applies, or `CAP_UNPROVEN` |
| T-PART-06 | Replay | Identical allowance |

### 10.7 Kelly

> **Status: REFERENCE** — T-KELLY-07 to T-KELLY-12 test the approved section 8.2 (item 1.3); the other rows also read the pending section 8.1.

| Id | Condition | Required result |
|---|---|---|
| T-KELLY-01 | No closed trade | Ordinary BLOCKED; incubation U5 gives `COLD_START_EXCEPTED` |
| T-KELLY-02 | No win | BLOCKED, never FAIL |
| T-KELLY-03 | No loss | BLOCKED, never f\* = 1 |
| T-KELLY-04 | Both, HC-16b not approved | BLOCKED |
| T-KELLY-05 | f\* ≤ 0 | FAIL |
| T-KELLY-06 | Σf ≤ 0.04 on actual risk | Never excepted |
| T-KELLY-07 | ACTIVE record; the first closed trade is a loss | U5 coverage ends; b undefined; BLOCKED (`KELLY_RATIO_UNDEFINED`); entry HOLD; no positive f\* |
| T-KELLY-08 | ACTIVE record; the first closed trade is a win | Same; never f\* = 1 |
| T-KELLY-09 | The first closing fill lands at the instant an entry is evaluated; or a close is still unproven at that instant | The fill counts first: U5 does not cover, BLOCKED, HOLD; an unproven count gives `KELLY_TRADE_COUNT_UNPROVEN`, BLOCKED |
| T-KELLY-10 | Replay, revocation, expiry, termination or a second record after the first closed trade | The count never falls; U5 never covers again; no re-incubation |
| T-KELLY-11 | Defined Kelly (a win and a loss, HC-16b approved) with f\* ≤ 0 | FAIL (`KELLY_NON_POSITIVE`); never `COLD_START_EXCEPTED` |
| T-KELLY-12 | Closed trades of one class only, in any record state | BLOCKED; never PASS and never `COLD_START_EXCEPTED` |

## 11. Human governance decision record

### 11.1 Record

```text
HUMAN_GOVERNANCE_DECISION_RECORD_V1
RECORD            S1_UNIFIED_DOCTRINE_PARTIAL_DECISION_V1, revision r1
DECISION TYPE     Partial approval; the human stated it as PARTIAL_APPROVAL_NOT_ADOPTED (approval, not adoption).
                  The approved items take effect only through the adoption merge (section 0.1).
SOURCE VERSION    Pull request 432 (CLOSED, not merged) · head 81058e84a0f70446509eef8dc0e77f3b3c5f30f1
                  tree f635649f5b63107452c5ccc02b9cf49dd7dfc4d9 · base main afd6a3fc846dbcae0f64734fcbda3eecb7355970
                  PRDV4 blob 743a27174ff07a7f2d8a1362f3616ce0465fdf8c · proposal blob 3227065a1858a16fe6737d9083886761b6809f28
DECIDED BY        The human, as relayed by the ChatGPT controller. Approver identity: not recorded here (UNKNOWN).
CHANNEL           The human's ChatGPT conversation with the controller, relayed in the controller packet of contract
                  S1_APPROVED_DOCTRINE_ADOPTION_V1.
DECISION INSTANT  Not recorded (UNKNOWN). It follows 2026-11-07T07:53:48Z, the closing of pull request 432, which the
                  decision records as executed.
HISTORY           The decision was first submitted labelled PROPOSED / UNSIGNED; clause A approved it as this
                  exact-version record.
HUMAN REPLY       "ya hepsine yetki, veri,yorum" (verbatim, Turkish), read by the controller as YES to clauses A-D.
CLAUSES           As relayed by the controller:
  A               The exact-version partial governance decision is approved, with the stated pending exclusions
                  (section 11.2).
  B               ONE docs-only adoption pull request is authorized.
  C               Its merge needs a separate, future, exact-head human standard-merge authorization.
  D               Implementation, real paper, shadow and live, capital, scheduler and readiness changes, unapproved
                  values and production approval-table changes remain forbidden.
SIGNATURE         None. Accepted main defines no signature mechanism for a doctrine decision (UNKNOWN). This record
                  transcribes a chat decision truthfully; it is not a signed artifact and claims no signature.
BINDING ACT       The human's separate exact-head standard-merge authorization of this change (clause C;
                  agent_workflow.md section 24.5). Naming the exact head names the exact bytes of both files.
```

### 11.2 Decision per item

Items follow the source decision form. Classes: APPROVED (scope stated by the human, bounded to the exact source text
and its exclusions), PENDING_VALUE, PENDING_METHOD, PENDING_EXTERNAL_PROOF and NOT_AUTHORIZED. No item is rejected.

| Item | Content | Location | Decision |
|---|---|---|---|
| 0.1 | HID-1: D1–D6 verbatim | PRDV4 §0.3, §3 (INV-002, INV-006, INV-EXEC-001), §8.6 | APPROVED |
| 1.1 | D7 and D8 | PRDV4 §1.21 | APPROVED |
| 1.2 | Covered classes U1–U5, none struck, and the exclusion list | Section 3.3 | APPROVED |
| 1.3 | U5 boundary: zero closed trades only; coverage never returns | Section 8.2 | APPROVED |
| 1.4 | A_max | Section 3.6 (proposal only) | PENDING_VALUE |
| 1.5 | T_max and the refusal unless S + T_max ≤ G + H | Section 3.6 (proposal only) | PENDING_VALUE |
| 1.6 | W_INC | Section 3.6 (proposal only) | PENDING_VALUE |
| 1.7 | PAPER_INCUBATION_RECORD_V1 | Sections 3.1, 3.2, 3.4–3.7 | PENDING_METHOD |
| 1.8 | F-1..F-4 acknowledgments | Sections 3.7, 4.7 and 8.2 | PENDING_METHOD (the acknowledgments that accompany item 1.7) |
| 2.1 | D9 | PRDV4 §1.7 | APPROVED |
| 2.2 | ALLOCATION_ENVELOPE_V1 | Sections 4.1–4.6 | APPROVED |
| 2.3 | A9′ amends CL2-11 (FCD-07) | Section 4.7 | APPROVED |
| 3.1 | D15 | PRDV4 §1.2 A.4 | APPROVED |
| 3.2 | CTR_SOURCE_QUALIFICATION_V1 | Section 5 | APPROVED; PASS needs a separately qualified source (PENDING_EXTERNAL_PROOF, X-M1-C) |
| 4.1 | D10, D11, D13 and D14 | PRDV4 §1.19, §1.29 | APPROVED |
| 4.2 | PROTECTIVE_OBLIGATION_LEDGER_V2 (FCD-11) | Section 6 | APPROVED, except the HC-11c and HC-11f bullets (section 0.4) |
| 4.3 | HD-04: participation reading, ADV definition and window | Section 7 | PENDING_METHOD; its sources PENDING_EXTERNAL_PROOF |
| 4.4 | HC-11c: target path and minimum spacing | Section 6.4 (quoted) | PENDING_METHOD |
| 4.5 | HC-11f: impact measure | Section 6.4 (quoted) | PENDING_METHOD |
| 4.6 | HC-05d: KS-4 trigger scope | Section 6.5, IR-2 | PENDING_METHOD |
| 5.1 | Kelly undefined cases | Section 8.1 | PENDING_METHOD |
| 5.2 | HC-16b | Section 8.1 | PENDING_METHOD |
| Part 6 | FCD-01..17 stay pending, except FCD-07 and FCD-11 in the scope of items 2.3 and 4.2 | Section 0.6 | Consistent with the decision |
| Part 7 | Non-authorizations | Section 11.5 | Restated; clause B now authorizes this one adoption change |
| HD-K1 | Kelly coverage after the first closed trade | Section 8.2 | NOT_AUTHORIZED (not offered by the source) |
| Other | HD-07, HC-11a, HC-11b, HC-11e, HC-13a..c, HC-14a..b, HC-16a, HC-16c, HC-16d, every other FCD decision | Section 12.1 | PENDING_METHOD |
| Other | C1–C9; DEC-1 authority and its window | Section 12.1 | PENDING_VALUE |
| Other | Every X-\* source qualification, source entitlement and venue fact | Section 12.2 | PENDING_EXTERNAL_PROOF |

Item 5.1 adds no permission while it is pending: section 8.2 already resolves an undefined b after the first closed
trade as BLOCKED, and PRDV4 resolves every other undefined Kelly reading to HOLD (INV-006).

### 11.3 Constitutional dependency order

1. Item 0.1 (D1–D6, Tier I) is decided first. It is approved, so Part 1 is not void.
2. D7 and D8 rest on D1–D6, the classes U1–U5 on D8, and the U5 boundary on U5.
3. An incubation basis needs, beyond them, the record schema (item 1.7), A_max, T_max and W_INC (items 1.4–1.6) and a
   human-approved record admitted by an approval table, all pending. No approved Part 1 item can admit an entry.
4. Parts 2–5 stand without Part 1: A9′ rests on D9 and ALLOCATION_ENVELOPE_V1, the CTR method on D15, and the ledger on
   D10, D11, D13 and D14.
5. An approved item whose dependency is pending resolves BLOCKED or HOLD. A later approval of a pending item may
   complete a dependency, but it never changes the text of an approved item.

### 11.4 Revocation and supersession

- Only a later human decision that names this record and its revision changes it. It applies from its own instant and
  never retroactively, and the decision it supersedes stays in the history.
- A revocation before the adoption merge removes the revoked item from this change's authority, and this change may
  then not be merged as it stands. After the adoption merge, changing adopted doctrine needs a new doctrine change
  through its own audit and exact-head merge authorization; no adopted text is edited in place.
- No decision, revocation or supersession erases evidence: a proven failure stays a failure, history is permanent, and
  evidence produced before a change stays valid under its own digests.

### 11.5 Adoption scope and non-authorizations

- **Installed.** The approved amendments D1–D11 and D13–D15 in PRDV4, untagged and byte-equal to the source text, with
  the D9 replacement of one §1.7 bullet; and this record.
- **Not installed.** Any pending item as doctrine; any value; the source's decision-record lifecycle and adoption
  procedure (source sections 0.2, 0.3, 10.8 and 11) as a rule of any kind; HD-K1.
- **Not authorized** (clause D): implementation; production approval-table or policy-artifact entries; real, shadow or
  live paper; orders, fills and positions; PnL or capital; scheduler or auto-loop; readiness or connector transitions;
  the qualification of any external source.
- **Merge.** Not authorized by this record. Clause C requires a separate human authorization naming this change, its
  exact head and the standard-merge command.

## 12. Pending decisions, external dependencies and future authorization boundaries

### 12.1 Pending human decisions

Every entry below is `PENDING_HUMAN_DECISION`. No implementation, admission or default may assume any outcome.

| Id | Decision | Where it is described |
|---|---|---|
| 1.4, 1.5, 1.6 | A_max; T_max with the S + T_max ≤ G + H refusal; W_INC | Section 3.6 (proposals only) |
| 1.7 | PAPER_INCUBATION_RECORD_V1 | Sections 3.1, 3.2, 3.4–3.7 |
| 1.8 | F-1 (calibration never covered), F-2 (X-H1), F-3 (Kelly), F-4 (σ = 0) | Sections 3.7, 4.7 and 8.2 |
| 4.3, HD-04 | Participation reading, ADV definition and window | Section 7 |
| 4.4, HC-11c | Target path and minimum spacing | Section 6.4 (quoted) |
| 4.5, HC-11f | Impact measure | Section 6.4 (quoted) |
| 4.6, HC-05d | KS-4 trigger scope | Section 6.5, IR-2 |
| 5.1 | Kelly undefined cases | Section 8.1 |
| 5.2, HC-16b | EWMA normalization of p | Section 8.1 |
| HD-07 | §1.24 calibration | Sections 3.3 and 4.7 |
| HC-11a, HC-11b, HC-11e | Trailing semantics, the SS-2 target, the protective exit order type | Section 6.7 |
| HC-13a..c, HC-14a..b, HC-16a, HC-16c, HC-16d | The other HC choices | The S1 final construction decision register |
| FCD-01..17 | Every FCD decision outside items 2.3 and 4.2, the gated-strategy re-validation (FCD-12) included | The S1 final construction decision register |
| C1–C9 | Governed paper constants, C2's G and H included | `docs/crypto_core/governance_decision_framework.md` section 6a |
| DEC-1 | Close-only authority and its window | Sections 3.7 and 6.1 |

The numbers proposed in section 3.6 (A_max = 20 entry attempts, T_max = 90 UTC days, W_INC = 0.40) are proposals and
not values. They set no default, enter no policy artifact or approval table and are read by no implementation; each
needs its own human decision and a separate adoption change.

### 12.2 External dependencies

All are `UNKNOWN`: X-H1 exchange health; X-M1-A qualified, sequenced market data and book cadence; X-M1-C a CTR
source; X-D1-A..E venue facts, X-D1-D being ADV; X-M1-B, X-M1-D and X-M1-E; X-CAL; X-BTC; the S1 instrument identity.
Adoption qualifies no source and asserts no provider. Each source needs a human-approved qualification record, and
current external facts route through controller-orchestrated Deep Research.

### 12.3 Future authorization boundaries

| Step | Needs |
|---|---|
| Deciding a pending item | A human decision naming exact text or an exact value; every value in exactly one digest-bound policy artifact; a separate adoption change for doctrine text |
| Changing adopted doctrine | A new doctrine change, with its own protected audit and exact-head human merge authorization |
| Implementing an approved contract | A separately authorized implementation contract with its own audit: a new entry-safety rule set and seal for A9′ and ENVELOPE_FIT, the PR-B engine for the ledger. Rule sets v1–v7, the v1 protective lifecycle and every historical evidence digest stay byte-identical |
| An approval-table or policy-artifact entry | An explicit human approval of the exact digest; adopting doctrine never enters one |
| Qualifying an external source | A human-approved qualification record (section 5 for CTR) |
| Real, shadow or live paper; orders; capital | Blocked or forbidden; outside this record |

Construction stays `NOT_CLOSED`, and no pending decision or unknown dependency is an implicit PASS.

## 13. Adoption verification matrix

### 13.1 Content binding

PRDV4 at the head of this change is blob `6f5ad9177ee30e6e52a9c20c5c23cc3b00f578b7` (113,839 bytes, SHA-256
`235e2c4c679b1f9864c3fd02f8fcbdf8bc998daa9cf049bdc615697232122119`). It is the source PRDV4 blob without three things:
its pending notice; the D9 bullet "- After floor/cap: renormalize to sum to 1.0", together with its tag; and the
sixteen other `[UNAPPROVED PROPOSAL Dn]` tags, each with its bold markers and one adjacent space. Against `main`'s
blob `6511639a2837d4df70fe166693b60e24c9079b33` it removes that one bullet and inserts thirteen passages, each the
untagged source text of its approved item. This target holds while `main`'s PRDV4 is blob `6511639a`. A passage's
digest is SHA-256 over the UTF-8 bytes of its inserted text without leading or trailing line feeds, and its lines are
those of PRDV4 at the head.

| Item | PRDV4 location | Lines at the head | SHA-256 of the inserted text |
|---|---|---|---|
| D1 | §0.3, lead sentence | 36 | `f83b3f7c3ccbc8ab941ff22820f87026dd99aae80b3188ff14b420dfe82766f5` |
| D2 | §0.3, after the invariant table | 47–56 | `3e6b02f78751186f2d8652e1edad20081d5c3c94aa571a7946d45e8a37665412` |
| D15 | §1.2 A.4 | 241–246 | `e4cf82a05368dbf9fae68ae1156519f1b235109f9d60fadbac05750a77f20cb2` |
| D9 | §1.7, Bounded Allocation | 578–597 | `a2c22bbd3b6f08115838830d8ddf2acceed5c2548bb8f9f46c53596a7e63293a` |
| D10 | §1.19, KS-4 row | 1117 | `4a8efb8fc12847a5976c847da2080f7c8a924cd4dcbab499aadf36426d1a9566` |
| D11 | §1.19, Position Closure Protocol item 5 | 1154–1158 | `df1f3e01f5511f695df8071e6700750456390bae0625deb2289a2b439f0fd312` |
| D7+D8 | §1.21, Enforcement and PAPER_INCUBATION_V1 Exception Record | 1303–1333 | `97d5f70c0937873f10226f4665024683f63dde83cf76b7c6c85dfe68bab72849` |
| D13 | §1.29, CRISIS (SS-3) | 1839 | `7d31afc7a9e181b9c01ea8695125e6c13ae0559a6e40ac15ac506c0b914a4ab9` |
| D14 | §1.29, HALT (SS-4) | 1841 | `ca8023137a177e5d7e6e5b0029fd7f92271f3599391a04e5b001da96627919e9` |
| D3 | §3, INV-002 | 1930 | `9a67656038e806c821a55a7b15ed718b7ed1f30d8c14ac20d9b05514b53a697e` |
| D4 | §3, INV-006 | 1934 | `9a67656038e806c821a55a7b15ed718b7ed1f30d8c14ac20d9b05514b53a697e` |
| D5 | §3, INV-EXEC-001 | 1939 | `c08a48545c547fb94aaeb48f88da52b7b43d4a9234256c3b7d0e6ab62b0c8d36` |
| D6 | §8.6 | 2195 | `41e437ce74e89728bf4c00c6ec75ebda099aa2268647b20d55ed11c4f05b5c85` |

Source sections of blob `3227065a1858a16fe6737d9083886761b6809f28`. A section's text runs from its heading line
through the line before the next level-2 or level-3 heading, joined by line feeds, without trailing empty lines; the
digest is SHA-256 over its UTF-8 bytes. Apart from its status block, a verbatim section of this record reproduces that
text byte for byte. In section 6.4 the quote markers of the two pending bullets are the only other addition.

| Source section | Status here | Reproduction | SHA-256 of the source section |
|---|---|---|---|
| Title and banner | — | Not reproduced | `c4893b75452d1b4d51547dfe854ff021a22b648f1c5395f91699a463f75462f1` |
| 0 | — | Not reproduced | `b2ef7d39e303e948196a3df84deaf40db91e4f5a9e1321506668374550c6e1f6` |
| 0.1 | — | Not reproduced | `72b037c052c61c25e1eb797597d1239586ea15a24d8da435b00a588c8d855a20` |
| 0.2 | — | Not reproduced | `85cb41aed2509ebbd4b6acfa6b993b0d3c2627f23f563826ead3e13ec2a485e6` |
| 0.3 | — | Not reproduced | `d0824748a71a95ab2a5cb7690fb06c146c6ac356d1f8603418a9e31d0c549c4f` |
| 1 | REFERENCE | Verbatim | `0d747aec15494ac5647f258997bfe28b4f813859b89c0da93e93d39791dc324a` |
| 2 | REFERENCE | Verbatim | `759f1392a4adb8770782be1e910ce4fdf87532b7355996a1a47310a183b1a6a7` |
| 2.1 | REFERENCE | Verbatim | `8f84422258d2e727e32f15a914671a29b1a0e180daa8fe66938d6a33ab792b62` |
| 2.2 | REFERENCE | Verbatim | `0cbebeb45ced908f0070a997e5ba1af06a11c708cb28f4fa7a508767f468d44d` |
| 2.3 | REFERENCE | Verbatim | `39776e5daa1f3c969dc2b1993afa269ef771e33a1d172fd14485268cde3c633f` |
| 3 | MIXED | Verbatim | `954209086146e1186a8b8c2693858316f0338af1d1acce8c41bdba996d0eb66d` |
| 3.1 | PENDING_HUMAN_DECISION | Verbatim | `ca6cb0c22794e6feb34f06d0abc4233fc773d1ef7a2fc406333063bd95618cef` |
| 3.2 | PENDING_HUMAN_DECISION | Verbatim | `f119aed41755f9ab38edabc8613d7ee0ae19d1d40480c7f8553a017244c1237a` |
| 3.3 | APPROVED | Verbatim | `749d48bd095a9334bed425e5b40db4e6af85d74e680579ca8bfd347e928a1c22` |
| 3.4 | PENDING_HUMAN_DECISION | Verbatim | `2804c48c3f9b2e8039013645845e586057c95da04599330b70c811f95717e0c9` |
| 3.5 | PENDING_HUMAN_DECISION | Verbatim | `bedd7d98aeaf79863a092e6ac5462fc78c5887a772d5ab06121c771731932c9d` |
| 3.6 | PENDING_HUMAN_DECISION | Verbatim | `3303f6a4477bd878e4ecf660914916ba2a42be5fbca570b0a145ecfcf0ea377f` |
| 3.7 | PENDING_HUMAN_DECISION | Verbatim | `00e7f642e78f111f6cb789b30f6526bd8e2b5918aa80fb61568c5beff2d4233b` |
| 4 | APPROVED | Verbatim | `918844b215dfa74ce97e014fa92c395276f381bbbe7950ce3d2a8dbbbd8a2bef` |
| 4.1 | APPROVED | Verbatim | `e1479c6236f16794468f1c2236ec73b3d6d567848dbc9bf44ae1bc9e3cf4744c` |
| 4.2 | APPROVED | Verbatim | `a9df51ee54dd7f3d3afd5264f8d9f6aea4df3f01bba0e44014bc81bfb5822c9c` |
| 4.3 | APPROVED | Verbatim | `ec056a59a73983b098f2c4dc21090a7b940b0c3dd457d107625e9ff4899eb150` |
| 4.4 | APPROVED | Verbatim | `29dd65846b1317199a2dc82d6fff214ecaca01ee26451888ceed4d34699708d3` |
| 4.5 | APPROVED | Verbatim | `cbe0f55070219d697d0bde8f7950d0b068866c7d9e271b5fc99b9ed0fcc31a25` |
| 4.6 | APPROVED | Verbatim | `31cf644aa4b1850def0e8336342a37af294e779b242d27393f0cf300e50ddfed` |
| 4.7 | APPROVED | Verbatim | `e1dc3ace46a1cf0bfa8b73f18219aeb4aea08ade262d6b37073038d59fdda75f` |
| 5 | APPROVED | Verbatim | `1c9f970c173e29a4bc2f503541e2c11a802e0185b55762ba65724f74dae42b7d` |
| 6 | APPROVED, with section 0.4 | Verbatim | `b5f51530595cd87b31b6a6ddd410c43b2db5b08460ced0371cdfd0ad6bbbde87` |
| 6.1 | APPROVED | Verbatim | `f93d7f4b2cae3b46f66d1fc3663d8ac8a1e7109a668f274cce6efe5d5af97627` |
| 6.2 | APPROVED | Verbatim | `e0f731c007a6de8883785411431e4c78c139eecc816e19a0f98cfa9be81aa738` |
| 6.3 | APPROVED | Verbatim | `d05ba4dd3f57d26a10feea30208da54e9a3af2d505b10557a3df29c4cdc45560` |
| 6.4 | APPROVED, with section 0.4 | Verbatim; two bullets quoted as pending | `01b9cb3626282fe5824cb190df1ce43e83dcd52a90b0b32ebda5d8551c718eaf` |
| 6.5 | APPROVED | Verbatim | `16ce90c805148b70910564c20075a1b813c1f37920c169dccda7efe023cefe9b` |
| 6.6 | APPROVED | Verbatim | `03defd4432eafc9263aff94008413ff96e1d95bdd3cce15ff434e3719247afc9` |
| 6.7 | APPROVED | Verbatim | `b48cf6ff936c8b52348d2e35e65a004e4bd6dccac72b108a1af613f8441bb2c3` |
| 7 | PENDING_HUMAN_DECISION | Verbatim | `bd53a829b2cfbb0c13972859f26e814fa50757e5ee4dbff4c257dfc2bec37bfc` |
| 7.1 | PENDING_HUMAN_DECISION | Verbatim | `0bc74eed1e907c269318720c7d58df8c04e1026e8b9cc29f8732f605b774ede2` |
| 7.2 | PENDING_HUMAN_DECISION | Verbatim | `4ab95377b47e1bdef62f58347e48ea53694b58b8a5e6cf720e1c712260f36c0c` |
| 7.3 | PENDING_HUMAN_DECISION | Verbatim | `f9cce2db1d05e542629fb15a2cab1931c6b274f3e923b1f37e4a7566bcac3f98` |
| 7.4 | PENDING_HUMAN_DECISION | Verbatim | `3b2627f4868651e78ff0cfca00a8e5e15291824e4c710f9c523c54ad6194e3fc` |
| 8 | MIXED | Verbatim | `97e60d437dbcc70af56d56a10518d81bd462a207fb4e5313a70d256ad0a6f1ec` |
| 8.1 | PENDING_HUMAN_DECISION | Verbatim | `254d4bc55ff18f009e604669d554905a5733c64cbbeb05b7d378d8685ffe5826` |
| 8.2 | APPROVED | Verbatim | `175f08bc45eadb84a704bea567729780c02844baf8c97cbfde794c0d8de56c17` |
| 9 | REFERENCE | Verbatim | `2ee7db8b2052f85bd177d71e15e1b3daee5c7bde68657542df09162dd04900a7` |
| 9.1 | REFERENCE | Verbatim | `488d3e06dd153f55d2d8db8b4c643df5b0b83c27bd875df35ae935e826e2461d` |
| 9.2 | REFERENCE | Verbatim | `aeb3b15785b4d48462283fa3d5f20bbe1ccd041e6dd89172d5b6a719f97a9c3b` |
| 9.3 | REFERENCE | Verbatim | `0c876d8941dbb98667b507f82dca7ad921e954b3ce6aa0fb7b22553228beeea2` |
| 10 | REFERENCE | Verbatim | `f439c3ac927134268a0dfb41d93001d1da20dcecae9d0c4aebd6135031b6437b` |
| 10.1 | REFERENCE | Rewritten; T-DOC-03 and its table verbatim | `93067489b0719e822cb528e14d0250e453bafbe6c6c5c538737393973ae12276` |
| 10.2 | REFERENCE | Verbatim | `2e60b9710a4fc5d9ee3bdf38ada52a134bfc875bf2a83f78f6b50735d31763d7` |
| 10.3 | REFERENCE | Verbatim | `e2c75f974ca4055c59e3535a0953b178282a536ebe7bbbf7129664f7f1cabf94` |
| 10.4 | REFERENCE | Verbatim | `b4376dfa8150567e943df038fe9d4b7b58bcdaf9b080652a863a1410b5736e94` |
| 10.5 | REFERENCE | Verbatim | `d5b2d5ffc2faf3c30962cf0678aca26a05b6bb508f8eb09bb16f76190126d6bf` |
| 10.6 | REFERENCE | Verbatim | `3f735eb9602b70f7693d72c6f6075f90280a8fbdfbb96b88736bdca8e4b1a5c2` |
| 10.7 | REFERENCE | Verbatim | `4dbf872ce623aee54e93eef1317fe284ae97da08f4f2b4a12d598fb4c6eed8e8` |
| 10.8 | — | Not reproduced | `db3bfcb73a8d1e8bcddf0175aff83b6332d91fbde6f875e3131a7b8dd90b0265` |
| 11 | — | Not reproduced | `f9194b370b445b087f9b98bb8bafa37af6b6e5fff71372219b4fb2310baf449d` |
| 12 | — | Not reproduced | `155a611357ef101e20ca364b3a8caa9821c4cbefd6380add23965d65ca6e898c` |

### 13.2 Checks

| Id | Check | Required result |
|---|---|---|
| V-01 | Files changed by this change | Exactly `docs/PRDV4_MULTI_MARKET_CRYPTO.md` and this file |
| V-02 | PRDV4 blob at the head | `6f5ad9177ee30e6e52a9c20c5c23cc3b00f578b7` |
| V-03 | PRDV4 against `main`'s blob `6511639a` | One removed line (the replaced D9 bullet) and the thirteen passages of section 13.1 |
| V-04 | Proposal tags and pending notice | None in PRDV4 |
| V-05 | Approved sections (3.3, 4.1–4.7, 5, 6.1–6.7, 8.2) | Byte-identical to the source, apart from the status block and the quote markers of section 6.4 |
| V-06 | Pending and reference sections | Byte-identical to the source under their status block; section 10.1 rewritten and keeping T-DOC-03 |
| V-07 | The numbers proposed for A_max, T_max and W_INC | Only in sections 3.6 and 12.1, each stated as a proposal |
| V-08 | HC-11c and HC-11f method text | Only inside the two quoted blocks of section 6.4 |
| V-09 | Code and document citations | Every cited file and line exists at the base and says what is cited |
| V-10 | Cross-references | Every reference to a section of this record resolves inside it |
| V-11 | Whitespace | `git diff --check` reports nothing |
| V-12 | Product surface | No file under `src/`, `tests/`, `scripts/` or `.github/` changes; rule sets v1–v7, seals, evidence digests and approval tables stay unchanged |
| V-13 | Exact-head CI | tests, codeql and CodeQL succeed on the head |
| V-14 | Independent audit | A protected T4 `CLASS_C_CROSS_CONTRACT` audit by GPT-6.1 Sol (Ultra) on the exact head; a self-audit never satisfies it |
| V-15 | Merge | Only after the human's exact-head standard-merge authorization (clause C) |
| V-16 | Post-merge | `main`'s PRDV4 is blob `6f5ad9177ee30e6e52a9c20c5c23cc3b00f578b7`, and this file's blob equals its blob at the authorized head |
