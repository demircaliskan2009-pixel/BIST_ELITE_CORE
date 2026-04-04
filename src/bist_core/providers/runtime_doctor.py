from __future__ import annotations

import json

from .runtime import inspect_runtime


def main() -> int:
    status = inspect_runtime(must_exist=False)
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
