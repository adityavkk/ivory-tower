"""Debate strategy -- structured turn-based argumentation via template executor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console

from ivory_tower.models import Flags, Manifest, PhaseStatus
from ivory_tower.templates import load_template, validate_template
from ivory_tower.templates.executor import GenericTemplateExecutor


console = Console()


class DebateStrategy:
    """Structured turn-based debate with shared transcript.

    Uses the built-in debate.yml template:
    - Opening statements (full isolation)
    - N rounds of debate (blackboard with append-only transcript)
    - Closing statements (read-blackboard)
    - Verdict (judge reads all)
    """

    name = "debate"
    description = "Structured turn-based debate with shared transcript"

    def validate(self, config: Any) -> list[str]:
        errors: list[str] = []
        if len(config.agents) < 2:
            errors.append("Debate requires at least 2 agents")
        if not config.synthesizer:
            errors.append("Debate requires a synthesizer (judge)")
        return errors

    def create_manifest(self, config: Any, run_id: str) -> Manifest:
        template = load_template("debate")
        phases: dict[str, Any] = {}
        for phase in template.phases:
            phases[phase.name] = {
                "status": PhaseStatus.PENDING,
                "isolation": phase.isolation,
            }

        return Manifest(
            run_id=run_id,
            topic=config.topic,
            agents=config.agents,
            synthesizer=config.synthesizer,
            flags=Flags(
                raw=config.raw,
                instructions=config.instructions,
                verbose=config.verbose,
            ),
            phases=phases,
            strategy="debate",
        )

    def run(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        import time

        start = time.monotonic()

        template = load_template("debate")
        executor = GenericTemplateExecutor(template)

        sandbox_backend = getattr(config, "sandbox_backend", "none")
        rounds_override = getattr(config, "rounds", None)

        executor.run(
            run_dir=run_dir,
            agents=config.agents,
            synthesizer=config.synthesizer,
            sandbox_backend=sandbox_backend,
            executor_name="counselors",
            topic=config.topic,
            rounds_override=rounds_override,
            verbose=config.verbose,
        )

        # Mark all phases complete
        for phase_name in manifest.phases:
            manifest.phases[phase_name]["status"] = PhaseStatus.COMPLETE

        manifest.total_duration_seconds = time.monotonic() - start
        manifest.save(run_dir / "manifest.json")
        return manifest

    def resume(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        # For now, restart from scratch if any phase incomplete
        all_complete = all(
            p.get("status") == PhaseStatus.COMPLETE
            for p in manifest.phases.values()
        )
        if all_complete:
            return manifest
        return self.run(run_dir, config, manifest)

    def dry_run(self, config: Any) -> None:
        template = load_template("debate")
        rounds = getattr(config, "rounds", None) or template.defaults.rounds or 3

        console.print(f"\n[bold]Strategy:[/bold] {self.name}")
        console.print(f"[bold]Description:[/bold] {self.description}")
        console.print(f"[bold]Agents:[/bold] {', '.join(config.agents)}")
        console.print(f"[bold]Synthesizer (Judge):[/bold] {config.synthesizer}")
        console.print(f"[bold]Rounds:[/bold] {rounds}")
        console.print(f"\n[bold]Phases:[/bold]")
        for phase in template.phases:
            agents_desc = (
                phase.agents
                if isinstance(phase.agents, str)
                else ", ".join(phase.agents)
            )
            console.print(
                f"  {phase.name}: {phase.description} "
                f"(isolation={phase.isolation}, agents={agents_desc})"
            )
            if phase.blackboard:
                console.print(
                    f"    Blackboard: {phase.blackboard.name} "
                    f"(access={phase.blackboard.access})"
                )

    def format_status(self, manifest: Manifest) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for phase_name, phase_data in manifest.phases.items():
            status = phase_data.get("status", PhaseStatus.PENDING)
            if isinstance(status, PhaseStatus):
                status_str = status.value
            else:
                status_str = str(status)
            result.append((phase_name, status_str))
        return result

    def phases_to_dict(self, phases: dict) -> dict:
        result: dict[str, Any] = {}
        for name, data in phases.items():
            entry = dict(data)
            if "status" in entry and isinstance(entry["status"], PhaseStatus):
                entry["status"] = entry["status"].value
            result[name] = entry
        return result

    def phases_from_dict(self, data: dict) -> dict:
        result: dict[str, Any] = {}
        for name, phase_data in data.items():
            entry = dict(phase_data)
            if "status" in entry:
                entry["status"] = PhaseStatus(entry["status"])
            result[name] = entry
        return result
