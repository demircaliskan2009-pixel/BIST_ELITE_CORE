# Pipeline manifest (EOD run)

The EOD pipeline writes a JSON manifest to three locations (same content):

- `<outdir>/pipeline_manifest.json`
- `<outdir>/<day>/pipeline_manifest.json`
- `<outdir>/_pipeline_manifest.json` (backward compatibility)

## Schema version 2 (audit-grade)

| Field | Description |
|-------|-------------|
| `schema_version` | Integer; **2** (v1 keys retained where possible). |
| `run_id` | Unique run ID (UUID). |
| `started_at_utc` | Run start time in UTC (ISO 8601). |
| `finished_at_utc` | Run finish time in UTC (ISO 8601). |
| `day` | Run day (e.g. `YYYY-MM-DD`). |
| `snapshot_root` | Path to EOD snapshot root. |
| `outdir` | Pipeline output directory. |
| `stages` | Per-stage status; each stage has deterministic keys and a **provenance** block (inputs, inputs_hash). |
| `runtime_ms` | Total pipeline runtime in milliseconds. |

## Top-level provenance

`provenance` contains (stable key order):

- `python` — Python version string.
- `platform` — Platform string.
- `cli_args` — CLI arguments (sorted keys).
- `git_sha` — Git commit (if provided).
- `snapshot_hash` — EOD snapshot hash (`algo`, `value`) when available.
- `policy` — Policy file path and hash when used.

## Per-stage provenance

Each entry in `stages` includes a **provenance** object:

- `inputs` — Map of input names to hashes or refs (e.g. `snapshot`, `policy`).
- `inputs_hash` — Single hash for the stage’s inputs (e.g. snapshot sha256, policy sha256).

Stage keys and list fields (e.g. `notes`) are deterministically ordered for repeatability.

## Raw cache

- **`raw_cache`** — EOD snapshot provenance (path, sha256, cache_only) when the EOD provider (e.g. LocalCSV) exposes it.
- **`events.raw_cache`** — Events pull provenance (path, sha256, cache_only) from the events provider (e.g. KAP HTML) when events are pulled.

Both are optional; omit when the corresponding provider does not expose raw cache metadata.
