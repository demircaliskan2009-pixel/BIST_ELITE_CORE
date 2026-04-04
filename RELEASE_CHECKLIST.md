# Release Checklist

Bu repo "fail-closed" prensibinde calisir. Bu checklist, release oncesi minimum dogrulama setidir.

## 0) Ortam
- Python: 3.12
- `pip install -e .` veya proje standart kurulum akisi

## 1) Test
- `pytest -q` -> YESIL

## 2) CLI Smoke
- `python -m bist_core.cli --help`
- `python -m bist_core.cli info --json`
- `python -m bist_core.cli healthcheck`

## 3) Broker config dogrulama
- `python -m bist_core.cli broker validate-config --config configs/broker_config.stub.example.json --schema configs/broker_config.schema.json`

## 4) Gateway Docker (PACK9)
- `.env` olustur (bkz: `.env.example`)
- `docker compose up --build`
- `curl http://localhost:8000/health` -> `{"ok": true}`

## 5) Security guardrails (network)
- Varsayilan: network kapali kalmali.
- OpenAI/model kullaniminda sadece `BIST_CORE_ALLOW_NETWORK=1` ile acilmali.

## 6) Artifact determinism (ornek)
- Ayni inputlarla iki kez calistir -> artifact alanlari/dosyalar deterministik olmali.
