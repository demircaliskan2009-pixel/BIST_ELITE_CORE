# S1 Native Risk Measurement Doctrine Adoption V1

> Adoption record of the human-approved RECORD B (`S1_NATIVE_RISK_MEASUREMENT_METHOD_DECISION_V3`) for the governed
> paper path of `LIMITED_S1_PAPER_V1`, contract `S1_NATIVE_RISK_MEASUREMENT_DOCTRINE_ADOPTION_V1`. It installs the
> horizon CVaR doctrine reading HZB-1 (PRDV4 §1.27, and section 2 below), records B1–B5 with the human selections and
> the approved deltas D-B1, D-B2 and D-B3 as approved construction methodology and V1–V4 as approved values (sections
> 3–9), and admits nothing: every governed S1 entry stays refused (section 14).

## 0. Status, source and reading rules

### 0.1 Status and effect

- **Adoption merge.** This document and its PRDV4 change take effect together, and only when four things hold: this
  change has passed its own protected independent audit (GPT-6.1 Sol, `docs/crypto_core/agent_workflow.md` section
  24.4) with exact-head CI; the human has authorized its standard merge by naming the pull request, its exact head and
  the merge command (section 24.5); that merge is done; and post-merge verification proves that `main` holds the
  changed files byte for byte as at that head. Until then neither text has force, and PRDV4, the companion
  `docs/crypto_core/s1_approved_doctrine_adoption_v1.md` and the RECORD A amendment
  `docs/crypto_core/s1_kelly_class_completion_amendment_v1.md` bind as written.
- **Role.** PRDV4 holds the constitutional text of HZB-1. This document holds the decision record (section 1), the
  reading notes of HZB-1 (section 2), the approved construction methodology B1–B5 with its selections and deltas
  (sections 3–8), the approved values V1–V4 (section 9) and the adoption rules of this section. It adds no doctrine
  beyond the approved items. Between this document and PRDV4, PRDV4 governs, and between two safety rules the stricter
  one applies.
- **Tiers.** II doctrine reading: HZB-1, the constitutional interpretation of §1.27, installed in PRDV4 §1.27. III
  methodology: B1–B5 as written in RECORD B, with the selections MC-8a, MC-10 and LS-A and the approved deltas D-B1, D-B2
  (its exactness rule) and D-B3, approved for construction only; the values V1–V4. IV implementation: not authorized.
- **Forward-only.** PRDV4 gains one bullet and the phase map one appended section; no other document is edited. The
  companion and the RECORD A amendment are unchanged, and nothing earlier is erased or re-dated.
- **Standing rules** (`docs/crypto_core/governance_decision_framework.md` section 8): a model proposes and only a human
  approves a number; every approved number lives in exactly one digest-bound policy artifact; changing a number is a
  new version and a new digest; an unapproved value rejects and never defaults.

### 0.2 Status blocks

Every heading below carries one status block:

- **ADOPTED** — binding from the adoption merge, as written.
- **APPROVED_METHODOLOGY** — approved for construction only. It binds a later, separately authorized implementation
  contract and is not implemented; until then the accepted readings stay as they are (section 10).
- **APPROVED_VALUE** — a human-approved number for that later contract. It enters no policy artifact or approval table
  here, and it reaches production only through a separately approved risk-policy digest (BV, section 9).
- **NOT_SELECTED** — an alternative the human did not choose, or an option outside the approved scope. It is quoted as
  historical text only: it has no force, is no default or fallback, and no implementation reads it.
- **PENDING_HUMAN_DECISION** — non-normative. No value, method, state or permission may be read, defaulted,
  implemented or admitted from it.
- **REFERENCE** — supporting record, analysis, index or acceptance criteria. It adds no rule.

### 0.3 Reading rules

- The approved texts are reproduced inside `text` blocks word for word, with their source line breaks, two spaces less
  indentation and without the decision form's change markers (`[=]`, `[Δ]`, `[Δ X-2]`). The labels
  `[DOCTRINE READING, explicit]`, `[choice]` and `[confirm]` belong to the text and stay. The passages changed by the
  approved deltas are re-flowed; section 1.4 lists each change exactly.
- Alternatives the human did not select (HZB-2, LS-B), RECORD B's optional Tier II alternative to §1.18 and its analysis
  line under B2-H are quoted, unchanged, only in the subsections marked NOT_SELECTED or REFERENCE (sections 2.3, 4.3 and
  5.2). MC-8 and X-7 hold an unselected option inside their own lines; those lines stay whole, and sections 4.3 and 7.2
  state which part has no force.
- Line references inside the approved texts (for example `:1257`) point into PRDV4 blob `6f5ad917` (`main`
  `10d88841`), on which RECORD B was written. At the head of this change a cited line L sits at L for L ≤ 50; at L + 3
  for 52 ≤ L ≤ 1315 and for 1319 ≤ L ≤ 1322; at L + 13 for 1323 ≤ L ≤ 1669; and at L + 16 for L ≥ 1670.
  RECORD A inserted 3 and 10 lines, and this change inserts 3 lines after base line 1669. Code references (for
  example `engine :151-154`) point into `main` `10d88841`, whose `src/` is identical at the base of this change.
  Companion references (`companion §3.3 :308`) point into the unchanged companion.
- FCD-01, FCD-02, FCD-03, FCD-08 and FCD-10 name entries of the S1 final construction decision register (companion
  section 0.6). This document decides them only as section 1.2 states.
- Missing, unproven or unknown evidence stays BLOCKED or HOLD. No status block, quotation, matrix row or verification
  row of this document is a permission.

## 1. Decision record

> **Status: REFERENCE** — the decision this document adopts.

### 1.1 Record

```text
HUMAN_GOVERNANCE_DECISION_RECORD_V1
RECORD            S1_NATIVE_RISK_MEASUREMENT_METHOD_DECISION_V3 (RECORD B), with the approved deltas D-B1, D-B2 and D-B3
FORM              B1, B2, B2-H, B2-L, B3, B4, B5 and BV, quoted in section 1.2.
DECISION          B1-B5 approved; MC-8a chosen; MC-10 confirmed; HZB-1 approved; LS-A approved; V1-V4 approved.
                  The deltas D-B1, D-B2 and D-B3 are approved, and each names one exact wording (section 1.3). The
                  conditional depth-definition clause of D-B2 offers no text and stays PENDING_HUMAN_DECISION.
DECIDED BY        The human, as relayed by the ChatGPT controller. Approver identity: not recorded here (UNKNOWN).
CHANNEL           Controller packet of 2026-11-15 for contract S1_PRE_PAPER_ARCHITECTURE_RED_TEAM_AND_CLOSURE_V1, which
                  states (line breaks joined):
                    "Human-approved decisions: RECORD_A=S1_KELLY_CLASS_COMPLETION_DECISION_V3
                     RECORD_B=S1_NATIVE_RISK_MEASUREMENT_METHOD_DECISION_V3"
                    "Approved B selections: B1-B5 MC-8a MC-10 HZB-1 LS-A V1-V4"
                    "These decisions are not yet merged doctrine or implemented product code."
                  Controller packet of 2026-11-15 for contract S1_GOVERNED_PAPER_VIABILITY_AND_INCUBATION_ARCHITECTURE_V1,
                  which states (line breaks joined):
                    "The previous Fable advisory already found RT-1, RT-2, RT-3 and RT-4. The human approved their exact
                     conservative corrections."
                    "HUMAN_APPROVED_NOT_YET_ADOPTED: RECORD_A=S1_KELLY_CLASS_COMPLETION_DECISION_V3
                     RECORD_B=S1_NATIVE_RISK_MEASUREMENT_METHOD_DECISION_V3"
                    "APPROVED_ADDITIONAL_DELTAS: D-B1 D-B2 D-B3 D-A1"
                    "RECORD_B_SELECTIONS: MC-8a MC-10 HZB-1 LS-A V1-V4"
                    "THESE ARE HUMAN DECISIONS, NOT MERGED AUTHORITY."
                  Controller packet of 2026-11-17 for contract S1_NATIVE_RISK_MEASUREMENT_DOCTRINE_ADOPTION_V1, which
                  relays the same selections and requires the exact wording of D-B1, D-B2 and D-B3 to be recovered.
DECISION INSTANT  Not recorded (UNKNOWN). The first relays are of 2026-11-15.
SIGNATURE         None. Accepted main defines no signature mechanism for a doctrine decision (UNKNOWN). This record
                  transcribes a relayed decision truthfully; it is not a signed artifact and claims no signature.
SOURCE TEXT       The RECORD B decision form that the relays above approve by its identifier: the text delivered to the
                  controller on 2026-11-15 in the handoff of contract S1_GOVERNANCE_FINAL_SAFETY_CORRECTION_V1, section
                  EXACT_RECORD_B_HUMAN_DECISION_TEXT (extract digest in section 15.1). The deltas:
                  FABLE52_EXTERNAL_ADVISORY_REPORT_V1 of 2026-11-15, its items D-B1, D-B2 and D-B3 and its findings
                  RT-1, RT-2 and RT-3. Neither is a repository artifact; their approved texts are reproduced in sections
                  1.2, 1.3 and 2-9.
BINDING ACT       The human's separate exact-head standard-merge authorization of this change.
OUTSIDE           RECORD A and its delta D-A1 (docs/crypto_core/s1_kelly_class_completion_amendment_v1.md); the
                  advisory's items D-B4 and D-B5; everything listed in section 13.
```

### 1.2 Decision per item

The decision form, word for word:

```text
FORM
B1   "I APPROVE / REJECT NT_R03_OPEN_RISK_AT_STOP_V1 (R-1..R-8) as FCD-01, for construction only."
B2   "I APPROVE / REJECT CVAR99_WEIGHTED_HS_DAILY_V2 (C-1..C-21) with CVAR99_MC_V1 (MC-1..MC-12) as FCD-02, for construction only, choosing MC-8a (max) /
     MC-8b (literal), and confirming / rejecting MC-10."
B2-H [DOCTRINE READING; adoption required] "I APPROVE HZB-1 / APPROVE HZB-2 / DEFER (HZ-CVAR, EDGE-CVAR and MARGINAL-CVAR stay BLOCKED)."
B2-L "I APPROVE LS-A / CHOOSE LS-B (needs Deep Research for ADV) / DEFER (STRESS-LIQ stays BLOCKED)."
B3   "I APPROVE / REJECT LIQ_COMPOSITE_OBS_V3 (L-1..L-10) as FCD-03, including the observational definition of 'sustained' and the fixed 30-day baseline
     universe, for construction only."
B4   "I APPROVE / REJECT NT_X03_AND_OB_SPREAD_V3 (X-1..X-7) as FCD-10, implementing §1.21 and §7.2 as written, with no amendment."
B5   "I APPROVE / REJECT HZ_TURNOVER_INTRADAY_V1 (T-1..T-6) as FCD-08, for construction only."
BV   "V1 (172,800 s), V2 (600 s), V3 (300 s), V4 (300 s): APPROVE / REJECT / DEFER each. An approved value enters production only through a separately
     approved policy digest."
No B choice is a default: HZB-1/2, LS-A/B and MC-8a/b are explicit human choices; DEFER keeps the dependent checks BLOCKED.
```

| Item | Decision | Adopted as |
|---|---|---|
| B1 | APPROVE | APPROVED_METHODOLOGY, section 3 |
| B2 | APPROVE; MC-8a chosen; MC-10 confirmed | APPROVED_METHODOLOGY, section 4; MC-8b NOT_SELECTED |
| B2-H | APPROVE HZB-1 | ADOPTED doctrine reading, PRDV4 §1.27 and section 2; HZB-2 NOT_SELECTED |
| B2-L | APPROVE LS-A | APPROVED_METHODOLOGY, section 5; LS-B NOT_SELECTED |
| B3 | APPROVE | APPROVED_METHODOLOGY with D-B1 and D-B2, section 6 |
| B4 | APPROVE | APPROVED_METHODOLOGY with D-B1, section 7; the Tier II alignment NOT_SELECTED |
| B5 | APPROVE | APPROVED_METHODOLOGY, section 8 |
| BV | APPROVE V1, V2, V3 and V4 | APPROVED_VALUE, section 9 |

Every choice above is the human's recorded selection. None is read as a default, and no unselected option is a
fallback.

### 1.3 Approved deltas D-B1, D-B2 and D-B3

The decision items, quoted from the advisory's list `PENDING_HUMAN_DECISIONS (exact)`:

```text
D-B1 Confirm the RT-1 wording for L-2 and X-2.
D-B2 Confirm the RT-2 exactness rule; decide the depth definition if depth-50 does not cover the band for the instrument.
D-B3 Confirm the RT-3 seed composition.
```

The wordings they name, quoted from item 5 ("Smallest correction") of findings RT-1, RT-2 and RT-3 of the same report:

```text
RT-1 [P2] Liquidity and spread observations are not read as-of their instant
  5 Smallest correction:
    - L-2: "the latest tip by native event time among tips whose visibility is <= s_i and whose event time is >= s_i - 10 s; a tip visible after s_i
      never enters the observation at s_i; kappa_i is the visibility of the bounding trade."
    - X-2: "a valid tip as of g_k (visibility <= g_k)."

RT-2 [P2] The depth metric ignores the depth-50 horizon
  5 Smallest correction: "a side's band value is exact only when its 50th level lies strictly beyond the band edge; depth_raw is defined only when the
    minimum is attained on an exact side (both exact, or one exact and the other's lower bound >= it); otherwise the observation is UNKNOWN."
    A separate human decision is needed on an observable depth definition if depth-50 does not cover 5 bps for the instrument.

RT-3 [P2] The Monte Carlo seed is not stable under archive growth
  5 Smallest correction: seed over {contract id, risk-policy digest, source declaration digest, interval, series end day, the 253 daily-close bar
    digests}; no whole-archive digest.
```

- **D-B1** names one wording: an L-2 text and an X-2 text. Approved; applied in sections 6.1 and 7.1.
- **D-B2** names one exactness rule. Approved; applied in section 6.1. Its second clause, "decide the depth definition
  if depth-50 does not cover the band for the instrument", offers no text and depends on external facts that are
  UNKNOWN (the S1 instrument and whether its depth-50 covers ±5 bps). It is PENDING_HUMAN_DECISION. Until a human
  decides it, the exactness rule alone governs, and an observation whose minimum is not attained on an exact side is
  UNKNOWN. No depth definition is selected or defaulted here.
- **D-B3** names one seed composition. Approved; applied to MC-3 in section 4.2.
- **No alternative was offered.** D-A1 asks the human to choose between two alternatives, so its relayed label selects
  nothing (RECORD A amendment section 5.2). D-B1, D-B2 and D-B3 each confirm a single wording, so each approved label
  selects exactly the wording quoted above. The controller's statement that the human "approved their exact conservative
  corrections" agrees with this; it is not used to choose anything.

### 1.4 Changes to the approved wording

| Passage | RECORD B wording | Adopted wording | Basis |
|---|---|---|---|
| L-2, first bullet | `the latest depth-50 tip with event time in [s_i - 10 s, s_i] (CL1-10)` | `the latest depth-50 tip by native event time among tips whose visibility is <= s_i and whose event time is >= s_i - 10 s (CL1-10)` | D-B1 |
| L-2, new second bullet | none | `a tip visible after s_i never enters the observation at s_i;` | D-B1 |
| L-2, new fourth bullet | none | The D-B2 exactness rule, word for word | D-B2 |
| L-2, last bullet | `kappa_i = the later of the tip's and that bounding trade's visibilities.` | `kappa_i is the visibility of the bounding trade.` | D-B1 |
| X-2, second sentence | `Each needs a valid tip (L-2's depth-50 tip with event time in [g_k - 10 s, g_k], ask > bid, from the re-proven authenticated dataset) visible at t.` | `Each needs a valid tip as of g_k (visibility <= g_k) (L-2's depth-50 tip with event time in [g_k - 10 s, g_k], ask > bid, from the re-proven authenticated dataset).` | D-B1 |
| MC-3 | `archive digest` and `in order}; independent of` | `source declaration digest` and `in order}; no whole-archive digest; independent of` | D-B3 |

D-B1's L-2 text says "the latest tip"; the adopted bullet keeps RECORD B's "depth-50", which D-B1 does not address. In
MC-3, D-B3's "contract id" is RECORD B's literal `"CVAR99_MC_V1"`, and RECORD B's "in order" stays. No other word of an
approved text changes.

### 1.5 Effect on earlier records

None of the records below is edited; each keeps its text as the history of the state it recorded.

- **Companion.** Companion sections 0.6 and 12.1 list FCD-01..FCD-17 as pending, apart from FCD-07 and FCD-11. As
  companion section 12.3 provides for deciding a pending item, this separate adoption change decides FCD-01, FCD-02,
  FCD-03, FCD-08 and FCD-10, for construction only and only as section 1.2 states. Every other FCD decision stays
  pending.
- **RECORD A amendment.** Its passages on RECORD B (sections 1.1, 4.2, 5.3, 7 and 8) record the state at its own
  adoption, when RECORD B was neither adopted nor implemented. From this change's adoption merge RECORD B is adopted as
  methodology and is still not implemented, so their operative consequence holds: no FCD-01 risk evidence exists and
  every Kelly reading stays BLOCKED (section 11).
- **Phase map.** Its section 13 lists RECORD B with HZB-1 as pending; the appended section 14 records this adoption.

## 2. HZB-1 — horizon CVaR doctrine reading (B2-H)

> **Status: ADOPTED** — doctrine reading, binding from the adoption merge. Its constitutional text is the bullet of
> PRDV4 §1.27 "Horizon Isolation Rules" that follows "Risk limits from §1.18 (CVaR) and §1.19 (kill-switch) applied
> PER-HORIZON before portfolio-level".

### 2.1 Text

```text
B2-H Horizon CVaR doctrine readings (PRDV4 §1.27 Horizon Isolation Rules, after "applied PER-HORIZON before portfolio-level"):
  HZB-1: "The §1.18 CVaR99 limit of a horizon is its Risk Budget share of the total portfolio CVaR99 budget (MICRO 20%, INTRADAY 40%, SWING 40% of 5% of NAV
    per day), evaluated on that horizon's positions; §1.18 per-edge budgets and the marginal rule allocate that horizon limit among its edges."
```

### 2.2 Reading notes

> **Status: REFERENCE** — section 2.1 and PRDV4 govern.

- **Location.** PRDV4 holds the quoted sentence, without its quotation marks, as a bullet nested under the PER-HORIZON
  rule of §1.27. No other PRDV4 text changes.
- **INTRADAY.** The INTRADAY horizon limit is 40% of the §1.18 total budget of 5% of NAV per day, that is 2% of NAV per
  day. This is arithmetic on existing doctrine (§1.27's Risk Budget column and §1.18's total budget), not a new
  parameter: it creates no policy value, and the HZ-CVAR reading (C-12) still needs an approved risk-policy digest
  before production (C-21). S1 is an INTRADAY edge (CL2-9: the §1.27 INTRADAY limits apply to S1; phase map section
  12).
- **Per-edge budgets.** Under HZB-1 the §1.18 per-edge formula and the marginal rule allocate the horizon limit. Both
  need K_max (FCD-17, external ADV) and H^(e), which PRDV4 does not define, so EDGE-CVAR (C-13) and MARGINAL-CVAR (C-14)
  stay BLOCKED. No edge or marginal budget is derived here.
- **Stress limits.** HZB-1 defines a horizon's §1.18 CVaR99 limit only. Whether the horizon share also applies to the
  §1.18 stress limits of 8% of NAV is the advisory's item D-B5, which is not approved (section 13). C-15 and LS-A read as
  approved, and no shared stress limit is adopted or defaulted.
- **Fill instant.** RECORD B binds NT-R05 at the fill (C-10) and is silent about HZ-CVAR and STRESS-LIQ at the fill. That
  question is the advisory's item D-B4, which is not approved (section 13); this document adds no fill-time rule.

### 2.3 Not selected, and the record's analysis

> **Status: NOT_SELECTED** (HZB-2) and **REFERENCE** (the analysis line) — no force.

```text
  HZB-2: "The §1.18 limits apply at their full values to each horizon's positions before the portfolio limit; the Risk Budget share is not a CVaR limit, and
    §1.18 per-edge budgets allocate the portfolio budget."
```

```text
  S1 consequences: HZ-CVAR < 2% (HZB-1) or < 5% (HZB-2); EDGE-CVAR <= 2% or 5%; MARGINAL-CVAR from flat <= 1% or 2.5%. The edge budget also needs
  K_max(e) > 0 (FCD-17, external ADV) and H^(e), which PRDV4 defines nowhere (only :1073). Recommendation: HZB-1.
```

The analysis line compared the two readings before the decision and is not a rule. Its HZB-1 horizon figure is the
arithmetic of section 2.2, its HZB-2 figures have no force, and its edge and marginal figures are not budgets: C-13 and
C-14 stay BLOCKED.

## 3. FCD-01 — NT_R03_OPEN_RISK_AT_STOP_V1 (B1)

> **Status: APPROVED_METHODOLOGY** — for construction only. Not implemented: rule set v9's NT-R03 keeps blocking every
> prospective entry (section 10).

### 3.1 Text

```text
B1 NT_R03_OPEN_RISK_AT_STOP_V1 (authority PRDV4 :1257, :2162, :1688, :2170-2172; CL2-10, engine :151-154; :1736; companion §3.3)
R-1 Armed stop s: basis = opening fill price; distance = min(1.5*ATR_4h, 0.015*basis); LONG s = basis - distance, SHORT s = basis + distance.
    At fresh mark m: x = s if sgn(q)*(m - s) > 0, else x = m.
    risk = |q|*sgn(q)*(m - x) + |q|*x*c, with c = (taker_fee_bps + slippage_floor_bps)/10,000 of the bound economics policy.
    Flat -> 0. Gap risk is excluded (non-claim).
R-2 E = the exact publication-visible NAV; E <= 0 -> BLOCKED.
R-3 rho = sum risk / E.
R-4 Decision (entry from flat): basis m(t); distance = min(1.5*ATR_4h(t), 0.015*m(t)); denominator = candidate NAV (mark net of the candidate's own fee).
R-5 Fill: exact rho on the post-fill position, the armed stop, the fill mark and the exact post-fill equity; rho > 0.04 -> REJECTED whole (schedule v7).
R-6 Current position: reported; never refuses a non-entry.
R-7 FAIL iff rho > 0.04 (0.04 PASSes); PASS iff rho <= 0.04 with every input proven. BLOCKED on: order in flight, no fresh mark, no armed stop, ATR missing,
    NAV missing or <= 0, unrepresentable.
R-8 [DOCTRINE READING, explicit] rho is a fraction of equity at stop risk (companion §3.3 :308; §1.28 :1736), never a notional allocation; KD-0/KD-9/KD-10
    consume it.
```

### 3.2 Reading notes

> **Status: REFERENCE.**

- **R-8 and KD-0.** R-8 agrees with RECORD A's adopted KD-0, which makes f\* and f fractions of equity at stop risk and
  rho the candidate's FCD-01 risk fraction (amendment section 4.1). R-8 is part of B1's construction-only approval and
  adds no rule to KD-0.
- **Gaps.** R-1 excludes gap risk as a non-claim, so a realized loss can exceed the FCD-01 risk. RECORD A's solvency
  domain (KD-10b) already handles R_j below -1 on the Kelly side.
- **No resize.** R-5 refuses the whole exposure-increasing fill and never resizes the fixed unit.

## 4. FCD-02 — CVAR99_WEIGHTED_HS_DAILY_V2 with CVAR99_MC_V1 (B2)

> **Status: APPROVED_METHODOLOGY** — for construction only, with MC-8a chosen and MC-10 confirmed. Not implemented:
> rule set v9's NT-R05 stays BLOCKED and S3 stays unmeasured (section 10).

### 4.1 Text

```text
B2 CVAR99_WEIGHTED_HS_DAILY_V2 (authority PRDV4 §1.18 :1047-1101, NT-R05 :1259, §8.2 :2161, §1.29 :1787, §1.27 :1663-1671)
C-1  Series: a policy-bound mark_price OHLC archive with an interval dividing 86,400 s; daily close = close of the bar ending at UTC midnight. At t, the 253
     consecutive closes ending with the latest visible one, which must have closed at or after t - V1; else BLOCKED (CVAR_HISTORY_INSUFFICIENT / STALE).
C-2  r_a = c_d/c_{d-1} - 1, 252 UTC days, a = 0 newest.
C-3  L_a = -q*m*r_a/E (hypothetical holdings at the fresh mark; price-only).
C-4  w_a = lambda^a*(1 - lambda)/(1 - lambda^252), lambda = 47/50.
C-5  ES = (1/tau)*sum L_(k)*min(w_(k), max(0, tau - W_{k-1})), with descending loss, ties by ascending age, tau = 1/100. VaR = L_(k*); n_tail = k*.
C-6  Fallback iff n_tail < 50 (<=> W_49 >= 0.01; range 1..178).
C-7  CVAR99_MC_V1 per MC-8.
C-8  CVaR99* = ES if n_tail >= 50, else per MC-8.
C-9  NT-R05 (decision; current + candidate over candidate NAV): FAIL iff >= 0.05; PASS iff < 0.05 with every input proven; else BLOCKED.
C-10 Fill: post-fill CVaR99* >= 0.05 -> REJECTED whole (schedule v7).
C-11 S3 = min(1, max(0, CVaR99*/0.05)) on current holdings at decisions, weight 0.15; s3 = 1 -> at least CRISIS.
C-12 HZ-CVAR < B_H (per B2-H), BLOCKED until adopted.
C-13 EDGE-CVAR (FAIL above the budget), BLOCKED until FCD-17, H^(e) and B2-H exist.
C-14 MARGINAL-CVAR (FAIL iff deltaCVaR > 0.5*budget; same series and draws), BLOCKED until the budget is defined.
C-15 STRESS-HV = 1.5*CVaR99*, FAIL at >= 0.08.
C-16 STRESS-CORR PROVEN_NOT_APPLICABLE on one instrument.
C-17 STRESS-LIQ BLOCKED until B2-L.
C-18 De-risk duties (:1075, :1095) are BLOCKED_UNREPRESENTABLE obligations.
C-19 Exact at every decision and fill; hourly monitoring between decisions is unmeasured (MONITORING_CADENCE pending).
C-20 NAV <= 0 -> BLOCKED; S3 unmeasured.
C-21 Production needs an approved risk-policy digest and an M1-qualified archive; tests TEST_ONLY only.
```

### 4.2 CVAR99_MC_V1

```text
CVAR99_MC_V1
MC-1  One-day losses drawn i.i.d. from the lambda-weighted empirical distribution of the 252 scenario losses (weighted bootstrap); never beyond the worst
      historical scenario.
MC-2  Exactly 10,000 paths, one draw each.
MC-3  Seed = SHA-256 of the canonical JSON of {"CVAR99_MC_V1", risk-policy digest, source declaration digest, interval, series end day, the 253 daily-close
      bar digests in order}; no whole-archive digest; independent of holdings, decision and side.
MC-4  d_i = SHA-256(seed || i as 8-byte big-endian); U_i = int(d_i[0:8])/2^64, i = 0..9,999.
MC-5  Draw the smallest a with U_i < C_a (ascending ages; C_251 = 1), i.e. u_i < ceil(C_a*2^64).
MC-6  Sort path losses descending, ties by path index. VaR_MC = the 100th; CVaR_MC = mean of the top 100 (exact); per (series day, side) scaling by |q|*m/E.
MC-7  Used only when n_tail < 50.
MC-8  [choice] MC-8a = max(ES, CVaR_MC) (recommended); MC-8b = CVaR_MC.
MC-9  Inputs per C-1; any failure -> BLOCKED; replay byte-identical.
MC-10 [confirm] A counter-based sequence derived from verified inputs satisfies INV-001 (:40).
MC-11 Regression:
      - r_a = ((37a mod 41) - 20)/1000 except r_5 = -0.12, r_30 = +0.10, r_100 = -0.15, r_200 = -0.20; LONG; |q|m/E = 1;
      - seed = SHA-256("CVAR99_MC_REGRESSION_V1") = fc670340bfcb039f6e651ee4f7d363fe4e3f7ff9859efea7aae2f57cee628857;
      - u_0 = 8420428673457154365, u_1 = 12947070990645480281, u_2 = 6972368347563711628 (each / 2^64);
      - picks 9, 19, 7, 18, 13; n_tail = 3; exact ES ≈ 0.12037190432654903 (pin the exact rational); CVaR_MC = 3/25;
      - MC-8a = 0.120372, MC-8b = 0.12.
MC-12 0.153 s per series day measured; cached per day and side; re-measure in the implementation (STOP_WITH_PROOF if infeasible).
```

### 4.3 Selections and texts not adopted

> **Status: REFERENCE** (the selections) and **NOT_SELECTED** (MC-8b and the Tier II alternative).

- **MC-8.** The human chose MC-8a: whenever C-6's fallback applies, CVaR99\* = max(ES, CVaR_MC). MC-8b, the literal
  CVaR_MC, is NOT_SELECTED.
- **MC-10.** Confirmed: the counter-based sequence derived from verified inputs satisfies INV-001.
- **C-12 and C-17.** B2-H is decided by HZB-1 (section 2) and B2-L by LS-A (section 5).
- **Tier II alternative.** NOT_SELECTED. It would amend PRDV4 §1.18 and needs its own adoption; it is not adopted, and
  §1.18's Monte Carlo fallback stands as written:

```text
Optional Tier II alternative (own adoption; not recommended): in §1.18 replace the 10,000-path fallback with "When fewer than 50 observations carry the 1%
tail, the estimate is the exact lambda-weighted tail expectation; no Monte Carlo is run."
```

## 5. STRESS-LIQ method LS-A (B2-L)

> **Status: APPROVED_METHODOLOGY** — for construction only; it is the STRESS-LIQ method of C-17. Not implemented: no
> STRESS-LIQ check exists in rule set v9 (section 10).

### 5.1 Text

```text
B2-L STRESS-LIQ methods
  LS-A (internal):
  - stressed book = the latest fresh depth-50 tip with every quantity x 1/5 (truncated on the quantity grid, as the engine's LOW_LIQUIDITY transform);
  - exit cost = the whole holding as one close-only order under the bound fill model (fill-ratio cap, slippage max(floor, half_spread +
    coefficient x participation), taker fee);
  - stress CVaR_liq = CVaR99* + exit cost / E;
  - FAIL iff >= 0.08 or if the stressed book cannot fill |q| in that order; PASS iff < 0.08 with every input proven.
```

### 5.2 Not selected

> **Status: NOT_SELECTED** — no force; no ADV source is qualified or requested.

```text
  LS-B: the §1.14 Almgren–Chriss model; needs ADV (X-D1-D, Deep Research) and per-asset calibration.
```

## 6. FCD-03 — LIQ_COMPOSITE_OBS_V3 (B3)

> **Status: APPROVED_METHODOLOGY** — for construction only, with D-B1 and D-B2 applied to L-2. Not implemented: rule set
> v9's NT-M01 stays BLOCKED, KS T8 and S6 stay unmeasured (section 10).

### 6.1 Text

```text
B3 LIQ_COMPOSITE_OBS_V3 (authority PRDV4 §1.17 :1010-1027, NT-M01 :1266, §1.19 T8 :1130, §1.29 S6 :1790; CL1-10 regime_state:190; NT-D05
entry_safety:139-143)
L-1  Observation instants s_i = UTC-aligned multiples of V3 = 300 s.
L-2  An observation at s_i is valid only when all of the following hold, read from records of the authenticated governed dataset that the consumer
     re-proves (intact, READY, advancing) under the registry semantics of its ORDER_BOOK and LAST_TRADE series:
     - depth_raw and spread_raw come from the latest depth-50 tip by native event time among tips whose visibility is <= s_i and whose event time is
       >= s_i - 10 s (CL1-10), with ask > bid and mid = (bid + ask)/2;
     - a tip visible after s_i never enters the observation at s_i;
     - depth_raw = min(sum_{bid >= mid*(1 - 0.0005)} price*qty, sum_{ask <= mid*(1 + 0.0005)} price*qty); spread_raw = (ask - bid)/mid;
     - a side's band value is exact only when its 50th level lies strictly beyond the band edge; depth_raw is defined only when the minimum is attained on
       an exact side (both exact, or one exact and the other's lower bound >= it); otherwise the observation is UNKNOWN.
     - arrival_raw = distinct native trade ids with event time in [s_i - 300 s, s_i), proven complete by one contiguous declared run from a visible trade
       strictly before s_i - 300 s to one at or after s_i (NT-D05's proof);
     - kappa_i is the visibility of the bounding trade.
L-3  Baseline universe: exactly the 8,640 consecutive grid instants s_i - k*300 s, k = 1..8,640, immediately preceding s_i (s_i excluded).
     - LIQ(s_i) is defined at a reading instant tau only if every member has a valid observation (L-2) with kappa <= tau.
     - A missing, invalid or not-yet-visible member makes LIQ(s_i) UNKNOWN at tau.
     - No instant is skipped, no older observation substitutes, and nothing is interpolated, backfilled, carried forward or estimated.
     - Scores over the 8,640 members: depth and arrival (#{y < x} + 0.5*#{y = x})/8,640; spread (#{y > x} + 0.5*#{y = x})/8,640.
     - Knowledge instant: K_i = max(kappa_i, kappa_{i-1}, ..., kappa_{i-8640}).
L-4  LIQ(s_i) = 0.4*depth + 0.3*spread + 0.3*arrival. CRISIS iff < 0.15; NON-CRISIS iff >= 0.15; otherwise UNKNOWN. No state between instants.
L-5  A run = consecutive grid instants s_a..s_b, each a valid CRISIS observation; a missing or UNKNOWN observation breaks it.
L-6  NT-M01 at decision t, using only observations whose LIQ is known at t (K <= t):
     - PASS (proven absence) iff some valid NON-CRISIS observation s_nc has t - s_nc <= 1,800 s. It proves that no CRISIS run longer than 30 minutes ends at
       t, observationally and in continuous time; it claims nothing about current liquidity or data freshness.
     - FAIL iff the latest observation s_l known at t is valid CRISIS, t - s_l <= V2, and s_l closes a run with s_l - s_a > 1,800 s. The run is proven
       through s_l; its continuation is not claimed; V2 only bounds how old the proof may be to be reported as FAIL rather than BLOCKED.
     - BLOCKED otherwise. PASS and FAIL are mutually exclusive.
L-7  KS T8 (standard trigger, lower bound):
     - Start: tau0 = max(K_a, ..., K_b) for consecutive valid CRISIS observations s_a..s_b with s_b - s_a > 1,800 s.
     - Extension: a later member known as valid CRISIS extends the run from its K.
     - Lapse: with s_k the last known member, T8 ends at the earlier of K_{k+1} (s_{k+1} known valid NON-CRISIS) and s_{k+1} + V4 (s_{k+1} not known valid
       by then).
     - No observation between s_k and s_{k+1} is assumed (T6 latest-visible precedent, kill_switch:46-49). A late member restarts T8 at its K; a lapse is
       never backfilled and records that the proof ended, never that CRISIS ended. No persistence or cool-down.
L-8  S6 = 1 - LIQ(s_l) at a decision only if s_l is valid and t - s_l <= V2 (the freshness rule), weight 0.08; otherwise unmeasured.
     LIQ = 0 -> s6 = 1 -> at least CRISIS.
L-9  Late data counts only from its knowledge instant; nothing is revised.
L-10 Decision time only.
```

### 6.2 Reading notes

> **Status: REFERENCE.**

- **As-of observations (D-B1).** An observation at s_i takes its tip only from tips visible at s_i, so a tip that
  arrives later never changes it; with L-9, late data counts only from its knowledge instant.
- **Exact depth (D-B2).** A side summed inside the band is exact only when its 50th level lies strictly beyond the band
  edge. The depth definition for an instrument whose depth-50 does not cover the band is PENDING_HUMAN_DECISION (section
  1.3). Until it is decided, an observation whose minimum is not attained on an exact side stays UNKNOWN; on an
  instrument whose depth-50 never covers the band on either side, every observation is UNKNOWN, LIQ is undefined and
  NT-M01 cannot PASS.
- **Fixed baseline.** Under L-3, one missing or invalid observation at grid instant g leaves LIQ UNKNOWN for every
  observation whose 8,640-member baseline contains g, that is for 30 days. Production therefore needs a gap-free,
  qualified 30-day capture (M1).

## 7. FCD-10 — NT_X03_AND_OB_SPREAD_V3 (B4)

> **Status: APPROVED_METHODOLOGY** — implementing §1.21 and §7.2 as written, with D-B1 applied to X-2. Not implemented:
> rule set v9's NT-X03 stays BLOCKED and no OB-SPREAD check exists (section 10).

### 7.1 Text

```text
B4 NT_X03_AND_OB_SPREAD_V3 (authority PRDV4 §1.21 :1286, §7.2 :2101)
X-1 s(t) = (ask - bid)/mid of the latest depth-50 tip visible at t with event time in [t - 10 s, t]; ask > bid.
X-2 Baseline universe: exactly the 8,640 consecutive grid instants g_1..g_8640, where g_1 is the latest UTC-aligned 300 s grid instant strictly before t
    and g_{k+1} = g_k - 300 s. Each needs a valid tip as of g_k (visibility <= g_k) (L-2's depth-50 tip with event time in [g_k - 10 s, g_k], ask > bid,
    from the re-proven authenticated dataset). Any missing, invalid or not-yet-visible member -> NT-X03 and OB-SPREAD BLOCKED. No skipping, substitution,
    interpolation or backfill; trade completeness is not required.
X-3 M = (x_(4,320) + x_(4,321))/2, exact.
X-4 NT-X03 (§1.21): FAIL iff s > 3M; PASS iff s <= 3M.
X-5 OB-SPREAD (§7.2, appended): PASS iff s < 3M; FAIL iff s >= 3M.
X-6 BLOCKED: no fresh tip, incomplete baseline, crossed or locked tip.
X-7 Decision time only; one shared M. Optional Tier II alignment (own adoption; not recommended): §1.21 NT-X03 ">" -> ">=".
```

### 7.2 Reading notes

> **Status: REFERENCE.**

- **No amendment.** B4 approves X-1..X-7 "implementing §1.21 and §7.2 as written, with no amendment". The Tier II
  alignment sentence of X-7 (`§1.21 NT-X03 ">" -> ">="`) is NOT_SELECTED: NT-X03 FAILs strictly above 3M and OB-SPREAD
  FAILs at or above 3M.
- **As-of baseline (D-B1).** Every baseline tip must be visible at its own grid instant g_k.

## 8. FCD-08 — HZ_TURNOVER_INTRADAY_V1 (B5)

> **Status: APPROVED_METHODOLOGY** — for construction only. Not implemented: rule set v9's HZ-LIMITS never passes
> (section 10).

### 8.1 Text

```text
B5 HZ_TURNOVER_INTRADAY_V1 (authority PRDV4 §1.27 :1687; CL2-9)
T-1 A trade = one excursion opened by an exposure-increasing entry fill, counted once at its first entry fill. Fills, exits, reductions, v1 STOP and
    MAX_HOLD attempts and v2 children never count.
T-2 Partial opening fills are one trade; rejected, unfilled or refused intents are none; replay recomputes the same trades.
T-3 N(t) = trades whose first entry fill falls in [UTC day_start(t), t), plus any exposure-increasing intent in flight (none on the governed path).
T-4 FAIL iff N(t) + 1 > 20; PASS iff <= 20; BLOCKED without the trade ledger.
T-5 HZ-LIMITS PASS iff both 8% shares hold and T-4 PASSes.
T-6 Decision time only.
```

## 9. Values V1–V4 (BV)

> **Status: APPROVED_VALUE** — approved by the human for the later construction contract. Each reaches production only
> through a separately approved risk-policy digest (BV); none enters a policy artifact or an approval table here.

### 9.1 Text

```text
BV Proposed values
V1 MAX_DAILY_BAR_AGE = 172,800 s.
V2 delta_stale = 600 s.
V3 delta_obs = 300 s. A 10 s grid (§1.29 :1779, §5.3 :2040) would need ~3 GB of depth-50 tips per 30 days, infeasible (C9).
V4 Lambda (T8 lapse) = 300 s.
```

V1 bounds the age of the latest daily close (C-1), V2 the age of a liquidity proof (L-6, L-8), V3 the observation grid
(L-1) and V4 the T8 lapse (L-7).

## 10. Clause matrix

> **Status: REFERENCE** — provenance, tier, later dependency and present fail-closed result of every adopted clause.
> Provenance for every row: section 1.1, with the deltas of section 1.3 where named. "Absent" means rule set v9 has no
> such check, so no reading can PASS; every S1 entry is refused by the blocking checks of the same rule set.

| Clauses | Consumer | Tier | Needs before it can PASS | Until implemented, on accepted `main` | Grants nothing for |
|---|---|---|---|---|---|
| HZB-1 | HZ-CVAR limit (C-12); per-edge allocation (C-13, C-14) | II, ADOPTED | C-12 construction; FCD-17 and H^(e) for C-13 and C-14 | No HZ-CVAR, EDGE-CVAR or MARGINAL-CVAR check (absent); C-13 and C-14 stay BLOCKED once built | A budget value, policy digest or approval-table entry; a shared stress limit (D-B5); a fill-time rule (D-B4) |
| R-1..R-7 | NT-R03 at the decision (R-4, R-7) and at the fill (R-5) | III | Construction; engine fill-time refusal (schedule v7) | NT-R03 BLOCKED for every prospective entry and every open position (`governed_paper_entry_safety.py:1133`, `:1120`) | Admission; a resize; a fill |
| R-8 | KD-0, KD-9 and KD-10 of RECORD A | III | RECORD A construction; D-A1 for KD-9 | Every Kelly reading BLOCKED: no FCD-01 risk evidence exists (amendment section 4.2) | A D-A1 variant; a Kelly fit |
| C-1..C-8, MC-1..MC-12 (MC-8a, MC-10, D-B3) | The CVaR99\* estimate | III | Construction; an M1-qualified mark archive (C-21) | No CVaR99\* is produced | A source qualification |
| C-9, C-10 | NT-R05 at the decision and at the fill | III | Construction | NT-R05 BLOCKED: `portfolio_cvar99_not_produced` (`governed_paper_entry_safety.py:1677`) | Admission |
| C-11, C-20 | S3 of the §1.29 system state | III | Construction | S3 unmeasured (`governed_paper_system_state.py:473`) | A state transition |
| C-12 | HZ-CVAR | III, with HZB-1 | Construction | Absent | A budget value |
| C-13 | EDGE-CVAR | III | FCD-17 and H^(e) | Absent; BLOCKED by C-13 once built | A capacity estimate |
| C-14 | MARGINAL-CVAR | III | A defined edge budget | Absent; BLOCKED by C-14 once built | A marginal cap |
| C-15 | STRESS-HV | III | Construction | Absent | A shared stress limit |
| C-16 | STRESS-CORR | III | Construction | Absent | — |
| C-17 with LS-A | STRESS-LIQ | III | Construction | Absent | LS-B; an ADV source |
| C-18 | §1.18 de-risk duties | III | A representable position action | BLOCKED_UNREPRESENTABLE (`governed_paper_system_state.py:48`) | A position, order or engine action |
| C-19 | Hourly monitoring between decisions | III | MONITORING_CADENCE (pending) | Unmeasured | A monitoring claim |
| C-21, BV | Production use | III, APPROVED_VALUE | An approved risk-policy digest; M1 | Every production reading BLOCKED | Production activation |
| L-1..L-5, L-9, L-10 (D-B1, D-B2) | LIQ observations | III | Construction; a qualified 30-day capture (M1) | No LIQ is produced | A liquidity claim |
| L-6 | NT-M01 | III | Construction | NT-M01 BLOCKED: `liquidity_regime_not_produced` (`governed_paper_entry_safety.py:1691`) | Admission |
| L-7 | KS T8 | III | Construction; a new ladder version | T8 unmeasured (`governed_paper_kill_switch.py:191`) | A kill-switch action |
| L-8 | S6 of the §1.29 system state | III | Construction | S6 unmeasured (`governed_paper_system_state.py:486`) | A state transition |
| X-1..X-4, X-6, X-7 (D-B1) | NT-X03 | III | Construction; a qualified 30-day book capture (M1) | NT-X03 BLOCKED (`governed_paper_entry_safety.py:1755`) | An amendment of §1.21 |
| X-5 | OB-SPREAD (§7.2) | III | Construction | Absent | — |
| T-1..T-6 | HZ-LIMITS turnover leg | III | Construction; the governed trade ledger | HZ-LIMITS never PASSes: `intraday_turnover_of_20_trades_per_day_has_no_defined_reading` (`governed_paper_entry_safety.py:1439`) | Admission |

## 11. RECORD A / RECORD B interface

> **Status: REFERENCE** — RECORD A (`docs/crypto_core/s1_kelly_class_completion_amendment_v1.md`) and the sections
> above govern.

- **Risk basis.** KD-0 defines Risk_j as "the FCD-01 risk amount (RECORD B1, R-5) of trade j's position at its opening
  fill", and KD-0's notation line (RECORD A clarification C-1) defines rho_t as the candidate's actual FCD-01 stop-risk
  fraction (R-4 at the decision, R-5 at the exposure-increasing fill). Section 3.1 is that FCD-01. KD-10a recomputes
  Risk_j from the sealed opening fill (fill price, the DEC-7 reading at its decision, policy, fill-instant mark), the
  inputs that R-1 and R-5 use.
- **Units.** R-8 and KD-0 agree: rho is a fraction of equity at stop risk, never a notional allocation.
- **Caps.** NT-R03's `rho <= 0.04` (R-7, R-5) and RECORD A's `rho_t <= min(f, 0.04)` and `rho <= 0.04` (KD-0, KD-13)
  bind together; neither relaxes the other.
- **D-A1.** Adopting B1 selects no D-A1 alternative. The exact variant stays PENDING_HUMAN_DECISION (amendment section
  5.2), so the Kelly fit of KD-9 stays not construction-ready, and FCD-01 is unchanged by either alternative.
- **No resize.** R-5 and C-10 refuse the whole exposure-increasing fill, as KD-0 and companion section 4.7 (A9′) require
  of the fixed unit.
- **Unchanged.** The RECORD A amendment is not edited. Its statements that RECORD B lay outside it, and that no FCD-01
  risk evidence exists, stay true: this change adopts FCD-01 as methodology and implements nothing.

## 12. Construction acceptance criteria

> **Status: REFERENCE** — acceptance criteria for a later, separately authorized implementation contract. Each row
> cites the clause that decides it; the clause governs, and a row never adds a rule. The D-B rows follow item 6
> ("Regression") of RT-1, RT-2 and RT-3.

```text
T-NRM-01 R-7: rho = 0.04 exactly -> PASS; rho above 0.04 -> FAIL;
T-NRM-02 R-7: order in flight, no fresh mark, no armed stop, ATR missing, NAV missing or <= 0, unrepresentable -> BLOCKED;
T-NRM-03 R-1: fresh mark at or beyond the armed stop (sgn(q)*(m - s) <= 0) -> x = m and risk = |q|*m*c; flat -> 0;
T-NRM-04 R-5: post-fill rho > 0.04 -> the exposure-increasing fill is REJECTED whole, never resized;
T-NRM-05 R-6: the current position's risk is reported and never refuses a non-entry;
T-NRM-06 C-1: fewer than 253 consecutive daily closes, or a latest visible close before t - V1 -> BLOCKED (CVAR_HISTORY_INSUFFICIENT / STALE);
T-NRM-07 C-6, C-8: n_tail >= 50 -> CVaR99* = ES; n_tail < 50 -> CVaR99* = max(ES, CVaR_MC) (MC-8a);
T-NRM-08 MC-11: the regression vector reproduces exactly (seed, u_0..u_2, picks, n_tail = 3, the exact ES rational, CVaR_MC = 3/25), and MC-8a gives the
         exact ES (about 0.120372);
T-NRM-09 MC-3 (D-B3): the same series day under archive A_k and under a strict superset A_{k+5} -> identical seed, picks and CVaR_MC;
T-NRM-10 MC-3: identical draws for any holdings, decision and side;
T-NRM-11 C-9: CVaR99* = 0.05 -> FAIL; below 0.05 with every input proven -> PASS; otherwise BLOCKED;
T-NRM-12 C-10: post-fill CVaR99* >= 0.05 -> the fill is REJECTED whole;
T-NRM-13 C-12 with HZB-1: an INTRADAY HZ-CVAR at 2% of NAV -> not PASS; strictly below with every input proven -> PASS;
T-NRM-14 C-13, C-14: EDGE-CVAR and MARGINAL-CVAR -> BLOCKED while FCD-17 and H^(e) are undecided;
T-NRM-15 C-15: STRESS-HV = 1.5 x CVaR99*; at 0.08 -> FAIL;
T-NRM-16 C-16: one instrument -> STRESS-CORR PROVEN_NOT_APPLICABLE;
T-NRM-17 LS-A: stress CVaR_liq at 0.08, or a stressed book that cannot fill |q| in one close-only order -> FAIL; below 0.08 with every input proven -> PASS;
T-NRM-18 C-18: de-risk duties -> BLOCKED_UNREPRESENTABLE obligations, never executed;
T-NRM-19 C-20: NAV <= 0 -> BLOCKED; S3 unmeasured;
T-NRM-20 L-2 (D-B1): tip A (event s-8 s, visible s-7 s), tip B (event s-2 s, visible s+1 s) -> the observation at s uses A at every reading instant; with
         only B present -> UNKNOWN;
T-NRM-21 L-2 (D-B2): exact/exact -> min; exact bid 10 with ask lower bound 12 -> 10; exact bid 10 with ask lower bound 7 -> UNKNOWN; both lower bounds
         -> UNKNOWN;
T-NRM-22 L-3: 8,639 valid members and one missing, an older valid observation present -> LIQ(s_i) UNKNOWN; the older observation never substitutes;
T-NRM-23 L-3: a member visible only after tau -> UNKNOWN at tau, defined from K_i, nothing revised;
T-NRM-24 L-5, L-6: 7 consecutive valid CRISIS observations (span 1,800 s) -> not FAIL; 8 (span 2,100 s) closing at s_l, the latest known at t, with
         t - s_l <= V2 -> FAIL;
T-NRM-25 L-6: a valid NON-CRISIS observation known at t with t - s_nc <= 1,800 s -> PASS; PASS and FAIL never both; otherwise BLOCKED;
T-NRM-26 L-7: T8 starts at max(K_a, ..., K_b); a later member extends it; it lapses at the earlier of K_{k+1} (valid NON-CRISIS) and s_{k+1} + V4; a
         late member restarts it at its K; a lapse is never backfilled;
T-NRM-27 L-8: S6 measured only when s_l is valid and t - s_l <= V2; LIQ = 0 -> s6 = 1 -> at least CRISIS;
T-NRM-28 X-4, X-5: s = 3M exactly -> NT-X03 PASS and OB-SPREAD FAIL;
T-NRM-29 X-2 (D-B1): one baseline grid tip missing, invalid or visible only after its g_k -> NT-X03 and OB-SPREAD BLOCKED;
T-NRM-30 X-6: no fresh tip, a crossed or a locked tip -> BLOCKED;
T-NRM-31 T-4: N(t) = 19 -> PASS; N(t) = 20 -> FAIL; no trade ledger -> BLOCKED;
T-NRM-32 T-1, T-2: partial opening fills are one trade; rejected, unfilled or refused intents, exits, reductions, v1 STOP and MAX_HOLD attempts and v2
         children are none;
T-NRM-33 C-21, BV: no admitted risk-policy digest -> every reading BLOCKED in production; tests use TEST_ONLY approvals only;
T-NRM-34 MC-9, L-9: replay is byte-identical, and late data never revises a reading.
```

## 13. Pending decisions after this adoption

> **Status: REFERENCE** — every entry stays PENDING_HUMAN_DECISION or an unproven external dependency. No implementation,
> admission or default may assume any outcome.

| Item | After this adoption |
|---|---|
| D-B2, second clause | The depth definition for an instrument whose depth-50 does not cover ±5 bps: no text offered; pending, with the S1 instrument identity and its depth coverage as external facts |
| Advisory D-B4 | Not approved: "State whether HZ-CVAR and STRESS-LIQ also bind at the fill." No fill-time rule beyond C-10 is adopted |
| Advisory D-B5 | Not approved: "State whether HZB-1 also shares the 8% stress limits." The advisory's interim reading ("PASS only below the stricter candidate (3.2%)") is not adopted |
| FCD-17 (K_max, external ADV) and H^(e) | Pending; EDGE-CVAR and MARGINAL-CVAR BLOCKED |
| MONITORING_CADENCE | Pending; hourly monitoring between decisions unmeasured (C-19) |
| FCD-05 | Pending (KS T3, T12, NT-T02, cool-down and recovery) |
| FCD-13, FCD-14 / HC-14a, HD-07 | Pending, unchanged |
| M1 source qualification | Pending: the mark archive and a gap-free 30-day depth-50 and trade capture; production readings BLOCKED |
| D1 venue facts | Pending: fees, funding and margin, including the bound economics policy that R-1's c reads |
| Risk-policy production approval | Pending: no risk-policy digest and no approval-table entry exist |
| C1–C9 and DEC-1 | Pending, unchanged |
| Incubation record and parameters (companion items 1.4–1.8) | Pending, unchanged |
| D-A1 | PENDING_HUMAN_DECISION (RECORD A amendment section 5.2) |
| The 100-trade Kelly bootstrap | Pending; BLOCKED at n_w = 100 (KD-7) |
| REAL_PAPER_EXECUTION and Stage-4 authorization | BLOCKED, not authorized |
| Every other FCD decision and HC choice | Pending (companion section 12.1) |

The advisory's items D-B4 and D-B5, quoted as historical text with no operative authority:

```text
D-B4 [P3] State whether HZ-CVAR and STRESS-LIQ also bind at the fill. Recommended: HZ-CVAR yes, using the same per-record factor.
D-B5 [P3] State whether HZB-1 also shares the 8% stress limits. Until decided, PASS only below the stricter candidate (3.2%).
```

## 14. Non-claims and admission effect

> **Status: REFERENCE.**

- **Admission effect: none.** This change edits no code, test, rule set, schedule, seal, policy artifact or approval
  table. NT-R03, NT-R05, NT-M01 and NT-X03 stay BLOCKED, HZ-LIMITS never passes, T8, S3 and S6 stay unmeasured, and the
  appended §1.18 and §7.2 checks do not exist (section 10), so the accepted entry gate still refuses every governed S1
  entry (`docs/crypto_core/paper_trading_phase_map.md` section 12).
- **Not claimed:** any CVaR, liquidity, spread or turnover measurement; a qualified source; risk-policy production
  approval; real-paper readiness (REAL_PAPER_EXECUTION stays BLOCKED); Stage-4 eligibility or credit; profitability or
  edge.
- **No authority** for shadow, live, capital, orders, fills, positions, a scheduler, readiness or connector
  transitions, or private API access.
- **No new value.** Beyond the approved V1–V4, no number, default, policy artifact or approval-table entry is created,
  and V1–V4 enter none.

## 15. Adoption verification matrix

> **Status: REFERENCE.**

### 15.1 Content binding

PRDV4 at the head of this change is:

- blob `455cdc1c988ad2d4af2767f0233c4e9cc6406316`, 115,565 bytes;
- SHA-256 `5ba8ba20411875363f1373c892622d6eeef9811e2b44da00c07b39e4383671ef`.

Against the base blob `f61965868b1b9bea109cdb409f59989f30e0a7d8` it inserts 3 lines after line 1682 and changes
nothing else. A passage digest is SHA-256 over the UTF-8 bytes of the passage's lines at the head, joined by line feeds,
without a leading or trailing line feed.

| Item | PRDV4 location | Lines at the head | SHA-256 of the passage |
|---|---|---|---|
| HZB-1 | §1.27, Horizon Isolation Rules, nested under the PER-HORIZON bullet | 1683–1685 | `bef57e10282a9d3e651eda5eab4195995f552b3a5433fc5af55fc4d64d79c106` |

The RECORD B text this document reproduces was taken from one extract of the decision form (UTF-8, line feeds,
156 lines from `EXACT_RECORD_B_HUMAN_DECISION_TEXT` through V4 and one closing empty line, 14,486 bytes)
with SHA-256 `7df83d991e7993ae1e8cc8c0be081d4c95b0e847095a529948fd8f541b1940f2`.

### 15.2 Checks

| Id | Check | Required result |
|---|---|---|
| T-NRA-01 | PRDV4 §1.27 | The HZB-1 sentence occurs once, as the bullet right after the PER-HORIZON rule, word for word without its quotation marks |
| T-NRA-02 | Every other PRDV4 byte | Unchanged against the base blob |
| T-NRA-03 | The companion and the RECORD A amendment | Blobs `d351b4fb0f92e03ab96e11f71708b733f9c3cb16` and `e0da520c0291e397e0499329bd452455809f8e83`, unchanged |
| T-NRA-04 | Sections 1.2, 2.1, 3.1, 4.1, 4.2, 5.1, 6.1, 7.1, 8.1 and 9.1 | Word for word the RECORD B text under section 0.3, except the changes of section 1.4 |
| T-NRA-05 | Section 1.3 | Word for word the advisory's items D-B1..D-B3 and item 5 of RT-1..RT-3 |
| T-NRA-06 | Texts not adopted | HZB-2, LS-B, MC-8b, the two Tier II texts, D-B4, D-B5 and the D-B2 depth definition appear only under NOT_SELECTED, REFERENCE or PENDING_HUMAN_DECISION, and nothing reads, defaults or falls back to one |
| T-NRA-07 | Values | No number beyond V1–V4 and RECORD B's approved text is introduced; no policy artifact, digest or approval-table entry is created |
| T-NRA-08 | The phase map | One section appended after its last line; every earlier byte unchanged |
| T-NRA-09 | Changed paths | Exactly PRDV4, this document and `docs/crypto_core/paper_trading_phase_map.md` |
| T-NRA-10 | Admission | No code, test, rule set, schedule, seal, policy artifact or approval table changes |
