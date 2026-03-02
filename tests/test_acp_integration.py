"""Live ACP integration tests -- require a real ACP-compatible agent on PATH.

These tests are marked @pytest.mark.live and excluded from default pytest
runs (configured in pyproject.toml: addopts = "-m 'not live'").

Run manually:
    uv run pytest tests/test_acp_integration.py -m live -v -s

Prerequisites:
    - At least one ACP agent binary on PATH (e.g. opencode, claude)
    - Agent config in ~/.ivory-tower/agents/<name>.yml
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ivory_tower.agents import load_agents
from ivory_tower.executor.acp_exec import ACPExecutor
from ivory_tower.sandbox.null import NullSandboxProvider

logger = logging.getLogger(__name__)


def _get_first_acp_agent() -> str | None:
    """Return the name of the first configured ACP agent, or None."""
    agents = load_agents()
    for name, config in agents.items():
        if config.protocol == "acp":
            return name
    return None


@pytest.fixture
def acp_agent_name():
    """Fixture that skips if no ACP agent is configured."""
    name = _get_first_acp_agent()
    if name is None:
        pytest.skip("No ACP agent configured in ~/.ivory-tower/agents/")
    return name


@pytest.fixture
def sandbox(tmp_path):
    """Create a NullSandbox for testing."""
    provider = NullSandboxProvider()
    return provider.create_sandbox(
        agent_name="test",
        run_id="live-test",
        config=None,
    )


@pytest.mark.live
class TestACPAgentLifecycle:
    """Full ACP lifecycle with a real agent."""

    def test_spawn_initialize_prompt_collect(self, acp_agent_name, sandbox):
        """Run a simple prompt through a real ACP agent."""
        executor = ACPExecutor()
        result = executor.run(
            sandbox=sandbox,
            agent_name=acp_agent_name,
            prompt="What is 2 + 2? Reply with just the number.",
            output_dir="test-output",
        )

        assert result.raw_output, "Agent should produce output"
        assert result.duration_seconds > 0
        assert result.metadata.get("protocol") == "acp"
        assert result.metadata.get("session_id"), "Should have a session_id"
        logger.info("Agent %s responded: %s", acp_agent_name, result.raw_output[:200])

    def test_streaming_callback_receives_chunks(self, acp_agent_name, sandbox):
        """Streaming callback should receive text chunks from a real agent."""
        chunks = []
        def on_chunk(agent: str, text: str) -> None:
            chunks.append((agent, text))

        executor = ACPExecutor()
        result = executor.run(
            sandbox=sandbox,
            agent_name=acp_agent_name,
            prompt="Say hello in exactly one word.",
            output_dir="test-stream",
            on_chunk=on_chunk,
        )

        assert result.raw_output, "Agent should produce output"
        # Chunks should have been received (at least one)
        assert len(chunks) > 0, "Streaming callback should receive chunks"
        # All chunks should reference the agent
        for agent, text in chunks:
            assert agent == acp_agent_name
            assert isinstance(text, str)

    def test_system_prompt_accepted(self, acp_agent_name, sandbox):
        """Agent should accept a system prompt without error."""
        executor = ACPExecutor()
        result = executor.run(
            sandbox=sandbox,
            agent_name=acp_agent_name,
            prompt="What is your role?",
            output_dir="test-system",
            system_prompt="You are a helpful math tutor.",
        )

        assert result.raw_output, "Agent should produce output"


@pytest.mark.live
class TestACPAgentDiscovery:
    """Tests for agent discovery and configuration."""

    def test_at_least_one_agent_configured(self):
        """There should be at least one agent configured for live tests."""
        agents = load_agents()
        if not agents:
            pytest.skip("No agents configured")
        assert len(agents) > 0

    def test_acp_agent_binary_exists(self, acp_agent_name):
        """The configured ACP agent's binary should be on PATH."""
        from ivory_tower.agents import load_agent, resolve_agent_binary

        config = load_agent(acp_agent_name)
        binary = resolve_agent_binary(config)
        assert binary.exists(), f"Binary {binary} should exist"
