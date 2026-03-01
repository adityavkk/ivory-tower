"""Agent profile loading and management.

Agent profiles define identity independent of strategy: model, role,
system prompt, tool permissions, sandbox overrides. Reusable across strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ivory_tower.sandbox.types import NetworkPolicy, ResourceLimits, SandboxConfig


PROFILES_DIR = Path.home() / ".ivory-tower" / "profiles"


@dataclass
class AgentProfile:
    """An agent's identity and configuration."""
    name: str
    role: str = "researcher"
    model: str | None = None              # None = use agent name as model
    system_prompt: str | None = None
    executor: str = "counselors"
    tools: list[str] = field(default_factory=list)
    sandbox: SandboxConfig | None = None  # Per-agent overrides

    @classmethod
    def from_yaml(cls, path: Path) -> AgentProfile:
        """Load an agent profile from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        sandbox = None
        if "sandbox" in data:
            sb = data["sandbox"]
            network = None
            if "network" in sb:
                network = NetworkPolicy(
                    allow_outbound=sb["network"].get("allow_outbound", True),
                    allowed_domains=sb["network"].get("allowed_domains"),
                    blocked_domains=sb["network"].get("blocked_domains", []),
                )
            resources = None
            if "resources" in sb:
                resources = ResourceLimits(
                    cpu_cores=sb["resources"].get("cpu_cores", 1.0),
                    memory_mb=sb["resources"].get("memory_mb", 1024),
                    disk_mb=sb["resources"].get("disk_mb", 512),
                    timeout_seconds=sb["resources"].get("timeout_seconds", 600),
                )
            sandbox = SandboxConfig(
                allow_paths=sb.get("allow_paths", []),
                network=network or NetworkPolicy(),
                resources=resources,
            )

        return cls(
            name=data["name"],
            role=data.get("role", "researcher"),
            model=data.get("model"),
            system_prompt=data.get("system_prompt"),
            executor=data.get("executor", "counselors"),
            tools=data.get("tools", []),
            sandbox=sandbox,
        )

    @classmethod
    def from_cli_shorthand(cls, spec: str) -> AgentProfile:
        """Parse CLI shorthand: '@profile-name', 'model:role', or 'model'.
        
        Examples:
            '@deep-researcher' -> loads from ~/.ivory-tower/profiles/deep-researcher.yml
            'claude:researcher' -> AgentProfile(name='claude', role='researcher', model='claude')
            'claude' -> AgentProfile(name='claude', model='claude')
        """
        if spec.startswith("@"):
            return cls.load_named(spec[1:])
        if ":" in spec:
            model, role = spec.split(":", 1)
            return cls(name=model, role=role, model=model)
        return cls(name=spec, model=spec)

    @classmethod
    def load_named(cls, name: str) -> AgentProfile:
        """Load from ~/.ivory-tower/profiles/<name>.yml."""
        path = PROFILES_DIR / f"{name}.yml"
        if not path.exists():
            raise FileNotFoundError(f"Agent profile not found: {path}")
        return cls.from_yaml(path)


def list_profiles() -> list[tuple[str, str, str]]:
    """List available agent profiles from ~/.ivory-tower/profiles/.
    
    Returns:
        List of (name, role, model) tuples.
    """
    if not PROFILES_DIR.exists():
        return []
    profiles = []
    for yml_file in sorted(PROFILES_DIR.glob("*.yml")):
        try:
            profile = AgentProfile.from_yaml(yml_file)
            profiles.append((profile.name, profile.role, profile.model or "default"))
        except Exception:
            continue
    return profiles
