"""Council strategy: the original 3-phase multi-agent research pipeline."""

from __future__ import annotations

import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_counselors_output(
    output_dir: Path, agents: list[str], suffix: str = "-report.md"
) -> None:
    """Copy agent outputs from counselors slug subdirectory to expected paths."""
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
        t0 = time.monotonic()

        manifest = self._run_phase1(run_dir, config, manifest)
        manifest = self._run_phase2(run_dir, config, manifest)
        manifest = self._run_phase3(run_dir, config, manifest)

        manifest.total_duration_seconds = time.monotonic() - t0
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
        """Execute Phase 1: independent research by all agents."""
        research: ResearchPhase = manifest.phases["research"]
        research.status = PhaseStatus.RUNNING
        research.started_at = _now_iso()

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

        _normalize_counselors_output(phase1_dir, config.agents, suffix="-report.md")

        elapsed = time.monotonic() - t0
        research.status = PhaseStatus.COMPLETE
        research.completed_at = _now_iso()
        research.duration_seconds = elapsed

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
    ) -> tuple[str, float]:
        """Run one refinement session: agent reviews all peer reports."""
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
        prompt_file = run_dir / "phase2" / f"{session_key}-prompt.md"
        prompt_file.write_text(prompt_text)

        session_out_dir = phase2_dir / f"{session_key}-out"
        session_out_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.monotonic()
        run_counselors(
            prompt_file=prompt_file,
            agents=[agent],
            output_dir=session_out_dir,
            verbose=config.verbose,
        )

        _normalize_counselors_output(session_out_dir, [agent], suffix=".md")
        agent_out = session_out_dir / f"{agent}.md"
        final_out = phase2_dir / f"{session_key}.md"
        if agent_out.exists() and not final_out.exists():
            shutil.copy2(agent_out, final_out)

        return session_key, time.monotonic() - t0

    def _run_phase2(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute Phase 2: cross-pollination refinements (one per agent)."""
        cp: CrossPollinationPhase = manifest.phases["cross_pollination"]
        cp.status = PhaseStatus.RUNNING
        cp.started_at = _now_iso()

        t0 = time.monotonic()

        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    self._run_single_refinement, run_dir, config, agent
                ): agent
                for agent in config.agents
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

    def _run_phase3(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute Phase 3: synthesis."""
        sp: SynthesisPhase = manifest.phases["synthesis"]
        sp.status = PhaseStatus.RUNNING
        sp.started_at = _now_iso()

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
        prompt_file = run_dir / "phase3" / "synthesis-prompt.md"
        prompt_file.write_text(prompt_text)

        t0 = time.monotonic()
        run_counselors(
            prompt_file=prompt_file,
            agents=[config.synthesizer],
            output_dir=phase3_dir,
            verbose=config.verbose,
        )

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
