# Chat Agent Flow — Pseudo-code for AI Integration

Example flow for a ChatGPT/Claude agent that uses BIST Elite Core.

---

## 1. Tool Definitions (OpenAI Function Calling / Claude Tools)

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "bist_ask",
        "description": "Get advisory for a single BIST symbol",
        "parameters": {
          "type": "object",
          "properties": {
            "symbol": { "type": "string", "description": "BIST symbol (e.g. AKBNK)" },
            "day": { "type": "string", "description": "YYYY-MM-DD" }
          },
          "required": ["symbol"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "bist_scan",
        "description": "Get ranked list of BIST symbols by score",
        "parameters": {
          "type": "object",
          "properties": {
            "day": { "type": "string", "description": "YYYY-MM-DD" },
            "top_n": { "type": "integer", "description": "Number of symbols to return", "default": 10 }
          }
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "bist_version",
        "description": "Get API version"
      }
    }
  ]
}
```

---

## 2. Pseudo-code Flow

```python
# Chat agent flow (pseudo-code)

def handle_user_message(msg: str) -> str:
    # 1. Parse intent (e.g. via LLM)
    intent = parse_intent(msg)  # "ask_symbol" | "scan_top" | "version" | "unknown"

    # 2. Call BIST API
    if intent == "ask_symbol":
        symbol = extract_symbol(msg)  # e.g. "AKBNK"
        day = extract_day(msg) or get_latest_day()
        result = post("/ask", json={"symbol": symbol, "day": day})
        return format_advice(result)

    elif intent == "scan_top":
        n = extract_top_n(msg) or 10
        day = extract_day(msg) or get_latest_day()
        result = post("/scan", json={"day": day, "top_n": n})
        return format_ranked(result["ranked"])

    elif intent == "version":
        result = get("/version")
        return f"API {result['api_version']}, schema {result['schema_version']}"

    else:
        return "I can help with: ask (symbol advice), scan (ranked list), version."
```

---

## 3. Example Dialogue

```
User: Hangi hisseler öne çıkıyor bugün?
Agent: [calls bist_scan(day=today, top_n=5)]
       En yüksek skorlu 5 hisse: AKBNK (0.85), GARAN (0.72), ...

User: AKBNK için ne diyorsun?
Agent: [calls bist_ask(symbol=AKBNK, day=today)]
       AKBNK için karar: BUY, skor 0.85. Kısa vadeli momentum olumlu.
```

---

## 4. Invariants

- **Versioned:** All responses include schema_version where applicable
- **Offline:** API requires BIST_CORE_ALLOW_NETWORK unset
- **BIST-only:** Symbols must be 2–6 uppercase alphanumeric
