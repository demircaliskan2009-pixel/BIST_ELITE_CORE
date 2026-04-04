"""run_system CLI — one cycle, no hang."""

from __future__ import annotations

from bist_core.cli.run_system import main


def test_run_system_main_single_cycle_exits() -> None:
    assert main(["--cycles", "1", "--sleep", "0"]) == 0
