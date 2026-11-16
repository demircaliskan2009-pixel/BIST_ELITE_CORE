# S1 Kelly Class Completion Amendment V1

> Adoption record of the human-approved RECORD A (`S1_KELLY_CLASS_COMPLETION_DECISION_V3`) for the governed paper
> path of `LIMITED_S1_PAPER_V1`, contract `S1_KELLY_CLASS_COMPLETION_DOCTRINE_ADOPTION_V1`. It installs A1 (PRDV4
> §0.3 and §1.21, and section 2 below) and the doctrine reading KD-0 (section 4), records KD-1..KD-13 as approved
> construction methodology (section 5), and admits nothing: every governed S1 entry stays refused (section 6).

## 0. Status, source and reading rules

### 0.1 Status and effect

- **Adoption merge.** This document and its PRDV4 change take effect together, and only when four things hold: this
  change has passed its own protected independent audit (GPT-6.1 Sol, `docs/crypto_core/agent_workflow.md` section
  24.4) with exact-head CI; the human has authorized its standard merge by naming the pull request, its exact head and
  the merge command (section 24.5); that merge is done; and post-merge verification proves that `main` holds the
  changed files byte for byte as at that head. Until then neither text has force, and PRDV4 and
  `docs/crypto_core/s1_approved_doctrine_adoption_v1.md` (the companion) bind as written.
- **Role.** PRDV4 holds the constitutional text of A1.1 and A1.2. This document holds A1.3 (section 2,
  `KELLY_CLASS_COMPLETION_WINDOW_V1`, with its forward-only supersession of companion clauses in section 3), the
  doctrine reading KD-0 (section 4), the approved construction methodology KD-1..KD-13 (section 5) and the decision
  record (section 1). It adds no doctrine beyond the approved items. Between this document and PRDV4, PRDV4 governs,
  and between two safety rules the stricter one applies.
- **Tiers.** I constitutional: A1.1, A1.2 and A1.3. II doctrine reading: KD-0. III methodology: KD-1..KD-13 with the
  approved delta D-A1, approved for construction only. IV implementation: not authorized.
- **Forward-only.** The companion is not edited. From the adoption merge the companion clauses of section 3.1 are
  superseded and have no force; they stay in the companion as history, and nothing earlier is erased or re-dated.

### 0.2 Status blocks

Every heading below carries one status block:

- **ADOPTED** — binding from the adoption merge, as written.
- **APPROVED_METHODOLOGY** — approved for construction only. It binds a later, separately authorized implementation
  contract and is not implemented; until then the accepted readings stay as they are.
- **PENDING_HUMAN_DECISION** — non-normative. No value, method, state or permission may be read, defaulted,
  implemented or admitted from it.
- **REFERENCE** — supporting record, index, analysis or acceptance criteria. It adds no rule.

### 0.3 Reading rules

- The approved texts are reproduced inside `text` blocks word for word, without the decision form's change markers
  (`[=]`, `[Δ]`, `[Δ new]`) and with their source line breaks, except that the passages changed by the clarification
  are re-flowed. The human-approved clarification of section 1.2 changes three passages; section 1.3 lists each change
  exactly.
- `rho_t` is the candidate's actual FCD-01 stop-risk fraction at the instant evaluated: R-4 at the decision and R-5 at
  the exposure-increasing fill. Every `rho` of the approved texts denotes `rho_t` (C-1, C-2).
- Line references inside the approved texts (for example `§1.28 :1751`) point into PRDV4 blob `6f5ad917`, the base of
  this change. This change inserts 13 lines before §1.28, so each cited §1.28 clause sits 13 lines later at
  the head of this change. Companion line references are unchanged, because the companion is unchanged.
- Missing, unproven or unknown evidence stays BLOCKED or HOLD. No status block, quotation or verification row of this
  document is a permission.

## 1. Decision record

> **Status: REFERENCE** — the decision this document adopts.

### 1.1 Record

```text
HUMAN_GOVERNANCE_DECISION_RECORD_V1
RECORD            S1_KELLY_CLASS_COMPLETION_DECISION_V3 (RECORD A), with the clarification of section 1.2
FORM              A1 [constitutional]: texts A1.1, A1.2 and A1.3, effective only through their own docs-only adoption
                  change, protected audit and exact-head merge.
                  A2 [doctrine reading]: KD-0, adopted in the same change.
                  A3 [methodology]: KD-1..KD-13 for construction only, deciding companion items 5.1 and 5.2
                  (HC-16b = KD-4). The bootstrap at n_w = 100 stays pending and reads BLOCKED; HC-16a, HC-16c and
                  HC-16d stay pending.
DECISION          A1, A2 and A3 approved, with the approved additional delta D-A1 (section 5.2).
DECIDED BY        The human, as relayed by the ChatGPT controller. Approver identity: not recorded here (UNKNOWN).
CHANNEL           Controller packet of 2026-11-15, which states:
                    "HUMAN_APPROVED_NOT_YET_ADOPTED: RECORD_A=S1_KELLY_CLASS_COMPLETION_DECISION_V3"
                    "APPROVED_ADDITIONAL_DELTAS: D-B1, D-B2, D-B3, D-A1"
                    "THESE ARE HUMAN DECISIONS, NOT MERGED AUTHORITY."
                  Controller packet of 2026-11-16 for contract S1_KELLY_CLASS_COMPLETION_DOCTRINE_ADOPTION_V1, which
                  relays the clarification of section 1.2.
DECISION INSTANT  Not recorded (UNKNOWN).
SIGNATURE         None. Accepted main defines no signature mechanism for a doctrine decision (UNKNOWN). This record
                  transcribes a relayed decision truthfully; it is not a signed artifact and claims no signature.
SOURCE TEXT       The decision form as presented to the human. It is not a repository artifact; its approved texts
                  are reproduced in sections 2, 4 and 5.
BINDING ACT       The human's separate exact-head standard-merge authorization of this change.
OUTSIDE           RECORD B (S1_NATIVE_RISK_MEASUREMENT_METHOD_DECISION_V3), its selections and the deltas D-B1, D-B2
                  and D-B3; HZB-1; everything listed in sections 7 and 8.
```

### 1.2 Human-approved clarification

```text
C-1  A1.2 notation (solvency).
     The solvency test must use the candidate's actual FCD-01 stop-risk fraction rho_t:
     1 + rho_t * R_j <= 0 => FAIL (KELLY_LOG_DOMAIN_RUIN).
     Never substitute the unconstrained f* or the fractional Kelly allocation f for rho_t.
     The condition applies from the first known trade, including under U5 coverage.
C-2  KD-0 (S1 fixed-unit sizing).
     For LIMITED_S1_PAPER_V1 only, f* and f denote equity-at-stop-risk fractions, not notional fractions.
     The generic PRDV4 §1.28 final-size expression does not resize this fixed unit.
     Require: rho_t <= min(f, 0.04) at decision and exposure-increasing fill.
     Keep independent notional, drawdown, multiplier, margin, risk and protective conditions binding.
     A proven reduction multiplier below 1 refuses the fixed-unit entry rather than resizing it.
     Missing or invalid FCD-01 risk evidence => BLOCKED.
     Do not alter the generic multi-edge sizing contract.
```

### 1.3 Changes to the approved wording

| Passage | Approved wording | Adopted wording | Basis |
|---|---|---|---|
| A1.2, PRDV4 §1.21, Kelly-coverage bullet | `a known outcome R with 1 + f*R <= 0 at the candidate's risk fraction f` | `a known outcome R_j with 1 + rho_t * R_j <= 0`, followed by one added sentence that states C-1 | C-1 |
| A1.3, section 2.1, "Covered components" | `1 + f*R > 0 for every known outcome at the candidate's risk fraction` and `is checked from the first known trade.` | `1 + rho_t * R_j > 0 for every known outcome R_j at the candidate's actual FCD-01 stop-risk fraction rho_t, never the unconstrained f* or the fractional Kelly allocation f` and `is checked from the first known trade, including under U5 coverage; 1 + rho_t * R_j <= 0 is FAIL (KELLY_LOG_DOMAIN_RUIN).` | C-1 |
| T-KCW-11 | `one known outcome with 1 + rho*R <= 0 under coverage` | `one known outcome R_j with 1 + rho_t * R_j <= 0 under coverage` | C-1 |
| KD-0 | The RECORD A text | The RECORD A text, then the C-2 lines and the C-1 notation line (section 4.1) | C-1, C-2 |
| KD-9 | `rho <= f_cap` | Read with D-A1 (section 5.2) | D-A1 |

PRDV4 does not use the companion's class identifiers, so its added sentence says "including while the Kelly estimate
is covered" where C-1 says "including under U5 coverage". No other word of an approved text changes.

## 2. KELLY_CLASS_COMPLETION_WINDOW_V1 (A1.3)

> **Status: ADOPTED** — binding from the adoption merge. It replaces companion section 8.2 (section 3.1).

### 2.1 Text

```text
8.2 U5 coverage boundary (KELLY_CLASS_COMPLETION_WINDOW_V1)
- Scope. U5 covers the Kelly reading only under an ACTIVE record whose covered list holds U5, and only while the edge's known closed governed-paper trades
  in the lineage include no win or no loss.
- Closed trades. One CLOSED excursion (FLAT -> nonzero -> FLAT) of the lineage's governed outcome. It counts once its closing fill is in the sealed lineage
  at or before the decision instant and every funding settlement it carries is published, recomputed by the verifier. At one instant a closing fill is
  ordered before an entry decision. A closed but not yet known trade -> BLOCKED (KELLY_TRADE_COUNT_UNPROVEN).
- Classes. Win: realized net PnL > 0. Loss: < 0. Zero: = 0 — counted, completes no class.
- Class completion. At the first instant both a win and a loss are known, U5 coverage ends and never returns.
- Covered components. Only components undefined for lack of own history: f*, b, the Kelly fit's f_cap, and the positivity of G(f) while fewer than two
  trades are known. The solvency domain of G(f) — 1 + rho_t * R_j > 0 for every known outcome R_j at the candidate's actual FCD-01 stop-risk fraction
  rho_t, never the unconstrained f* or the fractional Kelly allocation f — is checked from the first known trade, including under U5 coverage;
  1 + rho_t * R_j <= 0 is FAIL (KELLY_LOG_DOMAIN_RUIN). A defined component that fails is FAIL.
- Never covered. A Kelly reading undefined because a method is unapproved, an outcome or its risk basis is unproven, or the history fails verification;
  sum f <= 0.04 on actual risk at the stop; any reading proven to fail.
- No reset. Replay, revocation, expiry, termination and a new record never lower a count, undo a completion or restore coverage; a lineage–edge pair is
  never incubated twice.
- Bounds. Coverage ends no later than the record (A_max, T_max, X); every incubation-basis entry is an attempt; every KS trigger stays in force.
```

### 2.2 Verification rows

> **Status: REFERENCE** — the acceptance criteria of section 2.1 for a later implementation. They replace the
> companion rows superseded in section 3.1.

```text
T-KCW-01 first trade W or L under ACTIVE U5 -> still covered (cap and domain must pass);
T-KCW-02 completion -> coverage ends;
T-KCW-03 closed but unpublished -> KELLY_TRADE_COUNT_UNPROVEN;
T-KCW-04 zero-net trade -> counted, no class;
T-KCW-05 K3 with A3 unapproved -> BLOCKED;
T-KCW-06 replay, new record or revocation -> no reset;
T-KCW-07 rho > 0.04 under coverage -> FAIL;
T-KCW-08 two known losses under coverage -> prod(1 + rho*R) < 1 -> FAIL;
T-KCW-09 EXPIRED_HOLD while class-incomplete -> BLOCKED;
T-KCW-10 five consecutive T5-losing trades -> KS-1 -> SCALE-1 FAIL;
T-KCW-11 one known outcome R_j with 1 + rho_t * R_j <= 0 under coverage -> FAIL (KELLY_LOG_DOMAIN_RUIN);
T-KCW-12 a G-window trade without a proven R -> BLOCKED (KELLY_OUTCOME_UNPROVEN).
```

## 3. Forward-only supersession

> **Status: ADOPTED** — binding from the adoption merge.

### 3.1 Superseded companion clauses

RECORD A supersedes exactly these clauses of the companion (blob `d351b4fb`). Each is superseded by section 2 (its
text in section 2.1 and its rows in section 2.2) and keeps no force from the adoption merge. The companion is not
edited.

| Companion clause | Line | Status before |
|---|---|---|
| §3.3, U5 row, "Window" cell only | 303 | APPROVED (item 1.2) |
| §3.6, HD-K1 row | 361 | PENDING_HUMAN_DECISION |
| §8.1, K1 row | 823 | PENDING_HUMAN_DECISION (item 5.1) |
| §8.1, K2 row | 824 | PENDING_HUMAN_DECISION (item 5.1) |
| §8.2, the whole subsection | 831–855 | APPROVED (item 1.3) |
| §10.3, T-INC-21 | 987 | REFERENCE |
| §10.7, T-KELLY-07 | 1082 | REFERENCE |
| §10.7, T-KELLY-08 | 1083 | REFERENCE |
| §10.7, T-KELLY-12 | 1087 | REFERENCE |

The superseded text, quoted from blob `d351b4fb` (line, then text):

```text
 303  (§3.3, U5 row, Window cell only) Zero closed trades only; coverage ends at the first closed trade (section 8.2)
 361  | Kelly coverage after the first closed trade (HD-K1) | Not offered | U5 ends at the first closed trade (section 8.2); an extension would be a separate change | NOT_OFFERED |
 823  | K1: closed trades, no win | Average win over an empty set: b undefined | BLOCKED, never FAIL. No completion can hold p fixed, because the win that would define b also changes p. Never covered (section 8.2) |
 824  | K2: closed trades, no loss | b undefined | BLOCKED; "wins only gives f\* = 1" is rejected. Never covered (section 8.2) |
 831  ### 8.2 U5 coverage boundary   (lines 831-855, the whole subsection)
 987  | T-INC-21 | First closed trade under an ACTIVE record, a loss or a win | U5 coverage ends; Kelly BLOCKED; HOLD (T-KELLY-07..12) |
1082  | T-KELLY-07 | ACTIVE record; the first closed trade is a loss | U5 coverage ends; b undefined; BLOCKED (`KELLY_RATIO_UNDEFINED`); entry HOLD; no positive f\* |
1083  | T-KELLY-08 | ACTIVE record; the first closed trade is a win | Same; never f\* = 1 |
1087  | T-KELLY-12 | Closed trades of one class only, in any record state | BLOCKED; never PASS and never `COLD_START_EXCEPTED` |
```

### 3.2 Passages not superseded

A1.3 supersedes exactly the clauses of section 3.1. The companion passages below are not superseded. Each restates or
tests the zero-closed-trade boundary that section 3.1 supersedes, and none is adopted doctrine of its own: each is a
derived table, REFERENCE, PENDING_HUMAN_DECISION or decision-record history.

| Companion passage | Line | Status | What it restates |
|---|---|---|---|
| §0.5, "U5 Kelly coverage" row | 112 | Derived table ("Derived from the approved text and the pending decisions; the cited sections govern") | "after the first closed trade U5 never covers (section 8.2)" |
| §3.5, Graduation | 343 | PENDING_HUMAN_DECISION (item 1.7) | "(for U5, one closed trade)" |
| §3.7, Reachability | 373 | PENDING_HUMAN_DECISION (items 1.7, 1.8) | F-3: no entry after the edge's first closed trade |
| §10.7, T-KELLY-02 and T-KELLY-03 | 1077–1078 | REFERENCE; they read the superseded K1 and K2 rows | One class only: BLOCKED |
| §10.7, T-KELLY-09 and T-KELLY-10 | 1084–1085 | REFERENCE; they test the superseded section 8.2 | "U5 does not cover"; "U5 never covers again" |
| §11.2, rows 1.3, 5.1, 5.2 and HD-K1, and the note below the table | 1132, 1149–1150, 1153, 1158 | Decision-record history | The decisions that RECORD A follows |
| §12.1, rows 1.8, 5.1 and 5.2 | 1204, 1209–1210 | PENDING_HUMAN_DECISION list | F-3; items 5.1 and 5.2 as pending |

None of them has force against section 2. The companion's own rule decides it: "Between this record and PRDV4, PRDV4
governs" (companion section 0.1). From the adoption merge, PRDV4 §0.3 and §1.21 as amended by A1.1 and A1.2 govern each
of these passages, and section 2 states the governing boundary.

- The §0.5 row's result ("Never") still holds, because no PAPER_INCUBATION_V1 record can be ACTIVE (section 6); its
  reason clause describes the superseded boundary.
- T-KELLY-02, -03, -09 and -10 test superseded text, so they cannot hold together with section 2.2. Section 2.2 holds
  the acceptance criteria of the governing text.
- The decision-record rows stay as history, and section 1 records the later decision: A1.3 replaces item 1.3, and A3
  decides items 5.1 and 5.2 for construction only (section 5). Item 1.8 (F-1..F-4) stays pending; its F-3 statement
  describes the superseded boundary.

## 4. KD-0 — Kelly risk units for LIMITED_S1_PAPER_V1 (A2)

> **Status: ADOPTED** — doctrine reading, binding from the adoption merge.

### 4.1 Text

```text
KD-0 Units (resolves C-K1). Every Kelly quantity is in RISK units.
     - Risk_j = the FCD-01 risk amount (RECORD B1, R-5) of trade j's position at its opening fill (quote currency, > 0); R_j = realized net PnL_j / Risk_j.
     - f* and f are fractions of equity at stop risk; rho is the candidate's FCD-01 risk fraction.
     - §1.28 :1751 "Final size: size_e = min(f_e x equity, drawdown_mult x max_position)" is not evaluated: the unit is never resized, and the notional
       single-position limit stays HZ-LIMITS' 8%.
     - No approved FCD-01 -> BLOCKED (KELLY_METHOD_UNAPPROVED).
[C-2] For LIMITED_S1_PAPER_V1 only, f* and f denote equity-at-stop-risk fractions, not notional fractions.
[C-2] The generic PRDV4 §1.28 final-size expression does not resize this fixed unit.
[C-2] Require: rho_t <= min(f, 0.04) at decision and exposure-increasing fill.
[C-2] Keep independent notional, drawdown, multiplier, margin, risk and protective conditions binding.
[C-2] A proven reduction multiplier below 1 refuses the fixed-unit entry rather than resizing it.
[C-2] Missing or invalid FCD-01 risk evidence => BLOCKED.
[C-2] Do not alter the generic multi-edge sizing contract.
[C-1] Notation: rho_t is the candidate's actual FCD-01 stop-risk fraction (R-4 at the decision, R-5 at the
      exposure-increasing fill). Every rho of sections 2, 4 and 5 denotes rho_t; the unconstrained f* and the
      fractional Kelly allocation f never stand in for it.
```

### 4.2 Reading notes

> **Status: REFERENCE** — cross-references only; section 4.1 and the cited sections govern.

- **Coverage and the cap.** While U5 covers the reading, f\* and the Kelly fit's f_cap are covered components (section
  2.1), so KD-13 applies `rho_t <= 0.04` at the decision and at the fill; sum f ≤ 0.04 on the actual risk at the stop
  is never covered (PRDV4 §1.21). Once the reading is defined, KD-9 (with D-A1) and KD-12 apply
  `rho_t <= min(f, 0.04)`.
- **No resize.** The fixed unit's notional single-position limit stays HZ-LIMITS' 8%. A proven state-triggered
  multiplier below 1 refuses the entry, as companion section 4.7 (A9′) already requires, and a Kelly-fit failure at
  the fill is a FAIL with no resize (KD-9).
- **Generic §1.28.** PRDV4 §1.28 is not edited. KD-0 reads it for the one-edge fixed unit of LIMITED_S1_PAPER_V1 only.
  Portfolio Kelly (multi-edge) does not apply to one edge (KD-11) and stays as written for every other use.
- **FCD-01 today.** FCD-01 (NT_R03_OPEN_RISK_AT_STOP_V1, RECORD B1) is human-approved for construction and not
  implemented, so no FCD-01 risk evidence exists and every Kelly reading is BLOCKED (C-2).

## 5. KELLY_DEFINED_READING_V3 — KD-1..KD-13 (A3)

> **Status: APPROVED_METHODOLOGY** — for construction only; it decides companion items 5.1 and 5.2 (HC-16b = KD-4).
> Not implemented: every accepted rule set, schedule, seal and module stays unchanged, and the accepted SCALE-1
> reading keeps the Kelly fit unproven until a separately authorized implementation contract builds this methodology.

### 5.1 Text

```text
KD-1 Window: the latest n_w = min(n, 100) known closed trades, in engine close order.
KD-2 Classes per A1.3; zero trades count in the window and in p's denominator, never in b.
KD-3 Defined iff the window holds >= 1 win and >= 1 loss; else BLOCKED (KELLY_RATIO_UNDEFINED); never re-covered.
KD-4 (HC-16b) w_j = 0.95^j, j = 0 newest; p = sum_wins w_j / sum_all w_j; q = 1 - p (normalized finite-window EWMA; no initial value).
KD-5 b = mean_wins(R) / mean_losses(|R|), unweighted, same window.
KD-6 f* = (p*b - q)/b, exact; f* <= 0 -> FAIL (KELLY_NON_POSITIVE).
KD-7 n_w < 100 -> f = f*/4 (the estimation-error rule cannot change f below 100). n_w = 100 -> the bootstrap (sigma(f*) > 0.3*f*) is undecided ->
     BLOCKED.
KD-8 f_cap = min(f, 0.04) (§1.28 :1736, one edge).
KD-9 Kelly fit: rho <= f_cap at decision (R-4) and at fill (R-5); otherwise FAIL (no resize).
KD-10 Log utility (§1.28 :1739-1745). Evaluated exactly on the empirical distribution of the G window — the latest n_g = min(n, 60) known closed trades
      (§1.28 Sigma "rolling 60-trade"), equal weights — at the candidate's own risk fraction rho (R-4 at decision, R-5 at fill; never a historical trade's):
  KD-10a Outcomes: every G-window trade needs a known outcome and a proven R_j. Risk_j must be recomputed by the verifier from the sealed opening fill (fill
         price, the DEC-7 reading at its decision, policy, fill-instant mark) and must be > 0. Any missing or invalid R_j -> BLOCKED
         (KELLY_OUTCOME_UNPROVEN). No trade is skipped, substituted or estimated.
  KD-10b Solvency domain (from the first known trade): a_j = 1 + rho*R_j. If any a_j <= 0 -> FAIL (KELLY_LOG_DOMAIN_RUIN): at rho, outcome j exhausts equity,
         ln(1 + rho*R_j) is undefined and E[ln(1 + rho*R)] = -infinity. a_j = 0 FAILs.
  KD-10c Positivity (n_g >= 2 and every a_j > 0): G_emp(rho) = (1/n_g)*sum ln a_j > 0 <=> prod_j a_j > 1, decided by one exact rational comparison.
         prod <= 1 -> FAIL (KELLY_LOG_UTILITY_NON_POSITIVE); prod = 1 FAILs.
  KD-10d The second-order form rho*mu_R - rho^2*s2_R/2 (sample variance) is a reported diagnostic only, never a PASS basis.
  KD-10e Arithmetic uses exact rationals from the engine's exact values, never renderings. The product is never rendered as text (it can exceed CPython's
         4,300-digit int-to-str limit). Evidence records each a_j at scale 18 (ROUND_HALF_EVEN), the comparison outcome and the window's trade and risk
         digests.
KD-11 Portfolio Kelly inverse(Sigma)*mu ("multi-edge", :1727) does not apply to one edge.
KD-12 PASS iff defined (KD-3), f* > 0, n_w < 100, and at both decision and fill KD-9 holds and KD-10 holds (every R_j proven, every a_j > 0,
      prod > 1). FAIL on KD-6, KD-9, KD-10b or KD-10c. BLOCKED otherwise.
KD-13 Under A1 coverage:
      - FAIL if rho > 0.04, or if any known G-window trade has a_j <= 0, or if n_g >= 2 and prod <= 1;
      - COLD_START_EXCEPTED if rho <= 0.04 is proven, every G-window R_j is proven, every a_j > 0, and (n_g < 2 or prod > 1);
      - BLOCKED otherwise.
HC-16 MAPPING Only HC-16b is defined in the repo (companion :1210) = KD-4. HC-16a/c/d are ids only (:1154, :1213): mapping UNKNOWN. KD-5, KD-7, KD-10
      and KD-11 decide only what they state.
```

### 5.2 Approved delta D-A1 (KD-9)

```text
KD-9 (D-A1) Kelly fit: rho*max(1, Lbar) <= f_cap, with Lbar = mean_losses(|R|) of the KD-1 window, at decision (R-4)
            and at fill (R-5); otherwise FAIL (no resize).
```

- **Effect.** It never loosens the gate: max(1, Lbar) ≥ 1, so a fit that holds with D-A1 also holds without it. KD-12
  reads KD-9 with D-A1.
- **Provenance.** The human approved D-A1 by its label (section 1.1). Its source item offered two corrections of one
  finding: this minimal factor, or a Kelly stake measured from the entry price to the stop. Only the minimal factor is
  consistent with KD-0 and C-2, under which rho_t and every R_j are in FCD-01 risk units. The wording above is the
  minimal factor's exact source text; that source is a non-authoritative advisory, and the authority is the human
  approval.
- **Rationale (REFERENCE).** f\* = (p·b − q)/b is the equity fraction lost on an average losing trade. With an average
  loss of Lbar risk units, the growth-optimal stop-risk fraction is f\*/Lbar, so without the factor the fit could admit
  up to Lbar times the fractional-Kelly cap.

### 5.3 Still pending inside the methodology

- **The 100-trade bootstrap.** The estimation-error rule (sigma(f\*) > 0.3·f\*) is undecided, so the reading is BLOCKED
  once the window holds 100 known closed trades (KD-7).
- **HC-16a, HC-16c and HC-16d.** Identifiers only (companion lines 1154 and 1213); their mapping is UNKNOWN, and
  nothing here decides them.
- **FCD-01.** Every Kelly reading needs FCD-01 risk evidence (KD-0); RECORD B is not implemented.

## 6. Non-claims and admission effect

> **Status: REFERENCE.**

- **Admission effect: none.** This change edits no code, test, policy artifact or approval table. The accepted entry
  gate still refuses every governed S1 entry (`docs/crypto_core/paper_trading_phase_map.md` section 12).
- **No coverage today.** U5 needs an ACTIVE PAPER_INCUBATION_V1 record. The record schema (item 1.7) and A_max, T_max
  and W_INC (items 1.4–1.6) are pending, and no approval table admits a record, so U5 covers nothing and the Kelly
  reading is BLOCKED.
- **Not claimed:** that any lineage reaches class completion, survives the defined Kelly reading or reaches ordinary
  admission; any Stage-4 eligibility or credit (the Exception Record "grants nothing for shadow, live, capital, §1.13
  Stages 4–5 or §1.22 promotion", PRDV4 §1.21; LIMITED_S1_PAPER_V1 grants nothing for §1.13 Stages 4–5, PRDV4 §1.20);
  real-paper readiness (REAL_PAPER_EXECUTION stays BLOCKED, phase map section 12); profitability or edge.
- **No authority** for shadow, live, capital, orders, fills, positions, a scheduler, readiness or connector
  transitions.
- **No value.** No number, default, policy artifact or approval-table entry is created.

## 7. Remaining lifecycle risks

> **Status: PENDING_HUMAN_DECISION** — recorded so that construction does not assume them away; advisory evidence only,
> with no force. Source: `FABLE52_S1_VIABILITY_ARCHITECTURE_REPORT_V1` (2026-11-16), a user-initiated,
> non-authoritative advisory: not a routed execution, not an independent audit and not a repository artifact. Its
> figures come from synthetic outcome models. They describe the rules; they are never a forecast, a real edge or a
> qualification.

| Id | Risk | Pending decision or dependency |
|---|---|---|
| LR-1 | Kelly absorption after class completion. Once coverage ends, a refusal that depends only on the sealed history cannot clear without a new trade, and no trade follows a refusal: f\* ≤ 0 (KD-6); a non-positive log-utility verification whose G-window R values do not sum to a positive number (KD-10c); five consecutive losing trades (T5 gives KS-1, which refuses the fixed unit under A9′). Under RECORD A with D-A1, in the advisory's five illustrative synthetic edges, these refusals and the covered failures of section 2.1 together end 46% to 99% of lineages before 50 closed trades. | V-1 of the advisory (not adopted) |
| LR-2 | Incubation bounds. Under the proposals A_max = 20 and T_max = 90 UTC days (companion §3.6, not values), with U2 needing 90 UTC days and U4 20 orders, the advisory found that every entry before day 90 stays on the incubation basis, so ordinary admission needs the A_max-th attempt inside a narrow window of days. | Items 1.4, 1.5 and 1.7 |
| LR-3 | Refusal instead of reduction. Under A9′ (companion §4.7) a proven multiplier below 1 refuses the fixed unit, so an edge-health dip (α_edge < 1 below EHS 0.70), a DECAY_ALERT or KS-1 stops trading. A 30-day window of zero own returns has zero variance and is BLOCKED (F-4; companion T-INC-12), so a fully idle window does not clear by itself. | FCD-13, HC-13a and item 1.8 |
| LR-4 | The 100-trade bootstrap is undecided: BLOCKED from 100 known closed trades in the window (KD-7). | The bootstrap method |
| LR-5 | Ordinary-phase Kelly. PRDV4 §1.28 refuses at f\* ≤ 0 on the α = 0.05 EWMA at every entry, so thin-margin edges are also absorbed after coverage ends. | Constitutional (§1.28); nothing proposed |
| LR-6 | Stage-4 route. LIMITED_S1_PAPER_V1 grants nothing for §1.13 Stages 4–5 (§1.20), and no route to Stage-4 credit is decided. | A separate authorization |
| LR-7 | Other gates: RECORD B adoption and implementation (FCD-01, FCD-02, FCD-03, FCD-08, FCD-10) with HZB-1; HD-07 calibration; FCD-13; C1–C9, including C2's H and the C7 governor thresholds; DEC-1; every X-* source. | Companion §12 |

**Not adopted.** This document adopts none of the advisory's proposals: V-1, V-2, V-3 and V-4; its Option 2 (a Kelly
minimum-sample window with an incubation loss budget); `N_K = 50`; `Lambda = 0.025`; `A_max = 270`; `T_max = 365` UTC
days; `A9''`. None is a value, a default or a proposal of this document. None enters a policy artifact or an approval
table, and no implementation reads one. Each would need its own human decision and a separate adoption change.

## 8. Pending decisions after this adoption

> **Status: REFERENCE** — every entry not marked decided stays PENDING_HUMAN_DECISION.

| Item | After this adoption |
|---|---|
| Companion item 1.3 (U5 boundary) | Replaced by A1.3 (section 2) |
| Companion items 5.1 and 5.2 (HC-16b) | Decided by A3, for construction only (section 5) |
| Companion §3.6, HD-K1 row | Superseded (section 3.1); coverage after the first closed trade exists only as the class-completion window of section 2 |
| Bootstrap at n_w = 100 | Pending; BLOCKED (KD-7) |
| HC-16a, HC-16c, HC-16d | Pending; mapping UNKNOWN |
| Items 1.4–1.8 (A_max, T_max, W_INC, the record, F-1..F-4) | Pending, unchanged |
| RECORD B, its selections, D-B1..D-B3 and HZB-1 | Human-approved per the controller, not adopted or implemented; outside this change |
| Every other entry of companion §12.1 and §12.2 | Unchanged |

## 9. Adoption verification matrix

> **Status: REFERENCE.**

### 9.1 Content binding

PRDV4 at the head of this change is:

- blob `f61965868b1b9bea109cdb409f59989f30e0a7d8`, 115,265 bytes;
- SHA-256 `2f80d336a0872cd4cd076ab5ae3ae8c1c9e2f773a3ab123f5d1bac55350c9698`.

Against the base blob `6f5ad9177ee30e6e52a9c20c5c23cc3b00f578b7` it changes three passages of §0.3 and §1.21 and
nothing else. A passage digest is SHA-256 over the UTF-8 bytes of the passage's lines at the head, joined by line
feeds, without a leading or trailing line feed.

| Item | PRDV4 location | Lines at the head | SHA-256 of the passage |
|---|---|---|---|
| A1.1 | §0.3, scoped cold-start exception | 51–54 | `f1bfdbdeda6bfa30ee7af5644e5b70030c4929ac1674b193639622ece19d1269` |
| A1.2, covered readings | §1.21 Exception Record, bullet 1 | 1319–1321 | `e313904617249160360f140a89ccd40e5a09774e327f9d63c18990f7d6fdcc79` |
| A1.2, Kelly coverage | §1.21 Exception Record, new bullet after bullet 2 | 1326–1335 | `3fa2f95a72965abded8c9b1654859083027559e1fc7a72722d2e41dfd2939504` |

### 9.2 Checks

| Id | Check | Required result |
|---|---|---|
| T-KCD-01 | PRDV4 §0.3 | The A1.1 sentence follows "instead of HOLD." once, word for word |
| T-KCD-02 | PRDV4 §1.21, bullet 1 | The A1.2 phrase replaces "while the edge has no closed governed-paper trade", which no longer occurs in PRDV4 |
| T-KCD-03 | PRDV4 §1.21, Kelly coverage | The bullet occurs once, right after bullet 2, with C-1; `1 + f*R` does not occur in PRDV4 |
| T-KCD-04 | Every other PRDV4 byte | Unchanged against the base blob |
| T-KCD-05 | The companion | Blob `d351b4fb0f92e03ab96e11f71708b733f9c3cb16`, unchanged |
| T-KCD-06 | Sections 2.1, 2.2, 4.1 and 5.1 | Word for word the approved texts, except the changes of section 1.3 |
| T-KCD-07 | Changed paths | Exactly PRDV4, this document and `docs/crypto_core/paper_trading_phase_map.md` |
| T-KCD-08 | Values | No item of section 7's not-adopted list is a value, default or proposal of this document |
| T-KCD-09 | Admission | No code, test, policy artifact or approval table changes |
