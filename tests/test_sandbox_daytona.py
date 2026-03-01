"""Tests for Daytona sandbox provider -- all SDK calls mocked."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.sandbox.types import (
    ExecutionResult,
    NetworkPolicy,
    ResourceLimits,
    SandboxConfig,
)


# ---------------------------------------------------------------------------
# Helpers: fake daytona module injected via sys.modules
# ---------------------------------------------------------------------------


def _make_dir_entry(name: str, *, is_dir: bool = False) -> MagicMock:
    """Create a mock directory entry with a real ``name`` attribute.

    ``MagicMock(name=...)`` reserves *name* for the mock's own label, so we
    must set it after construction.
    """
    entry = MagicMock()
    entry.name = name
    entry.is_dir = is_dir
    return entry


def _make_fake_daytona_module() -> MagicMock:
    """Build a mock that stands in for the entire ``daytona`` package."""
    mod = MagicMock()
    # Each attribute must be a *callable* MagicMock instance so that
    # ``from daytona import Foo; Foo(...)`` records call_args properly.
    mod.Daytona = MagicMock()
    mod.CreateSandboxFromSnapshotParams = MagicMock()
    mod.Resources = MagicMock()
    return mod


@pytest.fixture()
def fake_daytona():
    """Inject a fake ``daytona`` module into *sys.modules* for the duration of
    the test, then clean up so it doesn't leak.  Returns the mock module."""
    mod = _make_fake_daytona_module()
    with patch.dict(sys.modules, {"daytona": mod}):
        yield mod


@pytest.fixture()
def _no_daytona():
    """Ensure ``daytona`` is NOT importable."""
    with patch.dict(sys.modules, {"daytona": None}):
        yield


# ---------------------------------------------------------------------------
# DaytonaSandboxProvider.is_available()
# ---------------------------------------------------------------------------


class TestIsAvailable:
    @pytest.mark.usefixtures("_no_daytona")
    def test_false_when_not_importable(self):
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider

        assert DaytonaSandboxProvider.is_available() is False

    def test_true_when_importable(self, fake_daytona):
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider

        assert DaytonaSandboxProvider.is_available() is True


# ---------------------------------------------------------------------------
# DaytonaSandboxProvider.__init__
# ---------------------------------------------------------------------------


class TestProviderInit:
    def test_creates_client(self, fake_daytona):
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider

        mock_client = MagicMock()
        fake_daytona.Daytona = MagicMock(return_value=mock_client)

        provider = DaytonaSandboxProvider()
        assert provider.client is mock_client
        fake_daytona.Daytona.assert_called_once()


# ---------------------------------------------------------------------------
# create_sandbox
# ---------------------------------------------------------------------------


class TestCreateSandbox:
    @pytest.fixture()
    def provider(self, fake_daytona):
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider

        mock_client = MagicMock()
        fake_daytona.Daytona = MagicMock(return_value=mock_client)
        p = DaytonaSandboxProvider()
        return p

    def test_calls_client_create(self, provider, fake_daytona, tmp_path):
        cfg = SandboxConfig()
        provider.create_sandbox(
            agent_name="researcher",
            run_id="run-1",
            run_dir=tmp_path,
            config=cfg,
        )
        provider.client.create.assert_called_once()

    def test_returns_sandbox_with_correct_id_and_workspace(self, provider, fake_daytona, tmp_path):
        from ivory_tower.sandbox.daytona import DaytonaSandbox

        cfg = SandboxConfig()
        sb = provider.create_sandbox(
            agent_name="researcher",
            run_id="run-1",
            run_dir=tmp_path,
            config=cfg,
        )
        assert isinstance(sb, DaytonaSandbox)
        assert sb.id == "run-1-researcher"
        assert sb.agent_name == "researcher"
        assert sb.workspace_dir == Path("/workspace")
        assert sb.run_dir == tmp_path

    def test_resource_limits_passed_correctly(self, provider, fake_daytona, tmp_path):
        rl = ResourceLimits(cpu_cores=2.0, memory_mb=2048, disk_mb=4096, timeout_seconds=900)
        cfg = SandboxConfig(resources=rl)

        provider.create_sandbox(
            agent_name="coder",
            run_id="run-2",
            run_dir=tmp_path,
            config=cfg,
        )

        # Resources() should have been called with correct values
        fake_daytona.Resources.assert_called_once_with(
            cpu=2,
            memory=2,   # 2048 / 1024
            disk=4,     # 4096 / 1024
        )

    def test_network_block_all_when_outbound_disabled(self, provider, fake_daytona, tmp_path):
        cfg = SandboxConfig(network=NetworkPolicy(allow_outbound=False))
        provider.create_sandbox(
            agent_name="agent",
            run_id="run-3",
            run_dir=tmp_path,
            config=cfg,
        )

        call_args = fake_daytona.CreateSandboxFromSnapshotParams.call_args
        assert call_args.kwargs["network_block_all"] is True

    def test_network_not_blocked_when_outbound_allowed(self, provider, fake_daytona, tmp_path):
        cfg = SandboxConfig(network=NetworkPolicy(allow_outbound=True))
        provider.create_sandbox(
            agent_name="agent",
            run_id="run-4",
            run_dir=tmp_path,
            config=cfg,
        )

        call_args = fake_daytona.CreateSandboxFromSnapshotParams.call_args
        assert call_args.kwargs["network_block_all"] is False

    def test_labels_set_correctly(self, provider, fake_daytona, tmp_path):
        cfg = SandboxConfig()
        provider.create_sandbox(
            agent_name="writer",
            run_id="run-5",
            run_dir=tmp_path,
            config=cfg,
        )

        call_args = fake_daytona.CreateSandboxFromSnapshotParams.call_args
        labels = call_args.kwargs["labels"]
        assert labels == {
            "ivory-tower": "true",
            "run-id": "run-5",
            "agent": "writer",
        }

    def test_auto_stop_from_resource_timeout(self, provider, fake_daytona, tmp_path):
        rl = ResourceLimits(timeout_seconds=900)
        cfg = SandboxConfig(resources=rl)
        provider.create_sandbox(
            agent_name="a",
            run_id="run-6",
            run_dir=tmp_path,
            config=cfg,
        )
        call_args = fake_daytona.CreateSandboxFromSnapshotParams.call_args
        assert call_args.kwargs["auto_stop_interval"] == 15  # 900 // 60

    def test_auto_stop_default_when_no_resources(self, provider, fake_daytona, tmp_path):
        cfg = SandboxConfig(resources=None)
        provider.create_sandbox(
            agent_name="a",
            run_id="run-7",
            run_dir=tmp_path,
            config=cfg,
        )
        call_args = fake_daytona.CreateSandboxFromSnapshotParams.call_args
        assert call_args.kwargs["auto_stop_interval"] == 15


# ---------------------------------------------------------------------------
# DaytonaSandbox methods
# ---------------------------------------------------------------------------


def _make_sandbox(mock_inner=None, workspace="/workspace", run_dir=None):
    """Helper to build a DaytonaSandbox with a mock inner sandbox."""
    from ivory_tower.sandbox.daytona import DaytonaSandbox

    if mock_inner is None:
        mock_inner = MagicMock()
    return DaytonaSandbox(
        id="run-1-agent",
        agent_name="agent",
        workspace_dir=Path(workspace),
        daytona_sandbox=mock_inner,
        run_dir=run_dir or Path("/tmp/run"),
    )


class TestDaytonaSandboxExecute:
    def test_calls_process_exec(self, fake_daytona):
        inner = MagicMock()
        inner.process.exec.return_value = MagicMock(
            exit_code=0, stdout="ok\n", stderr=""
        )
        sb = _make_sandbox(inner)

        sb.execute(["echo", "hello"])

        inner.process.exec.assert_called_once_with(
            "echo hello",
            cwd="/workspace",
            env={},
        )

    def test_returns_execution_result(self, fake_daytona):
        inner = MagicMock()
        inner.process.exec.return_value = MagicMock(
            exit_code=0, stdout="ok\n", stderr=""
        )
        sb = _make_sandbox(inner)

        result = sb.execute(["echo", "hello"])

        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        assert result.stdout == "ok\n"
        assert result.stderr == ""
        assert result.duration_seconds >= 0

    def test_passes_env_and_cwd(self, fake_daytona):
        inner = MagicMock()
        inner.process.exec.return_value = MagicMock(
            exit_code=0, stdout="", stderr=""
        )
        sb = _make_sandbox(inner)

        sb.execute(["ls"], env={"FOO": "bar"}, cwd="/custom")

        inner.process.exec.assert_called_once_with(
            "ls",
            cwd="/custom",
            env={"FOO": "bar"},
        )

    def test_handles_none_stdout_stderr(self, fake_daytona):
        inner = MagicMock()
        inner.process.exec.return_value = MagicMock(
            exit_code=1, stdout=None, stderr=None
        )
        sb = _make_sandbox(inner)

        result = sb.execute(["fail"])

        assert result.stdout == ""
        assert result.stderr == ""


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


class TestDaytonaSandboxFiles:
    def test_write_file(self, fake_daytona):
        inner = MagicMock()
        sb = _make_sandbox(inner)

        sb.write_file("hello.txt", "world")

        inner.fs.upload_file.assert_called_once_with("/workspace/hello.txt", "world")

    def test_write_file_bytes(self, fake_daytona):
        inner = MagicMock()
        sb = _make_sandbox(inner)

        sb.write_file("data.bin", b"\xc3\xa9")

        inner.fs.upload_file.assert_called_once_with("/workspace/data.bin", "é")

    def test_read_file(self, fake_daytona):
        inner = MagicMock()
        inner.fs.download_file.return_value = "contents"
        sb = _make_sandbox(inner)

        result = sb.read_file("hello.txt")

        inner.fs.download_file.assert_called_once_with("/workspace/hello.txt")
        assert result == "contents"

    def test_list_files(self, fake_daytona):
        inner = MagicMock()
        entry1 = _make_dir_entry("a.txt", is_dir=False)
        entry2 = _make_dir_entry("subdir", is_dir=True)
        entry3 = _make_dir_entry("b.txt", is_dir=False)
        inner.fs.list_dir.return_value = [entry1, entry2, entry3]
        sb = _make_sandbox(inner)

        result = sb.list_files()

        assert result == ["a.txt", "b.txt"]

    def test_list_files_returns_empty_on_error(self, fake_daytona):
        inner = MagicMock()
        inner.fs.list_dir.side_effect = Exception("not found")
        sb = _make_sandbox(inner)

        assert sb.list_files("nonexistent") == []

    def test_file_exists_true(self, fake_daytona):
        inner = MagicMock()
        inner.fs.download_file.return_value = "data"
        sb = _make_sandbox(inner)

        assert sb.file_exists("hello.txt") is True

    def test_file_exists_false(self, fake_daytona):
        inner = MagicMock()
        inner.fs.download_file.side_effect = Exception("not found")
        sb = _make_sandbox(inner)

        assert sb.file_exists("nope.txt") is False


# ---------------------------------------------------------------------------
# copy_in / copy_out
# ---------------------------------------------------------------------------


class TestDaytonaSandboxCopy:
    def test_copy_in(self, fake_daytona, tmp_path):
        inner = MagicMock()
        sb = _make_sandbox(inner)

        src = tmp_path / "local.txt"
        src.write_text("local content")

        sb.copy_in(src, "remote.txt")

        inner.fs.upload_file.assert_called_once_with(
            "/workspace/remote.txt", "local content"
        )

    def test_copy_out(self, fake_daytona, tmp_path):
        inner = MagicMock()
        inner.fs.download_file.return_value = "remote content"
        sb = _make_sandbox(inner)

        dst = tmp_path / "output" / "result.txt"
        sb.copy_out("result.txt", dst)

        inner.fs.download_file.assert_called_once_with("/workspace/result.txt")
        assert dst.read_text() == "remote content"
        assert dst.parent.is_dir()


# ---------------------------------------------------------------------------
# snapshot / diff / destroy
# ---------------------------------------------------------------------------


class TestDaytonaSandboxLifecycle:
    def test_snapshot_returns_none(self, fake_daytona):
        sb = _make_sandbox()
        assert sb.snapshot("label") is None

    def test_diff_returns_none(self, fake_daytona):
        sb = _make_sandbox()
        assert sb.diff() is None

    def test_destroy_calls_delete(self, fake_daytona):
        inner = MagicMock()
        sb = _make_sandbox(inner)

        sb.destroy()

        inner.delete.assert_called_once()

    def test_destroy_handles_exception(self, fake_daytona):
        inner = MagicMock()
        inner.delete.side_effect = RuntimeError("boom")
        sb = _make_sandbox(inner)

        # Should not raise
        sb.destroy()


# ---------------------------------------------------------------------------
# DaytonaSharedVolume
# ---------------------------------------------------------------------------


class TestDaytonaSharedVolume:
    def _make_volume(self):
        from ivory_tower.sandbox.daytona import DaytonaSharedVolume

        mock_vol = MagicMock()
        mock_client = MagicMock()
        return DaytonaSharedVolume(
            id="run-1-shared",
            path=Path("/shared/data"),
            volume=mock_vol,
            client=mock_client,
        ), mock_vol

    def test_write_file(self, fake_daytona):
        vol, mock_vol = self._make_volume()
        vol.write_file("note.txt", "hello")
        mock_vol.upload_file.assert_called_once_with("/shared/data/note.txt", "hello")

    def test_write_file_bytes(self, fake_daytona):
        vol, mock_vol = self._make_volume()
        vol.write_file("bin.dat", b"\xc3\xa9")  # UTF-8 for "é"
        mock_vol.upload_file.assert_called_once_with(
            "/shared/data/bin.dat", "é"
        )

    def test_read_file(self, fake_daytona):
        vol, mock_vol = self._make_volume()
        mock_vol.download_file.return_value = "content"
        result = vol.read_file("note.txt")
        mock_vol.download_file.assert_called_once_with("/shared/data/note.txt")
        assert result == "content"

    def test_append_file_creates_new(self, fake_daytona):
        vol, mock_vol = self._make_volume()
        mock_vol.download_file.side_effect = Exception("not found")
        vol.append_file("log.txt", "first line\n")
        mock_vol.upload_file.assert_called_once_with(
            "/shared/data/log.txt", "first line\n"
        )

    def test_append_file_appends_existing(self, fake_daytona):
        vol, mock_vol = self._make_volume()
        mock_vol.download_file.return_value = "existing\n"
        vol.append_file("log.txt", "new\n")
        mock_vol.upload_file.assert_called_once_with(
            "/shared/data/log.txt", "existing\nnew\n"
        )

    def test_list_files(self, fake_daytona):
        vol, mock_vol = self._make_volume()
        entry1 = _make_dir_entry("a.txt", is_dir=False)
        entry2 = _make_dir_entry("dir", is_dir=True)
        mock_vol.list_dir.return_value = [entry1, entry2]
        result = vol.list_files()
        assert result == ["a.txt"]

    def test_list_files_empty_on_error(self, fake_daytona):
        vol, mock_vol = self._make_volume()
        mock_vol.list_dir.side_effect = Exception("err")
        assert vol.list_files() == []


# ---------------------------------------------------------------------------
# create_shared_volume
# ---------------------------------------------------------------------------


class TestCreateSharedVolume:
    def test_calls_volume_get(self, fake_daytona):
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider, DaytonaSharedVolume

        mock_client = MagicMock()
        fake_daytona.Daytona = MagicMock(return_value=mock_client)

        provider = DaytonaSandboxProvider()
        vol = provider.create_shared_volume(
            name="shared",
            run_id="run-1",
            run_dir=Path("/tmp/run"),
        )

        mock_client.volume.get.assert_called_once_with("run-1-shared", create=True)
        assert isinstance(vol, DaytonaSharedVolume)
        assert vol.id == "run-1-shared"
        assert vol.path == Path("/shared/shared")


# ---------------------------------------------------------------------------
# destroy_all
# ---------------------------------------------------------------------------


class TestDestroyAll:
    def test_deletes_matching_sandboxes(self, fake_daytona):
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider

        mock_client = MagicMock()
        fake_daytona.Daytona = MagicMock(return_value=mock_client)

        provider = DaytonaSandboxProvider()

        # Simulate two sandboxes from same run and one from different run
        sb1 = MagicMock()
        sb2 = MagicMock()
        sb_other = MagicMock()
        provider._sandboxes = {
            "run-1-agent1": sb1,
            "run-1-agent2": sb2,
            "run-2-agent1": sb_other,
        }

        provider.destroy_all("run-1")

        sb1.delete.assert_called_once()
        sb2.delete.assert_called_once()
        sb_other.delete.assert_not_called()

    def test_handles_delete_exception(self, fake_daytona):
        from ivory_tower.sandbox.daytona import DaytonaSandboxProvider

        mock_client = MagicMock()
        fake_daytona.Daytona = MagicMock(return_value=mock_client)

        provider = DaytonaSandboxProvider()

        sb1 = MagicMock()
        sb1.delete.side_effect = RuntimeError("boom")
        sb2 = MagicMock()
        provider._sandboxes = {
            "run-1-a": sb1,
            "run-1-b": sb2,
        }

        # Should not raise even though sb1.delete() blows up
        provider.destroy_all("run-1")

        sb1.delete.assert_called_once()
        sb2.delete.assert_called_once()
