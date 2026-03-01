"""Wrapper around the external `counselors` CLI.

Resolves the counselors binary automatically: prefers a global install,
falls back to bunx then npx so users don't need a separate install step.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class CounselorsError(Exception):
    """Raised when a counselors CLI call fails."""

    def __init__(self, message: str, stderr: str | None = None):
        self.stderr = stderr
        super().__init__(message)


def resolve_counselors_cmd() -> list[str]:
    """Return the command prefix for invoking counselors.

    Resolution order:
      1. Global ``counselors`` binary on PATH
      2. ``bunx counselors`` (bun)
      3. ``npx counselors`` (node)

    Raises CounselorsError if none found.
    """
    if shutil.which("counselors"):
        return ["counselors"]
    if shutil.which("bunx"):
        return ["bunx", "counselors"]
    if shutil.which("npx"):
        return ["npx", "counselors"]
    raise CounselorsError(
        "counselors not found. Install globally (npm i -g counselors), "
        "or ensure bunx/npx is on PATH."
    )


def list_available_agents() -> list[str]:
    """Run ``counselors ls --json`` and return list of agent ID strings."""
    cmd = [*resolve_counselors_cmd(), "ls", "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CounselorsError(result.stderr, stderr=result.stderr)
    payload = json.loads(result.stdout)
    return [entry["id"] for entry in payload]


def validate_agents(requested: list[str], available: list[str]) -> list[str]:
    """Return agent names in *requested* that are not in *available*."""
    available_set = set(available)
    return [name for name in requested if name not in available_set]


def run_counselors(
    prompt_file: Path,
    agents: list[str],
    output_dir: Path,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run counselors with given prompt and agents.

    Resolves the binary automatically via resolve_counselors_cmd().
    If verbose, streams output to terminal; otherwise captures it.
    Raises CounselorsError on non-zero exit.
    """
    cmd = [
        *resolve_counselors_cmd(), "run",
        "-f", str(prompt_file),
        "--tools", ",".join(agents),
        "--json",
        "-o", str(output_dir) + "/",
    ]

    kwargs: dict = {"text": True}
    if not verbose:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    result = subprocess.run(cmd, **kwargs)

    if result.returncode != 0:
        stderr_text = result.stderr or ""
        raise CounselorsError(stderr_text, stderr=stderr_text)

    return result
