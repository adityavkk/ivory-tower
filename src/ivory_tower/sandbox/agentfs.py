"""AgentFS sandbox provider -- SQLite-backed CoW filesystem with OS-level sandboxing."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .types import ExecutionResult, SandboxConfig


class AgentFSSandbox:
    """AgentFS-backed sandbox for a single agent."""

    def __init__(
        self,
        id: str,
        agent_name: str,
        workspace_dir: Path,
        config: SandboxConfig,
        run_dir: Path,
    ) -> None:
        self.id = id
        self.agent_name = agent_name
        self.workspace_dir = workspace_dir
        self.config = config
        self.run_dir = run_dir
        self._session_id = id

    def execute(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ExecutionResult:
        start = time.monotonic()
        cmd = ["agentfs", "run", "--session", self._session_id]
        for allow_path in self.config.allow_paths:
            cmd.extend(["--allow", str(Path(allow_path).expanduser())])
        if self.config.encryption_key:
            cmd.extend(["--key", self.config.encryption_key])
        if self.config.encryption_cipher:
            cmd.extend(["--cipher", self.config.encryption_cipher])
        cmd.append("--")
        cmd.extend(command)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        elapsed = time.monotonic() - start
        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=elapsed,
        )

    def write_file(self, path: str, content: str | bytes) -> None:
        data = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
        subprocess.run(
            ["agentfs", "fs", self.id, "write", path, data],
            check=True,
        )

    def read_file(self, path: str) -> str:
        result = subprocess.run(
            ["agentfs", "fs", self.id, "cat", path],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def list_files(self, path: str = "/") -> list[str]:
        result = subprocess.run(
            ["agentfs", "fs", self.id, "ls", path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.strip().split("\n") if line]

    def file_exists(self, path: str) -> bool:
        result = subprocess.run(
            ["agentfs", "fs", self.id, "stat", path],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def copy_in(self, src: Path, dst: str) -> None:
        content = Path(src).read_text()
        self.write_file(dst, content)

    def copy_out(self, src: str, dst: Path) -> None:
        content = self.read_file(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content)

    def snapshot(self, label: str) -> Path | None:
        snapshot_dir = self.run_dir / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"{self.agent_name}-{label}.db"
        db_path = Path(f".agentfs/{self.id}.db")
        if db_path.exists():
            shutil.copy2(db_path, snapshot_path)
            return snapshot_path
        return None

    def diff(self) -> str | None:
        result = subprocess.run(
            ["agentfs", "diff", self.id],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            diff_dir = self.run_dir / "sandboxes" / self.agent_name
            diff_dir.mkdir(parents=True, exist_ok=True)
            diff_path = diff_dir / "diff.txt"
            diff_path.write_text(result.stdout)
            return result.stdout
        return None

    def destroy(self) -> None:
        pass  # AgentFS databases persist for audit


class AgentFSSharedVolume:
    """AgentFS-backed shared volume."""

    def __init__(self, id: str, path: Path) -> None:
        self.id = id
        self.path = path

    def write_file(self, path: str, content: str | bytes) -> None:
        data = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
        subprocess.run(
            ["agentfs", "fs", self.id, "write", path, data],
            check=True,
        )

    def read_file(self, path: str) -> str:
        result = subprocess.run(
            ["agentfs", "fs", self.id, "cat", path],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def append_file(self, path: str, content: str) -> None:
        subprocess.run(
            ["agentfs", "fs", self.id, "append", path, content],
            check=True,
        )

    def list_files(self, path: str = "/") -> list[str]:
        result = subprocess.run(
            ["agentfs", "fs", self.id, "ls", path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.strip().split("\n") if line]


class AgentFSSandboxProvider:
    """AgentFS sandbox provider with CoW overlay and audit support."""

    name = "agentfs"

    def create_sandbox(
        self,
        agent_name: str,
        run_id: str,
        run_dir: Path,
        config: SandboxConfig,
        base_dir: Path | None = None,
    ) -> AgentFSSandbox:
        agent_id = f"{run_id}-{agent_name}"

        cmd = ["agentfs", "init", agent_id]
        if base_dir:
            cmd.extend(["--base", str(base_dir)])
        if config.encryption_key:
            cmd.extend(["--key", config.encryption_key])
        if config.encryption_cipher:
            cmd.extend(["--cipher", config.encryption_cipher])
        subprocess.run(cmd, check=True)

        return AgentFSSandbox(
            id=agent_id,
            agent_name=agent_name,
            workspace_dir=Path(f".agentfs/{agent_id}.db"),
            config=config,
            run_dir=run_dir,
        )

    def create_shared_volume(
        self,
        name: str,
        run_id: str,
        run_dir: Path,
    ) -> AgentFSSharedVolume:
        vol_id = f"{run_id}-shared-{name}"
        subprocess.run(["agentfs", "init", vol_id], check=True)
        return AgentFSSharedVolume(
            id=vol_id,
            path=Path(f".agentfs/{vol_id}.db"),
        )

    def destroy_all(self, run_id: str) -> None:
        pass  # AgentFS databases persist for inspection/audit

    @staticmethod
    def is_available() -> bool:
        return shutil.which("agentfs") is not None
