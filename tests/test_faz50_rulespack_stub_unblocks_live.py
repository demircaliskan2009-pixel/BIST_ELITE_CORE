from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_faz50_rulespack_stub_unblocks_live(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(repo_root / 'src')
    env['BIST_RULESPACK_DIR'] = str(repo_root / 'configs' / 'rulespack_stub')
    env['BIST_RESTRICTIONS_FILE'] = str(repo_root / 'configs' / 'restrictions_stub_vbts.csv')

    outdir = tmp_path / 'out'
    day = '2024-01-01'
    daydir = outdir / day
    daydir.mkdir(parents=True, exist_ok=True)

    # create minimal orders-intent candidates so cli can load something
    candidates = ['orders_intent.json', 'orders.intent.json', 'orders-intent.json']
    payload = {'schema_version': 1, 'orders': [], '_meta': {'execution': 'live', 'dry_run': True, 'armed_live': False}}
    for name in candidates:
        (daydir / name).write_text(json.dumps(payload), encoding='utf-8')

    broker_cfg = repo_root / 'configs' / 'broker_config.stub.example.json'
    assert broker_cfg.is_file()

    r = subprocess.run(
        [sys.executable, '-m', 'bist_core.cli', 'eod', 'execute',
         '--day', day, '--outdir', str(outdir), '--execution', 'live', '--broker-config', str(broker_cfg)],
        capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, cwd=str(repo_root)
    )
    exec_path = outdir / day / 'execution_result.json'
    assert exec_path.is_file(), (r.stdout + '\n' + r.stderr)
    data = json.loads(exec_path.read_text(encoding='utf-8'))
    codes = [e.get('code') for e in data.get('errors', []) if isinstance(e, dict)]
    assert 'bist_rules_tick_bands_missing' not in codes
    assert 'bist_rules_vbts_missing' not in codes
    assert 'bist_rules_missing' not in codes
