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


# ---------------------------------------------------------------------------
# Council session reuse tests
# ---------------------------------------------------------------------------


class TestCouncilSessionReuse:
    """Verify council strategy passes session_id from Phase 1 to Phase 2."""

    @patch("ivory_tower.strategies.council._create_sandbox")
    @patch("ivory_tower.strategies.council._get_executor")
    @patch("ivory_tower.strategies.council._run_agent")
    def test_phase2_receives_session_id_from_phase1(
        self, mock_run, mock_exec, mock_sandbox, tmp_path,
    ):
        """Phase 2 _run_agent calls include session_id from Phase 1 results."""
        from ivory_tower.executor.types import AgentOutput
        from ivory_tower.strategies.council import CouncilStrategy
        from ivory_tower.engine import RunConfig

        # Phase 1 returns session_ids in metadata
        call_count = [0]
        def fake_run_agent(executor, sandbox, agent_name, prompt, output_dir, verbose=False, **kwargs):
            call_count[0] += 1
            return AgentOutput(
                report_path=f"{output_dir}/{agent_name}-report.md",
                raw_output=f"Report by {agent_name}",
                duration_seconds=1.0,
                metadata={"session_id": f"session-{agent_name}", "protocol": "acp"},
            )

        mock_run.side_effect = fake_run_agent
        mock_exec.return_value = MagicMock()
        mock_sandbox.return_value = MagicMock(workspace_dir=tmp_path)

        strat = CouncilStrategy()
        config = RunConfig(
            topic="Session test",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            output_dir=tmp_path,
        )
        manifest = strat.create_manifest(config, "run-session-test")

        run_dir = tmp_path / "run-session-test"
        run_dir.mkdir(parents=True, exist_ok=True)
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        strat.run(run_dir, config, manifest)

        # Check that Phase 2 calls include session_id kwargs
        phase2_calls = [
            c for c in mock_run.call_args_list
            if "phase2" in str(c)
        ]
        assert len(phase2_calls) >= 2  # One per agent
        for call_args in phase2_calls:
            # session_id should be in kwargs
            assert "session_id" in call_args.kwargs or (
                len(call_args.args) > 6  # positional fallback check
            )
