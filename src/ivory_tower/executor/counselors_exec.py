"""Counselors-based agent executor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ivory_tower.counselors import resolve_counselors_cmd
from ivory_tower.sandbox.types import Sandbox

from .types import AgentOutput


class CounselorsExecutor:
    """Executes agents by wrapping `counselors run` inside a sandbox."""

    name = "counselors"

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
        # Write prompt to sandbox
        sandbox.write_file("prompt.md", prompt)

        # Build counselors command
        cmd = [*resolve_counselors_cmd(), "run", "-f", "prompt.md"]

        # Use model if specified, otherwise use agent_name
        cmd.extend(["--tools", model or agent_name])

        # Output to agent's output directory within sandbox
        cmd.extend(["-o", f"{output_dir}/"])

        # Execute inside the sandbox
        env = {"COUNSELORS_VERBOSE": "1"} if verbose else None
        result = sandbox.execute(cmd, env=env)

        # Find and read the output
        report_path = _find_report(sandbox, output_dir, agent_name)
        report_text = sandbox.read_file(report_path) if report_path else ""

        return AgentOutput(
            report_path=report_path or f"{output_dir}/{agent_name}-report.md",
            raw_output=report_text,
            duration_seconds=result.duration_seconds,
            metadata={
                "exit_code": result.exit_code,
                "stderr": result.stderr,
            },
        )


def _find_report(sandbox: Sandbox, output_dir: str, agent_name: str) -> str | None:
    """Find the report file in the sandbox output directory.

    Counselors creates output in subdirectories named after the agent's slug.
    This searches for .md files in the output directory.
    """
    try:
        files = sandbox.list_files(output_dir)
    except (FileNotFoundError, OSError):
        return None

    # Look for .md files
    md_files = [f for f in files if f.endswith(".md")]
    if md_files:
        return f"{output_dir}/{md_files[0]}"

    # Fallback: any file
    if files:
        return f"{output_dir}/{files[0]}"

    return None
