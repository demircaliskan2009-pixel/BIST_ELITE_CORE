# Edge Factory (EF) — 7-Gate Design Contract (Fable-authored, 2026-07-08)

Status: EF-2..EF-8 IMPLEMENTED; EF-7 is v2 (`edge-paper-admission-decision.v2`), gated by the mandatory
pre-paper validation evidence of section 1a (`EF_PRE_PAPER_VALIDATION_COMPLETION_V1`); EF-7 v1 decisions are
historical only. Purpose: the idea→spec→admission→kill pipeline every future edge candidate must pass. No candidate
trades paper capital without surviving all gates; most candidates SHOULD die here — that is the design working, not
failing. Module namespace: `edge_*` under
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
   checks recorded as explicit proofs, not prose. V2 (`edge-leakage-bias-evidence.v2`) adds the regime
   filter ledger: re-proven, governed RF-2 policies whose set digest the preregistration approval commits.
   This is the only membership RF-6 admission accepts. Without filters the artifact stays V1, byte-identical
   (`regime_volatility_filter_design.md` section 8).
5. **EF-6 `edge_walk_forward_oos_evidence.py`**: replay/OOS/walk-forward results (consumes
   `walk_forward.py` window contract); re-proves the FULL back-chain (intake→packet→spec→ledger
   digests); regime_split_report field (digest-bound `regime_evidence_unavailable` until RF chain
   merges — never silently absent; the RF-7 report of `regime_volatility_filter_design.md` section 9 is
   NOT consumed by EF-6, so the field stays unavailable until a separately authorized EF-6 integration);
   costs/funding/slippage included per pilot rules.
6. **EF-7 `edge_paper_admission_decision.py`** (v2): the sleeve-entry gate — all prior gates READY with
   passing verdicts AND the pre-paper validation evidence (section 1a) READY + PASS, re-proven with the authenticated
   EF-6 as context; the admitted set is exactly the EF-6 survivors that passed every preregistered pre-paper gate (no
   selection); the authenticated admission cap fraction and the `LIMITED_S1_PAPER_V1` scope are carried for RG-7;
   kill-criteria SEALED (immutable from here); RG budget linkage; explicit capacity assumptions recorded; governance
   commits the EF-6 and pre-paper evidence digests. A v1 payload is refused (`schema_superseded_v1_historical_only`)
   and no v1 authority transfers. `pbo_passed` / `stress_passed` stay structural False: they name the complete PRDV4
   obligations, which this route does not prove.
7. **EF-8 `edge_kill_quarantine_decision.py`**: lifecycle state machine — ACTIVE →
   DISABLED (kill-criterion hit) → [>30d] QUARANTINE → [>=14d + revalidation from EF-5 onward]
   re-admission; NO auto-reactivation, ever; every transition digest-bound with reason.

## 1a. Pre-paper validation (`EF_PRE_PAPER_VALIDATION_COMPLETION_V1`)

PRDV4 §1.13 Stage 3 and §1.20 are closed for the LIMITED S1 paper-only route by three artifacts in
`src/crypto_core/validation/`, all paper-only, deterministic, exact (integer/rational, no float, no decimal context)
and fail-closed:

- **`edge_pre_paper_validation_policy.py`** — the governed values (PBO bands `a <= 0.20`, `c <= 0.40`, `e <= 0.60`;
  capped-band fraction `<= 1/2`; LIMITED_S1 regime fraction `<= 1/4`; Monte Carlo `p_max <= 0.05` and `>= 50`
  closed trades; sensitivity retention `>= 0.5`; stress multipliers at least the PRDV4 Stage 3 values; flash-crash
  depth, slippage and maintenance fraction, for which PRDV4 names no value) and the pinned trial-chain genesis. A
  value looser than PRDV4 is refused at construction; only an exact HUMAN_GOVERNANCE approval advances.
- **`edge_trial_count_chain.py`** (`EDGE_TRIAL_COUNT_CHAIN_V1`) — the cumulative count of edge variants ever tested: a
  governed genesis carrying the human-attested pre-genesis count E1 (never defaulted), one re-proven sealed EF-5 per
  link, monotone int64 cumulative counts, duplicates refused, iterative re-proof, plus one exact HUMAN_GOVERNANCE
  currentness attestation per evaluation. It cannot detect off-chain trials.
- **`edge_pre_paper_validation_evidence.py`** — consumes EF-6 by digest (EF-7 embeds it once), the policy, the chain,
  the attestation and a frame dataset equal to the union of the EF-6 segment datasets. Methods:
  - frame: the trailing `16 x floor(days / 16)` UTC days of the authenticated EF-6 span; one accepted
    `historical_decision_run` + `historical_execution_economics` full-frame run per registered variant;
  - returns and Sharpe: the accepted walk-forward methodology (shared `historical_walk_forward_*` helpers), never
    rounded before aggregation; risk-free must be zero;
  - CSCV/PBO (`CSCV_PBO_S16_LEXICOGRAPHIC_EXACT_V1`): 16 blocks, all 12 870 halves, exact ranking (certified
    intervals only accelerate; exact ties structural; other overlaps by integer cross-multiplication), every
    IS-maximal variant in theta*, ties counted against theta, overfit iff `2 x rank > N`, exact `PBO = overfit /
    12 870`, the full split matrix committed; fewer than two variants or an undefined half FAIL; PBO `>= c` FAILs and
    stops every later gate;
  - DSR (`DSR_PRDV4_STANDARDIZED_Z_EXACT_DECISION_V1`, a human-authorized interpretation, not the unchanged PRDV4
    formula): `SR_max` read as the maximal daily-return t-statistic over the frame, `N` the attested cumulative trial
    count; PASS iff `z > 0` and `z^2 >= 2 ln(2N)` by certified rational bounds; the DSR value is never rendered;
  - Monte Carlo (`MC_SIGN_FLIP_SHA256_CTR_V1`, human-authorized; a literal trade-order shuffle leaves the Sharpe
    unchanged and is not used): sign flips of the closed-trade returns under a symmetric independent zero null, 10 000
    samples from the SHA-256 counter stream of the EF-5 and assignment digests, ties counted against the candidate;
  - sensitivity (`SENSITIVITY_STAR_GRID_X20_V1`): every ±5..±20% probe of every SEARCHED parameter must be an exact,
    schema-valid, registered EF-5 assignment; a survivor without its own complete grid is not computable; fragile iff
    a ±10% probe keeps less than the retention floor; heatmap committed;
  - stress (`STRESS_PIT_TRANSFORM_V1`): the accepted economics engine re-runs the survivor's frame run under HIGH_VOL
    (log-returns x 1.5 from the start mark, slippage x governed), LOW_LIQUIDITY (depth and slippage) and FLASH_CRASH
    (a governed gap against the maximal-leverage day-boundary position, held for the governed recovery, with a
    maintenance-zone breach recorded, never a liquidation executed); PASS iff exact frame expectancy `>= 0`, positive
    equity and no breach. The PRDV4 "documented regime gate" alternative is unavailable (no input accepts one), so a
    failing scenario rejects the survivor. Modeled synthetic stress only, never venue-faithful liquidation;
  - cap (`ADMISSION_CAP_FRACTION_V1`): `min(PBO band cap, regime cap)`; the regime-conditional PBO is UNPROVEN and
    the LIMITED_S1_PAPER_V1 worst-case regime cap applies to every regime (PRDV4 record: `PRDV4_MULTI_MARKET_CRYPTO.md`,
    LIMITED_S1_PAPER_V1 exception).

Consumption graph: EF-5 → EF-6 → pre-paper evidence (with policy, chain, attestation, frame dataset) → EF-7 v2 →
EF-8 (v2 only, through the EF-7 verifier) → RG-7 (admission cap) → RG-8. RF-6/RF-7 and the legacy `validation/pbo.py`
and `stress_testing.py` are not consumed. Unresolved and never invented: production H-VAL values, E1 (the pre-genesis
tested-variant count), the per-evaluation currentness attestation and venue liquidation mechanics (E2). Every test
world uses explicit `test-fixture:` approvals and SYNTHETIC values; nothing proves an edge, profitability, readiness or
Stage-4 completion.

## 1b. Paper consumption of the EF-7 admission (`GOVERNED_PAPER_TYPED_PROVENANCE_V2`)

The governed paper period (`multi_sleeve_risk_governance_design.md` §7) consumes EF-7 v2 and EF-8 unchanged:

- the genesis re-proves the EF-7 decision through its public verifier and uses only its strict reconstruction. The
  risk-budget policy, the EF-6 economics-policy anchor, the executable binding digest, the spec digest, the admitted
  variant set, the admission cap and the capacity assumptions are all read from that authenticated decision; the
  risk-budget policy is rebuilt from the EF-7 binding and never supplied;
- one admitted variant runs, under its exact registered assignment and its parameter approval; a non-admitted variant
  or another assignment is refused;
- only the supported capacity measure is enforced (`u x L_k <= max_value` at each cycle opening); any other measure for
  the instrument blocks the genesis, because its semantics are not equivalent;
- the EF-8 INITIAL_ACTIVATION of that admission is the genesis head; a later EF-8 receipt (kill, quarantine) is a
  successor whose effective instant invalidates every later decision and fill inside the economics. A readmitted head
  is a different admission cycle and never continues a genesis.

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

Kill-criteria thresholds; preregistered search-bound sets (including the ±20% / 5% star grid every admitted
variant needs); minimum OOS window counts; capacity assumptions; the pre-paper validation policy values; the trial-chain
genesis (with E1) and each currentness attestation. See `governance_decision_framework.md`.

## 4. Test-matrix skeleton per gate

Happy READY+PASS; READY+FAIL (valid negative evidence); NEEDS_* cannot advance; root/predecessor
anchor tamper; kill-criteria weakening attempt (EF-4/7); unregistered variant (EF-5/6); regime
pending-pattern correctness (EF-6); no-auto-reactivation (EF-8); structural-False AST. Pre-paper: an authentic
distinct-variant positive world and the degenerate world A (PBO = 1); exact PBO, DSR, Monte Carlo and sensitivity
oracles; trial-chain and currentness negatives; v1 refusal; forged split matrix; failing stress, sensitivity, Monte
Carlo and DSR.

## 5. First consumer

The funding/basis/carry pilot (candidate order S1 passive carry → S4 vol-gated → S3 continuation
→ S2 basis mean-reversion → S5 two-leg; S5 blocked until SM enforced) enters ONLY through these
gates after the DR round (PRM-16 venue-mechanics facts) lands as packet/governance constants.

## 6. Stop conditions

Any gate consulted out of order; any performance data visible before EF-5 sealing; any attempt to
reuse a killed edge without full revalidation; any current venue fact from memory instead of DR.
