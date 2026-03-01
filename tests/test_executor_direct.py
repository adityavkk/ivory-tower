"""Tests for DirectExecutor."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.executor import DirectExecutor, get_executor
from ivory_tower.executor.types import AgentExecutor, AgentOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox() -> MagicMock:
    """Return a MagicMock sandbox."""
    return MagicMock()


def _fake_response(content: str = "Generated report.") -> SimpleNamespace:
    """Build a fake litellm response object."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], usage={"total_tokens": 42})


def _make_mock_litellm(response=None):
    """Create a mock litellm module with a completion function."""
    mock = MagicMock()
    mock.completion.return_value = response or _fake_response()
    return mock


@pytest.fixture()
def mock_litellm():
    """Inject a mock litellm into sys.modules for the duration of a test."""
    mock = _make_mock_litellm()
    with patch.dict(sys.modules, {"litellm": mock}):
        yield mock


# ---------------------------------------------------------------------------
# DirectExecutor basic attributes
# ---------------------------------------------------------------------------


class TestDirectExecutorAttributes:
    def test_name(self):
        assert DirectExecutor().name == "direct"

    def test_conforms_to_protocol(self):
        assert isinstance(DirectExecutor(), AgentExecutor)


# ---------------------------------------------------------------------------
# DirectExecutor.run()
# ---------------------------------------------------------------------------


class TestDirectExecutorRun:
    def test_calls_litellm_completion(self, mock_litellm):
        sb = _make_sandbox()
        DirectExecutor().run(sb, "gpt-4o", "Do stuff", "output")
        mock_litellm.completion.assert_called_once()

    def test_uses_model_param(self, mock_litellm):
        sb = _make_sandbox()
        DirectExecutor().run(
            sb, "agent-name", "prompt", "output", model="claude-3-opus",
        )
        call_kwargs = mock_litellm.completion.call_args[1]
        assert call_kwargs["model"] == "claude-3-opus"

    def test_uses_agent_name_when_model_none(self, mock_litellm):
        sb = _make_sandbox()
        DirectExecutor().run(sb, "gpt-4o", "prompt", "output", model=None)
        call_kwargs = mock_litellm.completion.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"

    def test_includes_system_prompt(self, mock_litellm):
        sb = _make_sandbox()
        DirectExecutor().run(
            sb, "gpt-4o", "user prompt", "output",
            system_prompt="You are helpful.",
        )
        messages = mock_litellm.completion.call_args[1]["messages"]
        assert messages[0] == {"role": "system", "content": "You are helpful."}
        assert messages[1] == {"role": "user", "content": "user prompt"}

    def test_no_system_prompt_when_none(self, mock_litellm):
        sb = _make_sandbox()
        DirectExecutor().run(sb, "gpt-4o", "user prompt", "output")
        messages = mock_litellm.completion.call_args[1]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_writes_output_to_sandbox(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("Hello world")
        sb = _make_sandbox()
        DirectExecutor().run(sb, "gpt-4o", "prompt", "output")
        sb.write_file.assert_called_once_with("output/gpt-4o-report.md", "Hello world")

    def test_returns_agent_output(self, mock_litellm):
        mock_litellm.completion.return_value = _fake_response("Report content")
        sb = _make_sandbox()
        result = DirectExecutor().run(sb, "gpt-4o", "prompt", "output")
        assert isinstance(result, AgentOutput)
        assert result.report_path == "output/gpt-4o-report.md"
        assert result.raw_output == "Report content"
        assert result.duration_seconds >= 0

    def test_metadata_includes_model(self, mock_litellm):
        sb = _make_sandbox()
        result = DirectExecutor().run(sb, "gpt-4o", "prompt", "output")
        assert result.metadata["model"] == "gpt-4o"

    def test_metadata_includes_usage(self, mock_litellm):
        resp = _fake_response()
        mock_litellm.completion.return_value = resp
        sb = _make_sandbox()
        result = DirectExecutor().run(sb, "gpt-4o", "prompt", "output")
        assert result.metadata["usage"] == {"total_tokens": 42}


# ---------------------------------------------------------------------------
# Import error handling
# ---------------------------------------------------------------------------


class TestDirectExecutorImportError:
    def test_raises_runtime_error_when_litellm_missing(self):
        sb = _make_sandbox()
        with patch.dict(sys.modules, {"litellm": None}):
            with pytest.raises(RuntimeError, match="litellm"):
                DirectExecutor().run(sb, "gpt-4o", "prompt", "output")


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestDirectRegistry:
    def test_get_executor_returns_direct(self):
        executor = get_executor("direct")
        assert isinstance(executor, DirectExecutor)

    def test_get_executor_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown executor 'unknown'"):
            get_executor("unknown")
