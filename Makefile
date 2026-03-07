SHELL := /bin/sh

.PHONY: test gateway-build gateway-up gateway-down gateway-logs gateway-health

test:
    pytest -q

gateway-build:
    docker compose build

gateway-up:
    docker compose up --build

gateway-down:
    docker compose down -v

gateway-logs:
    docker compose logs -f --tail=200

gateway-health:
    python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
