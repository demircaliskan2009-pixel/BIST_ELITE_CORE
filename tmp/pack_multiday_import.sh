#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/BIST_ELITE_CORE

COMPOSE_FILE=/opt/BIST_ELITE_CORE/docker-compose.yml
CID="$(docker compose -f "$COMPOSE_FILE" ps -q gateway)"
test -n "${CID:-}"

CSV=/opt/BIST_ELITE_CORE/data/inbox/multiday_eod.csv
test -f "$CSV"

echo "=== 1) CONTAINER STATUS ==="
echo "CID=$CID"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "=== 2) CSV PROFILE ==="
python3 - <<'PY'
import pandas as pd, json
p = "/opt/BIST_ELITE_CORE/data/inbox/multiday_eod.csv"
df = pd.read_csv(p)

if "date" not in df.columns or "symbol" not in df.columns:
    raise SystemExit("FAIL_MISSING_REQUIRED_COLUMNS_date_symbol")

d = pd.to_datetime(df["date"], errors="coerce")

payload = {
    "path": p,
    "rows": int(len(df)),
    "cols": list(df.columns),
    "days": int(d.dropna().dt.date.nunique()),
    "min_date": str(d.min().date()) if d.notna().any() else None,
    "max_date": str(d.max().date()) if d.notna().any() else None,
    "symbols": int(df["symbol"].astype(str).nunique()),
}
print(json.dumps(payload, ensure_ascii=False, indent=2))

if payload["days"] < 20:
    raise SystemExit("FAIL_DAYS_LT_20")
PY

echo
echo "=== 3) CLEAN SNAPSHOTS ==="
rm -rf /opt/BIST_ELITE_CORE/data/eod/snapshots/*
mkdir -p /opt/BIST_ELITE_CORE/data/eod/snapshots
find /opt/BIST_ELITE_CORE/data/eod/snapshots -maxdepth 2 | sed -n '1,50p'

echo
echo "=== 4) IMPORT -> SNAPSHOTS ==="
docker exec "$CID" sh -lc '
set -eu
cd /app
export PYTHONPATH=/app/src

python -m bist_core.cli data import \
  --input /app/data/inbox/multiday_eod.csv \
  --out /app/data/eod/snapshots \
  --date-col date \
  --symbol-col symbol
'

echo
echo "=== 5) TREE ==="
find /opt/BIST_ELITE_CORE/data/eod/snapshots -maxdepth 3 \( -type d -o -type f \) | sort | sed -n '1,240p'

echo
echo "=== 6) DOCTOR ==="
docker exec "$CID" sh -lc '
set -eu
cd /app
export PYTHONPATH=/app/src
python -m bist_core.cli data snapshots doctor --root /app/data/eod/snapshots --json
' | tee /tmp/doctor_multiday.json

echo
echo "=== 7) DOCTOR GUARD ==="
python3 - <<'PY'
import json
from pathlib import Path

txt = Path("/tmp/doctor_multiday.json").read_text(encoding="utf-8", errors="ignore")
obj = json.loads(txt)
days_count = obj.get("coverage_summary", {}).get("days_count", 0)
print({"days_count": days_count})
if days_count < 20:
    raise SystemExit("FAIL_DOCTOR_DAYS_LT_20")
PY

KEY="$(sed -n 's/^BIST_GATEWAY_API_KEY=//p' /opt/BIST_ELITE_CORE/.env | tr -d '\r' | head -n 1)"
test -n "${KEY:-}"

echo
echo "=== 8) LOCAL CHAT: scan top 3 ==="
curl -sS -D /tmp/chat_local_h.out \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -X POST http://127.0.0.1:8000/v1/chat \
  --data '{"message":"scan top 3","top_n":3}' \
  -o /tmp/chat_local_b.out \
  -w 'HTTP_CODE=%{http_code}\n'
sed -n '1,20p' /tmp/chat_local_h.out
cat /tmp/chat_local_b.out
echo

echo "=== 9) PUBLIC CHAT: scan top 3 ==="
curl -sS -D /tmp/chat_pub_h.out \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -X POST https://api.bistpiyasaaygiri.org/v1/chat \
  --data '{"message":"scan top 3","top_n":3}' \
  -o /tmp/chat_pub_b.out \
  -w 'HTTP_CODE=%{http_code}\n'
sed -n '1,20p' /tmp/chat_pub_h.out
cat /tmp/chat_pub_b.out
echo

echo "=== 10) LOCAL CHAT: symbol smoke ==="
curl -sS \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -X POST http://127.0.0.1:8000/v1/chat \
  --data '{"message":"ASELS için kısa vade senaryo üret"}' | tee /tmp/chat_symbol_local.out
echo

echo "=== 11) HISTORY GUARD ==="
python3 - <<'PY'
from pathlib import Path

local_scan = Path("/tmp/chat_local_b.out").read_text(encoding="utf-8", errors="ignore")
pub_scan   = Path("/tmp/chat_pub_b.out").read_text(encoding="utf-8", errors="ignore")
sym_local  = Path("/tmp/chat_symbol_local.out").read_text(encoding="utf-8", errors="ignore")

bad_local = "InsufficientHistory: 1 < 20" in local_scan or "No snapshots; provide day or run eod pipeline" in local_scan
bad_pub   = "InsufficientHistory: 1 < 20" in pub_scan   or "No snapshots; provide day or run eod pipeline" in pub_scan
bad_sym   = "InsufficientHistory: 1 < 20" in sym_local  or "No snapshots; provide day or run eod pipeline" in sym_local

print({
    "local_scan_old_error": bad_local,
    "public_scan_old_error": bad_pub,
    "local_symbol_old_error": bad_sym
})

if bad_local or bad_pub or bad_sym:
    raise SystemExit("FAIL_OLD_HISTORY_ERROR_STILL_PRESENT")
PY

echo
echo "=== OK: 20+ bar kanıtlandı; paid integration readiness gate açıldı ==="
