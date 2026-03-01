"""Logging configuration for ivory-tower.

Provides a rich-formatted logging setup that makes the multi-phase
pipeline easy to follow in a terminal.  Call ``setup_logging()`` once
at CLI startup; every module then uses ``logging.getLogger(__name__)``.

Visual language
---------------
Phases are bracketed with heavy box-drawing lines and phase icons:

    [phase icon] Phase Name
    --- step detail
    --- step detail
    [checkmark] Phase complete (12.3s)

Agent names are highlighted. Scores, durations, and round numbers
are right-aligned for scanability.
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from typing import Generator, Literal

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.theme import Theme

# ---- Rich console & theme --------------------------------------------------

_THEME = Theme(
    {
        "phase": "bold cyan",
        "agent": "bold magenta",
        "score": "bold yellow",
        "ok": "bold green",
        "warn": "bold yellow",
        "fail": "bold red",
        "dim": "dim",
        "duration": "cyan",
    }
)

console = Console(theme=_THEME, stderr=True)

# ---- Symbols ---------------------------------------------------------------

# Unicode symbols used throughout the pipeline output.
SYM_PHASE = "\u25b6"    # small right-pointing triangle
SYM_OK = "\u2714"       # heavy check mark
SYM_FAIL = "\u2718"     # heavy ballot X
SYM_ARROW = "\u25b8"    # small right-pointing triangle (bullet)
SYM_SCORE = "\u2605"    # star
SYM_ROUND = "\u27f3"    # clockwise arrow
SYM_SPARK = "\u2726"    # four-pointed star

# ---- Setup ------------------------------------------------------------------


def setup_logging(
    verbose: bool = False,
    level: Literal["DEBUG", "INFO", "WARNING"] | None = None,
) -> None:
    """Configure the root logger with a ``RichHandler``.

    * Default (no flags): ``INFO`` level, compact single-line format.
    * ``--verbose`` / ``-v``: ``DEBUG`` level with full tracebacks.
    * Explicit *level* overrides both.

    Safe to call multiple times (removes previous handlers first).
    """
    effective_level = level or ("DEBUG" if verbose else "INFO")

    root = logging.getLogger()

    # Remove existing handlers to avoid duplicates on re-init
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=verbose,
        tracebacks_show_locals=verbose,
        markup=True,
        log_time_format="[%H:%M:%S]",
    )

    # Compact format: just the message (rich handler adds time + level)
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))

    root.addHandler(handler)
    root.setLevel(effective_level)

    # Quieten noisy third-party loggers
    for name in ("httpx", "httpcore", "urllib3", "openai", "anthropic"):
        logging.getLogger(name).setLevel(logging.WARNING)


# ---- Helper formatters (used by strategies) ---------------------------------


def fmt_duration(seconds: float | None) -> str:
    """Format a duration in human-friendly style."""
    if seconds is None:
        return "--"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


def fmt_score(score: float | None) -> str:
    """Format a score with consistent width."""
    if score is None:
        return "--"
    return f"{score:.1f}/10"


def fmt_agent(name: str) -> str:
    """Wrap agent name in rich markup for highlighting."""
    return f"[agent]{name}[/agent]"


def fmt_phase(name: str) -> str:
    """Format a phase header line."""
    return f"[phase]{SYM_PHASE} {name}[/phase]"


def fmt_ok(msg: str) -> str:
    """Format a success line."""
    return f"[ok]{SYM_OK}[/ok] {msg}"


def fmt_fail(msg: str) -> str:
    """Format a failure line."""
    return f"[fail]{SYM_FAIL}[/fail] {msg}"


def fmt_bullet(msg: str) -> str:
    """Format a step/bullet line."""
    return f"  [dim]{SYM_ARROW}[/dim] {msg}"


# ---- Live spinners & progress -----------------------------------------------


@contextmanager
def phase_spinner(
    message: str,
    *,
    done_message: str | None = None,
    spinner: str = "dots",
) -> Generator[None, None, None]:
    """Show an animated spinner while a blocking operation runs.

    Usage::

        with phase_spinner("Agents researching..."):
            run_counselors(...)

    The spinner renders on stderr via the shared *console*.  When the
    block exits, the spinner is replaced with a checkmark and the
    optional *done_message* (or the original message + duration).
    """
    t0 = time.monotonic()
    with console.status(
        f"  [dim]{SYM_ARROW}[/dim] {message}",
        spinner=spinner,
        spinner_style="cyan",
    ):
        yield
    elapsed = time.monotonic() - t0
    final = done_message or message
    console.print(
        f"  [ok]{SYM_OK}[/ok] {final} [duration]({fmt_duration(elapsed)})[/duration]"
    )


def create_agent_progress() -> Progress:
    """Create a ``Progress`` instance styled for tracking concurrent agents.

    Returns a ``Progress`` object that the caller should use as a
    context manager.  Add tasks with ``progress.add_task(agent_name)``,
    then call ``progress.update(task_id, advance=...)`` or
    ``progress.update(task_id, completed=100)`` when done.

    Usage::

        progress = create_agent_progress()
        with progress:
            tasks = {agent: progress.add_task(agent, total=None) for agent in agents}
            ...  # launch work
            progress.update(tasks[agent], description=f"[ok]{SYM_OK}[/ok] {agent}", completed=100, total=100)
    """
    return Progress(
        SpinnerColumn("dots", style="cyan"),
        TextColumn("  {task.description}"),
        BarColumn(bar_width=20, style="dim", complete_style="green", finished_style="green"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )
