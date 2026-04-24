# PRDV4 HOOK ENGINE CONTRACT

## PURPOSE
Enforce deterministic execution discipline at runtime.

## EXECUTION FLOW

1. User input received
2. PRE-RESPONSE HOOK runs
3. If any rule fails → STOP → OUTPUT: "INSUFFICIENT EVIDENCE"
4. Agent generates response
5. POST-RESPONSE HOOK runs
6. If structure invalid → REJECT response

## HARD RULES

- No response without task classification
- No response without prompt selection
- No response with missing data
- No generic/template output
- All outputs must follow 5-section contract
