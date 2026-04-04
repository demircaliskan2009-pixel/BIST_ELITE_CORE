from pathlib import Path
from struct import Struct

from bist_core.vendors.ideal_01_tail import extract_ideal_01_tail, build_ideal_01_bridge_row

REC = Struct("<I7f")


def _pack_bar(time_code, o, h, l, c, v, t, r=0.0):
    return REC.pack(time_code, float(o), float(h), float(l), float(c), float(v), float(t), float(r))


def test_extract_ideal_01_tail_returns_last_valid_bar(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'ASELS.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018517, 322.75, 323.00, 322.50, 322.75, 217796, 70263704),
                _pack_bar(20018518, 322.75, 323.00, 322.50, 322.50, 112918, 36439024),
                _pack_bar(20018519, 322.75, 322.75, 322.50, 322.50, 192703, 62160624),
            ]
        )
    )

    got = extract_ideal_01_tail(p, tail_n=3)

    assert got["header_bytes"] == 0
    assert got["record_bytes"] == 32
    assert got["record_count"] == 3
    assert got["valid_count"] == 3
    assert got["last_raw_time_code"] == 20018519
    assert got["last_close"] == 322.5
    assert got["last_volume"] == 192703.0


def test_build_ideal_01_bridge_row_emits_current_price_fields(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.65, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["symbol"] == "AKBNK"
    assert got["source_period"] == "01"
    assert got["current_close"] == 72.65
    assert got["raw_time_code"] == 20018519
    assert got["header_bytes"] == 0
    assert got["record_bytes"] == 32


def test_build_ideal_01_bridge_row_rounds_float_artifacts(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'ASELS.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["current_close"] == 72.65
    if "current_price" in got:
        assert got["current_price"] == 72.65


def test_build_ideal_01_bridge_row_emits_price_aliases(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["current_price"] == 72.65
    assert got["last_price"] == 72.65


def test_build_ideal_01_bridge_row_emits_ohlcv_aliases(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["last_open"] == 72.55
    assert got["last_high"] == 72.65
    assert got["last_low"] == 72.55
    assert got["last_close"] == 72.65
    assert got["open"] == 72.55
    assert got["high"] == 72.65
    assert got["low"] == 72.55
    assert got["close"] == 72.65
    assert got["volume"] == 732956
    assert got["turnover"] == 53204712


def test_build_ideal_01_bridge_row_keeps_metadata_contract(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["symbol"] == "AKBNK"
    assert got["source_file"] == "IMKBH'AKBNK.01"
    assert got["source_period"] == "01"
    assert got["header_bytes"] == 0
    assert got["record_bytes"] == 32
    assert got["raw_time_code"] == 20018519
    assert got["last_raw_time_code"] == 20018519
    assert got["current_volume"] == 732956
    assert got["current_turnover"] == 53204712


def test_build_ideal_01_bridge_row_normalizes_return_contract(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["current_open"] == got["last_open"] == got["open"] == 72.55
    assert got["current_high"] == got["last_high"] == got["high"] == 72.65
    assert got["current_low"] == got["last_low"] == got["low"] == 72.55
    assert got["current_close"] == got["current_price"] == got["last_price"] == got["last_close"] == got["close"] == 72.65
    assert got["current_volume"] == got["volume"] == 732956
    assert got["current_turnover"] == got["turnover"] == 53204712
    assert isinstance(got["volume"], int)
    assert isinstance(got["turnover"], int)
    assert isinstance(got["header_bytes"], int)
    assert isinstance(got["record_bytes"], int)


def test_build_ideal_01_bridge_row_preserves_extended_metadata_contract(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    extracted = extract_ideal_01_tail(p, tail_n=8)
    got = build_ideal_01_bridge_row(p)

    for key in ("record_count", "valid_count", "anomaly_count"):
        if key in extracted and extracted[key] is not None:
            assert got[key] == int(extracted[key])

    for key in ("anomaly_ratio", "coverage_ratio"):
        if key in extracted and extracted[key] is not None:
            assert abs(float(got[key]) - float(extracted[key])) <= 1e-6


def test_build_ideal_01_bridge_row_emits_generic_price_aliases(tmp_path: Path) -> None:
    p = tmp_path / "IMKBH'AKBNK.01"
    p.write_bytes(
        b"".join(
            [
                _pack_bar(20018518, 72.55, 72.60, 72.50, 72.55, 624007, 45275084),
                _pack_bar(20018519, 72.55, 72.65, 72.55, 72.6500015258789, 732956, 53204712),
            ]
        )
    )

    got = build_ideal_01_bridge_row(p)

    assert got["price"] == 72.65
    assert got["live_price"] == 72.65
    assert got["asof_price"] == 72.65
    assert got["price"] == got["live_price"] == got["asof_price"] == got["current_price"] == got["last_price"]
