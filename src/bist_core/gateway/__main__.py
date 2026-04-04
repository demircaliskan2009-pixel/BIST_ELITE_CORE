from __future__ import annotations

import os

def main() -> int:
    # Optional runner: `python -m bist_core.gateway`
    import uvicorn
    host = os.environ.get("BIST_CORE_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("BIST_CORE_GATEWAY_PORT", "8000"))
    uvicorn.run("bist_core.gateway.app:app", host=host, port=port, reload=False)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
