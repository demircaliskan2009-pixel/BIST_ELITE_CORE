from __future__ import annotations

import ast
import re
from pathlib import Path

from crypto_core.data.public_feed_adapter import (
    PublicFeedAdapterProtocol,
    evaluate_public_feed_adapter_readiness,
    public_feed_adapter_ready,
)
from crypto_core.data.public_feed_connector import evaluate_public_feed_connector_gate
from crypto_core.data.public_feed_ingress import (
    evaluate_public_feed_ingress_packet,
    public_feed_ingress_decision_ready,
)
from crypto_core.data.public_feed_pipeline import (
    public_feed_pipeline_ready,
    run_offline_public_feed_pipeline,
)
from crypto_core.data.public_feed_run_plan import (
    PublicFeedRunMode,
    evaluate_public_feed_run_plan,
    public_feed_run_decision_ready,
)
from crypto_core.data.public_network_authorization import evaluate_public_network_authorization
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, RejectionReason
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.data import test_phase21t_public_feed_pipeline as phase21t

ROOT = Path(__file__).resolve().parents[3]
SCOPED_DATA_PATTERNS = (
    "public_feed_*.py",
    "public_network_authorization.py",
    "market_data_journal.py",
    "order_book.py",
)
SCOPED_VENUE_PATTERNS = ("dialect_*.py", "public_feed_dialects.py")
FORBIDDEN_IMPORT_ROOTS = {"requests", "httpx", "aiohttp", "websocket", "websockets"}
RUNTIME_METHOD_NAMES = {"connect", "start", "recv", "receive", "send", "subscribe", "stop"}


def test_scoped_public_feed_modules_do_not_import_network_libraries():
    imports = {imported for path in _scoped_public_feed_source_paths() for imported in _import_roots(path)}

    assert FORBIDDEN_IMPORT_ROOTS.isdisjoint(imports)


def test_scoped_public_feed_modules_do_not_read_environment():
    for path in _scoped_public_feed_source_paths():
        tree = _parse(path)
        for node in ast.walk(tree):
            assert not (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr == "environ"
            ), path
            assert not (isinstance(node, ast.Call) and _call_name(node) == "getenv"), path


def test_scoped_public_feed_modules_do_not_contain_credential_read_terms():
    forbidden_terms = re.compile(r"\b(api_key|api_secret|passphrase|private_key|token)\b", re.IGNORECASE)

    for path in _scoped_public_feed_source_paths():
        assert forbidden_terms.search(path.read_text(encoding="utf-8")) is None, path


def test_public_feed_adapter_protocol_exposes_no_runtime_methods():
    method_names = {
        name
        for name, value in PublicFeedAdapterProtocol.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert method_names == {"descriptor", "readiness"}
    assert RUNTIME_METHOD_NAMES.isdisjoint(method_names)


def test_new_public_feed_modules_do_not_import_execution_lifecycle_or_session_engine():
    forbidden_modules = {
        "crypto_core.execution.lifecycle",
        "crypto_core.session.engine",
    }

    for path in _scoped_public_feed_source_paths():
        imports = _import_modules(path)
        assert forbidden_modules.isdisjoint(imports), path


def test_execution_lifecycle_and_session_do_not_import_public_feed_modules():
    forbidden_prefixes = (
        "crypto_core.data.public_feed",
        "crypto_core.data.public_network_authorization",
        "crypto_core.data.market_data_journal",
        "crypto_core.data.order_book",
        "crypto_core.venue.dialect",
        "crypto_core.venue.public_feed_dialects",
    )
    inspected = (
        ROOT / "src" / "crypto_core" / "execution" / "lifecycle.py",
        ROOT / "src" / "crypto_core" / "session" / "engine.py",
    )

    for path in inspected:
        assert not any(module.startswith(forbidden_prefixes) for module in _import_modules(path)), path


def test_public_connector_stack_not_ready_if_network_authorization_rejects():
    auth = phase21t._auth(network_allowed=False)
    descriptor = phase21t._descriptor(network_authorization=auth)
    readiness = evaluate_public_feed_adapter_readiness(descriptor)
    decision = evaluate_public_feed_run_plan(
        phase21t._run_plan(
            adapter_descriptor=descriptor,
            adapter_readiness=readiness,
            network_authorization_decision=evaluate_public_network_authorization(auth),
        )
    )

    assert public_feed_adapter_ready(readiness) is False
    assert public_feed_run_decision_ready(decision) is False
    assert "public_network:not_allowed" in decision.rejection_reasons


def test_public_run_decision_not_ready_if_connector_gate_rejects():
    bad_gate = evaluate_public_feed_connector_gate(phase21t._connector_plan(network_enabled=True))
    decision = evaluate_public_feed_run_plan(phase21t._run_plan(connector_gate=bad_gate))

    assert public_feed_run_decision_ready(decision) is False
    assert "public_run:connector_gate_not_ready" in decision.rejection_reasons
    assert "public_connector:network_forbidden" in decision.rejection_reasons


def test_public_ingress_decision_not_ready_if_run_decision_rejects():
    rejected_run = evaluate_public_feed_run_plan(phase21t._run_plan(mode=PublicFeedRunMode.DISABLED))
    ingress = evaluate_public_feed_ingress_packet(phase21t._packet(run_decision=rejected_run))

    assert public_feed_ingress_decision_ready(ingress) is False
    assert "public_ingress:run_not_ready" in ingress.rejection_reasons
    assert "public_run:disabled" in ingress.rejection_reasons


def test_public_pipeline_not_ready_if_readiness_snapshot_rejects():
    policy = phase21t._policy(require_order_book=True)
    result = run_offline_public_feed_pipeline(phase21t._pipeline_input(run_plan=phase21t._run_plan(policy=policy)))

    assert public_feed_pipeline_ready(result) is False
    assert result.accepted is False
    assert "public_pipeline:readiness_rejected" in result.rejection_reasons
    assert "public_data:order_book_not_ready" in result.rejection_reasons


def test_static_public_feed_dialect_registry_has_no_connector_ready_placeholders():
    assert len(connector_ready_dialects()) == 1


def test_live_execution_still_rejected():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(
        phase21t._execution_request()
    )

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def test_no_bist_or_non_crypto_terms_in_scoped_public_feed_modules():
    forbidden_terms = re.compile(r"\b(BIST|Matriks|iDeal|KAP|VIOP)\b")

    for path in _scoped_public_feed_source_paths():
        assert forbidden_terms.search(path.read_text(encoding="utf-8")) is None, path


def test_scoped_filesystem_scan_excludes_legacy_ingestion_modules():
    paths = _scoped_public_feed_source_paths()

    assert paths
    assert all("src/crypto_core/data/ingestion/" not in _as_posix(path) for path in paths)
    assert all(_as_posix(path).startswith(("src/crypto_core/data/", "src/crypto_core/venue/")) for path in paths)


def _scoped_public_feed_source_paths() -> tuple[Path, ...]:
    data_dir = ROOT / "src" / "crypto_core" / "data"
    venue_dir = ROOT / "src" / "crypto_core" / "venue"
    paths: list[Path] = []
    for pattern in SCOPED_DATA_PATTERNS:
        paths.extend(path for path in data_dir.glob(pattern) if path.is_file())
    for pattern in SCOPED_VENUE_PATTERNS:
        paths.extend(path for path in venue_dir.glob(pattern) if path.is_file())
    return tuple(sorted(set(paths)))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _import_roots(path: Path) -> set[str]:
    return {module.split(".")[0] for module in _import_modules(path)}


def _import_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _as_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()
