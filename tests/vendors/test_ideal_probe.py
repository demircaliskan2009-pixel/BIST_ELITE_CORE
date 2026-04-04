from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bist_core.vendors.ideal.probe import probe_file


def test_probe_detects_text_delimited(tmp_path):
    p = tmp_path / "IMKBH'ASELS.G"
    p.write_text(
        "Date;Open;High;Low;Close;Volume\n2026-03-10;100;110;99;108;123456\n",
        encoding="utf-8",
    )
    info = probe_file(p)
    assert info["likely_text_or_delimited"] is True
    assert info["size_bytes"] > 0
    assert info["filename"] == "IMKBH'ASELS.G"


def test_probe_handles_binary(tmp_path):
    p = tmp_path / "IMKBH'ASELS.G"
    p.write_bytes(bytes(range(256)) * 4)
    info = probe_file(p)
    assert info["size_bytes"] == 1024
    assert "head_hex_256" in info
    assert isinstance(info["candidate_record_sizes"], list)
