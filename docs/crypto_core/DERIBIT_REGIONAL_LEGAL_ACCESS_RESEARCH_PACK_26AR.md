# Deribit Regional Legal Access — Deep Research Pack (Phase 26AR)

status: RESEARCH_PACK
phase: 26AR
reviewed_at_iso: 2026-05-19T00:00:00Z
scope: TURKEY_PUBLIC_MARKET_DATA_ONLY_NO_LOGIN_NO_PRIVATE_API_NO_ORDERS_NO_LIVE

> **NON-LEGAL-ADVICE NOTICE**: This document is a factual summary of
> publicly available Deribit documentation for the sole purpose of
> operator claim review. It does not constitute legal advice. An
> operator considering live trading or private API access must obtain
> independent legal counsel.

---

## Machine-Readable Verdict Block

```
VERDICT=TURKEY_PUBLIC_MARKET_DATA_DOCS_CLEAR_ENOUGH_FOR_OPERATOR_REVIEW
TURKEY_RESTRICTED_STATUS=NO
PUBLIC_MARKET_DATA_RESTRICTION_STATUS=UNCLEAR_NO_EXPLICIT_SEPARATE_PUBLIC_DATA_GEO_BAN_FOUND
UNAUTH_PUBLIC_API_STATUS=YES
REGIONAL_LEGAL_ACCESS_ROW=LEGAL_DOC_PROOF_READY_NOT_APPROVED
REGIONAL_LEGAL_ACCESS_REVIEW_ROW=LEGAL_REVIEW_READY_FOR_OPERATOR_SIGNOFF
SEPARATE_CONNECTOR_ENABLEMENT_ROW=DEFER_SEPARATE_PHASE
CAN_APPROVE_CLAIM_ROW_NOW=YES_WITH_OPERATOR_METADATA_AND_SCOPE_LIMITS
CAN_APPROVE_POLICY_LEGAL_ROW_NOW=NO_AUTOMATIC_APPROVAL_OPERATOR_SIGNOFF_REQUIRED
CAN_ENABLE_CONNECTOR_NOW=NO
CONFIDENCE=MEDIUM
```

---

## Official Source References

| source_id | url | description |
|---|---|---|
| `DERIBIT_RESTRICTED` | `https://docs.deribit.com/#restricted-countries` | Restricted Jurisdictions page |
| `DERIBIT_ENVIRONMENT` | `https://docs.deribit.com/#json-rpc-over-websocket` | JSON-RPC Protocol (unauthenticated public API) |
| `DERIBIT_TERMS_PANAMA` | `https://www.deribit.com/kb/terms` | DRB Panama Inc. Terms of Service |
| `DERIBIT_TERMS_FZE` | `https://www.deribit.com/kb/terms` | Deribit FZE Terms of Service |
| `DERIBIT_DOCS_LLMS` | `https://docs.deribit.com/llms.txt` | Public API documentation index (unauthenticated access confirmed) |

All source URLs are already listed in the Phase 22L source snapshot manifest.

---

## Finding F-1: Turkey Not Listed in Restricted Jurisdictions

The Deribit Restricted Countries page (`#restricted-countries`) lists
jurisdictions where Deribit services are unavailable. Based on the
documentation snapshot hashed in Phase 22L
(`source_sha256: a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`),
**Turkey is not listed** in the restricted jurisdictions enumeration.

The restricted jurisdictions list includes named regions such as the United
States of America, Ontario (Canada), Cuba, Iran, North Korea, Sudan, Syria,
and other OFAC/sanctioned regions. Turkey does not appear in this list.

**Confidence**: MEDIUM — Documentation snapshots may change. No real-time
verification was performed in Phase 26AR. The Phase 22L snapshot is the
authoritative evidence base for this claim.

---

## Finding F-2: Unauthenticated Public API Is Documented

The Deribit JSON-RPC documentation (`#json-rpc-over-websocket`) explicitly
documents that certain methods are available to unauthenticated (public)
connections. The public WebSocket API endpoint does not require credentials
for public-data methods including:

- `public/get_instruments`
- Orderbook subscriptions via the notifications feed
- Ticker subscriptions

This is consistent with the live observations recorded in the Phase 25M
public smoke-proof record (`DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md`).

**Confidence**: HIGH for the unauthenticated API availability claim.

---

## Limitation L-1: No Turkey-Specific Affirmative Legal Clearance

No Deribit documentation provides an explicit affirmative legal clearance
for Turkey-based operators to access Deribit services. The documentation
only asserts what is restricted; it does not assert what is permitted.

Absence of Turkey from the restricted list implies potential access is not
blocked by documented restrictions, but does not constitute a legal
affirmation that access is permitted.

---

## Limitation L-2: No Separate Public-Market-Data-Only Geo Safe Harbor

NO_EXPLICIT_PUBLIC_DATA_GEO_SAFE_HARBOR

Deribit's terms and documentation do not contain a geo safe harbor
specifically for public-market-data-only machine access. The terms apply
broadly to use of Deribit services.

The claim that public market data access is legally permissible from Turkey
cannot be derived solely from the absence of Turkey in the restricted list.

---

## Limitation L-3: Market Data Personal-Use-Only Without Prior Written Approval

MARKET_DATA_PERSONAL_USE_ONLY_WITHOUT_PRIOR_WRITTEN_APPROVAL

The Deribit Terms of Service (both DRB Panama and Deribit FZE variants)
contain provisions that market data and derived data are for personal use
only unless prior written approval has been obtained from Deribit. Any
redistribution, commercial use, or bulk data extraction requires
separate written authorization.

**Impact**: This limitation applies to the operator claim review. The
`regional_legal_access` claim row approval is scoped to
`PUBLIC_MARKET_DATA_ONLY` with no login, no private API, no orders,
and no live execution. Redistribution and commercial data use are
explicitly excluded from this scope.

---

## Limitation L-4: Documentation Snapshot Caveat

All evidence is based on the Phase 22L documentation snapshot
(`source_sha256: a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`).
Deribit may update its terms and restricted-countries list at any time.
This research pack does not provide real-time legal monitoring.

---

## Summary

| finding | value |
|---|---|
| Turkey in restricted list | NO |
| Unauthenticated public API documented | YES |
| Turkey-specific legal clearance | NOT FOUND |
| Public-data-only geo safe harbor | NOT FOUND |
| Market data personal-use limitation | YES |
| Can approve claim row with scope limits | YES_WITH_OPERATOR_METADATA |
| Can approve policy legal review row automatically | NO |
| Can enable connector | NO |

---

## Claim and Policy Row Status

| row | surface | status |
|---|---|---|
| `regional_legal_access` | `claim_review` | `LEGAL_DOC_PROOF_READY_NOT_APPROVED` |
| `regional_legal_access_review` | `policy_review` | `LEGAL_REVIEW_READY_FOR_OPERATOR_SIGNOFF` |
| `separate_connector_enablement` | `policy_review` | `DEFER_SEPARATE_PHASE` |

---

## What Is NOT Authorized by This Research Pack

- No connector enablement
- No paper, shadow, or live trading integration
- No private API access, credentials, or order submission
- No registry (`static_registry_verified`) change
- No `public_feed_dialects.py` change
- No approval of `regional_legal_access_review` policy row
- No approval of `separate_connector_enablement` policy row

---

## Evidence References

- `DERIBIT_CLAIM_REVIEW_WORKSHEET.md` — claim row under review
- `DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md` — policy rows under review
- `DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md` — Phase 22L source hashes
- `DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md` — Phase 26AS proof classification
- `DERIBIT_OPERATOR_LEGAL_SIGNOFF_PROPOSAL_26AT.md` — operator signoff proposal
