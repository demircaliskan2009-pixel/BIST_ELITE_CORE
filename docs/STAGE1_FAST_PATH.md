# Stage-1 Fast Path: Risk Plan → Order Ticket

One-command path from `risk_plan_h{H}.csv` to Midas-ready order ticket (CSV + TXT).

## Overview

1. **risk_plan_h{H}.csv** — ATR-based position sizing (FAZ585)
2. **orders_intent_draft_h{H}.json** — Draft orders intent (FAZ587)
3. **order_ticket.csv + order_ticket.txt** — Midas-ready ticket (FAZ582)

## One Command

```powershell
.\tools\midas_ticket_from_risk_plan.ps1 -Day 2025-03-15 -Horizon 1 -Top 5
```

Produces:
- `data/log/reports/2025-03-15/orders_intent_draft_h1.json`
- `data/out/order_ticket/2025-03-15/order_ticket.csv`
- `data/out/order_ticket/2025-03-15/order_ticket.txt`

## Step-by-Step (Manual)

```bash
# 1) Convert risk_plan to orders_intent draft
python tools/orders_intent_from_risk_plan.py --day 2025-03-15 --horizon 1 --top 5 --reports-root data/log/reports

# 2) Export to ticket
python tools/order_ticket_export.py --orders data/log/reports/2025-03-15/orders_intent_draft_h1.json --out data/out/order_ticket/2025-03-15
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--side` | BUY | BUY or SELL |
| `--order-type` | MARKET | MARKET or LIMIT |
| `--limit-price-mode` | NONE | NONE or LAST_CLOSE (requires snapshot for close) |

## Draft Semantics

- **draft: true** — Never treat as executable automation; human review required.
- **draft_reason: "generated_from_risk_plan"** — Source of the draft.
- **qty==0** — Skipped from actions; listed in `skipped` with reason (e.g. TooSmall, InsufficientHistory).

## Prerequisites

- `risk_plan_h{H}.csv` must exist under `data/log/reports/<DAY>/`
- Run `risk_sizer.py` (or live pipeline) first to generate the risk plan.
