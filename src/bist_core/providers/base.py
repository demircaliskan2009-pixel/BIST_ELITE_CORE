from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class ProviderError(RuntimeError):
    """Base class for provider related failures."""


class FailClosedError(ProviderError):
    """Raised when provider access must stop safely instead of guessing."""


class ProviderConfigError(ProviderError):
    """Raised when provider configuration is invalid or incomplete."""


@dataclass(frozen=True)
class ProviderDescriptor:
    kind: str
    name: str
    version: str = "v1"
    metadata: Mapping[str, Any] = field(default_factory=dict)
