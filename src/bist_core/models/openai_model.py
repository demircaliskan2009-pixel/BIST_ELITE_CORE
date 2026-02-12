"""
FAZ117: OpenAIModel — ModelPlugin using OpenAI API, batch JSON, fail-closed network, file cache.
Requires: pip install openai (optional; lazy import).
API key: OPENAI_API_KEY env. Windows: PowerShell $env:OPENAI_API_KEY="sk-..."; CMD setx OPENAI_API_KEY "sk-..."
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_OPENAI_API_KEY_MSG = (
    "OPENAI_API_KEY is required for OpenAIModel. Set it before use:\n"
    "  PowerShell: $env:OPENAI_API_KEY=\"sk-...\"\n"
    "  CMD (persistent): setx OPENAI_API_KEY \"sk-...\""
)


def _batch_prompt(features: List[Dict[str, Any]]) -> str:
    """Build a single prompt for all symbols; instructs GPT to return strict JSON."""
    lines = [f"- {r.get('symbol','UNK')}: close={r.get('close',0)}" for r in features]
    items = "\n".join(lines)
    return (
        "Given these BIST symbols and closing prices, output a JSON array with one object per symbol. "
        "Each object: {\"symbol\":\"...\", \"score\": <float>, \"reason\": \"...\"}. "
        "Score: positive=buy, negative=sell, 0=hold. Output ONLY the JSON array, no other text.\n\n"
        f"{items}"
    )


def _parse_batch_json(content: str, feature_symbols: List[str]) -> Dict[str, float]:
    """
    Parse GPT response as [{"symbol":"X","score":0.1,"reason":"..."}, ...].
    Returns symbol->score map. Missing or parse error -> 0.0 for that symbol.
    """
    out: Dict[str, float] = {s: 0.0 for s in feature_symbols}
    if not content or not isinstance(content, str):
        return out
    content = content.strip()
    # Extract JSON array (may be wrapped in markdown ```json ... ```)
    if "```" in content:
        for part in content.split("```"):
            part = part.strip()
            if part.lower().startswith("json"):
                part = part[4:].strip()
            if part.startswith("["):
                content = part
                break
    try:
        arr = json.loads(content)
        if not isinstance(arr, list):
            return out
        for item in arr:
            if isinstance(item, dict):
                sym = (item.get("symbol") or "").strip()
                try:
                    sc = float(item.get("score", 0))
                except (TypeError, ValueError):
                    sc = 0.0
                if sym in out:
                    out[sym] = sc
    except (json.JSONDecodeError, TypeError):
        pass
    return out


def _cache_key(model: str, features: List[Dict[str, Any]]) -> str:
    """SHA256(model + json.dumps(features, sort_keys=True))."""
    payload = model + json.dumps(features, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OpenAIModel:
    """
    ModelPlugin: OpenAI GPT batch API for trading scores. Fail-closed: network disabled or no key -> error.
    Batch mode: ONE request per predict(), JSON [{"symbol","score","reason"}, ...]. Cache supported.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        cache_dir: Path | str | None = None,
    ) -> None:
        """
        model: Override env OPENAI_MODEL_NAME (default gpt-3.5-turbo).
        api_key: Override env OPENAI_API_KEY. Required; do not hard-code.
        cache_dir: Optional; if set, cache responses. Key = sha256(model+features).
        """
        self._model = model or os.environ.get("OPENAI_MODEL_NAME") or "gpt-3.5-turbo"
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key or not str(self._api_key).strip():
            raise ValueError(_OPENAI_API_KEY_MSG)
        self._cache_dir: Optional[Path] = Path(cache_dir) if cache_dir else None

    def predict(self, features: List[Dict[str, Any]]) -> List[float]:
        """
        One batch request for all features. Returns scores in same order. Parse fail -> 0.0 per symbol.
        Raises RuntimeError if network disabled (BIST_CORE_ALLOW_NETWORK not set).
        """
        from bist_core.env import network_allowed

        symbols = [(r.get("symbol") or "").strip() or "UNKNOWN" for r in features]
        scores_default = [0.0] * len(features)

        if not network_allowed():
            raise RuntimeError("NETWORK_DISABLED: set BIST_CORE_ALLOW_NETWORK=1")

        # Cache lookup (opt-in, default on when cache_dir set)
        if self._cache_dir:
            key = _cache_key(self._model, features)
            cache_file = self._cache_dir / f"{key}.json"
            if cache_file.is_file():
                try:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    if isinstance(data, list) and len(data) == len(symbols):
                        return [float(x) for x in data]
                    score_map = data if isinstance(data, dict) else {}
                    return [float(score_map.get(s, 0)) for s in symbols]
                except Exception:
                    pass

        # API call (lazy import)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key)
        except ImportError:
            return scores_default

        prompt = _batch_prompt(features)
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.3,
            )
            content = response.choices[0].message.content if response.choices else ""
        except Exception:
            return scores_default

        score_map = _parse_batch_json(content or "", symbols)
        scores = [score_map.get(s, 0.0) for s in symbols]

        # Cache write
        if self._cache_dir and scores:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / f"{_cache_key(self._model, features)}.json"
            try:
                cache_file.write_text(json.dumps(scores), encoding="utf-8")
            except Exception:
                pass

        return scores
