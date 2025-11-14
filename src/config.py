import json, pathlib
BASE = pathlib.Path(__file__).resolve().parents[1]
def load_json(rel):
    with open(BASE/rel, 'r', encoding='utf-8') as f: return json.load(f)
CORE     = load_json('config/core.json')
SOURCES  = load_json('config/sources.json')
GATES    = load_json('config/gates.json')
STRATEGY = load_json('config/strategy.json')
