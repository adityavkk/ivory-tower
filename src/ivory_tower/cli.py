"""CLI interface for ivory-tower multi-agent research orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from ivory_tower.counselors import (
    CounselorsError,
    list_available_agents,
    resolve_counselors_cmd,
    validate_agents,
)
from ivory_tower.engine import (
    RunConfig,
    print_dry_run,
    resume_pipeline,
    run_pipeline,
    run_phase1,
    run_phase2,
    run_phase3,
)
from ivory_tower.models import Manifest, PhaseStatus
from ivory_tower.strategies import list_strategies as _list_strategies

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
) -> None:
    """Run a multi-agent deep research pipeline on a topic."""
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

    config = RunConfig(
        topic=resolved_topic,
        agents=agent_list,
        synthesizer=synthesizer,
        raw=raw,
        instructions=instructions,
        verbose=verbose,
        output_dir=output_dir,
        dry_run=dry_run,
    )

    if dry_run:
        print_dry_run(config)
        raise typer.Exit(code=0)

    run_dir = run_pipeline(config)

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

    manifest = Manifest.load(manifest_path)
    topic_path = run_dir / "topic.md"
    if not topic_path.exists():
        typer.echo(f"Error: no topic.md found in {run_dir}", err=True)
        raise typer.Exit(code=1)

    topic = topic_path.read_text()

    research_done = manifest.phases["research"].status == PhaseStatus.COMPLETE
    cp_done = manifest.phases["cross_pollination"].status == PhaseStatus.COMPLETE
    synthesis_done = manifest.phases["synthesis"].status == PhaseStatus.COMPLETE

    if research_done and cp_done and synthesis_done:
        typer.echo("All phases already complete.")
        raise typer.Exit(code=0)

    config = RunConfig(
        topic=topic,
        agents=manifest.agents,
        synthesizer=manifest.synthesizer,
        raw=manifest.flags.raw,
        instructions=manifest.flags.instructions,
        verbose=verbose,
        output_dir=run_dir.parent,
    )

    if not research_done:
        manifest = run_phase1(run_dir, config, manifest)

    if not cp_done:
        manifest = run_phase2(run_dir, config, manifest)

    if not synthesis_done:
        manifest = run_phase3(run_dir, config, manifest)

    manifest.save(manifest_path)
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
    typer.echo(f"Topic:              {topic_preview}")
    typer.echo(f"Research:           {manifest.phases['research'].status.value}")
    typer.echo(f"Cross-pollination:  {manifest.phases['cross_pollination'].status.value}")
    typer.echo(f"Synthesis:          {manifest.phases['synthesis'].status.value}")
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

    runs: list[tuple[str, str, str]] = []
    for entry in sorted(output_dir.iterdir()):
        manifest_path = entry / "manifest.json"
        if entry.is_dir() and manifest_path.exists():
            try:
                m = Manifest.load(manifest_path)
                topic_short = m.topic[:60]
                # Overall status: synthesis > cp > research
                if m.phases["synthesis"].status == PhaseStatus.COMPLETE:
                    overall = "complete"
                elif m.phases["cross_pollination"].status == PhaseStatus.COMPLETE:
                    overall = "synthesis pending"
                elif m.phases["research"].status == PhaseStatus.COMPLETE:
                    overall = "cross-pollination pending"
                else:
                    overall = m.phases["research"].status.value
                runs.append((m.run_id, topic_short, overall))
            except Exception:
                runs.append((entry.name, "(error reading manifest)", "unknown"))

    if not runs:
        typer.echo("No runs found.")
        raise typer.Exit(code=0)

    # Simple table
    typer.echo(f"{'Run ID':<30} {'Status':<26} {'Topic'}")
    typer.echo("-" * 90)
    for run_id, topic_short, overall in runs:
        typer.echo(f"{run_id:<30} {overall:<26} {topic_short}")


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
