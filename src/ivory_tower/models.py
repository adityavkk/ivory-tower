"""Data models for ivory-tower manifest and phase tracking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PhaseStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class AgentResult:
    status: PhaseStatus
    output: str
    duration_seconds: float | None = None


@dataclass
class CrossPollinationSession:
    status: PhaseStatus
    output: str
    duration_seconds: float | None = None


@dataclass
class ResearchPhase:
    status: PhaseStatus
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    agents: dict[str, AgentResult] = field(default_factory=dict)


@dataclass
class CrossPollinationPhase:
    status: PhaseStatus
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    sessions: dict[str, CrossPollinationSession] = field(default_factory=dict)


@dataclass
class SynthesisPhase:
    status: PhaseStatus
    agent: str
    output: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None


@dataclass
class SeedOptimizationResult:
    status: PhaseStatus
    judge: str
    rounds_completed: int = 0
    seed_score: float | None = None
    final_score: float | None = None
    output: str = ""
    log: str = ""


@dataclass
class AdversarialOptimizationPhase:
    status: PhaseStatus
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    seeds: dict[str, SeedOptimizationResult] = field(default_factory=dict)


@dataclass
class Flags:
    raw: bool = False
    instructions: str | None = None
    verbose: bool = False
    max_rounds: int = 10
    parse_agent: str | None = None


@dataclass
class Manifest:
    run_id: str
    topic: str
    agents: list[str]
    synthesizer: str
    flags: Flags
    phases: dict[str, Any]
    strategy: str = "council"
    total_duration_seconds: float | None = None
    sandbox_config: dict | None = None
    template_name: str | None = None
    agent_profiles: dict | None = None

    # -- serialization --

    def to_dict(self) -> dict[str, Any]:
        # Delegate phase serialization to strategy if available
        from ivory_tower.strategies import get_strategy
        try:
            strat = get_strategy(self.strategy)
            phases_dict = strat.phases_to_dict(self.phases)
        except (ValueError, NotImplementedError):
            # Fallback for council phases (backward compat)
            phases_dict = {
                "research": self._research_to_dict(),
                "cross_pollination": self._cross_pollination_to_dict(),
                "synthesis": self._synthesis_to_dict(),
            }

        result = {
            "run_id": self.run_id,
            "strategy": self.strategy,
            "topic": self.topic,
            "agents": self.agents,
            "synthesizer": self.synthesizer,
            "flags": {
                "raw": self.flags.raw,
                "instructions": self.flags.instructions,
                "verbose": self.flags.verbose,
                "max_rounds": self.flags.max_rounds,
                "parse_agent": self.flags.parse_agent,
            },
            "phases": phases_dict,
            "total_duration_seconds": self.total_duration_seconds,
        }
        if self.sandbox_config is not None:
            result["sandbox_config"] = self.sandbox_config
        if self.template_name is not None:
            result["template_name"] = self.template_name
        if self.agent_profiles is not None:
            result["agent_profiles"] = self.agent_profiles
        return result

    def _research_to_dict(self) -> dict[str, Any]:
        rp = self.phases["research"]
        assert isinstance(rp, ResearchPhase)
        return {
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

    def _cross_pollination_to_dict(self) -> dict[str, Any]:
        cp = self.phases["cross_pollination"]
        assert isinstance(cp, CrossPollinationPhase)
        return {
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

    def _synthesis_to_dict(self) -> dict[str, Any]:
        sp = self.phases["synthesis"]
        assert isinstance(sp, SynthesisPhase)
        return {
            "status": sp.status.value,
            "started_at": sp.started_at,
            "completed_at": sp.completed_at,
            "duration_seconds": sp.duration_seconds,
            "agent": sp.agent,
            "output": sp.output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        flags_d = data["flags"]
        flags = Flags(
            raw=flags_d["raw"],
            instructions=flags_d["instructions"],
            verbose=flags_d["verbose"],
            max_rounds=flags_d.get("max_rounds", 10),
            parse_agent=flags_d.get("parse_agent"),
        )

        strategy = data.get("strategy", "council")
        phases_d = data["phases"]

        # Delegate phase deserialization to strategy
        from ivory_tower.strategies import get_strategy
        try:
            strat = get_strategy(strategy)
            phases = strat.phases_from_dict(phases_d)
        except (ValueError, NotImplementedError):
            # Fallback for council phases (backward compat)
            phases = cls._council_phases_from_dict(phases_d)

        return cls(
            run_id=data["run_id"],
            topic=data["topic"],
            agents=data["agents"],
            synthesizer=data["synthesizer"],
            flags=flags,
            phases=phases,
            strategy=strategy,
            total_duration_seconds=data.get("total_duration_seconds"),
            sandbox_config=data.get("sandbox_config"),
            template_name=data.get("template_name"),
            agent_profiles=data.get("agent_profiles"),
        )

    @staticmethod
    def _council_phases_from_dict(phases_d: dict[str, Any]) -> dict[str, Any]:
        """Fallback council phase deserialization."""
        rp_d = phases_d["research"]
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

        cp_d = phases_d["cross_pollination"]
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

        sp_d = phases_d["synthesis"]
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

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> Manifest:
        data = json.loads(path.read_text())
        return cls.from_dict(data)
