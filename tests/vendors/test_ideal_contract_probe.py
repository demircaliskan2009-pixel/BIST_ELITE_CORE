from pathlib import Path

from bist_core.vendors.ideal_contract import inspect_ideal_file


def test_ideal_contract_probe_returns_basic_shape(tmp_path: Path) -> None:
    p = tmp_path / "sample.G"
    p.write_bytes((b"ABCD" * 40) + (b"\x00" * 16))

    got = inspect_ideal_file(p)

    assert got["path"].endswith("sample.G")
    assert got["size"] == 176
    assert len(got["sha256"]) == 64
    assert isinstance(got["head_hex"], str) and got["head_hex"]
    assert isinstance(got["tail_hex"], str)
    assert 0.0 <= got["zero_ratio"] <= 1.0
    assert 0.0 <= got["ascii_ratio"] <= 1.0
    assert isinstance(got["candidate_record_layouts"], list)
    assert got["candidate_record_layouts"]


def test_ideal_contract_probe_detects_repeatable_layout_candidates(tmp_path: Path) -> None:
    p = tmp_path / "sample2.G"
    p.write_bytes(b"\x11" * 32 + (b"\x22" * 48) * 10)

    got = inspect_ideal_file(p)
    pairs = {(x["header_bytes"], x["record_bytes"]) for x in got["candidate_record_layouts"]}

    assert (32, 48) in pairs or (0, 48) in pairs
