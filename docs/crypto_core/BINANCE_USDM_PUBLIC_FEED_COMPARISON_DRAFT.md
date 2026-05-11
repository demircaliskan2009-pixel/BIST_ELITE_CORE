# Binance USD-M Public Feed Comparison Draft

Status: `COMPARISON_ONLY`.

This document is a compact comparison draft for future research. It is not an
official evidence package, does not select Binance USD-M as connector-ready, and
does not enable any static registry dialect.

Guardrail: this is not an official evidence package.

## Safety

- No connector implementation.
- No network, REST, or WebSocket client.
- No private API.
- No credentials, API keys, or environment reads.
- No live execution or order path.
- No registry enablement.

## Official-Source-Mapped Comparison Items

The following items are supplied research mappings only. Every item still needs
independently reproducible content hashes, retrieval metadata, and manual review
before it can become an operational evidence package.

### REST Snapshot And WS Diff Book Depth

- `source_id`: `BINANCE_USDM_DIFF_BOOK_DEPTH`
- `official_url`: `https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams`
- `retrieval_date`: `2026-05-09`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE`
- `manual_hash_required`: `YES`
- `claim_mapping`: USD-M diff book depth stream exists and must be paired with a REST snapshot for reconstruction.

### U/u/pu Sequence Semantics

- `source_id`: `BINANCE_USDM_DIFF_BOOK_DEPTH`
- `official_url`: `https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams`
- `retrieval_date`: `2026-05-09`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE`
- `manual_hash_required`: `YES`
- `claim_mapping`: `U`, `u`, and `pu` sequence fields describe diff-book continuity.

### pu Mismatch Resync Rule

- `source_id`: `BINANCE_USDM_DIFF_BOOK_DEPTH`
- `official_url`: `https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Diff-Book-Depth-Streams`
- `retrieval_date`: `2026-05-09`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE`
- `manual_hash_required`: `YES`
- `claim_mapping`: `pu` mismatch requires local order-book resynchronization.

### Mark, Index, And Funding Feed

- `source_id`: `BINANCE_USDM_MARK_PRICE`
- `official_url`: `https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Mark-Price-Stream`
- `retrieval_date`: `2026-05-09`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE`
- `manual_hash_required`: `YES`
- `claim_mapping`: Mark price, index price, and funding-rate fields are available as public market-data signals.

### Open Interest REST

- `source_id`: `BINANCE_USDM_OPEN_INTEREST`
- `official_url`: `https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest`
- `retrieval_date`: `2026-05-09`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE`
- `manual_hash_required`: `YES`
- `claim_mapping`: Open interest is available through a public REST market-data endpoint.

### Connection And Rate-Limit Evidence

- `source_id`: `BINANCE_USDM_WEBSOCKET_LIMITS`
- `official_url`: `https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams`
- `retrieval_date`: `2026-05-09`
- `content_hash`: `CONTENT_HASH_UNAVAILABLE`
- `manual_hash_required`: `YES`
- `claim_mapping`: Connection and stream limits require manual review before connector authorization.

## Connector Readiness

- `comparison_only`: `true`
- `evidence_package`: `false`
- `enabled_for_connector`: `false`
- `static_registry_verified`: `false`
- `connector_ready_dialects_expected`: `[]`
