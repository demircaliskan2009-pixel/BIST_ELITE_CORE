---
name: "PRDV3 System Core Rules"
description: "Global deterministic execution, fail-closed behavior, and BIST-specific constraints"
applyTo: "**"
---

# BIST QUANT ENGINE — SYSTEM CONTRACT

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

When applicable, use the mapped prompt workflow instead of raw chat reasoning:

- DEBUG → `.github/prompts/forensic-debug.prompt.md`
- PATCH → `.github/prompts/safe-patch.prompt.md`
- Ranking/scoring issue → `.github/prompts/ranking-fix.prompt.md`
- Comparison issue → `.github/prompts/comparison-fix.prompt.md`
- Price-context issue → `.github/prompts/price-awareness.prompt.md`

If the mapped prompt applies, do not bypass it with ad-hoc reasoning.

---

## 1C. FULL-CONTEXT REQUIREMENT

Before implementation or conclusion:

- identify relevant files
- read actual implementation
- trace execution path

Shallow answers are invalid.

---

## 2. FAIL-CLOSED BEHAVIOR

The system MUST default to NO ACTION unless all conditions are satisfied.

Trading context:
- No setup → NO TRADE
- Weak signal → NO TRADE
- Missing confirmation → NO TRADE

Never force output.

---

## 3. DETERMINISTIC OUTPUT

Same input MUST produce same output.

Forbidden:
- random phrasing
- variable conclusions
- template drift

---

## 4. BIST-SPECIFIC CONSTRAINTS

System must respect:

- Tick size rules
- Price limits (tavan/taban)
- Circuit breaker logic
- Liquidity constraints
- Volume confirmation

If not verifiable:
→ reject signal

---

## 5. DATA VALIDATION LAYER

Before ANY reasoning:

Check:
- OHLCV completeness
- Time continuity
- Symbol validity
- No missing candles

If invalid:
→ STOP

---

## 6. FEATURE INTEGRITY

All features must be:

- explicitly defined
- reproducible
- non-leaking (no future data)

Reject:
- implicit indicators
- undefined formulas

---

## 7. RANKING RULES

Ranking must:

- produce DIFFERENT scores
- be explainable
- use stable tie-breaking

If all scores equal:
→ SYSTEM ERROR

---

## 8. COMPARISON LOGIC

When multiple symbols:

- Evaluate EACH independently
- Then compare

Forbidden:
- single-symbol fallback
- template reuse

---

## 9. PRICE AWARENESS

System MUST evaluate:

- current price vs entry
- missed entry detection
- pullback logic

If price context ignored:
→ INVALID OUTPUT

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

## 15. RESPONSE FORMAT

Always return:

1. What was analyzed
2. What is wrong (if any)
3. What was changed (if any)
4. Why it works now
5. Remaining risks