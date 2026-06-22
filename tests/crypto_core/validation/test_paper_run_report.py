"""Tests for the paper run report — deterministic, paper-only, gross-only, fail-closed, operator-readable
report/probe that binds an ADMITTED ``PaperEvidenceAdmissionRecord`` by digest with an independent expected
anchor. Verifies READY/REJECTED semantics, triple-digest binding, fail-closed defenses, determinism, the
forbidden-surface exclusions (no ``service/readiness``, no ``execution/paper_adapter``, no live/shadow/runtime),
the non-overclaim attestations, and the canonical serializer."""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_run_report as prr_module
from crypto_core.validation.paper_evidence_admission_record import (
    PaperEvidenceAdmissionRecord,
    PaperEvidenceAdmissionStatus,
    paper_evidence_admission_record_digest,
    paper_evidence_admission_record_to_dict,
)
from crypto_core.validation.paper_run_report import (
    PaperRunReport,
    PaperRunReportError,
    PaperRunReportStatus,
    build_paper_run_report,
    paper_run_report_digest,
    paper_run_report_to_dict,
)

_HEX_A = "a" * 64
_HEX_C = "c" * 64
_HEX_BAD = "d" * 64


class _SneakyStr(str):
    """A ``str`` subclass that lies about being non-empty — must never pass the exact-plain-string gate."""

    def strip(self, *args, **kwargs):  # noqa: D401 - adversarial override
        return "definitely-not-empty"


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _admitted(**overrides: object) -> PaperEvidenceAdmissionRecord:
    """Build a self-consistent ADMITTED admission record (digest sealed) for binding into a report."""
    fields: dict[str, object] = {
        "schema_version": "paper-evidence-admission-record.v1",
        "status": PaperEvidenceAdmissionStatus.ADMITTED,
        "admitted": True,
        "manifest_digest": _HEX_A,
        "expected_manifest_digest": _HEX_A,
        "manifest_status": "READY",
        "aggregate_id": "agg-1",
        "aggregate_digest": _HEX_C,
        "market_symbol": "BTC-PERPETUAL",
        "session_bridge_count": 1,
        "event_count": 1,
        "computed_event_count": 1,
        "closed_units_total": "10",
        "realized_pnl_total": "100",
        "rejection_reasons": (),
        "correlation_id": "corr-admit",
        "metadata": (),
    }
    fields.update(overrides)
    seed = PaperEvidenceAdmissionRecord(admission_digest="", **fields)  # type: ignore[arg-type]
    return replace(seed, admission_digest=paper_evidence_admission_record_digest(seed))


def _anchor(record: PaperEvidenceAdmissionRecord) -> str:
    return paper_evidence_admission_record_digest(record)


def _build_ready(**overrides: object) -> PaperRunReport:
    record = _admitted(**overrides)
    return build_paper_run_report(
        record,
        expected_admission_digest=_anchor(record),
        run_id="run-1",
        correlation_id="corr-report",
    )


# --------------------------------------------------------------------------------------------------
# 1. Happy path
# --------------------------------------------------------------------------------------------------


def test_admitted_record_with_matching_anchor_is_ready():
    report = _build_ready()
    assert report.status is PaperRunReportStatus.READY
    assert report.ready is True
    assert report.rejection_reasons == ()
    assert report.admission_status == "ADMITTED"
    assert report.run_id == "run-1"
    assert report.correlation_id == "corr-report"
    assert report.market_symbol == "BTC-PERPETUAL"
    assert report.event_count == 1
    assert report.realized_pnl_total == "100"
    assert report.closed_units_total == "10"
    assert _is_hex64(report.report_digest)


def test_report_digest_is_deterministic():
    a = _build_ready()
    b = _build_ready()
    assert a.report_digest == b.report_digest
    assert paper_run_report_to_dict(a) == paper_run_report_to_dict(b)


# --------------------------------------------------------------------------------------------------
# 2. Digest binding
# --------------------------------------------------------------------------------------------------


def test_wrong_expected_admission_digest_is_rejected_not_ready():
    record = _admitted()
    report = build_paper_run_report(
        record,
        expected_admission_digest=_HEX_BAD,
        run_id="run-1",
        correlation_id="corr-report",
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert report.ready is False
    assert "paper_run_report:expected_admission_digest_mismatch" in report.rejection_reasons


def test_bound_digests_appear_in_canonical_report():
    record = _admitted()
    payload = paper_run_report_to_dict(
        build_paper_run_report(
            record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
        )
    )
    assert payload["admission_digest"] == _anchor(record)
    assert payload["expected_admission_digest"] == _anchor(record)
    assert payload["manifest_digest"] == _HEX_A
    assert payload["expected_manifest_digest"] == _HEX_A
    assert payload["aggregate_digest"] == _HEX_C
    assert payload["aggregate_id"] == "agg-1"


def test_changed_bound_field_changes_report_digest():
    base = _build_ready()
    other_record = _admitted()
    other_run = build_paper_run_report(
        other_record, expected_admission_digest=_anchor(other_record), run_id="run-2", correlation_id="corr-report"
    )
    assert base.report_digest != other_run.report_digest

    # A different bound admission (different symbol) yields a different report digest.
    diff_symbol = _admitted(market_symbol="ETH-PERPETUAL")
    diff = build_paper_run_report(
        diff_symbol, expected_admission_digest=_anchor(diff_symbol), run_id="run-1", correlation_id="corr-report"
    )
    assert base.report_digest != diff.report_digest


def test_metadata_is_bound_and_changes_digest():
    record = _admitted()
    with_meta = build_paper_run_report(
        record,
        expected_admission_digest=_anchor(record),
        run_id="run-1",
        correlation_id="corr-report",
        metadata={"operator": "alice"},
    )
    without_meta = _build_ready()
    assert with_meta.metadata == (("operator", "alice"),)
    assert with_meta.report_digest != without_meta.report_digest


# --------------------------------------------------------------------------------------------------
# 3. Fail-closed
# --------------------------------------------------------------------------------------------------


def test_non_admitted_admission_cannot_be_ready():
    rejected = _admitted(status=PaperEvidenceAdmissionStatus.REJECTED, admitted=False, rejection_reasons=("x",))
    report = build_paper_run_report(
        rejected, expected_admission_digest=_anchor(rejected), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_not_admitted" in report.rejection_reasons


@pytest.mark.parametrize("bad", [None, object(), 123, "admission", {"status": "ADMITTED"}])
def test_wrong_typed_admission_raises(bad):
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(bad, expected_admission_digest=_HEX_A, run_id="run-1", correlation_id="corr-report")


def test_serializer_failure_is_rejected_not_crash(monkeypatch):
    def _boom(_record):
        raise RuntimeError("serializer exploded")

    monkeypatch.setattr(prr_module, "paper_evidence_admission_record_to_dict", _boom)
    record = _admitted()
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_payload_invalid" in report.rejection_reasons


def test_malformed_carried_manifest_digest_cannot_be_ready():
    # An admission carrying a non-hex manifest digest must not surface as a READY report.
    record = _admitted(manifest_digest="not-a-digest")
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_manifest_digest_invalid" in report.rejection_reasons


def test_malformed_admission_totals_cannot_be_ready():
    record = _admitted(realized_pnl_total="1.")  # non-canonical decimal
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_totals_malformed" in report.rejection_reasons


@pytest.mark.parametrize("bad_digest", ["", "x", "g" * 64, "A" * 64, "a" * 63, "a" * 65])
def test_malformed_expected_admission_digest_raises(bad_digest):
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record, expected_admission_digest=bad_digest, run_id="run-1", correlation_id="corr-report"
        )


@pytest.mark.parametrize("bad_run", ["", "   "])
def test_empty_run_id_raises(bad_run):
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record, expected_admission_digest=_anchor(record), run_id=bad_run, correlation_id="corr-report"
        )


@pytest.mark.parametrize("bad_corr", ["", "   "])
def test_empty_correlation_id_raises(bad_corr):
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id=bad_corr
        )


@pytest.mark.parametrize(
    "forbidden",
    ["live_order", "place_order", "deribit-x", "shadow_session", "route_id", "BIST100", "scheduler"],
)
def test_forbidden_token_in_run_id_raises(forbidden):
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record, expected_admission_digest=_anchor(record), run_id=forbidden, correlation_id="corr-report"
        )


def test_forbidden_token_in_metadata_raises():
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record,
            expected_admission_digest=_anchor(record),
            run_id="run-1",
            correlation_id="corr-report",
            metadata={"venue": "deribit"},
        )


@pytest.mark.parametrize("bad_meta", [{"k": 1}, {1: "v"}, [("k", "v")], "kv"])
def test_malformed_metadata_raises(bad_meta):
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record,
            expected_admission_digest=_anchor(record),
            run_id="run-1",
            correlation_id="corr-report",
            metadata=bad_meta,
        )


def test_str_subclass_empty_run_id_raises():
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record, expected_admission_digest=_anchor(record), run_id=_SneakyStr(""), correlation_id="corr-report"
        )


def test_str_subclass_empty_correlation_id_raises():
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id=_SneakyStr("")
        )


def test_str_subclass_metadata_key_raises():
    record = _admitted()
    with pytest.raises(PaperRunReportError):
        build_paper_run_report(
            record,
            expected_admission_digest=_anchor(record),
            run_id="run-1",
            correlation_id="corr-report",
            metadata={_SneakyStr("k"): "v"},
        )


def test_manifest_status_not_ready_cannot_be_ready():
    record = _admitted(manifest_status="REJECTED")
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_manifest_not_ready" in report.rejection_reasons


def test_upstream_rejection_reasons_cannot_be_ready():
    # Forged: admitted True but upstream rejection reasons present — must fail closed.
    record = _admitted(rejection_reasons=("upstream-x",))
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_upstream_rejected" in report.rejection_reasons


def test_manifest_digest_not_equal_expected_cannot_be_ready():
    # Forged: manifest_digest != expected_manifest_digest, self-consistently sealed — must fail closed.
    record = _admitted(expected_manifest_digest="b" * 64)
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_manifest_digest_mismatch" in report.rejection_reasons


def test_malformed_aggregate_digest_cannot_be_ready():
    record = _admitted(aggregate_digest="not-a-hex-digest")
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_aggregate_digest_invalid" in report.rejection_reasons


def test_computed_event_count_exceeding_event_count_cannot_be_ready():
    record = _admitted(event_count=1, computed_event_count=2)
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_count_incoherent" in report.rejection_reasons


def test_session_bridge_count_exceeding_event_count_cannot_be_ready():
    record = _admitted(event_count=1, session_bridge_count=2)
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_count_incoherent" in report.rejection_reasons


def test_zero_events_with_nonzero_totals_cannot_be_ready():
    record = _admitted(
        event_count=0,
        computed_event_count=0,
        session_bridge_count=0,
        realized_pnl_total="100",
        closed_units_total="10",
    )
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_empty_run_nonzero_totals" in report.rejection_reasons


# --------------------------------------------------------------------------------------------------
# 4. Determinism / immutability
# --------------------------------------------------------------------------------------------------


def test_build_does_not_mutate_admission_input():
    record = _admitted()
    before = paper_evidence_admission_record_to_dict(record)
    build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    after = paper_evidence_admission_record_to_dict(record)
    assert before == after


def test_admission_serializer_called_exactly_once(monkeypatch):
    # The single-snapshot contract: the public admission serializer is invoked exactly once (no second
    # read of mutable admission state after capture).
    original = prr_module.paper_evidence_admission_record_to_dict
    calls = {"n": 0}

    def _counting(record):
        calls["n"] += 1
        return original(record)

    monkeypatch.setattr(prr_module, "paper_evidence_admission_record_to_dict", _counting)
    record = _admitted()
    build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert calls["n"] == 1


def test_report_is_frozen():
    report = _build_ready()
    with pytest.raises(FrozenInstanceError):
        report.ready = False  # type: ignore[misc]


def test_digest_recompute_matches_self_digest():
    report = _build_ready()
    assert paper_run_report_digest(report) == report.report_digest


# --------------------------------------------------------------------------------------------------
# 5. Safety / imports (static analysis of the source module)
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(prr_module.__file__).read_text(encoding="utf-8")


# Module roots whose mere import would introduce nondeterminism / IO / network / time / threads.
_FORBIDDEN_RUNTIME_ROOTS = frozenset(
    {
        "time",
        "datetime",
        "random",
        "uuid",
        "secrets",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "asyncio",
        "threading",
        "multiprocessing",
        "subprocess",
        "os",
        "pathlib",
        "shutil",
        "signal",
        "selectors",
    }
)
# The only roots the pure report module is allowed to import.
_ALLOWED_IMPORT_ROOTS = frozenset(
    {"__future__", "hashlib", "json", "re", "collections", "dataclasses", "decimal", "enum", "crypto_core"}
)
_FORBIDDEN_BUILTIN_CALLS = frozenset({"open", "eval", "exec", "compile", "__import__", "input"})
_FORBIDDEN_IMPORT_FRAGMENTS = (
    "service.readiness",
    "execution.paper_adapter",
    "paper_live_service",
    "paper_shadow_session_controller",
    "connector",
    "scheduler",
    "runtime",
    "orchestrator",
    "venue",
)


def _collect_imports(tree: ast.AST) -> tuple[list[str], dict[str, str]]:
    """Return (full module paths imported, local-binding -> root-module map) — alias-aware."""
    modules: list[str] = []
    alias_to_root: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
                root = alias.name.split(".")[0]
                alias_to_root[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
            root = node.module.split(".")[0]
            for alias in node.names:
                # e.g. `from time import time as now` binds `now` -> root `time`.
                alias_to_root[alias.asname or alias.name] = root
    return modules, alias_to_root


def test_no_forbidden_module_imports():
    modules, _ = _collect_imports(ast.parse(_module_source()))
    for module in modules:
        root = module.split(".")[0]
        assert root in _ALLOWED_IMPORT_ROOTS, f"unexpected import root: {module}"
        assert root not in _FORBIDDEN_RUNTIME_ROOTS, f"forbidden runtime import: {module}"
        for fragment in _FORBIDDEN_IMPORT_FRAGMENTS:
            assert fragment not in module, f"forbidden import surface: {module}"
    # The only crypto_core import is the admission record contract it consumes.
    cc_imports = [m for m in modules if m.startswith("crypto_core")]
    assert cc_imports == ["crypto_core.validation.paper_evidence_admission_record"]


def test_no_forbidden_runtime_calls_alias_resistant():
    """Catch forbidden runtime calls even through aliases (``import time as t; t.time()`` /
    ``import datetime as dt; dt.datetime.now()`` / ``from time import time as now; now()``) and forbidden
    builtins (``open`` etc.). Alias-proof because imports are resolved to their real root module."""
    tree = ast.parse(_module_source())
    _, alias_to_root = _collect_imports(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            root = func
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                resolved = alias_to_root.get(root.id, root.id)
                assert resolved not in _FORBIDDEN_RUNTIME_ROOTS, f"forbidden runtime call via '{root.id}'"
        elif isinstance(func, ast.Name):
            assert func.id not in _FORBIDDEN_BUILTIN_CALLS, f"forbidden builtin call: {func.id}"
            assert alias_to_root.get(func.id) not in _FORBIDDEN_RUNTIME_ROOTS, f"forbidden call via bound '{func.id}'"


# --------------------------------------------------------------------------------------------------
# 6. Scope / non-overclaim
# --------------------------------------------------------------------------------------------------


def test_paper_only_and_gross_only_flags_true():
    report = _build_ready()
    assert report.paper_only is True
    assert report.gross_only is True


def test_all_hard_safety_flags_false():
    report = _build_ready()
    for flag in prr_module._ADMISSION_FALSE_FLAGS:
        assert getattr(report, flag) is False, flag


def test_non_overclaim_flags_false():
    report = _build_ready()
    assert report.prdv4_stage4_complete is False
    assert report.live_ready is False
    assert report.shadow_ready is False
    assert report.profitability_proven is False
    assert report.edge_proven is False


def test_admission_with_true_safety_flag_cannot_be_ready():
    record = _admitted(order_routed=True)
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.REJECTED
    assert "paper_run_report:admission_safety_violation" in report.rejection_reasons


# --------------------------------------------------------------------------------------------------
# 7. Operator-readable serializer
# --------------------------------------------------------------------------------------------------


def test_serializer_exact_keys_and_json_safe():
    report = _build_ready()
    payload = paper_run_report_to_dict(report)
    expected_keys = {
        "schema_version",
        "status",
        "ready",
        "run_id",
        "correlation_id",
        "admission_status",
        "admission_digest",
        "expected_admission_digest",
        "manifest_digest",
        "expected_manifest_digest",
        "aggregate_id",
        "aggregate_digest",
        "market_symbol",
        "session_bridge_count",
        "event_count",
        "computed_event_count",
        "closed_units_total",
        "realized_pnl_total",
        "rejection_reasons",
        "warnings",
        "metadata",
        "report_digest",
        "paper_only",
        "gross_only",
        "fees_included",
        "unrealized_pnl_included",
        "total_pnl_computed",
        "equity_or_capital_computed",
        "capital_reserved",
        "capital_mutated",
        "balance_mutated",
        "live_position_mutated",
        "real_money_enabled",
        "real_orders_enabled",
        "order_routed",
        "venue_order_id_created",
        "exchange_order_id_created",
        "client_order_id_created",
        "route_id_created",
        "execution_instruction_created",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "profitability_proven",
        "edge_proven",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["status"] == "READY"
    # Fully JSON-serializable with no float drift (canonical separators / allow_nan disabled).
    dumped = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert isinstance(dumped, str)


def test_empty_run_with_zero_totals_surfaces_warning_but_stays_ready():
    # A truthful empty run: zero events, zero counts, canonical-zero gross totals -> READY + warning.
    record = _admitted(
        event_count=0,
        computed_event_count=0,
        session_bridge_count=0,
        realized_pnl_total="0",
        closed_units_total="0",
    )
    report = build_paper_run_report(
        record, expected_admission_digest=_anchor(record), run_id="run-1", correlation_id="corr-report"
    )
    assert report.status is PaperRunReportStatus.READY
    assert "paper_run_report:no_realized_events" in report.warnings
