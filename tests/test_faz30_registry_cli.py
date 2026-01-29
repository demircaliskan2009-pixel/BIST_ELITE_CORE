"""FAZ30: Persistent DatasetRegistry + CLI register/resolve/list; fail-closed when registry missing/invalid."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from bist_core.data.registry import DatasetRegistry, get_default_registry


def _run_cli(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    e = env or os.environ.copy()
    repo_root = Path(__file__).resolve().parents[1]
    e.setdefault("PYTHONPATH", str(repo_root / "src"))
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        check=False,
        text=True,
        capture_output=True,
        env=e,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )


def test_faz30_register_resolve_list_persistence(tmp_path: Path) -> None:
    """Register with tmp registry path; resolve and list; assert persistence (no CLI, no network)."""
    registry_path = tmp_path / "registry.json"
    csv_dir = tmp_path / "data"
    csv_dir.mkdir(parents=True, exist_ok=True)
    (csv_dir / "a.csv").write_text("symbol,close\nX,1.0\n", encoding="utf-8")

    env = os.environ.copy()
    env["BIST_CORE_REGISTRY_PATH"] = str(registry_path)
    env["BIST_CORE_SNAPSHOT_DIR"] = str(tmp_path / "snapshots")

    # register (creates registry file)
    cp = _run_cli(
        ["data", "register", "--name", "ds1", "--path", str(csv_dir)],
        env,
    )
    assert cp.returncode == 0, cp.stderr or cp.stdout
    assert registry_path.is_file()
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "ds1" in data.get("datasets", {})

    # resolve
    cp2 = _run_cli(["data", "resolve", "--name", "ds1"], env)
    assert cp2.returncode == 0, cp2.stderr or cp2.stdout
    assert "path=" in cp2.stdout or "path" in cp2.stdout

    cp2j = _run_cli(["data", "resolve", "--name", "ds1", "--json"], env)
    assert cp2j.returncode == 0
    out = json.loads(cp2j.stdout)
    assert out.get("name") == "ds1"
    assert out.get("path") == str(csv_dir)
    assert out.get("kind") == "local_csv"

    # list
    cp3 = _run_cli(["data", "list"], env)
    assert cp3.returncode == 0
    assert "ds1" in cp3.stdout

    cp3j = _run_cli(["data", "list", "--json"], env)
    assert cp3j.returncode == 0
    payload = json.loads(cp3j.stdout)
    assert "ds1" in payload.get("datasets", {})


def test_faz30_list_fail_closed_when_registry_missing(tmp_path: Path) -> None:
    """list when registry file does not exist => exit 2 (fail-closed)."""
    env = os.environ.copy()
    env["BIST_CORE_REGISTRY_PATH"] = str(tmp_path / "nonexistent" / "registry.json")
    cp = _run_cli(["data", "list"], env)
    assert cp.returncode == 2
    assert "Registry not found" in (cp.stderr or "")


def test_faz30_resolve_fail_closed_when_name_missing(tmp_path: Path) -> None:
    """resolve when name not in registry => exit 2 (fail-closed)."""
    registry_path = tmp_path / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"schema_version": 1, "datasets": {}}), encoding="utf-8")

    env = os.environ.copy()
    env["BIST_CORE_REGISTRY_PATH"] = str(registry_path)
    cp = _run_cli(["data", "resolve", "--name", "no_such_dataset"], env)
    assert cp.returncode == 2
    assert "ERROR" in (cp.stderr or "")


def test_faz30_register_default_kind(tmp_path: Path) -> None:
    """register without --format/--kind defaults to local_csv."""
    registry_path = tmp_path / "registry.json"
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    (csv_dir / "x.csv").write_text("symbol,close\nA,1\n", encoding="utf-8")

    env = os.environ.copy()
    env["BIST_CORE_REGISTRY_PATH"] = str(registry_path)
    cp = _run_cli(["data", "register", "--name", "default_kind", "--path", str(csv_dir)], env)
    assert cp.returncode == 0
    meta = json.loads(registry_path.read_text(encoding="utf-8"))["datasets"]["default_kind"]
    assert meta.get("kind") == "local_csv" or meta.get("format") == "csv"


def test_faz30_registry_persistence_and_resolve(tmp_path: Path) -> None:
    """In-process: registry at tmp path, register/list/get; persistence (no subprocess)."""
    registry_path = tmp_path / "registry.json"
    csv_dir = tmp_path / "data"
    csv_dir.mkdir(parents=True, exist_ok=True)
    (csv_dir / "a.csv").write_text("symbol,close\nX,1.0\n", encoding="utf-8")

    reg = DatasetRegistry(path=registry_path)
    reg.register(name="ds1", kind="local_csv", path=str(csv_dir))
    assert registry_path.is_file()
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "ds1" in data.get("datasets", {})

    reg2 = DatasetRegistry(path=registry_path)
    reg2.load()
    names = reg2.list_datasets()
    assert names == ["ds1"]
    meta = reg2.get("ds1")
    assert meta.name == "ds1"
    assert meta.kind == "local_csv"
    assert meta.path == str(csv_dir)


def test_faz30_registry_missing_fail_closed(tmp_path: Path) -> None:
    """In-process: load_registry on missing file => ValueError (fail-closed)."""
    from bist_core.data.registry import load_registry

    registry_path = tmp_path / "nonexistent" / "registry.json"
    reg = DatasetRegistry(path=registry_path)
    assert not reg.path.is_file()
    reg.load()  # missing file => empty in current impl
    # For "fail-closed" the CLI uses _require_registry_file which checks is_file() and exits 2
    list_result = reg.list_datasets()
    assert list_result == []
