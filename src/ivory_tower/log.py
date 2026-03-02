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


# ---- Pipeline timeline (DAG-style TUI) -------------------------------------

# Vertical timeline for multi-phase pipeline execution.  Renders a
# hierarchical view of phases, agents, sandbox events, and blackboard
# operations so the operator sees every step in the workflow.
#
# Design:
#     ▶ Debate Template -- 4 phases (sandbox: local)
#     │
#     ├── ✦ Sandbox setup
#     │   ├─ alice → sandboxes/alice/workspace
#     │   ├─ bob → sandboxes/bob/workspace
#     │   └─ judge → sandboxes/judge/workspace
#     │
#     ├── ▶ Phase 1/4 -- Opening Statements [full]
#     │   ├─ alice working... ✔ (3.2s)
#     │   └─ bob working... ✔ (4.1s)
#     │
#     ├── ▶ Phase 2/4 -- Debate Rounds [blackboard]
#     │   ├─ ⟳ Round 1/3
#     │   │  ├─ Blackboard → sandboxes (0 chars)
#     │   │  ├─ alice (round 1/3) ✔ (5.0s)
#     │   │  ├─ Blackboard ← alice (1200 chars)
#     │   │  ├─ bob (round 1/3) ✔ (4.8s)
#     │   │  └─ Blackboard ← bob (980 chars)
#     │   └─ ⟳ Round 2/3 ...
#     │
#     ├── ✔ Phase 3/4 -- Closing [read-blackboard] (8.1s)
#     ├── ✔ Phase 4/4 -- Verdict [read-all] (6.3s)
#     │
#     └── ✦ Cleanup
#         ├─ Destroyed 3 sandboxes
#         └─ Provider cleanup complete
#
# The timeline is emitted through the standard logger so it respects
# the --verbose flag and RichHandler formatting.


_logger = logging.getLogger(__name__)


def log_pipeline_header(
    template_name: str,
    total_phases: int,
    agents: list[str],
    synthesizer: str,
    sandbox_backend: str,
) -> None:
    """Emit the top-level pipeline header."""
    _logger.info("")
    _logger.info(
        fmt_phase("%s Template -- %d phases [dim](sandbox: %s)[/dim]"),
        template_name, total_phases, sandbox_backend,
    )
    agents_str = ", ".join(fmt_agent(a) for a in agents)
    _logger.info(fmt_bullet("Agents: %s"), agents_str)
    _logger.info(fmt_bullet("Synthesizer: %s"), fmt_agent(synthesizer))


def log_sandbox_setup(
    backend: str,
    agents: list[str],
    volumes: list[str] | None = None,
) -> None:
    """Emit sandbox creation summary."""
    _logger.info("")
    _logger.info("  [dim]%s[/dim] [phase]Sandbox setup[/phase] [dim](%s)[/dim]", SYM_SPARK, backend)
    for agent in agents:
        _logger.info("  [dim]│[/dim]  [dim]%s[/dim] %s sandbox ready", SYM_ARROW, fmt_agent(agent))
    if volumes:
        for vol in volumes:
            _logger.info("  [dim]│[/dim]  [dim]%s[/dim] volume [bold]%s[/bold] created", SYM_ARROW, vol)


def log_phase_header(
    phase_idx: int,
    total_phases: int,
    description: str,
    isolation: str,
    agents: list[str],
    num_rounds: int | None = None,
) -> None:
    """Emit a phase header with isolation mode."""
    _logger.info("")
    agents_str = ", ".join(fmt_agent(a) for a in agents)
    _logger.info(
        "  [dim]├──[/dim] %s [dim]\\[%s][/dim]",
        fmt_phase("Phase %d/%d -- %s" % (phase_idx, total_phases, description)),
        isolation,
    )
    _logger.info("  [dim]│[/dim]  [dim]%s[/dim] Agents: %s", SYM_ARROW, agents_str)
    if num_rounds:
        _logger.info("  [dim]│[/dim]  [dim]%s[/dim] Rounds: %d", SYM_ARROW, num_rounds)


def log_isolation_setup(isolation: str, detail: str | None = None) -> None:
    """Emit isolation mode data-copying event."""
    if detail:
        _logger.info("  [dim]│[/dim]  [dim]%s[/dim] Isolation [dim](%s)[/dim]: %s", SYM_ARROW, isolation, detail)
    else:
        _logger.debug("Isolation setup: mode=%s", isolation)


def log_agent_start(agent_name: str, context: str = "") -> None:
    """Emit agent execution start."""
    if context:
        _logger.debug("  [dim]│[/dim]  %s %s...", fmt_agent(agent_name), context)


def log_agent_complete(agent_name: str, duration: float, context: str = "") -> None:
    """Emit agent execution completion."""
    suffix = f" {context}" if context else ""
    _logger.info(
        "  [dim]│[/dim]  [ok]%s[/ok] %s%s [duration](%s)[/duration]",
        SYM_OK, fmt_agent(agent_name), suffix, fmt_duration(duration),
    )


def log_round_header(round_num: int, total_rounds: int, agents: list[str]) -> None:
    """Emit round header for iterative phases."""
    agents_str = ", ".join(fmt_agent(a) for a in agents)
    _logger.info(
        "  [dim]│[/dim]  [phase]%s Round %d/%d[/phase] -- %s",
        SYM_ROUND, round_num, total_rounds, agents_str,
    )


def log_round_complete(round_num: int, total_rounds: int, duration: float) -> None:
    """Emit round completion."""
    _logger.info(
        "  [dim]│[/dim]  [ok]%s[/ok] Round %d/%d [duration](%s)[/duration]",
        SYM_OK, round_num, total_rounds, fmt_duration(duration),
    )


def log_blackboard_sync(direction: str, agent_name: str | None = None, chars: int = 0) -> None:
    """Emit blackboard data flow event.
    
    direction: 'push' (orchestrator -> sandboxes) or 'pull' (agent output -> blackboard)
    """
    if direction == "push":
        _logger.info(
            "  [dim]│[/dim]  [dim]%s[/dim] Blackboard [dim]→[/dim] sandboxes [dim](%d chars)[/dim]",
            SYM_ARROW, chars,
        )
    elif direction == "pull" and agent_name:
        _logger.info(
            "  [dim]│[/dim]  [dim]%s[/dim] Blackboard [dim]←[/dim] %s [dim](%d chars)[/dim]",
            SYM_ARROW, fmt_agent(agent_name), chars,
        )


def log_phase_complete(phase_idx: int, total_phases: int, duration: float) -> None:
    """Emit phase completion."""
    _logger.info(
        "  [dim]│[/dim]  [ok]%s[/ok] Phase %d/%d complete [duration](%s)[/duration]",
        SYM_OK, phase_idx, total_phases, fmt_duration(duration),
    )


def log_sandbox_cleanup(num_sandboxes: int, backend: str) -> None:
    """Emit sandbox teardown summary."""
    _logger.info("")
    _logger.info(
        "  [dim]%s[/dim] [phase]Cleanup[/phase] -- %d sandboxes [dim](%s)[/dim]",
        SYM_SPARK, num_sandboxes, backend,
    )


def log_pipeline_complete(template_name: str, duration: float) -> None:
    """Emit final pipeline completion."""
    _logger.info("")
    _logger.info(
        fmt_ok("%s template complete [duration](%s)[/duration]"),
        template_name, fmt_duration(duration),
    )


# ---- Streaming panel -------------------------------------------------------


class StreamingPanel:
    """Live streaming display for agent output.

    When --stream is enabled, this replaces the spinner and shows
    agent output as it arrives. Uses Rich's Live display for smooth
    terminal updates.

    Usage::

        panel = StreamingPanel()
        panel.start()
        panel.update("claude", "Some text from the agent...")
        panel.update("claude", " more text")
        panel.stop()

    Or as a context manager::

        with StreamingPanel() as panel:
            panel.update("claude", "text")
    """

    def __init__(self) -> None:
        from rich.live import Live
        from rich.panel import Panel
        from rich.text import Text

        self._text = Text()
        self._panel = Panel(self._text, title="", border_style="dim")
        self._live = Live(self._panel, console=console, refresh_per_second=8)
        self._agent: str = ""
        self._Panel = Panel
        self._started = False

    def start(self) -> None:
        """Begin live display."""
        self._live.start()
        self._started = True

    def stop(self) -> None:
        """End live display."""
        if self._started:
            self._live.stop()
            self._started = False

    def update(self, agent_name: str, text: str) -> None:
        """Append streaming text from an agent."""
        if agent_name != self._agent:
            if self._agent:
                self._text.append("\n")
            self._agent = agent_name
            self._panel.title = f"[agent]{agent_name}[/agent]"

        self._text.append(text)
        if self._started:
            self._live.update(self._panel)

    def make_callback(self) -> "Callable[[str, str], None]":
        """Return a callback suitable for on_chunk parameter."""
        return self.update

    def __enter__(self) -> StreamingPanel:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
