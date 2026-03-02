"""Generic template executor for YAML-defined strategies.

Handles phase sequencing, isolation setup, blackboard management,
round iteration, and dynamic fan-out. No custom Python needed.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ivory_tower.executor import get_executor
from ivory_tower.executor.types import AgentExecutor, AgentOutput
from ivory_tower.log import (
    fmt_agent,
    fmt_bullet,
    fmt_duration,
    fmt_ok,
    fmt_phase,
    phase_spinner,
)
from ivory_tower.sandbox import get_provider
from ivory_tower.sandbox.blackboard import FileBlackboard
from ivory_tower.sandbox.types import Sandbox, SandboxConfig, SharedVolume
from ivory_tower.templates.loader import (
    PhaseConfig,
    StrategyTemplate,
)

logger = logging.getLogger(__name__)


def setup_phase_isolation(
    phase: PhaseConfig,
    sandboxes: dict[str, Sandbox],
    volumes: dict[str, SharedVolume],
    previous_outputs: dict[str, dict[str, Path]],
    teams: dict[str, str] | None = None,  # agent_name -> team_name
) -> None:
    """Configure sandbox isolation for a phase.
    
    This is the core isolation logic -- it copies/mounts data into sandboxes
    based on the declared isolation mode.
    """
    match phase.isolation:
        case "full":
            # Nothing to do -- sandboxes are already isolated
            pass

        case "read-peers":
            input_phase = phase.input_from
            if isinstance(input_phase, list):
                input_phase = input_phase[0]
            if input_phase and input_phase in previous_outputs:
                prev = previous_outputs[input_phase]
                for agent_name, sandbox in sandboxes.items():
                    for peer_name, output_path in prev.items():
                        if peer_name != agent_name:
                            sandbox.copy_in(output_path, f"peers/{peer_name}.md")

        case "read-all":
            phases_to_read = phase.input_from
            if phases_to_read is None:
                phases_to_read = []
            elif isinstance(phases_to_read, str):
                phases_to_read = [phases_to_read]
            
            for phase_name in phases_to_read:
                if phase_name in previous_outputs:
                    for agent_name, output_path in previous_outputs[phase_name].items():
                        for sandbox in sandboxes.values():
                            sandbox.copy_in(
                                output_path,
                                f"inputs/{phase_name}/{agent_name}.md",
                            )

        case "blackboard":
            if phase.blackboard:
                bb_name = phase.blackboard.name
                if bb_name in volumes:
                    volume = volumes[bb_name]
                    bb_file = phase.blackboard.file
                    for sandbox in sandboxes.values():
                        if bb_file:
                            try:
                                bb_content = volume.read_file(bb_file)
                            except (FileNotFoundError, OSError):
                                bb_content = ""
                            sandbox.write_file(f"blackboard/{bb_file}", bb_content)

        case "read-blackboard":
            if phase.blackboard:
                bb_name = phase.blackboard.name
                if bb_name in volumes:
                    volume = volumes[bb_name]
                    bb_file = phase.blackboard.file
                    for sandbox in sandboxes.values():
                        if bb_file:
                            try:
                                bb_content = volume.read_file(bb_file)
                            except (FileNotFoundError, OSError):
                                bb_content = ""
                            sandbox.write_file(f"blackboard/{bb_file}", bb_content)

        case "team":
            if teams and phase.blackboard:
                for agent_name, sandbox in sandboxes.items():
                    agent_team = teams.get(agent_name)
                    if agent_team:
                        team_vol_name = f"team-{agent_team}"
                        if team_vol_name in volumes:
                            team_volume = volumes[team_vol_name]
                            for f in team_volume.list_files():
                                team_path = Path(team_volume.path) / f
                                if team_path.exists():
                                    sandbox.copy_in(team_path, f"team-board/{f}")

        case "cross-team-read":
            input_phase = phase.input_from
            if isinstance(input_phase, list):
                input_phase = input_phase[0]
            if input_phase and input_phase in previous_outputs and teams:
                prev = previous_outputs[input_phase]
                for agent_name, sandbox in sandboxes.items():
                    agent_team = teams.get(agent_name)
                    for peer_name, output_path in prev.items():
                        peer_team = teams.get(peer_name)
                        if peer_team != agent_team:
                            sandbox.copy_in(output_path, f"opposing/{peer_name}.md")

        case "none":
            pass


class GenericTemplateExecutor:
    """Executes a strategy defined entirely in YAML.

    Handles phase sequencing, isolation setup, blackboard management,
    round iteration, and dynamic fan-out. No custom Python needed.
    """

    def __init__(self, template: StrategyTemplate) -> None:
        self.template = template

    def run(
        self,
        run_dir: Path,
        agents: list[str],
        synthesizer: str,
        sandbox_backend: str = "none",
        sandbox_config: SandboxConfig | None = None,
        executor_name: str = "counselors",
        topic: str = "",
        teams: dict[str, str] | None = None,
        rounds_override: int | None = None,
        verbose: bool = False,
    ) -> dict[str, dict[str, Path]]:
        """Execute all phases of the template.
        
        Returns:
            Dict mapping phase_name -> {agent_name: output_path}
        """
        config = sandbox_config or SandboxConfig(backend=sandbox_backend)
        provider = get_provider(sandbox_backend)
        executor = get_executor(executor_name)

        sandboxes: dict[str, Sandbox] = {}
        volumes: dict[str, SharedVolume] = {}
        outputs: dict[str, dict[str, Path]] = {}

        run_id = run_dir.name

        template_name = self.template.name
        total_phases = len(self.template.phases)
        logger.info("")
        logger.info(fmt_phase("%s Template -- %d phases"), template_name, total_phases)
        agents_str = ", ".join(fmt_agent(a) for a in agents)
        logger.info(fmt_bullet("Agents: %s"), agents_str)
        logger.info(fmt_bullet("Synthesizer: %s"), fmt_agent(synthesizer))
        logger.info(fmt_bullet("Sandbox: %s"), sandbox_backend)

        t0_total = time.monotonic()

        try:
            # Create agent sandboxes (including synthesizer if not in agents list)
            all_participants = list(agents)
            if synthesizer and synthesizer not in all_participants:
                all_participants.append(synthesizer)

            for agent in all_participants:
                sandboxes[agent] = provider.create_sandbox(
                    agent_name=agent,
                    run_id=run_id,
                    run_dir=run_dir,
                    config=config,
                )

            # Create shared volumes for blackboards
            for phase in self.template.phases:
                if phase.blackboard:
                    bb = phase.blackboard
                    if bb.name not in volumes:
                        volumes[bb.name] = provider.create_shared_volume(
                            name=bb.name,
                            run_id=run_id,
                            run_dir=run_dir,
                        )
                        # Initialize blackboard file if specified
                        if bb.file:
                            volumes[bb.name].write_file(bb.file, "")

            # Create team volumes if needed
            if teams:
                team_names = set(teams.values())
                for team_name in team_names:
                    vol_name = f"team-{team_name}"
                    if vol_name not in volumes:
                        volumes[vol_name] = provider.create_shared_volume(
                            name=vol_name,
                            run_id=run_id,
                            run_dir=run_dir,
                        )

            # Execute phases in order
            for phase_idx, phase in enumerate(self.template.phases, 1):
                phase_agents = self._resolve_phase_agents(
                    phase, agents, synthesizer, teams, outputs,
                )
                phase_sandboxes = {}
                for a in phase_agents:
                    if a in sandboxes:
                        phase_sandboxes[a] = sandboxes[a]
                    elif a == synthesizer and synthesizer in sandboxes:
                        phase_sandboxes[a] = sandboxes[synthesizer]

                num_rounds = rounds_override or phase.rounds or self.template.defaults.rounds

                # -- Phase header --
                phase_desc = phase.description or phase.name
                phase_agents_str = ", ".join(fmt_agent(a) for a in phase_agents)
                logger.info("")
                logger.info(
                    fmt_phase("Phase %d/%d -- %s"),
                    phase_idx, total_phases, phase_desc,
                )
                logger.info(fmt_bullet("Agents: %s"), phase_agents_str)
                logger.info(
                    fmt_bullet("Isolation: %s"),
                    phase.isolation,
                )
                if num_rounds:
                    logger.info(fmt_bullet("Rounds: %d"), num_rounds)

                t0_phase = time.monotonic()

                if num_rounds:
                    outputs[phase.name] = self._run_iterative_phase(
                        phase, phase_sandboxes, volumes, outputs,
                        executor, run_dir, topic, teams, num_rounds, verbose,
                    )
                else:
                    outputs[phase.name] = self._run_single_phase(
                        phase, phase_sandboxes, volumes, outputs,
                        executor, run_dir, topic, teams, verbose,
                    )

                phase_elapsed = time.monotonic() - t0_phase
                logger.info(
                    fmt_ok("Phase %d/%d complete [duration](%s)[/duration]"),
                    phase_idx, total_phases, fmt_duration(phase_elapsed),
                )

        finally:
            # Cleanup
            for sandbox in sandboxes.values():
                sandbox.destroy()
            provider.destroy_all(run_id)

        total_elapsed = time.monotonic() - t0_total
        logger.info("")
        logger.info(
            fmt_ok("%s template complete [duration](%s)[/duration]"),
            template_name, fmt_duration(total_elapsed),
        )

        return outputs

    def _resolve_phase_agents(
        self,
        phase: PhaseConfig,
        agents: list[str],
        synthesizer: str,
        teams: dict[str, str] | None,
        outputs: dict[str, dict[str, Path]],
    ) -> list[str]:
        """Determine which agents participate in a phase."""
        if phase.agents == "all":
            return agents
        if phase.agents == "dynamic":
            # Dynamic fan-out: determined by output of a previous phase
            if phase.fan_out and phase.fan_out in outputs:
                # Read the planner output to determine subtopics
                return agents  # For now, return all agents (dynamic resolved at runtime)
            return agents
        if isinstance(phase.agents, list):
            result = []
            for agent_spec in phase.agents:
                if agent_spec == "synthesizer":
                    result.append(synthesizer)
                elif agent_spec == "planner":
                    result.append(agents[0])
                elif teams:
                    # Team reference: add all agents on that team
                    for agent_name, team_name in teams.items():
                        if team_name == agent_spec:
                            result.append(agent_name)
                else:
                    result.append(agent_spec)
            return result
        return agents

    def _run_single_phase(
        self,
        phase: PhaseConfig,
        sandboxes: dict[str, Sandbox],
        volumes: dict[str, SharedVolume],
        outputs: dict[str, dict[str, Path]],
        executor: AgentExecutor,
        run_dir: Path,
        topic: str,
        teams: dict[str, str] | None,
        verbose: bool,
    ) -> dict[str, Path]:
        """Run a non-iterative phase."""
        setup_phase_isolation(phase, sandboxes, volumes, outputs, teams)

        phase_outputs: dict[str, Path] = {}
        prompt = topic  # Base prompt is the topic

        n_agents = len(sandboxes)

        # Run all agents (parallel if multiple)
        if n_agents > 1:
            logger.info(fmt_bullet("%d agents running concurrently"), n_agents)
            with ThreadPoolExecutor(max_workers=n_agents) as pool:
                futures = {}
                for agent_name, sandbox in sandboxes.items():
                    futures[agent_name] = pool.submit(
                        executor.run,
                        sandbox,
                        agent_name,
                        prompt,
                        f"output/{phase.name}",
                        verbose=verbose,
                    )
                for agent_name, future in futures.items():
                    result = future.result()
                    output_filename = phase.output.format(agent=agent_name)
                    canonical = run_dir / phase.name / output_filename
                    canonical.parent.mkdir(parents=True, exist_ok=True)
                    sandboxes[agent_name].copy_out(result.report_path, canonical)
                    phase_outputs[agent_name] = canonical
                    logger.debug(
                        "Agent %s output -> %s", agent_name, canonical,
                    )
        else:
            for agent_name, sandbox in sandboxes.items():
                with phase_spinner(f"{fmt_agent(agent_name)} working..."):
                    result = executor.run(
                        sandbox, agent_name, prompt,
                        f"output/{phase.name}",
                        verbose=verbose,
                    )
                output_filename = phase.output.format(agent=agent_name)
                canonical = run_dir / phase.name / output_filename
                canonical.parent.mkdir(parents=True, exist_ok=True)
                sandbox.copy_out(result.report_path, canonical)
                phase_outputs[agent_name] = canonical
                logger.debug(
                    "Agent %s output -> %s", agent_name, canonical,
                )

        return phase_outputs

    def _run_iterative_phase(
        self,
        phase: PhaseConfig,
        sandboxes: dict[str, Sandbox],
        volumes: dict[str, SharedVolume],
        outputs: dict[str, dict[str, Path]],
        executor: AgentExecutor,
        run_dir: Path,
        topic: str,
        teams: dict[str, str] | None,
        num_rounds: int,
        verbose: bool,
    ) -> dict[str, Path]:
        """Run a round-based phase (debate rounds, optimization loops)."""
        blackboard = None
        if phase.blackboard and phase.blackboard.name in volumes:
            blackboard = FileBlackboard(
                volume=volumes[phase.blackboard.name],
                file_name=phase.blackboard.file,
                access_mode=phase.blackboard.access,
            )

        phase_outputs: dict[str, Path] = {}
        agent_names = list(sandboxes.keys())

        for round_num in range(1, num_rounds + 1):
            logger.info(
                fmt_bullet("Round %d/%d -- agents: %s"),
                round_num, num_rounds,
                ", ".join(fmt_agent(a) for a in agent_names),
            )
            t0_round = time.monotonic()

            # Refresh blackboard content in each sandbox
            if blackboard and phase.blackboard and phase.blackboard.file:
                current_bb = blackboard.get_content()
                for sandbox in sandboxes.values():
                    sandbox.write_file(
                        f"blackboard/{phase.blackboard.file}",
                        current_bb,
                    )

            # Run agents sequentially within each round (turn-based)
            for agent_name, sandbox in sandboxes.items():
                prompt = topic
                with phase_spinner(
                    f"{fmt_agent(agent_name)} (round {round_num}/{num_rounds})"
                ):
                    result = executor.run(
                        sandbox,
                        agent_name,
                        prompt,
                        f"output/{phase.name}/round-{round_num:02d}",
                        verbose=verbose,
                    )

                # Copy output to canonical location
                output_filename = phase.output.format(
                    agent=agent_name, round=round_num,
                )
                canonical = run_dir / phase.name / output_filename
                canonical.parent.mkdir(parents=True, exist_ok=True)
                sandbox.copy_out(result.report_path, canonical)

                # Orchestrator appends to blackboard
                if blackboard and phase.blackboard:
                    if phase.blackboard.access in ("append", "rw"):
                        report_text = canonical.read_text()
                        blackboard.append(agent_name, round_num, report_text)

                phase_outputs[f"{agent_name}-round-{round_num}"] = canonical

            round_elapsed = time.monotonic() - t0_round
            logger.debug(
                "Round %d complete (%s)", round_num, fmt_duration(round_elapsed),
            )

        return phase_outputs
