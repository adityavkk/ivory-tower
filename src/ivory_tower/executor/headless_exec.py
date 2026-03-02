"""Headless executor -- invokes non-ACP agents via their native CLI modes.

Tier 2 agents (Claude Code, Codex CLI, Amp, Aider) that have headless
CLI modes with machine-readable output but don't speak ACP. The executor
builds the subprocess command from agent config templates, runs it
inside the sandbox, and parses the output format to extract the agent's
response text.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from ivory_tower.agents import AgentConfig, load_agent
from ivory_tower.executor.types import AgentOutput
from ivory_tower.sandbox.types import Sandbox

logger = logging.getLogger(__name__)


class HeadlessExecExecutor:
    """AgentExecutor for non-ACP agents with headless CLI modes.

    Handles the diversity of headless CLI interfaces behind a uniform API
    by building commands from config templates and parsing agent-specific
    output formats (text, stream-json, jsonl).
    """

    name = "headless"

    def __init__(self) -> None:
        self._session_id: str | None = None

    def run(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
    ) -> AgentOutput:
        """Invoke a headless agent by building a CLI command and parsing output.

        Parameters
        ----------
        sandbox:
            The sandbox for execution.
        agent_name:
            Name of the agent (must match a config in ~/.ivory-tower/agents/).
        prompt:
            The prompt text to send to the agent.
        output_dir:
            Relative path within sandbox for output files.
        model:
            Optional model override (metadata only for headless agents).
        system_prompt:
            Optional system prompt (prepended to prompt text).
        verbose:
            Enable verbose logging.
        """
        config = load_agent(agent_name)

        # Build the effective prompt (prepend system prompt if given)
        effective_prompt = prompt
        if system_prompt:
            effective_prompt = f"{system_prompt}\n\n{prompt}"

        # Build command from config template
        cmd = self._build_command(config, effective_prompt, sandbox)

        # Prepare env
        env = dict(config.env) if config.env else None

        logger.info("[%s] Executing headless: %s", agent_name, " ".join(cmd))

        # Run in sandbox
        result = sandbox.execute(cmd, env=env)

        # Parse output based on format
        raw_output = self._parse_output(
            result.stdout,
            config.output_format,
        )

        logger.info(
            "[%s] Headless agent completed (exit=%d, %.1fs, %d chars)",
            agent_name, result.exit_code, result.duration_seconds,
            len(raw_output),
        )

        # Write report to sandbox
        report_path = f"{output_dir}/{agent_name}-report.md"
        sandbox.write_file(report_path, raw_output)

        metadata: dict[str, Any] = {
            "protocol": "headless",
            "exit_code": result.exit_code,
            "stderr": result.stderr,
            "output_format": config.output_format,
        }
        if self._session_id is not None:
            metadata["session_id"] = self._session_id

        return AgentOutput(
            report_path=report_path,
            raw_output=raw_output,
            duration_seconds=result.duration_seconds,
            metadata=metadata,
        )

    def _build_command(
        self,
        config: AgentConfig,
        prompt: str,
        sandbox: Sandbox,
    ) -> list[str]:
        """Build the CLI command, substituting placeholders in args."""
        cmd = [config.command]
        workspace_dir = str(sandbox.workspace_dir)

        for arg in config.args:
            cmd.append(
                arg.replace("{prompt}", prompt)
                   .replace("{workspace}", workspace_dir)
            )

        # Append session continuation flags if we have an active session
        if self._session_id and config.session:
            continue_flag = config.session.get("continue_flag")
            if continue_flag:
                cmd.append(continue_flag)

        return cmd

    def _parse_output(self, stdout: str, output_format: str | None) -> str:
        """Extract the agent's final response text from its output format."""
        match output_format:
            case "text" | None:
                return stdout
            case "json":
                return self._extract_text_from_json(stdout)
            case "jsonl" | "stream-json":
                return self._extract_text_from_jsonl(stdout, output_format)
        return stdout

    @staticmethod
    def _extract_text_from_json(stdout: str) -> str:
        """Extract text from a single JSON response."""
        try:
            data = json.loads(stdout)
            # Try common patterns
            if isinstance(data, dict):
                if "text" in data:
                    return data["text"]
                if "content" in data:
                    return str(data["content"])
                if "output" in data:
                    return str(data["output"])
            return str(data)
        except (json.JSONDecodeError, ValueError):
            return stdout

    @staticmethod
    def _extract_text_from_jsonl(stdout: str, format_hint: str) -> str:
        """Parse ndJSON event stream, extract assistant message text.

        Handles:
        - Claude Code stream-json: type=assistant -> message.content[].text
        - Codex JSONL: type=item.message.completed -> item.content[].text
        - Amp stream-json: type=assistant -> content.text
        """
        if not stdout.strip():
            return ""

        chunks: list[str] = []

        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(event, dict):
                continue

            event_type = event.get("type", "")

            # Claude Code stream-json format
            if event_type == "assistant" and "message" in event:
                message = event["message"]
                if isinstance(message, dict):
                    for block in message.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            chunks.append(block["text"])

            # Amp stream-json format (content directly on event)
            elif event_type == "assistant" and "content" in event:
                content = event["content"]
                if isinstance(content, dict) and content.get("type") == "text":
                    chunks.append(content["text"])

            # Codex JSONL format
            elif event_type == "item.message.completed":
                item = event.get("item", {})
                if isinstance(item, dict):
                    for part in item.get("content", []):
                        if isinstance(part, dict) and part.get("type") in (
                            "output_text", "text"
                        ):
                            chunks.append(part["text"])

        return "\n".join(chunks) if chunks else ""
