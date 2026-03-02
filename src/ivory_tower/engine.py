"""Phase orchestration engine for ivory-tower research pipeline.

This module provides the high-level pipeline entry points (run_pipeline,
resume_pipeline, print_dry_run) and RunConfig.  Actual phase execution is
delegated to strategy implementations in ivory_tower.strategies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ivory_tower.log import fmt_phase, fmt_ok, fmt_duration, fmt_agent, fmt_bullet, console
from ivory_tower.models import Manifest
from ivory_tower.run import create_run_directory, generate_run_id
from ivory_tower.strategies import get_strategy

logger = logging.getLogger(__name__)


@dataclass
class RunConfig:
    topic: str
    agents: list[str]
    synthesizer: str
    raw: bool = False
    instructions: str | None = None
    verbose: bool = False
    output_dir: Path = field(default_factory=lambda: Path("./research"))
    dry_run: bool = False
    strategy: str = "council"
    max_rounds: int = 10
    sandbox_backend: str = "none"
    parse_agent: str | None = None
    template: str | None = None
    rounds: int | None = None
    red_team: list[str] | None = None
    blue_team: list[str] | None = None


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(config: RunConfig) -> Path:
    """Run a research pipeline using the configured strategy.

    Delegates to the strategy's run() method. Returns path to run directory.
    """
    strategy = get_strategy(config.strategy)

    logger.info(
        fmt_phase("Research Pipeline"),
    )
    logger.info(
        fmt_bullet("Strategy: [phase]%s[/phase]"),
        config.strategy,
    )
    agents_str = ", ".join(fmt_agent(a) for a in config.agents)
    logger.info(
        fmt_bullet("Agents: %s"),
        agents_str,
    )
    logger.info(
        fmt_bullet("Synthesizer: %s"),
        fmt_agent(config.synthesizer),
    )
    topic_preview = config.topic[:100] + ("..." if len(config.topic) > 100 else "")
    logger.info(
        fmt_bullet('Topic: [dim]"%s"[/dim]'),
        topic_preview,
    )

    # Validate config
    errors = strategy.validate(config)
    if errors:
        raise ConfigError("; ".join(errors))

    run_id = generate_run_id()
    run_dir = create_run_directory(config.output_dir, run_id)

    logger.info(
        fmt_bullet("Run ID: [dim]%s[/dim]"),
        run_id,
    )

    manifest = strategy.create_manifest(config, run_id)

    # Save topic
    (run_dir / "topic.md").write_text(config.topic)

    # Save initial manifest
    manifest.save(run_dir / "manifest.json")

    strategy.run(run_dir, config, manifest)

    logger.info("")  # blank line separator

    return run_dir


class ConfigError(Exception):
    """Raised when a run configuration is invalid."""


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


def resume_pipeline(run_dir: Path, verbose: bool = False) -> Path:
    """Resume a partially-completed pipeline run.

    Reads strategy from manifest and dispatches to the appropriate strategy.
    Returns run_dir.
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in {run_dir}")

    manifest = Manifest.load(manifest_path)
    topic = (run_dir / "topic.md").read_text()

    strategy = get_strategy(manifest.strategy)

    logger.info(
        fmt_phase("Resuming Pipeline"),
    )
    logger.info(
        fmt_bullet("Run directory: [dim]%s[/dim]"),
        str(run_dir),
    )

    config = RunConfig(
        topic=topic,
        agents=manifest.agents,
        synthesizer=manifest.synthesizer,
        raw=manifest.flags.raw,
        instructions=manifest.flags.instructions,
        verbose=verbose,
        output_dir=run_dir.parent,
        strategy=manifest.strategy,
        max_rounds=manifest.flags.max_rounds,
        parse_agent=manifest.flags.parse_agent,
    )

    strategy.resume(run_dir, config, manifest)

    return run_dir


def print_dry_run(config: RunConfig) -> None:
    """Print execution plan without running anything.

    Delegates to the strategy's dry_run() method.
    """
    strategy = get_strategy(config.strategy)
    strategy.dry_run(config)
