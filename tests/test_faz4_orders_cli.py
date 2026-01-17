from pathlib import Path
from subprocess import run, PIPE
import csv

ROOT = Path(__file__).resolve().parents[1]


def _run(mod: str, *args: str) -> str:
    """CLI komutunu çalıştırıp stdout döndürür (returncode 0 olmalı)."""
    r = run(
        ["python", "-m", mod, *args],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    assert r.returncode == 0, f"Komut başarısız oldu: {r.stderr}"
    return r.stdout


def test_orders_cli_equal_weight_pass():
    day = "2025-01-15"
    # 1) Çoklu sembollü snapshot hazırla (AAA ve BBB)
    snap_dir = ROOT / "data" / "eod" / "snapshots" / day
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = snap_dir / "snapshot.csv"
    snapshot_file.write_text("symbol,close\nAAA,100.0\nBBB,200.0\n", encoding="utf-8")
    # 2) Plan oluştur (snapshot'tan plan_equal_weight.csv üretmeli)
    out = _run("bist_core.cli.main", "plan", "--date", day)
    assert "Plan yazıldı:" in out
    # 3) Orders oluştur (risk kontrolü PASS olmalı)
    out = _run("bist_core.cli.main", "orders", "--date", day)
    assert "Orders yazıldı:" in out
    # 4) Çıktıları kontrol et
    orders_csv = ROOT / f"data/eod/snapshots/{day}/orders_equal_weight.csv"
    meta_file = ROOT / f"data/eod/snapshots/{day}/orders_meta.txt"
    assert orders_csv.exists(), "Orders CSV oluşturulmadı"
    rows = list(csv.DictReader(orders_csv.open(encoding="utf-8")))
    # AAA ve BBB bekleniyor, ağırlıklar ~0.5
    symbols = {row["symbol"] for row in rows}
    assert symbols == {"AAA", "BBB"}
    assert all(abs(float(row["target_weight"]) - 0.5) < 1e-9 for row in rows)
    # Meta dosyası PASS içermeli
    assert meta_file.exists(), "Meta dosyası yok"
    meta_content = meta_file.read_text(encoding="utf-8")
    assert "PASS" in meta_content


def test_orders_cli_equal_weight_risk_fail():
    day = "2025-01-16"
    # Önce mevcut snapshot/plan dosyalarını temizle (test izolasyonu için)
    snap_dir = ROOT / "data" / "eod" / "snapshots" / day
    if snap_dir.exists():
        for f in snap_dir.glob("*"):
            f.unlink()
    # 1) Plan oluştur (snapshot yokken, CLI otomatik TEST verisi kullanacak)
    _ = _run("bist_core.cli.main", "plan", "--date", day)
    plan_csv = ROOT / f"data/eod/snapshots/{day}/plan_equal_weight.csv"
    # Plan dosyası tek sembollü olmalı (TEST)
    assert plan_csv.exists()
    rows = list(csv.DictReader(plan_csv.open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["symbol"] == "TEST"
    # 2) Orders komutunu çalıştır (FAIL bekleniyor)
    r = run(
        ["python", "-m", "bist_core.cli.main", "orders", "--date", day],
        stdout=PIPE,
        stderr=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    assert r.returncode == 2, "Riskli durumda çıkış kodu 2 olmalı"
    # 3) Çıktıları kontrol et
    orders_csv = ROOT / f"data/eod/snapshots/{day}/orders_equal_weight.csv"
    meta_file = ROOT / f"data/eod/snapshots/{day}/orders_meta.txt"
    # Orders dosyası oluşmamalı
    assert not orders_csv.exists(), "Riskli planda orders dosyası oluşmamalı"
    # Meta dosyası FAIL içermeli
    assert meta_file.exists(), "Meta dosyası oluşmalı"
    meta_content = meta_file.read_text(encoding="utf-8")
    assert "FAIL" in meta_content


def test_orders_risk_fail():
    day = "2025-01-15"
    # 1) Önce snapshot oluştur (tek sembollü). CLI 'eod' komutunu kullanabiliriz:
    result = run(
        ["python", "-m", "bist_core.cli.main", "eod", "--date", day],
        stdout=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    assert result.returncode == 0, "EOD snapshot oluşturulamadı"
    # 2) Ardından plan oluştur (equal_weight stratejisi varsayılan):
    result = run(
        ["python", "-m", "bist_core.cli.main", "plan", "--date", day],
        stdout=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    assert result.returncode == 0, "Plan komutu başarısız oldu"
    # 3) Şimdi orders komutunu çalıştır ve risk kontrolünün tetiklendiğini doğrula
    result = run(
        ["python", "-m", "bist_core.cli.main", "orders", "--date", day],
        stdout=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    # Beklenen: risk limiti aşıldı, exit code 2 ile çıkılmalı
    assert result.returncode == 2, "Risk limitine rağmen orders komutu 2 ile çıkmadı"
    # Konsol çıktısında uyarı mesajı olmalı:
    assert "Risk limiti aşıldı" in result.stdout
    # İlgili günün dizininde orders dosyası oluşmamalı (FAIL durumunda)
    orders_path = ROOT / f"data/eod/snapshots/{day}/orders_equal_weight.csv"
    assert not orders_path.exists(), "Risk FAIL durumunda orders dosyası oluşmamalıydı"
    # Meta dosyasında "FAIL" yazdığından emin olalım
    meta_path = ROOT / f"data/eod/snapshots/{day}/orders_meta.txt"
    assert meta_path.exists(), "orders_meta.txt oluşmalıydı"
    meta_content = meta_path.read_text(encoding="utf-8")
    assert "FAIL" in meta_content


def test_orders_risk_pass():
    day = "2025-01-16"
    # 1) Çoklu sembollü bir snapshot oluştur (örneğin 100 sembol)
    snapshot_dir = ROOT / f"data/eod/snapshots/{day}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / "snapshot.csv"
    # 100 adet örnek sembol verisi yaz (her biri close fiyatı ile)
    with snapshot_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "close"])
        for i in range(100):
            writer.writerow([f"SYM{i:03d}", "100.0"])  # SYM000, SYM001, ..., SYM099
    # 2) Plan komutunu çalıştır
    result = run(
        ["python", "-m", "bist_core.cli.main", "plan", "--date", day],
        stdout=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    assert result.returncode == 0, "Plan komutu başarısız (çoklu sembol)"
    # 3) Orders komutunu çalıştır
    result = run(
        ["python", "-m", "bist_core.cli.main", "orders", "--date", day],
        stdout=PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    assert result.returncode == 0, "Risk limiti aşılmadığı halde orders komutu başarısız"
    assert "Orders yazıldı:" in result.stdout  # başarı mesajı
    # Orders dosyası oluşmalı ve içeriğini kontrol edelim
    orders_path = snapshot_dir / "orders_equal_weight.csv"
    assert orders_path.exists(), "Orders dosyası oluşmadı (PASS durumu)"
    rows = list(csv.DictReader(orders_path.open(encoding="utf-8")))
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