# FAZ596: Example environment variables for live_session. NO SECRETS.
# Source: . .\tools\env_example.ps1
# Never commit secrets; this file contains none.

$env:BIST_SNAPSHOT_ROOT = "C:\path\to\data\eod\snapshots"
$env:BIST_CAPITAL_TRY = "30000"
$env:BIST_RISK_PCT = "0.02"
$env:BIST_ATR_N = "14"
$env:BIST_STOP_ATR_MULT = "2.0"
$env:BIST_TP_R_MULT = "2.0"
