"""Daytona sandbox provider -- Docker container isolation via Daytona SDK."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .types import ExecutionResult, SandboxConfig

logger = logging.getLogger(__name__)


class DaytonaSandbox:
    """Daytona container-based sandbox for a single agent."""

    def __init__(
        self,
        id: str,
        agent_name: str,
        workspace_dir: Path,
        daytona_sandbox: Any,
        run_dir: Path,
    ) -> None:
        self.id = id
        self.agent_name = agent_name
        self.workspace_dir = workspace_dir
        self._sandbox = daytona_sandbox
        self.run_dir = run_dir

    def execute(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ExecutionResult:
        start = time.monotonic()
        work_dir = cwd or str(self.workspace_dir)
        response = self._sandbox.process.exec(
            " ".join(command),
            cwd=work_dir,
            env=env or {},
        )
        elapsed = time.monotonic() - start
        return ExecutionResult(
            exit_code=response.exit_code,
            stdout=response.stdout or "",
            stderr=response.stderr or "",
            duration_seconds=elapsed,
        )

    def write_file(self, path: str, content: str | bytes) -> None:
        full_path = f"{self.workspace_dir}/{path}"
        data = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
        self._sandbox.fs.upload_file(full_path, data)

    def read_file(self, path: str) -> str:
        full_path = f"{self.workspace_dir}/{path}"
        return self._sandbox.fs.download_file(full_path)

    def list_files(self, path: str = "/") -> list[str]:
        full_path = f"{self.workspace_dir}/{path.lstrip('/')}"
        try:
            entries = self._sandbox.fs.list_dir(full_path)
            return [e.name for e in entries if not e.is_dir]
        except Exception:
            return []

    def file_exists(self, path: str) -> bool:
        full_path = f"{self.workspace_dir}/{path}"
        try:
            self._sandbox.fs.download_file(full_path)
            return True
        except Exception:
            return False

    def copy_in(self, src: Path, dst: str) -> None:
        content = Path(src).read_text()
        self.write_file(dst, content)

    def copy_out(self, src: str, dst: Path) -> None:
        content = self.read_file(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content)

    def snapshot(self, label: str) -> Path | None:
        return None  # Daytona snapshots managed by Daytona platform

    def diff(self) -> str | None:
        return None  # Daytona doesn't support diff

    def destroy(self) -> None:
        try:
            self._sandbox.delete()
            logger.debug("Sandbox destroyed [daytona]: agent=%s", self.agent_name)
        except Exception:
            logger.warning("Sandbox destroy failed [daytona]: agent=%s", self.agent_name, exc_info=True)


class DaytonaSharedVolume:
    """Daytona FUSE volume for shared state between sandboxes."""

    def __init__(self, id: str, path: Path, volume: Any, client: Any) -> None:
        self.id = id
        self.path = path
        self._volume = volume
        self._client = client

    def write_file(self, path: str, content: str | bytes) -> None:
        full_path = f"{self.path}/{path}"
        data = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
        self._volume.upload_file(full_path, data)

    def read_file(self, path: str) -> str:
        full_path = f"{self.path}/{path}"
        return self._volume.download_file(full_path)

    def append_file(self, path: str, content: str) -> None:
        full_path = f"{self.path}/{path}"
        try:
            existing = self._volume.download_file(full_path)
        except Exception:
            existing = ""
        self._volume.upload_file(full_path, existing + content)

    def list_files(self, path: str = "/") -> list[str]:
        full_path = f"{self.path}/{path.lstrip('/')}"
        try:
            entries = self._volume.list_dir(full_path)
            return [e.name for e in entries if not e.is_dir]
        except Exception:
            return []


class DaytonaSandboxProvider:
    """Daytona sandbox provider with Docker container isolation."""

    name = "daytona"

    def __init__(self) -> None:
        from daytona import Daytona
        self.client = Daytona()
        self._sandboxes: dict[str, Any] = {}

    def create_sandbox(
        self,
        agent_name: str,
        run_id: str,
        run_dir: Path,
        config: SandboxConfig,
        base_dir: Path | None = None,
    ) -> DaytonaSandbox:
        from daytona import CreateSandboxFromSnapshotParams, Resources

        resources = None
        if config.resources:
            resources = Resources(
                cpu=int(config.resources.cpu_cores),
                memory=int(config.resources.memory_mb / 1024),
                disk=int(config.resources.disk_mb / 1024),
            )

        sandbox = self.client.create(CreateSandboxFromSnapshotParams(
            language="python",
            resources=resources,
            network_block_all=not config.network.allow_outbound,
            auto_stop_interval=(config.resources.timeout_seconds // 60
                                if config.resources else 15),
            labels={
                "ivory-tower": "true",
                "run-id": run_id,
                "agent": agent_name,
            },
        ))

        sandbox_id = f"{run_id}-{agent_name}"
        self._sandboxes[sandbox_id] = sandbox
        logger.debug(
            "Sandbox created [daytona]: agent=%s container=%s network_blocked=%s",
            agent_name, sandbox_id, not config.network.allow_outbound,
        )
        return DaytonaSandbox(
            id=sandbox_id,
            agent_name=agent_name,
            workspace_dir=Path("/workspace"),
            daytona_sandbox=sandbox,
            run_dir=run_dir,
        )

    def create_shared_volume(
        self,
        name: str,
        run_id: str,
        run_dir: Path,
    ) -> DaytonaSharedVolume:
        volume = self.client.volume.get(f"{run_id}-{name}", create=True)
        logger.debug("Shared volume created [daytona]: name=%s id=%s", name, f"{run_id}-{name}")
        return DaytonaSharedVolume(
            id=f"{run_id}-{name}",
            path=Path(f"/shared/{name}"),
            volume=volume,
            client=self.client,
        )

    def destroy_all(self, run_id: str) -> None:
        count = sum(1 for k in self._sandboxes if k.startswith(run_id))
        logger.debug("Sandbox cleanup [daytona]: run_id=%s containers=%d", run_id, count)
        for key, sandbox in list(self._sandboxes.items()):
            if key.startswith(run_id):
                try:
                    sandbox.delete()
                except Exception:
                    logger.warning("Container delete failed [daytona]: %s", key, exc_info=True)

    @staticmethod
    def is_available() -> bool:
        try:
            import daytona  # noqa: F401
            return True
        except ImportError:
            return False
