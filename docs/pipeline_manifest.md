# Pipeline manifest (EOD run)

The EOD pipeline writes a JSON manifest to three locations (same content):

- `<outdir>/pipeline_manifest.json`
- `<outdir>/<day>/pipeline_manifest.json`
- `<outdir>/_pipeline_manifest.json` (backward compatibility)

## Top-level fields

| Field | Description |
|-------|-------------|
| `schema_version` | Integer; currently `1`. |
| `day` | Run day (e.g. `YYYY-MM-DD`). |
| `snapshot_root` | Path to EOD snapshot root. |
| `outdir` | Pipeline output directory. |
| `stages` | Per-stage status (snapshot, advice, dossier, events, instruments, corporate_actions, universe, calendar, policy). |
| `runtime_ms` | Total pipeline runtime in milliseconds. |

## Provenance

`provenance` contains:

- `python` — Python version string.
- `platform` — Platform string.
- `cli_args` — CLI arguments passed to the run.
- `git_sha` — Git commit (if provided).
- `snapshot_hash` — EOD snapshot hash (`algo`, `value`) when available.
- `policy` — Policy file path and hash when used.

## Raw cache

- **`raw_cache`** — EOD snapshot provenance (path, sha256, cache_only) when the EOD provider (e.g. LocalCSV) exposes it.
- **`events.raw_cache`** — Events pull provenance (path, sha256, cache_only) from the events provider (e.g. KAP HTML) when events are pulled.

Both are optional; omit when the corresponding provider does not expose raw cache metadata.
