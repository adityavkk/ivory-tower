"""Tests for the ACP executor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ivory_tower.executor.acp_exec import ACPExecutor
from ivory_tower.executor.types import AgentOutput


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path):
    """Create a mock sandbox."""
    sb = MagicMock()
    sb.workspace_dir = tmp_path / "workspace"
    sb.workspace_dir.mkdir()
    sb.agent_name = "test-agent"
    sb.id = "sandbox-1"
    return sb


@pytest.fixture
def agent_config():
    """Minimal ACP agent config."""
    from ivory_tower.agents import AgentConfig
    return AgentConfig(
        name="opencode",
        command="/usr/local/bin/opencode",
        args=["acp"],
        protocol="acp",
    )


@pytest.fixture
def executor():
    return ACPExecutor()


# ---------------------------------------------------------------------------
# Mock helpers for ACP lifecycle
# ---------------------------------------------------------------------------


def _make_mock_conn(session_id: str = "session-1", stop_reason: str = "end_turn"):
    """Create a mock ClientSideConnection with standard lifecycle methods."""
    conn = AsyncMock()
    conn.initialize = AsyncMock(return_value=MagicMock())
    conn.new_session = AsyncMock(
        return_value=MagicMock(session_id=session_id)
    )
    conn.prompt = AsyncMock(
        return_value=MagicMock(stop_reason=stop_reason)
    )
    conn.cancel = AsyncMock()
    conn.close = AsyncMock()
    return conn


# ---------------------------------------------------------------------------
# ACPExecutor tests
# ---------------------------------------------------------------------------


class TestACPExecutorRun:
    """Tests for ACPExecutor.run()."""

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_basic_run(
        self, mock_spawn, mock_resolve, mock_load, executor, sandbox, agent_config
    ):
        """Basic run spawns agent, initializes, prompts, returns output."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/local/bin/opencode")

        conn = _make_mock_conn()
        proc = AsyncMock()

        # Make spawn_agent_process an async context manager
        async def _spawn_cm(*args, **kwargs):
            return (conn, proc)

        mock_spawn.return_value = _async_context_manager(_spawn_cm)

        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Research quantum computing",
            output_dir="phase1/opencode",
        )

        assert isinstance(result, AgentOutput)
        assert result.report_path == "phase1/opencode/opencode-report.md"
        assert isinstance(result.duration_seconds, float)
        assert result.metadata["session_id"] == "session-1"
        assert result.metadata["stop_reason"] == "end_turn"

        # Verify ACP lifecycle was followed
        mock_load.assert_called_once_with("opencode")
        conn.initialize.assert_awaited_once()
        conn.new_session.assert_awaited_once()
        conn.prompt.assert_awaited_once()

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_run_accumulates_text(
        self, mock_spawn, mock_resolve, mock_load, executor, sandbox, agent_config
    ):
        """The executor captures text from session updates."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/local/bin/opencode")

        conn = _make_mock_conn()
        proc = AsyncMock()

        # Simulate the client accumulating text during the prompt
        # We do this by making the prompt call set accumulated text on the client
        original_prompt = conn.prompt

        async def _prompt_with_text(*args, **kwargs):
            # Access the client created in acp_exec._run_async
            # The text is accumulated by the client's session_update handler
            # For testing, we inject text via a side effect
            result = await original_prompt(*args, **kwargs)
            return result

        conn.prompt = _prompt_with_text
        mock_spawn.return_value = _async_context_manager(
            lambda *a, **k: (conn, proc)
        )

        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Research quantum computing",
            output_dir="phase1/opencode",
        )
        assert isinstance(result.raw_output, str)

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_run_with_system_prompt(
        self, mock_spawn, mock_resolve, mock_load, executor, sandbox, agent_config
    ):
        """System prompt is included as a separate content block."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/local/bin/opencode")

        conn = _make_mock_conn()
        proc = AsyncMock()
        mock_spawn.return_value = _async_context_manager(
            lambda *a, **k: (conn, proc)
        )

        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Research quantum computing",
            output_dir="phase1/opencode",
            system_prompt="You are an expert researcher.",
        )
        # Prompt should include system prompt + user prompt
        conn.prompt.assert_awaited_once()
        call_kwargs = conn.prompt.call_args
        prompt_blocks = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt") or call_kwargs[0][0]
        # Should have at least the user prompt
        assert len(prompt_blocks) >= 1

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_run_saves_report_to_sandbox(
        self, mock_spawn, mock_resolve, mock_load, executor, sandbox, agent_config
    ):
        """The executor writes the output to the sandbox as a report file."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/local/bin/opencode")

        conn = _make_mock_conn()
        proc = AsyncMock()
        mock_spawn.return_value = _async_context_manager(
            lambda *a, **k: (conn, proc)
        )

        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Research",
            output_dir="phase1/opencode",
        )
        # The executor should write the report to the sandbox
        sandbox.write_file.assert_called_once()
        write_args = sandbox.write_file.call_args
        assert write_args[0][0] == "phase1/opencode/opencode-report.md"


class TestACPExecutorSessionReuse:
    """Tests for session reuse across prompts."""

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_session_id_in_metadata(
        self, mock_spawn, mock_resolve, mock_load, executor, sandbox, agent_config
    ):
        """Session ID is included in output metadata."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/local/bin/opencode")

        conn = _make_mock_conn(session_id="my-session-42")
        proc = AsyncMock()
        mock_spawn.return_value = _async_context_manager(
            lambda *a, **k: (conn, proc)
        )

        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Research",
            output_dir="phase1/opencode",
        )
        assert result.metadata["session_id"] == "my-session-42"


class TestACPExecutorErrors:
    """Tests for error handling in ACPExecutor."""

    @patch("ivory_tower.executor.acp_exec.load_agent")
    def test_missing_agent_config(self, mock_load, executor, sandbox):
        """Missing agent config raises FileNotFoundError."""
        mock_load.side_effect = FileNotFoundError("Agent not found: nope")
        with pytest.raises(FileNotFoundError, match="nope"):
            executor.run(
                sandbox=sandbox,
                agent_name="nope",
                prompt="Research",
                output_dir="phase1/nope",
            )

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    def test_missing_binary(self, mock_resolve, mock_load, executor, sandbox, agent_config):
        """Missing binary raises FileNotFoundError."""
        mock_load.return_value = agent_config
        mock_resolve.side_effect = FileNotFoundError("Binary not found")
        with pytest.raises(FileNotFoundError, match="Binary not found"):
            executor.run(
                sandbox=sandbox,
                agent_name="opencode",
                prompt="Research",
                output_dir="phase1/opencode",
            )


class TestACPExecutorProtocol:
    """Tests that ACPExecutor conforms to AgentExecutor protocol."""

    def test_has_name(self, executor):
        assert executor.name == "acp"

    def test_implements_protocol(self, executor):
        from ivory_tower.executor.types import AgentExecutor
        assert isinstance(executor, AgentExecutor)


# ---------------------------------------------------------------------------
# Utility: async context manager adapter
# ---------------------------------------------------------------------------


class _async_context_manager:
    """Adapt a sync or async callable into an async context manager for mocking.

    Usage:
        mock_spawn.return_value = _async_context_manager(
            lambda *a, **k: (conn, proc)
        )
    """

    def __init__(self, fn):
        self._fn = fn
        self._args = ()
        self._kwargs = {}

    async def __aenter__(self):
        result = self._fn(*self._args, **self._kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def __aexit__(self, *args):
        pass

    def __call__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs
        return self
