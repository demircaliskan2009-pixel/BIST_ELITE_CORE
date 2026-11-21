# S1 paper incubation doctrine adoption V1

## Decision and effect

The human approved `S1_PAPER_INCUBATION_DECISION_PACKET_V1`, revision `r1`, on 2026-11-21 in the controller
conversation. The controller relayed that decision and its five items in the implementation contract
`S1_PAPER_INCUBATION_DOCTRINE_ADOPTION_V1`. The approval covers docs-only adoption for one edge of one
`LIMITED_S1_PAPER_V1` lineage. The relay supplies the date. The exact approval instant, a signature and a
signed-message digest are unknown.

This record and its phase-map entry acquire doctrine authority prospectively after protected independent audit and
required exact-head CI, the human's separate exact-head standard-merge authorization, the merge and post-merge
verification of the accepted bytes. Until then the accepted main governs. Adoption supplies bounded methodology for
a separately authorized construction. Every approved number needs exactly one digest-bound policy artifact and its
applicable separate approval before use. Changing a value requires a new version and digest. This document is a
decision record. Production has no approved incubation record or risk-policy digest through this adoption.

| Item | Decision in r1 | Accepted authority applied |
|---|---|---|
| 1.4 | `A_max = 21` admitted incubation entry attempts per immutable lineage–edge record | [Companion] §§3.5–3.6 and [PRDV4] §1.21 |
| 1.5 | `T_max = 91` UTC days, conditional on the approved lineage horizon | [Companion] §§3.1–3.2, 3.6 and [Governance] §6a, C2 |
| 1.6 | `W_INC = 0.08` of verified publication-visible NAV for an eligible incubation member | [Companion] §§4.1, 4.5–4.7, `ALLOCATION_ENVELOPE_V1` |
| 1.7 | Adopt the bounded `PAPER_INCUBATION_RECORD_V1` schema, lifecycle, verification, evaluation and reachability methodology | [Companion] §§3.1–3.2 and 3.4–3.7, subject to r1's values and [RECORD A] §2.1 for U5 |
| 1.8 | Acknowledge F-1 through F-4 under the conditions below | [Companion] §§3.3, 3.7 and 4.7, [RECORD A] §§2.1 and 3, and [PRDV4] §§0.3 and 1.21 |

This is a forward-only disposition of the five pending rows in companion §11.2. Earlier pending tables and proposals
retain their meaning at their own dates. In particular, the examples in companion §3.6 supply no defaults. RECORD A
had already superseded the first-closed-trade wording throughout the companion, including §§3.3, 3.5, 3.6, 3.7 and
8.2. The [D-A1 decision] governs the defined KD-9 fit. PRDV4 governs the constitutional exception and the stricter
applicable safety bound governs each evaluation.

## The record and its approval

Use the supplied fields and public serialization in companion §3.1. The verifier recomputes SHA-256 over canonical
record bytes and rejects a mismatch before granting any basis. The digest excludes the self-digest, derived end and
separate approval.

| Bound input | Verification |
|---|---|
| Schema and lineage | Exact `PAPER_INCUBATION_RECORD_V1`, sealed genesis identity and digest, genesis instant `G`, approved bootstrap horizon `H` and `LIMITED_S1_PAPER_V1` scope. Recompute the lineage binding from the seal. |
| Edge and validation | Match the exact edge, strategy-spec and parameter digests to the executed candidate. Verify the EF-5 preregistration sealed before the result, the EF-7 v2 PASS decision digest and the trial-count chain head. Recompute the evidence digests and re-prove currentness at every decision. |
| Coverage | The human selects a nonempty subset of U1–U5 for this record. Their original windows and exclusions govern U1–U4. RECORD A governs U5. Membership in the closed list alone grants no exception. |
| Bounds and start | Bind the approved attempt and duration bounds and UTC start `S`. Require the separate approval instant at or before `S` and `S + T_max <= G + H`. Derive `X = min(S + T_max, G + H)`. Missing C2 authority or an insufficient horizon refuses the record. |
| Separate approval | A `HUMAN_GOVERNANCE` approval names the exact recomputed record digest and carries the approver identity, approval instant and digest of the signed decision record. Verify its separate production approval-table entry. The approval of r1 cannot serve as the approval of an individual record. |

At most one record may exist for a lineage–edge pair, ever. Count only verified, publication-visible own-history
observations from the sealed, digest-chained lineage, keyed by lineage and sequence. Replaying that chain reproduces
the same counts. A duplicate or out-of-order observation terminates the record. A second approved record for the
same key terminates both. Backtests, another lineage and synthetic or unauthenticated fills cannot add history.

## Lifecycle and admission

| State | Condition and effect |
|---|---|
| `NOT_ESTABLISHED` | No verified record, or the instant precedes `S`. There is no incubation basis. |
| `ACTIVE` | Verification and approval hold, the record has not been revoked, `S <= t < X`, and fewer than 21 attempts have been admitted. Each new decision must satisfy the coverage and entry rules below. |
| `GRADUATED` | Coverage ended for every selected reading before the bound. All subsequent readings use ordinary rules. |
| `EXPIRED_HOLD` | The end instant or final admitted attempt is reached with coverage incomplete. No further incubation entry is eligible. |
| `REVOKED` | A verified human revocation ends the basis. |
| `TERMINATED` | Verification fails, including forgery, invalid approval, loss of validation currentness, wrong lineage, duplicate records or invalid observation sequence. |

The last four states are final. Per-reading completion is irreversible, including when a later window becomes
undefined. Expiry, revocation, termination and replay preserve negative evidence and the attempt count. No state
transition itself closes a position. Protective rules continue under their own authority.

Count one attempt when an entry is **admitted on the incubation basis**, even if it never fills. A refusal, exit or
protective action consumes none. With 20 attempts already counted, one further admission can consume attempt 21 if
every other condition holds. At 21 there is no further attempt. Attempt count proves neither a fill nor completion
of a fill-rate window.

A defined reading follows its ordinary rule. A proven FAIL dominates, including a check that fails under every
completion of the missing history. Only eligible missing own history can yield `COLD_START_EXCEPTED`, and only for a
selected reading under an ACTIVE record when all its non-history components pass. Other unresolved evidence is
BLOCKED. Incubation admission requires at least one such exception and every other check PASS or
PROVEN_NOT_APPLICABLE. The decision records the separate incubation basis and record digest. An exception supplies
no ordinary PASS or Stage-4 evidence.

## Incubation-member exposure envelope

Apply companion §4.1 eligibility first. `INCUBATION_MEMBER` requires exactly one candidate, U4 as the only non-PASS
leg of activation and U1 as the only undefined input to edge health. Both must qualify as `COLD_START_EXCEPTED`. For
exposure increases, apply §4.6 at the decision and again at the fill using verified NAV at each instant.

| Instant | Exposure tested against `0.08 × B`, where `B` is publication-visible NAV |
|---|---|
| Decision | `abs(q_pre) × mark(t) + u × L_k` |
| Fill | `abs(q_post) × mark(t_f)` |

For an eligible incubation member, proven usage at or below the envelope yields the companion's
`COLD_START_EXCEPTED` envelope result. A proven breach at either instant is FAIL. Missing NAV or usage is BLOCKED.
Equality satisfies only this comparison. All stricter bounds and state reductions still apply. Refuse the whole
fixed unit on a breach, including a fill-time breach after a decision fit. Exits and protective actions follow their
own rules. FCD-01 separately measures risk at the stop and Kelly uses its verified risk fraction. The exposure
envelope supplies neither quantity.

## F-1 through F-4 and boundary checks

| Item | Binding decision |
|---|---|
| F-1 · Calibration | Calibration is outside coverage. Pending HD-07 or missing proof of calibration blocks admission. |
| F-2 · Exchange health | Exchange health is outside coverage. Missing qualified X-H1 evidence or a required latency, API or maintenance proof blocks admission. |
| F-3 · Kelly | Apply `KELLY_CLASS_COMPLETION_WINDOW_V1`. Under an ACTIVE record selecting U5, only eligible components undefined solely for missing own history can be covered. At the first known closed win **and** known closed loss coverage ends permanently. Count a closed excursion only when its closing fill and all carried funding settlements are known under RECORD A. A zero-net trade counts but completes neither class. |
| F-4 · Sharpe | A full zero-variance Sharpe window remains BLOCKED pending an approved HC-13a convention. Incubation provides no epsilon, substitute history or score. |

| Boundary | Required outcome |
|---|---|
| No approved record, unauthenticated approval, changed bytes, replay after revocation | No incubation basis. A failed verification terminates the record under evaluation. Replay cannot restore authority. |
| At `S`, just before `X`, and at `X` | The first two instants can be ACTIVE only if all other conditions hold. At `X` the basis has ended. A 90-day U2 history first known on or after expiry cannot graduate the record retroactively. Late, invalid or insufficient observations can prevent graduation throughout the 91 days. |
| `S + 91 UTC days > G + H` | Refuse establishment. There is no shortened substitute, grace period or retrospective extension. C2 must independently establish both G and H. |
| Win-only, loss-only or zero-net history | Class completion has not occurred. RECORD A's KD-13 restrictions still apply. Solvency is tested from the first known trade at actual FCD-01 stop risk. Require the proven stop-risk cap and every required risk basis. From the first known trade each `1 + rho_t * R_j` must be positive. At two or more known G-window trades, the exact product must exceed one. A proven non-positive Kelly, domain ruin, non-positive required utility or proven cap breach is FAIL. |
| First known win and loss, or a closed trade awaiting publication | At class completion evaluate Kelly ordinarily, even if the result refuses entry. An unpublished outcome, unverified risk basis, unsupported outcome or unapproved method blocks the affected reading. A proven FAIL elsewhere still dominates. |
| Covered missing history alongside an ordinary refusal | Market-data integrity, CVaR, exchange health, calibration, margin, liquidation, capacity and protective obligations stay outside coverage. A proven failure refuses entry. A missing source or production risk-policy approval blocks it. The full companion §3.3 exclusion list applies. |

## Outstanding decisions and execution boundary

KD-7 at exactly `n_w = 100` remains BLOCKED on the undecided bootstrap. HC-16a/c/d have no approved mapping. FCD-17
and `H^(e)` remain pending, leaving edge and marginal CVaR blocked. M1 source qualification, D1 venue facts,
production risk-policy approval, C1–C9 including G/H, DEC-1 close-only authority, HD-07, HC-13a and the other open
FCD/HC choices keep their own gates. Hourly monitoring between decisions is unmeasured pending `MONITORING_CADENCE`;
the [native risk record] also preserves the C-18 de-risk obligation boundary.

This adoption creates no policy artifact, production table entry, ACTIVE record or executable behavior. With no
ACTIVE record, the first entry's empty own-history window still refuses it. The production risk table independently
admits no policy. Real paper execution (`REAL_PAPER_EXECUTION`) and Stage-4 remain blocked. Historical decision
tables, seals and artifacts retain their original bytes and authority.

[Companion]: s1_approved_doctrine_adoption_v1.md
[PRDV4]: ../PRDV4_MULTI_MARKET_CRYPTO.md
[Governance]: governance_decision_framework.md
[RECORD A]: s1_kelly_class_completion_amendment_v1.md
[D-A1 decision]: s1_kelly_da1_doctrine_adoption_v1.md
[native risk record]: s1_native_risk_measurement_doctrine_adoption_v1.md
