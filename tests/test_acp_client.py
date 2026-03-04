"""Tests for the ACP client with sandbox routing."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from ivory_tower.acp_client import (
    SandboxACPClient,
    PathTraversalError,
    PermissionDeniedError,
)


def _run(coro):
    """Run an async ACP client method in sync tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path):
    """Create a mock sandbox with a real workspace directory."""
    sb = MagicMock()
    sb.workspace_dir = tmp_path / "workspace"
    sb.workspace_dir.mkdir()
    sb.agent_name = "test-agent"

    # Wire up read_file / write_file to actually hit the filesystem
    def _read_file(path: str) -> str:
        full = sb.workspace_dir / path
        return full.read_text()

    def _write_file(path: str, content: str | bytes) -> None:
        full = sb.workspace_dir / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            full.write_bytes(content)
        else:
            full.write_text(content)

    def _file_exists(path: str) -> bool:
        return (sb.workspace_dir / path).exists()

    sb.read_file.side_effect = _read_file
    sb.write_file.side_effect = _write_file
    sb.file_exists.side_effect = _file_exists
    return sb


@pytest.fixture
def client(sandbox):
    """Default client with auto-approve permissions."""
    return SandboxACPClient(
        sandbox=sandbox,
        isolation_mode="full",
        permissions="auto-approve",
    )


# ---------------------------------------------------------------------------
# Text accumulation from session updates
# ---------------------------------------------------------------------------


class TestTextAccumulation:
    """Verify that session update text chunks are accumulated."""

    def _text_chunk(self, text: str):
        """Helper: create an AgentMessageChunk with text content."""
        from acp.interfaces import AgentMessageChunk, TextContentBlock

        return AgentMessageChunk(
            session_update="agent_message_chunk",
            content=TextContentBlock(type="text", text=text),
        )

    def test_accumulate_text_chunk(self, client):
        """Text content from AgentMessageChunk is accumulated."""
        _run(client.session_update(session_id="s1", update=self._text_chunk("Hello ")))
        assert client.accumulated_text == ["Hello "]

    def test_accumulate_multiple_chunks(self, client):
        """Multiple chunks are accumulated in order."""
        for text in ["Hello ", "world", "!"]:
            _run(client.session_update(session_id="s1", update=self._text_chunk(text)))
        assert client.accumulated_text == ["Hello ", "world", "!"]
        assert client.get_full_text() == "Hello world!"

    def test_non_text_content_ignored(self, client):
        """Non-text content blocks don't accumulate text."""
        from acp.interfaces import AgentMessageChunk, ImageContentBlock

        chunk = AgentMessageChunk(
            session_update="agent_message_chunk",
            content=ImageContentBlock(type="image", data="base64data", mime_type="image/png"),
        )
        _run(client.session_update(session_id="s1", update=chunk))
        assert client.accumulated_text == []

    def test_non_message_updates_ignored(self, client):
        """Non-AgentMessageChunk updates don't accumulate."""
        from acp.interfaces import ToolCallStart

        update = ToolCallStart(
            session_update="tool_call",
            tool_call_id="tc1",
            title="readTextFile",
        )
        _run(client.session_update(session_id="s1", update=update))
        assert client.accumulated_text == []

    def test_streaming_callback_called(self, sandbox):
        """on_chunk callback is invoked for each text chunk."""
        chunks_received = []

        def on_chunk(agent: str, text: str) -> None:
            chunks_received.append((agent, text))

        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="full",
            permissions="auto-approve",
            on_chunk=on_chunk,
        )

        _run(client.session_update(session_id="s1", update=self._text_chunk("Hello")))
        assert chunks_received == [("test-agent", "Hello")]

    def test_reset_text(self, client):
        """reset_text() clears accumulated text."""
        _run(client.session_update(session_id="s1", update=self._text_chunk("Hello")))
        client.reset_text()
        assert client.accumulated_text == []
        assert client.get_full_text() == ""


# ---------------------------------------------------------------------------
# readTextFile routing through sandbox
# ---------------------------------------------------------------------------


class TestReadTextFile:
    """Verify readTextFile routes through sandbox with path safety."""

    def test_read_file_in_workspace(self, client, sandbox):
        """Reading a file inside the workspace succeeds."""
        (sandbox.workspace_dir / "notes.md").write_text("my notes")
        result = _run(client.read_text_file(path="notes.md", session_id="s1"))
        assert result.content == "my notes"

    def test_read_nested_file(self, client, sandbox):
        """Reading a nested path inside workspace succeeds."""
        sub = sandbox.workspace_dir / "sub" / "dir"
        sub.mkdir(parents=True)
        (sub / "deep.txt").write_text("deep content")
        result = _run(client.read_text_file(path="sub/dir/deep.txt", session_id="s1"))
        assert result.content == "deep content"

    def test_path_traversal_rejected(self, client):
        """Paths with .. that escape workspace are rejected."""
        with pytest.raises(PathTraversalError):
            _run(client.read_text_file(path="../../../etc/passwd", session_id="s1"))

    def test_absolute_path_outside_workspace_rejected(self, client):
        """Absolute paths outside workspace are rejected."""
        with pytest.raises(PathTraversalError):
            _run(client.read_text_file(path="/etc/passwd", session_id="s1"))

    def test_absolute_path_inside_workspace_ok(self, client, sandbox):
        """Absolute paths inside the workspace are allowed."""
        (sandbox.workspace_dir / "ok.txt").write_text("allowed")
        abs_path = str(sandbox.workspace_dir / "ok.txt")
        result = _run(client.read_text_file(path=abs_path, session_id="s1"))
        assert result.content == "allowed"


# ---------------------------------------------------------------------------
# writeTextFile routing through sandbox
# ---------------------------------------------------------------------------


class TestWriteTextFile:
    """Verify writeTextFile routes through sandbox with path safety."""

    def test_write_file_in_workspace(self, client, sandbox):
        """Writing a file inside the workspace succeeds."""
        _run(client.write_text_file(
            path="output.md",
            content="report text",
            session_id="s1",
        ))
        sandbox.write_file.assert_called_once_with("output.md", "report text")

    def test_write_nested_file(self, client, sandbox):
        """Writing a nested path creates intermediate dirs."""
        _run(client.write_text_file(
            path="reports/final.md",
            content="final report",
            session_id="s1",
        ))
        sandbox.write_file.assert_called_once_with("reports/final.md", "final report")

    def test_write_path_traversal_rejected(self, client):
        """Path traversal on writes is rejected."""
        with pytest.raises(PathTraversalError):
            _run(client.write_text_file(
                path="../../evil.sh",
                content="malicious",
                session_id="s1",
            ))

    def test_write_tracks_files(self, client, sandbox):
        """Written file paths are tracked."""
        _run(client.write_text_file(
            path="a.md",
            content="aaa",
            session_id="s1",
        ))
        _run(client.write_text_file(
            path="b.md",
            content="bbb",
            session_id="s1",
        ))
        assert client.written_files == ["a.md", "b.md"]


# ---------------------------------------------------------------------------
# createTerminal routing through sandbox
# ---------------------------------------------------------------------------


class TestCreateTerminal:
    """Verify createTerminal routes through sandbox.execute()."""

    def test_create_terminal_routes_to_sandbox(self, client, sandbox):
        """Terminal creation routes through sandbox.execute()."""
        sandbox.execute.return_value = MagicMock(
            exit_code=0, stdout="output", stderr=""
        )
        result = _run(client.create_terminal(
            command="python",
            session_id="s1",
            args=["-c", "print('hi')"],
        ))
        assert result.terminal_id is not None
        sandbox.execute.assert_called_once()
        # Verify the command list
        call_args = sandbox.execute.call_args
        assert call_args[0][0] == ["python", "-c", "print('hi')"]


# ---------------------------------------------------------------------------
# Permission policies
# ---------------------------------------------------------------------------


class TestPermissionPolicies:
    """Verify permission request handling per policy."""

    def test_auto_approve(self, sandbox):
        """auto-approve policy approves all permissions."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="full",
            permissions="auto-approve",
        )
        from acp.interfaces import PermissionOption, ToolCallUpdate

        result = _run(client.request_permission(
            options=[
                PermissionOption(option_id="yes", kind="allow_once", name="Allow"),
            ],
            session_id="s1",
            tool_call=ToolCallUpdate(tool_call_id="tc1"),
        ))
        assert result.outcome.option_id == "yes"
        assert result.outcome.outcome == "selected"

    def test_reads_only_approves_reads(self, sandbox):
        """reads-only policy approves read permissions."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="full",
            permissions="reads-only",
        )
        from acp.interfaces import PermissionOption, ToolCallUpdate

        result = _run(client.request_permission(
            options=[
                PermissionOption(option_id="yes", kind="allow_once", name="Read file"),
            ],
            session_id="s1",
            tool_call=ToolCallUpdate(
                tool_call_id="tc1",
                title="readTextFile",
            ),
        ))
        assert result.outcome.option_id == "yes"

    def test_reject_all(self, sandbox):
        """reject-all policy rejects all permissions."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="full",
            permissions="reject-all",
        )
        from acp.interfaces import PermissionOption, ToolCallUpdate

        result = _run(client.request_permission(
            options=[
                PermissionOption(option_id="yes", kind="allow_once", name="Allow"),
            ],
            session_id="s1",
            tool_call=ToolCallUpdate(tool_call_id="tc1"),
        ))
        assert result.outcome.outcome == "cancelled"


# ---------------------------------------------------------------------------
# Isolation mode enforcement
# ---------------------------------------------------------------------------


class TestIsolationModes:
    """Verify that isolation modes restrict file access correctly."""

    def test_full_isolation_blocks_peer_reads(self, sandbox):
        """In full isolation, reading peer reports is blocked."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="full",
            permissions="auto-approve",
        )
        # Peer paths should be blocked
        with pytest.raises(PermissionDeniedError):
            _run(client.read_text_file(path="peers/codex-report.md", session_id="s1"))

    def test_read_peers_allows_peer_reads(self, sandbox):
        """In read-peers mode, reading peer reports is allowed."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="read-peers",
            permissions="auto-approve",
        )
        (sandbox.workspace_dir / "peers").mkdir()
        (sandbox.workspace_dir / "peers" / "codex-report.md").write_text("peer report")
        result = _run(client.read_text_file(path="peers/codex-report.md", session_id="s1"))
        assert result.content == "peer report"

    def test_read_blackboard_allows_reads(self, sandbox):
        """In read-blackboard mode, reading blackboard is allowed."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="read-blackboard",
            permissions="auto-approve",
        )
        (sandbox.workspace_dir / "blackboard").mkdir()
        (sandbox.workspace_dir / "blackboard" / "transcript.md").write_text("bb content")
        result = _run(client.read_text_file(path="blackboard/transcript.md", session_id="s1"))
        assert result.content == "bb content"

    def test_read_blackboard_blocks_writes(self, sandbox):
        """In read-blackboard mode, writing to blackboard is blocked."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="read-blackboard",
            permissions="auto-approve",
        )
        with pytest.raises(PermissionDeniedError):
            _run(client.write_text_file(
                path="blackboard/transcript.md",
                content="overwrite",
                session_id="s1",
            ))

    def test_none_isolation_allows_everything(self, sandbox):
        """No isolation allows all reads and writes."""
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="none",
            permissions="auto-approve",
        )
        (sandbox.workspace_dir / "anything.txt").write_text("free")
        result = _run(client.read_text_file(path="anything.txt", session_id="s1"))
        assert result.content == "free"
