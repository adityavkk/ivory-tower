"""Phase orchestration engine for ivory-tower research pipeline.

This module provides the high-level pipeline entry points (run_pipeline,
resume_pipeline, print_dry_run) and RunConfig.  Actual phase execution is
delegated to strategy implementations in ivory_tower.strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ivory_tower.models import Manifest
from ivory_tower.run import create_run_directory, generate_run_id
from ivory_tower.strategies import get_strategy


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


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(config: RunConfig) -> Path:
    """Run a research pipeline using the configured strategy.

    Delegates to the strategy's run() method. Returns path to run directory.
    """
    strategy = get_strategy(config.strategy)

    # Validate config
    errors = strategy.validate(config)
    if errors:
        raise ConfigError("; ".join(errors))

    run_id = generate_run_id()
    run_dir = create_run_directory(config.output_dir, run_id)

    manifest = strategy.create_manifest(config, run_id)

    # Save topic
    (run_dir / "topic.md").write_text(config.topic)

    # Save initial manifest
    manifest.save(run_dir / "manifest.json")

    strategy.run(run_dir, config, manifest)

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
    )

    strategy.resume(run_dir, config, manifest)

    return run_dir


def print_dry_run(config: RunConfig) -> None:
    """Print execution plan without running anything.

    Delegates to the strategy's dry_run() method.
    """
    strategy = get_strategy(config.strategy)
    strategy.dry_run(config)
