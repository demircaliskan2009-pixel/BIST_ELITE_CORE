---
name: "Product Value Implementation Rules"
description: "Primary implementation mode for crypto_core with audit-first, bounded slices, and local proof-driven validation"
applyTo: "**"
---

# PRODUCT VALUE IMPLEMENTATION MODE

This is the default implementation mode.

## Core Behavior

- Run a read-only product audit before code implementation when scope is not already proven.
- Execute one bounded implementation slice at a time.
- Fail closed on missing evidence.
- crypto_core only.
- No live/private APIs, order routing, scheduler changes, or BIST implementation expansion.

## Target Product Layers

- edge intake
- strategy specification
- data registry and PIT parity
- leakage, bias, and repaint validator
- backtest and replay
- paper sleeve
- decision ledger
- allocator to risk bridge
- execution simulator

## Local Validation Contract

For each bounded implementation slice:

1. ruff check --fix
2. ruff format
3. ruff format --check
4. ruff check
5. targeted pytest
6. full tests/crypto_core
7. readiness and connector probes when relevant
8. git diff --check

No merge if any validation step fails.
