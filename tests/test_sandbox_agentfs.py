"""Tests for the AgentFS sandbox provider -- all subprocess calls mocked."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from ivory_tower.sandbox.agentfs import (
    AgentFSSandbox,
    AgentFSSandboxProvider,
    AgentFSSharedVolume,
)
from ivory_tower.sandbox.types import ExecutionResult, SandboxConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> SandboxConfig:
    defaults = dict(backend="agentfs")
    defaults.update(overrides)
    return SandboxConfig(**defaults)


def _make_sandbox(
    tmp_path: Path,
    config: SandboxConfig | None = None,
    agent_name: str = "researcher",
    sandbox_id: str = "run1-researcher",
) -> AgentFSSandbox:
    cfg = config or _make_config()
    return AgentFSSandbox(
        id=sandbox_id,
        agent_name=agent_name,
        workspace_dir=Path(f".agentfs/{sandbox_id}.db"),
        config=cfg,
        run_dir=tmp_path,
    )


def _mock_completed_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# AgentFSSandboxProvider.is_available
# ---------------------------------------------------------------------------

class TestIsAvailable:
    @patch("ivory_tower.sandbox.agentfs.shutil.which", return_value="/usr/local/bin/agentfs")
    def test_returns_true_when_on_path(self, mock_which):
        assert AgentFSSandboxProvider.is_available() is True
        mock_which.assert_called_once_with("agentfs")

    @patch("ivory_tower.sandbox.agentfs.shutil.which", return_value=None)
    def test_returns_false_when_not_on_path(self, mock_which):
        assert AgentFSSandboxProvider.is_available() is False
        mock_which.assert_called_once_with("agentfs")


# ---------------------------------------------------------------------------
# AgentFSSandboxProvider.create_sandbox
# ---------------------------------------------------------------------------

class TestCreateSandbox:
    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_calls_agentfs_init(self, mock_run, tmp_path):
        provider = AgentFSSandboxProvider()
        config = _make_config()
        provider.create_sandbox("researcher", "run1", tmp_path, config)

        mock_run.assert_called_once_with(
            ["agentfs", "init", "run1-researcher"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_includes_base_flag(self, mock_run, tmp_path):
        provider = AgentFSSandboxProvider()
        config = _make_config()
        base = Path("/workspace/repo")
        provider.create_sandbox("researcher", "run1", tmp_path, config, base_dir=base)

        mock_run.assert_called_once_with(
            ["agentfs", "init", "run1-researcher", "--base", "/workspace/repo"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_includes_encryption_key(self, mock_run, tmp_path):
        provider = AgentFSSandboxProvider()
        config = _make_config(encryption_key="secret123")
        provider.create_sandbox("researcher", "run1", tmp_path, config)

        mock_run.assert_called_once_with(
            ["agentfs", "init", "run1-researcher", "--key", "secret123"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_includes_encryption_cipher(self, mock_run, tmp_path):
        provider = AgentFSSandboxProvider()
        config = _make_config(encryption_key="k", encryption_cipher="aes-256-gcm")
        provider.create_sandbox("researcher", "run1", tmp_path, config)

        mock_run.assert_called_once_with(
            [
                "agentfs", "init", "run1-researcher",
                "--key", "k",
                "--cipher", "aes-256-gcm",
            ],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_returns_sandbox_with_correct_id(self, mock_run, tmp_path):
        provider = AgentFSSandboxProvider()
        config = _make_config()
        sandbox = provider.create_sandbox("writer", "run42", tmp_path, config)

        assert sandbox.id == "run42-writer"
        assert sandbox.agent_name == "writer"
        assert sandbox.workspace_dir == Path(".agentfs/run42-writer.db")
        assert sandbox.config is config
        assert sandbox.run_dir == tmp_path


# ---------------------------------------------------------------------------
# AgentFSSandbox.execute
# ---------------------------------------------------------------------------

class TestExecute:
    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_builds_correct_command(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process()
        sandbox = _make_sandbox(tmp_path)
        sandbox.execute(["python", "main.py"])

        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd[:4] == ["agentfs", "run", "--session", "run1-researcher"]
        assert cmd[-3:] == ["--", "python", "main.py"]

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_includes_allow_paths(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process()
        config = _make_config(allow_paths=["/tmp/data", "/home/user/docs"])
        sandbox = _make_sandbox(tmp_path, config=config)
        sandbox.execute(["ls"])

        cmd = mock_run.call_args[0][0]
        # Find --allow flags
        allow_indices = [i for i, v in enumerate(cmd) if v == "--allow"]
        assert len(allow_indices) == 2
        assert cmd[allow_indices[0] + 1] == "/tmp/data"
        assert cmd[allow_indices[1] + 1] == "/home/user/docs"

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_includes_key_and_cipher(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process()
        config = _make_config(encryption_key="mykey", encryption_cipher="chacha20")
        sandbox = _make_sandbox(tmp_path, config=config)
        sandbox.execute(["echo", "hi"])

        cmd = mock_run.call_args[0][0]
        key_idx = cmd.index("--key")
        assert cmd[key_idx + 1] == "mykey"
        cipher_idx = cmd.index("--cipher")
        assert cmd[cipher_idx + 1] == "chacha20"

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_returns_execution_result(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(
            returncode=1, stdout="out", stderr="err"
        )
        sandbox = _make_sandbox(tmp_path)
        result = sandbox.execute(["false"])

        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 1
        assert result.stdout == "out"
        assert result.stderr == "err"
        assert result.duration_seconds >= 0


# ---------------------------------------------------------------------------
# AgentFSSandbox file operations
# ---------------------------------------------------------------------------

class TestSandboxFileOps:
    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_write_file(self, mock_run, tmp_path):
        sandbox = _make_sandbox(tmp_path)
        sandbox.write_file("/src/main.py", "print('hello')")

        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-researcher", "write", "/src/main.py", "print('hello')"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_write_file_bytes(self, mock_run, tmp_path):
        sandbox = _make_sandbox(tmp_path)
        sandbox.write_file("/data.bin", b"binary content")

        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-researcher", "write", "/data.bin", "binary content"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_read_file(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(stdout="file contents here")
        sandbox = _make_sandbox(tmp_path)
        content = sandbox.read_file("/src/main.py")

        assert content == "file contents here"
        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-researcher", "cat", "/src/main.py"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_list_files(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(stdout="a.py\nb.py\nc.py\n")
        sandbox = _make_sandbox(tmp_path)
        files = sandbox.list_files("/src")

        assert files == ["a.py", "b.py", "c.py"]

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_list_files_empty_on_error(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(returncode=1)
        sandbox = _make_sandbox(tmp_path)
        files = sandbox.list_files("/nonexistent")

        assert files == []

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_file_exists_true(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(returncode=0)
        sandbox = _make_sandbox(tmp_path)
        assert sandbox.file_exists("/src/main.py") is True

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_file_exists_false(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(returncode=1)
        sandbox = _make_sandbox(tmp_path)
        assert sandbox.file_exists("/nope.txt") is False


# ---------------------------------------------------------------------------
# AgentFSSandbox.copy_in / copy_out
# ---------------------------------------------------------------------------

class TestCopyInOut:
    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_copy_in_reads_then_writes(self, mock_run, tmp_path):
        # Create a real source file
        src = tmp_path / "source.txt"
        src.write_text("source content")

        sandbox = _make_sandbox(tmp_path)
        sandbox.copy_in(src, "/dest.txt")

        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-researcher", "write", "/dest.txt", "source content"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_copy_out_reads_from_agentfs_writes_to_disk(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(stdout="sandbox content")
        sandbox = _make_sandbox(tmp_path)

        dst = tmp_path / "output" / "result.txt"
        sandbox.copy_out("/result.txt", dst)

        assert dst.read_text() == "sandbox content"
        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-researcher", "cat", "/result.txt"],
            capture_output=True,
            text=True,
            check=True,
        )


# ---------------------------------------------------------------------------
# AgentFSSandbox.snapshot
# ---------------------------------------------------------------------------

class TestSnapshot:
    @patch("ivory_tower.sandbox.agentfs.shutil.copy2")
    @patch("ivory_tower.sandbox.agentfs.Path.exists", return_value=True)
    def test_copies_db_when_exists(self, mock_exists, mock_copy2, tmp_path):
        sandbox = _make_sandbox(tmp_path)
        result = sandbox.snapshot("phase1")

        expected_path = tmp_path / "snapshots" / "researcher-phase1.db"
        assert result == expected_path
        mock_copy2.assert_called_once()
        # Verify first arg is the db path
        src_arg = mock_copy2.call_args[0][0]
        assert str(src_arg) == f".agentfs/run1-researcher.db"
        # Verify second arg is the snapshot path
        dst_arg = mock_copy2.call_args[0][1]
        assert dst_arg == expected_path

    @patch("ivory_tower.sandbox.agentfs.Path.exists", return_value=False)
    def test_returns_none_when_db_missing(self, mock_exists, tmp_path):
        sandbox = _make_sandbox(tmp_path)
        result = sandbox.snapshot("phase1")
        assert result is None


# ---------------------------------------------------------------------------
# AgentFSSandbox.diff
# ---------------------------------------------------------------------------

class TestDiff:
    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_saves_diff_output(self, mock_run, tmp_path):
        diff_text = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        mock_run.return_value = _mock_completed_process(stdout=diff_text)
        sandbox = _make_sandbox(tmp_path)
        result = sandbox.diff()

        assert result == diff_text
        # Check diff file was written
        diff_file = tmp_path / "sandboxes" / "researcher" / "diff.txt"
        assert diff_file.read_text() == diff_text

        mock_run.assert_called_once_with(
            ["agentfs", "diff", "run1-researcher"],
            capture_output=True,
            text=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_returns_none_on_error(self, mock_run, tmp_path):
        mock_run.return_value = _mock_completed_process(returncode=1, stderr="error")
        sandbox = _make_sandbox(tmp_path)
        result = sandbox.diff()
        assert result is None


# ---------------------------------------------------------------------------
# AgentFSSharedVolume
# ---------------------------------------------------------------------------

class TestSharedVolume:
    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_write_file(self, mock_run):
        vol = AgentFSSharedVolume(id="run1-shared-comms", path=Path(".agentfs/run1-shared-comms.db"))
        vol.write_file("/log.txt", "entry1")

        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-shared-comms", "write", "/log.txt", "entry1"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_read_file(self, mock_run):
        mock_run.return_value = _mock_completed_process(stdout="entry1\nentry2")
        vol = AgentFSSharedVolume(id="run1-shared-comms", path=Path(".agentfs/run1-shared-comms.db"))
        content = vol.read_file("/log.txt")

        assert content == "entry1\nentry2"
        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-shared-comms", "cat", "/log.txt"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_append_file(self, mock_run):
        vol = AgentFSSharedVolume(id="run1-shared-comms", path=Path(".agentfs/run1-shared-comms.db"))
        vol.append_file("/log.txt", "new entry")

        mock_run.assert_called_once_with(
            ["agentfs", "fs", "run1-shared-comms", "append", "/log.txt", "new entry"],
            check=True,
        )

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_list_files(self, mock_run):
        mock_run.return_value = _mock_completed_process(stdout="a.txt\nb.txt\n")
        vol = AgentFSSharedVolume(id="run1-shared-comms", path=Path(".agentfs/run1-shared-comms.db"))
        files = vol.list_files()

        assert files == ["a.txt", "b.txt"]

    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_list_files_empty_on_error(self, mock_run):
        mock_run.return_value = _mock_completed_process(returncode=1)
        vol = AgentFSSharedVolume(id="v", path=Path("."))
        assert vol.list_files() == []


# ---------------------------------------------------------------------------
# AgentFSSandboxProvider.create_shared_volume
# ---------------------------------------------------------------------------

class TestCreateSharedVolume:
    @patch("ivory_tower.sandbox.agentfs.subprocess.run")
    def test_calls_agentfs_init_with_vol_id(self, mock_run, tmp_path):
        provider = AgentFSSandboxProvider()
        vol = provider.create_shared_volume("comms", "run1", tmp_path)

        mock_run.assert_called_once_with(
            ["agentfs", "init", "run1-shared-comms"],
            check=True,
        )
        assert vol.id == "run1-shared-comms"
        assert vol.path == Path(".agentfs/run1-shared-comms.db")


# ---------------------------------------------------------------------------
# AgentFSSandboxProvider.destroy_all (noop)
# ---------------------------------------------------------------------------

class TestDestroyAll:
    def test_destroy_all_is_noop(self):
        provider = AgentFSSandboxProvider()
        # Should not raise
        provider.destroy_all("run1")


# ---------------------------------------------------------------------------
# AgentFSSandbox.destroy (noop)
# ---------------------------------------------------------------------------

class TestSandboxDestroy:
    def test_destroy_is_noop(self, tmp_path):
        sandbox = _make_sandbox(tmp_path)
        # Should not raise
        sandbox.destroy()
