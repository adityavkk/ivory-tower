"""Tests for ivory_tower.profiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ivory_tower.profiles import AgentProfile, PROFILES_DIR, list_profiles
from ivory_tower.sandbox.types import NetworkPolicy, ResourceLimits, SandboxConfig


# ---------------------------------------------------------------------------
# 1. AgentProfile defaults
# ---------------------------------------------------------------------------
class TestAgentProfileDefaults:
    def test_defaults(self):
        p = AgentProfile(name="test-agent")
        assert p.name == "test-agent"
        assert p.role == "researcher"
        assert p.model is None
        assert p.system_prompt is None
        assert p.executor == "counselors"
        assert p.tools == []
        assert p.sandbox is None


# ---------------------------------------------------------------------------
# 2-4. from_cli_shorthand – inline specs
# ---------------------------------------------------------------------------
class TestFromCliShorthand:
    def test_model_and_role(self):
        """'claude:researcher' parses model and role."""
        p = AgentProfile.from_cli_shorthand("claude:researcher")
        assert p.name == "claude"
        assert p.model == "claude"
        assert p.role == "researcher"

    def test_model_only(self):
        """'claude' parses model-only with default role."""
        p = AgentProfile.from_cli_shorthand("claude")
        assert p.name == "claude"
        assert p.model == "claude"
        assert p.role == "researcher"  # default

    def test_different_role(self):
        """'openai:critic' parses different role."""
        p = AgentProfile.from_cli_shorthand("openai:critic")
        assert p.name == "openai"
        assert p.model == "openai"
        assert p.role == "critic"


# ---------------------------------------------------------------------------
# 5-9. from_yaml
# ---------------------------------------------------------------------------
class TestFromYaml:
    def test_all_fields(self, tmp_path: Path):
        """from_yaml loads all fields from a YAML file."""
        data = {
            "name": "deep-researcher",
            "role": "analyst",
            "model": "claude-opus-4",
            "system_prompt": "You are an analyst.",
            "executor": "opencode",
            "tools": ["search", "browse"],
            "sandbox": {
                "allow_paths": ["/data"],
                "network": {
                    "allow_outbound": False,
                    "allowed_domains": ["example.com"],
                    "blocked_domains": ["evil.com"],
                },
                "resources": {
                    "cpu_cores": 2.0,
                    "memory_mb": 2048,
                    "disk_mb": 1024,
                    "timeout_seconds": 300,
                },
            },
        }
        yml = tmp_path / "full.yml"
        yml.write_text(yaml.dump(data))

        p = AgentProfile.from_yaml(yml)
        assert p.name == "deep-researcher"
        assert p.role == "analyst"
        assert p.model == "claude-opus-4"
        assert p.system_prompt == "You are an analyst."
        assert p.executor == "opencode"
        assert p.tools == ["search", "browse"]
        assert p.sandbox is not None
        assert p.sandbox.allow_paths == ["/data"]
        assert p.sandbox.network.allow_outbound is False
        assert p.sandbox.network.allowed_domains == ["example.com"]
        assert p.sandbox.network.blocked_domains == ["evil.com"]
        assert p.sandbox.resources is not None
        assert p.sandbox.resources.cpu_cores == 2.0
        assert p.sandbox.resources.memory_mb == 2048
        assert p.sandbox.resources.disk_mb == 1024
        assert p.sandbox.resources.timeout_seconds == 300

    def test_minimal_yaml(self, tmp_path: Path):
        """from_yaml with minimal YAML (only name) uses defaults."""
        yml = tmp_path / "minimal.yml"
        yml.write_text(yaml.dump({"name": "minimal-agent"}))

        p = AgentProfile.from_yaml(yml)
        assert p.name == "minimal-agent"
        assert p.role == "researcher"
        assert p.model is None
        assert p.system_prompt is None
        assert p.executor == "counselors"
        assert p.tools == []
        assert p.sandbox is None

    def test_sandbox_section_loads_config(self, tmp_path: Path):
        """from_yaml with sandbox section loads SandboxConfig."""
        data = {
            "name": "sandboxed",
            "sandbox": {
                "allow_paths": ["/tmp"],
            },
        }
        yml = tmp_path / "sandbox.yml"
        yml.write_text(yaml.dump(data))

        p = AgentProfile.from_yaml(yml)
        assert isinstance(p.sandbox, SandboxConfig)
        assert p.sandbox.allow_paths == ["/tmp"]
        # network defaults when not specified
        assert isinstance(p.sandbox.network, NetworkPolicy)
        assert p.sandbox.network.allow_outbound is True
        assert p.sandbox.resources is None

    def test_sandbox_network_loads_policy(self, tmp_path: Path):
        """from_yaml with sandbox.network loads NetworkPolicy."""
        data = {
            "name": "net-agent",
            "sandbox": {
                "network": {
                    "allow_outbound": False,
                    "allowed_domains": ["api.example.com"],
                },
            },
        }
        yml = tmp_path / "net.yml"
        yml.write_text(yaml.dump(data))

        p = AgentProfile.from_yaml(yml)
        assert p.sandbox is not None
        assert p.sandbox.network.allow_outbound is False
        assert p.sandbox.network.allowed_domains == ["api.example.com"]
        assert p.sandbox.network.blocked_domains == []

    def test_sandbox_resources_loads_limits(self, tmp_path: Path):
        """from_yaml with sandbox.resources loads ResourceLimits."""
        data = {
            "name": "heavy-agent",
            "sandbox": {
                "resources": {
                    "cpu_cores": 4.0,
                    "memory_mb": 4096,
                },
            },
        }
        yml = tmp_path / "resources.yml"
        yml.write_text(yaml.dump(data))

        p = AgentProfile.from_yaml(yml)
        assert p.sandbox is not None
        assert isinstance(p.sandbox.resources, ResourceLimits)
        assert p.sandbox.resources.cpu_cores == 4.0
        assert p.sandbox.resources.memory_mb == 4096
        # defaults for unspecified
        assert p.sandbox.resources.disk_mb == 512
        assert p.sandbox.resources.timeout_seconds == 600


# ---------------------------------------------------------------------------
# 10-11. from_cli_shorthand with @-prefix (load_named)
# ---------------------------------------------------------------------------
class TestLoadNamed:
    def test_at_prefix_loads_from_profiles_dir(self, tmp_path: Path):
        """'@deep-researcher' loads from profiles dir."""
        data = {
            "name": "deep-researcher",
            "role": "analyst",
            "model": "claude-opus-4",
        }
        yml = tmp_path / "deep-researcher.yml"
        yml.write_text(yaml.dump(data))

        with patch("ivory_tower.profiles.PROFILES_DIR", tmp_path):
            p = AgentProfile.from_cli_shorthand("@deep-researcher")
        assert p.name == "deep-researcher"
        assert p.role == "analyst"
        assert p.model == "claude-opus-4"

    def test_at_prefix_nonexistent_raises(self, tmp_path: Path):
        """'@nonexistent' raises FileNotFoundError."""
        with patch("ivory_tower.profiles.PROFILES_DIR", tmp_path):
            with pytest.raises(FileNotFoundError, match="Agent profile not found"):
                AgentProfile.from_cli_shorthand("@nonexistent")


# ---------------------------------------------------------------------------
# 12-13. list_profiles
# ---------------------------------------------------------------------------
class TestListProfiles:
    def test_list_profiles_returns_tuples(self, tmp_path: Path):
        """list_profiles() returns list of (name, role, model) tuples."""
        for name, role, model in [
            ("alpha", "researcher", "claude"),
            ("beta", "critic", None),
        ]:
            data = {"name": name, "role": role}
            if model:
                data["model"] = model
            (tmp_path / f"{name}.yml").write_text(yaml.dump(data))

        with patch("ivory_tower.profiles.PROFILES_DIR", tmp_path):
            result = list_profiles()

        assert len(result) == 2
        # sorted by filename
        assert result[0] == ("alpha", "researcher", "claude")
        assert result[1] == ("beta", "critic", "default")  # model=None -> "default"

    def test_list_profiles_empty_when_dir_missing(self, tmp_path: Path):
        """list_profiles() returns empty list when dir doesn't exist."""
        nonexistent = tmp_path / "does-not-exist"
        with patch("ivory_tower.profiles.PROFILES_DIR", nonexistent):
            result = list_profiles()
        assert result == []
