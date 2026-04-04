from pathlib import Path
import sys
import struct
import datetime as dt

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bist_core.vendors.ideal.parser import IdealGParser


def pack_rec(date_code, o, h, l, c, v, turnover=0.0, reserved=0):
    return struct.pack("<I6fI", date_code, o, h, l, c, v, turnover, reserved)


def test_parser_reads_binary_g_fixture(tmp_path):
    p = tmp_path / "IMKBH'ASELS.G"

    # Choose explicit mapping so parser can recover exact dates with last_date override.
    offset = 38373
    recs = []
    recs.append(pack_rec(dt.date(2026, 3, 8).toordinal() + offset, 0.0, 0.0, 0.0, 0.0, 0.0, 88.0, 0))
    recs.append(pack_rec(dt.date(2026, 3, 9).toordinal() + offset, 333.5, 337.75, 318.5, 319.0, 35339368.0, 11505104896.0, 0))
    recs.append(pack_rec(dt.date(2026, 3, 10).toordinal() + offset, 319.25, 336.0, 319.25, 334.25, 29364718.0, 9669047296.0, 0))
    recs.append(pack_rec(dt.date(2026, 3, 11).toordinal() + offset, 334.5, 335.75, 326.5, 335.75, 18257244.0, 6062096384.0, 0))
    p.write_bytes(b"".join(recs))

    bars = IdealGParser().parse(p, probe_out_dir=tmp_path, last_date=dt.date(2026, 3, 11))
    assert len(bars) == 3
    assert bars[0].ts == "2026-03-09"
    assert bars[-1].ts == "2026-03-11"
    assert bars[-1].close == 335.75
    assert bars[-1].volume == 18257244.0
