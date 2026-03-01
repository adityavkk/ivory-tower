"""Agent executor registry."""

from __future__ import annotations

from .counselors_exec import CounselorsExecutor
from .direct import DirectExecutor
from .types import AgentExecutor, AgentOutput

EXECUTORS: dict[str, type] = {
    "counselors": CounselorsExecutor,
    "direct": DirectExecutor,
}


def get_executor(name: str) -> AgentExecutor:
    """Return an instantiated agent executor by name.

    Raises ValueError for unknown executors.
    """
    cls = EXECUTORS.get(name)
    if cls is None:
        available = ", ".join(sorted(EXECUTORS.keys()))
        raise ValueError(f"Unknown executor '{name}'. Available: {available}")
    return cls()


__all__ = [
    "AgentExecutor",
    "AgentOutput",
    "CounselorsExecutor",
    "DirectExecutor",
    "get_executor",
    "EXECUTORS",
]
