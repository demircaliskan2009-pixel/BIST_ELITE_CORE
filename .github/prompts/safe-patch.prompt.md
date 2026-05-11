---
name: safe-patch
description: "Use when a code change or surgical patch is required and the smallest fail-closed fix must be implemented without refactor or architecture drift."
agent: agent
---

Follow `docs/PRDV4_MULTI_MARKET_CRYPTO.md` as the architecture constitution.

You must implement a FIX with the following constraints:

RULES:
- MINIMAL change only
- NO refactor
- NO architecture change
- FAIL-CLOSED behavior required
- NO guessing
- READ the real implementation and call chain before editing
- VALIDATE the touched path after editing
- STOP on ambiguity and output exactly: `INSUFFICIENT EVIDENCE`

PROCESS:
1. Identify exact bug location
2. Read the surrounding call chain
3. Apply smallest possible fix
4. Preserve existing structure
5. Add or update validation only if behavior changes
6. Run the narrowest deterministic validation that proves the fix

OUTPUT:
- file path
- patch
- validation command
- validation result
- edge case handling

REJECT:
- broad rewrites
- speculative fixes
- unvalidated patches
