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
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler
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
