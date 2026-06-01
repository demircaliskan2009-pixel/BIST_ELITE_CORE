---
name: crypto-product-layer-audit
description: "Read-only audit of crypto_core product layers with gap ranking and one next bounded PR recommendation."
agent: agent
---

Run a read-only product-layer audit.

Rules:
- no edits
- no branch/commit/PR actions
- crypto_core scope only
- fail closed on missing evidence

Inventory these layers:
1. edge intake
2. strategy spec
3. data registry
4. leakage and bias validator
5. backtest and replay
6. paper sleeve
7. decision ledger
8. allocator-risk bridge
9. execution simulator
10. venue and readiness

For each layer:
- classify as IMPLEMENTED, PARTIAL, ARTIFACT_ONLY, or MISSING
- cite evidence
- mark Deep Research needed: yes/no

Output:
- layer inventory table
- top 5 gaps by impact
- exactly one next PR recommendation with bounded files and tests
