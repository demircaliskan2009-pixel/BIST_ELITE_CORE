import csv
import os
import sys
from pathlib import Path
from subprocess import PIPE, run

ROOT = Path(__file__).resolve().parents[1]


def _run(mod: str, *args: str, env: dict | None = None) -> str:
    """CLI komutunu çalıştırıp stdout döndürür (returncode 0 olmalı)."""
    e = env or os.environ.copy()
    e.setdefault("PYTHONPATH", str(ROOT / "src"))
    r = run(
        [sys.executable, "-m", mod, *args],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=e,
    )
    assert r.returncode == 0, f"Komut başarısız oldu: {r.stderr}"
    return r.stdout


def test_orders_cli_equal_weight_pass(tmp_path: Path) -> None:
    """2 sembol (AAA, BBB) -> weight 0.5 each -> risk PASS."""
    day = "2025-01-15"
    snap_dir = tmp_path / "snapshots" / day
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nAAA,100.0\nBBB,200.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    # 2) Plan oluştur
    out = _run("bist_core.cli.main", "plan", "--date", day, env=env)
    assert "Plan yazıldı:" in out
    # 3) Orders oluştur (risk PASS: 2 symbols -> weight 0.5 each)
    out = _run("bist_core.cli.main", "orders", "--date", day, env=env)
    assert "Orders yazıldı:" in out
    # 4) Çıktıları kontrol et
    orders_csv = snap_dir / "orders_equal_weight.csv"
    meta_file = snap_dir / "orders_meta.txt"
    assert orders_csv.exists(), "Orders CSV oluşturulmadı"
    with orders_csv.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    # AAA ve BBB bekleniyor, ağırlıklar ~0.5
    symbols = {row["symbol"] for row in rows}
    assert symbols == {"AAA", "BBB"}
    assert all(abs(float(row["target_weight"]) - 0.5) < 1e-9 for row in rows)
    # Meta dosyası PASS içermeli
    assert meta_file.exists(), "Meta dosyası yok"
    meta_content = meta_file.read_text(encoding="utf-8")
    assert "PASS" in meta_content


def test_orders_cli_equal_weight_risk_fail(tmp_path: Path) -> None:
    """1 sembol (TEST) -> weight 1.0 -> risk FAIL."""
    day = "2025-01-16"
    snap_dir = tmp_path / "snapshots" / day
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nTEST,10.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    # 1) Plan oluştur (1 symbol -> weight 1.0)
    _ = _run("bist_core.cli.main", "plan", "--date", day, env=env)
    plan_csv = snap_dir / "plan_equal_weight.csv"
    assert plan_csv.exists()
    with plan_csv.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1 and rows[0]["symbol"] == "TEST"
    # 2) Orders komutunu çalıştır (FAIL bekleniyor: weight 1.0 > 0.5)
    r = run(
        [sys.executable, "-m", "bist_core.cli.main", "orders", "--date", day],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
    )
    assert r.returncode == 2, "Riskli durumda çıkış kodu 2 olmalı"
    # 3) Çıktıları kontrol et
    orders_csv = snap_dir / "orders_equal_weight.csv"
    meta_file = snap_dir / "orders_meta.txt"
    # Orders dosyası oluşmamalı
    assert not orders_csv.exists(), "Riskli planda orders dosyası oluşmamalı"
    # Meta dosyası FAIL içermeli
    assert meta_file.exists(), "Meta dosyası oluşmalı"
    meta_content = meta_file.read_text(encoding="utf-8")
    assert "FAIL" in meta_content


def test_orders_risk_fail(tmp_path: Path) -> None:
    """1 sembol (TEST) -> risk FAIL."""
    day = "2025-01-15"
    snap_dir = tmp_path / "snapshots" / day
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.csv").write_text("symbol,close\nTEST,10.0\n", encoding="utf-8")
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    _ = _run("bist_core.cli.main", "plan", "--date", day, env=env)
    result = run(
        [sys.executable, "-m", "bist_core.cli.main", "orders", "--date", day],
        stdout=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
    )
    assert result.returncode == 2, "Risk limitine rağmen orders komutu 2 ile çıkmadı"
    assert "Risk limiti aşıldı" in result.stdout
    orders_path = snap_dir / "orders_equal_weight.csv"
    assert not orders_path.exists(), "Risk FAIL durumunda orders dosyası oluşmamalıydı"
    meta_path = snap_dir / "orders_meta.txt"
    assert meta_path.exists(), "orders_meta.txt oluşmalıydı"
    meta_content = meta_path.read_text(encoding="utf-8")
    assert "FAIL" in meta_content


def test_orders_risk_pass(tmp_path: Path) -> None:
    """100 sembol -> weight 0.01 each -> risk PASS."""
    day = "2025-01-16"
    snapshot_dir = tmp_path / "snapshots" / day
    snapshot_dir.mkdir(parents=True)
    snapshot_path = snapshot_dir / "snapshot.csv"
    with snapshot_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "close"])
        for i in range(100):
            writer.writerow([f"SYM{i:03d}", "100.0"])
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    _ = _run("bist_core.cli.main", "plan", "--date", day, env=env)
    result = run(
        [sys.executable, "-m", "bist_core.cli.main", "orders", "--date", day],
        stdout=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=env,
    )
    assert result.returncode == 0, "Risk limiti aşılmadığı halde orders komutu başarısız"
    assert "Orders yazıldı:" in result.stdout
    orders_path = snapshot_dir / "orders_equal_weight.csv"
    assert orders_path.exists(), "Orders dosyası oluşmadı (PASS durumu)"
    with orders_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    # 100 sembol olmalı ve her birinin target_weight ~ 0.01 olmalı
    assert len(rows) == 100
    for row in rows:
        w = float(row["target_weight"])
        assert abs(w - 0.01) < 1e-6, "Target weight beklenen değilden sapıyor"
    # Meta dosyası PASS içermeli
    meta_path = snapshot_dir / "orders_meta.txt"
    assert meta_path.exists()
    meta_content = meta_path.read_text(encoding="utf-8")
    assert "PASS" in meta_content
