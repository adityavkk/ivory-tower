"""Phase orchestration engine for ivory-tower research pipeline."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import shutil

from ivory_tower.counselors import CounselorsError, run_counselors
from ivory_tower.models import (
    AgentResult,
    CrossPollinationPhase,
    CrossPollinationSession,
    Flags,
    Manifest,
    PhaseStatus,
    ResearchPhase,
    SynthesisPhase,
)
from ivory_tower.prompts import (
    build_refinement_prompt,
    build_research_prompt,
    build_synthesis_prompt,
)
from ivory_tower.run import create_initial_manifest, create_run_directory, generate_run_id
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_counselors_output(
    output_dir: Path, agents: list[str], suffix: str = "-report.md"
) -> None:
    """Copy agent outputs from counselors slug subdirectory to expected paths.

    counselors writes: ``output_dir/<slug>/<agent>.md``
    The engine expects: ``output_dir/<agent><suffix>``

    Finds the most-recently-created slug subdirectory and copies each agent's
    ``.md`` file to the expected location.
    """
    # Find the slug subdirectory (there should be exactly one new one)
    slug_dirs = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not slug_dirs:
        return

    slug_dir = slug_dirs[0]

    for agent in agents:
        src = slug_dir / f"{agent}.md"
        dst = output_dir / f"{agent}{suffix}"
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Phase 1: Independent Research
# ---------------------------------------------------------------------------


def run_phase1(run_dir: Path, config: RunConfig, manifest: Manifest) -> Manifest:
    """Execute Phase 1: independent research by all agents."""
    research: ResearchPhase = manifest.phases["research"]  # type: ignore[assignment]
    research.status = PhaseStatus.RUNNING
    research.started_at = _now_iso()

    # Build and write research prompt
    prompt_text = build_research_prompt(
        config.topic, instructions=config.instructions, raw=config.raw
    )
    prompt_file = run_dir / "research-prompt.md"
    prompt_file.write_text(prompt_text)

    phase1_dir = run_dir / "phase1"
    phase1_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    try:
        run_counselors(
            prompt_file=prompt_file,
            agents=config.agents,
            output_dir=phase1_dir,
            verbose=config.verbose,
        )
    except CounselorsError:
        research.status = PhaseStatus.FAILED
        research.completed_at = _now_iso()
        research.duration_seconds = time.monotonic() - t0
        manifest.save(run_dir / "manifest.json")
        raise

    # Normalize counselors output: copy <slug>/<agent>.md -> <agent>-report.md
    _normalize_counselors_output(phase1_dir, config.agents, suffix="-report.md")

    elapsed = time.monotonic() - t0
    research.status = PhaseStatus.COMPLETE
    research.completed_at = _now_iso()
    research.duration_seconds = elapsed

    # Populate per-agent results
    for agent in config.agents:
        output_rel = f"phase1/{agent}-report.md"
        research.agents[agent] = AgentResult(
            status=PhaseStatus.COMPLETE,
            duration_seconds=elapsed,
            output=output_rel,
        )

    manifest.save(run_dir / "manifest.json")
    return manifest


# ---------------------------------------------------------------------------
# Phase 2: Cross-Pollination
# ---------------------------------------------------------------------------


def _run_single_refinement(
    run_dir: Path,
    config: RunConfig,
    agent: str,
    peer: str,
) -> tuple[str, float]:
    """Run one refinement session: agent reviews peer's report.

    Returns (session_key, duration_seconds).
    """
    phase1_dir = run_dir / "phase1"
    phase2_dir = run_dir / "phase2"
    phase2_dir.mkdir(parents=True, exist_ok=True)

    own_report = (phase1_dir / f"{agent}-report.md").read_text()
    peer_report = (phase1_dir / f"{peer}-report.md").read_text()

    prompt_text = build_refinement_prompt(
        config.topic, own_report, peer_report, peer
    )

    session_key = f"{agent}-cross-{peer}"
    prompt_file = run_dir / "phase2" / f"{session_key}-prompt.md"
    prompt_file.write_text(prompt_text)

    # Use a dedicated subdirectory per session so slug dirs don't collide
    session_out_dir = phase2_dir / f"{session_key}-out"
    session_out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    run_counselors(
        prompt_file=prompt_file,
        agents=[agent],
        output_dir=session_out_dir,
        verbose=config.verbose,
    )

    # Copy agent output from counselors slug subdir -> phase2/<session_key>.md
    _normalize_counselors_output(session_out_dir, [agent], suffix=".md")
    agent_out = session_out_dir / f"{agent}.md"
    final_out = phase2_dir / f"{session_key}.md"
    if agent_out.exists() and not final_out.exists():
        shutil.copy2(agent_out, final_out)

    return session_key, time.monotonic() - t0


def run_phase2(run_dir: Path, config: RunConfig, manifest: Manifest) -> Manifest:
    """Execute Phase 2: cross-pollination refinements for all agent pairs."""
    cp: CrossPollinationPhase = manifest.phases["cross_pollination"]  # type: ignore[assignment]
    cp.status = PhaseStatus.RUNNING
    cp.started_at = _now_iso()

    t0 = time.monotonic()

    # Build all (agent, peer) pairs
    pairs = [
        (agent, peer)
        for agent in config.agents
        for peer in config.agents
        if agent != peer
    ]

    # Run concurrently
    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_run_single_refinement, run_dir, config, agent, peer): (agent, peer)
            for agent, peer in pairs
        }
        for future in as_completed(futures):
            session_key, duration = future.result()
            cp.sessions[session_key] = CrossPollinationSession(
                status=PhaseStatus.COMPLETE,
                duration_seconds=duration,
                output=f"phase2/{session_key}.md",
            )

    elapsed = time.monotonic() - t0
    cp.status = PhaseStatus.COMPLETE
    cp.completed_at = _now_iso()
    cp.duration_seconds = elapsed

    manifest.save(run_dir / "manifest.json")
    return manifest


# ---------------------------------------------------------------------------
# Phase 3: Synthesis
# ---------------------------------------------------------------------------


def run_phase3(run_dir: Path, config: RunConfig, manifest: Manifest) -> Manifest:
    """Execute Phase 3: synthesis of all refinement reports."""
    sp: SynthesisPhase = manifest.phases["synthesis"]  # type: ignore[assignment]
    sp.status = PhaseStatus.RUNNING
    sp.started_at = _now_iso()

    phase2_dir = run_dir / "phase2"
    phase3_dir = run_dir / "phase3"
    phase3_dir.mkdir(parents=True, exist_ok=True)

    # Read all refinement files (exclude prompt files)
    refinement_files = sorted(
        f for f in phase2_dir.iterdir()
        if f.suffix == ".md" and not f.name.endswith("-prompt.md")
    )

    all_reports_parts = []
    for f in refinement_files:
        all_reports_parts.append(f"### {f.stem}\n\n{f.read_text()}")
    all_reports = "\n\n---\n\n".join(all_reports_parts)

    prompt_text = build_synthesis_prompt(
        config.topic, len(config.agents), all_reports
    )
    prompt_file = run_dir / "phase3" / "synthesis-prompt.md"
    prompt_file.write_text(prompt_text)

    t0 = time.monotonic()
    run_counselors(
        prompt_file=prompt_file,
        agents=[config.synthesizer],
        output_dir=phase3_dir,
        verbose=config.verbose,
    )

    # Normalize: copy synthesizer output -> final-report.md
    _normalize_counselors_output(phase3_dir, [config.synthesizer], suffix=".md")
    synth_out = phase3_dir / f"{config.synthesizer}.md"
    final_report = phase3_dir / "final-report.md"
    if synth_out.exists() and not final_report.exists():
        shutil.copy2(synth_out, final_report)

    elapsed = time.monotonic() - t0

    sp.status = PhaseStatus.COMPLETE
    sp.completed_at = _now_iso()
    sp.duration_seconds = elapsed

    manifest.save(run_dir / "manifest.json")
    return manifest


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
# Dry Run
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
