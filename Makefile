SHELL := /bin/sh

.PHONY: test test-slow test-full gateway-build gateway-up gateway-down gateway-logs gateway-health

test:
	pytest -q

# MANDATORY: run weekly and before every release
# Executes all tests including slow end-to-end pipeline tests
test-slow:
	pytest -q --runslow

# Alias for pre-release gate: full suite with coverage
test-full:
	pytest -q --runslow --cov=src --cov-report=term --cov-fail-under=70
    docker compose build

gateway-up:
    docker compose up --build

gateway-down:
    docker compose down -v

gateway-logs:
    docker compose logs -f --tail=200

gateway-health:
    python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"

PY ?= python
LIVE_TEST_ROOT ?= data/live_test
SNAPSHOT_ROOT ?= data/eod/snapshots

live-test-stats:
    $(PY) -m bist_core.live_test.cli --root $(LIVE_TEST_ROOT) stats

live-test-daily-close:
    $(PY) -m bist_core.live_test.daily_close --root $(LIVE_TEST_ROOT) --snapshot-root $(SNAPSHOT_ROOT) --max-holding-days 5
