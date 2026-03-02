"""Tests for ACP session continuity across multiple prompts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from ivory_tower.executor.acp_exec import ACPExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _async_context_manager:
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


@pytest.fixture
def sandbox(tmp_path):
    sb = MagicMock()
    sb.workspace_dir = tmp_path / "workspace"
    sb.workspace_dir.mkdir()
    sb.agent_name = "test-agent"
    sb.id = "sandbox-1"
    return sb


@pytest.fixture
def agent_config():
    from ivory_tower.agents import AgentConfig
    return AgentConfig(
        name="opencode", command="/usr/bin/opencode",
        args=["acp"], protocol="acp",
    )


def _make_mock_conn(session_id="s1"):
    conn = AsyncMock()
    conn.initialize = AsyncMock(return_value=MagicMock())
    conn.new_session = AsyncMock(return_value=MagicMock(session_id=session_id))
    conn.prompt = AsyncMock(return_value=MagicMock(stop_reason="end_turn"))
    conn.cancel = AsyncMock()
    conn.close = AsyncMock()
    return conn


# ---------------------------------------------------------------------------
# Session continuity tests
# ---------------------------------------------------------------------------


class TestSessionContinuity:
    """Tests for maintaining sessions across multiple run() calls."""

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_first_call_creates_session(
        self, mock_spawn, mock_resolve, mock_load, sandbox, agent_config,
    ):
        """First run() creates a new session and returns session_id."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/bin/opencode")

        conn = _make_mock_conn(session_id="new-session-1")
        proc = AsyncMock()
        mock_spawn.return_value = _async_context_manager(lambda *a, **k: (conn, proc))

        executor = ACPExecutor()
        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Initial research",
            output_dir="phase1/opencode",
        )

        assert result.metadata["session_id"] == "new-session-1"
        conn.new_session.assert_awaited_once()
        conn.prompt.assert_awaited_once()

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_session_id_passed_through(
        self, mock_spawn, mock_resolve, mock_load, sandbox, agent_config,
    ):
        """When session_id is passed, it appears in the output metadata."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/bin/opencode")

        conn = _make_mock_conn(session_id="reused-session")
        proc = AsyncMock()
        mock_spawn.return_value = _async_context_manager(lambda *a, **k: (conn, proc))

        executor = ACPExecutor()
        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Refinement prompt",
            output_dir="phase2/opencode",
            session_id="reused-session",
        )

        assert result.metadata["session_id"] == "reused-session"

    @patch("ivory_tower.executor.acp_exec.load_agent")
    @patch("ivory_tower.executor.acp_exec.resolve_agent_binary")
    @patch("ivory_tower.executor.acp_exec.spawn_agent_process")
    def test_stop_reason_in_metadata(
        self, mock_spawn, mock_resolve, mock_load, sandbox, agent_config,
    ):
        """Stop reason from PromptResponse is captured in metadata."""
        mock_load.return_value = agent_config
        mock_resolve.return_value = Path("/usr/bin/opencode")

        conn = _make_mock_conn()
        conn.prompt = AsyncMock(return_value=MagicMock(stop_reason="max_tokens"))
        proc = AsyncMock()
        mock_spawn.return_value = _async_context_manager(lambda *a, **k: (conn, proc))

        executor = ACPExecutor()
        result = executor.run(
            sandbox=sandbox,
            agent_name="opencode",
            prompt="Long research",
            output_dir="phase1/opencode",
        )

        assert result.metadata["stop_reason"] == "max_tokens"


class TestSessionCleanup:
    """Tests for session cleanup."""

    def test_close_session_removes_entry(self):
        """close_session removes the session from internal state."""
        executor = ACPExecutor()
        # Manually add a session to simulate state
        executor._sessions["test-session"] = "some-data"
        executor.close_session("test-session")
        assert "test-session" not in executor._sessions

    def test_close_nonexistent_session_is_noop(self):
        """Closing a non-existent session doesn't raise."""
        executor = ACPExecutor()
        executor.close_session("no-such-session")  # Should not raise
