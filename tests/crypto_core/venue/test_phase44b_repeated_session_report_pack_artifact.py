from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SESSION_ARTIFACT = Path("docs/crypto_core/DERIBIT_HARD_CAPPED_PAPER_SESSION_ARTIFACT_42B.json")
PROMOTION_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_READINESS_43B.json")
REPORT_PACK = Path("docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json")

FALSE_FLAGS = ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled")
TRUE_FLAGS = (
    "no_private_api",
    "no_credentials",
    "no_exchange_orders",
    "no_execution_adapter",
    "no_order_routing",
    "no_strategy_signal",
    "no_scheduler",
    "no_automatic_paper_loop",
    "no_shadow",
    "no_live",
)
AGGREGATE_FIELDS = (
    ("aggregate_trades_requested", "trades_requested"),
    ("aggregate_trades_attempted", "trades_attempted"),
    ("aggregate_trades_filled", "trades_filled"),
    ("aggregate_trades_rejected", "trades_rejected"),
    ("aggregate_ledger_mutations", "ledger_mutations"),
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _session_artifact() -> dict[str, object]:
    return _json(SESSION_ARTIFACT)


def _promotion_readiness() -> dict[str, object]:
    return _json(PROMOTION_READINESS)


def _report_pack() -> dict[str, object]:
    return _json(REPORT_PACK)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_first_session(pack: dict[str, object], **updates: object) -> dict[str, object]:
    next_pack = copy.deepcopy(pack)
    sessions = list(next_pack["sessions"])
    first = dict(sessions[0])
    first.update(updates)
    sessions[0] = first
    next_pack["sessions"] = sessions
    return next_pack


def _report_pack_rejection_reasons(
    session: dict[str, object],
    promotion: dict[str, object],
    pack: dict[str, object],
) -> tuple[str, ...]:
    reasons: list[str] = []
    sessions = pack.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        reasons.append("report_pack:sessions_missing")
        sessions = []
    if pack.get("source_phase42_artifact") != str(SESSION_ARTIFACT).replace("\\", "/"):
        reasons.append("report_pack:source_phase42_artifact_mismatch")
    if pack.get("source_phase43_promotion_readiness") != str(PROMOTION_READINESS).replace("\\", "/"):
        reasons.append("report_pack:source_phase43_promotion_mismatch")
    if pack.get("source_phase42_artifact_sha256") != _sha256(SESSION_ARTIFACT):
        reasons.append("report_pack:source_phase42_hash_mismatch")
    if pack.get("source_phase43_promotion_readiness_sha256") != _sha256(PROMOTION_READINESS):
        reasons.append("report_pack:source_phase43_hash_mismatch")
    if session.get("session_verdict") != "PASS":
        reasons.append("report_pack:source_phase42_not_pass")
    if promotion.get("promotion_verdict") != "NOT_READY":
        reasons.append("report_pack:source_phase43_not_not_ready")
    if pack.get("hard_cap") != session.get("hard_cap") or pack.get("hard_cap") != 3:
        reasons.append("report_pack:hard_cap_mismatch")
    if (
        pack.get("per_session_max_trades") != session.get("max_session_trades")
        or pack.get("per_session_max_trades") != 2
    ):
        reasons.append("report_pack:per_session_max_trades_mismatch")
    required_minimum = promotion.get("required_future_sessions_minimum")
    if pack.get("required_future_sessions_minimum") != required_minimum:
        reasons.append("report_pack:required_minimum_mismatch")
    if not isinstance(required_minimum, int) or pack.get("session_count", 0) < required_minimum:
        reasons.append("report_pack:session_count_below_required_minimum")
    if pack.get("session_count") != len(sessions):
        reasons.append("report_pack:session_count_mismatch")
    session_ids = [item.get("session_id") for item in sessions if isinstance(item, dict)]
    idempotency_hashes = [item.get("idempotency_key_sha256") for item in sessions if isinstance(item, dict)]
    if any(not session_id for session_id in session_ids):
        reasons.append("report_pack:session_id_missing")
    if len(set(session_ids)) != len(session_ids):
        reasons.append("report_pack:duplicate_session_id")
    if len(set(idempotency_hashes)) != len(idempotency_hashes):
        reasons.append("report_pack:duplicate_idempotency")
    for item in sessions:
        if not isinstance(item, dict):
            reasons.append("report_pack:session_not_mapping")
            continue
        if item.get("hard_cap") != pack.get("hard_cap"):
            reasons.append("report_pack:session_hard_cap_mismatch")
        if item.get("max_session_trades") != pack.get("per_session_max_trades"):
            reasons.append("report_pack:session_max_trades_mismatch")
        if item.get("max_session_trades", 0) > pack.get("hard_cap", 0):
            reasons.append("report_pack:session_exceeds_hard_cap")
        if item.get("trades_requested", 0) > item.get("max_session_trades", 0):
            reasons.append("report_pack:session_exceeds_max_trades")
        if item.get("session_verdict") != "PASS":
            reasons.append("report_pack:session_not_pass")
        if item.get("ledger_mutated") is not True:
            reasons.append("report_pack:session_ledger_not_mutated")
        if item.get("duplicate_mutation_blocked") is not True:
            reasons.append("report_pack:session_duplicate_mutation_not_blocked")
        for field in FALSE_FLAGS:
            if item.get(field) is not False:
                reasons.append(f"report_pack:session_{field}_not_false")
        for field in TRUE_FLAGS:
            if item.get(field) is not True:
                reasons.append(f"report_pack:session_{field}_not_true")
    for aggregate_field, session_field in AGGREGATE_FIELDS:
        if pack.get(aggregate_field) != sum(
            int(item.get(session_field, 0)) for item in sessions if isinstance(item, dict)
        ):
            reasons.append(f"report_pack:{aggregate_field}_mismatch")
    if pack.get("duplicate_mutation_blocked") is not True:
        reasons.append("report_pack:duplicate_mutation_not_blocked")
    if pack.get("all_sessions_simulation_only") is not True:
        reasons.append("report_pack:all_sessions_simulation_only_not_true")
    for field in FALSE_FLAGS:
        if pack.get(field) is not False:
            reasons.append(f"report_pack:{field}_not_false")
    for field in TRUE_FLAGS:
        if pack.get(field) is not True:
            reasons.append(f"report_pack:{field}_not_true")
    if pack.get("connector_ready_dialects_count") != 1:
        reasons.append("report_pack:connector_ready_count_mismatch")
    if pack.get("report_pack_verdict") != "PASS":
        reasons.append("report_pack:verdict_not_pass")
    if pack.get("promotion_granted") is not False:
        reasons.append("report_pack:promotion_granted_not_false")
    if pack.get("next_blocker") != "PROMOTION_CRITERIA_REEVALUATION_NOT_READY":
        reasons.append("report_pack:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase44b_artifact_has_required_schema_and_source_references() -> None:
    pack = _report_pack()

    assert SESSION_ARTIFACT.exists()
    assert PROMOTION_READINESS.exists()
    assert REPORT_PACK.exists()
    assert pack["schema_version"] == "deribit_repeated_hard_capped_session_report_pack.v1"
    assert pack["phase"] == "44"
    assert pack["source"] == "deterministic_phase44_repeated_session_report_pack"
    assert pack["source_phase42_artifact"] == str(SESSION_ARTIFACT).replace("\\", "/")
    assert pack["source_phase43_promotion_readiness"] == str(PROMOTION_READINESS).replace("\\", "/")
    assert pack["source_phase42_artifact_sha256"] == _sha256(SESSION_ARTIFACT)
    assert pack["source_phase43_promotion_readiness_sha256"] == _sha256(PROMOTION_READINESS)


def test_phase44b_artifact_records_repeated_bounded_session_evidence() -> None:
    session = _session_artifact()
    promotion = _promotion_readiness()
    pack = _report_pack()

    assert pack["hard_cap"] == session["hard_cap"] == 3
    assert pack["per_session_max_trades"] == session["max_session_trades"] == 2
    assert pack["session_count"] == 3
    assert pack["session_count"] >= promotion["required_future_sessions_minimum"]
    assert pack["report_pack_verdict"] == "PASS"
    assert pack["promotion_granted"] is False
    assert _report_pack_rejection_reasons(session, promotion, pack) == ()


def test_phase44b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    pack = _report_pack()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert pack["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1
