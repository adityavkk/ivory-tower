"""Sandbox protocol definitions and data types."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class NetworkPolicy:
    """Network access policy for sandboxed agents."""
    allow_outbound: bool = True
    allowed_domains: list[str] | None = None    # None = unrestricted
    blocked_domains: list[str] = field(default_factory=list)


@dataclass
class ResourceLimits:
    """Resource limits for sandboxed agents."""
    cpu_cores: float = 1.0
    memory_mb: int = 1024
    disk_mb: int = 512
    timeout_seconds: int = 600


@dataclass
class SandboxConfig:
    """Configuration for a sandbox instance."""
    backend: str = "none"                       # "none", "local", "agentfs", "daytona"
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    resources: ResourceLimits | None = None
    allow_paths: list[str] = field(default_factory=list)
    snapshot_after_phase: bool = False
    snapshot_on_failure: bool = True
    encryption_key: str | None = None           # AgentFS only
    encryption_cipher: str | None = None        # AgentFS only


@dataclass
class ExecutionResult:
    """Result of executing a command inside a sandbox."""
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


@runtime_checkable
class Sandbox(Protocol):
    """An isolated execution environment for a single agent."""
    id: str
    agent_name: str
    workspace_dir: Path

    def execute(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ExecutionResult: ...

    def write_file(self, path: str, content: str | bytes) -> None: ...
    def read_file(self, path: str) -> str: ...
    def list_files(self, path: str = "/") -> list[str]: ...
    def file_exists(self, path: str) -> bool: ...
    def copy_in(self, src: Path, dst: str) -> None: ...
    def copy_out(self, src: str, dst: Path) -> None: ...
    def snapshot(self, label: str) -> Path | None: ...
    def diff(self) -> str | None: ...
    def destroy(self) -> None: ...


@runtime_checkable
class SharedVolume(Protocol):
    """A shared filesystem region mountable into multiple sandboxes."""
    id: str
    path: Path

    def write_file(self, path: str, content: str | bytes) -> None: ...
    def read_file(self, path: str) -> str: ...
    def append_file(self, path: str, content: str) -> None: ...
    def list_files(self, path: str = "/") -> list[str]: ...


@runtime_checkable
class SandboxProvider(Protocol):
    """Factory for creating sandboxes and shared volumes."""
    name: str

    def create_sandbox(
        self,
        agent_name: str,
        run_id: str,
        run_dir: Path,
        config: SandboxConfig,
        base_dir: Path | None = None,
    ) -> Sandbox: ...

    def create_shared_volume(
        self,
        name: str,
        run_id: str,
        run_dir: Path,
    ) -> SharedVolume: ...

    def destroy_all(self, run_id: str) -> None: ...

    @staticmethod
    def is_available() -> bool: ...
