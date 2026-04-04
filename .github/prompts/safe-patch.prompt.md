---
name: safe-patch
description: "Use when a code change or surgical patch is required and the smallest fail-closed fix must be implemented without refactor or architecture drift."
agent: agent
tools: ["filesystem/*"]
---

You must implement a FIX with the following constraints:

RULES:
- MINIMAL change only
- NO refactor
- NO architecture change
- FAIL-CLOSED behavior required

PROCESS:
1. Identify exact bug location
2. Apply smallest possible fix
3. Preserve existing structure
4. Add validation if needed

OUTPUT:
- file path
- patch (diff format)
- explanation
- edge case handling

REJECT:
- broad rewrites
- speculative fixes