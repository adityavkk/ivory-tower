"""Live tests for sandbox provider lifecycle -- real filesystem, no mocks.

These tests exercise the actual sandbox backends end-to-end:
  - NullSandboxProvider
  - LocalSandboxProvider
  - FileBlackboard with local backend
  - AgentFSSandboxProvider (skipped if agentfs CLI not installed)
  - DaytonaSandboxProvider (skipped if daytona SDK not importable)

Run with: uv run pytest tests/test_sandbox_live.py -m live -v -s
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from ivory_tower.sandbox import get_provider
from ivory_tower.sandbox.blackboard import FileBlackboard
from ivory_tower.sandbox.local import (
    LocalSandbox,
    LocalSandboxProvider,
    LocalSharedVolume,
)
from ivory_tower.sandbox.null import (
    NullSandbox,
    NullSandboxProvider,
    NullSharedVolume,
)
from ivory_tower.sandbox.types import ExecutionResult, SandboxConfig

# All tests in this file require the live marker
pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# NullSandboxProvider -- end-to-end lifecycle
# ---------------------------------------------------------------------------


class TestNullSandboxProviderLive:
    """Full lifecycle: create → write → read → shared volume → destroy."""

    def test_is_available(self) -> None:
        assert NullSandboxProvider.is_available() is True

    def test_get_provider_returns_null(self) -> None:
        provider = get_provider("none")
        assert isinstance(provider, NullSandboxProvider)
        assert provider.name == "none"

    def test_create_sandbox_lifecycle(self, tmp_path: Path) -> None:
        provider = NullSandboxProvider()
        config = SandboxConfig(backend="none")

        sandbox = provider.create_sandbox(
            agent_name="test-agent",
            run_id="live-null-001",
            run_dir=tmp_path,
            config=config,
        )

        # Sandbox points to run_dir directly (null = no isolation)
        assert sandbox.workspace_dir == tmp_path
        assert sandbox.agent_name == "test-agent"
        assert sandbox.id == "live-null-001-test-agent"

        # Write and read a file
        sandbox.write_file("report.md", "# Test Report\n\nThis works.")
        assert sandbox.read_file("report.md") == "# Test Report\n\nThis works."
        assert (tmp_path / "report.md").exists()

        # Write nested file
        sandbox.write_file("output/deep/nested.txt", "deep content")
        assert sandbox.read_file("output/deep/nested.txt") == "deep content"

        # File exists
        assert sandbox.file_exists("report.md") is True
        assert sandbox.file_exists("nonexistent.txt") is False

        # List files
        files = sandbox.list_files()
        assert "report.md" in files
        assert any("nested.txt" in f for f in files)

        # Execute a real command
        result = sandbox.execute(["echo", "hello from null sandbox"])
        assert result.exit_code == 0
        assert "hello from null sandbox" in result.stdout
        assert result.duration_seconds >= 0

        # Execute with env
        result = sandbox.execute(
            [sys.executable, "-c", "import os; print(os.environ['LIVE_TEST'])"],
            env={"LIVE_TEST": "sandbox-value"},
        )
        assert result.exit_code == 0
        assert "sandbox-value" in result.stdout

        # Snapshot and diff return None for null backend
        assert sandbox.snapshot("test") is None
        assert sandbox.diff() is None

        # Destroy is a no-op
        sandbox.destroy()
        assert (tmp_path / "report.md").exists()  # Files preserved

    def test_shared_volume_lifecycle(self, tmp_path: Path) -> None:
        provider = NullSandboxProvider()

        vol = provider.create_shared_volume(
            name="shared-data",
            run_id="live-null-002",
            run_dir=tmp_path,
        )

        # Volume directory created
        assert vol.path.exists()
        assert vol.path == tmp_path / "volumes" / "shared-data"
        assert vol.id == "live-null-002-shared-data"

        # Write and read
        vol.write_file("notes.txt", "shared notes")
        assert vol.read_file("notes.txt") == "shared notes"

        # Append
        vol.append_file("log.txt", "entry 1\n")
        vol.append_file("log.txt", "entry 2\n")
        content = vol.read_file("log.txt")
        assert "entry 1" in content
        assert "entry 2" in content

        # List files
        files = vol.list_files()
        assert "notes.txt" in files
        assert "log.txt" in files

    def test_destroy_all_is_noop(self, tmp_path: Path) -> None:
        provider = NullSandboxProvider()
        # Should not raise
        provider.destroy_all("some-run-id")

    def test_multiple_sandboxes_share_run_dir(self, tmp_path: Path) -> None:
        """Null provider: all sandboxes share the same run directory."""
        provider = NullSandboxProvider()
        config = SandboxConfig(backend="none")

        sb1 = provider.create_sandbox("agent-a", "run-shared", tmp_path, config)
        sb2 = provider.create_sandbox("agent-b", "run-shared", tmp_path, config)

        # Both point to same dir (no isolation)
        assert sb1.workspace_dir == sb2.workspace_dir == tmp_path

        # Agent A writes, Agent B can read (no isolation)
        sb1.write_file("from-a.txt", "hello from A")
        assert sb2.read_file("from-a.txt") == "hello from A"


# ---------------------------------------------------------------------------
# LocalSandboxProvider -- end-to-end lifecycle
# ---------------------------------------------------------------------------


class TestLocalSandboxProviderLive:
    """Full lifecycle with real filesystem isolation."""

    def test_is_available(self) -> None:
        assert LocalSandboxProvider.is_available() is True

    def test_get_provider_returns_local(self) -> None:
        provider = get_provider("local")
        assert isinstance(provider, LocalSandboxProvider)
        assert provider.name == "local"

    def test_create_sandbox_lifecycle(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")

        sandbox = provider.create_sandbox(
            agent_name="claude",
            run_id="live-local-001",
            run_dir=tmp_path,
            config=config,
        )

        # Workspace is isolated under sandboxes/<agent>/workspace
        expected_ws = tmp_path / "sandboxes" / "claude" / "workspace"
        assert sandbox.workspace_dir == expected_ws
        assert expected_ws.exists()
        assert sandbox.agent_name == "claude"
        assert sandbox.id == "live-local-001-claude"

        # Write and read
        sandbox.write_file("report.md", "# Research Report\n\nFindings here.")
        assert sandbox.read_file("report.md") == "# Research Report\n\nFindings here."
        assert (expected_ws / "report.md").exists()

        # Write nested
        sandbox.write_file("results/data/analysis.txt", "analysis results")
        assert sandbox.read_file("results/data/analysis.txt") == "analysis results"

        # Write binary
        binary_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        sandbox.write_file("image.png", binary_data)
        assert (expected_ws / "image.png").read_bytes() == binary_data

        # File exists
        assert sandbox.file_exists("report.md") is True
        assert sandbox.file_exists("nope.txt") is False
        assert sandbox.file_exists("results/data/analysis.txt") is True

        # List files
        files = sandbox.list_files()
        assert "report.md" in files
        assert "image.png" in files
        assert any("analysis.txt" in f for f in files)
        assert len(files) >= 3

        # List files in subdirectory
        sub_files = sandbox.list_files("results")
        assert any("analysis.txt" in f for f in sub_files)

        # List nonexistent directory
        assert sandbox.list_files("no-such-dir") == []

    def test_copy_in_and_copy_out(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")

        sandbox = provider.create_sandbox(
            agent_name="copier",
            run_id="live-local-copy",
            run_dir=tmp_path,
            config=config,
        )

        # Create an external file to copy in
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        src_file = external_dir / "input-data.txt"
        src_file.write_text("external input data for the agent")

        # copy_in: external → sandbox
        sandbox.copy_in(src_file, "inputs/data.txt")
        assert sandbox.read_file("inputs/data.txt") == "external input data for the agent"

        # Write a result in the sandbox
        sandbox.write_file("outputs/result.md", "# Agent Result\n\nDone.")

        # copy_out: sandbox → external
        dst_file = tmp_path / "collected" / "result.md"
        sandbox.copy_out("outputs/result.md", dst_file)
        assert dst_file.exists()
        assert dst_file.read_text() == "# Agent Result\n\nDone."

    def test_execute_real_commands(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")

        sandbox = provider.create_sandbox(
            agent_name="executor",
            run_id="live-local-exec",
            run_dir=tmp_path,
            config=config,
        )

        # Simple echo
        result = sandbox.execute(["echo", "sandbox execution works"])
        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        assert "sandbox execution works" in result.stdout

        # Write a file and read it back via command
        sandbox.write_file("data.txt", "line1\nline2\nline3")
        result = sandbox.execute(
            [sys.executable, "-c", "print(open('data.txt').read())"],
        )
        assert result.exit_code == 0
        assert "line1" in result.stdout
        assert "line3" in result.stdout

        # Command with env vars
        result = sandbox.execute(
            [sys.executable, "-c", "import os; print(os.environ.get('SANDBOX_ID', 'not set'))"],
            env={"SANDBOX_ID": "live-local-exec"},
        )
        assert result.exit_code == 0
        assert "live-local-exec" in result.stdout

        # Command that fails
        result = sandbox.execute(
            [sys.executable, "-c", "raise ValueError('test error')"],
        )
        assert result.exit_code == 1
        assert "ValueError" in result.stderr

    def test_shared_volume_with_append(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()

        vol = provider.create_shared_volume(
            name="transcript",
            run_id="live-local-vol",
            run_dir=tmp_path,
        )

        # Initial state
        assert vol.path.exists()
        assert vol.list_files() == []

        # Write initial content
        vol.write_file("transcript.md", "# Debate Transcript\n\n")

        # Multiple agents append
        vol.append_file("transcript.md", "## Agent A -- Round 1\n\nI argue X.\n\n")
        vol.append_file("transcript.md", "## Agent B -- Round 1\n\nI argue Y.\n\n")
        vol.append_file("transcript.md", "## Agent A -- Round 2\n\nCounter to Y.\n\n")

        content = vol.read_file("transcript.md")
        assert "# Debate Transcript" in content
        assert "Agent A -- Round 1" in content
        assert "Agent B -- Round 1" in content
        assert "Agent A -- Round 2" in content
        assert content.index("Agent A -- Round 1") < content.index("Agent B -- Round 1")
        assert content.index("Agent B -- Round 1") < content.index("Agent A -- Round 2")

    def test_sandbox_isolation_between_agents(self, tmp_path: Path) -> None:
        """Local provider: each agent gets its own workspace directory."""
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")

        sb_a = provider.create_sandbox("agent-a", "run-iso", tmp_path, config)
        sb_b = provider.create_sandbox("agent-b", "run-iso", tmp_path, config)

        # Different workspace dirs
        assert sb_a.workspace_dir != sb_b.workspace_dir

        # Agent A writes a file
        sb_a.write_file("secret.txt", "agent A's data")

        # Agent B cannot see it
        assert sb_b.file_exists("secret.txt") is False
        assert sb_a.file_exists("secret.txt") is True

    def test_snapshot_returns_none_for_local(self, tmp_path: Path) -> None:
        """Local backend doesn't support snapshots (returns None)."""
        sandbox = LocalSandbox(id="s", agent_name="a", workspace_dir=tmp_path)
        sandbox.write_file("data.txt", "some data")
        assert sandbox.snapshot("phase-1") is None

    def test_destroy_preserves_files(self, tmp_path: Path) -> None:
        """Local backend preserves files after destroy for inspection."""
        sandbox = LocalSandbox(id="s", agent_name="a", workspace_dir=tmp_path)
        sandbox.write_file("keep-me.txt", "important data")
        sandbox.destroy()
        assert (tmp_path / "keep-me.txt").exists()


# ---------------------------------------------------------------------------
# FileBlackboard with LocalSandboxProvider -- end-to-end
# ---------------------------------------------------------------------------


class TestFileBlackboardLive:
    """FileBlackboard exercised with real filesystem (local backend)."""

    def test_transcript_mode_multi_agent_multi_round(self, tmp_path: Path) -> None:
        """Multi-agent, multi-round append and read in transcript mode."""
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="debate-bb", run_id="live-bb-001", run_dir=tmp_path,
        )

        bb = FileBlackboard(
            volume=vol,
            file_name="debate-transcript.md",
            access_mode="append",
        )

        # Initially empty
        assert bb.get_content() == ""

        # Round 1
        bb.append("alice", 1, "Python is versatile and readable.")
        bb.append("bob", 1, "JavaScript has broader ecosystem.")

        content = bb.get_content()
        assert "alice" in content
        assert "Round 1" in content
        assert "Python is versatile" in content
        assert "bob" in content
        assert "JavaScript has broader" in content

        # Round 2
        bb.append("alice", 2, "Python dominates in data science and ML.")
        bb.append("bob", 2, "JS runs everywhere: browser, server, mobile.")

        content = bb.get_content()
        assert "Round 2" in content
        assert "data science" in content
        assert "JS runs everywhere" in content

        # Verify ordering: round 1 before round 2
        assert content.index("Round 1") < content.index("Round 2")

        # Snapshot returns current content
        snapshot = bb.snapshot("after-round-2")
        assert "Round 1" in snapshot
        assert "Round 2" in snapshot

    def test_directory_mode(self, tmp_path: Path) -> None:
        """Directory mode: each contribution stored as separate file."""
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="dir-bb", run_id="live-bb-002", run_dir=tmp_path,
        )

        bb = FileBlackboard(
            volume=vol,
            file_name=None,  # Directory mode
            access_mode="rw",
        )

        # Initially empty
        assert bb.get_content() == ""

        # Append creates separate files
        bb.append("agent-1", 1, "First agent's contribution")
        bb.append("agent-2", 1, "Second agent's contribution")
        bb.append("agent-1", 2, "First agent round 2")

        # Directory should have 3 files
        files = vol.list_files()
        assert len(files) == 3
        assert "01-agent-1.md" in files
        assert "01-agent-2.md" in files
        assert "02-agent-1.md" in files

        # get_content concatenates all files (sorted)
        content = bb.get_content()
        assert "First agent's contribution" in content
        assert "Second agent's contribution" in content
        assert "First agent round 2" in content

    def test_read_only_raises_on_append(self, tmp_path: Path) -> None:
        """Read-only blackboard raises PermissionError on append."""
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="readonly-bb", run_id="live-bb-003", run_dir=tmp_path,
        )

        # Write some initial content
        vol.write_file("transcript.md", "Previous debate content.\n")

        bb = FileBlackboard(
            volume=vol,
            file_name="transcript.md",
            access_mode="read",
        )

        # Can read
        assert bb.get_content() == "Previous debate content.\n"

        # Cannot write
        with pytest.raises(PermissionError, match="read-only"):
            bb.append("agent", 1, "Trying to write")

    def test_rw_mode_allows_read_and_write(self, tmp_path: Path) -> None:
        """RW mode allows both reading and appending."""
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="rw-bb", run_id="live-bb-004", run_dir=tmp_path,
        )

        bb = FileBlackboard(
            volume=vol,
            file_name="board.md",
            access_mode="rw",
        )

        # Write via append
        bb.append("writer", 1, "Something important")

        # Read it back
        content = bb.get_content()
        assert "Something important" in content

    def test_snapshot_captures_state(self, tmp_path: Path) -> None:
        """Snapshot captures current blackboard state."""
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="snap-bb", run_id="live-bb-005", run_dir=tmp_path,
        )

        bb = FileBlackboard(
            volume=vol,
            file_name="transcript.md",
            access_mode="append",
        )

        bb.append("agent", 1, "Round 1 content")
        snap1 = bb.snapshot("after-round-1")
        assert "Round 1 content" in snap1

        bb.append("agent", 2, "Round 2 content")
        snap2 = bb.snapshot("after-round-2")
        assert "Round 1 content" in snap2
        assert "Round 2 content" in snap2


# ---------------------------------------------------------------------------
# AgentFS sandbox provider -- skip if CLI not installed
# ---------------------------------------------------------------------------

HAS_AGENTFS = shutil.which("agentfs") is not None


@pytest.mark.skipif(not HAS_AGENTFS, reason="agentfs CLI not installed")
class TestAgentFSSandboxProviderLive:
    """AgentFS sandbox lifecycle with real agentfs CLI."""

    def test_is_available(self) -> None:
        from ivory_tower.sandbox.agentfs import AgentFSSandboxProvider
        assert AgentFSSandboxProvider.is_available() is True

    def test_create_write_read_destroy(self, tmp_path: Path) -> None:
        from ivory_tower.sandbox.agentfs import AgentFSSandboxProvider
        from ivory_tower.sandbox.types import SandboxConfig

        provider = AgentFSSandboxProvider()
        config = SandboxConfig(backend="agentfs")

        sandbox = provider.create_sandbox(
            agent_name="test-agent",
            run_id="live-agentfs-001",
            run_dir=tmp_path,
            config=config,
        )

        # Write and read
        sandbox.write_file("test.txt", "hello agentfs")
        content = sandbox.read_file("test.txt")
        assert "hello agentfs" in content

        # File exists
        assert sandbox.file_exists("test.txt")

        # List files
        files = sandbox.list_files()
        assert any("test.txt" in f for f in files)

        # Destroy
        sandbox.destroy()


# ---------------------------------------------------------------------------
# Daytona sandbox provider -- skip if SDK not importable
# ---------------------------------------------------------------------------

HAS_DAYTONA = False
try:
    import daytona  # noqa: F401
    HAS_DAYTONA = True
except ImportError:
    pass


@pytest.mark.skipif(not HAS_DAYTONA, reason="daytona SDK not installed")
class TestDaytonaSandboxProviderLive:
    """Daytona sandbox lifecycle with real Daytona SDK."""

    def test_is_available(self) -> None:
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider
        assert DaytonaSandboxProvider.is_available() is True

    def test_create_write_read_destroy(self, tmp_path: Path) -> None:
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider
        from ivory_tower.sandbox.types import SandboxConfig

        provider = DaytonaSandboxProvider()
        config = SandboxConfig(backend="daytona")

        sandbox = provider.create_sandbox(
            agent_name="test-agent",
            run_id="live-daytona-001",
            run_dir=tmp_path,
            config=config,
        )

        try:
            # Write and read
            sandbox.write_file("test.txt", "hello daytona")
            content = sandbox.read_file("test.txt")
            assert "hello daytona" in content

            # File exists
            assert sandbox.file_exists("test.txt")
        finally:
            sandbox.destroy()


# ---------------------------------------------------------------------------
# get_provider() registry integration
# ---------------------------------------------------------------------------


class TestGetProviderLive:
    """Test the provider registry with real backends."""

    def test_none_provider(self) -> None:
        p = get_provider("none")
        assert p.name == "none"

    def test_local_provider(self) -> None:
        p = get_provider("local")
        assert p.name == "local"

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown sandbox backend"):
            get_provider("fantasy")

    @pytest.mark.skipif(HAS_AGENTFS, reason="agentfs IS available (testing absence)")
    def test_agentfs_unavailable_raises_runtime(self) -> None:
        """When agentfs CLI is not installed, get_provider should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="agentfs"):
            get_provider("agentfs")

    @pytest.mark.skipif(HAS_DAYTONA, reason="daytona IS available (testing absence)")
    def test_daytona_unavailable_raises_runtime(self) -> None:
        """When daytona SDK is not installed, get_provider should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="daytona"):
            get_provider("daytona")
