---
name: "PRDV4 System Core Rules"
description: "Global deterministic execution, fail-closed behavior, and crypto-specific constraints"
applyTo: "**"
---

# CRYPTO QUANT ENGINE — SYSTEM CONTRACT

## 1. CORE PRINCIPLE

This system operates under STRICT ENGINE MODE.

Rules:
- No guessing
- No hallucination
- No implicit assumptions
- All outputs must be evidence-based

If data is missing:
→ OUTPUT: "INSUFFICIENT EVIDENCE"

---

## 1A. TASK CLASSIFICATION

Before any action, classify the task as exactly one of:

- DEBUG
- PATCH
- ANALYSIS
- VALIDATION

Then follow the matching workflow deterministically.

---

## 1B. TOOL-FIRST EXECUTION

When applicable, use the mapped prompt workflow:

- DEBUG → `.github/prompts/forensic-debug.prompt.md`
- PATCH → `.github/prompts/safe-patch.prompt.md`
- Edge validation → `.github/prompts/edge-validation.prompt.md`
- Edge discovery → `.github/prompts/edge-discovery.prompt.md`

If the mapped prompt applies, do not bypass it with ad-hoc reasoning.

---

## 1C. FULL-CONTEXT REQUIREMENT

Before implementation or conclusion:

- identify relevant files
- read actual implementation
- trace execution path

Shallow answers are invalid.

---

## 1D. MINIMAL TOOL DISCIPLINE

Use the minimum necessary tools only.

Forbidden:
- unnecessary tool calls
- broad noisy tool activation without need
- continuing exploration after sufficient evidence exists

If ambiguity remains after minimal evidence gathering:
→ FAIL CLOSED

---

## 1E. HIDDEN DEFECT DISCIPLINE

The system MUST surface hidden issues explicitly.

Treat as defects unless explicitly justified:
- unexpected SKIP
- unexpected XFAIL
- warnings
- file-handle leaks
- slow hangs
- clean-checkout failures masked by local artifacts

---

## 2. FAIL-CLOSED BEHAVIOR

The system MUST default to NO ACTION unless all conditions are satisfied.

Trading context:
- No setup → NO TRADE
- Weak signal → NO TRADE
- Missing confirmation → NO TRADE
- Missing data → HOLD with explicit reason

Never force output.

---

## 3. DETERMINISTIC OUTPUT

Same input MUST produce same output.

Forbidden:
- random phrasing
- variable conclusions
- template drift

---

## 4. CRYPTO-SPECIFIC CONSTRAINTS

System must respect:

- Perpetual futures only (no spot, no options, no delivery)
- 3× maximum leverage (system-wide hard cap)
- USD base currency
- Binance primary, Bybit secondary, CoinGecko discovery
- 24/7 market operation
- Funding rate settlement cycles (8h)
- Liquidation mechanics (maintenance margin, DTL monitoring)
- Cross-exchange latency and order book integrity

If not verifiable:
→ reject signal

---

## 5. DATA VALIDATION LAYER

Before ANY reasoning:

Check:
- WebSocket stream continuity
- Order book CRC32 integrity
- Trade stream sequence numbers
- OHLCV completeness
- Symbol validity
- No stale data (>10s = stale)

If invalid:
→ STOP

---

## 6. EDGE INTEGRITY

All edges must be:

- explicitly defined per §1.1-§1.10 taxonomy
- reproducible
- non-leaking (no future data)
- microstructure-justified (INV-EDGE-001)
- invalidation-conditioned (INV-EDGE-002)
- crowding-detected (INV-EDGE-003)
- validation-pipeline completed (INV-EDGE-004)

Reject:
- implicit indicators
- undefined formulas
- ML-generated signals

---

## 7. RISK RULES

Risk overrides strategy unconditionally (INV-003).

Enforce:
- CVaR₉₉ < 5% NAV daily (§1.18)
- Kill-switch 5-level ladder (§1.19)
- Kelly-bounded sizing (§1.28)
- DTL safety bands (§1.26)
- Margin utilization tiers (§1.26)

If risk state invalid:
→ BLOCKED

---

## 8. SYSTEM STATE ENGINE

System operates under 5-state SHS model (§1.29):

NORMAL → DEGRADED → DEFENSIVE → CRISIS → HALT

- Escalation: immediate
- De-escalation: hysteresis required
- SHS computed every 10 seconds from 10 weighted signals
- Single source of truth for operational state

---

## 9. AI CONSTRAINT (INV-005)

AI MUST NOT:
- generate orders
- modify risk parameters
- execute trades

AI has read-only access. Signal logic must be deterministic code only.

---

## 10. EXPLANATION STANDARD

Every output must include:

- reasoning chain
- evidence reference
- decision logic

No vague explanations allowed.

---

## 11. HARD REJECTION RULES

System MUST reject output if:

- data missing
- logic incomplete
- ambiguity exists

Output:
"INSUFFICIENT EVIDENCE"

---

## 12. OUTPUT DISCIPLINE

Allowed outputs:

- Structured analysis
- Deterministic signals
- Explicit rejection

Forbidden:

- speculation
- motivational text
- filler

---

## 13. SYSTEM PRIORITY

Priority order:

1. Instructions (this file)
2. Skills
3. Prompts

If conflict:
→ Instructions WIN

---

## 14. VALIDATION BEFORE CONCLUSION

Before concluding:

- verify logic consistency
- check edge cases
- confirm output correctness

---

## 14A. REPO HYGIENE + CI GUARDIAN

Before commit or push:
- inspect git status and diff
- verify no generated or runtime artifacts are committed
- untrack runtime artifacts before commit

If diff is large, mixed-purpose, or unclear:
→ STOP

If CI fails:
→ fix and retry until green or until blocked by explicit missing evidence

Commit policy:
- atomic only
- minimal only
- relevant only

If branch protection blocks direct push:
→ switch to PR workflow automatically

---

## 15. RESPONSE FORMAT

Always return:

1. What was analyzed
2. What is wrong (if any)
3. What was changed (if any)
4. Why it works now
5. Remaining risks

---

## 16. AUTONOMOUS EXECUTION LOOP

The system operates as a closed autonomous loop:

```
code → lint → test → validate → commit → push → CI → feedback → fix → repeat
```

Rules:
- Every code change must complete the full loop before the task is done.
- No manual intervention required at any step.
- If any step fails → fix automatically and restart from the failed step.
- Toolchain rules in `.github/instructions/toolchain.instructions.md` govern each step.
- Git automation rules in `.github/skills/repo-hygiene-ci-guardian/SKILL.md` govern commit/push/PR.

The loop terminates when:
- CI is green AND all commit gates pass, OR
- A structural blocker is identified and reported with evidence.

---

## 17. RETRY AND ESCALATION DISCIPLINE

### Retry Limits

| Operation | Max Retries | On Exhaustion |
|-----------|-------------|---------------|
| Lint fix | 3 | STOP — report unfixable diagnostic |
| Test fix | 5 | STOP — report structural test failure |
| CI fix-push cycle | 5 | STOP — report blocking CI issues |
| Type error fix | 3 | STOP — report type system conflict |
| Import resolution | 3 | STOP — report missing dependency |

### Escalation Protocol

When retries exhausted:
1. Collect all evidence from failed attempts.
2. Classify as: FIXABLE (need different approach) or BLOCKED (need external input).
3. If FIXABLE → try alternative approach (max 1 alternative).
4. If BLOCKED → report with exact blocking evidence and stop.

### Same-Failure Rule

If the same failure occurs 3 consecutive times with the same fix approach:
→ STOP immediately.
→ The approach is wrong, not the execution.
→ Switch strategy or report as blocked.

---

## 18. DEAD LOOP PREVENTION

### Prohibited Patterns

- Infinite retry without progress tracking
- Fix that reintroduces a previously fixed issue
- Circular dependency between fixes
- Retry without changing approach after failure

### Progress Tracking

Every retry must demonstrate measurable progress:
- Fewer failing tests
- Different failure message
- Reduced error count

If a retry produces identical output to the previous attempt → STOP.

### Fallback States

| Situation | Fallback |
|-----------|----------|
| Tests won't pass after 5 cycles | Revert to last known good, report |
| Lint unfixable | Flag as tech debt, skip file with justification |
| CI flaky (passes locally, fails remotely) | Report as environment issue |
| Merge conflict | Report conflict files, do not auto-resolve |

### Hard Stops

These conditions IMMEDIATELY terminate the loop:
- Working tree has uncommitted changes from a different task
- More than 10 files modified in a single loop iteration
- Revert needed but would affect other people's work
- Force push would be required

---

## 19. PERFORMANCE TELEMETRY

Every pipeline execution must emit structured telemetry:

### Required Metrics

| Metric | Source | Alert Threshold |
|--------|--------|----------------|
| `stage_latency_ms` | Per pipeline stage | >5000ms |
| `edge_hit_rate` | Edge engine | <30% over 24h |
| `execution_slippage_bps` | Execution engine | >10 bps vs estimate |
| `fill_rate_pct` | Order state machine | <85% |
| `data_drift_psi` | PSI per feature | >0.25 |
| `data_drift_ks` | KS test per feature | p < 0.01 |
| `book_crc32_fail_rate` | Data pipeline | >1% of checks |
| `ws_reconnect_count` | WebSocket manager | >3 per hour |
| `shs_value` | System state engine | <0.50 |
| `kill_switch_level` | Risk engine | ≥ KS-1 |

### Output Format

```json
{
  "timestamp_ms": 1700000000000,
  "stage": "edge",
  "metrics": {
    "stage_latency_ms": 142,
    "edge_hit_rate": 0.42,
    "active_edges": 3,
    "shs_value": 0.82
  },
  "alerts": []
}
```

### Rules
- Telemetry is structured JSON to `logs/telemetry/`.
- One file per day: `telemetry_YYYY-MM-DD.jsonl`.
- Alerts appended when thresholds breached.
- Telemetry must not affect pipeline latency (async write).
