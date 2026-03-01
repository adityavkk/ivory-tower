"""Tests for the local sandbox provider."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ivory_tower.sandbox.local import (
    LocalSandbox,
    LocalSandboxProvider,
    LocalSharedVolume,
)
from ivory_tower.sandbox.types import ExecutionResult, SandboxConfig


# ---------------------------------------------------------------------------
# LocalSandboxProvider tests
# ---------------------------------------------------------------------------


class TestLocalSandboxProviderIsAvailable:
    def test_is_available_returns_true(self) -> None:
        assert LocalSandboxProvider.is_available() is True


class TestLocalSandboxProviderCreateSandbox:
    def test_creates_workspace_directory(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")
        sandbox = provider.create_sandbox(
            agent_name="claude",
            run_id="run-001",
            run_dir=tmp_path,
            config=config,
        )
        expected_dir = tmp_path / "sandboxes" / "claude" / "workspace"
        assert expected_dir.exists()
        assert expected_dir.is_dir()

    def test_sandbox_id_format(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")
        sandbox = provider.create_sandbox(
            agent_name="openai",
            run_id="run-42",
            run_dir=tmp_path,
            config=config,
        )
        assert sandbox.id == "run-42-openai"

    def test_sandbox_workspace_dir_set_correctly(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")
        sandbox = provider.create_sandbox(
            agent_name="gemini",
            run_id="run-x",
            run_dir=tmp_path,
            config=config,
        )
        assert sandbox.workspace_dir == tmp_path / "sandboxes" / "gemini" / "workspace"

    def test_sandbox_agent_name(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        config = SandboxConfig(backend="local")
        sandbox = provider.create_sandbox(
            agent_name="deepseek",
            run_id="run-y",
            run_dir=tmp_path,
            config=config,
        )
        assert sandbox.agent_name == "deepseek"


class TestLocalSandboxProviderCreateSharedVolume:
    def test_creates_volume_directory(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="blackboard",
            run_id="run-001",
            run_dir=tmp_path,
        )
        expected_dir = tmp_path / "volumes" / "blackboard"
        assert expected_dir.exists()
        assert expected_dir.is_dir()

    def test_volume_id_format(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="transcript",
            run_id="run-99",
            run_dir=tmp_path,
        )
        assert vol.id == "run-99-transcript"

    def test_volume_path_set_correctly(self, tmp_path: Path) -> None:
        provider = LocalSandboxProvider()
        vol = provider.create_shared_volume(
            name="shared",
            run_id="run-z",
            run_dir=tmp_path,
        )
        assert vol.path == tmp_path / "volumes" / "shared"


# ---------------------------------------------------------------------------
# LocalSandbox tests
# ---------------------------------------------------------------------------


class TestLocalSandboxWriteReadFile:
    def test_roundtrip_text(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        sandbox.write_file("hello.txt", "world")
        assert sandbox.read_file("hello.txt") == "world"

    def test_write_creates_nested_directories(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        sandbox.write_file("deep/nested/dir/file.txt", "content")
        assert (tmp_path / "deep" / "nested" / "dir" / "file.txt").exists()
        assert sandbox.read_file("deep/nested/dir/file.txt") == "content"

    def test_write_bytes_content(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        data = b"\x00\x01\x02\xff"
        sandbox.write_file("binary.dat", data)
        assert (tmp_path / "binary.dat").read_bytes() == data


class TestLocalSandboxListFiles:
    def test_lists_files_relative_to_workspace(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        sandbox.write_file("a.txt", "aaa")
        sandbox.write_file("sub/b.txt", "bbb")
        files = sorted(sandbox.list_files())
        assert "a.txt" in files
        assert str(Path("sub") / "b.txt") in files

    def test_list_files_empty_directory(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        assert sandbox.list_files() == []

    def test_list_files_nonexistent_path(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        assert sandbox.list_files("nonexistent") == []


class TestLocalSandboxFileExists:
    def test_returns_true_for_existing_file(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        sandbox.write_file("exists.txt", "yes")
        assert sandbox.file_exists("exists.txt") is True

    def test_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        assert sandbox.file_exists("nope.txt") is False


class TestLocalSandboxCopyIn:
    def test_copies_external_file_into_workspace(self, tmp_path: Path) -> None:
        # Set up an external file
        external = tmp_path / "external"
        external.mkdir()
        src_file = external / "source.txt"
        src_file.write_text("external content")

        # Set up sandbox with a separate workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=workspace)

        sandbox.copy_in(src_file, "imported/source.txt")
        assert sandbox.read_file("imported/source.txt") == "external content"


class TestLocalSandboxCopyOut:
    def test_copies_workspace_file_to_external_path(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=workspace)
        sandbox.write_file("report.md", "# Report")

        dst = tmp_path / "output" / "report.md"
        sandbox.copy_out("report.md", dst)
        assert dst.read_text() == "# Report"


class TestLocalSandboxExecute:
    def test_echo_hello(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        result = sandbox.execute(["echo", "hello"])
        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"
        assert result.stderr == ""
        assert result.duration_seconds >= 0

    def test_execute_with_env(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        result = sandbox.execute(
            [sys.executable, "-c", "import os; print(os.environ['MY_VAR'])"],
            env={"MY_VAR": "test_value"},
        )
        assert result.exit_code == 0
        assert result.stdout.strip() == "test_value"

    def test_execute_failing_command(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        result = sandbox.execute(
            [sys.executable, "-c", "import sys; sys.exit(42)"],
        )
        assert result.exit_code == 42


class TestLocalSandboxSnapshotDiffDestroy:
    def test_snapshot_returns_none(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        assert sandbox.snapshot("label") is None

    def test_diff_returns_none(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        assert sandbox.diff() is None

    def test_destroy_is_noop(self, tmp_path: Path) -> None:
        sandbox = LocalSandbox(id="s1", agent_name="a", workspace_dir=tmp_path)
        sandbox.write_file("keep.txt", "data")
        sandbox.destroy()
        # Files still exist after destroy (local backend preserves for inspection)
        assert (tmp_path / "keep.txt").exists()


# ---------------------------------------------------------------------------
# LocalSharedVolume tests
# ---------------------------------------------------------------------------


class TestLocalSharedVolumeWriteRead:
    def test_roundtrip_text(self, tmp_path: Path) -> None:
        vol = LocalSharedVolume(id="v1", path=tmp_path)
        vol.write_file("notes.txt", "hello shared")
        assert vol.read_file("notes.txt") == "hello shared"

    def test_write_creates_nested_directories(self, tmp_path: Path) -> None:
        vol = LocalSharedVolume(id="v1", path=tmp_path)
        vol.write_file("a/b/c.txt", "deep")
        assert vol.read_file("a/b/c.txt") == "deep"


class TestLocalSharedVolumeAppend:
    def test_append_to_existing_content(self, tmp_path: Path) -> None:
        vol = LocalSharedVolume(id="v1", path=tmp_path)
        vol.write_file("log.txt", "line1\n")
        vol.append_file("log.txt", "line2\n")
        assert vol.read_file("log.txt") == "line1\nline2\n"

    def test_append_creates_file_if_missing(self, tmp_path: Path) -> None:
        vol = LocalSharedVolume(id="v1", path=tmp_path)
        vol.append_file("new.txt", "first")
        assert vol.read_file("new.txt") == "first"


class TestLocalSharedVolumeListFiles:
    def test_lists_files(self, tmp_path: Path) -> None:
        vol = LocalSharedVolume(id="v1", path=tmp_path)
        vol.write_file("a.txt", "a")
        vol.write_file("sub/b.txt", "b")
        files = sorted(vol.list_files())
        assert "a.txt" in files
        assert str(Path("sub") / "b.txt") in files

    def test_list_files_empty(self, tmp_path: Path) -> None:
        vol = LocalSharedVolume(id="v1", path=tmp_path)
        assert vol.list_files() == []

    def test_list_files_nonexistent_path(self, tmp_path: Path) -> None:
        vol = LocalSharedVolume(id="v1", path=tmp_path)
        assert vol.list_files("nope") == []
