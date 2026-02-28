"""FAZ123: CLI data import - CSV to daily snapshots (Matriks-style, TR decimals)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz123_data_import_daily_snapshots(tmp_path: Path) -> None:
    """data import creates daily snapshots from CSV with symbol,close,date."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "symbol,close,date\nAAA,100.0,2099-01-01\nBBB,30.000,2099-01-01\nCCC,50.5,2099-01-02\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")
    env["BIST_CORE_SNAPSHOT_DIR"] = str(out_dir)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(csv_path),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert (out_dir / "2099-01-01" / "snapshot.csv").exists()
    assert (out_dir / "2099-01-02" / "snapshot.csv").exists()
    snap1 = (out_dir / "2099-01-01" / "snapshot.csv").read_text(encoding="utf-8")
    assert "AAA" in snap1 and "BBB" in snap1
    snap2 = (out_dir / "2099-01-02" / "snapshot.csv").read_text(encoding="utf-8")
    assert "CCC" in snap2


def test_faz123_data_import_tr_decimals(tmp_path: Path) -> None:
    """data import parses TR decimals (30.000 -> 30000)."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "symbol,close,date\nX,30.000,2099-01-01\nY,2.000,2099-01-01\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(csv_path),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    snap = (out_dir / "2099-01-01" / "snapshot.csv").read_text(encoding="utf-8")
    assert "X" in snap and "Y" in snap
    import pandas as pd

    df = pd.read_csv(out_dir / "2099-01-01" / "snapshot.csv")
    assert df[df["symbol"] == "X"]["close"].iloc[0] == 30000.0
    assert df[df["symbol"] == "Y"]["close"].iloc[0] == 2000.0


def test_faz123_data_import_no_date_requires_day(tmp_path: Path) -> None:
    """data import without date column requires --day."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("symbol,close\nAAA,100.0\n", encoding="utf-8")
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(csv_path),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 2
    assert "day" in result.stderr.lower() or "required" in result.stderr.lower()


def test_faz123_matriks_turkish_columns_dd_mm_yyyy(tmp_path: Path) -> None:
    """data import accepts Turkish columns (Tarih, Hisse, Kapanış) and DD.MM.YYYY dates."""
    fixtures = _project_root() / "tests" / "fixtures" / "matriks_variant1.csv"
    if not fixtures.is_file():
        fixtures = tmp_path / "variant1.csv"
        fixtures.write_text(
            "Tarih,Hisse,Açılış,Yüksek,Düşük,Kapanış,Hacim\n"
            "01.01.2099,QNBFK,100,105,98,102.5,1000000\n"
            "01.01.2099,THYAO,50.000,52,48,51.500,2000000\n"
            "02.01.2099,QNBFK,102,108,101,106,1500000\n",
            encoding="utf-8",
        )
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(fixtures),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert (out_dir / "2099-01-01" / "snapshot.csv").exists()
    assert (out_dir / "2099-01-02" / "snapshot.csv").exists()
    import pandas as pd

    df = pd.read_csv(out_dir / "2099-01-01" / "snapshot.csv")
    assert set(df["symbol"]) == {"QNBFK", "THYAO"}
    assert "open" in df.columns or "close" in df.columns
    assert df[df["symbol"] == "THYAO"]["close"].iloc[0] == 51500.0  # 51.500 TR -> 51500


def test_faz123_matriks_english_iso_date(tmp_path: Path) -> None:
    """data import accepts English columns and YYYY-MM-DD dates."""
    fixtures = _project_root() / "tests" / "fixtures" / "matriks_variant2.csv"
    if not fixtures.is_file():
        fixtures = tmp_path / "variant2.csv"
        fixtures.write_text(
            "Date,Symbol,Open,High,Low,Close,Volume\n"
            "2099-01-01,AKBNK,10.5,11,10,10.75,500000\n"
            "2099-01-01,GARAN,25.000,26,24,25.500,800000\n"
            "2099-01-02,AKBNK,10.75,11.5,10.5,11.25,600000\n",
            encoding="utf-8",
        )
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(fixtures),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert (out_dir / "2099-01-01" / "snapshot.csv").exists()
    import pandas as pd

    df = pd.read_csv(out_dir / "2099-01-01" / "snapshot.csv")
    assert df[df["symbol"] == "GARAN"]["close"].iloc[0] == 25500.0  # 25.000 TR -> 25500


def test_faz123_matriks_dd_slash_mm_yyyy_symbol_normalize(tmp_path: Path) -> None:
    """data import accepts DD/MM/YYYY, TR decimals, and normalizes symbols (strip, uppercase, .E removal)."""
    fixtures = _project_root() / "tests" / "fixtures" / "matriks_variant3.csv"
    if not fixtures.is_file():
        fixtures = tmp_path / "variant3.csv"
        fixtures.write_text(
            'date,symbol,close\n15/02/2099,SISE.E,30.000\n15/02/2099,  TUPRS  ,25.500\n15/02/2099,EREGL,"42,75"\n',
            encoding="utf-8",
        )
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(fixtures),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert (out_dir / "2099-02-15" / "snapshot.csv").exists()
    import pandas as pd

    df = pd.read_csv(out_dir / "2099-02-15" / "snapshot.csv")
    assert "SISE" in df["symbol"].values  # .E removed
    assert "TUPRS" in df["symbol"].values  # spaces stripped, uppercase
    assert df[df["symbol"] == "SISE"]["close"].iloc[0] == 30000.0  # 30.000 TR
    assert df[df["symbol"] == "EREGL"]["close"].iloc[0] == 42.75  # 42,75 TR decimal


def test_faz129_import_mapping_auto_ignores_unknown(tmp_path: Path) -> None:
    """data import --mapping auto ignores unknown columns."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "symbol,close,date,extra_col\nAAA,100,2099-01-01,ignore\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(csv_path),
            "--out",
            str(out_dir),
            "--mapping",
            "auto",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert (out_dir / "2099-01-01" / "snapshot.csv").exists()


def test_faz129_import_mapping_strict_rejects_unknown(tmp_path: Path) -> None:
    """data import --mapping strict rejects unknown columns."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "symbol,close,date,unknown_col\nAAA,100,2099-01-01,x\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(csv_path),
            "--out",
            str(out_dir),
            "--mapping",
            "strict",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 2
    assert "unknown" in result.stderr.lower() or "strict" in result.stderr.lower()


def test_faz134_import_encoding_fallback(tmp_path: Path) -> None:
    """data import falls back to latin-1 when utf-8 fails."""
    csv_path = tmp_path / "input.csv"
    content = "symbol,close,date\nAAÉ,100,2099-01-01\n"
    csv_path.write_bytes(content.encode("latin-1"))
    out_dir = tmp_path / "snapshots"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(csv_path),
            "--out",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    assert (out_dir / "2099-01-01" / "snapshot.csv").exists()
    snap = (out_dir / "2099-01-01" / "snapshot.csv").read_text(encoding="utf-8")
    assert "100" in snap
