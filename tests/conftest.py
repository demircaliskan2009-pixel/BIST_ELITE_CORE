import os
import sys

import pytest

# Repo kökünü (içinde 'src/' olan dizini) sys.path'e ekle
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _strip_non_whitelist_bist_env() -> None:
    """
    CI/local: dev shells often export ad-hoc BIST_* keys (e.g. live runner paths).
    Subprocess CLI tests inherit os.environ and fail early with env_contract_violation.
    Remove only unknown BIST_* keys before collection (test infra; does not relax whitelist).
    """
    try:
        from bist_core.security.env_contract import BIST_ALLOWED_ENV_KEYS
    except Exception:
        return
    allow = {k.upper() for k in BIST_ALLOWED_ENV_KEYS}
    for k in list(os.environ.keys()):
        ku = str(k).upper()
        if ku.startswith("BIST_") and ku not in allow:
            try:
                del os.environ[k]
            except Exception:  # noqa: S110
                pass


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "slow: marks tests as slow (deselected by default, run with --runslow)")
    _strip_non_whitelist_bist_env()


def pytest_addoption(parser) -> None:
    parser.addoption("--runslow", action="store_true", default=False, help="run slow tests")


def pytest_collection_modifyitems(config, items) -> None:
    if config.getoption("--runslow"):
        return
    skip_slow = pytest.mark.skip(reason="slow test — pass --runslow to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture(autouse=True)
def _isolate_bist_env() -> None:
    """Tests sometimes leak ad-hoc BIST_* keys into os.environ; strip before/after each test."""
    _strip_non_whitelist_bist_env()
    yield
    _strip_non_whitelist_bist_env()
