"""Wrapper around the external `counselors` CLI."""

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


def check_counselors_installed() -> bool:
    """Return True if the counselors binary is on PATH."""
    return shutil.which("counselors") is not None


def list_available_agents() -> list[str]:
    """Run `counselors ls --json` and return list of agent ID strings."""
    result = subprocess.run(
        ["counselors", "ls", "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CounselorsError(result.stderr, stderr=result.stderr)
    payload = json.loads(result.stdout)
    return [entry["id"] for entry in payload]


def validate_agents(requested: list[str], available: list[str]) -> list[str]:
    """Return list of agent names in `requested` that are not in `available`."""
    available_set = set(available)
    return [name for name in requested if name not in available_set]


def run_counselors(
    prompt_file: Path,
    agents: list[str],
    output_dir: Path,
    verbose: bool = False,
) -> subprocess.CompletedProcess:
    """Run counselors with given prompt and agents.

    If verbose, streams output to terminal; otherwise captures it.
    Raises CounselorsError on non-zero exit.
    """
    cmd = [
        "counselors", "run",
        "-f", str(prompt_file),
        "--tools", ",".join(agents),
        "--json",
        "-o", str(output_dir) + "/",
    ]

    kwargs: dict = {"text": True}
    if verbose:
        # stdout/stderr inherit from parent -- not passed as kwargs
        pass
    else:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    result = subprocess.run(cmd, **kwargs)

    if result.returncode != 0:
        stderr_text = result.stderr or ""
        raise CounselorsError(stderr_text, stderr=stderr_text)

    return result
