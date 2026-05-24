from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

SESSION_ARTIFACT = Path("docs/crypto_core/DERIBIT_HARD_CAPPED_PAPER_SESSION_ARTIFACT_42B.json")
PHASE41_REPORT = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_RUN_TELEMETRY_REPORT_41B.json")
PROMOTION_REPORT = Path("docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_READINESS_43B.json")

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
REQUIRED_LIST_FIELDS = (
    "required_safety_counters",
    "required_ledger_checks",
    "required_idempotency_checks",
    "required_rejection_accounting_checks",
    "required_no_live_scope_checks",
    "required_determinism_checks",
    "promotion_checks",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _session_artifact() -> dict[str, object]:
    return _json(SESSION_ARTIFACT)


def _phase41_report() -> dict[str, object]:
    return _json(PHASE41_REPORT)


def _promotion_report() -> dict[str, object]:
    return _json(PROMOTION_REPORT)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _promotion_rejection_reasons(
    session: dict[str, object],
    phase41: dict[str, object],
    report: dict[str, object],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if report.get("source_phase42_artifact") != str(SESSION_ARTIFACT).replace("\\", "/"):
        reasons.append("promotion:source_phase42_artifact_mismatch")
    if report.get("source_phase41_report") != str(PHASE41_REPORT).replace("\\", "/"):
        reasons.append("promotion:source_phase41_report_mismatch")
    if report.get("source_phase42_artifact_sha256") != _sha256(SESSION_ARTIFACT):
        reasons.append("promotion:source_phase42_hash_mismatch")
    if report.get("source_phase41_report_sha256") != _sha256(PHASE41_REPORT):
        reasons.append("promotion:source_phase41_hash_mismatch")
    if not session.get("session_id"):
        reasons.append("promotion:session_id_missing")
    if report.get("evaluated_session_id") != session.get("session_id"):
        reasons.append("promotion:session_id_mismatch")
    if report.get("evaluated_operator_id") != session.get("operator_id"):
        reasons.append("promotion:operator_id_mismatch")
    if session.get("accepted") is not True or session.get("session_verdict") != "PASS":
        reasons.append("promotion:phase42_session_not_pass")
    if phase41.get("report_verdict") != "PASS":
        reasons.append("promotion:phase41_report_not_pass")
    if report.get("phase42_session_verdict") != session.get("session_verdict"):
        reasons.append("promotion:phase42_verdict_mismatch")
    if report.get("phase41_report_verdict") != phase41.get("report_verdict"):
        reasons.append("promotion:phase41_verdict_mismatch")
    if report.get("hard_cap") != session.get("hard_cap") or report.get("hard_cap") != 3:
        reasons.append("promotion:hard_cap_mismatch")
    if (
        report.get("evaluated_max_session_trades") != session.get("max_session_trades")
        or session.get("max_session_trades") != 2
    ):
        reasons.append("promotion:max_session_trades_mismatch")
    if report.get("evaluated_sessions") != 1:
        reasons.append("promotion:evaluated_sessions_mismatch")
    if report.get("evaluated_trades_requested") != session.get("trades_requested"):
        reasons.append("promotion:trades_requested_mismatch")
    if report.get("evaluated_trades_attempted") != session.get("trades_attempted"):
        reasons.append("promotion:trades_attempted_mismatch")
    if report.get("evaluated_trades_filled") != session.get("trades_filled"):
        reasons.append("promotion:trades_filled_mismatch")
    if report.get("evaluated_trades_rejected") != session.get("trades_rejected"):
        reasons.append("promotion:trades_rejected_mismatch")
    if report.get("evaluated_ledger_mutated") != session.get("ledger_mutated"):
        reasons.append("promotion:ledger_mutated_mismatch")
    if report.get("repeated_session_campaign_ready") is not False:
        reasons.append("promotion:campaign_ready_not_false")
    if report.get("promotion_verdict") != "NOT_READY":
        reasons.append("promotion:verdict_not_not_ready")
    if report.get("promotion_reason") != "PAPER_PROMOTION_REQUIRES_REPEATED_SESSION_EVIDENCE":
        reasons.append("promotion:reason_mismatch")
    if not isinstance(report.get("required_future_sessions_minimum"), int) or report.get(
        "required_future_sessions_minimum"
    ) <= report.get("evaluated_sessions", 0):
        reasons.append("promotion:future_session_minimum_not_repeated")
    if session.get("duplicate_mutation_blocked") is not True:
        reasons.append("promotion:duplicate_mutation_not_blocked")
    for field in FALSE_FLAGS:
        if session.get(field) is not False or report.get(field) is not False:
            reasons.append(f"promotion:{field}_not_false")
    for field in TRUE_FLAGS:
        if session.get(field) is not True or phase41.get(field) is not True or report.get(field) is not True:
            reasons.append(f"promotion:{field}_not_true")
    for field in REQUIRED_LIST_FIELDS:
        if not isinstance(report.get(field), list) or not report[field]:
            reasons.append(f"promotion:{field}_missing")
    if report.get("connector_ready_dialects_count") != 1:
        reasons.append("promotion:connector_ready_count_mismatch")
    if report.get("next_blocker") != "REPEATED_DETERMINISTIC_SESSION_REPORT_PACK_NOT_READY":
        reasons.append("promotion:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase43b_artifact_has_required_schema_and_source_references() -> None:
    report = _promotion_report()

    assert SESSION_ARTIFACT.exists()
    assert PHASE41_REPORT.exists()
    assert PROMOTION_REPORT.exists()
    assert report["schema_version"] == "deribit_paper_session_promotion_readiness.v1"
    assert report["phase"] == "43"
    assert report["source"] == "deterministic_phase42_session_promotion_readiness"
    assert report["source_phase42_artifact"] == str(SESSION_ARTIFACT).replace("\\", "/")
    assert report["source_phase41_report"] == str(PHASE41_REPORT).replace("\\", "/")
    assert report["source_phase42_artifact_sha256"] == _sha256(SESSION_ARTIFACT)
    assert report["source_phase41_report_sha256"] == _sha256(PHASE41_REPORT)


def test_phase43b_artifact_matches_phase42_session_and_phase41_report() -> None:
    session = _session_artifact()
    phase41 = _phase41_report()
    report = _promotion_report()

    assert report["evaluated_session_id"] == session["session_id"]
    assert report["evaluated_operator_id"] == session["operator_id"]
    assert report["phase42_session_verdict"] == session["session_verdict"] == "PASS"
    assert report["phase41_report_verdict"] == phase41["report_verdict"] == "PASS"
    assert report["hard_cap"] == session["hard_cap"] == 3
    assert report["evaluated_max_session_trades"] == session["max_session_trades"] == 2
    assert report["evaluated_sessions"] == 1
    assert report["repeated_session_campaign_ready"] is False
    assert report["promotion_verdict"] == "NOT_READY"


def test_phase43b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    report = _promotion_report()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert report["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1


def test_phase43b_promotion_validation_is_fail_closed_and_not_promoted() -> None:
    reasons = _promotion_rejection_reasons(_session_artifact(), _phase41_report(), _promotion_report())

    assert reasons == ()
    assert _promotion_report()["promotion_verdict"] == "NOT_READY"
    assert _promotion_report()["next_blocker"] == "REPEATED_DETERMINISTIC_SESSION_REPORT_PACK_NOT_READY"
