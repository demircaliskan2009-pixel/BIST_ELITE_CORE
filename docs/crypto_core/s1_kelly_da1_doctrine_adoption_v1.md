# S1 Kelly D-A1 Doctrine Adoption V1

> Adoption record of the human decision `S1_KELLY_DA1_DECISION_V1` of 2026-11-19 for the governed paper path of
> `LIMITED_S1_PAPER_V1`, contract `S1_KELLY_DA1_DOCTRINE_ADOPTION_V1`. It resolves the delta D-A1 to KD-9 of RECORD A
> (`docs/crypto_core/s1_kelly_class_completion_amendment_v1.md` section 5.2) by adopting the human-approved Kelly fit
> as Tier III construction methodology (section 2). It implements nothing and admits nothing: every governed S1 entry
> stays refused (section 6).

## 0. Status, source and reading rules

### 0.1 Status and effect

- **Adoption merge.** This document and its phase-map entry take effect together, and only when four things hold:
  this change has passed its own protected independent audit (GPT-6.1 Sol, `docs/crypto_core/agent_workflow.md`
  section 24.4) with exact-head CI; the human has authorized its standard merge by naming the pull request, its exact
  head and the merge command (section 24.5); that merge is done; and post-merge verification proves that `main` holds
  the changed files byte for byte as at that head. Until then this document has no force: the RECORD A amendment
  binds as written, D-A1 stays PENDING_HUMAN_DECISION and the Kelly fit of KD-9 stays not construction-ready.
- **Role.** This document holds the decision record (section 1), the adopted KD-9 (section 2) and the forward-only
  supersession of the passages that state D-A1 as pending (section 3). It adds no doctrine beyond the decision.
  Between this document and PRDV4, PRDV4 governs. Between this document and the RECORD A amendment, this document
  governs KD-9 and the status of D-A1 only, and every other text of the amendment binds as written. Between two
  safety rules the stricter one applies.
- **Tier.** III methodology: KD-9 as decided, for construction only, under `LIMITED_S1_PAPER_V1`. IV implementation:
  not authorized.
- **Forward-only.** No other doctrine document is edited: the RECORD A amendment, the RECORD B adoption document
  (`docs/crypto_core/s1_native_risk_measurement_doctrine_adoption_v1.md`), PRDV4 and the companion
  (`docs/crypto_core/s1_approved_doctrine_adoption_v1.md`) stay byte-identical, and the phase map only gains its
  section 16. From the adoption merge the passages of section 3.1 are superseded and keep no force; they stay in their
  documents as history, and nothing earlier is erased or re-dated.

### 0.2 Status blocks

Every heading below carries one status block, with the meanings of the RECORD A amendment section 0.2:

- **ADOPTED** — binding from the adoption merge, as written.
- **APPROVED_METHODOLOGY** — approved for construction only. It binds a later, separately authorized implementation
  contract and is not implemented; until then the accepted readings stay as they are.
- **PENDING_HUMAN_DECISION** — non-normative. No value, method, state or permission may be read, defaulted,
  implemented or admitted from it.
- **REFERENCE** — supporting record, index, analysis or acceptance criteria. It adds no rule.

### 0.3 Reading rules

- Section 1.2 reproduces the decision word for word, with its line breaks and its Markdown markers. Section 2.1
  reproduces the decision's KD-9 paragraph word for word; the only change is the removal of its four code markers
  (`` ` ``), which carry no words.
- `rho_t`, `R_j`, `Lbar`, `f_cap` and the KD-1 window keep their adopted meanings; section 2.2 cross-references them
  and adds no rule.
- Line references point into the blobs at the base of this change, `main` 7ba501050d40afb8fa71b1337fa021c353900488
  (section 7.1).
- Missing, unproven or unknown evidence stays BLOCKED or HOLD. No status block, quotation or verification row of
  this document is a permission.

## 1. Decision record

> **Status: REFERENCE** — the decision this document adopts.

### 1.1 Record

```text
DIRECT_HUMAN_DECISION_RECORD_V1
RECORD            S1_KELLY_DA1_DECISION_V1, given under the title HUMAN_GOVERNANCE_DECISION_RECORD_V1.
DATE              2026-11-19. No time of day is recorded.
GIVEN TO          The Claude Opus 5.5 implementation session of contract S1_KELLY_DA1_DOCTRINE_ADOPTION_V1, as a
                  message from the human. That session had stopped at its human-decision precheck because no direct
                  human decision existed, and had asked for one.
RELAYED BY        None. Section 1.2 reproduces that message line for line.
SUBJECT           Delta D-A1 to KD-9 of RECORD A (RECORD A amendment section 5.2), PENDING_HUMAN_DECISION on main
                  7ba501050d40afb8fa71b1337fa021c353900488 when the decision was given.
DECISION          D-A1 Alternative 1 approved for LIMITED_S1_PAPER_V1, as Tier III construction methodology only, in
                  the exact KD-9 wording of section 2.1. Alternative 2 not selected.
UNCHANGED         KD-0 risk units, FCD-01 methodology, KD-1..KD-8, KD-10..KD-13, PRDV4 constitutional rules and
                  generic multi-edge Kelly.
AUTHORIZES        A separate docs-only adoption proposal, subject to protected independent audit and separate
                  exact-head merge authorization.
NOT AUTHORIZED    Product implementation, policy activation, admission, real paper, live trading, orders, capital
                  mutation or merge.
APPROVER IDENTITY Not recorded (UNKNOWN).
SIGNATURE         None. The repository holds no signature, message identifier, message hash, session identifier or
                  permanent URL for this decision, and this record claims none.
BINDING ACT       The human's separate exact-head standard-merge authorization of this change.
```

### 1.2 Decision text

The decision as given, word for word with its line breaks:

```text
**HUMAN_GOVERNANCE_DECISION_RECORD_V1**

RECORD: `S1_KELLY_DA1_DECISION_V1`

DECISION: **I APPROVE D-A1 Alternative 1** for `LIMITED_S1_PAPER_V1`, as Tier III construction methodology only.

Approved KD-9:

`rho_t * max(1, Lbar) <= f_cap` at decision (R-4) and exposure-increasing fill (R-5), where `Lbar = mean_losses(abs(R_j))` over the KD-1 window. Otherwise FAIL, with no resize. Missing or invalid required evidence remains BLOCKED.

The existing KD-0 risk units, FCD-01 methodology, KD-1..KD-8, KD-10..KD-13, PRDV4 constitutional rules and generic multi-edge Kelly remain unchanged.

Alternative 2 is not selected.

This decision authorizes a separate docs-only adoption proposal, subject to protected independent audit and separate exact-head merge authorization. It does not authorize product implementation, policy activation, admission, real paper, live trading, orders, capital mutation or merge.
```

### 1.3 Source and authority

| Record | Class | Establishes | Does not establish | Quoted in |
|---|---|---|---|---|
| The decision of 2026-11-19 | Direct human decision | The selected variant of D-A1 (Alternative 1), the exact KD-9 wording, its Tier III scope and its authorization boundary | Implementation, policy activation, admission or merge | Sections 1.2 and 2.1 |
| D-A1 and its two alternatives: RECORD A amendment section 5.2, quoting `FABLE52_EXTERNAL_ADVISORY_REPORT_V1` (finding RT-4) | Historical advisory text, not authoritative | The two alternatives the decision chooses between | Any approval | Sections 2.2 and 2.3 |
| The controller packet of 2026-11-15 that lists D-A1 under `APPROVED_ADDITIONAL_DELTAS` | Controller relay, label only | That an item labelled D-A1 was relayed as approved | Which alternative was selected, or any wording (RECORD A amendment section 1.1) | RECORD A amendment section 1.1 |
| The controller's implementation packet of 2026-11-19 for this contract | Controller instruction | The docs-only scope, the allowed files and the branch, conditional on a direct human decision, which it stated as not yet proven | Any approval | Not quoted |
| The read-only analysis `S1_KELLY_DA1_ARCHITECTURE_DECISION_V1` of 2026-11-19 (the Claude lane; not a repository artifact) | Recommendation, not authoritative | Nothing: it recommended Alternative 1 and proposed a wording marked PROPOSED_NOT_APPROVED | Any approval | Not quoted |

### 1.4 Clause mapping

Each clause of the decision, with its Markdown markers removed, and where this document applies it:

| Clause of the decision | Applied in |
|---|---|
| "I APPROVE D-A1 Alternative 1 for LIMITED_S1_PAPER_V1, as Tier III construction methodology only." | Section 2: status APPROVED_METHODOLOGY, scope `LIMITED_S1_PAPER_V1`; section 3.1 resolves D-A1 |
| "Approved KD-9:" and the paragraph that follows it | Section 2.1, word for word |
| "The existing KD-0 risk units, FCD-01 methodology, KD-1..KD-8, KD-10..KD-13, PRDV4 constitutional rules and generic multi-edge Kelly remain unchanged." | Section 3.3 |
| "Alternative 2 is not selected." | Section 2.3 |
| "This decision authorizes a separate docs-only adoption proposal, subject to protected independent audit and separate exact-head merge authorization." | Section 0.1, adoption merge; this change is that proposal |
| "It does not authorize product implementation, policy activation, admission, real paper, live trading, orders, capital mutation or merge." | Section 6 |

### 1.5 Forward-only provenance

The decision is recorded as given on 2026-11-19 and is not backdated. It does not establish that Alternative 1 was
approved in this wording on 2026-11-15: the relay of that date stays a label-only relay, and the RECORD A amendment's
statement that the variant was UNPROVEN at its adoption stays true for that time.

## 2. KD-9 — the Kelly fit (D-A1 resolved)

> **Status: APPROVED_METHODOLOGY** — for construction only, under `LIMITED_S1_PAPER_V1`, from the adoption merge. Not
> implemented: every accepted rule set, schedule, seal and module stays unchanged, and the accepted SCALE-1 reading
> keeps the Kelly fit unproven (`src/crypto_core/validation/governed_paper_entry_safety.py:1695`) until a separately
> authorized implementation contract builds RECORD A's methodology with this KD-9.

### 2.1 Text

The approved KD-9, the decision's paragraph word for word without its code markers:

```text
rho_t * max(1, Lbar) <= f_cap at decision (R-4) and exposure-increasing fill (R-5), where Lbar = mean_losses(abs(R_j)) over the KD-1 window. Otherwise FAIL, with no resize. Missing or invalid required evidence remains BLOCKED.
```

From the adoption merge this text is KD-9 of `KELLY_DEFINED_READING_V3` (RECORD A amendment section 5.1) and
replaces the RECORD A wording quoted in section 3.1. KD-12 keeps its wording, and its "KD-9 holds" reads this text.

### 2.2 Reading notes

> **Status: REFERENCE** — cross-references only; section 2.1 and the cited sections govern.

- **Notation.** `rho_t` is the candidate's actual FCD-01 stop-risk fraction: R-4 at the decision, R-5 at the
  exposure-increasing fill (KD-0 with C-1; RECORD B adoption document section 3.1). `R_j` is KD-0's realized net
  PnL_j / Risk_j, with Risk_j the FCD-01 R-5 risk amount of trade j's position at its opening fill, recomputed by the
  verifier (KD-0, KD-10a). The KD-1 window is the latest n_w = min(n, 100) known closed trades (KD-1). `f_cap` is
  KD-8's min(f, 0.04).
- **Lbar.** `mean_losses(abs(R_j))` is the mean of abs(R_j) over the window's losses (realized net PnL < 0, A1.3):
  the quantity that KD-5 writes `mean_losses(|R|)`, unweighted, as the denominator of b. Zero trades are not losses
  and never enter it (KD-2). A defined reading holds at least one loss (KD-3), so Lbar is defined whenever KD-9 is
  evaluated.
- **Alternative 1.** The decision approves Alternative 1, quoted in the RECORD A amendment section 5.2 as
  `rho*max(1, Lbar) <= f_cap, with Lbar = mean_losses(|R|) of the KD-1 window`. The approved wording states it in
  KD-0's notation (`rho_t` for rho, as C-1 reads every rho; `abs(R_j)` for |R|), with RECORD A's instants R-4 and
  R-5, its FAIL with no resize and C-2's BLOCKED rule.
- **Strictness.** Since max(1, Lbar) >= 1, a KD-9 PASS implies KD-0's `rho_t <= min(f, 0.04)` at the same instant,
  and KD-9 never admits an entry that RECORD A's wording would refuse. NT-R03 (`rho <= 0.04`, RECORD B R-5 and R-7),
  KD-0 and KD-13 still bind on their own; none relaxes another.
- **Equality.** `<=` admits equality. The methodology's arithmetic convention is KD-10e's: exact rationals from the
  engine's exact values, never renderings.
- **Coverage.** While U5 covers the reading, f_cap is a covered component (A1.3), so KD-9 is not evaluated and KD-13
  applies unchanged. KD-9 binds once the reading is defined (KD-3).
- **Not claimed.** KD-9 is a conservative fit constraint. This document does not claim that it equals the
  growth-optimal or the quarter-Kelly stop-risk fraction of an arbitrary empirical outcome distribution.

### 2.3 Not selected

> **Status: REFERENCE** — historical text with no operative authority.

Alternative 2, quoted from the RECORD A amendment section 5.2:

```text
Alternative 2: Kelly stake = entry-price-to-stop plus exit cost, leaving FCD-01's NT-R03 measure unchanged.
```

Alternative 2 is NOT_SELECTED: it has no force, is no default and no fallback, and no implementation reads it. The
quoted text of Alternative 1 has no force either; Alternative 1 binds only in the wording of section 2.1.

## 3. Forward-only supersession and unchanged doctrine

> **Status: ADOPTED** — binding from the adoption merge.

### 3.1 Superseded passages

From the adoption merge these passages of the RECORD A amendment (blob `e0da520c`) are superseded and keep no force.
The amendment is not edited.

| Amendment passage | Lines | Status before | From the adoption merge |
|---|---|---|---|
| Section 0.1, "Tiers": the D-A1 clause only | 24–25 | Status and effect | D-A1 is decided; Tier III holds KD-9 as section 2.1 |
| Section 5, status block: the D-A1 sentences | 279–281 | APPROVED_METHODOLOGY | The Kelly fit of KD-9 is construction-ready as methodology; KD-12 can PASS only through a separately authorized implementation (section 4) |
| Section 5.1, KD-9 | 295 | APPROVED_METHODOLOGY | Replaced by section 2.1 |
| Section 5.2, the whole subsection as a pending item | 320–342 | PENDING_HUMAN_DECISION | Resolved by the decision of section 1; its quotations stay as history (section 2.3) |
| Section 5.3, the D-A1 bullet | 351–352 | APPROVED_METHODOLOGY (section 5) | Resolved |

The superseded text, quoted from blob `e0da520c` (line, then text; for section 5.2 its heading, status block and
bullets):

```text
  24    written in RECORD A, approved for construction only; the exact variant of the relayed delta D-A1 is
  25    PENDING_HUMAN_DECISION (section 5.2). IV implementation: not authorized.

 279  > The Kelly fit of KD-9 is not construction-ready while the exact variant of the relayed delta D-A1 is pending
 280  > (section 5.2): no implementation builds either alternative of section 5.2, or KD-9's RECORD A wording alone, as a
 281  > final Kelly fit. KD-12 needs KD-9 to hold, so it cannot PASS until a human decision resolves D-A1.

 295  KD-9 Kelly fit: rho <= f_cap at decision (R-4) and at fill (R-5); otherwise FAIL (no resize).

 320  ### 5.2 Delta D-A1 — exact variant pending
 322  > **Status: PENDING_HUMAN_DECISION** — no force. Nothing in this subsection is approved methodology, a default or a
 323  > fallback, and no implementation reads it.
 337  - **Neither alternative is approved.** Neither is adopted, a default or a fallback, and this document selects neither.
 338  - **While pending.** No implementation builds either alternative, or KD-9's RECORD A wording alone, as a final Kelly
 339    fit; the Kelly fit of KD-9 is not construction-ready, and KD-12 cannot PASS (section 5). The adopted KD-0
 340    requirements of section 4.1 are unchanged.
 341  - **Resolution.** Only a later human decision that records the selected variant in exact text resolves this item,
 342    through its own adoption change.

 351  - **D-A1.** The exact variant of the relayed delta to KD-9 is PENDING_HUMAN_DECISION (section 5.2). Until a human
 352    decision records it, the Kelly fit of KD-9 is not construction-ready.
```

### 3.2 Passages not superseded

These passages state D-A1 as pending or relay its label. Each records its own time, none has force against section
2, and none is edited.

| Document (blob) | Lines | Status | What it states |
|---|---|---|---|
| RECORD A amendment (`e0da520c`) | 69–72, 76 | REFERENCE (section 1.1) | The 2026-11-15 label relay; the variant UNPROVEN at that adoption |
| RECORD A amendment (`e0da520c`) | 118–120 | REFERENCE (section 1.3) | KD-9 and KD-12 keep their RECORD A wording; the variant pending |
| RECORD A amendment (`e0da520c`) | 264–265 | REFERENCE (section 4.2) | KD-9 and a KD-12 PASS not construction-ready while D-A1 is pending |
| RECORD A amendment (`e0da520c`) | 402 | REFERENCE (section 8) | D-A1 pending |
| RECORD B adoption document (`454d6922`) | 100, 115 | Decision record (section 1.1) | The label relay; RECORD A and D-A1 outside RECORD B |
| RECORD B adoption document (`454d6922`) | 298 | Decision record (section 1.3) | D-A1 outside the D-B decision and pending |
| RECORD B adoption document (`454d6922`) | 671 | REFERENCE (section 10) | R-8's later dependency "D-A1 for KD-9" |
| RECORD B adoption document (`454d6922`) | 705–706 | REFERENCE (section 11) | B1 selects no D-A1 alternative; the variant pending |
| RECORD B adoption document (`454d6922`) | 780 | REFERENCE (section 13) | D-A1 pending |
| Phase map (`2bbf1702`) | 577–578, 607, 648 | Dated records (sections 13–15) | D-A1 pending at those dates |

Two source references are outside this docs-only change and stay unchanged: `GOVERNED_PAPER_RISK_PENDING_ITEMS` lists
"D-A1" among the items that module never reads (`src/crypto_core/validation/governed_paper_risk_measurement.py:200-201`),
and SCALE-1 keeps its Kelly-fit term unproven (`src/crypto_core/validation/governed_paper_entry_safety.py:1695`).
Neither reads KD-9; a later, separately authorized implementation contract decides any change to them.

### 3.3 Unchanged doctrine

As the decision states, these stay unchanged: KD-0 with C-1 and C-2 (RECORD A amendment section 4.1); FCD-01,
R-1..R-8 (RECORD B adoption document section 3.1); KD-1..KD-8 and KD-10..KD-13 (RECORD A amendment section 5.1);
A1.1–A1.3 (PRDV4 §0.3 and §1.21; RECORD A amendment section 2); PRDV4, including the generic and portfolio
(multi-edge) Kelly of §1.28; RECORD B; and the companion.

## 4. Effect on KD-12 and on admission

> **Status: REFERENCE.**

- KD-9 is construction-ready as methodology. KD-12 can PASS only through a separately authorized implementation
  contract with its own protected audit; nothing here implements it.
- Every Kelly reading stays BLOCKED today. The production risk table admits no risk policy and no archive is
  M1-qualified, so no FCD-01 risk evidence exists in production (KD-0, C-2; phase map section 15). No
  PAPER_INCUBATION_V1 record can be ACTIVE (companion items 1.4–1.7), so U5 covers nothing. The reading is BLOCKED
  once the window holds 100 known closed trades (KD-7).
- SCALE-1 under A9′ keeps the Kelly fit unproven, so every governed S1 entry stays refused.

## 5. Pending decisions and gates after this adoption

> **Status: REFERENCE** — every entry not marked decided stays PENDING_HUMAN_DECISION or BLOCKED.

| Item | After this adoption |
|---|---|
| D-A1 | Decided (section 1); binding only from the adoption merge |
| Construction of KD-1..KD-13 with this KD-9 | Not authorized; needs a separately authorized implementation contract and its own protected audit |
| The 100-trade bootstrap (KD-7) | Pending; BLOCKED at n_w = 100 |
| HC-16a, HC-16c, HC-16d | Pending; mapping UNKNOWN |
| Incubation: companion items 1.4–1.8 | Pending; no ACTIVE record, so no U5 coverage |
| RECORD B's pending items | D-B2's alternative depth definition, D-B4, D-B5, FCD-17 and H^(e), MONITORING_CADENCE, FCD-05, FCD-13, FCD-14 and HD-07: pending (RECORD B adoption document section 13) |
| Source and venue gates | M1 source qualification, D1 venue facts and risk-policy production approval: pending; production readings BLOCKED |
| C1–C9 and DEC-1 | Pending, unchanged |
| Lifecycle risks LR-1..LR-7 (RECORD A amendment section 7) | Unchanged |
| REAL_PAPER_EXECUTION and Stage-4 | BLOCKED, not authorized |

## 6. Non-claims and admission effect

> **Status: REFERENCE.**

- **Admission effect: none.** This change edits no code, test, policy artifact, approval table, workflow or host
  adapter. Every governed S1 entry stays refused.
- **Not claimed:** that KD-9 equals the growth-optimal or the quarter-Kelly fraction of an arbitrary empirical
  distribution (section 2.2); Kelly survival, class completion or ordinary admission; Stage-4 eligibility or credit;
  real-paper readiness; profitability or edge.
- **No authority** for product implementation, policy activation, admission, real paper, shadow, live trading,
  orders, fills, positions, capital, a scheduler, readiness or connector transitions, or merge.
- **No value.** No number, default, policy artifact or approval-table entry is created; the 1 of `max(1, Lbar)` and
  the 0.04 of f_cap are adopted text, not new parameters.

## 7. Adoption verification matrix

> **Status: REFERENCE.**

### 7.1 Content binding

The base of this change is `main` 7ba501050d40afb8fa71b1337fa021c353900488 (tree
e37662c1cb1b9b25ccc19579000b7ce0336826dc).

| File | Base blob | At the head of this change |
|---|---|---|
| `docs/PRDV4_MULTI_MARKET_CRYPTO.md` | `455cdc1c988ad2d4af2767f0233c4e9cc6406316` | Unchanged |
| `docs/crypto_core/s1_kelly_class_completion_amendment_v1.md` | `e0da520c0291e397e0499329bd452455809f8e83` | Unchanged |
| `docs/crypto_core/s1_native_risk_measurement_doctrine_adoption_v1.md` | `454d69225ffb826806856bd1d4169ec5a3dcdd57` | Unchanged |
| `docs/crypto_core/s1_approved_doctrine_adoption_v1.md` | `d351b4fb0f92e03ab96e11f71708b733f9c3cb16` | Unchanged |
| `docs/crypto_core/paper_trading_phase_map.md` | `2bbf170298d388cf0fa3353142811ef2cc16374f` | `b42d77b7de12a95afdae8cce2dd2a1440f3927e0`: the base bytes, then section 16 |

### 7.2 Checks

| Id | Check | Required result |
|---|---|---|
| T-KDA-01 | Section 1.2 | The decision word for word, with its line breaks and Markdown markers |
| T-KDA-02 | Section 2.1 | The decision's KD-9 paragraph word for word, with only its four code markers removed |
| T-KDA-03 | Section 1.4 | Each quoted clause occurs in the decision once its Markdown markers are removed |
| T-KDA-04 | Section 3.1 quotations | Byte-identical to the cited lines of blob `e0da520c` |
| T-KDA-05 | RECORD A amendment, RECORD B adoption document, PRDV4, companion | Base blobs, unchanged |
| T-KDA-06 | Phase map | The base blob's bytes are an exact prefix of the head's; only section 16 is added |
| T-KDA-07 | Changed paths | Exactly this document and the phase map |
| T-KDA-08 | Code, tests, policy artifacts, approval tables, workflow and host adapters | Unchanged |
| T-KDA-09 | Values | No new number, default, policy artifact or approval-table entry |
| T-KDA-10 | Alternative 2 | NOT_SELECTED; quoted only as history (section 2.3) |
