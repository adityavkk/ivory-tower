"""Run ID generation and directory setup for ivory-tower."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

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


def generate_run_id() -> str:
    """Return a run ID in format YYYYMMDD-HHMMSS-hex6."""
    now = datetime.now(timezone.utc)
    hex6 = secrets.token_hex(3)  # 3 bytes = 6 hex chars
    return f"{now:%Y%m%d-%H%M%S}-{hex6}"


def create_run_directory(base_dir: Path, run_id: str) -> Path:
    """Create the full run directory structure and return the run dir path."""
    run_dir = base_dir / run_id
    for subdir in ("phase1", "phase2", "phase3", "logs"):
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)
    return run_dir


def create_initial_manifest(
    run_id: str,
    topic: str,
    agents: list[str],
    synthesizer: str,
    flags: Flags,
) -> Manifest:
    """Create a Manifest with all phases in pending status."""
    # Research: one AgentResult per agent
    research_agents = {
        agent: AgentResult(
            status=PhaseStatus.PENDING,
            output=f"phase1/{agent}-report.md",
        )
        for agent in agents
    }

    # Cross-pollination: N*(N-1) sessions
    sessions: dict[str, CrossPollinationSession] = {}
    for agent in agents:
        for peer in agents:
            if agent == peer:
                continue
            key = f"{agent}-cross-{peer}"
            sessions[key] = CrossPollinationSession(
                status=PhaseStatus.PENDING,
                output=f"phase2/{key}.md",
            )

    return Manifest(
        run_id=run_id,
        topic=topic,
        agents=agents,
        synthesizer=synthesizer,
        flags=flags,
        phases={
            "research": ResearchPhase(
                status=PhaseStatus.PENDING,
                agents=research_agents,
            ),
            "cross_pollination": CrossPollinationPhase(
                status=PhaseStatus.PENDING,
                sessions=sessions,
            ),
            "synthesis": SynthesisPhase(
                status=PhaseStatus.PENDING,
                agent=synthesizer,
                output="phase3/final-report.md",
            ),
        },
        total_duration_seconds=None,
    )
