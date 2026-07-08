# PaperStage4CompletionDecisionV2 — Design Contract (Fable-authored, 2026-07-08)

Status: DESIGN ONLY — nothing here is implemented, merged, or proven. Implementation requires the
§21.4 gate order: Codex design audit (this file is the audit input) → Opus 4.8 xhigh implementation
→ validation/CI → Codex implementation audit → connector gate → human merge authorization.
Every field name below was verified against merged source on `main` — not invented.

## 1. Slice identity

- Branch: `feature/paper-stage4-completion-decision-v2-pr1`. Exactly 2 new files:
  `src/crypto_core/validation/paper_stage4_completion_decision_v2.py`,
  `tests/crypto_core/validation/test_paper_stage4_completion_decision_v2.py`.
- Non-goals: no completion=True path; no machine-time/readiness claims; no comparator call; no
  change to v1 or any upstream module; no `__init__.py`; no docs in the implementation PR.
- Corrected module fact: the return-series gate module is
  `paper_30day_evidence_gate_decision.py` (class `PaperThirtyDayEvidenceGateDecision`, digest fn
  `paper_30day_evidence_gate_decision_digest`) — NOT `paper_return_series_thirty_day_gate_decision.py`.

## 2. Public API

- Dataclass `PaperStage4CompletionDecisionV2` (frozen); enum
  `PaperStage4CompletionDecisionV2Status {READY, REJECTED}`; error
  `PaperStage4CompletionDecisionV2Error(RuntimeError)`.
- Builder `build_paper_stage4_completion_decision_v2(comparison_evidence, *,
  expected_comparison_evidence_digest, sharpe_evidence, expected_sharpe_evidence_digest,
  methodology, expected_methodology_digest, edge_identity, expected_edge_identity_digest,
  baseline_evidence, expected_baseline_evidence_digest, gate_decision,
  expected_gate_decision_digest, attested_gate_decision, expected_attested_gate_decision_digest,
  predecessor_decision, expected_predecessor_decision_digest, completion_decision_id,
  correlation_id, metadata=None)`.
- Serializer `paper_stage4_completion_decision_v2_to_dict` / digest
  `paper_stage4_completion_decision_v2_digest` (canonical JSON, SHA-256, self-digest field
  `completion_decision_digest` excluded).
- Constants: `_SCHEMA_VERSION = _DECISION_VERSION = "paper-stage4-completion-decision.v2"`;
  `_REASON_PREFIX = "paper_stage4_completion_decision_v2"`;
  `_EXPECTED_PREDECESSOR_SCHEMA_VERSION = "paper-stage4-completion-decision.v1"`;
  `_EXPECTED_ATTESTED_GATE_SCHEMA_VERSION = "paper-attested-operational-thirty-day-gate-decision.v1"`;
  `_COMPLETION_POLICY_ID = "stage4_completion_blocked_pending_machine_time_and_secondary_metrics.v1"`;
  `_ATTESTED_CHAIN_LINK = "correlation_market_and_utc_day_index_only.v1"`;
  `_DAY_NS = 86_400_000_000_000`. ALL v1 governance re-pin constants are copied verbatim
  (never imported — independent consumer-boundary re-pin).
- Fields: all v1 fields (same names) PLUS: expected/verified_attested_gate_decision_digest;
  expected/verified_predecessor_decision_digest; predecessor_decision_id; predecessor_schema_version;
  attested_gate_decision_id; attested_day_count; attested_selected_start_utc_day_index;
  attested_selected_end_utc_day_index; gate_window_start_utc_day_index;
  gate_window_end_utc_day_index; attested_chain_link (constant string, digest-bound);
  stage4_completion_blockers = the new 3-tuple; `attested_operational_thirty_day_gate_consumed:
  bool = True`; `predecessor_decision_consumed: bool = True`; `operational_day_gate_deferred:
  bool = False` (consumed, attestation-only); `operational_day_evidence_consumed: bool = False`
  (the GATE was consumed, not raw days); every v1 structural-False flag verbatim PLUS explicit
  `machine_time_origin_proven: bool = False`.

## 3. Digest anchors (8; each: recompute == carried == expected, else REJECTED)

| # | Input | Digest fn | Mismatch reason | Test |
|---|---|---|---|---|
| 1 | PaperStage4ComparisonEvidence | paper_stage4_comparison_evidence_digest | comparison_evidence_digest_mismatch | test_comparison_evidence_digest_tamper_rejected |
| 2 | PaperSharpeEvidence | paper_sharpe_evidence_digest | sharpe_evidence_digest_mismatch | test_sharpe_evidence_digest_tamper_rejected |
| 3 | PaperVsBacktestMethodology | paper_vs_backtest_methodology_digest | methodology_digest_mismatch | test_methodology_digest_tamper_rejected |
| 4 | PaperEdgeIdentityEvidence | paper_edge_identity_evidence_digest | edge_identity_digest_mismatch | test_edge_identity_digest_tamper_rejected |
| 5 | PaperStage4BacktestBaselineEvidence | paper_stage4_backtest_baseline_evidence_digest | baseline_evidence_digest_mismatch | test_baseline_evidence_digest_tamper_rejected |
| 6 | PaperThirtyDayEvidenceGateDecision | paper_30day_evidence_gate_decision_digest | gate_decision_digest_mismatch | test_gate_decision_digest_tamper_rejected |
| 7 | PaperAttestedOperationalThirtyDayGateDecision | paper_attested_operational_thirty_day_gate_decision_digest | attested_gate_decision_digest_mismatch | test_attested_gate_digest_tamper_rejected |
| 8 | PaperStage4CompletionDecision (v1) | paper_stage4_completion_decision_digest | predecessor_decision_digest_mismatch | test_predecessor_digest_tamper_rejected |

Additional reseal defense for anchors 1-6 (v1 pattern): the comparison evidence's own
`verified_*` digests must equal v2's independent recomputes
(`comparison_consumed_artifact_mismatch_<name>`).

## 4. Predecessor continuity (all REJECTED; P1-class reseal defenses)

- schema_version != "paper-stage4-completion-decision.v1" → `predecessor_schema_version_mismatch`.
- status != READY or ready != True → `predecessor_not_ready`.
- completion_verdict != "STAGE4_COMPLETION_BLOCKED" or stage4_completion_decided != True →
  `predecessor_verdict_incoherent`.
- prdv4_stage4_complete != False (resealed True) → `predecessor_completion_flag_unsafe`.
- stage4_completion_blockers != v1's EXACT 4-tuple (order included) →
  `predecessor_blocker_tuple_mismatch`.
- CHAIN CONTINUITY, field-by-field (never one aggregate digest): each of v1's six `verified_*`
  digests must equal v2's own recompute of the same artifact →
  `predecessor_chain_discontinuity_<name>` (6 parametrized tests).
- predecessor correlation_id / market_symbol mismatch → `predecessor_correlation_mismatch` /
  `predecessor_market_symbol_mismatch`.
- No carried summary/flag is ever trusted without recompute from raw canonical fields.

## 5. Day-index alignment (top P1 risk area)

- Alignment BEFORE division: `gate_used_first_bucket_start_ns % _DAY_NS != 0` →
  `gate_window_start_not_day_aligned`; `gate_used_last_bucket_end_ns % _DAY_NS != 0` →
  `gate_window_end_not_day_aligned`.
- `start_day = gate_used_first_bucket_start_ns // _DAY_NS`;
  `end_day_inclusive = (gate_used_last_bucket_end_ns // _DAY_NS) - 1` — end_ns is the EXCLUSIVE
  end of the last UTC day; the `-1` is where an off-by-one bug will hide
  (`test_end_day_off_by_one_rejected`).
- Required equalities (else REJECTED): attested `selected_start_utc_day_index == start_day`
  (`attested_window_start_mismatch`); `selected_end_utc_day_index == end_day_inclusive`
  (`attested_window_end_mismatch`); `selected_utc_day_indices ==
  tuple(range(start_day, start_day + 30))` (`attested_day_indices_mismatch`);
  `len(selected_utc_day_indices) == 30`, `day_count >= 30`, `gate_bucket_count_used == 30`;
  `selected_operational_day_evidence_digests`: exactly 30, all unique hex64
  (`attested_day_digest_duplicate` on duplicates); attested gate must carry
  `attested_operational_thirty_day_gate_satisfied == True` and `..._decided == True`
  (`attested_gate_not_satisfied`). Bind ONLY `selected_*` fields — `supplied_*` may be a superset.

## 6. Correlation / market / chain link

- Single-correlation rule (precedent: merged review package #308):
  `attested_gate.correlation_id == correlation_id == predecessor.correlation_id`
  (`attested_gate_correlation_mismatch`). Market equality across the comparison chain, the
  attested gate, and the predecessor (`attested_gate_market_symbol_mismatch`).
- The attested chain binds to the return-series chain ONLY via correlation + market + UTC
  day-index equality. There is NO session-digest bridge and none is claimed:
  `attested_chain_link = "correlation_market_and_utc_day_index_only.v1"` (digest-bound constant;
  `test_chain_link_label_preserved`).

## 7. Blockers and non-overclaim

- v2 blocker tuple (EXACT, ordered):
  `("operator_attested_only_machine_time_origin_unproven",
  "timestamp_origin_not_proven_injected_deterministic_time_only",
  "secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1")`.
- DROP `operational_day_evidence_source_unavailable` (the attested source now exists — #318/#319);
  REPLACE `prdv4_minimum_30_day_live_paper_trading_unproven` →
  `operator_attested_only_machine_time_origin_unproven` (30 consecutive days now proven, but only
  by operator attestation); KEEP the timestamp-origin and secondary-metrics blockers.
- `prdv4_stage4_complete` stays STRUCTURALLY False — no code path may assign True. Only the future
  v3 artifact (machine-proven 30-day gate + enforced secondary metrics + council + explicit human
  authorization) may ever set it. Attestation-only evidence is never machine proof (§21.5).

## 8. Structural-False set and AST forbidden surface

- Structural-False (dataclass default False; builder never assigns True; AST + regex tests):
  prdv4_stage4_complete, machine_time_origin_proven, timestamp_origin_proven,
  operational_day_machine_proven, real_wall_clock_used, real_time_paper_operation_proven,
  operational_readiness, live_ready, shadow_ready, deribit_ready, connector_invoked,
  private_api_ready, live_api_called, production_execution, real_orders_enabled,
  real_money_enabled, real_capital_reserved, real_account_equity_used, real_capital_used,
  scheduler_enabled, auto_loop_enabled, edge_proven, profitability_proven,
  same_edge_as_backtest_proven, backtest_validity_proven.
- AST: imports limited to {hashlib, json, re, collections.abc, dataclasses, decimal, enum,
  __future__} + the 8 anchor modules; no crypto_core.(service|execution|venue|runtime|
  orchestrator|temporal|session|data|portfolio); no stage4_comparator import (comparator is never
  re-run); no socket/http/requests/urllib/subprocess/threading/time/datetime/os/pathlib/open call
  names; source regex: no `(?<![A-Za-z0-9_])<flag>\s*=\s*True` assignment for any structural-False
  flag; v1's `_BIST_PATTERN` / `_FORBIDDEN_PATTERN` / `_CLOCK_TOKENS` guards copied verbatim.

## 9. Test matrix (~55-65 tests; fixture pattern = v1 test file `_chain()` + new `_attested_chain()`)

Happy: ready_blocked_v2_decision (READY + STAGE4_COMPLETION_BLOCKED + 3-tuple + all-False flags +
chain-link string), ready_not_satisfied_methodology_path. Tamper: 8 digest tampers + 6
comparison-consumed reseals + 6 predecessor-chain discontinuities. Predecessor: not_ready /
wrong_schema / wrong_verdict / completion_flag_tamper / blocker_tuple_tamper / correlation /
market. Day alignment: start_misaligned / end_misaligned / end_off_by_one / indices_mismatch /
duplicate_digest / too_few / too_many / gate_bucket_count. Attested: not_satisfied / decided_false
/ satisfied-field-namespace check (generic `thirty_day_gate_*` stays False). Structure:
structural_false_ast / forbidden_import_ast / assignment_regex / deterministic_digest_roundtrip /
serializer_excludes_self_digest / frozen_immutability / metadata_validation (raise) /
malformed_ids (raise) / wrong_type_artifacts (8× raise) / blocker_tuple_exactness /
reason_code_prefix.

## 10. Codex design-audit checklist (run BEFORE implementation)

1. 8-anchor list complete — does any missing anchor open a reseal path? 2. Predecessor continuity
field-by-field (not aggregate)? 3. `end_day_inclusive = end_ns//DAY_NS - 1` — UTC epoch-day only,
no DST/leap assumptions? 4. `%` alignment BEFORE division at both ends? 5. `selected_*` vs
`supplied_*` confusion? 6. Single-correlation rule buildable in fixtures? 7. New 3-tuple
consistent with PRDV4 text; DROP justification correct? 8. Structural-False set diffed against
#319's `_DAY_FALSE_FLAGS`? 9. Chain-link non-claim sufficient? 10. Generic vs attested gate field
namespace separation? 11. Governance re-pin constants bit-identical to v1? 12. raise-vs-REJECTED
boundary consistent with v1?

## 11. Stop conditions for the implementer

Field-name mismatch against this contract; fixture requires upstream module changes; invariant
requires editing v1/upstream; any pressure to claim machine-time/readiness/completion; scope
beyond 2 files; full-suite failure whose repair is out of scope → STOP_WITH_PROOF.
