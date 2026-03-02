"""CLI interface for ivory-tower multi-agent research orchestrator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from ivory_tower.log import setup_logging
from ivory_tower.agents import validate_agent_configs
from ivory_tower.engine import (
    ConfigError,
    RunConfig,
    print_dry_run,
    resume_pipeline,
    run_pipeline,
)
from ivory_tower.models import Manifest, PhaseStatus
from ivory_tower.profiles import AgentProfile, list_profiles
from ivory_tower.sandbox import PROVIDERS, get_provider
from ivory_tower.strategies import STRATEGIES, get_strategy, list_strategies as _list_strategies
from ivory_tower.templates import list_templates, load_template, validate_template

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
    stream: Annotated[
        bool, typer.Option("--stream", help="Show live agent output as it streams")
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
    parse_agent: Annotated[
        Optional[str],
        typer.Option(
            "--parse-agent",
            help="Agent to use as structured-output fallback when judge JSON parsing fails (adversarial only)",
        ),
    ] = None,
    sandbox: Annotated[
        str,
        typer.Option("--sandbox", help="Sandbox backend (none, local, agentfs, daytona)"),
    ] = "none",
    template: Annotated[
        Optional[str],
        typer.Option("--template", "-t", help="Strategy template (built-in name or YAML path)"),
    ] = None,
    rounds: Annotated[
        Optional[int],
        typer.Option("--rounds", help="Number of rounds for iterative phases"),
    ] = None,
    red_team: Annotated[
        Optional[str],
        typer.Option("--red-team", help="Comma-separated agent specs for red team"),
    ] = None,
    blue_team: Annotated[
        Optional[str],
        typer.Option("--blue-team", help="Comma-separated agent specs for blue team"),
    ] = None,
) -> None:
    """Run a multi-agent deep research pipeline on a topic."""
    # -- sandbox validation --
    if sandbox != "none":
        if sandbox not in PROVIDERS:
            available = ", ".join(sorted(PROVIDERS.keys()))
            typer.echo(
                f"Unknown sandbox backend '{sandbox}'. Available: {available}",
                err=True,
            )
            raise typer.Exit(code=1)
        try:
            get_provider(sandbox)
        except RuntimeError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1)

    # -- template support --
    resolved_strategy = strategy
    if template is not None:
        try:
            tmpl = load_template(template)
        except FileNotFoundError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)
        errors = validate_template(tmpl)
        if errors:
            typer.echo("Template validation errors:", err=True)
            for err in errors:
                typer.echo(f"  - {err}", err=True)
            raise typer.Exit(code=1)
        # Template's strategy name overrides --strategy
        resolved_strategy = tmpl.name

    # -- validate strategy --
    try:
        get_strategy(resolved_strategy)
    except ValueError:
        available = ", ".join(name for name, _ in _list_strategies())
        typer.echo(
            f"Unknown strategy '{resolved_strategy}'. Available: {available}",
            err=True,
        )
        raise typer.Exit(code=1)

    # -- warn if --max-rounds used with council --
    if max_rounds != 10 and resolved_strategy == "council":
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

    # -- parse agent specs (support @profile-name, model:role, model) --
    agent_specs = [a.strip() for a in agents.split(",")]
    agent_list = []
    for spec in agent_specs:
        profile = AgentProfile.from_cli_shorthand(spec)
        agent_list.append(profile.model or profile.name)

    # -- validate agent configs --
    all_agents = agent_list + [synthesizer]
    if parse_agent is not None:
        all_agents.append(parse_agent)
    invalid = validate_agent_configs(all_agents)
    if invalid:
        from ivory_tower.agents import AGENTS_DIR

        typer.echo(
            f"Error: no agent config for: {', '.join(invalid)}\n"
            f"Add YAML configs to {AGENTS_DIR}/ or run 'ivory migrate' to import from counselors.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Configure logging
    setup_logging(verbose=verbose)

    # -- parse team specs --
    parsed_red_team: list[str] | None = None
    if red_team is not None:
        parsed_red_team = [
            (AgentProfile.from_cli_shorthand(s.strip()).model
             or AgentProfile.from_cli_shorthand(s.strip()).name)
            for s in red_team.split(",")
        ]

    parsed_blue_team: list[str] | None = None
    if blue_team is not None:
        parsed_blue_team = [
            (AgentProfile.from_cli_shorthand(s.strip()).model
             or AgentProfile.from_cli_shorthand(s.strip()).name)
            for s in blue_team.split(",")
        ]

    config = RunConfig(
        topic=resolved_topic,
        agents=agent_list,
        synthesizer=synthesizer,
        raw=raw,
        instructions=instructions,
        verbose=verbose,
        output_dir=output_dir,
        dry_run=dry_run,
        strategy=resolved_strategy,
        max_rounds=max_rounds,
        parse_agent=parse_agent,
        sandbox_backend=sandbox,
        template=template,
        rounds=rounds,
        red_team=parsed_red_team,
        blue_team=parsed_blue_team,
        stream=stream,
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


# ---------------------------------------------------------------------------
# ivory templates
# ---------------------------------------------------------------------------


@app.command()
def templates() -> None:
    """List available strategy templates (built-in + user-defined)."""
    from rich.console import Console
    from rich.table import Table

    items = list_templates()
    table = Table(title="Strategy Templates")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Source")

    for name, description, source in items:
        table.add_row(name, description, source)

    if not items:
        typer.echo("No templates found.")
        raise typer.Exit(code=0)

    console = Console()
    console.print(table)


# ---------------------------------------------------------------------------
# ivory profiles
# ---------------------------------------------------------------------------


@app.command()
def profiles() -> None:
    """List available agent profiles from ~/.ivory-tower/profiles/."""
    from rich.console import Console
    from rich.table import Table

    items = list_profiles()
    table = Table(title="Agent Profiles")
    table.add_column("Name", style="bold")
    table.add_column("Role")
    table.add_column("Model")

    for name, role, model in items:
        table.add_row(name, role, model)

    if not items:
        typer.echo("No profiles found. Add YAML files to ~/.ivory-tower/profiles/")
        raise typer.Exit(code=0)

    console = Console()
    console.print(table)


# ---------------------------------------------------------------------------
# ivory agents
# ---------------------------------------------------------------------------


@app.command()
def agents(
    check: Annotated[
        Optional[str],
        typer.Argument(help="Agent name to check ACP connectivity"),
    ] = None,
) -> None:
    """List configured agents from ~/.ivory-tower/agents/ or check one."""
    from rich.console import Console
    from rich.table import Table

    from ivory_tower.agents import AGENTS_DIR, load_agents, resolve_agent_binary

    if check is not None:
        # Check a specific agent
        from ivory_tower.agents import load_agent

        try:
            config = load_agent(check)
        except FileNotFoundError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)

        try:
            binary = resolve_agent_binary(config)
            typer.echo(
                f"{config.name}: OK ({config.protocol}, "
                f"binary={binary})"
            )
        except FileNotFoundError:
            typer.echo(
                f"{config.name}: FAIL (binary '{config.command}' not found on PATH)",
                err=True,
            )
            raise typer.Exit(code=1)
        return

    # List all agents
    all_agents = load_agents()
    if not all_agents:
        typer.echo(
            f"No agents configured. Add YAML files to {AGENTS_DIR}/"
        )
        raise typer.Exit(code=0)

    table = Table(title="Configured Agents")
    table.add_column("Name", style="bold")
    table.add_column("Protocol")
    table.add_column("Command")
    table.add_column("Binary")

    for name, config in sorted(all_agents.items()):
        try:
            binary = str(resolve_agent_binary(config))
        except FileNotFoundError:
            binary = "(not found)"
        table.add_row(name, config.protocol, config.command, binary)

    console = Console()
    console.print(table)


# ---------------------------------------------------------------------------
# ivory migrate
# ---------------------------------------------------------------------------


@app.command()
def migrate() -> None:
    """Import agents from counselors into ~/.ivory-tower/agents/ as YAML configs."""
    from ivory_tower.agents import AGENTS_DIR, load_agents

    try:
        from ivory_tower.counselors import list_available_agents, resolve_counselors_cmd
    except ImportError:
        typer.echo(
            "Error: counselors is not installed. Install it to use migrate.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        resolve_counselors_cmd()
    except Exception as exc:
        typer.echo(f"Error: could not find counselors: {exc}", err=True)
        raise typer.Exit(code=1)

    available = list_available_agents()
    if not available:
        typer.echo("No agents found in counselors.")
        raise typer.Exit(code=0)

    existing = load_agents()
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0

    for name in available:
        if name in existing:
            typer.echo(f"  skip: {name} (already configured)")
            skipped += 1
            continue

        config_path = AGENTS_DIR / f"{name}.yml"
        config_path.write_text(
            f"name: {name}\n"
            f"command: counselors\n"
            f"args:\n"
            f"  - run\n"
            f"  - --tools\n"
            f"  - \"{name}\"\n"
            f"protocol: counselors\n"
        )
        typer.echo(f"  created: {config_path}")
        created += 1

    typer.echo(f"\nMigrated {created} agent(s), skipped {skipped}.")


# ---------------------------------------------------------------------------
# ivory audit
# ---------------------------------------------------------------------------


@app.command()
def audit(
    run_dir: Annotated[Path, typer.Argument(help="Path to run directory")],
    agent: Annotated[
        Optional[str], typer.Argument(help="Agent name to filter")
    ] = None,
) -> None:
    """Query AgentFS tool call audit trail for a run."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        typer.echo(f"Error: no manifest.json found in {run_dir}", err=True)
        raise typer.Exit(code=1)

    manifest = Manifest.load(manifest_path)

    typer.echo(f"Run ID:    {manifest.run_id}")
    typer.echo(f"Strategy:  {manifest.strategy}")

    if manifest.sandbox_config:
        backend = manifest.sandbox_config.get("backend", "none")
        typer.echo(f"Sandbox:   {backend}")
    else:
        typer.echo("Sandbox:   none")

    if agent:
        typer.echo(f"Agent:     {agent}")

    typer.echo("")
    typer.echo("Full AgentFS audit query requires the agentfs package.")
    typer.echo("Install: curl -fsSL https://agentfs.ai/install | bash")
