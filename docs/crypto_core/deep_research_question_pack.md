# Deep Research Question Pack — Combined Round (Fable-authored, 2026-07-08)

Consolidates and supersedes the archived PRM-07 + PRM-16 question sets as the single repo source
for the combined Deep Research round. §19 binds: DR is strictly read-only/advisory, never merge
authority, never a gate waiver; ChatGPT decides when it runs. Output contract: every answer cites
sources; REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN separated; anything unverifiable
is marked `UNPROVEN` and stays OUT of governance constants. Answers become digest-pinned
governance/registry constants (with citation ids) — never free-text repo rules.

## Batch A — Funding/basis/carry venue mechanics (consumer: pilot packet + governance §7)

For each candidate venue class (major perp venues; exact venue list is itself question A0):

1. **A0** Which venues are appropriate references for a paper-only perp funding study
   (liquidity, data availability, documentation quality)?
2. **A1** Funding interval and exact accrual/payment timing semantics (when is a position liable;
   boundary behavior at the funding timestamp)?
3. **A2** Predicted vs final funding rate: publication timing of each, revision behavior, and the
   exact moment the final value is immutable (maps to `funding_published_ns` /
   `funding_finalized_ns` / `funding_semantics`).
4. **A3** Funding rate formula components (premium index, interest rate component, clamps) and
   whether the venue publishes the components or only the aggregate.
5. **A4** Fee structure for the relevant instruments: maker/taker tiers, and whether funding is
   fee-adjacent or separate.
6. **A5** Mark price vs index price vs last price definitions and their roles in funding/
   liquidation (mark/index confusion is a named alpha-killer class).
7. **A6** Historical funding + mark/index data availability: depth of history, granularity,
   revision policy, export mechanics (for PIT-grade packet construction).
8. **A7** Rate limits and terms-of-use constraints for historical data collection (paper-only,
   public endpoints).
9. **A8** Liquidation mechanics relevant to carry positions (maintenance margin bands, ADL) —
   needed for honest kill-criteria, not for execution.
10. **A9** Two-leg (cash-and-carry) cost stack: spot fees, margin/borrow costs, settlement
    frictions (S5 feasibility inputs; S5 remains SM-blocked regardless).
11. **A10** Funding-pause / outage / symbol-migration semantics (how gaps appear in data and how
    they must be represented in the packet rather than silently bridged).

## Batch B — Machine-time sources (consumer: MT-3 registry; see machine_time_provenance_design.md)

1. **B1** Current public randomness/time beacons (e.g. NIST-class beacons): publication cadence,
   value format, signature/verification mechanics, archival access.
2. **B2** RFC 3161 timestamping authorities: availability, verification semantics, chain/trust
   model, suitability for hashing a JSON self-digest.
3. **B3** Roughtime ecosystem status: live servers, protocol maturity, verification tooling.
4. **B4** Exchange server-time endpoints: reliability and manipulation surface — presumption is
   NOT quorum-eligible alone; confirm or refute with evidence.
5. **B5** Recommended proof archival formats and re-verification longevity (can a 2026 proof be
   re-verified in 2030?).
6. **B6** Any additional independent source CLASS suitable for the not-before or not-after role
   (quorum requires >= 2 independent classes per role).

## Batch C — Optional / packet-conditional (only if Batch A answers make them relevant)

1. **C1** Depth/spread proxy availability for RF feature class F5 (order-book snapshots or
   aggregated liquidity metrics with PIT semantics).
2. **C2** Liquidation-event feeds for RF F6 / future liquidation-reflexivity family: coverage,
   latency, historical archives, reliability.

## Routing

Run as ONE combined round (token/effort efficiency). Answers land as: Batch A → cited fact packet
and decision inputs for pilot packet constants plus `governance_decision_framework.md` §7
human/controller approval; Batch B → cited fact packet and decision inputs for MT-3
`machine_time_source_registry.py`; Batch C → cited fact packet and decision inputs for RF policy
enable/disable flags for F5/F6. No DR answer approves a value by itself — any repo constant must
be introduced later through a separate scoped governance/registry PR with citations, required
approvals, and the full §21.4 gate order. No answer authorizes implementation by itself — every consumer
slice still runs the full §21.4 gate order.
