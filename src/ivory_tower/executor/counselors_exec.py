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
    """Find the agent's report file in the sandbox output directory.

    Counselors creates output in a subdirectory (slug) like:
        <output_dir>/<slug>/prompt.md
        <output_dir>/<slug>/summary.md
        <output_dir>/<slug>/run.json
        <output_dir>/<slug>/<agent>.md        <- the actual output
        <output_dir>/<slug>/<agent>.stderr

    Strategy: prefer the file matching the agent name, then fall back to
    the largest .md file excluding known counselors meta-files.
    """
    # Known counselors meta-files that are NOT agent output
    META_FILES = {"prompt.md", "summary.md", "run.json"}

    try:
        files = sandbox.list_files(output_dir)
    except (FileNotFoundError, OSError):
        return None

    if not files:
        return None

    md_files = [f for f in files if f.endswith(".md")]

    # 1. Prefer the file matching the agent name exactly
    agent_file = f"{agent_name}.md"
    for f in md_files:
        if Path(f).name == agent_file:
            return f"{output_dir}/{f}"

    # 2. Filter out known meta-files and .stderr files
    candidate_md = [f for f in md_files if Path(f).name not in META_FILES]

    # 3. If exactly one candidate, use it directly (no need to measure sizes)
    if len(candidate_md) == 1:
        return f"{output_dir}/{candidate_md[0]}"

    # 4. Multiple candidates: pick the largest (likely the actual report)
    if candidate_md:
        best = max(
            candidate_md,
            key=lambda f: len(sandbox.read_file(f"{output_dir}/{f}")),
        )
        return f"{output_dir}/{best}"

    # 5. Last resort: any .md file (even meta-files)
    if md_files:
        return f"{output_dir}/{md_files[0]}"

    # 6. Any file at all
    return f"{output_dir}/{files[0]}"
