"""Local sandbox provider -- directory-based isolation."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from .types import ExecutionResult, SandboxConfig

logger = logging.getLogger(__name__)


class LocalSandbox:
    """Directory-based isolated sandbox for a single agent."""

    def __init__(self, id: str, agent_name: str, workspace_dir: Path) -> None:
        self.id = id
        self.agent_name = agent_name
        self.workspace_dir = workspace_dir

    def execute(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ExecutionResult:
        start = time.monotonic()
        work_dir = Path(cwd) if cwd else self.workspace_dir
        result = subprocess.run(
            command,
            cwd=work_dir,
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
        full = self.workspace_dir / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            full.write_bytes(content)
        else:
            full.write_text(content)

    def read_file(self, path: str) -> str:
        return (self.workspace_dir / path).read_text()

    def list_files(self, path: str = "/") -> list[str]:
        target = self.workspace_dir / path.lstrip("/")
        if not target.exists():
            return []
        return [str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()]

    def file_exists(self, path: str) -> bool:
        return (self.workspace_dir / path).exists()

    def copy_in(self, src: Path, dst: str) -> None:
        full_dst = self.workspace_dir / dst
        full_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, full_dst)

    def copy_out(self, src: str, dst: Path) -> None:
        full_src = self.workspace_dir / src
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full_src, dst)

    def snapshot(self, label: str) -> Path | None:
        return None  # Local backend doesn't support snapshots

    def diff(self) -> str | None:
        return None  # Local backend doesn't support diffs

    def destroy(self) -> None:
        pass  # Keep directories for inspection


class LocalSharedVolume:
    """Directory-based shared volume."""

    def __init__(self, id: str, path: Path) -> None:
        self.id = id
        self.path = path

    def write_file(self, path: str, content: str | bytes) -> None:
        full = self.path / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            full.write_bytes(content)
        else:
            full.write_text(content)

    def read_file(self, path: str) -> str:
        return (self.path / path).read_text()

    def append_file(self, path: str, content: str) -> None:
        full = self.path / path
        full.parent.mkdir(parents=True, exist_ok=True)
        with open(full, "a") as f:
            f.write(content)

    def list_files(self, path: str = "/") -> list[str]:
        target = self.path / path.lstrip("/")
        if not target.exists():
            return []
        return [str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()]


class LocalSandboxProvider:
    """Local sandbox provider using directory-based isolation."""

    name = "local"

    def create_sandbox(
        self,
        agent_name: str,
        run_id: str,
        run_dir: Path,
        config: SandboxConfig,
        base_dir: Path | None = None,
    ) -> LocalSandbox:
        workspace = run_dir / "sandboxes" / agent_name / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        sandbox = LocalSandbox(
            id=f"{run_id}-{agent_name}",
            agent_name=agent_name,
            workspace_dir=workspace,
        )
        logger.debug("Sandbox created [local]: agent=%s workspace=%s", agent_name, workspace)
        return sandbox

    def create_shared_volume(
        self,
        name: str,
        run_id: str,
        run_dir: Path,
    ) -> LocalSharedVolume:
        vol_dir = run_dir / "volumes" / name
        vol_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Shared volume created [local]: name=%s path=%s", name, vol_dir)
        return LocalSharedVolume(id=f"{run_id}-{name}", path=vol_dir)

    def destroy_all(self, run_id: str) -> None:
        logger.debug("Sandbox cleanup [local]: run_id=%s (dirs persist)", run_id)

    @staticmethod
    def is_available() -> bool:
        return True
