---
name: comparison-fix
description: "Use when multi-symbol comparison, pairwise reasoning, leader selection, or anti-template comparison behavior needs deterministic correction."
agent: agent
tools: ["filesystem/*"]
---

You are fixing comparison across multiple symbols.

PROBLEM:
System collapses to single-symbol logic.

TASK:
- Ensure independent evaluation per symbol
- Ensure comparative reasoning
- Prevent template reuse

OUTPUT:
- comparison logic breakdown
- bug location
- fix implementation
- example with 2+ symbols