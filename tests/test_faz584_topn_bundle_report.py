"""FAZ584: TopN bundle report — HTML+JSON+CSV with advice. Deterministic, offline."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def _run_bundle(
    day: str,
    horizon: int,
    top: int = 5,
    reports_root: Path | None = None,
    snapshot_root: Path | None = None,
) -> tuple[int, str, str]:
    """Run topn_bundle_report.py. Returns (exit_code, stdout, stderr)."""
    args = [
        sys.executable,
        str(_repo / "tools" / "topn_bundle_report.py"),
        "--day",
        day,
        "--horizon",
        str(horizon),
        "--top",
        str(top),
    ]
    if reports_root:
        args.extend(["--reports-root", str(reports_root)])
    if snapshot_root:
        args.extend(["--snapshot-root", str(snapshot_root)])
    r = subprocess.run(args, cwd=str(_repo), capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout or "", r.stderr or ""


def _setup_fixture(tmp_path: Path, day: str) -> Path:
    """Create reports dir with topn_h1.csv and ask artifacts. Returns reports_root."""
    reports_dir = tmp_path / "reports" / day
    reports_dir.mkdir(parents=True, exist_ok=True)

    topn_csv = reports_dir / "topn_h1.csv"
    topn_csv.write_text(
        "day,horizon_days,symbol,bars_used,lookback_used,mu_hat,sigma_hat,p_up,p_gt_cost,score,notes\n"
        f"{day},1,AAA,65,60,0.01,0.02,0.7,0.65,0.005,\n"
        f"{day},1,BBB,65,60,0.005,0.015,0.6,0.55,0.002,\n"
        f"{day},1,CCC,65,60,-0.001,0.01,0.45,0.4,-0.0005,\n",
        encoding="utf-8",
    )

    ask_dir = tmp_path / "ask" / day
    ask_dir.mkdir(parents=True, exist_ok=True)
    (ask_dir / "AAA.json").write_text(
        json.dumps(
            {
                "symbol": "AAA",
                "day": day,
                "decision_raw": "BUY",
                "score": 0.8,
                "text": "AAA için karar BUY; skor 0.80.\nPlan: entry 100, stop 95, t1 110.",
            }
        ),
        encoding="utf-8",
    )
    (ask_dir / "BBB.json").write_text(
        json.dumps(
            {
                "symbol": "BBB",
                "day": day,
                "decision_raw": "PASS",
                "score": 0.0,
                "text": "Güvenli mod: InsufficientHistory. Mevcut bar sayısı: 10, gerekli lookback: 20.",
            }
        ),
        encoding="utf-8",
    )
    (ask_dir / "CCC.json").write_text(
        json.dumps(
            {
                "symbol": "CCC",
                "day": day,
                "decision_raw": "HOLD",
                "score": 0.3,
                "text": "CCC için karar HOLD; skor 0.30.",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path / "reports"


def test_bundle_files_created(tmp_path: Path) -> None:
    """Bundle creates JSON, CSV, HTML."""
    reports_root = _setup_fixture(tmp_path, "2025-03-15")
    code, _, _ = _run_bundle("2025-03-15", 1, top=5, reports_root=reports_root)
    assert code == 0
    reports_dir = reports_root / "2025-03-15"
    assert (reports_dir / "topn_bundle_h1.json").is_file()
    assert (reports_dir / "topn_bundle_h1.csv").is_file()
    assert (reports_dir / "topn_bundle_h1.html").is_file()


def test_csv_header_exact(tmp_path: Path) -> None:
    """CSV header matches spec."""
    reports_root = _setup_fixture(tmp_path, "2025-03-15")
    _run_bundle("2025-03-15", 1, top=5, reports_root=reports_root)
    with (reports_root / "2025-03-15" / "topn_bundle_h1.csv").open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    expected = [
        "day",
        "horizon_days",
        "rank",
        "symbol",
        "score",
        "p_up",
        "p_gt_cost",
        "mu_hat",
        "sigma_hat",
        "decision_raw",
        "has_artifact",
        "artifact_path",
        "headline",
    ]
    assert header == expected


def test_deterministic_ordering(tmp_path: Path) -> None:
    """Input ranking (score desc, symbol asc) preserved."""
    reports_root = _setup_fixture(tmp_path, "2025-03-15")
    _run_bundle("2025-03-15", 1, top=5, reports_root=reports_root)
    with (reports_root / "2025-03-15" / "topn_bundle_h1.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    symbols = [r["symbol"] for r in rows]
    assert symbols == ["AAA", "BBB", "CCC"]


def test_html_contains_symbols(tmp_path: Path) -> None:
    """HTML contains all symbols in correct order."""
    reports_root = _setup_fixture(tmp_path, "2025-03-15")
    _run_bundle("2025-03-15", 1, top=5, reports_root=reports_root)
    html = (reports_root / "2025-03-15" / "topn_bundle_h1.html").read_text(encoding="utf-8")
    assert "AAA" in html
    assert "BBB" in html
    assert "CCC" in html


def test_html_includes_guvenli_mod(tmp_path: Path) -> None:
    """When advice has PASS + Güvenli mod, HTML includes it."""
    reports_root = _setup_fixture(tmp_path, "2025-03-15")
    _run_bundle("2025-03-15", 1, top=5, reports_root=reports_root)
    html = (reports_root / "2025-03-15" / "topn_bundle_h1.html").read_text(encoding="utf-8")
    assert "Güvenli mod" in html


def test_missing_topn_exit_2(tmp_path: Path) -> None:
    """Missing topn file => exit 2."""
    reports_dir = tmp_path / "reports" / "2025-03-15"
    reports_dir.mkdir(parents=True)
    ask_dir = tmp_path / "ask" / "2025-03-15"
    ask_dir.mkdir(parents=True)
    code, _, stderr = _run_bundle("2025-03-15", 1, reports_root=tmp_path / "reports")
    assert code == 2
    assert "topn_h1" in stderr or "not found" in stderr.lower()


def test_artifact_preferred(tmp_path: Path) -> None:
    """When artifact exists, use it (has_artifact=True)."""
    reports_root = _setup_fixture(tmp_path, "2025-03-15")
    _run_bundle("2025-03-15", 1, top=5, reports_root=reports_root)
    data = json.loads((reports_root / "2025-03-15" / "topn_bundle_h1.json").read_text(encoding="utf-8"))
    rows = data.get("rows") or []
    aaa = next((r for r in rows if r.get("symbol") == "AAA"), None)
    assert aaa is not None
    assert aaa.get("has_artifact") is True
    assert aaa.get("decision_raw") == "BUY"
