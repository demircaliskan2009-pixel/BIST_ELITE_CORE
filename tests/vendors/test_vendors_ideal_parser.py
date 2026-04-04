from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bist_core.vendors.ideal.parser import IdealGParser, IdealFormatUnverifiedError


def test_parser_reads_text_fixture(tmp_path):
    p = tmp_path / "IMKBH'ASELS.G"
    p.write_text(
        "Date;Open;High;Low;Close;Volume\n"
        "2026-03-10;100;110;99;108;123456\n"
        "2026-03-11;108;112;107;111;234567\n",
        encoding="utf-8",
    )

    bars = IdealGParser().parse(p, probe_out_dir=tmp_path)
    assert len(bars) == 2
    assert bars[0].symbol == "ASELS"
    assert bars[0].timeframe == "G"
    assert bars[0].ts == "2026-03-10"
    assert bars[1].close == 111.0


def test_parser_fail_closed_on_binary(tmp_path):
    p = tmp_path / "IMKBH'ASELS.G"
    p.write_bytes(bytes(range(256)) * 8)

    try:
        IdealGParser().parse(p, probe_out_dir=tmp_path)
        assert False, "binary dosyada fail-closed bekleniyordu"
    except IdealFormatUnverifiedError as exc:
        assert ("binary layout" in str(exc).lower()) or ("tarih ofseti" in str(exc).lower())
