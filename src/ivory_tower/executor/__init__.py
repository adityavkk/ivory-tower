"""Agent executor registry."""

from __future__ import annotations

from ivory_tower.agents import load_agent

from .acp_exec import ACPExecutor
from .counselors_exec import CounselorsExecutor
from .direct import DirectExecutor
from .headless_exec import HeadlessExecExecutor
from .types import AgentExecutor, AgentOutput

EXECUTORS: dict[str, type] = {
    "acp": ACPExecutor,
    "counselors": CounselorsExecutor,
    "direct": DirectExecutor,
    "headless": HeadlessExecExecutor,
}

# Maps agent config protocol field -> executor name
_PROTOCOL_TO_EXECUTOR: dict[str, str] = {
    "acp": "acp",
    "headless": "headless",
    "direct": "direct",
    "counselors": "counselors",
    "legacy-counselors": "counselors",
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


def get_executor_for_agent(agent_name: str) -> AgentExecutor:
    """Select the correct executor based on an agent's config protocol field.

    Loads the agent config from ~/.ivory-tower/agents/<name>.yml and
    dispatches to the appropriate executor based on the protocol field.

    Raises FileNotFoundError if no config exists.
    Raises ValueError for unknown protocols.
    """
    config = load_agent(agent_name)
    executor_name = _PROTOCOL_TO_EXECUTOR.get(config.protocol)
    if executor_name is None:
        raise ValueError(
            f"Unknown protocol '{config.protocol}' for agent '{agent_name}'. "
            f"Supported: {', '.join(sorted(_PROTOCOL_TO_EXECUTOR.keys()))}"
        )
    return get_executor(executor_name)


__all__ = [
    "ACPExecutor",
    "AgentExecutor",
    "AgentOutput",
    "CounselorsExecutor",
    "DirectExecutor",
    "HeadlessExecExecutor",
    "get_executor",
    "get_executor_for_agent",
    "EXECUTORS",
]
