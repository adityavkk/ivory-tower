"""CLI interface for ivory-tower multi-agent research orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from ivory_tower.log import setup_logging
from ivory_tower.counselors import (
    CounselorsError,
    list_available_agents,
    resolve_counselors_cmd,
    validate_agents,
)
from ivory_tower.engine import (
    ConfigError,
    RunConfig,
    print_dry_run,
    resume_pipeline,
    run_pipeline,
)
from ivory_tower.models import Manifest, PhaseStatus
from ivory_tower.strategies import get_strategy, list_strategies as _list_strategies

app = typer.Typer(name="ivory", help="Multi-agent deep research orchestrator.")


# ---------------------------------------------------------------------------
# ivory research
# ---------------------------------------------------------------------------


@app.command()
def research(
    topic: Annotated[
        Optional[str], typer.Argument(help="Research topic")
    ] = None,
    agents: Annotated[
        Optional[str],
        typer.Option("--agents", "-a", help="Comma-separated agent IDs"),
    ] = None,
    synthesizer: Annotated[
        Optional[str],
        typer.Option("--synthesizer", "-s", help="Agent ID for synthesis"),
    ] = None,
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Research strategy (council, adversarial)"),
    ] = "council",
    file: Annotated[
        Optional[Path],
        typer.Option("--file", "-f", help="Read topic from file"),
    ] = None,
    instructions: Annotated[
        Optional[str],
        typer.Option("--instructions", "-i", help="Custom instructions"),
    ] = None,
    raw: Annotated[bool, typer.Option("--raw", help="Send topic as-is")] = False,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Override output directory"),
    ] = Path("./research"),
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Stream logs")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show plan only")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Output manifest JSON on completion")
    ] = False,
    max_rounds: Annotated[
        int,
        typer.Option("--max-rounds", help="Max optimization rounds (adversarial only)"),
    ] = 10,
) -> None:
    """Run a multi-agent deep research pipeline on a topic."""
    # -- validate strategy --
    try:
        get_strategy(strategy)
    except ValueError:
        available = ", ".join(name for name, _ in _list_strategies())
        typer.echo(
            f"Unknown strategy '{strategy}'. Available: {available}",
            err=True,
        )
        raise typer.Exit(code=1)

    # -- warn if --max-rounds used with council --
    if max_rounds != 10 and strategy == "council":
        typer.echo(
            "Warning: --max-rounds is only used by the adversarial strategy.",
            err=True,
        )

    # -- required options --
    if agents is None:
        typer.echo("Error: --agents / -a is required.", err=True)
        raise typer.Exit(code=1)
    if synthesizer is None:
        typer.echo("Error: --synthesizer / -s is required.", err=True)
        raise typer.Exit(code=1)

    # -- resolve topic --
    resolved_topic = _resolve_topic(topic, file)
    if resolved_topic is None:
        typer.echo("Error: no topic provided. Pass as argument, --file, or pipe to stdin.", err=True)
        raise typer.Exit(code=1)

    # -- check counselors --
    try:
        resolve_counselors_cmd()
    except CounselorsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    # -- validate agents --
    agent_list = [a.strip() for a in agents.split(",")]
    all_agents = agent_list + [synthesizer]
    available = list_available_agents()
    invalid = validate_agents(all_agents, available)
    if invalid:
        typer.echo(
            f"Error: unknown agents: {', '.join(invalid)}\n"
            f"Available: {', '.join(available)}",
            err=True,
        )
        raise typer.Exit(code=1)

    # Configure logging
    setup_logging(verbose=verbose)

    config = RunConfig(
        topic=resolved_topic,
        agents=agent_list,
        synthesizer=synthesizer,
        raw=raw,
        instructions=instructions,
        verbose=verbose,
        output_dir=output_dir,
        dry_run=dry_run,
        strategy=strategy,
        max_rounds=max_rounds,
    )

    if dry_run:
        print_dry_run(config)
        raise typer.Exit(code=0)

    try:
        run_dir = run_pipeline(config)
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        manifest = Manifest.load(run_dir / "manifest.json")
        typer.echo(json.dumps(manifest.to_dict(), indent=2))
    else:
        typer.echo(f"Done. Report: {run_dir / 'phase3' / 'final-report.md'}")


def _resolve_topic(
    positional: str | None,
    file: Path | None,
) -> str | None:
    """Resolve topic from positional arg, --file, or stdin."""
    if positional:
        return positional
    if file is not None:
        return file.read_text().strip()
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return text
    return None


# ---------------------------------------------------------------------------
# ivory resume
# ---------------------------------------------------------------------------


@app.command()
def resume(
    run_dir: Annotated[Path, typer.Argument(help="Path to run directory")],
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Stream logs")
    ] = False,
) -> None:
    """Resume a partially-completed research run."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        typer.echo(f"Error: no manifest.json found in {run_dir}", err=True)
        raise typer.Exit(code=1)

    setup_logging(verbose=verbose)
    resume_pipeline(run_dir, verbose=verbose)
    typer.echo(f"Resumed. Report: {run_dir / 'phase3' / 'final-report.md'}")


# ---------------------------------------------------------------------------
# ivory status
# ---------------------------------------------------------------------------


@app.command()
def status(
    run_dir: Annotated[Path, typer.Argument(help="Path to run directory")],
) -> None:
    """Print status summary of a research run."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        typer.echo(f"Error: no manifest.json found in {run_dir}", err=True)
        raise typer.Exit(code=1)

    manifest = Manifest.load(manifest_path)
    topic_preview = manifest.topic[:80]

    typer.echo(f"Run ID:             {manifest.run_id}")
    typer.echo(f"Strategy:           {manifest.strategy}")
    typer.echo(f"Topic:              {topic_preview}")

    # Delegate phase status display to the strategy
    try:
        strat = get_strategy(manifest.strategy)
        phase_statuses = strat.format_status(manifest)
        for label, value in phase_statuses:
            typer.echo(f"{label + ':':<20} {value}")
    except (ValueError, NotImplementedError):
        # Fallback for unknown strategies
        typer.echo(f"Research:           {manifest.phases.get('research', {})}")

    duration = manifest.total_duration_seconds
    typer.echo(f"Total duration:     {duration:.1f}s" if duration else "Total duration:     --")


# ---------------------------------------------------------------------------
# ivory list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_runs(
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory to scan"),
    ] = Path("./research"),
) -> None:
    """List research runs found in the output directory."""
    if not output_dir.exists():
        typer.echo(f"No runs found (directory {output_dir} does not exist).")
        raise typer.Exit(code=0)

    runs: list[tuple[str, str, str, str]] = []
    for entry in sorted(output_dir.iterdir()):
        manifest_path = entry / "manifest.json"
        if entry.is_dir() and manifest_path.exists():
            try:
                m = Manifest.load(manifest_path)
                topic_short = m.topic[:50]
                strat_name = m.strategy

                # Determine overall status from strategy
                try:
                    strat = get_strategy(strat_name)
                    phase_statuses = strat.format_status(m)
                    # Use the last phase's status as overall
                    if phase_statuses:
                        last_status = phase_statuses[-1][1]
                        if last_status == "complete":
                            overall = "complete"
                        else:
                            # Find the first non-complete phase
                            for label, val in phase_statuses:
                                if val != "complete":
                                    overall = f"{label.lower()} {val}"
                                    break
                            else:
                                overall = "complete"
                    else:
                        overall = "unknown"
                except (ValueError, NotImplementedError):
                    overall = "unknown"

                runs.append((m.run_id, strat_name, topic_short, overall))
            except Exception:
                runs.append((entry.name, "?", "(error reading manifest)", "unknown"))

    if not runs:
        typer.echo("No runs found.")
        raise typer.Exit(code=0)

    # Simple table
    typer.echo(f"{'Run ID':<30} {'Strategy':<14} {'Status':<22} {'Topic'}")
    typer.echo("-" * 100)
    for run_id, strat_name, topic_short, overall in runs:
        typer.echo(f"{run_id:<30} {strat_name:<14} {overall:<22} {topic_short}")


# ---------------------------------------------------------------------------
# ivory strategies
# ---------------------------------------------------------------------------


@app.command()
def strategies() -> None:
    """List available research strategies."""
    items = _list_strategies()
    typer.echo(f"{'Strategy':<20} {'Description'}")
    typer.echo("-" * 60)
    for name, description in items:
        typer.echo(f"{name:<20} {description}")
