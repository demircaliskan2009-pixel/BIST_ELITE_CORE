# Edge Factory (EF) — 7-Gate Design Contract (Fable-authored, 2026-07-08)

Status: DESIGN ONLY. Purpose: the idea→spec→admission→kill pipeline every future edge candidate
must pass. No candidate trades paper capital without surviving all gates; most candidates SHOULD
die here — that is the design working, not failing. Module namespace: `edge_*` under
`src/crypto_core/validation/` (avoids collision with existing `edge/` runtime package).

## 1. Gate sequence (EF-2..EF-8, one artifact per slice)

1. **EF-2 `edge_idea_intake_evidence.py`**: hypothesis record — edge family, economic rationale,
   data requirements, external-fact needs (DR triggers), kill-criteria DRAFT, declared regime
   dependence. The intake digest is the ROOT ANCHOR every later gate carries.
2. **EF-3 `edge_source_packet_evidence.py`**: PIT-grade data manifest — every input series with
   event_time/available_at/finalized_at semantics (pattern: `data/requirements.py` FUNDING_RATE),
   rights/licensing status, revision policy. No unfinalized series may feed features.
3. **EF-4 `edge_strategy_spec_admission.py`**: binds a validated `StrategySpec`
   (`strategy/spec.py`) to the intake + packet; market universe ⊆ packet coverage;
   `expected_regime` expressed against the pinned RF label enum (once RF exists — pending pattern
   until then); kill-criteria SUPERSET check (spec may only strengthen the draft).
4. **EF-5 `edge_leakage_bias_evidence.py`**: preregistration ledger — pinned feature set,
   parameter search bounds, label/threshold structures BEFORE any performance is seen; the
   multiple-testing counter (every tried variant is a ledger entry); lookahead/repaint/survivorship
   checks recorded as explicit proofs, not prose.
5. **EF-6 `edge_walk_forward_oos_evidence.py`**: replay/OOS/walk-forward results (consumes
   `walk_forward.py` window contract); re-proves the FULL back-chain (intake→packet→spec→ledger
   digests); regime_split_report field (digest-bound `regime_evidence_unavailable` until RF chain
   merges — never silently absent); costs/funding/slippage included per pilot rules.
6. **EF-7 `edge_paper_admission_decision.py`**: the sleeve-entry gate — all prior gates READY with
   passing verdicts; kill-criteria SEALED (immutable from here); RG budget linkage; explicit
   capacity assumptions recorded.
7. **EF-8 `edge_kill_quarantine_decision.py`**: lifecycle state machine — ACTIVE →
   DISABLED (kill-criterion hit) → [>30d] QUARANTINE → [>=14d + revalidation from EF-5 onward]
   re-admission; NO auto-reactivation, ever; every transition digest-bound with reason.

## 2. Cross-cutting invariants

- **status vs gate_verdict separation**: `status ∈ {READY, REJECTED}` = trust/digest integrity
  only; `gate_verdict` = the gate's outcome (PASS / FAIL / NEEDS_*). READY + FAIL is valid
  evidence; a NEEDS_* verdict can NEVER advance to the next gate.
- **Dual anchor**: every gate carries (a) the root intake digest and (b) its immediate
  predecessor's digest, both re-proven via public serializers — chain splicing is structurally
  impossible.
- **Kill-criteria lifecycle**: draft (EF-2) → superset-only strengthening (EF-4) → sealed
  (EF-7) → immutable (EF-8 enforces against the sealed digest).
- **Preregistration is the overfit firewall**: EF-6 results are only interpretable against the
  EF-5 ledger; any variant not in the ledger is REJECTED regardless of performance.
- Non-overclaim: EF admission proves PROCESS survival, never profit. edge_proven /
  profitability_proven stay structurally False in every EF artifact; only long-horizon governed
  paper performance (RG layer) plus human governance may ever elevate a claim.

## 3. GOVERNANCE_REQUIRED

Kill-criteria thresholds; preregistered search-bound sets; minimum OOS window counts; capacity
assumptions. See `governance_decision_framework.md`.

## 4. Test-matrix skeleton per gate

Happy READY+PASS; READY+FAIL (valid negative evidence); NEEDS_* cannot advance; root/predecessor
anchor tamper; kill-criteria weakening attempt (EF-4/7); unregistered variant (EF-5/6); regime
pending-pattern correctness (EF-6); no-auto-reactivation (EF-8); structural-False AST.

## 5. First consumer

The funding/basis/carry pilot (candidate order S1 passive carry → S4 vol-gated → S3 continuation
→ S2 basis mean-reversion → S5 two-leg; S5 blocked until SM enforced) enters ONLY through these
gates after the DR round (PRM-16 venue-mechanics facts) lands as packet/governance constants.

## 6. Stop conditions

Any gate consulted out of order; any performance data visible before EF-5 sealing; any attempt to
reuse a killed edge without full revalidation; any current venue fact from memory instead of DR.
