"""ACP Client that routes agent tool calls through a Sandbox.

Implements the ``acp.Client`` interface so the orchestrator can intercept
every file read, file write, and terminal command an agent makes, enforcing
sandbox isolation at the protocol level.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from acp.interfaces import (
    AgentMessageChunk,
    Client,
    CreateTerminalResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    KillTerminalCommandResponse,
    TextContentBlock,
    TerminalOutputResponse,
    ToolCallUpdate,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)
from acp.schema import AllowedOutcome, DeniedOutcome

from ivory_tower.sandbox.types import Sandbox

logger = logging.getLogger(__name__)


class PathTraversalError(Exception):
    """Raised when an agent attempts to access a path outside its sandbox."""


class PermissionDeniedError(Exception):
    """Raised when an agent attempts an operation blocked by isolation mode."""


# Paths considered special by isolation modes.
_PEER_PREFIXES = ("peers/", "peers\\")
_BLACKBOARD_PREFIXES = ("blackboard/", "blackboard\\")

# Read-only tool names for the reads-only permission policy.
_READ_TOOL_NAMES = frozenset({
    "readTextFile", "read_text_file", "Read", "read",
    "terminalOutput", "terminal_output",
    "waitForTerminalExit", "wait_for_terminal_exit",
})


class SandboxACPClient(Client):
    """ACP Client that routes all agent tool calls through a Sandbox.

    Parameters
    ----------
    sandbox:
        The sandbox instance for the agent.
    isolation_mode:
        One of ``"full"`` (no peer/blackboard access), ``"read-peers"``
        (read peer reports), ``"read-blackboard"`` (read shared blackboard),
        or ``"none"`` (no restrictions beyond path traversal).
    permissions:
        Permission request policy: ``"auto-approve"`` (approve everything),
        ``"reads-only"`` (approve reads, reject writes), ``"reject-all"``.
    on_chunk:
        Optional streaming callback ``(agent_name, text_chunk) -> None``.
    """

    def __init__(
        self,
        sandbox: Sandbox,
        isolation_mode: str = "full",
        permissions: str = "auto-approve",
        on_chunk: Callable[[str, str], None] | None = None,
    ) -> None:
        self.sandbox = sandbox
        self.isolation_mode = isolation_mode
        self.permissions = permissions
        self.on_chunk = on_chunk

        self.accumulated_text: list[str] = []
        self.written_files: list[str] = []
        self._terminals: dict[str, Any] = {}
        self._last_tool_context: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_full_text(self) -> str:
        """Return all accumulated text joined as a single string."""
        return "".join(self.accumulated_text)

    def get_last_tool_context(self) -> dict[str, Any] | None:
        """Return the last observed ACP tool/request context."""
        if self._last_tool_context is None:
            return None
        return dict(self._last_tool_context)

    def reset_text(self) -> None:
        """Clear accumulated text (for session reuse across phases)."""
        self.accumulated_text.clear()

    # ------------------------------------------------------------------
    # ACP Client interface
    # ------------------------------------------------------------------

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        """Receive streaming session updates from the agent."""
        if isinstance(update, AgentMessageChunk):
            if isinstance(update.content, TextContentBlock):
                text = update.content.text
                self.accumulated_text.append(text)
                if self.on_chunk is not None:
                    self.on_chunk(self.sandbox.agent_name, text)
        elif isinstance(update, ToolCallUpdate):
            self._record_tool_context(
                tool_name="tool_call_update",
                session_id=session_id,
                title=update.title,
            )

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        """Read a text file, routed through the sandbox."""
        self._record_tool_context(
            tool_name="readTextFile",
            session_id=session_id,
            path=path,
            limit=limit,
            line=line,
        )
        try:
            resolved = self._resolve_sandbox_path(path)
            self._record_tool_context(
                tool_name="readTextFile",
                session_id=session_id,
                path=path,
                resolved_path=resolved,
            )
            self._check_read_allowed(resolved)
            content = self.sandbox.read_file(resolved)
            return ReadTextFileResponse(content=content)
        except Exception:
            logger.exception(
                "[%s] readTextFile failed (path=%r, isolation_mode=%s, permissions=%s)",
                self.sandbox.agent_name,
                path,
                self.isolation_mode,
                self.permissions,
            )
            raise

    async def write_text_file(
        self,
        content: str,
        path: str,
        session_id: str,
        **kwargs: Any,
    ) -> WriteTextFileResponse | None:
        """Write a text file, routed through the sandbox."""
        self._record_tool_context(
            tool_name="writeTextFile",
            session_id=session_id,
            path=path,
            content_bytes=len(content),
        )
        try:
            resolved = self._resolve_sandbox_path(path)
            self._record_tool_context(
                tool_name="writeTextFile",
                session_id=session_id,
                path=path,
                resolved_path=resolved,
                content_bytes=len(content),
            )
            self._check_write_allowed(resolved)
            self.sandbox.write_file(resolved, content)
            self.written_files.append(resolved)
            logger.info(
                "[%s] writeTextFile: %s (%d bytes)",
                self.sandbox.agent_name, resolved, len(content),
            )
            return WriteTextFileResponse()
        except Exception:
            logger.exception(
                "[%s] writeTextFile failed (path=%r, isolation_mode=%s, permissions=%s)",
                self.sandbox.agent_name,
                path,
                self.isolation_mode,
                self.permissions,
            )
            raise

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: Any | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        """Create a terminal, routed through sandbox.execute()."""
        self._record_tool_context(
            tool_name="createTerminal",
            session_id=session_id,
            command=command,
            args=args or [],
            cwd=cwd,
        )
        cmd_list = [command] + (args or [])

        # Convert env from ACP EnvVariable list to dict
        env_dict: dict[str, str] | None = None
        if env:
            env_dict = {}
            for var in env:
                if hasattr(var, "name") and hasattr(var, "value"):
                    env_dict[var.name] = var.value

        try:
            result = self.sandbox.execute(cmd_list, env=env_dict, cwd=cwd)
            terminal_id = str(uuid.uuid4())
            self._terminals[terminal_id] = result
            self._record_tool_context(
                tool_name="createTerminal",
                session_id=session_id,
                command=command,
                args=args or [],
                cwd=cwd,
                terminal_id=terminal_id,
                exit_code=result.exit_code,
            )
            return CreateTerminalResponse(terminal_id=terminal_id)
        except Exception:
            logger.exception(
                "[%s] createTerminal failed (command=%r, args=%s, cwd=%r)",
                self.sandbox.agent_name,
                command,
                args or [],
                cwd,
            )
            raise

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        """Handle permission requests based on the configured policy."""
        self._record_tool_context(
            tool_name="requestPermission",
            session_id=session_id,
            requested_tool=tool_call.title,
            permissions_policy=self.permissions,
            options=[opt.kind for opt in options],
        )
        match self.permissions:
            case "auto-approve":
                return self._approve_first_allow(options)
            case "reads-only":
                tool_name = tool_call.title or ""
                if tool_name in _READ_TOOL_NAMES:
                    return self._approve_first_allow(options)
                return self._reject()
            case "reject-all":
                return self._reject()
            case _:
                return self._reject()

    async def terminal_output(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> TerminalOutputResponse:
        """Return terminal output."""
        self._record_tool_context(
            tool_name="terminalOutput",
            session_id=session_id,
            terminal_id=terminal_id,
        )
        result = self._terminals.get(terminal_id)
        if result is None:
            return TerminalOutputResponse(output="")
        return TerminalOutputResponse(output=result.stdout)

    async def wait_for_terminal_exit(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> WaitForTerminalExitResponse:
        """Wait for terminal exit -- our terminals are synchronous."""
        self._record_tool_context(
            tool_name="waitForTerminalExit",
            session_id=session_id,
            terminal_id=terminal_id,
        )
        result = self._terminals.get(terminal_id)
        exit_code = result.exit_code if result else -1
        return WaitForTerminalExitResponse(exit_code=exit_code)

    async def kill_terminal(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> KillTerminalCommandResponse | None:
        """Kill a terminal -- no-op since our terminals are synchronous."""
        self._record_tool_context(
            tool_name="killTerminal",
            session_id=session_id,
            terminal_id=terminal_id,
        )
        self._terminals.pop(terminal_id, None)
        return KillTerminalCommandResponse()

    async def release_terminal(
        self,
        session_id: str,
        terminal_id: str,
        **kwargs: Any,
    ) -> ReleaseTerminalResponse | None:
        """Release a terminal."""
        self._record_tool_context(
            tool_name="releaseTerminal",
            session_id=session_id,
            terminal_id=terminal_id,
        )
        self._terminals.pop(terminal_id, None)
        return ReleaseTerminalResponse()

    def _record_tool_context(self, tool_name: str, **context: Any) -> None:
        """Track most recent ACP tool/request context for debugging."""
        self._last_tool_context = {
            "tool": tool_name,
            **context,
        }

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle unknown extension methods."""
        logger.debug("Unhandled ext_method: %s", method)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle unknown extension notifications."""
        logger.debug("Unhandled ext_notification: %s", method)

    # ------------------------------------------------------------------
    # Path resolution and validation
    # ------------------------------------------------------------------

    def _resolve_sandbox_path(self, path: str) -> str:
        """Resolve a path relative to the sandbox workspace.

        Returns a relative path string suitable for sandbox.read_file() /
        sandbox.write_file().

        Raises PathTraversalError if the resolved path escapes the workspace.
        """
        workspace = self.sandbox.workspace_dir.resolve()

        p = Path(path)
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (workspace / path).resolve()

        # Ensure the resolved path is inside the workspace
        try:
            resolved.relative_to(workspace)
        except ValueError:
            raise PathTraversalError(
                f"Path traversal denied: {path!r} resolves to "
                f"{resolved} which is outside workspace {workspace}"
            )

        # Return as relative path string
        return str(resolved.relative_to(workspace))

    # ------------------------------------------------------------------
    # Isolation mode checks
    # ------------------------------------------------------------------

    def _check_read_allowed(self, path: str) -> None:
        """Check if a read is allowed under the current isolation mode."""
        match self.isolation_mode:
            case "full":
                if self._is_peer_path(path):
                    raise PermissionDeniedError(
                        f"Read denied: {path!r} is a peer path "
                        f"(isolation_mode='full')"
                    )
                if self._is_blackboard_path(path):
                    raise PermissionDeniedError(
                        f"Read denied: {path!r} is a blackboard path "
                        f"(isolation_mode='full')"
                    )
            case "read-peers":
                # Peer reads allowed; blackboard reads blocked
                if self._is_blackboard_path(path):
                    raise PermissionDeniedError(
                        f"Read denied: {path!r} is a blackboard path "
                        f"(isolation_mode='read-peers')"
                    )
            case "read-blackboard":
                # Blackboard reads allowed; peer reads blocked
                if self._is_peer_path(path):
                    raise PermissionDeniedError(
                        f"Read denied: {path!r} is a peer path "
                        f"(isolation_mode='read-blackboard')"
                    )
            case "none":
                pass  # No restrictions

    def _check_write_allowed(self, path: str) -> None:
        """Check if a write is allowed under the current isolation mode."""
        match self.isolation_mode:
            case "full":
                if self._is_peer_path(path):
                    raise PermissionDeniedError(
                        f"Write denied: {path!r} is a peer path"
                    )
                if self._is_blackboard_path(path):
                    raise PermissionDeniedError(
                        f"Write denied: {path!r} is a blackboard path"
                    )
            case "read-peers":
                if self._is_peer_path(path):
                    raise PermissionDeniedError(
                        f"Write denied: {path!r} is a peer path "
                        f"(isolation_mode='read-peers', writes blocked)"
                    )
                if self._is_blackboard_path(path):
                    raise PermissionDeniedError(
                        f"Write denied: {path!r} is a blackboard path"
                    )
            case "read-blackboard":
                if self._is_blackboard_path(path):
                    raise PermissionDeniedError(
                        f"Write denied: {path!r} is a blackboard path "
                        f"(isolation_mode='read-blackboard', writes blocked)"
                    )
                if self._is_peer_path(path):
                    raise PermissionDeniedError(
                        f"Write denied: {path!r} is a peer path"
                    )
            case "none":
                pass

    @staticmethod
    def _is_peer_path(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in _PEER_PREFIXES)

    @staticmethod
    def _is_blackboard_path(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in _BLACKBOARD_PREFIXES)

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _approve_first_allow(
        options: list[PermissionOption],
    ) -> RequestPermissionResponse:
        """Approve the first 'allow' option."""
        for opt in options:
            if opt.kind in ("allow_once", "allow_always"):
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(
                        outcome="selected",
                        optionId=opt.option_id,
                    )
                )
        # Fallback: no allow option found
        return RequestPermissionResponse(
            outcome=DeniedOutcome(outcome="cancelled")
        )

    @staticmethod
    def _reject() -> RequestPermissionResponse:
        """Reject all permissions."""
        return RequestPermissionResponse(
            outcome=DeniedOutcome(outcome="cancelled")
        )
