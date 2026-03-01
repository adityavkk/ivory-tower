"""Agent executor protocol definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ivory_tower.sandbox.types import Sandbox


@dataclass
class AgentOutput:
    """Result of an agent execution."""
    report_path: str           # Relative path within sandbox to the agent's output
    raw_output: str            # Full text of the agent's response
    duration_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AgentExecutor(Protocol):
    """Abstraction over how LLM agents are invoked within a sandbox."""
    name: str

    def run(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
    ) -> AgentOutput: ...
