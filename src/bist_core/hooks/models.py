from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HookRule:
    type: str
    error: str
    field: str | None = None
    condition: str | None = None
    sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class HookResult:
    status: str
    reason: str = ""
    output: str | None = None


@dataclass(frozen=True)
class HookContext:
    task_type: str | None = None
    selected_prompt: str | None = None
    context: str | None = None
    response_style: str | None = None
    raw_text: str | None = None
    route: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
