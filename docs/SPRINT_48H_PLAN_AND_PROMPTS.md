# BIST Advisory Robot — 48-Hour Sprint Plan & Prompt Pack

## A) Prioritized 48-Hour Plan (Measurable DoD per Step)

| # | Step | DoD | Est. |
|---|------|-----|------|
| 1 | **NoDecision → HOLD + explicit reason + coverage** | All fail-closed paths return `decision_raw=HOLD`; `_advice_payload` includes `bars_count`, `lookback_required`, `reason`; tests pass | 2h |
| 2 | **`snapshots doctor`** | CLI `data snapshots doctor` reports root/day/symbol coverage; no external shell; tests pass | 2h |
| 3 | **`data import`** | Single CSV (Matriks-style TR decimals) → daily snapshots; `--input`, `--out`; tests pass | 3h |
| 4 | **`scan --interactive`** | Wizard (horizon/risk/capital/max_loss/top_n/liquidity/exclusions) → ranked candidates + drill-down command | 4h |
| 5 | **Output template + JSON artifact** | Consistent report sections (Decision, Entry/Stop/Targets, Evidence, Cause-Effect); JSON saved to file and path printed | 2h |
| 6 | **Offline KAP cache ingestion** | Minimal ingest from local KAP HTML cache; events in evidence pack | 3h |
| 7 | **Walk-forward / backtest scoreboard** | Proof-oriented report; no overfit claims | 3h |
| 8 | **Risk gate enhancements** | VBTS/exclusions hooks if present; BIST-only advisory | 2h |
| 9 | **Optional local chat UI** | FastAPI wrapper around ask/scan; scope guard; network OFF; LLM explanation only | 4h |

---

## B) Prompt Pack (12–16 Prompts)

---

### Prompt-1: Fix NoDecision → HOLD + explicit reason + coverage

**Goal & rationale:** Replace any ambiguous "NoDecision" or fail-closed PASS with HOLD + explicit reason (e.g. InsufficientHistory, NoBars) + coverage metrics (bars_count, lookback_required). Fail-closed must always be HOLD.

**Files to edit:**
- `src/bist_core/services/advisor.py`
- `src/bist_core/cli/main.py`
- `tests/test_faz118_insufficient_history_returns_hold.py`
- `tests/test_faz8_advisor_failclosed_reasons.py` (adjust if needed)

**Exact changes:**
1. In `advisor.py`:
   - Change `_safe_advice` to return `decision_raw="HOLD"` (not PASS) and include `reason` in text (e.g. "NoBars", exception name).
   - Add optional `coverage` dict to Advice or extend text: `bars_count`, `lookback_required` for both `_safe_advice` and `_insufficient_history_advice`.
   - Ensure `_insufficient_history_advice` text explicitly includes `bars_count` and `lookback_required`.
2. In `main.py`:
   - Update `_advice_payload` to include `reason`, `bars_count`, `lookback_required` when available (extend Advice dataclass or derive from text).
   - Update `_fallback_payload` to use `decision_raw="HOLD"` and include `reason`.
3. Add/extend Advice dataclass with optional `reason`, `bars_count`, `lookback_required` fields; populate in `_safe_advice` and `_insufficient_history_advice`.

**Tests to add/modify:**
- `tests/test_faz118_insufficient_history_returns_hold.py`: assert `bars_count`, `lookback_required` in payload or text.
- `tests/test_faz8_advisor_failclosed_reasons.py`: assert `decision_raw == "HOLD"` and `"nobars" in text.lower() or "nodecision" in text.lower()` (or equivalent reason).
- New: `tests/test_faz121_hold_reason_and_coverage.py`: NoBars → HOLD + reason; exception → HOLD + reason; coverage in JSON output.

**DoD checklist:**
- [ ] `decision_raw` is never "PASS" for fail-closed (NoBars, InsufficientHistory, exceptions).
- [ ] `reason` appears in text and JSON.
- [ ] `bars_count`, `lookback_required` appear when applicable.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-2: Add CLI `snapshots doctor` command

**Goal & rationale:** Debug snapshot root/day/symbol coverage without external shell tricks. Pure Python/CLI.

**Files to edit:**
- `src/bist_core/cli/main.py`
- `tests/test_faz118_doctor_command.py` (or new `tests/test_faz122_snapshots_doctor.py`)

**Exact changes:**
1. Add subparser under `data`: `data snapshots doctor` (or `snapshots doctor` as top-level if preferred; user said "snapshots doctor").
2. If `snapshots` is a subcommand of `data`, add: `p_snapshots = sub_data.add_parser("snapshots")` with `sub_snapshots = p_snapshots.add_subparsers(dest="snapshots_cmd", required=True)`, then `p_doctor = sub_snapshots.add_parser("doctor")`.
3. Implement `_cmd_snapshots_doctor(args)`:
   - Resolve snapshot root: `--root` or `BIST_CORE_SNAPSHOT_DIR` or `data/eod/snapshots`.
   - Scan `root/YYYY-MM-DD/snapshot.csv` for each day dir.
   - Output: root path, list of days, symbols per day, total symbols, any missing/invalid files.
   - `--json` for machine-readable: `{root, days: [...], symbols_by_day: {...}, coverage_summary: {...}}`.
4. No subprocess/shell; use `Path.iterdir()`, `Path.is_file()`, pandas or csv for row count.

**Tests to add/modify:**
- `tests/test_faz122_snapshots_doctor.py`: tmp_path with `snapshots/2099-01-01/snapshot.csv`, run doctor, assert day and symbol in output; `--json` valid JSON with expected keys.

**DoD checklist:**
- [ ] `python -m bist_core.cli data snapshots doctor` (or equivalent) runs.
- [ ] Output shows root, days, symbol coverage.
- [ ] `--json` returns valid schema.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-3: Add `data import` command

**Goal & rationale:** Ingest a single CSV export (Matriks-style, TR decimals supported) and split into daily snapshots under `data/eod/snapshots/YYYY-MM-DD/snapshot.csv`.

**Files to edit:**
- `src/bist_core/cli/main.py`
- `tests/test_faz123_data_import.py` (new)

**Exact changes:**
1. Add `data import` subparser: `--input` (required), `--out` (default: `data/eod/snapshots`), `--date-col` (default: `date` or infer), `--symbol-col` (default: `symbol`).
2. Implement `_cmd_data_import(args)`:
   - Read CSV with pandas.
   - Support TR decimals: `30.000` → 30000, `30,5` → 30.5 (reuse `_parse_tr_number` logic for numeric cols if needed, or use locale-aware parsing).
   - Required columns: `symbol`, `close`; optional: `open`, `high`, `low`, `volume`, `turnover`, `date`.
   - If CSV has `date` column: group by date, write `out/YYYY-MM-DD/snapshot.csv` per day.
   - If no `date`: require `--day` and treat entire file as single day.
   - Schema: `symbol,close,date` (and optional OHLCV); fail-closed on invalid schema.
3. Windows-safe writes: atomic or temp+replace.

**Tests to add/modify:**
- `tests/test_faz123_data_import.py`: CSV with `symbol,close,date` and TR decimals; assert daily snapshots created; schema valid.

**DoD checklist:**
- [ ] `python -m bist_core.cli data import --input file.csv --out data/eod/snapshots` creates daily dirs.
- [ ] TR decimals parsed correctly.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-4: Implement `scan --interactive` wizard + ranked output + drill-down

**Goal & rationale:** Interactive scan: horizon/risk/capital/max_loss/top_n/liquidity/exclusions. Returns ranked candidates + short rationales; drill-down command per symbol.

**Files to edit:**
- `src/bist_core/cli/main.py`
- `src/bist_core/advisory/generate.py` (or new scan module)
- `tests/test_faz124_scan_interactive.py` (new)

**Exact changes:**
1. Add `scan` command (or `eod scan`): `--interactive` triggers wizard.
2. Wizard prompts: horizon (short/mid/long), risk (low/med/high), capital (TL), max_loss (TL), top_n, liquidity min (optional), exclusions (comma-separated symbols, optional).
3. Use `build_advice_for_symbol` for each symbol in snapshot; rank by score; output top N with short rationale (1-line per symbol).
4. Drill-down: print `python -m bist_core.cli ask SYMBOL --day YYYY-MM-DD --interactive` for each symbol so user can run manually.
5. Deterministic ordering; no randomness.

**Tests to add/modify:**
- `tests/test_faz124_scan_interactive.py`: non-interactive mode (all args passed) produces ranked list; drill-down command format correct.

**DoD checklist:**
- [ ] `scan --interactive` prompts for missing params.
- [ ] Ranked output with rationales.
- [ ] Drill-down command printed per symbol.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-5: Output template upgrade + structured JSON artifact

**Goal & rationale:** Consistent report sections (Decision, Entry/Stop/Targets, Evidence, Cause-Effect) and save JSON artifact to file; print path.

**Files to edit:**
- `src/bist_core/services/advisor.py`
- `src/bist_core/cli/main.py`
- `tests/test_faz125_ask_json_artifact.py` (new)

**Exact changes:**
1. Define report sections: `Decision`, `Entry/Stop/Targets`, `Evidence` (bars_count, lookback_required, signals, gates), `Cause-Effect` (why, invalidates, watch_next).
2. In `_cmd_ask`: when producing output, optionally write JSON to `data/out/ask/YYYY-MM-DD/SYMBOL.json` (or `--out` path); print "Artifact: <path>".
3. Extend `_advice_payload` to include structured sections; ensure `reason`, `bars_count`, `lookback_required`, `gates_outcomes` (if available).
4. Text output: format as sections (headers) for readability.

**Tests to add/modify:**
- `tests/test_faz125_ask_json_artifact.py`: ask with `--out` or default; assert JSON file exists, has expected keys, path printed.

**DoD checklist:**
- [ ] Report has consistent sections.
- [ ] JSON artifact saved and path printed.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-6: Offline KAP cache ingestion (minimal) + events evidence

**Goal & rationale:** Ingest from local KAP HTML cache; include events in evidence pack for ask output.

**Files to edit:**
- `src/bist_core/providers/events/kap_html.py` (or new offline cache reader)
- `src/bist_core/services/advisor.py`
- `tests/test_faz126_kap_cache_ingest.py` (new)

**Exact changes:**
1. Add offline cache path: `BIST_KAP_CACHE_DIR` or `data/raw/kap_html/`.
2. If `cache_only=1` or dir exists, read `{cache_dir}/{day}.html` (or similar); parse to events; no network.
3. In advisor evidence: include `events` in payload when loaded from eventstore/cache.
4. Minimal: only add cache read path; reuse existing KapHtmlEventsProvider parsing.

**Tests to add/modify:**
- `tests/test_faz126_kap_cache_ingest.py`: local HTML file; ingest; events in output.

**DoD checklist:**
- [ ] Offline cache read works.
- [ ] Events in evidence pack.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-7: Walk-forward / backtest scoreboard report

**Goal & rationale:** Proof-oriented scoreboard; avoid overfit claims; deterministic.

**Files to edit:**
- `src/bist_core/services/backtest.py`
- `src/bist_core/cli/main.py` (backtest output formatting)
- `tests/test_faz127_backtest_scoreboard.py` (new or extend)

**Exact changes:**
1. Add scoreboard report: date range, symbol count, win rate (if defined), total trades, summary stats.
2. Explicit disclaimer: "Proof-oriented; not a guarantee of future performance."
3. Deterministic ordering; stable output.

**Tests to add/modify:**
- Extend existing backtest tests; assert scoreboard keys present.

**DoD checklist:**
- [ ] Scoreboard report generated.
- [ ] Disclaimer present.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-8: Risk gate enhancements (BIST-only)

**Goal & rationale:** VBTS/exclusions hooks for BIST-only advisory if already present.

**Files to edit:**
- `src/bist_core/risk/gates.py` (or equivalent)
- `src/bist_core/eval/gates.py`
- `tests/test_faz128_risk_gates_bist.py` (new, if hooks exist)

**Exact changes:**
1. Search for VBTS, exclusions, BIST-specific gates.
2. If present: add/adjust hooks for advisory context (e.g. exclude symbols from scan).
3. If not present: document as optional; skip or add minimal stub.

**Tests to add/modify:**
- Only if hooks exist; add test for BIST exclusion behavior.

**DoD checklist:**
- [ ] VBTS/exclusions integrated if present.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-9: Optional local chat UI (FastAPI)

**Goal & rationale:** Local FastAPI wrapper around ask/scan; scope guard; network OFF by default; LLM only for explanation, never signals.

**Files to edit:**
- New: `src/bist_core/api/` or `scripts/chat_server.py`
- `docs/` for usage

**Exact changes:**
1. FastAPI app: POST `/ask` (symbol, day, params) → calls `build_advice_for_symbol`; returns JSON.
2. POST `/scan` (params) → calls scan logic; returns ranked list.
3. Scope guard: non-BIST symbol → 400 "out of scope".
4. Network OFF by default; no external API calls for signals.
5. LLM only for formatting/summarizing evidence; never for raw signals.

**Tests to add/modify:**
- `tests/test_faz129_chat_api.py`: test /ask, /scan, scope guard.

**DoD checklist:**
- [ ] API runs locally.
- [ ] Scope guard works.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-10: Ask risk sizing suggestion

**Goal & rationale:** Add risk sizing suggestion (position size, stop distance) based on capital & max_loss.

**Files to edit:**
- `src/bist_core/services/advisor.py`
- `src/bist_core/cli/main.py`
- `tests/test_faz130_risk_sizing.py` (new)

**Exact changes:**
1. When capital and max_loss_tl provided: compute suggested position size (max_loss / stop_distance_pct) and units.
2. Include in plan section: "Risk sizing: max X shares for max_loss Y TL at stop Z."

**Tests to add/modify:**
- `tests/test_faz130_risk_sizing.py`: ask with capital+max_loss; assert sizing in output.

**DoD checklist:**
- [ ] Risk sizing in output when params provided.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-11: Gates outcomes in evidence pack

**Goal & rationale:** Include gates outcomes (PASS/FAIL per gate) in evidence section.

**Files to edit:**
- `src/bist_core/strategy/engine.py` (or gates eval)
- `src/bist_core/services/advisor.py`
- `tests/test_faz131_gates_evidence.py` (new)

**Exact changes:**
1. If engine/gates produce per-gate results, pass through to Advice.
2. Add `gates_outcomes` to evidence in payload and text.

**Tests to add/modify:**
- `tests/test_faz131_gates_evidence.py`: assert gates in evidence when available.

**DoD checklist:**
- [ ] Gates outcomes in evidence.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-12: Scan liquidity filter

**Goal & rationale:** Filter scan candidates by minimum liquidity (e.g. min turnover or volume).

**Files to edit:**
- `src/bist_core/cli/main.py` (scan logic)
- `tests/test_faz132_scan_liquidity.py` (new)

**Exact changes:**
1. Add `--min-turnover` or `--min-volume` to scan.
2. Filter symbols before ranking.

**Tests to add/modify:**
- `tests/test_faz132_scan_liquidity.py`: liquidity filter applied.

**DoD checklist:**
- [ ] Liquidity filter works.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-13: Cause-effect section (why, invalidates, watch_next)

**Goal & rationale:** Explicit cause-effect: why this plan, what invalidates it, what to watch next.

**Files to edit:**
- `src/bist_core/services/advisor.py`
- `src/bist_core/cli/main.py`
- `tests/test_faz133_cause_effect.py` (new)

**Exact changes:**
1. Add structured cause-effect to Advice: `why`, `invalidates`, `watch_next`.
2. Populate from signals/gates (deterministic rules).
3. Render in text and JSON.

**Tests to add/modify:**
- `tests/test_faz133_cause_effect.py`: assert cause-effect keys in output.

**DoD checklist:**
- [ ] Cause-effect section present.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-14: README quickstart update (ask/scan flow)

**Goal & rationale:** Document ask + scan flow for Advisory Robot usage.

**Files to edit:**
- `README.md`

**Exact changes:**
1. Add "Advisory Robot Quickstart" section: ask (single symbol), scan (ranked), drill-down.
2. Document `data import`, `snapshots doctor`.
3. Link to proof_pack.

**DoD checklist:**
- [ ] README reflects new commands.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-15: Proof pack includes new tests

**Goal & rationale:** Ensure all new tests are discovered by proof_pack.

**Files to edit:**
- `tools/proof_pack.ps1` (no change if pytest discovers all)
- Verify `conftest.py` or test layout

**Exact changes:**
1. Confirm pytest collects `test_faz12*.py`, `test_faz13*.py`, etc.
2. Add any missing test markers if needed.

**DoD checklist:**
- [ ] `.\proof_pack.ps1` runs all new tests.
- [ ] No skipped tests unintentionally.

**Post-step:** Run `.\proof_pack.ps1`

---

### Prompt-16: Final integration smoke test

**Goal & rationale:** End-to-end smoke: import CSV → doctor → ask → scan.

**Files to edit:**
- `tests/test_faz134_integration_smoke.py` (new)

**Exact changes:**
1. Create minimal CSV; run data import.
2. Run snapshots doctor; assert coverage.
3. Run ask for one symbol; assert HOLD or BUY/SELL with structure.
4. Run scan (non-interactive); assert ranked output.

**DoD checklist:**
- [ ] Full flow passes.
- [ ] `.\proof_pack.ps1` passes.

**Post-step:** Run `.\proof_pack.ps1`

---

## C) Mandatory Ordering (First 5)

1. **Prompt-1** — NoDecision → HOLD + reason + coverage
2. **Prompt-2** — snapshots doctor
3. **Prompt-3** — data import
4. **Prompt-4** — scan --interactive
5. **Prompt-5** — Output template + JSON artifact

## D) Remaining Order (6–16, ROI)

6. Prompt-6 — Offline KAP cache + events evidence  
7. Prompt-7 — Walk-forward scoreboard  
8. Prompt-8 — Risk gate enhancements  
9. Prompt-10 — Risk sizing suggestion  
10. Prompt-11 — Gates outcomes in evidence  
11. Prompt-13 — Cause-effect section  
12. Prompt-12 — Scan liquidity filter  
13. Prompt-14 — README update  
14. Prompt-15 — Proof pack verification  
15. Prompt-16 — Integration smoke test  
16. Prompt-9 — Optional chat UI (only if 1–8 complete)
