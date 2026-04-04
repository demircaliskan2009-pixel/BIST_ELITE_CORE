from bist_core.gateway.app import app
rows = []
for r in app.routes:
    path = getattr(r, "path", None)
    methods = sorted(list(getattr(r, "methods", []) or []))
    rows.append((path, methods))
for row in sorted(rows):
    print(row)
