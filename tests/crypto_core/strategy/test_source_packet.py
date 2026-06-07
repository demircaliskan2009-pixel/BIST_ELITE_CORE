"""Tests for the strategy source packet (edge-idea provenance intake)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from crypto_core.strategy.source_packet import (
    SourcePacket,
    SourcePacketError,
    SourcePacketRightsStatus,
    SourcePacketSourceType,
    build_source_packet,
    source_packet_to_dict,
)

_HEX64 = "a" * 64


def _valid(**overrides):
    kwargs = {
        "packet_id": "src:funding-carry-001",
        "source_type": SourcePacketSourceType.ACADEMIC_PAPER,
        "source_reference": "https://example.org/funding-carry",
        "source_title": "Perpetual funding carry edge",
        "rights_status": SourcePacketRightsStatus.OWN_RESEARCH,
        "edge_hypothesis": "Cross-sectional perpetual funding carry harvests positive funding skew",
        "content_digest": _HEX64,
        "market_scope_tags": ("btc-perp", "eth-perp", "funding"),
        "data_requirement_hints": ("funding-rate-1h", "mark-price"),
    }
    kwargs.update(overrides)
    return build_source_packet(**kwargs)


def test_valid_minimal_packet_builds():
    packet = _valid()
    assert isinstance(packet, SourcePacket)
    assert packet.schema_version == "source-packet.v1"
    assert packet.source_type is SourcePacketSourceType.ACADEMIC_PAPER
    assert packet.rights_status is SourcePacketRightsStatus.OWN_RESEARCH
    assert packet.usable_for_compilation is True
    assert packet.market_scope_tags == ("btc-perp", "eth-perp", "funding")
    assert len(packet.packet_digest) == 64
    assert packet.paper_only is True
    assert packet.real_orders_enabled is False
    assert packet.real_money_enabled is False


def test_deterministic_digest_and_dict():
    first = _valid()
    second = _valid()
    assert first == second
    assert first.packet_digest == second.packet_digest
    assert source_packet_to_dict(first) == source_packet_to_dict(second)
    assert source_packet_to_dict(first)["packet_digest"] == first.packet_digest


def test_material_change_changes_digest():
    base = _valid()
    changed = _valid(edge_hypothesis="A different funding-basis dislocation hypothesis")
    assert changed.packet_digest != base.packet_digest


def test_empty_or_whitespace_identifiers_reject():
    for field, value in (
        ("packet_id", ""),
        ("packet_id", "   "),
        ("source_reference", ""),
        ("source_title", "  "),
        ("edge_hypothesis", ""),
    ):
        with pytest.raises(SourcePacketError):
            _valid(**{field: value})


def test_unknown_source_type_rejects():
    with pytest.raises(SourcePacketError):
        _valid(source_type="twitter")
    with pytest.raises(SourcePacketError):
        _valid(source_type=5)


def test_unknown_rights_status_rejects():
    with pytest.raises(SourcePacketError):
        _valid(rights_status="stolen")


def test_invalid_content_digest_rejects():
    for bad in ("abc", "g" * 64, "a" * 63, "A" * 65, 123):
        with pytest.raises(SourcePacketError):
            _valid(content_digest=bad)


def test_bist_leakage_rejected():
    with pytest.raises(SourcePacketError):
        _valid(edge_hypothesis="Mean reversion on borsa index constituents")
    with pytest.raises(SourcePacketError):
        _valid(market_scope_tags=("bist30", "btc-perp"))
    with pytest.raises(SourcePacketError):
        _valid(source_title="KAP disclosure momentum")


def test_forbidden_live_order_scheduler_tokens_rejected():
    for field, value in (
        ("edge_hypothesis", "Route signals to live trading immediately"),
        ("edge_hypothesis", "Uses order_router for entries"),
        ("source_title", "scheduler-driven rebalance"),
        ("risk_flags", ("auto_loop",)),
    ):
        with pytest.raises(SourcePacketError):
            _valid(**{field: value})


def test_safely_detectable_only_no_false_positives():
    # "ideal" (collides with English) and substring-"live" (delivery) must NOT false-reject.
    packet = _valid(
        edge_hypothesis="An ideal entry on delivery-day basis convergence with kappa weighting",
    )
    assert packet.usable_for_compilation is True


def test_restricted_rights_recorded_not_raised():
    packet = _valid(rights_status=SourcePacketRightsStatus.RESTRICTED)
    assert packet.rights_status is SourcePacketRightsStatus.RESTRICTED
    assert packet.usable_for_compilation is False
    assert "source_packet:restricted_rights" in packet.risk_flags


def test_market_scope_required_non_empty():
    with pytest.raises(SourcePacketError):
        _valid(market_scope_tags=())


def test_tags_sorted_unique_and_malformed_rejects():
    packet = _valid(
        market_scope_tags=("funding", "btc-perp", "funding", "btc-perp"),
        data_requirement_hints=("mark-price", "funding-rate-1h", "mark-price"),
        risk_flags=("regime-dependent", "regime-dependent"),
    )
    assert packet.market_scope_tags == ("btc-perp", "funding")
    assert packet.data_requirement_hints == ("funding-rate-1h", "mark-price")
    assert packet.risk_flags == ("regime-dependent",)
    for bad in (("ok", ""), ("ok", 7), "not-a-tuple"):
        with pytest.raises(SourcePacketError):
            _valid(data_requirement_hints=bad)


def test_string_enum_coercion():
    packet = _valid(source_type="code_repository", rights_status="permissive_license")
    assert packet.source_type is SourcePacketSourceType.CODE_REPOSITORY
    assert packet.rights_status is SourcePacketRightsStatus.PERMISSIVE_LICENSE


def test_immutable_and_no_leakage_fields():
    packet = _valid()
    with pytest.raises(FrozenInstanceError):
        packet.packet_id = "x"  # type: ignore[misc]
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(packet)}.isdisjoint(forbidden)
    payload = source_packet_to_dict(packet)
    assert payload["schema_version"] == "source-packet.v1"
    assert set(payload).isdisjoint(forbidden)
