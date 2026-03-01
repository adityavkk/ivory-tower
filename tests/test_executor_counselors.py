"""Tests for CounselorsExecutor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.executor import CounselorsExecutor, get_executor
from ivory_tower.executor.counselors_exec import _find_report
from ivory_tower.executor.types import AgentExecutor, AgentOutput
from ivory_tower.sandbox.types import ExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox(**overrides) -> MagicMock:
    """Return a MagicMock sandbox with sensible defaults."""
    sb = MagicMock()
    sb.execute.return_value = ExecutionResult(
        exit_code=0, stdout="", stderr="", duration_seconds=1.5,
    )
    sb.list_files.return_value = ["agent-report.md"]
    sb.read_file.return_value = "# Report\nDone."
    for k, v in overrides.items():
        setattr(sb, k, v)
    return sb


RESOLVE_PATCH = "ivory_tower.executor.counselors_exec.resolve_counselors_cmd"


# ---------------------------------------------------------------------------
# CounselorsExecutor basic attributes
# ---------------------------------------------------------------------------


class TestCounselorsExecutorAttributes:
    def test_name(self):
        assert CounselorsExecutor().name == "counselors"

    def test_conforms_to_protocol(self):
        assert isinstance(CounselorsExecutor(), AgentExecutor)


# ---------------------------------------------------------------------------
# CounselorsExecutor.run()
# ---------------------------------------------------------------------------


class TestCounselorsExecutorRun:
    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_writes_prompt_to_sandbox(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(sb, "researcher", "Do research", "output")
        sb.write_file.assert_any_call("prompt.md", "Do research")

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_calls_sandbox_execute(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(sb, "researcher", "Do research", "output")
        sb.execute.assert_called_once()

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_command_includes_prompt_flag(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(sb, "researcher", "prompt text", "output")
        cmd = sb.execute.call_args[0][0]
        assert "-f" in cmd
        idx = cmd.index("-f")
        assert cmd[idx + 1] == "prompt.md"

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_command_includes_agent_name_as_tools(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(sb, "researcher", "prompt", "output")
        cmd = sb.execute.call_args[0][0]
        assert "--tools" in cmd
        idx = cmd.index("--tools")
        assert cmd[idx + 1] == "researcher"

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_command_includes_model_as_tools_when_specified(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(
            sb, "researcher", "prompt", "output", model="gpt-4o",
        )
        cmd = sb.execute.call_args[0][0]
        idx = cmd.index("--tools")
        assert cmd[idx + 1] == "gpt-4o"

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_command_includes_output_dir(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(sb, "researcher", "prompt", "my_output")
        cmd = sb.execute.call_args[0][0]
        assert "-o" in cmd
        idx = cmd.index("-o")
        assert cmd[idx + 1] == "my_output/"

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_verbose_sets_env_var(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(
            sb, "researcher", "prompt", "output", verbose=True,
        )
        call_kwargs = sb.execute.call_args
        env = call_kwargs[1].get("env") if call_kwargs[1] else call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None
        # Check the keyword arg
        assert sb.execute.call_args.kwargs.get("env") == {"COUNSELORS_VERBOSE": "1"} or \
               sb.execute.call_args[1].get("env") == {"COUNSELORS_VERBOSE": "1"}

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_verbose_false_passes_no_env(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(
            sb, "researcher", "prompt", "output", verbose=False,
        )
        assert sb.execute.call_args[1].get("env") is None

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_returns_agent_output(self, _resolve):
        sb = _make_sandbox()
        result = CounselorsExecutor().run(sb, "researcher", "prompt", "output")
        assert isinstance(result, AgentOutput)
        assert result.raw_output == "# Report\nDone."
        assert result.duration_seconds == 1.5

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_reads_report_from_sandbox(self, _resolve):
        sb = _make_sandbox()
        CounselorsExecutor().run(sb, "researcher", "prompt", "output")
        sb.read_file.assert_called_once_with("output/agent-report.md")

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_report_path_in_output(self, _resolve):
        sb = _make_sandbox()
        result = CounselorsExecutor().run(sb, "researcher", "prompt", "output")
        assert result.report_path == "output/agent-report.md"

    @patch(RESOLVE_PATCH, return_value=["counselors"])
    def test_metadata_includes_exit_code(self, _resolve):
        sb = _make_sandbox()
        result = CounselorsExecutor().run(sb, "researcher", "prompt", "output")
        assert result.metadata["exit_code"] == 0
        assert result.metadata["stderr"] == ""


# ---------------------------------------------------------------------------
# _find_report()
# ---------------------------------------------------------------------------


class TestFindReport:
    def test_finds_md_files(self):
        sb = MagicMock()
        sb.list_files.return_value = ["data.json", "report.md"]
        path = _find_report(sb, "out", "agent")
        assert path == "out/report.md"

    def test_falls_back_to_any_file(self):
        sb = MagicMock()
        sb.list_files.return_value = ["output.txt"]
        path = _find_report(sb, "out", "agent")
        assert path == "out/output.txt"

    def test_returns_none_when_empty(self):
        sb = MagicMock()
        sb.list_files.return_value = []
        assert _find_report(sb, "out", "agent") is None

    def test_returns_none_on_file_not_found(self):
        sb = MagicMock()
        sb.list_files.side_effect = FileNotFoundError
        assert _find_report(sb, "out", "agent") is None

    def test_returns_none_on_os_error(self):
        sb = MagicMock()
        sb.list_files.side_effect = OSError
        assert _find_report(sb, "out", "agent") is None


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestCounselorsRegistry:
    def test_get_executor_returns_counselors(self):
        executor = get_executor("counselors")
        assert isinstance(executor, CounselorsExecutor)
