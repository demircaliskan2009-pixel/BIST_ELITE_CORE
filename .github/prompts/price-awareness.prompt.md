---
name: price-awareness
description: "Use when current-price context, entry-versus-price evaluation, missed-entry detection, pullback logic, or stale live-price reasoning needs correction."
agent: agent
tools: ["filesystem/*"]
---

You are fixing price-awareness logic.

CHECK:
- entry vs current price
- missed entry detection
- pullback logic
- stale signal detection

OUTPUT:
- flaw explanation
- logic fix
- improved decision examples