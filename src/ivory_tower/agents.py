"""Agent configuration system.

Agent configs define how to invoke an agent: binary path, args, protocol,
environment variables, capabilities. Stored as YAML files in
~/.ivory-tower/agents/, one per agent.

Supports three protocol tiers:
  - acp: native ACP over stdio (Tier 1)
  - headless: non-ACP agents with structured CLI output (Tier 2)
  - legacy-counselors: existing counselors wrapper (compat)
  - direct: raw litellm calls, no agent runtime
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

AGENTS_DIR = Path.home() / ".ivory-tower" / "agents"

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(value: str) -> str:
    """Expand ${VAR} patterns in a string, keeping unresolvable ones as-is."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))
    return _ENV_VAR_PATTERN.sub(_replace, value)


@dataclass
class AgentConfig:
    """Configuration for an agent binary."""

    name: str
    command: str                                    # binary name or absolute path
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    protocol: str = "acp"                           # "acp" | "headless" | "legacy-counselors" | "direct"
    capabilities: dict[str, Any] = field(default_factory=dict)
    output_format: str | None = None                # headless only: "text" | "json" | "jsonl" | "stream-json"
    session: dict[str, str] | None = None           # headless only: continue/resume flags

    @classmethod
    def from_yaml(cls, path: Path) -> AgentConfig:
        """Load an agent config from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        name = data["name"]
        command = data["command"]

        # Expand env vars in the env dict
        raw_env = data.get("env", {})
        env = {k: _expand_env_vars(str(v)) for k, v in raw_env.items()}

        return cls(
            name=name,
            command=command,
            args=data.get("args", []),
            env=env,
            protocol=data.get("protocol", "acp"),
            capabilities=data.get("capabilities", {}),
            output_format=data.get("output_format"),
            session=data.get("session"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        """Create an AgentConfig from a plain dict."""
        return cls(
            name=data["name"],
            command=data["command"],
            args=data.get("args", []),
            env=data.get("env", {}),
            protocol=data.get("protocol", "acp"),
            capabilities=data.get("capabilities", {}),
            output_format=data.get("output_format"),
            session=data.get("session"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (suitable for YAML/JSON)."""
        d: dict[str, Any] = {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "protocol": self.protocol,
            "capabilities": self.capabilities,
        }
        if self.output_format is not None:
            d["output_format"] = self.output_format
        if self.session is not None:
            d["session"] = self.session
        return d


def load_agents() -> dict[str, AgentConfig]:
    """Load all agent configs from ~/.ivory-tower/agents/.

    Returns a dict mapping agent name -> AgentConfig.
    Skips non-YAML files and logs warnings for invalid configs.
    """
    if not AGENTS_DIR.exists():
        return {}

    agents: dict[str, AgentConfig] = {}
    for yml_file in sorted(AGENTS_DIR.glob("*.yml")):
        try:
            config = AgentConfig.from_yaml(yml_file)
            agents[config.name] = config
        except Exception:
            logger.warning("Failed to load agent config: %s", yml_file)
            continue
    return agents


def load_agent(name: str) -> AgentConfig:
    """Load a specific agent config by name.

    Raises FileNotFoundError if no config exists for the agent.
    """
    path = AGENTS_DIR / f"{name}.yml"
    if not path.exists():
        raise FileNotFoundError(
            f"Agent config not found: {path} -- "
            f"create it with: ivory agents add {name}"
        )
    return AgentConfig.from_yaml(path)


def resolve_agent_binary(config: AgentConfig) -> Path:
    """Resolve the agent's command to an absolute binary path.

    Tries the command as-is (absolute path), then searches PATH via
    shutil.which(). Raises FileNotFoundError if not found.
    """
    # Absolute path?
    cmd_path = Path(config.command)
    if cmd_path.is_absolute() and cmd_path.exists():
        return cmd_path

    # Search PATH
    found = shutil.which(config.command)
    if found is not None:
        return Path(found)

    raise FileNotFoundError(
        f"Agent binary not found: {config.command} "
        f"(agent: {config.name}). "
        f"Ensure the binary is installed and on your PATH."
    )


def validate_agent_configs(names: list[str]) -> list[str]:
    """Validate that agent configs exist for the given names.

    Returns a list of agent names that do NOT have configs.
    """
    if not names:
        return []

    available = load_agents()
    return [name for name in names if name not in available]
