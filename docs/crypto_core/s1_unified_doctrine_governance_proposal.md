# S1 Unified Doctrine and Paper Governance Closure V1 — Unsigned Proposal

> **DOCTRINE_PROPOSAL_NOT_HUMAN_APPROVED · NO_PRODUCTION_AUTHORIZATION · NO_PAPER_ACTIVATION · MERGE_NOT_AUTHORIZED**
>
> Contract `S1_UNIFIED_DOCTRINE_AND_PAPER_GOVERNANCE_CLOSURE_V1`. Every decision below is `PENDING_HUMAN_DECISION`.
> Nothing here is approved, adopted or in force. It changes no accepted rule set, evidence or execution semantics, and
> it authorizes no implementation, paper activation, order, capital, scheduler, shadow or live step.

## 0. Status, authority and adoption

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
- **Adoption**, all steps in order:
  1. The human decides every item of section 11: approve, amend with exact text, or reject.
  2. One adoption edit on the same pull request, routed by the controller (it may travel with the candidate's one
     consolidated repair), deletes rejected passages, removes the tags of approved passages and
     the PRDV4 pending notice, performs each named replacement (D9 replaces one bullet of §1.7), records the signed
     decision in section 11, and changes nothing else.
  3. The protected T4 `CLASS_C_CROSS_CONTRACT` audit (GPT-6.1 Sol) of that exact head, with fresh exact-head CI.
  4. Explicit per-PR human merge authorization of that exact head.
  5. Standard merge, which is the only adoption act.

  Until step 5 every tagged passage is void and PRDV4 binds as written.
- **FCD register.** FCD-01..17 and their HC choices stay proposals on the prior record. This record amends FCD-07
  (section 4.7) and FCD-11 (section 6) only. The decision ids HID-1, HD-04, HD-07, HD-K1, HC-05d, HC-11a..f,
  HC-13a..c, HC-14a..b and HC-16a..d keep their identity.

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
| GRADUATED (final) | Every covered reading became defined before the end | None; ordinary basis only |
| EXPIRED_HOLD (final) | t ≥ X, or the A_max-th attempt was admitted, with a covered reading still undefined | None |
| REVOKED (final) | An approved human revocation record | None |
| TERMINATED (final) | Failed verification: digest, approval, validation currentness, lineage, a duplicate record or a duplicate observation | None |

Outside ACTIVE, a covered reading that is still undefined is BLOCKED and the entry decision is HOLD. A final state is
never left. No state change closes a position by itself; the protective rules keep running.

### 3.3 Covered classes U and exclusions

| Id | Reading | Window | Own history of | Feeds |
|---|---|---|---|---|
| U1 | Sharpe_30d (§1.6 Component 1) | 30 UTC days of returns | The edge | S_sharpe, EHS, NT-E01, NT-E02, NT-E04, α_edge, E_active, the BOOST condition |
| U2 | Sharpe_90d and DECAY_ALERT (§1.6) | 90 UTC days | The edge | §1.7 DE-WEIGHT and the BOOST condition |
| U3 | Fill rate of the last 10 orders (NT-X02) | 10 orders | The lineage, per exchange | NT-X02 |
| U4 | Fill rate of the last 20 orders (§1.5 Execution Conditions) | 20 orders | The lineage, per exchange | The §1.5 fill-rate leg, A_e, FB-ACTIVATION |
| U5 | Kelly estimate (§1.28) | First closed trade | The edge | p, b, f\*, G(f), the Kelly fit of SCALE-1 |

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
- **Graduation.** Per reading and irreversible: once a window holds enough own observations, the reading is ordinary
  for good and is never covered again.
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
| HD-K1 | None proposed | Section 8; without approval the no-win or no-loss Kelly class is not covered | PENDING_HUMAN_DECISION |

No new risk constant is proposed. One attempt risks at most the §1.27 INTRADAY single-position limit (8% of NAV)
times its 1.5% stop, about 0.12% of NAV plus fees, excluding gaps through the stop.

### 3.7 Reachability (not a safety property)

Incubation admits nothing until all of these hold: HD-07 decides calibration, which is never covered; X-H1 qualifies
exchange health; every non-covered check is PASS-capable (FCD-01..17 approvals and the X-* sources); the protective
engine of section 6 exists; DEC-1 authority covers the FB-MAX-HOLD horizon; and C1–C9 carry approved values. Two
viability limits remain: under strict Kelly an incubation yields at most one closed trade (F-3, section 8), and a
30-day window of zero returns leaves Sharpe_30d undefined (σ = 0, F-4) until HC-13a sets a convention.

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

### 6.2 Obligation record

| Field | Content |
|---|---|
| `obligation_id` | SHA-256 of the canonical (lineage, position id, trigger kind, trigger proof digest, opened instant) |
| `trigger_kind` | `KS3_CLOSE`, `SS3_CLOSE`, `KS4_FLATTEN` or `SS4_FLATTEN` |
| `trigger_proof` | Digest of the verifier's proof of the level at the opened instant |
| `integrity_class` | True exactly for `KS4_FLATTEN` and `SS4_FLATTEN` |
| `target` | Signed position q0 re-derived by the verifier from the sealed ledger; executor state is never read |
| `opened` | τ0, the injected PIT instant at which the trigger became known |
| `deadline` | KS-3: τ0 + 30 min. SS-3: MICRO τ0 and INTRADAY τ0 + 15 min; SWING follows the §1.29 rule (close unless DTL > 15% and EHS > 0.70, an unproven condition closing), its deadline is not set by doctrine and it is outside S1. KS-4 and SS-4: τ0 |
| `caps` | Participation method id and digest or `CAP_UNPROVEN`; impact measure id (HC-11f); liquidity-regime halving; the fill model's depth cap |
| `children` | Child id, decision instant, requested quantity, attributed fill ids, filled quantity, VWAP |
| `remaining` | abs(q0) minus the attributed fills; never negative |

### 6.3 Lifecycle

Events are append-only and digest-chained, each carrying the digest of the previous event:

`OPENED`, `CHILD_SENT`, `CHILD_FILLED`, `PAUSED` (impact), `CAP_UNPROVEN`, `AUTHORITY_UNPROVEN`, `BOOK_UNAVAILABLE`,
`POSITION_UNPROVEN`, `INTEGRITY_UNPROVEN`, `MERGED`, `DEADLINE_MISSED`, `DISCHARGED`.

- At the deadline with remaining > 0, the ledger appends `UNFULFILLED_PROTECTIVE_OBLIGATION_V1`: obligation id,
  deadline, remaining exposure, and a reason from `CAP_BINDING`, `CAP_UNPROVEN`, `IMPACT_PAUSE`, `BOOK_UNAVAILABLE`,
  `INTEGRITY_UNPROVEN`, `AUTHORITY_UNPROVEN` or `ENGINE_UNREPRESENTABLE`. The obligation stays open and closing
  continues under the same caps. The record never asserts that the position closed.
- `DISCHARGED` only when the verifier proves the position is zero from the sealed ledger.
- Fills are attributed only from the accepted paper fill model on an authenticated PIT book (C-MODEL evidence). No fill
  is manufactured, inferred or carried from an unauthenticated book.

### 6.4 Deadlines, caps and child derivation

- The earliest applicable deadline binds, and every applicable proven cap binds, so the strictest one binds.
- **Target path (HC-11c proposal).** Q\*(τ) = abs(q0) · min(1, (τ − τ0) / (τ_D − τ0)) when τ_D > τ0, and abs(q0) when
  τ_D = τ0. At each admissible authenticated book instant, child = min(Q\*(τ) − filled, R(τ), remaining, depth cap),
  where R(τ) is the shared participation allowance of section 7. No child is sent when the value is not positive.
  There is no fixed grid; a minimum spacing would be a performance choice.
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

### 6.6 Concurrency, replay and history

- Obligations on one position merge into one effective schedule: the earliest deadline, every cap, one child in
  flight. A proven integrity-class obligation supersedes the paced schedule. Each original record stays; the merge is
  an event.
- The participation allowance is shared per (venue, instrument) across every open obligation (section 7.3).
- Deterministic replay from sealed inputs and injected instants reproduces the ledger byte for byte. There is no
  autonomous loop: every instant is injected.
- History is permanent: no event is deleted or rewritten, and v1 histories verify under their original digests.

### 6.7 FCD-11 execution boundary

- **Engine today.** A single net position that may not cross zero; no partial close, no TWAP; KS and SS actions are
  `BLOCKED_UNREPRESENTABLE` (`governed_paper_system_state.py:48`). This ledger is a specification. Executing it needs
  a separately authorized engine contract (PR-B): close-only partial children, the obligation ledger and
  instant-driven scheduling.
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

Doctrine: f\* = (p·b − q)/b; p is the EWMA-weighted win rate over at most 100 trades (α = 0.05); b is average win over
average loss in the same window; f\* ≤ 0 gives no allocation; below 100 trades, quarter-Kelly; Σf ≤ 0.04; G(f) > 0;
Kelly is an upper bound and never overrides risk limits.

| Case | Reading | Status |
|---|---|---|
| K0: no closed trade | p, b and f\* undefined | Ordinary BLOCKED; under incubation U5 gives `COLD_START_EXCEPTED` |
| K1: closed trades, no win | Average win over an empty set: b undefined | BLOCKED, never FAIL. No completion can hold p fixed, because the win that would define b also changes p. Covered only if HD-K1 extends coverage |
| K2: closed trades, no loss | b undefined | BLOCKED; "wins only gives f\* = 1" is rejected |
| K3: at least one win and one loss | b defined; p needs the EWMA normalization (HC-16b) | BLOCKED until HC-16b is approved; then f\* ≤ 0 is FAIL, otherwise f = 0.25·f\* below 100 trades; G(f) needs at least 2 trades |

No finite b is ever assumed. Σf ≤ 0.04 on actual risk at stop is never excepted. F-3: under strict Kelly every first
closed trade leaves b undefined, so an incubation yields at most one closed trade and then holds, unless HD-K1 extends
coverage. Even then it stays bounded by A_max, T_max, KS trigger #5 (5 consecutive losses gives KS-1 and a SCALE-1
FAIL) and the §1.6 drawdown rule (DD ≥ the edge's maximum disables the edge), all proven failures that are never
covered.

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
`BOOK_UNAVAILABLE`, `POSITION_UNPROVEN`, `INTEGRITY_UNPROVEN`, `AUTHORITY_UNPROVEN`, `ENGINE_UNREPRESENTABLE`,
`KELLY_RATIO_UNDEFINED`, `KELLY_METHOD_UNAPPROVED`, `KELLY_NON_POSITIVE`.

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
| T-INC-21 | HD-K1 not approved; first closed trade has no win or no loss | BLOCKED |
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
| T-PROT-08 | KS-3 and SS-3 at once | Earliest deadline, every cap, one child in flight |
| T-PROT-09 | Proven KS-4 or SS-4 | Urgent walk without pacing, participation or pause, bounded by the authenticated book |
| T-PROT-10 | Failed independent integrity proof | `INTEGRITY_UNPROVEN`; no fill; obligation open |
| T-PROT-11 | Legacy history | v1 STOP and MAX_HOLD bytes and digests unchanged |
| T-PROT-12 | Cap unproven | No KS-3 child; v1 exits unaffected |
| T-PROT-13 | DEC-1 authority absent | No child; `AUTHORITY_UNPROVEN` |
| T-PROT-14 | Manual restart | Never discharges an open obligation |
| T-PROT-15 | Entry while an obligation is open | Refused |
| T-PROT-16 | Replay | Byte-identical ledger |
| T-PROT-17 | Executor self-report clearing KS-4 | Ignored |

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

## 11. Unsigned human decision record

```text
HUMAN DECISION RECORD — S1_UNIFIED_DOCTRINE_AND_PAPER_GOVERNANCE_CLOSURE_V1 (UNSIGNED)
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
  1.3 HD-K1 (cover the Kelly class with closed trades but no win or no loss?): NO ___ / YES ___
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
  4.2 PROTECTIVE_OBLIGATION_LEDGER_V2 with IR-1..IR-6 and v1 precedence (section 6) ___
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
  This record authorizes no implementation, commit beyond the adoption edit, merge, production-table entry, DEC-1
  authority, real, shadow or live paper, order, capital, scheduler or readiness change. It qualifies no external
  source and changes no accepted artifact.

Approved ___  Amended ___  Rejected ___  By ___  Date (UTC) ___
```

## 12. Pending dependencies and non-authorizations

- **Human decisions.** Every item of section 11; HD-07 (calibration); HD-K1; HD-04 and the ADV definition; HC-05d;
  HC-11a, HC-11b, HC-11c, HC-11e, HC-11f; HC-13a..c; HC-14a..b; HC-16a..d; every FCD-01..17 approval; C1–C9 values
  (C2's G and H included); DEC-1 authority and window; gated-strategy re-validation (FCD-12).
- **External sources, all UNKNOWN.** X-H1 exchange health; X-M1-A qualified sequenced market data and book cadence;
  X-M1-C CTR source; X-D1-A..E venue facts, X-D1-D being ADV; X-M1-B, X-M1-D and X-M1-E; X-CAL; X-BTC; the S1
  instrument identity.
- **Engine.** The protective execution mechanics of section 6.7 (PR-B); KS and SS actions remain
  `BLOCKED_UNREPRESENTABLE` until then.
- **Not authorized.** Doctrine adoption, merge, implementation, production approval-table entries, paper activation,
  real or shadow or live orders, capital, scheduler or auto-loop, readiness or connector transitions. Construction
  stays NOT_CLOSED, and none of the blockers above is an implicit PASS.
