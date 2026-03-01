"""Phase orchestration engine for ivory-tower research pipeline."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    t0 = time.monotonic()
    run_counselors(
        prompt_file=prompt_file,
        agents=[agent],
        output_dir=phase2_dir,
        verbose=config.verbose,
    )
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
    """Run the full 3-phase research pipeline. Returns path to run directory."""
    run_id = generate_run_id()
    run_dir = create_run_directory(config.output_dir, run_id)

    manifest = create_initial_manifest(
        run_id=run_id,
        topic=config.topic,
        agents=config.agents,
        synthesizer=config.synthesizer,
        flags=Flags(
            raw=config.raw,
            instructions=config.instructions,
            verbose=config.verbose,
        ),
    )

    # Save topic
    (run_dir / "topic.md").write_text(config.topic)

    # Save initial manifest
    manifest.save(run_dir / "manifest.json")

    t0 = time.monotonic()

    manifest = run_phase1(run_dir, config, manifest)
    manifest = run_phase2(run_dir, config, manifest)
    manifest = run_phase3(run_dir, config, manifest)

    manifest.total_duration_seconds = time.monotonic() - t0
    manifest.save(run_dir / "manifest.json")

    return run_dir


# ---------------------------------------------------------------------------
# Dry Run
# ---------------------------------------------------------------------------


def resume_pipeline(run_dir: Path, verbose: bool = False) -> Path:
    """Resume a partially-completed pipeline run.

    Loads manifest from run_dir, determines which phases are done,
    and runs the remaining ones. Returns run_dir.
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in {run_dir}")

    manifest = Manifest.load(manifest_path)
    topic = (run_dir / "topic.md").read_text()

    config = RunConfig(
        topic=topic,
        agents=manifest.agents,
        synthesizer=manifest.synthesizer,
        raw=manifest.flags.raw,
        instructions=manifest.flags.instructions,
        verbose=verbose,
        output_dir=run_dir.parent,
    )

    research_done = manifest.phases["research"].status == PhaseStatus.COMPLETE
    cp_done = manifest.phases["cross_pollination"].status == PhaseStatus.COMPLETE
    synthesis_done = manifest.phases["synthesis"].status == PhaseStatus.COMPLETE

    if research_done and cp_done and synthesis_done:
        return run_dir

    t0 = time.monotonic()

    if not research_done:
        manifest = run_phase1(run_dir, config, manifest)

    if not cp_done:
        manifest = run_phase2(run_dir, config, manifest)

    if not synthesis_done:
        manifest = run_phase3(run_dir, config, manifest)

    manifest.total_duration_seconds = time.monotonic() - t0
    manifest.save(manifest_path)

    return run_dir


def print_dry_run(config: RunConfig) -> None:
    """Print execution plan without running anything."""
    prompt_preview = build_research_prompt(
        config.topic, instructions=config.instructions, raw=config.raw
    )
    preview = prompt_preview[:200]

    n = len(config.agents)
    phase2_sessions = n * (n - 1)

    print("=== Dry Run: Execution Plan ===")
    print()
    print(f"Topic: {config.topic}")
    print()
    print(f"Agents ({n}): {', '.join(config.agents)}")
    print(f"Synthesizer: {config.synthesizer}")
    print()
    print("Phases:")
    print(f"  1. Research: {n} agents research independently")
    print(f"  2. Cross-Pollination: {phase2_sessions} refinement sessions")
    print(f"  3. Synthesis: {config.synthesizer} produces final report")
    print()
    print(f"Prompt Preview (first 200 chars):")
    print(f"  {preview}")
