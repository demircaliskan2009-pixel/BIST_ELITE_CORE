---
name: crypto-product-slice-runner
description: "Execute one bounded crypto_core product implementation slice with strict local validation and PR closeout."
agent: agent
---

Execute exactly one bounded implementation slice.

Rules:
- crypto_core only
- no live/private API, order routing, or scheduler work
- fail closed on missing evidence
- no broad refactor

Required inputs:
- exact files in scope
- exact tests in scope
- explicit done condition

Execution contract:
1. patch bounded files only
2. run validation:
   - ruff check --fix
   - ruff format
   - ruff format --check
   - ruff check
   - targeted pytest
   - full tests/crypto_core
   - readiness/connector probes when relevant
   - git diff --check
3. open PR
4. poll CI and CodeQL to terminal state
5. standard merge only
6. post-verify main

Stop if external or current facts are required and repository evidence is insufficient.
Output DEEP_RESEARCH_REQUIRED in that case.
