# Stage-4 Completion Decision v3 — Invariant Skeleton (Fable-authored, 2026-07-08)

Status: PRE-DESIGN SKELETON. v3 is the ONLY artifact that may ever set
`prdv4_stage4_complete=True`. This skeleton pins the invariants that are INDEPENDENT of MT/SM
implementation details, so the final v3 design does not depend on any particular model being
available — any §21 lane can complete it when its inputs exist. Nothing here authorizes
implementation; v3 has its own design → Codex audit → council → human authorization path.

## 1. Preconditions (ALL must be merged, READY, and digest-proven before v3 design finalizes)

1. `PaperStage4CompletionDecisionV2` — the blocked predecessor v3 consumes.
2. MT chain complete: `machine_proven_thirty_day_gate_decision` (MT-6) — machine-proven >= 30
   consecutive UTC days (sandwich + quorum + spacing), same market/correlation as the chain.
3. SM chain complete: `paper_stage4_comparison_evidence_v2` (SM-6) — comparison with REAL
   enforced hit/fill/slippage (None → REJECTED), methodology v2 with `*_enforced=True` bound to
   approved governance numbers.

## 2. Fixed v3 invariants (implementation-independent)

- v3 consumes v2 as predecessor with the SAME field-by-field continuity discipline v2 applies to
  v1 (verified_* recompute equality; blocker-tuple exactness; completion-flag reseal defense).
- v3's completion condition is structural, not judgmental: `prdv4_stage4_complete=True` requires
  EVERY v2 blocker to be discharged by a NAMED merged artifact —
  `operator_attested_only_machine_time_origin_unproven` → discharged only by MT-6 READY+satisfied;
  `timestamp_origin_not_proven_injected_deterministic_time_only` → discharged only by MT-5/MT-6
  machine-time origin proof over the SAME evidence window;
  `secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1` → discharged only by
  SM-5/SM-6 enforced methodology + comparison.
- Discharge is digest-bound: v3 carries (blocker, discharging_artifact_digest) pairs; a blocker
  without a verified discharger → v3 stays BLOCKED (READY + BLOCKED remains a valid outcome).
- Window identity: the MT-proven 30-day window, the SM-enforced comparison window, and the v2
  return-series window must be THE SAME UTC day-index range (day-index equality, not overlap).
- All non-completion overclaim flags (live/shadow/Deribit/readiness/orders/capital/edge/
  profitability) remain structurally False EVEN WHEN completion=True — Stage-4 completion is a
  methodology milestone, not a trading authorization.
- Process gates: v3 design gets a Codex design audit; v3 PR gets the 3-step council review
  (internal council + Codex + connector) and EXPLICIT human authorization naming v3; no standing
  authorization may cover it.

## 3. What v3 may NOT do (structural)

No comparator re-run; no new metric computation (it consumes proven evidence only); no attestation
fallback (if MT evidence is missing, v3 cannot substitute #319's attested gate); no partial
completion (no "complete except X" verdict — blockers are discharged fully or completion stays
False); no readiness/live semantics of any kind.

## 4. Open items deferred to v3 final design (post-MT/SM)

Exact anchored-input list (superset of v2's 8 + MT-6 + SM-6 + their policies); council evidence
format; completion-record retention/archival; whether v2 stays the terminal blocked record or is
re-rendered under v3 schema. These need MT/SM final shapes — deferring them is deliberate, not a
gap.
