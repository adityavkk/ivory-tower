"""Tests for protocol-based executor routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ivory_tower.agents import AgentConfig
from ivory_tower.executor import get_executor_for_agent
from ivory_tower.executor.acp_exec import ACPExecutor
from ivory_tower.executor.counselors_exec import CounselorsExecutor
from ivory_tower.executor.direct import DirectExecutor
from ivory_tower.executor.headless_exec import HeadlessExecExecutor


LOAD_AGENT_PATCH = "ivory_tower.executor.load_agent"


class TestGetExecutorForAgent:
    """Verify executor routing based on agent config protocol field."""

    @patch(LOAD_AGENT_PATCH)
    def test_acp_protocol_returns_acp_executor(self, mock_load):
        mock_load.return_value = AgentConfig(
            name="opencode", command="opencode", protocol="acp",
        )
        executor = get_executor_for_agent("opencode")
        assert isinstance(executor, ACPExecutor)

    @patch(LOAD_AGENT_PATCH)
    def test_headless_protocol_returns_headless_executor(self, mock_load):
        mock_load.return_value = AgentConfig(
            name="claude", command="claude", protocol="headless",
        )
        executor = get_executor_for_agent("claude")
        assert isinstance(executor, HeadlessExecExecutor)

    @patch(LOAD_AGENT_PATCH)
    def test_direct_protocol_returns_direct_executor(self, mock_load):
        mock_load.return_value = AgentConfig(
            name="llm", command="llm", protocol="direct",
        )
        executor = get_executor_for_agent("llm")
        assert isinstance(executor, DirectExecutor)

    @patch(LOAD_AGENT_PATCH)
    def test_counselors_protocol_returns_counselors_executor(self, mock_load):
        mock_load.return_value = AgentConfig(
            name="legacy", command="legacy", protocol="counselors",
        )
        executor = get_executor_for_agent("legacy")
        assert isinstance(executor, CounselorsExecutor)

    @patch(LOAD_AGENT_PATCH)
    def test_unknown_protocol_raises(self, mock_load):
        mock_load.return_value = AgentConfig(
            name="alien", command="alien", protocol="telepathy",
        )
        with pytest.raises(ValueError, match="telepathy"):
            get_executor_for_agent("alien")

    @patch(LOAD_AGENT_PATCH)
    def test_default_protocol_is_acp(self, mock_load):
        """Default protocol 'acp' routes to ACPExecutor."""
        mock_load.return_value = AgentConfig(
            name="default", command="default",
        )
        executor = get_executor_for_agent("default")
        assert isinstance(executor, ACPExecutor)

    def test_missing_agent_config_propagates(self):
        """FileNotFoundError from load_agent propagates."""
        with patch(LOAD_AGENT_PATCH, side_effect=FileNotFoundError("not found")):
            with pytest.raises(FileNotFoundError):
                get_executor_for_agent("ghost")
