"""Council strategy: the original 3-phase multi-agent research pipeline.

Uses the AgentExecutor protocol for agent invocation. Each agent is invoked
via its configured executor (ACP, headless, or legacy counselors) through
a per-agent sandbox. Agent output is captured from AgentOutput.raw_output --
no filesystem-convention scraping.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ivory_tower.executor import get_executor, get_executor_for_agent
from ivory_tower.executor.types import AgentExecutor, AgentOutput
from ivory_tower.log import (
    SYM_OK,
    create_agent_progress,
    fmt_agent,
    fmt_bullet,
    fmt_duration,
    fmt_ok,
    fmt_phase,
    phase_spinner,
)
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
from ivory_tower.sandbox import get_provider
from ivory_tower.sandbox.types import Sandbox, SandboxConfig

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_executor(agent_name: str) -> AgentExecutor:
    """Get the executor for an agent, falling back to counselors if no config.

    Tries to load the agent config from ~/.ivory-tower/agents/<name>.yml
    and returns the appropriate executor. If no config exists, falls back
    to the legacy CounselorsExecutor.
    """
    try:
        return get_executor_for_agent(agent_name)
    except FileNotFoundError:
        logger.debug(
            "No agent config for '%s', falling back to counselors executor",
            agent_name,
        )
        return get_executor("counselors")


def _create_sandbox(
    run_dir: Path, agent_name: str, run_id: str, backend: str = "none",
) -> Sandbox:
    """Create a sandbox for an agent in the given run directory."""
    provider = get_provider(backend)
    config = SandboxConfig(backend=backend)
    return provider.create_sandbox(
        agent_name=agent_name,
        run_id=run_id,
        run_dir=run_dir,
        config=config,
    )


def _run_agent(
    executor: AgentExecutor,
    sandbox: Sandbox,
    agent_name: str,
    prompt: str,
    output_dir: str,
    verbose: bool = False,
    **kwargs: Any,
) -> AgentOutput:
    """Run an agent through the executor and return its output.

    Wraps executor.run() with consistent parameters. The executor handles
    all protocol-specific details (ACP lifecycle, headless parsing, etc.).
    Extra kwargs (e.g. session_id, on_chunk) are forwarded to the executor.
    """
    return executor.run(
        sandbox=sandbox,
        agent_name=agent_name,
        prompt=prompt,
        output_dir=output_dir,
        verbose=verbose,
        **kwargs,
    )


class CouncilStrategy:
    """Multi-agent research with cross-pollination and synthesis."""

    name: str = "council"
    description: str = "Multi-agent research with cross-pollination and synthesis"

    def validate(self, config: Any) -> list[str]:
        """Validate config for council strategy."""
        errors: list[str] = []
        if len(config.agents) < 2:
            errors.append("Council strategy requires at least 2 agents.")
        if not config.synthesizer:
            errors.append("Synthesizer agent is required.")
        return errors

    def create_manifest(self, config: Any, run_id: str) -> Manifest:
        """Create initial manifest with council-shaped phases."""
        research_agents = {
            agent: AgentResult(
                status=PhaseStatus.PENDING,
                output=f"phase1/{agent}-report.md",
            )
            for agent in config.agents
        }

        sessions: dict[str, CrossPollinationSession] = {}
        for agent in config.agents:
            key = f"{agent}-refined"
            sessions[key] = CrossPollinationSession(
                status=PhaseStatus.PENDING,
                output=f"phase2/{key}.md",
            )

        return Manifest(
            run_id=run_id,
            topic=config.topic,
            agents=config.agents,
            synthesizer=config.synthesizer,
            flags=Flags(
                raw=config.raw,
                instructions=config.instructions,
                verbose=config.verbose,
                max_rounds=getattr(config, "max_rounds", 10),
            ),
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
                    agent=config.synthesizer,
                    output="phase3/final-report.md",
                ),
            },
            strategy="council",
        )

    def run(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute the full council pipeline: research, cross-pollination, synthesis."""
        logger.info("")  # blank separator
        t0 = time.monotonic()

        manifest = self._run_phase1(run_dir, config, manifest)
        manifest = self._run_phase2(run_dir, config, manifest)
        manifest = self._run_phase3(run_dir, config, manifest)

        manifest.total_duration_seconds = time.monotonic() - t0

        logger.info("")
        logger.info(
            fmt_ok("Council pipeline complete [duration](%s)[/duration]"),
            fmt_duration(manifest.total_duration_seconds),
        )

        manifest.save(run_dir / "manifest.json")
        return manifest

    def resume(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Resume a partially-completed council run."""
        research_done = manifest.phases["research"].status == PhaseStatus.COMPLETE
        cp_done = manifest.phases["cross_pollination"].status == PhaseStatus.COMPLETE
        synthesis_done = manifest.phases["synthesis"].status == PhaseStatus.COMPLETE

        if research_done and cp_done and synthesis_done:
            return manifest

        t0 = time.monotonic()

        if not research_done:
            manifest = self._run_phase1(run_dir, config, manifest)

        if not cp_done:
            manifest = self._run_phase2(run_dir, config, manifest)

        if not synthesis_done:
            manifest = self._run_phase3(run_dir, config, manifest)

        manifest.total_duration_seconds = time.monotonic() - t0
        manifest.save(run_dir / "manifest.json")
        return manifest

    def dry_run(self, config: Any) -> None:
        """Print council execution plan."""
        prompt_preview = build_research_prompt(
            config.topic, instructions=config.instructions, raw=config.raw
        )
        preview = prompt_preview[:200]

        n = len(config.agents)

        print("=== Dry Run: Execution Plan ===")
        print()
        print(f"Topic: {config.topic}")
        print()
        print(f"Agents ({n}): {', '.join(config.agents)}")
        print(f"Synthesizer: {config.synthesizer}")
        print()
        print("Phases:")
        print(f"  1. Research: {n} agents research independently")
        print(f"  2. Cross-Pollination: {n} agents refine reports (each reviews all peers)")
        print(f"  3. Synthesis: {config.synthesizer} produces final report")
        print()
        print(f"Prompt Preview (first 200 chars):")
        print(f"  {preview}")

    def format_status(self, manifest: Manifest) -> list[tuple[str, str]]:
        """Return status tuples for each council phase."""
        return [
            ("Research", manifest.phases["research"].status.value),
            ("Cross-pollination", manifest.phases["cross_pollination"].status.value),
            ("Synthesis", manifest.phases["synthesis"].status.value),
        ]

    def phases_to_dict(self, phases: dict) -> dict:
        """Serialize council phases to dict."""
        rp = phases["research"]
        assert isinstance(rp, ResearchPhase)
        research_dict = {
            "status": rp.status.value,
            "started_at": rp.started_at,
            "completed_at": rp.completed_at,
            "duration_seconds": rp.duration_seconds,
            "agents": {
                name: {
                    "status": ar.status.value,
                    "duration_seconds": ar.duration_seconds,
                    "output": ar.output,
                }
                for name, ar in rp.agents.items()
            },
        }

        cp = phases["cross_pollination"]
        assert isinstance(cp, CrossPollinationPhase)
        cp_dict = {
            "status": cp.status.value,
            "started_at": cp.started_at,
            "completed_at": cp.completed_at,
            "duration_seconds": cp.duration_seconds,
            "sessions": {
                name: {
                    "status": s.status.value,
                    "duration_seconds": s.duration_seconds,
                    "output": s.output,
                }
                for name, s in cp.sessions.items()
            },
        }

        sp = phases["synthesis"]
        assert isinstance(sp, SynthesisPhase)
        synthesis_dict = {
            "status": sp.status.value,
            "started_at": sp.started_at,
            "completed_at": sp.completed_at,
            "duration_seconds": sp.duration_seconds,
            "agent": sp.agent,
            "output": sp.output,
        }

        return {
            "research": research_dict,
            "cross_pollination": cp_dict,
            "synthesis": synthesis_dict,
        }

    def phases_from_dict(self, data: dict) -> dict:
        """Deserialize council phases from dict."""
        rp_d = data["research"]
        research = ResearchPhase(
            status=PhaseStatus(rp_d["status"]),
            started_at=rp_d.get("started_at"),
            completed_at=rp_d.get("completed_at"),
            duration_seconds=rp_d.get("duration_seconds"),
            agents={
                name: AgentResult(
                    status=PhaseStatus(ar["status"]),
                    duration_seconds=ar.get("duration_seconds"),
                    output=ar["output"],
                )
                for name, ar in rp_d.get("agents", {}).items()
            },
        )

        cp_d = data["cross_pollination"]
        cross_pollination = CrossPollinationPhase(
            status=PhaseStatus(cp_d["status"]),
            started_at=cp_d.get("started_at"),
            completed_at=cp_d.get("completed_at"),
            duration_seconds=cp_d.get("duration_seconds"),
            sessions={
                name: CrossPollinationSession(
                    status=PhaseStatus(s["status"]),
                    duration_seconds=s.get("duration_seconds"),
                    output=s["output"],
                )
                for name, s in cp_d.get("sessions", {}).items()
            },
        )

        sp_d = data["synthesis"]
        synthesis = SynthesisPhase(
            status=PhaseStatus(sp_d["status"]),
            agent=sp_d["agent"],
            output=sp_d["output"],
            started_at=sp_d.get("started_at"),
            completed_at=sp_d.get("completed_at"),
            duration_seconds=sp_d.get("duration_seconds"),
        )

        return {
            "research": research,
            "cross_pollination": cross_pollination,
            "synthesis": synthesis,
        }

    # -- Private phase execution methods --

    def _run_phase1(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute Phase 1: independent research by all agents.

        Each agent receives the research prompt and produces a report.
        Agents run concurrently via ThreadPoolExecutor, each through its
        own executor and sandbox.
        """
        research: ResearchPhase = manifest.phases["research"]
        research.status = PhaseStatus.RUNNING
        research.started_at = _now_iso()

        agents_str = ", ".join(fmt_agent(a) for a in config.agents)
        logger.info(fmt_phase("Phase 1 -- Independent Research"))
        logger.info(fmt_bullet("Agents: %s"), agents_str)

        prompt_text = build_research_prompt(
            config.topic, instructions=config.instructions, raw=config.raw
        )
        prompt_file = run_dir / "research-prompt.md"
        prompt_file.write_text(prompt_text)

        phase1_dir = run_dir / "phase1"
        phase1_dir.mkdir(parents=True, exist_ok=True)

        sandbox_backend = getattr(config, "sandbox_backend", "none")
        run_id = manifest.run_id

        t0 = time.monotonic()
        try:
            agents_label = ", ".join(config.agents)
            with phase_spinner(f"Agents researching: [agent]{agents_label}[/agent]"):
                with ThreadPoolExecutor() as pool:
                    futures = {}
                    for agent in config.agents:
                        executor = _get_executor(agent)
                        sandbox = _create_sandbox(run_dir, agent, run_id, sandbox_backend)
                        futures[pool.submit(
                            _run_agent, executor, sandbox, agent,
                            prompt_text, f"phase1/{agent}", config.verbose,
                        )] = agent

                    session_ids: dict[str, str | None] = {}
                    for future in as_completed(futures):
                        agent = futures[future]
                        result = future.result()
                        # Write report from agent output to canonical path
                        report_path = phase1_dir / f"{agent}-report.md"
                        report_path.write_text(result.raw_output)
                        # Capture session_id for Phase 2 reuse
                        session_ids[agent] = result.metadata.get("session_id")
                        logger.debug(
                            "[%s] Phase 1 report: %d chars",
                            agent, len(result.raw_output),
                        )

            # Store session_ids for Phase 2 reuse
            self._session_ids = session_ids

        except Exception:
            research.status = PhaseStatus.FAILED
            research.completed_at = _now_iso()
            research.duration_seconds = time.monotonic() - t0
            manifest.save(run_dir / "manifest.json")
            raise

        elapsed = time.monotonic() - t0
        research.status = PhaseStatus.COMPLETE
        research.completed_at = _now_iso()
        research.duration_seconds = elapsed

        logger.info(
            fmt_ok("Phase 1 complete [duration](%s)[/duration]"),
            fmt_duration(elapsed),
        )

        for agent in config.agents:
            output_rel = f"phase1/{agent}-report.md"
            research.agents[agent] = AgentResult(
                status=PhaseStatus.COMPLETE,
                duration_seconds=elapsed,
                output=output_rel,
            )

        manifest.save(run_dir / "manifest.json")
        return manifest

    def _run_single_refinement(
        self, run_dir: Path, config: Any, agent: str,
        session_id: str | None = None,
    ) -> tuple[str, float]:
        """Run one refinement session: agent reviews all peer reports.

        If session_id is provided, it's passed to the executor so the
        agent can reuse context from Phase 1.
        """
        phase1_dir = run_dir / "phase1"
        phase2_dir = run_dir / "phase2"
        phase2_dir.mkdir(parents=True, exist_ok=True)

        own_report = (phase1_dir / f"{agent}-report.md").read_text()

        # Collect all peer reports
        peers = [a for a in config.agents if a != agent]
        peer_parts = []
        for peer in peers:
            peer_report = (phase1_dir / f"{peer}-report.md").read_text()
            peer_parts.append(f"### {peer}\n\n{peer_report}")
        all_peer_reports = "\n\n---\n\n".join(peer_parts)

        prompt_text = build_refinement_prompt(
            config.topic, own_report, all_peer_reports
        )

        session_key = f"{agent}-refined"
        # Save prompt for inspection
        prompt_file = phase2_dir / f"{session_key}-prompt.md"
        prompt_file.write_text(prompt_text)

        sandbox_backend = getattr(config, "sandbox_backend", "none")
        run_id = getattr(config, "_run_id", "unknown")
        # Try to get run_id from the run_dir name if not on config
        if run_id == "unknown":
            run_id = run_dir.name

        executor = _get_executor(agent)
        sandbox = _create_sandbox(run_dir, agent, run_id, sandbox_backend)

        t0 = time.monotonic()
        # Pass session_id for ACP session reuse from Phase 1
        run_kwargs: dict[str, Any] = {}
        if session_id is not None:
            run_kwargs["session_id"] = session_id

        result = _run_agent(
            executor, sandbox, agent,
            prompt_text, f"phase2/{session_key}", config.verbose,
            **run_kwargs,
        )

        # Write refined report to canonical path
        final_out = phase2_dir / f"{session_key}.md"
        final_out.write_text(result.raw_output)

        elapsed = time.monotonic() - t0
        return session_key, elapsed

    def _run_phase2(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute Phase 2: cross-pollination refinements (one per agent)."""
        cp: CrossPollinationPhase = manifest.phases["cross_pollination"]
        cp.status = PhaseStatus.RUNNING
        cp.started_at = _now_iso()

        n = len(config.agents)
        logger.info(fmt_phase("Phase 2 -- Cross-Pollination"))
        logger.info(fmt_bullet("%d agents refining reports concurrently"), n)

        t0 = time.monotonic()

        progress = create_agent_progress()
        with progress:
            tasks = {
                agent: progress.add_task(
                    f"  [agent]{agent}[/agent] refining...",
                    total=None,
                )
                for agent in config.agents
            }

            # Get session IDs from Phase 1 for session reuse
            phase1_sessions = getattr(self, "_session_ids", {})

            with ThreadPoolExecutor() as pool:
                futures = {
                    pool.submit(
                        self._run_single_refinement, run_dir, config, agent,
                        session_id=phase1_sessions.get(agent),
                    ): agent
                    for agent in config.agents
                }
                for future in as_completed(futures):
                    agent = futures[future]
                    session_key, duration = future.result()
                    cp.sessions[session_key] = CrossPollinationSession(
                        status=PhaseStatus.COMPLETE,
                        duration_seconds=duration,
                        output=f"phase2/{session_key}.md",
                    )
                    # Mark this agent's task as done
                    progress.update(
                        tasks[agent],
                        description=f"  [ok]{SYM_OK}[/ok] [agent]{agent}[/agent] refined ({fmt_duration(duration)})",
                        completed=100,
                        total=100,
                    )

        elapsed = time.monotonic() - t0
        logger.info(
            fmt_ok("Phase 2 complete [duration](%s)[/duration]"),
            fmt_duration(elapsed),
        )
        cp.status = PhaseStatus.COMPLETE
        cp.completed_at = _now_iso()
        cp.duration_seconds = elapsed

        manifest.save(run_dir / "manifest.json")
        return manifest

    def _run_phase3(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute Phase 3: synthesis."""
        sp: SynthesisPhase = manifest.phases["synthesis"]
        sp.status = PhaseStatus.RUNNING
        sp.started_at = _now_iso()

        logger.info(fmt_phase("Phase 3 -- Synthesis"))
        logger.info(
            fmt_bullet("Synthesizer: %s combining %d refined reports"),
            fmt_agent(config.synthesizer), len(config.agents),
        )

        phase2_dir = run_dir / "phase2"
        phase3_dir = run_dir / "phase3"
        phase3_dir.mkdir(parents=True, exist_ok=True)

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
        prompt_file = phase3_dir / "synthesis-prompt.md"
        prompt_file.write_text(prompt_text)

        sandbox_backend = getattr(config, "sandbox_backend", "none")
        run_id = manifest.run_id

        executor = _get_executor(config.synthesizer)
        sandbox = _create_sandbox(run_dir, config.synthesizer, run_id, sandbox_backend)

        t0 = time.monotonic()
        with phase_spinner(f"Synthesizer [agent]{config.synthesizer}[/agent] working..."):
            result = _run_agent(
                executor, sandbox, config.synthesizer,
                prompt_text, "phase3", config.verbose,
            )

        # Write final report from agent output
        final_report = phase3_dir / "final-report.md"
        final_report.write_text(result.raw_output)

        elapsed = time.monotonic() - t0
        sp.status = PhaseStatus.COMPLETE
        sp.completed_at = _now_iso()
        sp.duration_seconds = elapsed

        report_size = len(result.raw_output)
        logger.info(
            fmt_ok("Phase 3 complete [duration](%s)[/duration] -- final report: %d bytes"),
            fmt_duration(elapsed), report_size,
        )

        manifest.save(run_dir / "manifest.json")
        return manifest
