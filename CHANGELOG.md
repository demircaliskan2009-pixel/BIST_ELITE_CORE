# Changelog

All notable changes are tracked by phase. Format: `[fazNNN] YYYY-MM-DD — summary`.

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
- [faz390] — KAP ingestion fixture minimal parse without network
- [faz391] — KAP event dedupe by id first-wins deterministic
- [faz393] — scoreboard leakage guard date less than as_of
- [faz405] — KAP empty cache no crash
- [faz395] — config validation on load (strict schema)
- [faz397] — changelog discipline (CHANGELOG.md, append script)
- [faz551] — packaging smoke test (python -m build sdist + wheel)
