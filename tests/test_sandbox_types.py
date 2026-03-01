"""Tests for sandbox types and null provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from ivory_tower.sandbox.types import (
    ExecutionResult,
    NetworkPolicy,
    ResourceLimits,
    Sandbox,
    SandboxConfig,
    SandboxProvider,
    SharedVolume,
)
from ivory_tower.sandbox.null import NullSandbox, NullSandboxProvider, NullSharedVolume


# ---------------------------------------------------------------------------
# Dataclass default tests
# ---------------------------------------------------------------------------


class TestSandboxConfig:
    def test_defaults(self):
        cfg = SandboxConfig()
        assert cfg.backend == "none"
        assert cfg.snapshot_after_phase is False
        assert cfg.snapshot_on_failure is True
        assert cfg.resources is None
        assert cfg.allow_paths == []
        assert cfg.encryption_key is None
        assert cfg.encryption_cipher is None

    def test_network_default_is_fresh_instance(self):
        cfg = SandboxConfig()
        assert isinstance(cfg.network, NetworkPolicy)
        assert cfg.network.allow_outbound is True


class TestNetworkPolicy:
    def test_defaults(self):
        np = NetworkPolicy()
        assert np.allow_outbound is True
        assert np.allowed_domains is None
        assert np.blocked_domains == []

    def test_custom_values(self):
        np = NetworkPolicy(
            allow_outbound=False,
            allowed_domains=["example.com"],
            blocked_domains=["evil.com"],
        )
        assert np.allow_outbound is False
        assert np.allowed_domains == ["example.com"]
        assert np.blocked_domains == ["evil.com"]


class TestResourceLimits:
    def test_defaults(self):
        rl = ResourceLimits()
        assert rl.cpu_cores == 1.0
        assert rl.memory_mb == 1024
        assert rl.disk_mb == 512
        assert rl.timeout_seconds == 600


class TestExecutionResult:
    def test_stores_fields(self):
        er = ExecutionResult(
            exit_code=0,
            stdout="hello\n",
            stderr="",
            duration_seconds=1.5,
        )
        assert er.exit_code == 0
        assert er.stdout == "hello\n"
        assert er.stderr == ""
        assert er.duration_seconds == 1.5

    def test_nonzero_exit(self):
        er = ExecutionResult(exit_code=1, stdout="", stderr="fail", duration_seconds=0.1)
        assert er.exit_code == 1
        assert er.stderr == "fail"


# ---------------------------------------------------------------------------
# Protocol conformance tests
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_null_sandbox_is_sandbox(self):
        sb = NullSandbox(id="x", agent_name="a", workspace_dir=Path("/tmp"))
        assert isinstance(sb, Sandbox)

    def test_null_shared_volume_is_shared_volume(self):
        sv = NullSharedVolume(id="x", path=Path("/tmp"))
        assert isinstance(sv, SharedVolume)

    def test_null_provider_is_sandbox_provider(self):
        provider = NullSandboxProvider()
        assert isinstance(provider, SandboxProvider)


# ---------------------------------------------------------------------------
# NullSandboxProvider tests
# ---------------------------------------------------------------------------


class TestNullSandboxProvider:
    def test_is_available(self):
        assert NullSandboxProvider.is_available() is True

    def test_name(self):
        provider = NullSandboxProvider()
        assert provider.name == "none"

    def test_create_sandbox(self, tmp_path: Path):
        provider = NullSandboxProvider()
        cfg = SandboxConfig()
        sb = provider.create_sandbox(
            agent_name="researcher",
            run_id="run-42",
            run_dir=tmp_path,
            config=cfg,
        )
        assert isinstance(sb, NullSandbox)
        assert sb.id == "run-42-researcher"
        assert sb.agent_name == "researcher"
        assert sb.workspace_dir == tmp_path

    def test_create_shared_volume(self, tmp_path: Path):
        provider = NullSandboxProvider()
        vol = provider.create_shared_volume(
            name="shared",
            run_id="run-42",
            run_dir=tmp_path,
        )
        assert isinstance(vol, NullSharedVolume)
        assert vol.id == "run-42-shared"
        assert vol.path == tmp_path / "volumes" / "shared"
        assert vol.path.is_dir()

    def test_destroy_all_is_noop(self):
        provider = NullSandboxProvider()
        # Should not raise
        provider.destroy_all("run-42")


# ---------------------------------------------------------------------------
# NullSandbox tests
# ---------------------------------------------------------------------------


class TestNullSandbox:
    def test_write_and_read_file(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        sb.write_file("hello.txt", "world")
        assert sb.read_file("hello.txt") == "world"

    def test_write_and_read_binary(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        sb.write_file("data.bin", b"\x00\x01\x02")
        assert (tmp_path / "data.bin").read_bytes() == b"\x00\x01\x02"

    def test_write_creates_subdirectories(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        sb.write_file("sub/dir/file.txt", "nested")
        assert sb.read_file("sub/dir/file.txt") == "nested"

    def test_list_files(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        sb.write_file("a.txt", "a")
        sb.write_file("sub/b.txt", "b")
        files = sb.list_files()
        assert sorted(files) == sorted(["a.txt", "sub/b.txt"])

    def test_list_files_empty_dir(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        assert sb.list_files("nonexistent") == []

    def test_file_exists_true(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        sb.write_file("exists.txt", "yes")
        assert sb.file_exists("exists.txt") is True

    def test_file_exists_false(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        assert sb.file_exists("nope.txt") is False

    def test_copy_in(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path / "workspace")
        (tmp_path / "workspace").mkdir()
        # Create a source file outside the workspace
        src = tmp_path / "external.txt"
        src.write_text("external content")
        sb.copy_in(src, "imported.txt")
        assert sb.read_file("imported.txt") == "external content"

    def test_copy_out(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path / "workspace")
        (tmp_path / "workspace").mkdir()
        sb.write_file("internal.txt", "internal content")
        dst = tmp_path / "output" / "exported.txt"
        sb.copy_out("internal.txt", dst)
        assert dst.read_text() == "internal content"

    def test_execute_echo(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        result = sb.execute(["echo", "hello"])
        assert isinstance(result, ExecutionResult)
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"
        assert result.stderr == ""
        assert result.duration_seconds >= 0

    def test_execute_with_env(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        result = sb.execute(["sh", "-c", "echo $MY_VAR"], env={"MY_VAR": "test_val"})
        assert result.stdout.strip() == "test_val"

    def test_execute_nonzero_exit(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        result = sb.execute(["sh", "-c", "exit 42"])
        assert result.exit_code == 42

    def test_snapshot_returns_none(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        assert sb.snapshot("label") is None

    def test_diff_returns_none(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        assert sb.diff() is None

    def test_destroy_is_noop(self, tmp_path: Path):
        sb = NullSandbox(id="t", agent_name="a", workspace_dir=tmp_path)
        sb.write_file("keep.txt", "still here")
        sb.destroy()
        # Files should still exist after destroy (no-op)
        assert sb.file_exists("keep.txt") is True


# ---------------------------------------------------------------------------
# NullSharedVolume tests
# ---------------------------------------------------------------------------


class TestNullSharedVolume:
    def test_write_and_read_file(self, tmp_path: Path):
        vol = NullSharedVolume(id="v", path=tmp_path)
        vol.write_file("note.txt", "content")
        assert vol.read_file("note.txt") == "content"

    def test_write_binary(self, tmp_path: Path):
        vol = NullSharedVolume(id="v", path=tmp_path)
        vol.write_file("bin.dat", b"\xff\xfe")
        assert (tmp_path / "bin.dat").read_bytes() == b"\xff\xfe"

    def test_append_file(self, tmp_path: Path):
        vol = NullSharedVolume(id="v", path=tmp_path)
        vol.append_file("log.txt", "line1\n")
        vol.append_file("log.txt", "line2\n")
        assert vol.read_file("log.txt") == "line1\nline2\n"

    def test_append_creates_file_if_missing(self, tmp_path: Path):
        vol = NullSharedVolume(id="v", path=tmp_path)
        vol.append_file("new.txt", "first")
        assert vol.read_file("new.txt") == "first"

    def test_list_files(self, tmp_path: Path):
        vol = NullSharedVolume(id="v", path=tmp_path)
        vol.write_file("a.txt", "a")
        vol.write_file("sub/b.txt", "b")
        files = vol.list_files()
        assert sorted(files) == sorted(["a.txt", "sub/b.txt"])

    def test_list_files_empty(self, tmp_path: Path):
        vol = NullSharedVolume(id="v", path=tmp_path)
        assert vol.list_files("nonexistent") == []
