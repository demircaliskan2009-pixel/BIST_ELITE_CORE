from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _biz_days(start: date, count: int) -> list[str]:
    out = []
    cur = start
    while len(out) < count:
        if cur.weekday() < 5:
            out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _write_snapshots(root: Path) -> str:
    days = _biz_days(date(2025, 1, 2), 25)
    for i, day in enumerate(days):
        day_dir = root / day
        day_dir.mkdir(parents=True, exist_ok=True)

        asels_close = 100 + i * 2.0
        akfis_close = 50 + i * 0.35
        aefes_close = 80 - i * 0.9

        asels_vol = 1_000_000 + i * 60_000
        akfis_vol = 900_000 + i * 5_000
        aefes_vol = 1_100_000 - i * 20_000

        rows = [
            ("ASELS", asels_close - 1.0, asels_close + 1.2, asels_close - 1.5, asels_close, asels_vol),
            ("AKFIS", akfis_close - 0.4, akfis_close + 0.5, akfis_close - 0.6, akfis_close, akfis_vol),
            ("AEFES", aefes_close - 0.8, aefes_close + 0.4, aefes_close - 1.1, aefes_close, aefes_vol),
        ]

        lines = ["symbol,open,high,low,close,volume,turnover_tl"]
        for sym, o, h, l, c, v in rows:
            turnover = c * v
            lines.append(f"{sym},{o:.2f},{h:.2f},{l:.2f},{c:.2f},{int(v)},{turnover:.2f}")
        (day_dir / "snapshot.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return days[-1]


def _run(args: list[str], snap_root: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )


def test_faz591_freeform_single_pick(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots"
    day = _write_snapshots(snap)
    r = _run(["ask", "bugün işlem açılacak tek hisse seçilecek olsa hangisi olurdu ve neden", "--day", day, "--json"], snap)
    assert r.returncode == 0, r.stderr or r.stdout
    data = json.loads(r.stdout)
    assert data["query_type"] == "single_pick"
    assert data["best_symbol"] == "ASELS"
    assert data["ranked"][0]["symbol"] == "ASELS"


def test_faz592_freeform_compare(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots"
    day = _write_snapshots(snap)
    r = _run(["ask", "ASELS ile AKFIS arasında bugün hangisi daha güçlü ve neden", "--day", day, "--json"], snap)
    assert r.returncode == 0, r.stderr or r.stdout
    data = json.loads(r.stdout)
    assert data["query_type"] == "compare"
    assert data["preferred_symbol"] == "ASELS"
    assert [x["symbol"] for x in data["ranked"][:2]] == ["ASELS", "AKFIS"]


def test_faz593_scan_scores_not_all_equal(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots"
    day = _write_snapshots(snap)
    r = _run(["scan", "--day", day, "--top-n", "3", "--json"], snap)
    assert r.returncode == 0, r.stderr or r.stdout
    data = json.loads(r.stdout)
    scores = [float(x["score"]) for x in data["ranked"]]
    assert len(set(scores)) > 1


def test_faz593_ask_mentions_current_price_context(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots"
    day = _write_snapshots(snap)
    r = _run(["ask", "ASELS", "--day", day, "--json"], snap)
    assert r.returncode == 0, r.stderr or r.stdout
    data = json.loads(r.stdout)
    assert data["plan"]["current_close"] is not None
    if "live_current_close_source" in data["plan"]:
        assert data["plan"]["live_current_close_source"] == "01"
    assert "entry seviyesinin" in data["text"]


def test_faz594_scan_emits_live_bridge_fields(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots"
    day = _write_snapshots(snap)
    r = _run(["scan", "--day", day, "--top-n", "3", "--json"], snap)
    assert r.returncode == 0, r.stderr or r.stdout
    data = json.loads(r.stdout)
    first = data["ranked"][0]
    if "current_close" in first:
        assert "entry_status" in first
        assert "current_close_source" in first


def test_scan_ranked_item_view_preserves_live_fields():
    from bist_core.cli.main import _scan_ranked_item_view

    item = {
        "symbol": "ASELS",
        "score": 1.5,
        "reason": "dispersion+momentum",
        "current_close": 330.0,
        "current_close_source": "01",
        "live_vs_g_close_pct": 0.0,
        "entry_status": "below_entry_trigger",
    }

    got = _scan_ranked_item_view(item)

    assert got["symbol"] == "ASELS"
    assert got["score"] == 1.5
    assert got["rationale"] == "dispersion+momentum"
    assert got["current_close"] == 330.0
    assert got["current_close_source"] == "01"
    assert got["live_vs_g_close_pct"] == 0.0
    assert got["entry_status"] == "below_entry_trigger"


def test_ranked_item_view_preserves_live_fields_from_plan_or_record():
    from pathlib import Path
    import importlib.util

    candidates = list(Path("src/bist_core").rglob("*.py"))
    mod = None
    for p in candidates:
        txt = p.read_text(encoding="utf-8")
        if "def _ranked_item_view(" in txt and "schema_version" in txt and "generated_at" in txt and '"ranked"' in txt:
            spec = importlib.util.spec_from_file_location("tmp_ranked_mod", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            break

    assert mod is not None
    fn = getattr(mod, "_ranked_item_view")

    item = {
        "symbol": "ASELS",
        "score": 1.5,
        "reason": "dispersion+momentum",
        "plan": {
            "current_close": 330.0,
            "live_current_close_source": "01",
            "live_vs_g_close_pct": 0.0,
            "entry_status": "below_entry_trigger",
        },
    }

    got = fn(item)

    assert got["symbol"] == "ASELS"
    assert got["score"] == 1.5
    assert got["rationale"] == "dispersion+momentum"
    assert got["current_close"] == 330.0
    assert got["current_close_source"] == "01"
    assert got["live_vs_g_close_pct"] == 0.0
    assert got["entry_status"] == "below_entry_trigger"


def test_scan_ranked_item_view_handles_tuple_core_and_live_dict():
    from bist_core.cli.main import _scan_ranked_item_view

    got_tuple = _scan_ranked_item_view(("ASELS", 1.5, "dispersion+momentum"))
    assert got_tuple["symbol"] == "ASELS"
    assert got_tuple["score"] == 1.5
    assert got_tuple["rationale"] == "dispersion+momentum"

    got_dict = _scan_ranked_item_view({
        "symbol": "ASELS",
        "score": 1.5,
        "reason": "dispersion+momentum",
        "plan": {
            "current_close": 330.0,
            "live_current_close_source": "01",
            "live_vs_g_close_pct": 0.0,
            "entry_status": "below_entry_trigger",
        },
    }, "2026-03-09")
    assert got_dict["symbol"] == "ASELS"
    assert got_dict["score"] == 1.5
    assert got_dict["rationale"] == "below_entry_trigger"
    assert got_dict["current_close"] == 330.0
    assert got_dict["current_close_source"] == "01"
    assert got_dict["live_vs_g_close_pct"] == 0.0
    assert got_dict["entry_status"] == "below_entry_trigger"


def test_score_enrichment_penalizes_extended_and_rewards_near_entry():
    from bist_core.services.advisor import _augment_engine_result_with_bar_context

    bars = [
        {"close": 100.0, "volume": 1000},
        {"close": 100.5, "volume": 1100},
        {"close": 101.0, "volume": 1200},
        {"close": 101.5, "volume": 1300},
        {"close": 101.8, "volume": 1250},
        {"close": 102.0, "volume": 1400},
    ]

    near_result = _augment_engine_result_with_bar_context(
        {"score": 1.50, "decision_raw": "BUY", "signals": {}, "plan": {"entry": 102.0}},
        bars,
    )
    extended_result = _augment_engine_result_with_bar_context(
        {"score": 1.50, "decision_raw": "BUY", "signals": {}, "plan": {"entry": 100.0}},
        bars,
    )

    assert near_result["plan"]["entry_status"] == "near_entry"
    assert extended_result["plan"]["entry_status"] == "extended_above_entry"
    assert near_result["score"] > extended_result["score"]

    near_sig = near_result["signals"]
    ext_sig = extended_result["signals"]
    assert "score_components" in near_sig
    assert "score_components" in ext_sig
    assert near_sig["score_components"]["entry"] > ext_sig["score_components"]["entry"]


def test_scan_ranked_item_view_builds_compact_rationale_from_components():
    from bist_core.cli.main import _scan_ranked_item_view

    got = _scan_ranked_item_view(
        {
            "symbol": "ASELS",
            "score": 1.23,
            "reason": "very long generic explanation that should not be the compact rationale anymore",
            "signals": {
                "entry_gap_pct": -0.96,
                "score_components": {
                    "entry": 0.08,
                    "ret1": 0.02,
                    "range": 0.14,
                    "volume": -0.09,
                },
            },
            "plan": {
                "entry_status": "below_entry_trigger",
                "current_close": 330.0,
                "live_current_close_source": "01",
                "live_vs_g_close_pct": 0.0,
            },
        }
    )

    assert got["symbol"] == "ASELS"
    assert got["score"] == 1.23
    assert "below_entry_trigger" in got["rationale"]
    assert "gap=-0.96%" in got["rationale"]
    assert "E=+0.08" in got["rationale"]
    assert "R1=+0.02" in got["rationale"]
    assert "Rp=+0.14" in got["rationale"]
    assert "V=-0.09" in got["rationale"]
    assert got["current_close"] == 330.0
    assert got["current_close_source"] == "01"
    assert got["live_vs_g_close_pct"] == 0.0
    assert got["entry_status"] == "below_entry_trigger"


def test_live_overlay_recomputes_entry_gap_from_live_price(monkeypatch):
    from bist_core.services import advisor as advisor_mod

    monkeypatch.setattr(
        "bist_core.vendors.ideal_bridge_runtime.get_live_bridge_row",
        lambda symbol: {
            "current_close": 110.0,
            "current_close_source": "01",
            "delta_current_vs_g_close_pct": 5.0,
        },
    )

    out = advisor_mod._overlay_live_bridge_context(
        {
            "plan": {"entry": 100.0, "current_close": 98.0},
            "signals": {"entry_gap_pct": -2.0},
        },
        "ASELS",
    )

    assert out["plan"]["current_close"] == 110.0
    assert out["plan"]["entry_status"] == "extended_above_entry"
    assert out["plan"]["entry_gap_pct"] == 10.0
    assert out["signals"]["entry_gap_pct"] == 10.0

def test_freeform_single_pick_text_uses_compact_rationale(tmp_path):
    import json

    snap = tmp_path / "snapshots"
    day = _write_snapshots(snap)
    r = _run(["ask", "bugün en güçlü tek hisse hangisi", "--day", day, "--json"], snap)
    assert r.returncode == 0, r.stderr or r.stdout

    data = json.loads(r.stdout)
    assert data["best_symbol"]
    assert data["ranked"]
    assert "Kompakt gerekçe:" in data["text"]
    assert "entry_gap=" in data["text"]
    assert "durum=" in data["text"]

def test_freeform_compare_text_uses_compact_rationale(tmp_path):
    import json

    snap = tmp_path / "snapshots"
    day = _write_snapshots(snap)
    r = _run(["ask", "ASELS ile AKFIS arasında bugün hangisi daha güçlü ve neden", "--day", day, "--json"], snap)
    assert r.returncode == 0, r.stderr or r.stdout

    data = json.loads(r.stdout)
    assert data["preferred_symbol"] in data["text"]
    assert "->" in data["text"]
    assert "gap=" in data["text"]

def test_render_advice_text_includes_live_gap_and_score_components():
    from datetime import date
    from bist_core.services.advisor import _render_advice_text

    text = _render_advice_text(
        symbol="ASELS",
        day=date(2026, 3, 9),
        decision_raw="WATCH",
        score=1.16,
        signals={
            "ret1_pct": 0.45,
            "range_pos": 0.819,
            "vol_ratio": 0.48,
            "entry_gap_pct": -2.65,
            "score_components": {
                "base": 1.00,
                "ret1": 0.02,
                "range": 0.14,
                "volume": -0.09,
                "entry": 0.08,
            },
        },
        plan={
            "entry": 339.0,
            "stop": 329.0,
            "t1": 345.75,
            "current_close": 330.0,
            "entry_status": "below_entry_trigger",
            "live_current_close_source": "01",
            "live_vs_g_close_pct": 0.0,
            "entry_gap_pct": -2.65,
        },
        has_ohlcv=True,
        events=[],
        events_errors=[],
    )

    assert "ASELS için karar WATCH; skor 1.16." in text
    assert "Skor bileşenleri:" in text
    assert "giriş +0.08" in text
    assert "Canlı bağlam:" in text
    assert "entry gap -2.65%" in text
    assert "tetik henüz oluşmamış olabilir" in text
    assert "Senaryo iptal / yeniden değerlendirme:" in text

def test_render_advice_text_marks_extended_entry_as_do_not_chase():
    from datetime import date
    from bist_core.services.advisor import _render_advice_text

    text = _render_advice_text(
        symbol="AKFIS",
        day=date(2026, 3, 9),
        decision_raw="BUY",
        score=1.36,
        signals={
            "entry_gap_pct": 6.09,
            "score_components": {
                "base": 1.00,
                "ret1": 0.13,
                "range": 0.19,
                "volume": -0.04,
                "entry": 0.08,
            },
        },
        plan={
            "entry": 34.5,
            "stop": 33.48,
            "t1": 35.18,
            "current_close": 36.6,
            "entry_status": "extended_above_entry",
            "live_current_close_source": "01",
            "live_vs_g_close_pct": 0.0,
            "entry_gap_pct": 6.09,
        },
        has_ohlcv=True,
        events=[],
        events_errors=[],
    )

    assert "AKFIS için karar BUY; skor 1.36." in text
    assert "plan kovalanmamalı" in text
    assert "entry gap +6.09%" in text
