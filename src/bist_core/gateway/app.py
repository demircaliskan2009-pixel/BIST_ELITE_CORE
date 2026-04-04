from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from bist_core.api.app import (
    AskRequest,
    ScanRequest,
    ask as api_ask,
    scan as api_scan,
    _latest_snapshot_day,
    _snapshot_root,
)
from bist_core.gateway.audit import AuditLogMiddleware, RequestIdMiddleware
from bist_core.gateway.security import GatewaySecurityMiddleware, customize_openapi
from bist_core.live_test.gateway_middleware import LiveTestChatLoggingMiddleware


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _with_src_on_pythonpath(env: dict[str, str]) -> dict[str, str]:
    repo = _repo_root()
    src = str(repo / "src")
    cur = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + os.pathsep + cur if cur else src
    return env


def _resolve_day(day: Optional[str]) -> str:
    base = _snapshot_root()
    resolved = day or _latest_snapshot_day(base)
    if not resolved:
        raise HTTPException(status_code=400, detail="No snapshots; provide day or run eod pipeline")
    return resolved


def _available_symbols(day: str) -> set[str]:
    try:
        from bist_core.services.marketdata import MarketData
        md = MarketData(_snapshot_root())
        return {str(x).strip().upper() for x in md.symbols(day)}
    except Exception:
        return set()


def _extract_symbol_from_message(message: str, day: str) -> Optional[str]:
    tokens = re.findall(r"\b[A-Z0-9]{2,6}\b", message.upper())
    symbols = _available_symbols(day)
    for token in tokens:
        if token in symbols:
            return token
    return None


def _extract_top_n(message: str, fallback: int) -> int:
    m = re.search(r"\btop\s+(\d{1,3})\b", message, flags=re.IGNORECASE)
    if not m:
        return fallback
    try:
        n = int(m.group(1))
    except Exception:
        return fallback
    return max(1, min(n, 100))


def _is_scan_message(message: str) -> bool:
    msg = message.lower()
    return "scan" in msg


def _format_scan_answer(payload: dict[str, Any]) -> str:
    day = str(payload.get("day", "")).strip()
    ranked = payload.get("ranked") or []
    lines = [f"Day: {day}"]
    for i, item in enumerate(ranked, start=1):
        sym = item.get("symbol")
        score = item.get("score")
        rationale = item.get("rationale")
        lines.append(f"{i}. {sym} | score={score} | {rationale}")
    return "\n".join(lines)


def _format_ask_answer(payload: dict[str, Any]) -> str:
    symbol = payload.get("symbol")
    day = payload.get("day")
    decision = payload.get("decision_raw", payload.get("decision"))
    score = payload.get("score")
    text = payload.get("text") or ""
    return (
        f"Symbol: {symbol}\n"
        f"Day: {day}\n"
        f"Decision: {decision}\n"
        f"Score: {score}\n"
        f"Reason: {text}"
    )


CHAT_HTML = """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>BIST_ELITE_CORE Chat</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; }
    h1 { font-size: 24px; }
    label { display:block; margin-top: 12px; font-weight: 600; }
    input, textarea, button { width: 100%; box-sizing: border-box; margin-top: 6px; padding: 10px; font-size: 14px; }
    textarea { min-height: 120px; }
    button { cursor: pointer; }
    pre { white-space: pre-wrap; background: #111; color: #eee; padding: 12px; border-radius: 8px; overflow-x: auto; }
    .muted { color: #666; font-size: 13px; margin-top: 8px; }
  </style>
</head>
<body>
  <h1>BIST_ELITE_CORE Chat</h1>
  <p class="muted">API key alanına gateway anahtarını gir. Örnek mesaj: “AKBNK için kısa vade senaryo üret” veya “scan top 3”</p>

  <label for="apiKey">X-API-Key</label>
  <input id="apiKey" type="password" placeholder="API key" />

  <label for="message">Mesaj</label>
  <textarea id="message" placeholder="AKBNK için kısa vade senaryo üret"></textarea>

  <label for="topN">top_n (opsiyonel)</label>
  <input id="topN" type="number" value="3" min="1" max="100" />

  <button id="sendBtn">Gönder</button>

  <h3>Yanıt</h3>
  <pre id="out">Hazır.</pre>

  <script>
    const apiKeyEl = document.getElementById("apiKey");
    const msgEl = document.getElementById("message");
    const topNEl = document.getElementById("topN");
    const outEl = document.getElementById("out");
    const btnEl = document.getElementById("sendBtn");

    apiKeyEl.value = localStorage.getItem("bist_gateway_api_key") || "";

    btnEl.addEventListener("click", async () => {
      const apiKey = apiKeyEl.value.trim();
      const message = msgEl.value.trim();
      const topN = parseInt(topNEl.value || "3", 10);

      localStorage.setItem("bist_gateway_api_key", apiKey);

      outEl.textContent = "İstek gönderiliyor...";
      try {
        const resp = await fetch("/v1/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": apiKey
          },
          body: JSON.stringify({ message, top_n: topN })
        });

        const text = await resp.text();
        let parsed = null;
        try { parsed = JSON.parse(text); } catch (_) {}

        outEl.textContent = parsed ? JSON.stringify(parsed, null, 2) : text;
      } catch (err) {
        outEl.textContent = String(err);
      }
    });
  </script>
</body>
</html>
"""


app = FastAPI(title="BIST_ELITE_CORE Gateway", version="0.1.0")

app.add_middleware(LiveTestChatLoggingMiddleware)
app.add_middleware(GatewaySecurityMiddleware)
app.openapi = (lambda _app=app: customize_openapi(_app))
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "bist_core_gateway", "version": "0.1.0"}


@app.get("/chat", response_class=HTMLResponse)
def chat_ui() -> str:
    return CHAT_HTML


class CliRequest(BaseModel):
    args: List[str] = Field(..., description="Arguments after 'bist_core.cli' module. Example: ['data','snapshots','doctor','--json']")
    timeout_s: int = Field(30, ge=1, le=120)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    top_n: int = Field(10, ge=1, le=100)
    day: Optional[str] = None
    horizon: Optional[str] = Field(None, pattern="^(short|mid|long)$")
    risk: Optional[str] = Field(None, pattern="^(low|med|high)$")
    capital: Optional[float] = None
    max_loss_tl: Optional[float] = None
    exclusions: Optional[str] = None


@app.post("/v1/cli")
def run_cli(req: CliRequest) -> dict[str, Any]:
    if not req.args:
        raise HTTPException(status_code=400, detail="args required")
    if req.args[0] != "data":
        raise HTTPException(status_code=403, detail="only 'data' commands allowed (gateway skeleton)")

    env = _with_src_on_pythonpath(os.environ.copy())
    cp = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *req.args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=int(req.timeout_s),
    )
    return {
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }


@app.post("/v1/ask")
def gateway_ask(req: AskRequest) -> dict[str, Any]:
    return api_ask(req)


@app.post("/v1/scan")
def gateway_scan(req: ScanRequest) -> dict[str, Any]:
    return api_scan(req)


@app.post("/v1/chat")
def gateway_chat(req: ChatRequest) -> dict[str, Any]:
    day = _resolve_day(req.day)
    message = req.message.strip()

    if _is_scan_message(message):
        scan_req = ScanRequest(
            day=day,
            top_n=_extract_top_n(message, req.top_n),
            horizon=req.horizon,
            risk=req.risk,
            capital=req.capital,
            max_loss_tl=req.max_loss_tl,
            exclusions=req.exclusions,
        )
        payload = api_scan(scan_req)
        return {
            "mode": "scan",
            "answer": _format_scan_answer(payload),
            "payload": payload,
        }

    symbol = _extract_symbol_from_message(message, day)
    if not symbol:
        raise HTTPException(status_code=400, detail="Mesajdan geçerli BIST sembolü çıkarılamadı")

    ask_req = AskRequest(
        symbol=symbol,
        day=day,
        horizon=req.horizon,
        risk=req.risk,
        capital=req.capital,
        max_loss_tl=req.max_loss_tl,
    )
    payload = api_ask(ask_req)
    return {
        "mode": "ask",
        "answer": _format_ask_answer(payload),
        "payload": payload,
    }
