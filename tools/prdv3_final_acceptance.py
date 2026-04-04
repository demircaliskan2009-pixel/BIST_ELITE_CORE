"""PRDV3 final acceptance — validates real live_runner JSON telemetry (no env mutation).

Requires BIST_IDEAL_DATA_PATH. Inherits operator env only (no BIST_REALISM_* injection).

Checks: hard_rules from SYSTEM_STATUS_REPORT, execution realism (fill rate < 1 when attempts),
risk FSM activity, edge_signal diversity, structured blocks.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_json_blocks(text: str) -> dict[str, dict]:
    """Last wins for each top-level key like {\"SIMULATION_SUMMARY\": {...}}."""
    out: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and len(obj) == 1:
            k, v = next(iter(obj.items()))
            if isinstance(v, dict):
                out[str(k)] = v
    return out


def _max_feed_bars(text: str) -> int:
    best = 0
    for m in re.finditer(r"['\"]bars['\"]\s*:\s*(\d+)", text):
        try:
            best = max(best, int(m.group(1)))
        except ValueError:
            continue
    return best


_ALLOWED_OP_STATES = frozenset({"ACTIVE", "DE_RISK", "PAUSE", "RECOVER", "DISABLED"})


def _run_live_runner_streaming(
    cmd: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    timeout_sec: int,
) -> tuple[int, str]:
    """Run live_runner: stream every line to stdout (live) and keep full text for parsing.

    Uses a pipe + reader thread so Windows ``subprocess`` gets real OS handles; output is
    not held until the end (unlike ``capture_output=True``).
    """
    chunks: list[str] = []

    def _tee_reader(pipe) -> None:
        try:
            for line in iter(pipe.readline, ""):
                chunks.append(line)
                sys.stdout.write(line)
                sys.stdout.flush()
        finally:
            pipe.close()

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    reader = threading.Thread(target=_tee_reader, args=(proc.stdout,), daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)
        raise
    reader.join(timeout=30)
    return proc.returncode, "".join(chunks)


def main() -> int:
    root = _repo_root()
    data_path = os.environ.get("BIST_IDEAL_DATA_PATH", "").strip()
    if not data_path:
        print("FAIL: BIST_IDEAL_DATA_PATH is not set", file=sys.stderr)
        return 2
    if not Path(data_path).is_dir():
        print(f"FAIL: BIST_IDEAL_DATA_PATH is not a directory: {data_path}", file=sys.stderr)
        return 2

    try:
        timeout_sec = int(os.environ.get("BIST_PRDV3_ACCEPTANCE_TIMEOUT_SEC", "3600"))
    except ValueError:
        timeout_sec = 3600
    timeout_sec = max(60, min(timeout_sec, 86_400))

    env = os.environ.copy()
    cmd = [sys.executable, "-u", "-m", "bist_core.live.live_runner"]
    try:
        returncode, text = _run_live_runner_streaming(
            cmd,
            cwd=str(root),
            env=env,
            timeout_sec=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        print("FAIL: live_runner timed out", file=sys.stderr)
        return 3
    blocks = _parse_json_blocks(text)
    sim = blocks.get("SIMULATION_SUMMARY") or {}
    status = blocks.get("SYSTEM_STATUS_REPORT") or {}
    exec_m = blocks.get("EXECUTION_METRICS") or {}
    risk_m = blocks.get("RISK_METRICS") or {}
    realism = blocks.get("MARKET_REALISM") or {}

    failures: list[str] = []

    if returncode != 0:
        failures.append(f"process_exit_code={returncode}")

    for name in (
        "SIMULATION_SUMMARY",
        "SYSTEM_STATUS_REPORT",
        "EXECUTION_METRICS",
        "RISK_METRICS",
        "MARKET_REALISM",
    ):
        if name not in blocks:
            failures.append(f"missing_json_block:{name}")

    if "NO_PARSED_BARS" in text:
        failures.append("NO_PARSED_BARS in log")

    if "LOOP_EXCEPTION" in text or '{"fatal_error"' in text:
        failures.append("fatal loop / fatal_error in log")

    if "STOPPED_AFTER_MAX_CYCLES" not in text:
        failures.append("ENGINE: STOPPED_AFTER_MAX_CYCLES not observed in log")

    max_bars = _max_feed_bars(text)
    if max_bars <= 0:
        failures.append("DATA: no feed bars > 0")

    op = str(risk_m.get("operational_state") or "").strip().upper()
    if op not in _ALLOWED_OP_STATES:
        failures.append(f"RISK: operational_state invalid ({risk_m.get('operational_state')!r})")

    if "risk_multiplier" not in risk_m:
        failures.append("RISK: risk_multiplier missing")

    if bool(risk_m.get("kill_switch")):
        failures.append("RISK: kill_switch is true")

    if not bool(risk_m.get("fsm_transitions_observed")):
        failures.append("RISK: no FSM transitions observed (fsm_transitions_observed=false)")

    hr = status.get("hard_rules")
    if not isinstance(hr, dict) or not hr:
        failures.append("SYSTEM: hard_rules missing or empty")
    else:
        for k, v in hr.items():
            if not bool(v):
                failures.append(f"SYSTEM: hard_rules.{k}=false")
        if not bool(hr.get("confidence_variance_ok")):
            failures.append("BRAIN: confidence_variance_ok is false (need spread >= 0.25)")
        if int(status.get("action_diversity") or 0) < 3:
            failures.append("BRAIN: action_diversity < 3")
        epc_raw = status.get("empty_portfolio_cycles")
        if epc_raw is None:
            failures.append("PORTFOLIO: empty_portfolio_cycles missing")
        elif int(epc_raw) != 0:
            failures.append("PORTFOLIO: empty_portfolio_cycles != 0")

    # live_runner prints dict repr with single quotes; JSON blocks use double quotes
    if not re.search(
        r'''["']edge_signal["']\s*:\s*["'](?:STRONG_BUY|STRONG_SELL|BUY|SELL)["']''',
        text,
    ):
        failures.append("BRAIN: no actionable edge_signal (BUY/SELL/STRONG_*) in log")

    fa = int(exec_m.get("fill_attempts") or 0)
    fa_mr = int(realism.get("fill_attempts") or 0)
    fr = float(exec_m.get("fill_rate") or 0.0)
    fr_mr = float(realism.get("fill_success_rate") or 0.0)
    fills_ok_mr = int(realism.get("fills_ok") or 0)
    fills_ok_ex = int(exec_m.get("fills_ok") or 0)
    avg_sl_exec = float(exec_m.get("avg_slippage") or 0.0)
    avg_sl_real = float(realism.get("avg_slippage_fraction") or 0.0)
    slip_n = int(realism.get("slippage_samples") or 0)
    had_attempts = fa > 0 or fa_mr > 0
    had_fills = fr > 0 or fr_mr > 0
    if had_attempts and not had_fills:
        failures.append(
            "EXECUTION: fill attempts occurred but fill_rate and fill_success_rate both zero"
        )
    if had_fills:
        if avg_sl_exec <= 0 and avg_sl_real <= 0 and slip_n <= 0:
            failures.append("EXECUTION: fills reported but slippage metrics all zero")

    # MARKET_REALISM internal consistency (PaperExecution metrics only).
    mt = int(realism.get("missed_trades") or 0)
    mr_sr = float(realism.get("fill_success_rate") or 0.0)
    if fa_mr > 0:
        if fills_ok_mr + mt != fa_mr:
            failures.append(
                "EXECUTION: MARKET_REALISM fills_ok + missed_trades != fill_attempts"
            )
        expected_rate = fills_ok_mr / float(fa_mr)
        if abs(mr_sr - expected_rate) > 1e-5:
            failures.append(
                "EXECUTION: MARKET_REALISM fill_success_rate != fills_ok/fill_attempts"
            )
    if fa_mr > 0 and mt > 0 and mr_sr >= 0.9999:
        failures.append(
            "EXECUTION: missed_trades>0 but MARKET_REALISM fill_success_rate~1.0 (inconsistent)"
        )

    exec_src = str(exec_m.get("source") or "").strip()
    if exec_src == "execution_intelligence" and fa_mr > 0:
        if fa != fa_mr or fills_ok_ex != fills_ok_mr:
            failures.append(
                "EXECUTION: EXECUTION_METRICS vs MARKET_REALISM fill counts mismatch"
            )
        if abs(fr - fr_mr) > 1e-5:
            failures.append(
                "EXECUTION: EXECUTION_METRICS fill_rate vs MARKET_REALISM fill_success_rate mismatch"
            )
    if exec_src == "paper_realism" and fa_mr > 0:
        if fa != fa_mr or fills_ok_ex != fills_ok_mr or abs(fr - fr_mr) > 1e-5:
            failures.append(
                "EXECUTION: EXECUTION_METRICS (paper_realism) not aligned with MARKET_REALISM"
            )

    max_c = int(sim.get("max_cycles_config") or 0)
    tc_sim = int(sim.get("total_cycles") or 0)
    tc_st = int(status.get("total_cycles") or 0)
    if max_c > 0 and tc_sim != max_c:
        failures.append(
            f"SYSTEM: SIMULATION_SUMMARY total_cycles {tc_sim} != max_cycles_config {max_c}"
        )
    if max_c > 0 and tc_st != max_c:
        failures.append(
            f"SYSTEM: SYSTEM_STATUS_REPORT total_cycles {tc_st} != max_cycles_config {max_c}"
        )

    err = sim.get("error")
    if err:
        failures.append(f"SIMULATION_SUMMARY.error={err!r}")

    if failures:
        print("PRDV3 FINAL ACCEPTANCE — FAILED", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("PRDV3_FINAL_ACCEPTANCE_PASS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
