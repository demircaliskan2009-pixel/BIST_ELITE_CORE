---
name: ranking-fix
description: "Use when ranking, scoring, dispersion, weighting, normalization, or tie-break determinism is broken or needs forensic correction."
agent: agent
tools: ["filesystem/*"]
---

You are fixing a ranking system.

STRICT:
- No hardcoded values
- No template outputs
- Must produce differentiated scores

CHECK:
- scoring inputs
- weighting logic
- normalization
- output diversity

OUTPUT:
- issue explanation
- why all scores equal
- corrected formula
- before/after example

FAIL:
If system cannot differentiate → explain why