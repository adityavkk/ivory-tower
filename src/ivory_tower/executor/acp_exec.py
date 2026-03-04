"""ACP executor -- invokes agents via the Agent Client Protocol over stdio."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Callable

from acp import spawn_agent_process, text_block

from ivory_tower.acp_client import SandboxACPClient
from ivory_tower.agents import load_agent, resolve_agent_binary
from ivory_tower.executor.types import AgentOutput
from ivory_tower.sandbox.types import Sandbox

logger = logging.getLogger(__name__)


class ACPExecutor:
    """AgentExecutor that invokes agents via ACP over stdio.

    Manages the full ACP lifecycle per invocation:
    initialize -> session/new -> session/prompt -> collect response -> cleanup.

    Agent output is the accumulated text from AgentMessageChunk session
    updates. No filesystem scraping.
    """

    name = "acp"

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}

    def run(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
        session_id: str | None = None,
        on_chunk: Callable[[str, str], None] | None = None,
    ) -> AgentOutput:
        """Invoke an agent via ACP. Blocks until agent completes.

        Parameters
        ----------
        sandbox:
            The sandbox for the agent's workspace.
        agent_name:
            Name of the agent (must match a config in ~/.ivory-tower/agents/).
        prompt:
            The prompt text to send to the agent.
        output_dir:
            Relative path within sandbox for output files.
        model:
            Optional model override (sent via set_session_model if supported).
        system_prompt:
            Optional system prompt (prepended to prompt content blocks).
        verbose:
            Enable verbose logging.
        session_id:
            Optional session ID for reusing an existing session.
        on_chunk:
            Optional streaming callback (agent_name, text_chunk).
        """
        return asyncio.run(self._run_async(
            sandbox, agent_name, prompt, output_dir,
            model, system_prompt, verbose, session_id, on_chunk,
        ))

    async def _run_async(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None,
        system_prompt: str | None,
        verbose: bool,
        session_id: str | None,
        on_chunk: Callable[[str, str], None] | None,
    ) -> AgentOutput:
        """Async implementation of the ACP invocation lifecycle."""
        config = load_agent(agent_name)
        binary = resolve_agent_binary(config)

        start_time = time.monotonic()

        # Build the ACP client that routes tool calls through the sandbox
        client = SandboxACPClient(
            sandbox=sandbox,
            isolation_mode="full",
            permissions="auto-approve",
            on_chunk=on_chunk,
        )

        # Build command args
        cmd_args = [str(a) for a in config.args]

        # Merge agent env with process env
        env = dict(config.env) if config.env else None

        logger.info("[%s] Spawning ACP agent: %s %s", agent_name, binary, " ".join(cmd_args))

        async with spawn_agent_process(
            client,
            str(binary),
            *cmd_args,
            env=env,
            cwd=str(sandbox.workspace_dir),
            transport_kwargs={"limit": 10 * 1024 * 1024},  # 10 MB stdio buffer
        ) as (conn, proc):
            # Step 1: Initialize
            init_response = await conn.initialize(protocol_version=1)
            logger.debug("[%s] ACP initialized: %s", agent_name, init_response)

            # Step 2: Create or reuse session
            session = await conn.new_session(cwd=str(sandbox.workspace_dir))
            current_session_id = session.session_id
            logger.debug("[%s] Session created: %s", agent_name, current_session_id)

            # Step 3: Set model if requested
            if model:
                try:
                    await conn.set_session_model(
                        model_id=model,
                        session_id=current_session_id,
                    )
                except Exception:
                    logger.debug(
                        "[%s] set_session_model not supported, ignoring",
                        agent_name,
                    )

            # Step 4: Build prompt content blocks
            blocks = []
            if system_prompt:
                blocks.append(text_block(f"[System]\n{system_prompt}\n\n"))
            blocks.append(text_block(prompt))

            # Step 5: Send prompt and wait for response
            logger.info("[%s] Sending prompt (%d chars)", agent_name, len(prompt))
            try:
                response = await conn.prompt(
                    prompt=blocks,
                    session_id=current_session_id,
                )
            except Exception:
                logger.exception(
                    "[%s] ACP prompt failed (session_id=%s, last_tool_context=%s)",
                    agent_name,
                    current_session_id,
                    client.get_last_tool_context(),
                )
                raise

            duration = time.monotonic() - start_time
            raw_output = client.get_full_text()

            logger.info(
                "[%s] Agent completed in %.1fs (%d chars, stop_reason=%s)",
                agent_name, duration, len(raw_output),
                response.stop_reason,
            )

            # Step 6: Write the report to the sandbox
            report_path = f"{output_dir}/{agent_name}-report.md"
            sandbox.write_file(report_path, raw_output)

            return AgentOutput(
                report_path=report_path,
                raw_output=raw_output,
                duration_seconds=duration,
                metadata={
                    "session_id": current_session_id,
                    "stop_reason": response.stop_reason,
                    "written_files": list(client.written_files),
                    "protocol": "acp",
                },
            )

    def close_session(self, session_id: str) -> None:
        """Terminate a persistent session and its agent process."""
        session_data = self._sessions.pop(session_id, None)
        if session_data is not None:
            logger.info("Closing session %s", session_id)
