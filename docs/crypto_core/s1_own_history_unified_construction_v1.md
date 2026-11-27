# S1 own-history unified authority — construction record (`S1_OWN_HISTORY_UNIFIED_CONSTRUCTION_V1`)

Status: construction candidate on accepted main `7ef48bd7`. It is pending a protected independent audit, exact-head CI and
human merge authorization. It adds no policy artifact, approval-table entry, source qualification or admission path. It
admits no entry.

Design authority: the [own-history measurement adoption record](s1_own_history_measurement_doctrine_adoption_v1.md)
(`S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1`, D1–D7) and the
[own-history residual adoption record](s1_own_history_residual_doctrine_adoption_v1.md)
(`S1_OWN_HISTORY_RESIDUAL_METHOD_DECISION_V1`, P-1 to P-6, RD-1 to RD-15, the shared numerical and authority contract,
FA-1 to FA-19). These are read with PRDV4 §0.3, §1.5, §1.6, §1.7, §1.21 and §1.29, the approved companion §§3–4, and the
incubation records `r1` and `HD-INC-AUTH-1` `r2`. The phase map records this candidate in its section 23.

## 1. What is constructed

One engine and one authority. Every own-history fact is derived from the replay authority of the same governed re-run.
That authority is the authenticated economics result, its anchor and the governed outcome, whose schedule must be a
schedule v10. Nothing is ever accepted from a caller.

| Artifact | Version | Module |
|---|---|---|
| Admission schedule | `historical-execution-admission-schedule.v10`: schedule v9's fields, no new wire field | `historical_execution_economics.py` |
| Own-history evidence | `governed-paper-own-history-evidence.v1` | `governed_paper_own_history.py` (new) |
| Coverage claim | `governed-paper-own-history-coverage.v1` | `governed_paper_own_history.py` |
| Entry gate rule set | `governed-paper-entry-safety.v13` | `governed_paper_entry_safety.py` |
| Incubation evidence | `governed-paper-incubation-evidence.v2`: graduation on the U1–U4 coverage ends | `governed_paper_incubation_authority.py` |
| Sizing chain | rule `governed-paper-sizing-chain.v2`, evidence `governed-paper-sizing-evidence.v2` | `governed_paper_sizing_chain.py` |
| Decided allocation | `derive_governed_paper_allocation_decided` (exact comparisons, R-1 boundary) | `governed_paper_allocation_envelope.py` |
| Day seal, lineage evidence | `governed-paper-day-seal.v14`, `governed-paper-execution-evidence.v14` | `governed_admitted_variant_paper_execution.py` |

Every new artifact exists only in an opt-in lineage. An incubation lineage whose protection inputs carry an own-history
context does so from day 0 and never switches. Without that context, every v2–v13 seal and evidence, schedules v2–v9,
outcomes v2–v4 and entry rule sets v1–v12 stay byte-identical. World G's first two v13 seals, v9 schedules,
incubation, entry and Kelly evidence, governed outcomes and the v13 lineage evidence are pinned to their accepted-main
digests. Those digests were computed on a detached worktree of `7ef48bd7` before any change
(`test_governed_paper_own_history_lineage`).

## 2. Closure matrix

| Item | Producer | Supported consumer | Public verifier | Tests | Residual gates |
|---|---|---|---|---|---|
| C-1 valuation path | Engine schedule v10: NAV at every anchor and, while positioned, at every mark visibility and staleness instant, each with its knowledge instant (the final-rate visibility of every settlement booked so far) | S_drawdown, U1/U2 day boundaries, the state machine | The derivation re-runs the engine and rejects an unreproduced outcome | `test_drawdown_*`, `test_sharpe_*` | E-1 (M1 mark archive) |
| C-2 Sharpe_30d, Sharpe_90d | UTC day-boundary NAVs (a partial genesis day is never completed), latest 30/90 returns, sample variance, `sqrt(365)`; zero variance or non-positive NAV UNDEFINED; a day awaiting a publication UNPROVEN | EHS, DECAY_ALERT, DE-WEIGHT, the allocation reading, U1/U2 cuts | Same | `test_sharpe_*`, `test_decay_alert_*` | E-1; G-1 |
| C-3 signal | Exact mean of the decision's own latest N final rates, re-derived from its input record digests over the archive, for every scheduled evaluation | S_stability | Same; the run's verifier | `test_fa1_*`, `test_p1_*`, `test_stability_*` | E-1, E-2 |
| C-4 EHS and state machine | Exact surd EHS; knowledge-time state machine (start at the first fully defined EHS, 0.70/0.30, 48-hour recovery, QUARANTINE on the second episode inside `(t − 30d, t]`) | NT-E01, NT-E02, NT-E04, alpha_edge, the allocation reading | Same | `test_ehs_*`, `test_state_machine_*`, `test_state_check_*` | R-1, R-2, R-3, E-1, G-1 |
| C-5 submissions and fill rates | Engine schedule v10: each logical submission at the coordinate of the event that issued it, its run-independent identity and its resolution; FR_10 and FR_20 equal-weighted | NT-X02, FB-ACTIVATION (FR_20 ≤ 0.70 only), the activation input, U3/U4 cuts | Same | `test_fill_rate_*`, `test_rd11_*`, `test_rd12_*`, `test_fa8_*`–`test_fa12_*`, `test_starved_*` | E-1; X-H1 |
| C-6 coverage ends and incubation | Irreversible U1–U4 cuts (30/90 completed known days, 10/20 conclusively resolved submissions); incubation graduation at the latest of every selected reading's end, `S` and `P_A` | The incubation authority, the cold-start exception | The incubation verifier (evidence v2) | `test_coverage_ends_*`, `test_incubation_v13_*`, `test_starved_*` | E-3, the policy artifact, record approvals |
| C-7 entry gate, sizing, seal | Rule set v13, sizing chain v2, day seal v14 and lineage evidence v14 | The governed entry path | The seal and lineage-evidence verifiers; `verify_governed_paper_own_history_evidence` | `test_fa7_*`, `test_fa18_*`, `test_cold_start_*`, `test_scale_1_*`, `test_fb_activation_*`, `test_allocation_*`, the lineage tests | R-1; G-1; production approvals |

## 3. Readings and checks

Each reading is in one of D6's categories: DEFINED, INSUFFICIENT (proven insufficient own history), UNDEFINED (complete
but mathematically undefined) or UNPROVEN (missing or unproven). A defined reading yields a proven PASS or FAIL. Only an
INSUFFICIENT reading that is not failing under every completion is COVERED. It is `COLD_START_EXCEPTED` only under an
ACTIVE incubation record that selects every covered reading before its coverage ends. A proven FAIL dominates every
exception.

| Check | Reading | PASS | FAIL | COVERED | Otherwise |
|---|---|---|---|---|---|
| NT-E01 | EHS | EHS ≥ 0.30 | EHS < 0.30 | U1 insufficient only | BLOCKED |
| NT-E02 | State machine, after EF-8 | ACTIVE or WARNING with a defined EHS | A proven disable condition; DISABLED; QUARANTINE | STATE_NOT_ESTABLISHED on U1 alone, without a breach | BLOCKED |
| NT-E04 | EHS of the one-sleeve universe | EHS > 0.50 | EHS ≤ 0.50, or ≤ 0.50 under every completion | U1 insufficient only | BLOCKED |
| NT-X02 | FR_10 | FR_10 ≥ 0.50 | FR_10 < 0.50, or below under every completion | U3 insufficient | BLOCKED |
| FB-ACTIVATION | FR_20 execution column | Never (X-H1) | FR_20 ≤ 0.70, or at most 0.70 under every completion | — | BLOCKED |
| SCALE-1 alpha_edge | EHS ≥ 0.70 | Proven one | Proven below one | U1 insufficient only | Unproven |
| SCALE-1 DE-WEIGHT | DECAY_ALERT | Proven one | Proven below one | U1/U2 insufficient | Unproven |

The allocation reading of the genesis sleeve is taken at the latest rebalance: every UTC midnight and every proven state
transition. It is decided on exact comparisons by `derive_governed_paper_allocation_decided`. One proven member weighs
exactly 2/5. Two or more members are BLOCKED on R-1, and no general R-1 solution is constructed. Activation is never
PASS, so a proven NON_MEMBER is the only new outcome.

## 4. Implementation choices inside the adopted doctrine

1. Knowledge coordinates. Every fact sits at `(t, phase, native_sequence)` over the engine's unchanged equal-instant
   phases. A publication, a mark visibility and a time-defined instant take phase −1, before every engine phase of
   their instant. The genesis anchor precedes every other fact of its instant.
2. Completeness is uniform over `[G, t]`. Each reading needing complete own history needs the funding, mark and
   order-book series covered from G through t, by claims known at t and admitted by the active table. One unknown
   interval therefore leaves every later reading UNPROVEN. This is stricter than FA-4's "restarts when coverage
   resumes": no recovery is ever proven across a gap.
3. A disable condition that never becomes known keeps every later coordinate waiting. From STATE_NOT_ESTABLISHED, ACTIVE
   or WARNING the lifecycle is then LIFECYCLE_UNPROVEN, because a hidden DISABLED transition is possible. DISABLED and
   QUARANTINE stay proven, and DISABLED never recovers across it. A transition is dated at the coordinate where it
   becomes known, never earlier.
4. The X1 prefix of the own-history evidence holds only knowledge-stable content. It leaves out the horizon's
   still-pending lifecycle conditions, which a longer horizon may resolve.
5. A cold-start-excepted NT-D or NT-X status is read as `BLOCKED_ON_MISSING_INPUT` by the §1.29 system-state reading
   (S4, S5). It excepts the entry check only and never proves the signal healthy or active. Rule sets v1–v12 never
   produce that status for those checks.
6. Fill-time exposure envelopes stay the input-only derivation of the sizing chain v1. An envelope a later admission
   could change would enter the fixed point. With no reachable member, every exposure-increasing fill is refused
   either way.
7. The fixed point is unchanged. The refusals, the incubation bounds and the own-history readings of one evaluation
   settle together in at most `len(entries) + 2` evaluations, because each reading reads only the admissions before
   its decision.

## 5. Acceptance trace (FA-1 to FA-19)

Tests are in `tests/crypto_core/validation/test_governed_paper_own_history.py` (U) and
`tests/crypto_core/validation/test_governed_paper_own_history_lineage.py` (L).

| FA | Test |
|---|---|
| FA-1 | U `test_fa1_the_signal_population_is_every_scheduled_evaluation_not_only_the_entries`, `test_p1_*` |
| FA-2 | U `test_fa2_a_later_publication_never_rewrites_an_earlier_reading_or_prefix`, `test_x1_*`; L `test_a_claim_published_inside_day_2_never_rewrites_a_sealed_fact` |
| FA-3 | U `test_rd11_a_child_in_flight_at_a_decision_is_unresolved_there_and_its_remainder_follows_the_fill`, `test_fill_rate_*`, `test_hit_rate_*` |
| FA-4 | U `test_state_machine_recovery_needs_48_continuous_hours_and_restarts_on_every_interruption`, `test_state_machine_an_unknown_disable_condition_waits_and_its_transition_is_dated_when_known` |
| FA-5, FA-6 | U `test_state_machine_two_disable_episodes_within_30_days_enter_quarantine_which_is_never_released` |
| FA-7 | U `test_fa7_an_ef8_successor_refuses_whatever_the_own_history_state` |
| FA-8, FA-9 | U `test_fa8_and_fa9_*`, `test_rd11_a_child_refused_at_its_protective_admission_is_a_ledger_row_not_a_submission` |
| FA-10, FA-12 | U `test_fa10_and_fa12_a_pending_order_is_unknown_at_the_end_and_an_extension_keeps_its_identity` |
| FA-11 | U `test_fa11_a_close_only_order_divides_by_its_own_requested_quantity` |
| FA-13 | U `test_drawdown_a_stale_or_unknown_valuation_leaves_only_a_lower_bound_that_can_prove_fail_never_pass` |
| FA-14 | U `test_drawdown_exactly_5pct_breaches_inclusively_and_its_score_is_zero` |
| FA-15 | U `test_fa15_partial_fills_inside_one_excursion_are_one_trade` |
| FA-16, FA-17 | U `test_hit_rate_window_zero_net_neutral_knowledge_and_clipping` |
| FA-18 | U `test_fa18_a_proven_fail_refuses_the_entry_whatever_is_cold_start_excepted`, `test_d6_defined_pass_and_defined_fail_are_exact_and_a_proven_fail_is_never_covered` |
| FA-19 | L `test_the_accepted_v13_seals_v9_schedules_and_lineage_evidence_are_byte_identical`, with every accepted-identity test of the existing suite |

The PR450/PR452 regressions are rebuilt on the accepted synthetic lifecycle fixtures under the policy v2 and a schedule
v10. They cover a flatten child in flight at the DECISION instant `1641657631000000000` that fills 0.5 at that FILL,
with its 0.5 remainder submitted after the fill. They cover the v1 MAX_HOLD remainder attempt at `1641716131000000000`.
They also cover a child refused at its attempt-time protective admission, which is a ledger row and not a submission.

## 6. Reachability and what is not claimed

- No governed entry is reachable. World G refuses its one entry at NT-D01, and its 30-day horizon refuses every 91-day
  incubation record. SCALE-1's other terms are never proven, activation is never PASS (X-H1), and production
  completeness is never proven. No integrated positive admission is claimed. The long-horizon semantics are proven on
  SYNTHETIC derivation facts and on engine worlds of up to four days: the 30/90-day boundaries, the 10/20-submission
  cuts and the state machine.
- The engine's SHORT-to-LONG close-only clamp is unreachable for `passive_funding_carry.v1`, which never targets LONG.
  Every reachable close-only order divides by its own requested quantity.
- MEMBER and INCUBATION_MEMBER are unreachable, and QUARANTINE release is always BLOCKED (R-2, R-3).
- Non-claims: no production coverage, M1 source qualification or signal provenance qualification (E-2), and no venue
  health or X-H1 proof. Also none of: an approved release, an allocation for two or more members (R-1), readiness,
  profitability, an edge or Stage-4 credit. Every claim, record and history in the tests is synthetic. No test table
  is a production approval.

## 7. Residual gates

E-1 (M1 and the human coverage approvals); E-2; E-3 (A4–A6, O2); R-1; R-2; R-3; G-1 (C2's G and H,
`MONITORING_CADENCE`); X-H1; HD-07; NT-D01; C1–C9; D1; the incubation and own-history policy artifacts; record approvals;
REAL_PAPER_EXECUTION; Stage-4.

## 8. Validation

Targeted tests run through `scripts/crypto_core/run_logged_command.ps1`. Ruff check and format run on `src/crypto_core`,
`tests/crypto_core` and `scripts/crypto_core`. The full suite runs only through
`scripts/crypto_core/run_full_tests_logged.ps1`. The results bind to the exact head reported with the change.
