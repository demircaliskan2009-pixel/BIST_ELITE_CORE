# S1 Unified Doctrine and Paper Governance Closure V1 — Unsigned Proposal

> **DOCTRINE_PROPOSAL_NOT_HUMAN_APPROVED · NO_PRODUCTION_AUTHORIZATION · NO_PAPER_ACTIVATION · MERGE_NOT_AUTHORIZED**
>
> Contract `S1_UNIFIED_DOCTRINE_AND_PAPER_GOVERNANCE_CLOSURE_V1`. This text is written in record state
> `UNSIGNED_PROPOSAL` and is never edited to record a decision: a decision exists only in a separate human decision
> artifact, which changes the computed record state (section 0.2), never this text (section 0.3). Every decision
> offered below is `PENDING_HUMAN_DECISION` in this text. This text is no approval, adoption or force in any record
> state: every tagged passage stays void unless a separate adoption change installs the signed text (section 0.3).
> It changes no accepted rule set, evidence or execution semantics, and it authorizes no implementation, paper
> activation, order, capital, scheduler, shadow or live step.

## 0. Status, authority and adoption

### 0.1 Base, role and standing rules

- **Base.** `main` `afd6a3fc846dbcae0f64734fcbda3eecb7355970`, tree `84ed70edf439a153fcfde214760ae0a868b938f5`;
  `docs/PRDV4_MULTI_MARKET_CRYPTO.md` blob `6511639a`.
- **Role.** Companion to the PRDV4 passages tagged **[UNAPPROVED PROPOSAL Dn]**. PRDV4 holds the normative text of
  every amendment. This document holds what PRDV4 does not: the record schemas, the exact methods and their proofs,
  the trust boundaries, the verification matrix and the unsigned decision record. It adds no doctrine of its own, in
  the same way the LIMITED_S1_PAPER_V1 record keeps its method readings in `edge_factory_design.md` section 1a.
- **Tiers.** I constitutional: HID-1 (D1–D6). II doctrine: D7–D11, D13–D15. III methodology and parameters:
  sections 3–8. IV implementation: not authorized by this record.
- **Standing rules** (`governance_decision_framework.md` section 8): a model proposes and only a human approves a
  number; every approved number lives in exactly one digest-bound policy artifact; changing a number is a new
  version; an unapproved value rejects and never defaults.
- **FCD register.** FCD-01..17 and their HC choices stay proposals on the prior record. This record amends FCD-07
  (section 4.7) and FCD-11 (section 6) only. The decision ids HID-1, HD-04, HD-07, HC-05d, HC-11a..f, HC-13a..c,
  HC-14a..b and HC-16a..d keep their identity. HD-K1, an extension of Kelly coverage past the first closed trade, is
  not offered in this record (section 8.2).

### 0.2 Decision-record lifecycle

Each item of section 11 is decided APPROVE, AMEND (exact text), REJECT or left PENDING. Only a human decision artifact
through `HUMAN_GOVERNANCE` decides an item. It names the approver, the decision instant, the exact version it judges
(pull request number, head commit, and the blob ids of this document and of PRDV4) and the decision of each item. An
agent assertion, model output, review approval, audit verdict, CI result, or text written into section 11 inside a
pull request is never a decision, and an artifact that names another version decides nothing for this one. A decided
item is final for this version; changing it needs a new proposal version. An item voided by section 11 (Part 1 after
a rejected 0.1) counts as rejected.

| State | Item decisions in force | Doctrine effect |
|---|---|---|
| `UNSIGNED_PROPOSAL` | None decided | None; every tagged passage is void |
| `REJECTED_NOT_ADOPTED` | At least one rejected, none approved or amended; final once every item is rejected | None; the rejections are decision history, never rules |
| `PARTIALLY_APPROVED_NOT_ADOPTED` | At least one approved or amended, at least one rejected or pending | None |
| `HUMAN_APPROVED_NOT_ADOPTED` | Every item approved or amended | None |
| `ADOPTED_EXACT_MERGE` | An approved state, then the separate adoption change of section 0.3 merged by standard merge at its exact authorized head, and post-merge verification that `main` holds exactly the signed text | Only the approved and amended items, from the verified merge on; pending items stay pending and rejected items stay history |

The state is computed from the decisions in force and their evidence, never asserted, and it lives outside this
text: the status statements of this document describe the text as written (`UNSIGNED_PROPOSAL`) and are never
edited to follow a decision. No state before `ADOPTED_EXACT_MERGE` has any doctrine effect, and no state authorizes
implementation (Tier IV).

### 0.3 Adoption lifecycle: a separate change, never an edit of this pull request

`docs/crypto_core/agent_workflow.md` section 24.8 binds every audit verdict and CI result to the exact head it judged.
After the implementation only the one consolidated repair may move the head; apart from an authorized empty
re-trigger commit with an identical tree, any other head movement voids the verdicts and freezes the candidate. An
adoption edit on this pull request after its re-audit would be such a movement, and the specialist budget has no
further repair or audit to spend on it. Adoption therefore runs as a separate lifecycle:

1. This pull request is audited only as an unsigned, non-adopted draft (`UNSIGNED_PROPOSAL`) and is never edited for
   adoption.
2. The human decides the exact clauses in a decision artifact (section 0.2) naming the exact re-audited head.
3. This pull request closes without merge, only under a separate explicit authorization.
4. A new adoption pull request may then start from freshly verified accepted `main`, under an explicit controller
   decision. It is a new contract (installing signed text), not a repair or replacement cycle of this one; it has its
   own lifecycle under `agent_workflow.md` section 24.8 and inherits no verdict from this pull request.
5. It contains exactly the signed selections and truthful adopted, pending and rejected status text (below).
6. It receives its own independent protected T4 `CLASS_C_CROSS_CONTRACT` audit (GPT-6.1 Sol) with fresh exact-head CI.
7. Its standard merge needs its own explicit exact-head human merge authorization.
8. Only post-merge verification that `main` holds byte for byte the signed text promotes the approved items to
   `ADOPTED_EXACT_MERGE`.

An adoption candidate:

- installs in PRDV4 only the approved and amended items, untagged and byte-equal to the signed text, with each named
  replacement (D9 replaces one bullet of §1.7); a rejected or pending item installs nothing;
- leaves no pending notice that contradicts the result: a notice remains only for passages still tagged, and names
  only them;
- states the actual state of every item (adopted by that merge, still `PENDING_HUMAN_DECISION`, or rejected as
  decision history, never an active rule), records the chosen values and the digest of the signed decision artifact,
  and replaces every blanket pending or nothing-approved statement;
- keeps every non-authorization that still applies: implementation (Tier IV), production approval-table and policy
  artifact entries (approving a number does not enter it), real, shadow or live paper, orders, capital, scheduler,
  readiness and connector transitions, and every pending external source (X-\*).

This pull request is not authority for adoption. Until step 8 every tagged passage here is void and PRDV4 binds as
written, and a tagged passage never becomes doctrine itself: only the adoption change's untagged signed text, after
its authorized and verified standard merge, does. This record authorizes none of steps 2–8.

## 1. Amendment index and deviations

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

### 2.1 Conflict with current authority

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

1. **Offline deterministic simulation**: EF-5..EF-8, FCD-12 replay, archive economics. Validation evidence only; it
   never fills an own-history window.
2. **Paper-incubation observation**: governed paper entries on the PAPER_INCUBATION basis under an ACTIVE record.
3. **Governed paper entry, ordinary basis**: every check PASS or proven not applicable.
4. **PRDV4 §1.13 Stage 4**: separate. Tiers 2 and 3 neither start, satisfy nor shorten it.
5. **Live execution**: forbidden and unreachable; INV-EDGE-004 requires all five §1.13 stages first.

§1.22 INCUBATION ("14-day shadow execution") is a post-§1.13 meta-layer stage. It is not tier 2, and nothing in this
record authorizes governed S1 admission through it.

## 3. PAPER_INCUBATION_RECORD_V1 (D8)

### 3.1 Fields

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

Incubation admits nothing until all of these hold: HD-07 decides calibration, which is never covered; X-H1 qualifies
exchange health; every non-covered check is PASS-capable (FCD-01..17 approvals and the X-* sources); the protective
engine of section 6 exists; DEC-1 authority covers the FB-MAX-HOLD horizon; and C1–C9 carry approved values. Two
viability limits remain: under strict Kelly no entry is admitted after the edge's first closed trade (F-3,
section 8.2), and a 30-day window of zero returns leaves Sharpe_30d undefined (σ = 0, F-4) until HC-13a sets a
convention.

## 4. ALLOCATION_ENVELOPE_V1 (D9; FCD-07)

### 4.1 Eligibility at each rebalance

Rebalances run at 00:00 UTC and on every edge state transition (§1.7).

- **MEMBER**: A_e = PASS and EHS ≥ 0.30, both defined and proven at the rebalance instant.
- **NON_MEMBER**: A_e proven FAIL, EHS defined and below 0.30 (DISABLE), or proven outside the top five.
- **UNKNOWN**: anything else. One UNKNOWN candidate leaves n and every weight unproven, so every weight is BLOCKED.
- **INCUBATION_MEMBER** (only if D1–D8 are adopted and a record is ACTIVE): exactly one candidate; the only non-PASS
  leg of A_e is U4 and the only undefined EHS input is U1, each `COLD_START_EXCEPTED` and neither FAIL.
- **Selection** (n > 5): top five by EHS × Sharpe_30d; ties broken by the higher EHS, then by the ascending edge id
  compared as UTF-8 bytes.

### 4.2 Share vector

- v_i = max(EHS_i × Sharpe_30d,i, 0), as §1.7 writes it; r_i = v_i / Σv, or 1/n when every numerator is 0.
- BOOST β_i = 1.2 when "Sharpe_30d > 1.5 AND EHS > 0.80 AND no DECAY_ALERT" is proven true and 1 when it is proven
  false. When it is unknown (DECAY_ALERT undefined), the weights are computed with and without the boost; if they are
  identical the result stands, otherwise every weight is BLOCKED.
- t = (r ⊙ β) / Σ(r ⊙ β), so BOOST keeps its doctrinal place before renormalization.

### 4.3 Bounded projection

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

| Symbol | Quantity | Source | Relation |
|---|---|---|---|
| E0 | Economics `initial_equity` | Accepted EF-6 economics (C1) | Equity origin: NAV(G) = E0 |
| R | C5 equity-basis reference notional | `governance_decision_framework.md` C5; `multi_sleeve_risk_governance_design.md` | R == E0 exactly, re-proven at genesis; a difference is a structural block |
| K | RG-2 `max_paper_risk_budget` | RG-2 | Bounds the RG-7 admission cap: u·L_k ≤ `admission_cap_fraction` × K; no doctrine relation to E0 |
| B(t) | Publication-visible NAV | The engine's equity on the same publication-visible snapshot as every other admission check | The envelope base; missing gives BLOCKED |

The envelope introduces no capital quantity and no capital commitment. "Committed paper capital" is not a repository
artifact and is not used.

### 4.6 ENVELOPE_FIT

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

### 6.1 Scope and precedence

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

- **Effective deadline.** The earliest applicable deadline binds: D_eff(t) = min D_k over the open nonurgent
  obligations of the schedule. Obligations stay open until `DISCHARGED`, so D_eff never increases. A joining trigger
  keeps or advances it; a later, less urgent trigger changes nothing. Every applicable proven cap binds, so the
  strictest one binds.
- **Target path (HC-11c proposal).** One cumulative position-level target on the schedule anchor, defined while the
  schedule holds a nonurgent obligation (otherwise only the integrity-class rule below applies), for t ≥ τ0:
  TARGET(t) = ANCHOR_Q0 · min(1, max(0, (t − τ0) / (D_eff(t) − τ0))) when D_eff(t) > τ0, and TARGET(t) = ANCHOR_Q0
  when D_eff(t) ≤ τ0. A joining trigger never restarts the clock and never raises the owed quantity: TARGET never
  exceeds ANCHOR_Q0 and never decreases, and a smaller D_eff only raises it.
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
- **Impact pause (HC-11f proposal).** For each child, m = abs(fill VWAP − mid) / mid, with the mid taken at the
  child's decision instant from the same authenticated book. If m > 1%, no child is sent for 5 minutes of injected
  time after that fill.
- **Retry.** When no admissible authenticated book exists, or exchange unavailability is proven, the next attempt is at
  the first admissible instant at least 30 seconds later (§1.19 item 4).
- **Largest first.** With several positions, the highest notional at τ0 closes first; ties go by ascending position id.

### 6.5 Integrity-class rules (KS-4 is "System integrity threat", SS-4 is "System integrity compromised")

| Id | Rule |
|---|---|
| IR-1 | Every KS-4 and SS-4 obligation is integrity-class |
| IR-2 | The trigger is proven only by the independent verifier, from raw sealed inputs against anchors outside the lineage, or through the operator raise channel (HC-05d). The executor's self-report never proves or clears it |
| IR-3 | The target is the position the verifier re-derives from the sealed digest-chained ledger. A ledger that fails verification gives `POSITION_UNPROVEN` and no fill |
| IR-4 | Fills only from a book authenticated independently of the threatened component. A threatened feed or an unknown threat scope gives `INTEGRITY_UNPROVEN`, no fill, and never a stale book |
| IR-5 | The urgent walk is exempt from pacing, participation and the impact pause (§1.29 HALT: "urgency overrides impact"), but bounded by the authenticated book and the fill model. The remainder stays an open obligation; disabling the engines and the manual restart never discharge it, and entries stay refused until it is discharged |
| IR-6 | No fabricated fill, no zero crossing, no inferred higher level |

### 6.6 Concurrency, equal instants, replay and history

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

### 7.1 Status

PRDV4 states several participation caps without one shared denominator. No formula is established doctrine. The
earlier daily-rate formula A(τ) = 0.02 · ADV · (τ − τ0) / 86,400 s is one candidate reading, not a verified rule.
Until a human approves a complete method and its sources are qualified, every participation cap that applies is
`CAP_UNPROVEN`: no KS-3 child is sent (D11), and v1 STOP and MAX_HOLD exits are unaffected. The open position then
stays bounded by its v1 stop and maximum hold, and entries stay refused (NT-R01).

### 7.2 Doctrine reconciliation

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

| Id | A(τ) | Assessment |
|---|---|---|
| P-A | 0.02 · ADV · (τ − τ0) / 86,400 s | Rate on ADV. Over 30 minutes it allows 1/2,400 of ADV. Needs ADV (X-D1-D) and its definition |
| P-B | 0.02 · V_market[τ0, τ) | Closest to the §1.14 "real-time volume" wording. Needs a qualified trade feed (X-M1-A) |
| P-C | 0.02 · ADV over the whole closure | Permits 24/25 (96%) of an average 30-minute volume, which is barely a cap; recommended for rejection |

No reading is adopted. The choice is HD-04, `PENDING_HUMAN_DECISION`.

## 8. Kelly undefined cases (§1.28)

### 8.1 Cases

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

### 9.1 Trust boundaries

| Boundary | Trusted side | Never trusted |
|---|---|---|
| Approval | A human approval of an exact digest through `HUMAN_GOVERNANCE`, entered in the production approval table | Model output, TEST_ONLY_SYNTHETIC approvals, caller text, unsigned records |
| Verification | The public verifier recomputing digests from sealed inputs | The executor's own state, self-reports and cached results |
| Market data | Authenticated, sequenced PIT ingress | L2-inferred or model-inferred counts, unauthenticated or stale books |
| History | The sealed digest-chained lineage | Offline simulation, replays counted as new observations, other lineages |
| External facts | Sources qualified by a human-approved record | Any provider claim without qualification (X-*) |

### 9.2 Refusal vocabulary (fixed codes, never caller text)

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

- Contracts: `PAPER_INCUBATION_RECORD_V1`, `ALLOCATION_ENVELOPE_V1`, `CTR_SOURCE_QUALIFICATION_V1`,
  `PROTECTIVE_OBLIGATION_LEDGER_V2`, `UNFULFILLED_PROTECTIVE_OBLIGATION_V1` and `PARTICIPATION_METHOD_V1` (pending).
  Each carries a schema id and a digest through the public serializer.
- A later implementation is opt-in and separately authorized: a new entry-safety rule set (v8) adding
  `COLD_START_EXCEPTED`, ENVELOPE_FIT and A9′, a new seal version, and a v2 protective ledger. Rule sets v1–v7, the
  v1 protective lifecycle and every historical evidence digest stay byte-identical.
- Every approved number lives in exactly one policy artifact. Changing it is a new version and a new digest; old
  evidence stays historical under its old digest.

## 10. Verification matrix (acceptance criteria for later implementation)

### 10.1 Doctrine consistency

T-DOC-01 and T-DOC-02 are checked in this pull request; T-DOC-03 is the clause review below.

- **T-DOC-01.** Deleting every tagged passage and the pending notice reproduces base PRDV4 byte for byte, so no
  untagged doctrine text changes.
- **T-DOC-02.** Every tag D1–D11, D13–D15 appears in PRDV4 and in section 1, and no other tag does.
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

| Id | Condition | Required result |
|---|---|---|
| T-PART-01 | No approved method | `CAP_UNPROVEN` |
| T-PART-02 | ADV unavailable or not point-in-time | `CAP_UNPROVEN` |
| T-PART-03 | Concurrent obligations | One shared allowance |
| T-PART-04 | Liquidity CRISIS, or an unknown liquidity regime | Halved rate |
| T-PART-05 | Order above 5% ADV, or not proven at most 5% ADV | Real-time volume cap applies, or `CAP_UNPROVEN` |
| T-PART-06 | Replay | Identical allowance |

### 10.7 Kelly

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

### 10.8 Decision-record lifecycle

| Id | Condition | Required result |
|---|---|---|
| T-STATE-01 | Every item proposed, none decided | `UNSIGNED_PROPOSAL`; every tagged passage void; PRDV4 binds as written |
| T-STATE-02 | Only 0.1 (HID-1) approved | `PARTIALLY_APPROVED_NOT_ADOPTED`; no doctrine effect; D1–D6 alone authorize nothing, and with D8 pending no incubation is possible |
| T-STATE-03 | Some items approved, some rejected, the rest pending | `PARTIALLY_APPROVED_NOT_ADOPTED`; rejections kept as decision history |
| T-STATE-04 | Every item approved or amended | `HUMAN_APPROVED_NOT_ADOPTED`; no doctrine effect and no merge authority |
| T-STATE-05 | Every item rejected, or 0.1 rejected with nothing else approved | `REJECTED_NOT_ADOPTED`; final once every item is decided; PRDV4 as written binds |
| T-STATE-06 | An approved adoption candidate open but unmerged | Still `…_NOT_ADOPTED`; the candidate's text has no force until its own audit, exact-head merge authorization, standard merge and verification |
| T-STATE-07 | The adoption change merged by standard merge and verified byte for byte against the signed text | `ADOPTED_EXACT_MERGE` for the approved and amended items only; pending items stay pending |
| T-STATE-08 | After `ADOPTED_EXACT_MERGE` | Implementation (Tier IV), policy-artifact entries, paper activation and capital stay unauthorized until separately authorized |
| T-STATE-09 | A rejected item | Never installed untagged in PRDV4; never stated as an active rule in any state |
| T-STATE-10 | Pending external facts (X-\*) | `UNKNOWN` in every state, `ADOPTED_EXACT_MERGE` included; no adoption qualifies a source |
| T-STATE-11 | An agent assertion, model output, review approval, audit verdict, CI result or text filled into section 11 offered as a decision | Refused; the state is unchanged |
| T-STATE-12 | A decision artifact naming another head or other blob ids | Decides nothing for this version |
| T-STATE-13 | Any head movement of this pull request after its re-audit other than an authorized tree-identical empty re-trigger commit, an adoption edit included | Forbidden by `agent_workflow.md` section 24.8; the bound verdicts are void and the candidate freezes; adoption runs only through section 0.3 |

## 11. Unsigned human decision record

```text
HUMAN DECISION RECORD — S1_UNIFIED_DOCTRINE_AND_PAPER_GOVERNANCE_CLOSURE_V1 (UNSIGNED)
Written in record state UNSIGNED_PROPOSAL; the current state is computed from decision artifacts (section 0.2).
A decision exists only in a separate HUMAN_GOVERNANCE artifact that names pull request 432, the exact re-audited
head commit and the blob ids of both files. Filling in this block inside a pull request decides nothing.
Each item: APPROVE / AMEND (exact text) / REJECT / PENDING.
Base: main afd6a3fc846dbcae0f64734fcbda3eecb7355970 · tree 84ed70edf439a153fcfde214760ae0a868b938f5 · PRDV4 6511639a
Tiers: I constitutional | II doctrine | III methodology and parameters | IV implementation (not authorized here)
A model may propose; only a human approves a number.

PART 0 (Tier I; decide first)
  0.1 HID-1 = D1-D6 verbatim: APPROVE / REJECT ___
      If rejected: Part 1 is void; S1 is recorded PROVEN_UNADMITTABLE_AT_COLD_START under PRDV4 as written;
      Parts 2-5 stand on their own.
PART 1 (void unless 0.1 is approved)
  1.1 D7 ___  D8 ___
  1.2 Covered list (strike any): U1 ___ U2 ___ U3 ___ U4 ___ U5 ___
  1.3 U5 boundary (section 8.2): Kelly covered at zero closed trades only; after the first closed trade an undefined
      b is BLOCKED and coverage never returns. No extension is offered here. Acknowledged ___
  1.4 A_max = ___ (proposal 20)
  1.5 T_max = ___ UTC days (proposal 90); refusal unless S + T_max <= G + H acknowledged ___
  1.6 W_INC = ___ (proposal 0.40)
  1.7 PAPER_INCUBATION_RECORD_V1 (section 3): APPROVE / AMEND (exact text) ___
  1.8 F-1 (calibration never covered), F-2 (X-H1), F-3 (Kelly), F-4 (sigma = 0) acknowledged ___
PART 2
  2.1 D9 ___
  2.2 ALLOCATION_ENVELOPE_V1 (section 4: eligibility, shares, projection, ENVELOPE_FIT, B = NAV) ___
  2.3 A9' amends CL2-11 (meta-layer term -> ENVELOPE_FIT; calibration added; every other term stays exactly 1) ___
PART 3
  3.1 D15 ___
  3.2 CTR_SOURCE_QUALIFICATION_V1 method (section 5) ___ (PASS stays BLOCKED until a source is separately qualified)
PART 4
  4.1 D10 ___  D11 ___  D13 ___  D14 ___
  4.2 PROTECTIVE_OBLIGATION_LEDGER_V2 with the position schedule anchor, IR-1..IR-6 and v1 precedence (section 6) ___
  4.3 HD-04 participation reading: P-A ___ / P-B ___ / other (exact text) ___ ; ADV definition and window = ___
  4.4 HC-11c target path (section 6.4) ___ ; minimum spacing = ___
  4.5 HC-11f impact measure (section 6.4) ___
  4.6 HC-05d (KS-4 trigger scope) stays on the FCD record ___
PART 5
  5.1 Kelly: b undefined -> BLOCKED (section 8) ___
  5.2 HC-16b = ___
PART 6
  FCD-01..17 and their HC choices stay on the prior record; this record amends only FCD-07 (2.3) and FCD-11 (Part 4) ___
PART 7 (non-authorizations)
  This record authorizes no implementation, adoption edit, adoption pull request, closing of this pull request,
  merge, production-table entry, DEC-1 authority, real, shadow or live paper, order, capital, scheduler or readiness
  change. It qualifies no external source and changes no accepted artifact. Adoption follows section 0.3 only.

Approved ___  Amended ___  Rejected ___  Pending ___  Resulting state (section 0.2) ___  By ___  Date (UTC) ___
```

## 12. Pending dependencies and non-authorizations

- **Human decisions.** Every item of section 11; HD-07 (calibration); HD-04 and the ADV definition; HC-05d; HC-11a,
  HC-11b, HC-11c, HC-11e, HC-11f; HC-13a..c; HC-14a..b; HC-16a..d; every FCD-01..17 approval; C1–C9 values (C2's G
  and H included); DEC-1 authority and window; gated-strategy re-validation (FCD-12).
- **Not offered.** HD-K1: Kelly coverage after the first closed trade would be a separate, unapproved
  constitutional and methodology change (section 8.2).
- **External sources, all UNKNOWN.** X-H1 exchange health; X-M1-A qualified sequenced market data and book cadence;
  X-M1-C CTR source; X-D1-A..E venue facts, X-D1-D being ADV; X-M1-B, X-M1-D and X-M1-E; X-CAL; X-BTC; the S1
  instrument identity.
- **Engine.** The protective execution mechanics of section 6.7 (PR-B); KS and SS actions remain
  `BLOCKED_UNREPRESENTABLE` until then.
- **Not authorized.** Doctrine adoption, an adoption edit or adoption pull request, closing this pull request, merge,
  implementation, production approval-table entries, paper activation, real or shadow or live orders, capital,
  scheduler or auto-loop, readiness or connector transitions. Construction stays NOT_CLOSED, and none of the
  blockers above is an implicit PASS.
