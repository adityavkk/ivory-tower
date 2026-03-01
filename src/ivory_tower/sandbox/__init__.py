"""Pluggable sandbox provider registry.

Usage:
    from ivory_tower.sandbox import get_provider
    provider = get_provider("local")
    sandbox = provider.create_sandbox(agent_name="claude", run_id="abc", ...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .agentfs import AgentFSSandboxProvider
from .daytona import DaytonaSandboxProvider
from .local import LocalSandboxProvider
from .null import NullSandboxProvider
from .types import (
    ExecutionResult,
    NetworkPolicy,
    ResourceLimits,
    Sandbox,
    SandboxConfig,
    SandboxProvider,
    SharedVolume,
)

if TYPE_CHECKING:
    pass

PROVIDERS: dict[str, type] = {
    "none": NullSandboxProvider,
    "local": LocalSandboxProvider,
    "agentfs": AgentFSSandboxProvider,
    "daytona": DaytonaSandboxProvider,
}

_INSTALL_MESSAGES: dict[str, str] = {
    "agentfs": (
        "The agentfs sandbox backend requires AgentFS CLI. "
        "Install: curl -fsSL https://agentfs.ai/install | bash"
    ),
    "daytona": (
        "The daytona sandbox backend requires the daytona SDK. "
        "Install: uv add daytona"
    ),
}


def get_provider(name: str) -> SandboxProvider:
    """Return an instantiated sandbox provider by name.

    Raises ValueError for unknown providers.
    Raises RuntimeError if the provider's dependencies are not installed.
    """
    cls = PROVIDERS.get(name)
    if cls is None:
        available = ", ".join(sorted(PROVIDERS.keys()))
        raise ValueError(f"Unknown sandbox backend '{name}'. Available: {available}")
    if not cls.is_available():
        msg = _INSTALL_MESSAGES.get(name, f"Sandbox backend '{name}' is not available.")
        raise RuntimeError(msg)
    return cls()


__all__ = [
    "ExecutionResult",
    "NetworkPolicy",
    "ResourceLimits",
    "Sandbox",
    "SandboxConfig",
    "SandboxProvider",
    "SharedVolume",
    "get_provider",
    "PROVIDERS",
]
