# Funding / Basis / Carry Pilot — Design Contract (Fable-authored, 2026-07-08)

Status: DESIGN ONLY. The first edge family to enter the edge factory (`edge_factory_design.md`).
Nothing here claims an edge exists — the pilot's PURPOSE is to test whether one survives the
gates; most candidates dying is the system working. All current venue facts are DR-gated
(`deep_research_question_pack.md`); none may come from model memory.

## 1. Existing substrate (verified merged; consume, never modify)

- `edge/families/funding.py`: `FundingRateEdge` (PRDV4 Family B safety-gated paper evaluator),
  `FundingConfig`, `FundingSafetyContext` (its `regime_state` input is caller-supplied today —
  the RF chain becomes its evidence source); fail-closed block reasons
  (funding_feed_unavailable, funding_regime_blocked, ...).
- `data/requirements.py`: PIT-grade `FUNDING_RATE` DataRequirement —
  event_time=funding_window_open_ns, available_at=funding_published_ns,
  finalized_at=funding_finalized_ns, funding_semantics ∈ {predicted, final},
  finality=funding_cycle_closed. Evidence features consume `final` semantics ONLY.

## 2. Why this family first

Funding/basis/carry premia are STRUCTURAL (they exist because leverage demand pays for balance
sheet, not because of forecasting skill), measurable from PIT-grade public data, testable without
order-book microstructure fidelity (except S5), and naturally fail-closed (no funding data → no
position). They are also capacity-limited and regime-sensitive — which the gates must expose,
not hide.

## 3. Candidate ladder (strict order; each is its own EF-2 intake with its own kill criteria)

| # | Candidate | Hypothesis (to be TESTED, not believed) | Blocked by |
|---|---|---|---|
| S1 | Passive funding carry | Persistent positive (or negative) funding regimes pay a harvestable premium to the opposite side after costs | — (first) |
| S4 | Vol-gated carry | S1 conditioned on RF labels (F1 realized-vol + F4 funding-regime): carry pays asymmetrically across vol regimes; gating reduces left tail | RF chain (labels as evidence) |
| S3 | Funding continuation | Extreme funding persists short-horizon; entering with (not against) extreme funding captures continuation before mean reversion | S1 baseline for comparison |
| S2 | Basis mean-reversion | Perp-spot basis dislocations revert within bounded windows after costs | Basis series in packet (DR) |
| S5 | Two-leg cash-and-carry | Simultaneous spot+perp legs lock the basis; profitability = basis minus BOTH legs' costs | SM chain ENFORCED (fill/slippage integrity is the whole trade) — hard block |

Order rationale: S1 needs the least data and defines the cost baseline every later candidate must
beat; S4 is S1 + merged RF evidence; S3/S2 add path dependence; S5 is last because without
enforced fill/slippage metrics its paper results are structurally untrustworthy.

## 4. Per-candidate contract requirements (bind at EF-2/EF-4)

- Cost model MANDATORY in every backtest/paper evaluation: taker/maker fees (DR-pinned), funding
  actually paid/received per cycle (final semantics; never predicted), slippage per the pinned
  `fill_pricer` model, and for S5 both legs + borrow/margin costs.
- Kill-criteria draft at intake (sketches; numbers GOVERNANCE_REQUIRED): max consecutive losing
  funding cycles; max drawdown vs envelope ladder; funding-regime flip persistence; realized
  cost-ratio ceiling (costs eating > X% of gross premium); capacity breach (position vs open
  interest proxy).
- Regime declaration: S1/S3/S2 declare expected-regime honestly at intake; S4 declares its RF
  label dependence explicitly (EF-4 checks against the pinned label enum).
- Capacity assumptions recorded at EF-7 (premium per unit shrinks with size; the claim must be
  bounded, not asymptotic).

## 5. Data requirements (packet, EF-3)

Funding rate series (predicted AND final, both archived; features use final only); mark/index
price series; spot series (S2/S5); fee schedule constants (DR); venue funding interval/timing
constants (DR); optional depth/OI proxies (packet-conditional, enables RF F5 and capacity
checks). All with event_time/available_at/finalized_at and revision policy.

## 6. Pipeline mapping (nothing bypasses the factory)

Each candidate: EF-2 intake → EF-3 packet → EF-4 spec admission (`strategy/spec.py` — edge_family
funding_basis_carry; kill draft → superset) → EF-5 preregistration (parameter bounds per candidate
BEFORE any performance) → EF-6 walk-forward/OOS with costs (regime_split via RF when merged) →
EF-7 paper admission (RG budget linkage) → paper sleeve under RG envelope → EF-8 kill/quarantine
lifecycle. S4 additionally requires RF-6 filter admission (policy in the EF-5 ledger).

## 7. What would count as FAILURE (pre-committed honesty)

S1 gross premium exists but costs consume it → REJECT family sizing up, record as evidence;
premium exists only in one regime and RF stability fails → REJECT S4 rather than curve-fit the
labels; S5 paper profits appear only under unenforced fill assumptions → blocked until SM, and if
enforced metrics kill it, it stays dead. A pilot where all five candidates die is a VALID,
valuable outcome — the factory proved it kills.

## 8. GOVERNANCE_REQUIRED (see governance_decision_framework.md §7)

All kill thresholds; per-candidate parameter bounds; sizing bounds within the RG envelope;
go/no-go per candidate after EF-6 evidence.

## 9. Stop conditions

Any venue fact from memory (fees, intervals, limits) → DEEP_RESEARCH_REQUIRED; any candidate
skipping a gate; any S5 work before SM-5/SM-6 merge; any performance peeked before EF-5 sealing.
