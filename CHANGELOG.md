# Changelog

All notable changes are tracked by phase. Format: `[fazNNN] — summary`.

## Phases

- [faz126] — Matriks/CSV ingestion hardening
- [faz127] — snapshots doctor --symbol bars_count lookback
- [faz128] — snapshots doctor missing days in range
- [faz129] — data import --mapping auto|strict
- [faz130] — data import --schema-report
- [faz134] — import encoding fallback utf-8 then latin-1
- [faz135] — snapshot schema version proof tests
- [faz136] — risk sizing from capital, max_loss, stop distance
- [faz139] — advice artifact schema golden HOLD proof tests
- [faz140] — evidence pack structure source and hash
- [faz142] — HOLD reason and next_action in artifact
- [faz143] — content_sha256 in advice artifact for reproducibility
- [faz144] — bars_count and lookback_required in advice JSON
- [faz155] — KAP cache loader BIST_KAP_CACHE_DIR
- [faz368] — CLI surface golden proof
- [faz386] — gates outcomes PASS FAIL JSON schema
- [faz387] — evidence stabilization sorted signals keys deterministic JSON
- [faz388] — scan artifact schema_version generated_at required keys
- [faz389] — scan stable ordering tie break by symbol ascending
- [faz390] — KAP ingestion fixture minimal parse without network
- [faz391] — KAP event dedupe by id first-wins deterministic
- [faz392] — scoreboard schema_version day params metrics keys
- [faz393] — scoreboard leakage guard date less than as_of
- [faz395] — config validation on load (strict schema)
- [faz397] — changelog discipline (CHANGELOG.md, append script)
- [faz405] — KAP empty cache no crash
- [faz145] — scan liquidity filter min volume turnover
- [faz146] — scan exclusions support exclude symbols
- [faz147] — scan scoring rationale 1-line per ranked symbol
- [faz148] — scan --out artifact save ranked list JSON
- [faz149] — scan stable ordering deterministic tie-break
- [faz150] — scan drill-down determinism same params produce same ask command
- [faz151] — scan top_n validation within bounds reject zero
- [faz152] — scan artifact schema stable JSON
- [faz546] — registry uses normalize_symbol uppercase trim on load
- [faz547] — snapshots use normalize_symbol on read
- [faz548] — symbol normalization shared helper uppercase trim
- [faz549] — snapshot malformed row detection missing symbol invalid close
- [faz550] — snapshot invalid rows report JSON format non-zero exit
- [faz551] — packaging smoke test (python -m build sdist + wheel)
- [faz552] — API deterministic CLI parity (schema_version, ask/scan match CLI --json)
- [faz553] — Theta3 security guardrails network validation CLI sandbox
- [faz554] — ask interactive chat prompt symbol day params
- [faz555] — risk sizing edge cases zero capital extreme max_loss fail-closed
- [faz556] — orders export CSV JSON schema --out orders_meta format
- [faz557] — plan/orders corner cases empty symbols empty plan FAIL invalid date
- [faz558] — E2E multi-day scenario eod run plan orders golden regression tests
- [faz559] — security sanity guards no os.system whitelisted imports ruff config
- [faz560] — AI interface SDK docs version endpoint chat agent flow
- [faz561] — strategy registry (logger) ask/scan append to strategies.jsonl
- [faz562] — outcome evaluation for strategies (stop/target, R-multiple, strategy_outcomes.jsonl)
