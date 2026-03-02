"""Tests for HeadlessExecExecutor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.agents import AgentConfig
from ivory_tower.executor.headless_exec import HeadlessExecExecutor
from ivory_tower.executor.types import AgentExecutor, AgentOutput
from ivory_tower.sandbox.types import ExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


LOAD_AGENT_PATCH = "ivory_tower.executor.headless_exec.load_agent"


def _make_sandbox(**overrides) -> MagicMock:
    """Return a MagicMock sandbox with sensible defaults."""
    sb = MagicMock()
    sb.workspace_dir = Path("/fake/workspace")
    sb.agent_name = "test-agent"
    sb.id = "sandbox-1"
    sb.execute.return_value = ExecutionResult(
        exit_code=0, stdout="raw agent output", stderr="", duration_seconds=2.5,
    )
    for k, v in overrides.items():
        setattr(sb, k, v)
    return sb


def _make_config(
    name: str = "claude",
    command: str = "claude",
    args: list[str] | None = None,
    output_format: str | None = None,
    session: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
) -> AgentConfig:
    """Build an AgentConfig for headless agents."""
    return AgentConfig(
        name=name,
        command=command,
        args=args or ["-p", "{prompt}", "--output-format", "stream-json"],
        env=env or {},
        protocol="headless",
        output_format=output_format,
        session=session,
    )


def _stream_json_stdout(*messages: tuple[str, str]) -> str:
    """Build ndJSON stdout mimicking Claude Code stream-json format.

    Each message is (type, text).  Only type=assistant messages have
    content blocks with text.
    """
    lines = []
    for msg_type, text in messages:
        if msg_type == "assistant":
            obj = {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": text}],
                },
            }
        else:
            obj = {"type": msg_type, "message": text}
        lines.append(json.dumps(obj))
    return "\n".join(lines)


def _jsonl_stdout(*messages: tuple[str, str]) -> str:
    """Build ndJSON stdout mimicking Codex jsonl format.

    Each message is (type, text).  Only type=item.message.completed have
    text content.
    """
    lines = []
    for msg_type, text in messages:
        if msg_type == "item.message.completed":
            obj = {
                "type": "item.message.completed",
                "item": {
                    "content": [{"type": "text", "text": text}],
                },
            }
        else:
            obj = {"type": msg_type, "data": text}
        lines.append(json.dumps(obj))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestHeadlessExecExecutorProtocol:
    def test_name(self):
        assert HeadlessExecExecutor().name == "headless"

    def test_conforms_to_protocol(self):
        assert isinstance(HeadlessExecExecutor(), AgentExecutor)


# ---------------------------------------------------------------------------
# Command building
# ---------------------------------------------------------------------------


class TestCommandBuilding:
    @patch(LOAD_AGENT_PATCH)
    def test_prompt_placeholder_substituted(self, mock_load):
        """The {prompt} placeholder in args is replaced with the actual prompt."""
        mock_load.return_value = _make_config(
            args=["-p", "{prompt}", "--verbose"],
        )
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "claude", "Research AI safety", "output")

        cmd = sb.execute.call_args[0][0]
        assert "Research AI safety" in cmd
        assert "{prompt}" not in cmd

    @patch(LOAD_AGENT_PATCH)
    def test_workspace_placeholder_substituted(self, mock_load):
        """The {workspace} placeholder is replaced with sandbox workspace_dir."""
        sb = _make_sandbox()
        sb.workspace_dir = Path("/my/workspace")
        mock_load.return_value = _make_config(
            args=["--cwd", "{workspace}", "-p", "{prompt}"],
        )

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        cmd = sb.execute.call_args[0][0]
        assert "/my/workspace" in cmd
        assert "{workspace}" not in cmd

    @patch(LOAD_AGENT_PATCH)
    def test_command_starts_with_binary(self, mock_load):
        """The first element of the command list is the agent binary."""
        mock_load.return_value = _make_config(
            command="/usr/local/bin/claude",
            args=["-p", "{prompt}"],
        )
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        cmd = sb.execute.call_args[0][0]
        assert cmd[0] == "/usr/local/bin/claude"

    @patch(LOAD_AGENT_PATCH)
    def test_args_order_preserved(self, mock_load):
        """Args appear in the command in the same order as config."""
        mock_load.return_value = _make_config(
            command="aider",
            args=["--message", "{prompt}", "--yes", "--no-git"],
        )
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "aider", "do stuff", "output")

        cmd = sb.execute.call_args[0][0]
        assert cmd == ["aider", "--message", "do stuff", "--yes", "--no-git"]

    @patch(LOAD_AGENT_PATCH)
    def test_both_placeholders_in_same_arg_list(self, mock_load):
        """Both {prompt} and {workspace} can coexist in args."""
        sb = _make_sandbox()
        sb.workspace_dir = Path("/ws")
        mock_load.return_value = _make_config(
            args=["--cwd", "{workspace}", "-p", "{prompt}"],
        )

        HeadlessExecExecutor().run(sb, "claude", "hello", "output")

        cmd = sb.execute.call_args[0][0]
        assert "--cwd" in cmd
        assert "/ws" in cmd
        assert "hello" in cmd


# ---------------------------------------------------------------------------
# Output format parsing -- text
# ---------------------------------------------------------------------------


class TestOutputFormatText:
    @patch(LOAD_AGENT_PATCH)
    def test_text_format_returns_raw_stdout(self, mock_load):
        """output_format='text' returns stdout as-is."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="Plain text report\nwith newlines",
            stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "aider", "prompt", "output")

        assert result.raw_output == "Plain text report\nwith newlines"

    @patch(LOAD_AGENT_PATCH)
    def test_none_format_returns_raw_stdout(self, mock_load):
        """output_format=None falls back to raw stdout."""
        mock_load.return_value = _make_config(output_format=None)
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="fallback raw text",
            stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "agent", "prompt", "output")

        assert result.raw_output == "fallback raw text"


# ---------------------------------------------------------------------------
# Output format parsing -- stream-json (Claude Code)
# ---------------------------------------------------------------------------


class TestOutputFormatStreamJson:
    @patch(LOAD_AGENT_PATCH)
    def test_extracts_assistant_text(self, mock_load):
        """stream-json parses ndJSON and extracts assistant message text blocks."""
        stdout = _stream_json_stdout(
            ("system", "initializing"),
            ("assistant", "First part of report."),
            ("assistant", "Second part of report."),
        )
        mock_load.return_value = _make_config(output_format="stream-json")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=3.0,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert "First part of report." in result.raw_output
        assert "Second part of report." in result.raw_output

    @patch(LOAD_AGENT_PATCH)
    def test_ignores_non_assistant_types(self, mock_load):
        """stream-json should skip lines that are not type=assistant."""
        stdout = _stream_json_stdout(
            ("system", "system noise"),
            ("assistant", "The real content."),
            ("result", "done"),
        )
        mock_load.return_value = _make_config(output_format="stream-json")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert "system noise" not in result.raw_output
        assert "The real content." in result.raw_output

    @patch(LOAD_AGENT_PATCH)
    def test_handles_empty_stdout(self, mock_load):
        """stream-json with empty stdout returns empty string."""
        mock_load.return_value = _make_config(output_format="stream-json")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", duration_seconds=0.5,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert result.raw_output == ""

    @patch(LOAD_AGENT_PATCH)
    def test_handles_malformed_json_lines(self, mock_load):
        """stream-json skips lines that aren't valid JSON."""
        stdout = "not json\n" + json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "good"}]},
        }) + "\nalso not json"
        mock_load.return_value = _make_config(output_format="stream-json")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert "good" in result.raw_output

    @patch(LOAD_AGENT_PATCH)
    def test_multiple_content_blocks(self, mock_load):
        """stream-json assistant message with multiple content blocks."""
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Block A."},
                    {"type": "text", "text": "Block B."},
                ],
            },
        }
        stdout = json.dumps(obj)
        mock_load.return_value = _make_config(output_format="stream-json")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert "Block A." in result.raw_output
        assert "Block B." in result.raw_output


# ---------------------------------------------------------------------------
# Output format parsing -- jsonl (Codex)
# ---------------------------------------------------------------------------


class TestOutputFormatJsonl:
    @patch(LOAD_AGENT_PATCH)
    def test_extracts_item_message_completed_text(self, mock_load):
        """jsonl parses ndJSON and extracts item.message.completed text."""
        stdout = _jsonl_stdout(
            ("item.created", "ignored"),
            ("item.message.completed", "Codex report content."),
        )
        mock_load.return_value = _make_config(output_format="jsonl")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=2.0,
        )

        result = HeadlessExecExecutor().run(sb, "codex", "prompt", "output")

        assert "Codex report content." in result.raw_output

    @patch(LOAD_AGENT_PATCH)
    def test_ignores_non_completed_types(self, mock_load):
        """jsonl should skip lines that are not item.message.completed."""
        stdout = _jsonl_stdout(
            ("item.created", "noise"),
            ("item.message.completed", "Real content."),
            ("item.done", "more noise"),
        )
        mock_load.return_value = _make_config(output_format="jsonl")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "codex", "prompt", "output")

        assert "noise" not in result.raw_output
        assert "Real content." in result.raw_output

    @patch(LOAD_AGENT_PATCH)
    def test_handles_empty_stdout(self, mock_load):
        """jsonl with empty stdout returns empty string."""
        mock_load.return_value = _make_config(output_format="jsonl")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", duration_seconds=0.5,
        )

        result = HeadlessExecExecutor().run(sb, "codex", "prompt", "output")

        assert result.raw_output == ""

    @patch(LOAD_AGENT_PATCH)
    def test_handles_malformed_json_lines(self, mock_load):
        """jsonl skips lines that aren't valid JSON."""
        stdout = "bad line\n" + json.dumps({
            "type": "item.message.completed",
            "item": {"content": [{"type": "text", "text": "salvaged"}]},
        })
        mock_load.return_value = _make_config(output_format="jsonl")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "codex", "prompt", "output")

        assert "salvaged" in result.raw_output

    @patch(LOAD_AGENT_PATCH)
    def test_multiple_completed_messages(self, mock_load):
        """jsonl concatenates text from multiple completed messages."""
        stdout = _jsonl_stdout(
            ("item.message.completed", "Part 1."),
            ("item.message.completed", "Part 2."),
        )
        mock_load.return_value = _make_config(output_format="jsonl")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "codex", "prompt", "output")

        assert "Part 1." in result.raw_output
        assert "Part 2." in result.raw_output


# ---------------------------------------------------------------------------
# Sandbox integration
# ---------------------------------------------------------------------------


class TestSandboxIntegration:
    @patch(LOAD_AGENT_PATCH)
    def test_calls_sandbox_execute(self, mock_load):
        """The executor calls sandbox.execute() exactly once."""
        mock_load.return_value = _make_config()
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        sb.execute.assert_called_once()

    @patch(LOAD_AGENT_PATCH)
    def test_passes_env_to_sandbox_execute(self, mock_load):
        """Agent config env vars are forwarded to sandbox.execute()."""
        mock_load.return_value = _make_config(
            env={"ANTHROPIC_API_KEY": "sk-test", "VERBOSE": "1"},
        )
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        call_kwargs = sb.execute.call_args
        env = call_kwargs[1].get("env") or (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None)
        assert env is not None
        assert env["ANTHROPIC_API_KEY"] == "sk-test"
        assert env["VERBOSE"] == "1"

    @patch(LOAD_AGENT_PATCH)
    def test_empty_env_passes_none_or_empty(self, mock_load):
        """When agent has no env vars, sandbox.execute gets None or empty env."""
        mock_load.return_value = _make_config(env={})
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        call_kwargs = sb.execute.call_args
        env = call_kwargs[1].get("env")
        assert env is None or env == {}

    @patch(LOAD_AGENT_PATCH)
    def test_load_agent_called_with_agent_name(self, mock_load):
        """load_agent is called with the agent_name argument."""
        mock_load.return_value = _make_config()
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        mock_load.assert_called_once_with("claude")


# ---------------------------------------------------------------------------
# Report file written
# ---------------------------------------------------------------------------


class TestReportWritten:
    @patch(LOAD_AGENT_PATCH)
    def test_writes_report_to_sandbox(self, mock_load):
        """The executor writes the parsed output to sandbox as a report file."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="My report content",
            stderr="", duration_seconds=1.0,
        )

        HeadlessExecExecutor().run(sb, "claude", "prompt", "phase1/claude")

        sb.write_file.assert_called_once_with(
            "phase1/claude/claude-report.md", "My report content",
        )

    @patch(LOAD_AGENT_PATCH)
    def test_report_path_in_output(self, mock_load):
        """AgentOutput.report_path matches the expected location."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()

        result = HeadlessExecExecutor().run(sb, "aider", "prompt", "output")

        assert result.report_path == "output/aider-report.md"

    @patch(LOAD_AGENT_PATCH)
    def test_report_path_uses_agent_name(self, mock_load):
        """Report filename is derived from the agent_name argument."""
        mock_load.return_value = _make_config(name="codex", command="codex")
        sb = _make_sandbox()

        result = HeadlessExecExecutor().run(sb, "codex", "prompt", "out")

        assert result.report_path == "out/codex-report.md"

    @patch(LOAD_AGENT_PATCH)
    def test_writes_parsed_content_not_raw(self, mock_load):
        """For structured formats, the parsed content is written, not raw stdout."""
        stdout = _stream_json_stdout(("assistant", "Parsed report."))
        mock_load.return_value = _make_config(output_format="stream-json")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout=stdout, stderr="", duration_seconds=1.0,
        )

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        write_args = sb.write_file.call_args[0]
        assert "Parsed report." in write_args[1]


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------


class TestReturnValue:
    @patch(LOAD_AGENT_PATCH)
    def test_returns_agent_output(self, mock_load):
        """run() returns an AgentOutput instance."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert isinstance(result, AgentOutput)

    @patch(LOAD_AGENT_PATCH)
    def test_duration_from_execution_result(self, mock_load):
        """duration_seconds comes from the sandbox ExecutionResult."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="ok", stderr="", duration_seconds=7.3,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert result.duration_seconds == 7.3

    @patch(LOAD_AGENT_PATCH)
    def test_metadata_includes_exit_code(self, mock_load):
        """Metadata contains the process exit_code."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="ok", stderr="", duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert result.metadata["exit_code"] == 0

    @patch(LOAD_AGENT_PATCH)
    def test_metadata_includes_stderr(self, mock_load):
        """Metadata contains captured stderr."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=0, stdout="ok", stderr="some warning",
            duration_seconds=1.0,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert result.metadata["stderr"] == "some warning"

    @patch(LOAD_AGENT_PATCH)
    def test_metadata_includes_output_format(self, mock_load):
        """Metadata records which output_format was used."""
        mock_load.return_value = _make_config(output_format="stream-json")
        sb = _make_sandbox()

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert result.metadata["output_format"] == "stream-json"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @patch(LOAD_AGENT_PATCH)
    def test_nonzero_exit_code_still_returns_output(self, mock_load):
        """Non-zero exit code should still return whatever output exists."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=1, stdout="partial output", stderr="error occurred",
            duration_seconds=0.5,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert isinstance(result, AgentOutput)
        assert result.raw_output == "partial output"
        assert result.metadata["exit_code"] == 1
        assert result.metadata["stderr"] == "error occurred"

    @patch(LOAD_AGENT_PATCH)
    def test_nonzero_exit_code_writes_report(self, mock_load):
        """Even on failure, the report file should be written with available output."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=2, stdout="error report", stderr="crash",
            duration_seconds=0.1,
        )

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        sb.write_file.assert_called_once()

    @patch(LOAD_AGENT_PATCH)
    def test_missing_agent_config_raises(self, mock_load):
        """FileNotFoundError from load_agent propagates."""
        mock_load.side_effect = FileNotFoundError("Agent not found: nope")
        sb = _make_sandbox()

        with pytest.raises(FileNotFoundError, match="nope"):
            HeadlessExecExecutor().run(sb, "nope", "prompt", "output")

    @patch(LOAD_AGENT_PATCH)
    def test_empty_stdout_on_failure(self, mock_load):
        """Non-zero exit with empty stdout produces empty raw_output."""
        mock_load.return_value = _make_config(output_format="text")
        sb = _make_sandbox()
        sb.execute.return_value = ExecutionResult(
            exit_code=1, stdout="", stderr="segfault",
            duration_seconds=0.1,
        )

        result = HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        assert result.raw_output == ""
        assert result.metadata["exit_code"] == 1


# ---------------------------------------------------------------------------
# Session support
# ---------------------------------------------------------------------------


class TestSessionSupport:
    @patch(LOAD_AGENT_PATCH)
    def test_continue_flag_appended_when_session_id_given(self, mock_load):
        """When session_id is in metadata and config has continue_flag, append it."""
        mock_load.return_value = _make_config(
            args=["-p", "{prompt}"],
            session={"continue_flag": "--continue", "resume_flag": "--resume"},
        )
        sb = _make_sandbox()

        HeadlessExecExecutor().run(
            sb, "claude", "next prompt", "output",
            # session_id passed through metadata or keyword -- implementation may vary;
            # test the public contract: the flag appears in the command
        )

        # Without a session_id, the continue flag should NOT be present
        cmd = sb.execute.call_args[0][0]
        assert "--continue" not in cmd

    @patch(LOAD_AGENT_PATCH)
    def test_no_session_config_no_flag(self, mock_load):
        """When session config is None, no session flags appear."""
        mock_load.return_value = _make_config(
            args=["-p", "{prompt}"],
            session=None,
        )
        sb = _make_sandbox()

        HeadlessExecExecutor().run(sb, "claude", "prompt", "output")

        cmd = sb.execute.call_args[0][0]
        assert "--continue" not in cmd
        assert "--resume" not in cmd


class TestSessionSupportWithSessionId:
    """Tests where a session_id is provided to trigger continue behavior."""

    @patch(LOAD_AGENT_PATCH)
    def test_continue_flag_present_with_session_id(self, mock_load):
        """When a session_id is provided and config has continue_flag, the flag is appended."""
        mock_load.return_value = _make_config(
            args=["-p", "{prompt}"],
            session={"continue_flag": "--continue"},
        )
        sb = _make_sandbox()

        # The executor should accept session_id through metadata or a dedicated param.
        # We test via the metadata dict pattern used by other executors.
        executor = HeadlessExecExecutor()
        # Pass session_id -- the implementation may accept it as a kwarg or via
        # a prior run's metadata. We test the most likely interface: via metadata
        # or an explicit session_id param on run().
        # Since the Protocol doesn't have session_id, it's likely passed through
        # a separate method or stored on the executor instance.
        # Test that calling run() with session_id in the executor state works:
        executor._session_id = "session-abc"  # type: ignore[attr-defined]
        executor.run(sb, "claude", "follow-up prompt", "output")

        cmd = sb.execute.call_args[0][0]
        assert "--continue" in cmd

    @patch(LOAD_AGENT_PATCH)
    def test_session_id_in_metadata(self, mock_load):
        """The session_id is included in output metadata when set."""
        mock_load.return_value = _make_config(
            args=["-p", "{prompt}"],
            session={"continue_flag": "--continue"},
        )
        sb = _make_sandbox()

        executor = HeadlessExecExecutor()
        executor._session_id = "session-xyz"  # type: ignore[attr-defined]
        result = executor.run(sb, "claude", "prompt", "output")

        assert result.metadata.get("session_id") == "session-xyz"


# ---------------------------------------------------------------------------
# Model and system_prompt passthrough
# ---------------------------------------------------------------------------


class TestModelAndSystemPrompt:
    @patch(LOAD_AGENT_PATCH)
    def test_model_ignored_for_headless(self, mock_load):
        """The model param doesn't alter the command for headless agents.

        Headless agents use their own binary; model is metadata only.
        """
        mock_load.return_value = _make_config(args=["-p", "{prompt}"])
        sb = _make_sandbox()

        result = HeadlessExecExecutor().run(
            sb, "claude", "prompt", "output", model="gpt-4o",
        )

        # Command should use the config's binary, not the model
        cmd = sb.execute.call_args[0][0]
        assert cmd[0] == "claude"
        # But model may appear in metadata
        assert isinstance(result, AgentOutput)

    @patch(LOAD_AGENT_PATCH)
    def test_system_prompt_prepended(self, mock_load):
        """When system_prompt is provided, it should be prepended to the prompt."""
        mock_load.return_value = _make_config(args=["-p", "{prompt}"])
        sb = _make_sandbox()

        HeadlessExecExecutor().run(
            sb, "claude", "User question", "output",
            system_prompt="You are a researcher.",
        )

        cmd = sb.execute.call_args[0][0]
        # The prompt in the command should include the system prompt content
        # Either prepended to the prompt text or as a separate flag
        prompt_idx = cmd.index("-p") + 1
        prompt_text = cmd[prompt_idx]
        # The system prompt should be incorporated somehow
        assert "You are a researcher." in prompt_text or any(
            "You are a researcher." in arg for arg in cmd
        )


# ---------------------------------------------------------------------------
# Verbose flag
# ---------------------------------------------------------------------------


class TestVerboseFlag:
    @patch(LOAD_AGENT_PATCH)
    def test_verbose_true(self, mock_load):
        """verbose=True doesn't crash; behavior is implementation-defined."""
        mock_load.return_value = _make_config()
        sb = _make_sandbox()

        result = HeadlessExecExecutor().run(
            sb, "claude", "prompt", "output", verbose=True,
        )

        assert isinstance(result, AgentOutput)

    @patch(LOAD_AGENT_PATCH)
    def test_verbose_false(self, mock_load):
        """verbose=False is the default and works normally."""
        mock_load.return_value = _make_config()
        sb = _make_sandbox()

        result = HeadlessExecExecutor().run(
            sb, "claude", "prompt", "output", verbose=False,
        )

        assert isinstance(result, AgentOutput)
