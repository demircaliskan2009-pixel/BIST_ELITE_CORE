# Live Test Runbook

## Amaç
Gateway `/v1/chat` çağrılarından çıkan önerileri otomatik olarak
`data/live_test/recommendations.jsonl` dosyasına yazmak.

## Env
- `BIST_LIVE_TEST_AUTOLOG=1`
- `BIST_LIVE_TEST_ROOT=/app/data/live_test`

## Kayıt Türleri
- `mode=ask` -> tek sembol önerisi
- `mode=scan` -> scan adayları

## Saklanan Metadata
- `request_id`
- `message`
- `top_n` (scan ise)
- `client_host`
- `mode`

## CLI Komutları

### Stats
`python -m bist_core.live_test.cli --root data/live_test stats`

### List
`python -m bist_core.live_test.cli --root data/live_test list --limit 20`

### Manuel log
`python -m bist_core.live_test.cli --root data/live_test log --source gateway_chat --symbol AKBNK --day 2026-02-27 --decision WATCH`

### Manuel close
`python -m bist_core.live_test.cli --root data/live_test close --id <REC_ID> --outcome-label win --realized-return-r 1.0`

## Kanıtlanan Durum
- `/v1/chat` aktif
- VPS autolog aktif
- UTF-8 Türkçe metadata doğru saklanıyor
- `recommendations.jsonl` host üzerinde oluşuyor

## Daily Close Tek Komut
`python -m bist_core.live_test.daily_close --root data/live_test --snapshot-root data/eod/snapshots --max-holding-days 5`

Bu komut:
- açık kayıtları değerlendirir
- `report.json` üretir
- `report_records.csv` üretir
- günlük kapanış özetini tek JSON çıktı ile verir
