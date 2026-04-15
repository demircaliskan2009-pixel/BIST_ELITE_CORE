"""crypto_core.data — Complete crypto data layer.

Subsystems:
- models/      — Immutable typed event + state data models
- ingestion/   — WebSocket client abstraction + exchange adapters
- processing/  — Event routing, trade processing, order book management, OHLCV building
- validation/  — Fail-closed data integrity enforcement
- recovery/    — Connection recovery + snapshot protocol
"""
