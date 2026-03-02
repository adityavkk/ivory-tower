"""Map/Reduce strategy -- topic decomposition, specialist research, synthesis."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from rich.console import Console


from ivory_tower.models import Flags, Manifest, PhaseStatus
from ivory_tower.templates import load_template
from ivory_tower.templates.executor import GenericTemplateExecutor

logger = logging.getLogger(__name__)

# Stdout console for dry_run output (distinct from log.py's stderr console)
_dry_run_console = Console()


class MapReduceStrategy:
    """Decompose topic into subtopics, assign specialists, synthesize.

    Uses the built-in map-reduce.yml template:
    - Decompose: planner breaks topic into subtopics
    - Map: one agent per subtopic in full isolation
    - Reduce: synthesizer merges all specialist reports
    """

    name = "map-reduce"
    description = "Decompose topic into subtopics, specialist research, synthesize"

    def validate(self, config: Any) -> list[str]:
        errors = []
        if len(config.agents) < 2:
            errors.append("Map/Reduce requires at least 2 agents")
        if not config.synthesizer:
            errors.append("Map/Reduce requires a synthesizer")
        return errors

    def create_manifest(self, config: Any, run_id: str) -> Manifest:
        template = load_template("map-reduce")
        phases = {}
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
            strategy="map-reduce",
        )

    def run(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        t0 = time.monotonic()

        template = load_template("map-reduce")
        executor = GenericTemplateExecutor(template)

        sandbox_backend = getattr(config, "sandbox_backend", "none")

        executor.run(
            run_dir=run_dir,
            agents=config.agents,
            synthesizer=config.synthesizer,
            sandbox_backend=sandbox_backend,
            executor_name="counselors",
            topic=config.topic,
            verbose=config.verbose,
        )

        for phase_name in manifest.phases:
            manifest.phases[phase_name]["status"] = PhaseStatus.COMPLETE

        manifest.total_duration_seconds = time.monotonic() - t0
        manifest.save(run_dir / "manifest.json")

        return manifest

    def resume(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        all_complete = all(
            p.get("status") == PhaseStatus.COMPLETE
            for p in manifest.phases.values()
        )
        if all_complete:
            return manifest
        return self.run(run_dir, config, manifest)

    def dry_run(self, config: Any) -> None:
        template = load_template("map-reduce")

        _dry_run_console.print(f"\n[bold]Strategy:[/bold] {self.name}")
        _dry_run_console.print(f"[bold]Description:[/bold] {self.description}")
        _dry_run_console.print(f"[bold]Agents:[/bold] {', '.join(config.agents)}")
        _dry_run_console.print(f"[bold]Synthesizer:[/bold] {config.synthesizer}")
        _dry_run_console.print(f"\n[bold]Phases:[/bold]")
        for phase in template.phases:
            agents_desc = (
                phase.agents
                if isinstance(phase.agents, str)
                else ", ".join(phase.agents)
            )
            _dry_run_console.print(
                f"  {phase.name}: {phase.description} "
                f"(isolation={phase.isolation}, agents={agents_desc})"
            )

    def format_status(self, manifest: Manifest) -> list[tuple[str, str]]:
        result = []
        for phase_name, phase_data in manifest.phases.items():
            status = phase_data.get("status", PhaseStatus.PENDING)
            if isinstance(status, PhaseStatus):
                status_str = status.value
            else:
                status_str = str(status)
            result.append((phase_name, status_str))
        return result

    def phases_to_dict(self, phases: dict) -> dict:
        result = {}
        for name, data in phases.items():
            entry = dict(data)
            if "status" in entry and isinstance(entry["status"], PhaseStatus):
                entry["status"] = entry["status"].value
            result[name] = entry
        return result

    def phases_from_dict(self, data: dict) -> dict:
        result = {}
        for name, phase_data in data.items():
            entry = dict(phase_data)
            if "status" in entry:
                entry["status"] = PhaseStatus(entry["status"])
            result[name] = entry
        return result
