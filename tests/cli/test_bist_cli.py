"""BIST CLI unit tests — commands, JSON output, invalid input."""

from __future__ import annotations

import json

import pytest

from bist_core.cli.bist_cli import main, run_backtest, run_paper, run_scan, _build_synthetic_bars


class TestScanCommand:
    def test_scan_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["scan", "--symbols", "GARAN,ASELS"])
        assert code == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "timestamp" in data
        assert "signals" in data

    def test_scan_function(self) -> None:
        dataset = _build_synthetic_bars(["GARAN"])
        result = run_scan(dataset)
        assert "timestamp" in result
        assert "signals" in result
        assert isinstance(result["signals"], list)


class TestPaperCommand:
    def test_paper_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["paper", "--symbols", "GARAN,ASELS"])
        assert code == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "signals" in data
        assert "approved" in data
        assert "executed" in data

    def test_paper_function(self) -> None:
        dataset = _build_synthetic_bars(["GARAN"])
        result = run_paper(dataset)
        assert "signals" in result
        assert isinstance(result["executed"], int)


class TestBacktestCommand:
    def test_backtest_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["backtest", "--symbols", "GARAN", "--bars", "60"])
        assert code == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "metrics" in data

    def test_backtest_function(self) -> None:
        dataset = _build_synthetic_bars(["GARAN"])
        bars = []
        for v in dataset.values():
            bars.extend(v)
        result = run_backtest(bars)
        assert "metrics" in result
        assert "trades" in result


class TestCLIOutputsJSON:
    def test_cli_outputs_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["scan", "--symbols", "GARAN"])
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert isinstance(parsed, dict)


class TestInvalidCommand:
    def test_invalid_command_fails_closed(self) -> None:
        code = main([])
        assert code == 2

    def test_unknown_command_fails(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent"])
        assert exc_info.value.code == 2
