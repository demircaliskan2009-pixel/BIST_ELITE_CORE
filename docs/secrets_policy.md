# Secrets Policy (FAZ600)

This repository is designed to be **offline-first** and **secrets-free** by default. Real broker integration must never introduce secrets or network access into shared code paths.

## Invariants

- **No secrets in git**  
  - No API keys, passwords, tokens, or private endpoints in:
    - Source code
    - Config files under `config/` that are checked into git
    - Docs, examples, or tests
- **No network by default**  
  - All tools and modules must run fully offline.
  - Any future real broker transport must be injected behind a config/feature flag and kept out of this repo.
- **Fail-closed**  
  - When real broker config or transport is missing, commands must *refuse* to run live and print a clear message.

## Broker config pattern

- Committed file: `config/broker.example.yaml`
  - Structure only; placeholder values.
  - Safe to share; **must not** contain real credentials.
- Local, untracked file: `config/broker.yaml`
  - Your actual broker config.
  - Add to `.gitignore` (never commit).
  - Reference secrets via **environment variables**, e.g.:

    ```yaml
    auth:
      api_key_env: BIST_BROKER_API_KEY
    ```

- Environment:
  - Set secrets only in your shell / OS keychain / secrets manager, **not** in this repo.

## broker_run.ps1 behavior

- `-Mode manual`
  - Offline, deterministic path (order ticket + fills CSV).
  - No secrets; no network.
- `-Mode real`
  - **Blocked in this phase.** The script fails-closed and prints a message pointing to this policy.
  - No network calls are made; no orders are sent.

Before wiring any real broker transport, update this document and ensure the design keeps secrets and network usage out of the shared codebase and automated test paths.

