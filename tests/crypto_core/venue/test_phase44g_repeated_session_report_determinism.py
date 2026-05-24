from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase44b_repeated_session_report_pack_artifact import (
    _promotion_readiness,
    _report_pack,
    _report_pack_rejection_reasons,
    _session_artifact,
)


def test_phase44g_report_pack_validation_is_deterministic() -> None:
    session = _session_artifact()
    promotion = _promotion_readiness()
    pack = _report_pack()

    first = _report_pack_rejection_reasons(session, promotion, pack)
    second = _report_pack_rejection_reasons(session, promotion, pack)

    assert first == second == ()


def test_phase44g_report_pack_json_round_trip_is_deterministic() -> None:
    pack = _report_pack()

    first = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))

    assert first == second
