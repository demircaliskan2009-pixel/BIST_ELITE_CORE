# KAP Backfill Resume Script
# Probes rate limit once, then runs backfill if API is available.
# Usage: .\scripts\kap_backfill_resume.ps1
# Re-run after rate limit cooldown (~15-30 min between batches).

$ErrorActionPreference = "Stop"
$env:BIST_CORE_ALLOW_NETWORK = "1"

Write-Host "Probing KAP API..."
$probe = python -c @"
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
req = Request(
    'https://www.kap.org.tr/tr/api/disclosure/members/byCriteria',
    data=json.dumps({'fromDate': '2025-06-06', 'toDate': '2025-06-06'}).encode(),
    headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json;charset=UTF-8', 'Accept': 'application/json'}
)
try:
    resp = urlopen(req, timeout=30)
    print(f'OK:{len(resp.read())}')
except HTTPError as e:
    print(f'BLOCKED:{e.code}')
except Exception as e:
    print(f'ERROR:{e}')
"@ 2>&1

if ($probe -match "^OK:") {
    $current = (Get-ChildItem data/events/*.jsonl -ErrorAction SilentlyContinue).Count
    Write-Host "API available. Current files: $current / 390"
    Write-Host "Starting backfill with 3s delay..."
    python scripts/kap_backfill.py --from 2024-09-02 --to 2026-02-27 --delay 3.0 --timeout 30 --max-consecutive-empty 5
    $after = (Get-ChildItem data/events/*.jsonl -ErrorAction SilentlyContinue).Count
    Write-Host "Batch complete. Files: $after / 390"
    if ($after -ge 390) {
        Write-Host "BACKFILL COMPLETE."
    } else {
        Write-Host "Rate limit hit again. Wait ~15-30 min and re-run this script."
    }
} elseif ($probe -match "BLOCKED:429") {
    $current = (Get-ChildItem data/events/*.jsonl -ErrorAction SilentlyContinue).Count
    Write-Host "Rate limit still active (429). Current files: $current / 390"
    Write-Host "Wait ~15-30 min and try again."
} else {
    Write-Host "Unexpected response: $probe"
}
