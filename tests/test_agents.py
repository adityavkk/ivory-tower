"""Tests for agent configuration system."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from ivory_tower.agents import (
    AGENTS_DIR,
    AgentConfig,
    load_agent,
    load_agents,
    resolve_agent_binary,
    validate_agent_configs,
)


# ---------------------------------------------------------------------------
# AgentConfig dataclass
# ---------------------------------------------------------------------------


class TestAgentConfig:
    """Tests for the AgentConfig dataclass."""

    def test_minimal_config(self):
        config = AgentConfig(name="opencode", command="opencode")
        assert config.name == "opencode"
        assert config.command == "opencode"
        assert config.args == []
        assert config.env == {}
        assert config.protocol == "acp"
        assert config.capabilities == {}

    def test_full_config(self):
        config = AgentConfig(
            name="claude",
            command="claude",
            args=["--no-ui"],
            env={"ANTHROPIC_API_KEY": "sk-test"},
            protocol="acp",
            capabilities={"tools": ["read", "write", "execute"]},
        )
        assert config.name == "claude"
        assert config.command == "claude"
        assert config.args == ["--no-ui"]
        assert config.env == {"ANTHROPIC_API_KEY": "sk-test"}
        assert config.protocol == "acp"
        assert config.capabilities == {"tools": ["read", "write", "execute"]}

    def test_headless_protocol(self):
        config = AgentConfig(
            name="aider",
            command="aider",
            args=["--message", "{prompt}", "--yes"],
            protocol="headless",
            output_format="text",
        )
        assert config.protocol == "headless"
        assert config.output_format == "text"

    def test_session_config(self):
        config = AgentConfig(
            name="claude",
            command="claude",
            protocol="headless",
            session={"continue_flag": "--continue", "resume_flag": "--resume"},
        )
        assert config.session == {"continue_flag": "--continue", "resume_flag": "--resume"}

    def test_default_protocol_is_acp(self):
        config = AgentConfig(name="test", command="test")
        assert config.protocol == "acp"

    def test_default_output_format_is_none(self):
        config = AgentConfig(name="test", command="test")
        assert config.output_format is None


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class TestYAMLLoading:
    """Tests for loading agent configs from YAML files."""

    def test_load_agent_from_yaml(self, tmp_path):
        """Load a single agent config from a YAML file."""
        yaml_content = dedent("""\
            name: opencode
            command: opencode
            args: ["acp", "--cwd", "{workspace}"]
            protocol: acp
            env:
              OPENCODE_CONFIG_CONTENT: '{"model": "anthropic/claude-sonnet-4-5"}'
            capabilities:
              tools: [read, write, execute]
        """)
        config_path = tmp_path / "opencode.yml"
        config_path.write_text(yaml_content)

        config = AgentConfig.from_yaml(config_path)
        assert config.name == "opencode"
        assert config.command == "opencode"
        assert config.args == ["acp", "--cwd", "{workspace}"]
        assert config.protocol == "acp"
        assert config.env == {"OPENCODE_CONFIG_CONTENT": '{"model": "anthropic/claude-sonnet-4-5"}'}
        assert config.capabilities == {"tools": ["read", "write", "execute"]}

    def test_load_minimal_yaml(self, tmp_path):
        """Minimal YAML with just name and command."""
        yaml_content = dedent("""\
            name: goose
            command: goose
        """)
        config_path = tmp_path / "goose.yml"
        config_path.write_text(yaml_content)

        config = AgentConfig.from_yaml(config_path)
        assert config.name == "goose"
        assert config.command == "goose"
        assert config.args == []
        assert config.env == {}
        assert config.protocol == "acp"
        assert config.capabilities == {}

    def test_load_headless_agent_yaml(self, tmp_path):
        """Load a headless (Tier 2) agent config."""
        yaml_content = dedent("""\
            name: claude
            command: claude
            args:
              - "-p"
              - "{prompt}"
              - "--output-format"
              - "stream-json"
              - "--verbose"
            protocol: headless
            output_format: stream-json
            session:
              continue_flag: "--continue"
              resume_flag: "--resume"
            env:
              ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
            capabilities:
              tools: [read, write, execute]
        """)
        config_path = tmp_path / "claude.yml"
        config_path.write_text(yaml_content)

        config = AgentConfig.from_yaml(config_path)
        assert config.name == "claude"
        assert config.protocol == "headless"
        assert config.output_format == "stream-json"
        assert config.session == {"continue_flag": "--continue", "resume_flag": "--resume"}

    def test_load_agent_missing_name_raises(self, tmp_path):
        """YAML without 'name' field should raise."""
        yaml_content = dedent("""\
            command: opencode
        """)
        config_path = tmp_path / "bad.yml"
        config_path.write_text(yaml_content)

        with pytest.raises(KeyError, match="name"):
            AgentConfig.from_yaml(config_path)

    def test_load_agent_missing_command_raises(self, tmp_path):
        """YAML without 'command' field should raise."""
        yaml_content = dedent("""\
            name: opencode
        """)
        config_path = tmp_path / "bad.yml"
        config_path.write_text(yaml_content)

        with pytest.raises(KeyError, match="command"):
            AgentConfig.from_yaml(config_path)

    def test_env_var_expansion(self, tmp_path, monkeypatch):
        """Environment variables in ${VAR} format are expanded."""
        monkeypatch.setenv("MY_API_KEY", "sk-real-key")
        yaml_content = dedent("""\
            name: claude
            command: claude
            env:
              API_KEY: "${MY_API_KEY}"
        """)
        config_path = tmp_path / "claude.yml"
        config_path.write_text(yaml_content)

        config = AgentConfig.from_yaml(config_path)
        assert config.env == {"API_KEY": "sk-real-key"}

    def test_env_var_expansion_missing_var_kept(self, tmp_path, monkeypatch):
        """Missing env vars stay as literal ${VAR} strings."""
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        yaml_content = dedent("""\
            name: claude
            command: claude
            env:
              API_KEY: "${NONEXISTENT_KEY}"
        """)
        config_path = tmp_path / "claude.yml"
        config_path.write_text(yaml_content)

        config = AgentConfig.from_yaml(config_path)
        assert config.env == {"API_KEY": "${NONEXISTENT_KEY}"}


# ---------------------------------------------------------------------------
# load_agents / load_agent (directory-based loading)
# ---------------------------------------------------------------------------


class TestLoadAgents:
    """Tests for loading agents from the agents directory."""

    def test_load_agents_from_dir(self, tmp_path, monkeypatch):
        """Load all agents from a directory."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        (agents_dir / "opencode.yml").write_text(yaml.dump({
            "name": "opencode",
            "command": "opencode",
            "args": ["acp"],
        }))
        (agents_dir / "goose.yml").write_text(yaml.dump({
            "name": "goose",
            "command": "goose",
            "args": ["acp"],
        }))

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        agents = load_agents()
        assert "opencode" in agents
        assert "goose" in agents
        assert agents["opencode"].command == "opencode"

    def test_load_agents_empty_dir(self, tmp_path, monkeypatch):
        """Empty directory returns empty dict."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        agents = load_agents()
        assert agents == {}

    def test_load_agents_dir_not_exists(self, tmp_path, monkeypatch):
        """Non-existent directory returns empty dict."""
        agents_dir = tmp_path / "no-such-dir"

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        agents = load_agents()
        assert agents == {}

    def test_load_agent_by_name(self, tmp_path, monkeypatch):
        """Load a specific agent by name."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "opencode.yml").write_text(yaml.dump({
            "name": "opencode",
            "command": "opencode",
        }))

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        config = load_agent("opencode")
        assert config.name == "opencode"

    def test_load_agent_not_found(self, tmp_path, monkeypatch):
        """Loading a non-existent agent raises FileNotFoundError."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        with pytest.raises(FileNotFoundError, match="no-such-agent"):
            load_agent("no-such-agent")

    def test_load_agents_skips_non_yaml(self, tmp_path, monkeypatch):
        """Non-YAML files in the directory are ignored."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "opencode.yml").write_text(yaml.dump({
            "name": "opencode",
            "command": "opencode",
        }))
        (agents_dir / "README.md").write_text("# Agents")

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        agents = load_agents()
        assert len(agents) == 1
        assert "opencode" in agents


# ---------------------------------------------------------------------------
# resolve_agent_binary
# ---------------------------------------------------------------------------


class TestResolveAgentBinary:
    """Tests for resolving agent binary paths."""

    def test_resolve_absolute_path(self, tmp_path):
        """Absolute command path that exists resolves directly."""
        fake_bin = tmp_path / "myagent"
        fake_bin.write_text("#!/bin/sh\necho hi")
        fake_bin.chmod(0o755)

        config = AgentConfig(name="test", command=str(fake_bin))
        resolved = resolve_agent_binary(config)
        assert resolved == fake_bin

    def test_resolve_on_path(self, monkeypatch):
        """Command available on PATH resolves via shutil.which."""
        # 'python3' should be on PATH in most CI/dev environments
        config = AgentConfig(name="test", command="python3")
        resolved = resolve_agent_binary(config)
        assert resolved is not None
        assert resolved.exists()

    def test_resolve_missing_binary_raises(self, monkeypatch):
        """Command not found anywhere raises FileNotFoundError."""
        config = AgentConfig(
            name="test",
            command="nonexistent-binary-abc123xyz",
        )
        with pytest.raises(FileNotFoundError, match="nonexistent-binary-abc123xyz"):
            resolve_agent_binary(config)


# ---------------------------------------------------------------------------
# validate_agent_configs
# ---------------------------------------------------------------------------


class TestValidateAgentConfigs:
    """Tests for validating agent config names against registered agents."""

    def test_all_valid(self, tmp_path, monkeypatch):
        """All requested agents have configs -- returns empty list."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        for name in ["opencode", "goose"]:
            (agents_dir / f"{name}.yml").write_text(yaml.dump({
                "name": name,
                "command": name,
            }))

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        invalid = validate_agent_configs(["opencode", "goose"])
        assert invalid == []

    def test_some_invalid(self, tmp_path, monkeypatch):
        """Some agents missing -- returns names of missing agents."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "opencode.yml").write_text(yaml.dump({
            "name": "opencode",
            "command": "opencode",
        }))

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        invalid = validate_agent_configs(["opencode", "claude", "gemini"])
        assert sorted(invalid) == ["claude", "gemini"]

    def test_empty_list(self, tmp_path, monkeypatch):
        """Validating empty list returns empty."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        monkeypatch.setattr("ivory_tower.agents.AGENTS_DIR", agents_dir)
        invalid = validate_agent_configs([])
        assert invalid == []


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for AgentConfig serialization."""

    def test_to_dict(self):
        config = AgentConfig(
            name="opencode",
            command="opencode",
            args=["acp"],
            env={"KEY": "val"},
            protocol="acp",
            capabilities={"tools": ["read"]},
        )
        d = config.to_dict()
        assert d["name"] == "opencode"
        assert d["command"] == "opencode"
        assert d["args"] == ["acp"]
        assert d["env"] == {"KEY": "val"}
        assert d["protocol"] == "acp"

    def test_from_dict(self):
        d = {
            "name": "goose",
            "command": "goose",
            "args": ["acp"],
            "protocol": "acp",
        }
        config = AgentConfig.from_dict(d)
        assert config.name == "goose"
        assert config.command == "goose"

    def test_round_trip(self):
        original = AgentConfig(
            name="claude",
            command="claude",
            args=["--no-ui"],
            env={"KEY": "val"},
            protocol="headless",
            output_format="stream-json",
            session={"continue_flag": "--continue"},
            capabilities={"tools": ["read", "write"]},
        )
        d = original.to_dict()
        restored = AgentConfig.from_dict(d)
        assert restored.name == original.name
        assert restored.command == original.command
        assert restored.args == original.args
        assert restored.env == original.env
        assert restored.protocol == original.protocol
        assert restored.output_format == original.output_format
        assert restored.session == original.session
        assert restored.capabilities == original.capabilities
