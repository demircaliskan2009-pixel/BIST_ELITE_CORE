from __future__ import annotations

import ast
from pathlib import Path

import pytest

from crypto_core.data.public_feed_dialect import (
    FeedDialectVerificationStatus,
    public_feed_dialect_connector_ready,
    public_feed_dialect_rejection_reasons,
)
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import (
    VenuePublicFeedDialectRegistryError,
    all_public_feed_dialects,
    connector_ready_dialects,
    dialects_for_venue,
    get_public_feed_dialect,
)


def test_public_feed_dialect_registry_order_is_deterministic():
    first = tuple(spec.dialect_id for spec in all_public_feed_dialects())
    second = tuple(spec.dialect_id for spec in all_public_feed_dialects())

    assert first == tuple(sorted(first))
    assert first == second


def test_all_candidate_venues_represented():
    venues = {spec.venue_id for spec in all_public_feed_dialects()}

    assert venues == set(VenueId)


def test_only_deribit_public_dialect_is_connector_ready_after_b5_enablement():
    specs = all_public_feed_dialects()

    assert specs
    ready = tuple(spec for spec in specs if public_feed_dialect_connector_ready(spec))
    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT
    assert any(spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS for spec in specs)
    assert all(
        (spec.enabled_for_connector is True and spec.venue_id is VenueId.DERIBIT)
        or (
            spec.enabled_for_connector is False
            and spec.venue_id is not VenueId.DERIBIT
            and (
                spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
                or "public_feed_dialect:unverified" in public_feed_dialect_rejection_reasons(spec)
            )
        )
        for spec in specs
    )


def test_connector_ready_dialects_contains_only_deribit_public_market_data():
    ready = connector_ready_dialects()
    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_unknown_dialect_fails_closed():
    with pytest.raises(VenuePublicFeedDialectRegistryError, match="unknown public feed dialect"):
        get_public_feed_dialect("unknown:l2_orderbook")


def test_unknown_venue_returns_empty_fail_closed():
    assert dialects_for_venue("unknown_venue") == ()
    assert dialects_for_venue(object()) == ()  # type: ignore[arg-type]


def test_deribit_candidate_exists_verified_and_connector_enabled():
    specs = dialects_for_venue(VenueId.DERIBIT)

    assert len(specs) == 1
    assert specs[0].enabled_for_connector is True
    assert specs[0].verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS


def test_binance_usdm_candidate_exists_but_unverified_connector_disabled():
    specs = dialects_for_venue(VenueId.BINANCE_USDM)

    assert len(specs) == 1
    assert specs[0].enabled_for_connector is False
    assert specs[0].verification_status is FeedDialectVerificationStatus.UNVERIFIED


def test_static_dialect_registry_has_no_endpoint_network_or_client_strings():
    source = Path("src/crypto_core/venue/public_feed_dialects.py").read_text(encoding="utf-8").lower()

    assert "http" not in source
    assert "wss" not in source
    assert "endpoint" not in source
    assert "requests" not in source
    assert "websocket" not in source
    assert "client" not in source


def test_new_public_feed_dialect_registry_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/venue/public_feed_dialects.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imports)
