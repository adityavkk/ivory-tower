"""YAML strategy template loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Built-in templates shipped with the package
BUILTIN_DIR = Path(__file__).parent.parent / "data" / "strategies"

# User-defined templates
USER_DIR = Path.home() / ".ivory-tower" / "strategies"

VALID_ISOLATION_MODES = {
    "full", "read-peers", "read-all", "blackboard",
    "read-blackboard", "team", "cross-team-read", "none",
}


@dataclass
class BlackboardConfig:
    """Blackboard configuration for a phase."""
    name: str
    file: str | None = None
    dir: str | None = None
    access: str = "read"


@dataclass
class PhaseConfig:
    """Configuration for a single strategy phase."""
    name: str
    description: str
    isolation: str
    agents: str | list[str]
    output: str
    rounds: int | None = None
    input_from: str | list[str] | None = None
    fan_out: str | None = None
    blackboard: BlackboardConfig | None = None
    sandbox: dict[str, Any] | None = None


@dataclass
class TeamConfig:
    """Team definition for team-based strategies."""
    name: str
    role: str
    description: str = ""


@dataclass
class StrategyDefaults:
    """Default values for a strategy template."""
    sandbox_backend: str | None = None
    agents_min: int | None = None
    agents_max: int | None = None
    executor: str | None = None
    tools: list[str] = field(default_factory=list)
    rounds: int | None = None
    network: dict[str, Any] | None = None
    resources: dict[str, Any] | None = None
    snapshot_after_phase: bool = False
    snapshot_on_failure: bool = True


@dataclass
class StrategyTemplate:
    """A parsed and validated strategy template."""
    name: str
    description: str
    version: int
    engine: str | None = None
    phases: list[PhaseConfig] = field(default_factory=list)
    teams: list[TeamConfig] = field(default_factory=list)
    defaults: StrategyDefaults = field(default_factory=StrategyDefaults)
    source_path: Path | None = None


def load_template(name_or_path: str) -> StrategyTemplate:
    """Load a strategy template by name or file path.
    
    Resolution order:
    1. If it's an absolute path or contains path separators, load as file
    2. If it starts with ~ or /, expand and load as file
    3. Look in built-in templates (data/strategies/<name>.yml)
    4. Look in user templates (~/.ivory-tower/strategies/<name>.yml)
    
    Raises:
        FileNotFoundError: Template not found
    """
    # Check if it's a file path
    path = Path(name_or_path).expanduser()
    if path.is_absolute() or "/" in name_or_path or "\\" in name_or_path:
        if not path.exists():
            raise FileNotFoundError(f"Template file not found: {name_or_path}")
        return _load_from_file(path)
    
    # Look in built-in templates
    builtin_path = BUILTIN_DIR / f"{name_or_path}.yml"
    if builtin_path.exists():
        return _load_from_file(builtin_path)
    
    # Look in user templates
    user_path = USER_DIR / f"{name_or_path}.yml"
    if user_path.exists():
        return _load_from_file(user_path)
    
    # Not found
    available = list_template_names()
    available_str = ", ".join(available) if available else "none"
    raise FileNotFoundError(
        f"Template '{name_or_path}' not found. Available: {available_str}"
    )


def _load_from_file(path: Path) -> StrategyTemplate:
    """Parse a YAML file into a StrategyTemplate."""
    with open(path) as f:
        data = yaml.safe_load(f)
    
    template = _parse_template(data)
    template.source_path = path
    return template


def _parse_template(data: dict) -> StrategyTemplate:
    """Parse raw YAML dict into StrategyTemplate."""
    strategy = data.get("strategy", {})
    
    # Parse phases
    phases = []
    for phase_data in data.get("phases", []):
        bb = None
        if "blackboard" in phase_data:
            bb_data = phase_data["blackboard"]
            bb = BlackboardConfig(
                name=bb_data["name"],
                file=bb_data.get("file"),
                dir=bb_data.get("dir"),
                access=bb_data.get("access", "read"),
            )
        phases.append(PhaseConfig(
            name=phase_data["name"],
            description=phase_data.get("description", ""),
            isolation=phase_data["isolation"],
            agents=phase_data["agents"],
            output=phase_data["output"],
            rounds=phase_data.get("rounds"),
            input_from=phase_data.get("input_from"),
            fan_out=phase_data.get("fan_out"),
            blackboard=bb,
            sandbox=phase_data.get("sandbox"),
        ))
    
    # Parse teams
    teams = []
    for team_name, team_data in data.get("teams", {}).items():
        teams.append(TeamConfig(
            name=team_name,
            role=team_data.get("role", ""),
            description=team_data.get("description", ""),
        ))
    
    # Parse defaults
    defaults_data = data.get("defaults", {})
    sandbox_defaults = defaults_data.get("sandbox", {})
    agents_defaults = defaults_data.get("agents", {})
    
    defaults = StrategyDefaults(
        sandbox_backend=sandbox_defaults.get("backend"),
        agents_min=agents_defaults.get("min"),
        agents_max=agents_defaults.get("max"),
        executor=agents_defaults.get("executor"),
        tools=agents_defaults.get("tools", []),
        rounds=defaults_data.get("rounds"),
        network=sandbox_defaults.get("network"),
        resources=sandbox_defaults.get("resources"),
        snapshot_after_phase=sandbox_defaults.get("snapshot_after_phase", False),
        snapshot_on_failure=sandbox_defaults.get("snapshot_on_failure", True),
    )
    
    return StrategyTemplate(
        name=strategy.get("name", "unknown"),
        description=strategy.get("description", ""),
        version=strategy.get("version", 1),
        engine=strategy.get("engine"),
        phases=phases,
        teams=teams,
        defaults=defaults,
    )


def validate_template(template: StrategyTemplate) -> list[str]:
    """Validate a strategy template. Returns list of error messages (empty = valid)."""
    errors = []
    
    if not template.name or template.name == "unknown":
        errors.append("Template missing required field: strategy.name")
    
    if not template.description:
        errors.append("Template missing required field: strategy.description")
    
    if not template.phases:
        errors.append("Template must define at least one phase")
    
    phase_names = set()
    for phase in template.phases:
        if not phase.name:
            errors.append("Phase missing required field: name")
            continue
            
        if phase.name in phase_names:
            errors.append(f"Duplicate phase name: '{phase.name}'")
        phase_names.add(phase.name)
        
        if phase.isolation not in VALID_ISOLATION_MODES:
            errors.append(
                f"Phase '{phase.name}': unknown isolation mode '{phase.isolation}'. "
                f"Valid modes: {', '.join(sorted(VALID_ISOLATION_MODES))}"
            )
        
        # Validate input_from references
        if phase.input_from:
            refs = phase.input_from if isinstance(phase.input_from, list) else [phase.input_from]
            for ref in refs:
                if ref not in phase_names:
                    errors.append(
                        f"Phase '{phase.name}' references unknown phase '{ref}' in input_from"
                    )
        
        # Validate blackboard has name
        if phase.blackboard and not phase.blackboard.name:
            errors.append(f"Phase '{phase.name}': blackboard missing required field 'name'")
        
        # Validate blackboard access mode
        if phase.blackboard and phase.blackboard.access not in ("read", "append", "rw"):
            errors.append(
                f"Phase '{phase.name}': invalid blackboard access mode '{phase.blackboard.access}'"
            )
        
        # Validate fan_out references
        if phase.fan_out and phase.fan_out not in phase_names:
            errors.append(
                f"Phase '{phase.name}' references unknown phase '{phase.fan_out}' in fan_out"
            )
    
    return errors


def list_template_names() -> list[str]:
    """List available template names (built-in + user-defined)."""
    names = []
    
    # Built-in templates
    if BUILTIN_DIR.exists():
        for yml in sorted(BUILTIN_DIR.glob("*.yml")):
            names.append(yml.stem)
    
    # User-defined templates
    if USER_DIR.exists():
        for yml in sorted(USER_DIR.glob("*.yml")):
            if yml.stem not in names:
                names.append(yml.stem)
    
    return names


def list_templates() -> list[tuple[str, str, str]]:
    """List available templates with metadata.
    
    Returns:
        List of (name, description, source) tuples.
    """
    templates = []
    
    if BUILTIN_DIR.exists():
        for yml in sorted(BUILTIN_DIR.glob("*.yml")):
            try:
                t = _load_from_file(yml)
                templates.append((t.name, t.description, "built-in"))
            except Exception:
                continue
    
    if USER_DIR.exists():
        for yml in sorted(USER_DIR.glob("*.yml")):
            try:
                t = _load_from_file(yml)
                templates.append((t.name, t.description, "user"))
            except Exception:
                continue
    
    return templates
