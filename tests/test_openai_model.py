"""FAZ117: OpenAIModel — batch JSON, network fail-closed, cache, Windows-friendly key message."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bist_core.models.openai_model import OpenAIModel


def test_openai_model_requires_api_key() -> None:
    """OpenAIModel raises ValueError when OPENAI_API_KEY is not set; message includes PowerShell/CMD."""
    import os
    old = os.environ.pop("OPENAI_API_KEY", None)
    try:
        with pytest.raises(ValueError) as exc:
            OpenAIModel()
        msg = str(exc.value)
        assert "OPENAI_API_KEY" in msg
        assert "PowerShell" in msg
        assert "setx" in msg or "CMD" in msg
    finally:
        if old:
            os.environ["OPENAI_API_KEY"] = old


def test_openai_model_network_disabled_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """When network disabled, predict raises RuntimeError and OpenAI client is NOT called."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    mock_create = MagicMock()
    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create
    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    model = OpenAIModel(api_key="test-key")
    with pytest.raises(RuntimeError, match="NETWORK_DISABLED"):
        model.predict([{"symbol": "A", "close": 1.0}])
    mock_create.assert_not_called()


def test_openai_model_batch_json_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batch mode: ONE request, strict JSON response parsed correctly."""
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "1")
    json_resp = '[{"symbol":"THYA","score":0.5,"reason":"bullish"},{"symbol":"AKBNK","score":-0.2,"reason":"bearish"}]'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json_resp

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    model = OpenAIModel(api_key="test-key")
    scores = model.predict([
        {"symbol": "THYA", "close": 100.0},
        {"symbol": "AKBNK", "close": 50.0},
    ])
    assert scores == [0.5, -0.2]
    mock_client.chat.completions.create.assert_called_once()


def test_openai_model_batch_json_parse_fail_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When JSON parse fails, fallback to 0.0 per symbol."""
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "1")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "I cannot provide JSON"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    model = OpenAIModel(api_key="test-key")
    scores = model.predict([{"symbol": "X", "close": 10.0}])
    assert scores == [0.0]


def test_openai_model_cache_second_run_no_api_call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Caching: second predict uses cache; OpenAI client called once."""
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "1")
    cache_dir = tmp_path / "cache"
    json_resp = '[{"symbol":"A","score":0.3,"reason":"ok"}]'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json_resp

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    model = OpenAIModel(api_key="test-key", cache_dir=cache_dir)
    features = [{"symbol": "A", "close": 1.0}]
    scores1 = model.predict(features)
    assert scores1 == [0.3]
    assert mock_client.chat.completions.create.call_count == 1

    scores2 = model.predict(features)
    assert scores2 == [0.3]
    assert mock_client.chat.completions.create.call_count == 1


def test_openai_model_implements_model_plugin() -> None:
    """OpenAIModel has predict method (ModelPlugin contract)."""
    model = OpenAIModel(api_key="dummy")
    assert hasattr(model, "predict")
    assert callable(model.predict)


def test_cli_model_openai_missing_key_exit_2(tmp_path: Path) -> None:
    """CLI --model openai with missing key: exit 2, blocked message."""
    import os
    snap_dir = tmp_path / "snap"
    (snap_dir / "2099-01-22").mkdir(parents=True, exist_ok=True)
    (snap_dir / "2099-01-22" / "snapshot.csv").write_text("symbol,date,close\nX,2099-01-22,10\n", encoding="utf-8")
    outdir = tmp_path / "out"
    outdir.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items()}
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_dir)
    env["BIST_CORE_ALLOW_NETWORK"] = "1"
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "advice", "--day", "2099-01-22", "--outdir", str(outdir), "--model", "openai"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )
    assert result.returncode == 2
    assert "blocked" in result.stderr
    assert "OPENAI_API_KEY" in result.stderr


def test_cli_model_openai_network_disabled_exit_2(tmp_path: Path) -> None:
    """CLI --model openai with network disabled: exit 2, OpenAI not called."""
    import os
    snap_dir = tmp_path / "snap2"
    (snap_dir / "2099-01-23").mkdir(parents=True, exist_ok=True)
    (snap_dir / "2099-01-23" / "snapshot.csv").write_text("symbol,date,close\nY,2099-01-23,20\n", encoding="utf-8")
    outdir = tmp_path / "out2"
    outdir.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items()}
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_dir)
    env["OPENAI_API_KEY"] = "sk-test"
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    result = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "eod", "advice", "--day", "2099-01-23", "--outdir", str(outdir), "--model", "openai"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )
    assert result.returncode == 2
    assert "blocked" in result.stderr
    assert "NETWORK_DISABLED" in result.stderr


def test_generate_advice_uses_openai_when_env_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When USE_OPENAI_MODEL=1 and OPENAI_API_KEY set, generate_advice uses OpenAIModel (mocked batch API)."""
    monkeypatch.setenv("USE_OPENAI_MODEL", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BIST_CORE_ALLOW_NETWORK", "1")

    json_resp = '[{"symbol":"XYZ","score":0.8,"reason":"strong buy"}]'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json_resp
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    monkeypatch.setitem(sys.modules, "openai", mock_openai)

    from bist_core.advisory.generate import generate_advice

    day = "2099-01-22"
    snap_dir = tmp_path / "snap"
    (snap_dir / day).mkdir(parents=True, exist_ok=True)
    (snap_dir / day / "snapshot.csv").write_text("symbol,date,close\nXYZ,2099-01-22,50\n", encoding="utf-8")
    outdir = tmp_path / "out"
    result = generate_advice(day, snap_dir, outdir, model_plugin=None)
    assert result["total"] == 1
    rec = next(r for r in result["records"] if r["symbol"] == "XYZ")
    assert rec["score"] == 0.8
    assert rec["side"] == "BUY"
