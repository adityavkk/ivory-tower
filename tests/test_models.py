"""Tests for ivory_tower.models -- data models and serialization."""

import json
from pathlib import Path

from ivory_tower.models import (
    AdversarialOptimizationPhase,
    AgentResult,
    CrossPollinationPhase,
    CrossPollinationSession,
    Flags,
    Manifest,
    PhaseStatus,
    ResearchPhase,
    SeedOptimizationResult,
    SynthesisPhase,
)


# --- PhaseStatus enum ---


class TestPhaseStatus:
    def test_values(self):
        assert PhaseStatus.PENDING.value == "pending"
        assert PhaseStatus.RUNNING.value == "running"
        assert PhaseStatus.COMPLETE.value == "complete"
        assert PhaseStatus.FAILED.value == "failed"

    def test_from_string(self):
        assert PhaseStatus("pending") is PhaseStatus.PENDING
        assert PhaseStatus("failed") is PhaseStatus.FAILED


# --- AgentResult ---


class TestAgentResult:
    def test_defaults(self):
        r = AgentResult(
            status=PhaseStatus.PENDING,
            output="phase1/claude-opus-report.md",
        )
        assert r.status is PhaseStatus.PENDING
        assert r.duration_seconds is None
        assert r.output == "phase1/claude-opus-report.md"

    def test_with_duration(self):
        r = AgentResult(
            status=PhaseStatus.COMPLETE,
            duration_seconds=280.5,
            output="phase1/claude-opus-report.md",
        )
        assert r.duration_seconds == 280.5


# --- CrossPollinationSession ---


class TestCrossPollinationSession:
    def test_defaults(self):
        s = CrossPollinationSession(
            status=PhaseStatus.PENDING,
            output="phase2/claude-opus-cross-codex.md",
        )
        assert s.status is PhaseStatus.PENDING
        assert s.duration_seconds is None
        assert s.output == "phase2/claude-opus-cross-codex.md"


# --- ResearchPhase ---


class TestResearchPhase:
    def test_pending_defaults(self):
        rp = ResearchPhase(status=PhaseStatus.PENDING)
        assert rp.started_at is None
        assert rp.completed_at is None
        assert rp.duration_seconds is None
        assert rp.agents == {}

    def test_with_agents(self):
        agents = {
            "claude-opus": AgentResult(
                status=PhaseStatus.COMPLETE,
                duration_seconds=280,
                output="phase1/claude-opus-report.md",
            ),
        }
        rp = ResearchPhase(
            status=PhaseStatus.COMPLETE,
            started_at="2026-03-01T14:30:00Z",
            completed_at="2026-03-01T14:35:12Z",
            duration_seconds=312,
            agents=agents,
        )
        assert rp.agents["claude-opus"].duration_seconds == 280


# --- CrossPollinationPhase ---


class TestCrossPollinationPhase:
    def test_pending_defaults(self):
        cp = CrossPollinationPhase(status=PhaseStatus.PENDING)
        assert cp.sessions == {}

    def test_with_sessions(self):
        sessions = {
            "claude-opus-cross-codex": CrossPollinationSession(
                status=PhaseStatus.COMPLETE,
                duration_seconds=150,
                output="phase2/claude-opus-cross-codex.md",
            ),
        }
        cp = CrossPollinationPhase(
            status=PhaseStatus.COMPLETE,
            sessions=sessions,
        )
        assert cp.sessions["claude-opus-cross-codex"].duration_seconds == 150


# --- SynthesisPhase ---


class TestSynthesisPhase:
    def test_pending_defaults(self):
        sp = SynthesisPhase(
            status=PhaseStatus.PENDING,
            agent="claude-opus",
            output="phase3/final-report.md",
        )
        assert sp.started_at is None
        assert sp.completed_at is None
        assert sp.duration_seconds is None


# --- Flags ---


class TestFlags:
    def test_defaults(self):
        f = Flags()
        assert f.raw is False
        assert f.instructions is None
        assert f.verbose is False

    def test_custom(self):
        f = Flags(raw=True, instructions="focus on cost", verbose=True)
        assert f.raw is True
        assert f.instructions == "focus on cost"


# --- Manifest ---


def _make_manifest() -> Manifest:
    """Helper to build a full manifest matching the spec example."""
    return Manifest(
        run_id="20260301-143000-a1b2c3",
        topic="AI safety techniques",
        agents=["claude-opus", "codex-5.3-xhigh"],
        synthesizer="claude-opus",
        flags=Flags(),
        phases={
            "research": ResearchPhase(
                status=PhaseStatus.COMPLETE,
                started_at="2026-03-01T14:30:00Z",
                completed_at="2026-03-01T14:35:12Z",
                duration_seconds=312,
                agents={
                    "claude-opus": AgentResult(
                        status=PhaseStatus.COMPLETE,
                        duration_seconds=280,
                        output="phase1/claude-opus-report.md",
                    ),
                    "codex-5.3-xhigh": AgentResult(
                        status=PhaseStatus.COMPLETE,
                        duration_seconds=312,
                        output="phase1/codex-5.3-xhigh-report.md",
                    ),
                },
            ),
            "cross_pollination": CrossPollinationPhase(
                status=PhaseStatus.PENDING,
            ),
            "synthesis": SynthesisPhase(
                status=PhaseStatus.PENDING,
                agent="claude-opus",
                output="phase3/final-report.md",
            ),
        },
        total_duration_seconds=None,
    )


class TestManifest:
    def test_fields(self):
        m = _make_manifest()
        assert m.run_id == "20260301-143000-a1b2c3"
        assert m.agents == ["claude-opus", "codex-5.3-xhigh"]
        assert m.synthesizer == "claude-opus"
        assert isinstance(m.phases["research"], ResearchPhase)
        assert isinstance(m.phases["cross_pollination"], CrossPollinationPhase)
        assert isinstance(m.phases["synthesis"], SynthesisPhase)

    def test_to_dict_structure(self):
        m = _make_manifest()
        d = m.to_dict()
        assert d["run_id"] == "20260301-143000-a1b2c3"
        assert d["agents"] == ["claude-opus", "codex-5.3-xhigh"]
        assert d["flags"]["raw"] is False
        assert d["flags"]["instructions"] is None
        # Phase statuses serialize as strings
        assert d["phases"]["research"]["status"] == "complete"
        assert d["phases"]["cross_pollination"]["status"] == "pending"
        assert d["phases"]["synthesis"]["status"] == "pending"
        # Nested agent result
        ar = d["phases"]["research"]["agents"]["claude-opus"]
        assert ar["status"] == "complete"
        assert ar["duration_seconds"] == 280
        assert ar["output"] == "phase1/claude-opus-report.md"
        # Synthesis fields
        assert d["phases"]["synthesis"]["agent"] == "claude-opus"
        assert d["phases"]["synthesis"]["output"] == "phase3/final-report.md"
        assert d["total_duration_seconds"] is None

    def test_to_dict_is_json_serializable(self):
        m = _make_manifest()
        text = json.dumps(m.to_dict())
        assert isinstance(text, str)

    def test_roundtrip_dict(self):
        m = _make_manifest()
        d = m.to_dict()
        m2 = Manifest.from_dict(d)
        assert m2.run_id == m.run_id
        assert m2.topic == m.topic
        assert m2.agents == m.agents
        assert m2.synthesizer == m.synthesizer
        assert m2.flags.raw == m.flags.raw
        assert m2.flags.instructions == m.flags.instructions
        assert m2.phases["research"].status is PhaseStatus.COMPLETE
        assert m2.phases["research"].agents["claude-opus"].duration_seconds == 280
        assert m2.phases["cross_pollination"].status is PhaseStatus.PENDING
        assert m2.phases["synthesis"].agent == "claude-opus"

    def test_save_and_load(self, tmp_path: Path):
        m = _make_manifest()
        filepath = tmp_path / "manifest.json"
        m.save(filepath)
        # File exists and is valid JSON
        assert filepath.exists()
        data = json.loads(filepath.read_text())
        assert data["run_id"] == "20260301-143000-a1b2c3"
        # Load back
        m2 = Manifest.load(filepath)
        assert m2.run_id == m.run_id
        assert m2.phases["research"].agents["codex-5.3-xhigh"].output == "phase1/codex-5.3-xhigh-report.md"

    def test_from_dict_cross_pollination_sessions(self):
        """Roundtrip with populated cross-pollination sessions."""
        m = _make_manifest()
        # Mutate to add sessions
        cp = m.phases["cross_pollination"]
        assert isinstance(cp, CrossPollinationPhase)
        cp.sessions["claude-opus-cross-codex-5.3-xhigh"] = CrossPollinationSession(
            status=PhaseStatus.COMPLETE,
            duration_seconds=200,
            output="phase2/claude-opus-cross-codex-5.3-xhigh.md",
        )
        d = m.to_dict()
        m2 = Manifest.from_dict(d)
        cp2 = m2.phases["cross_pollination"]
        assert isinstance(cp2, CrossPollinationPhase)
        sess = cp2.sessions["claude-opus-cross-codex-5.3-xhigh"]
        assert sess.status is PhaseStatus.COMPLETE
        assert sess.duration_seconds == 200


# --- PhaseStatus.PARTIAL ---


class TestPhaseStatusPartial:
    def test_partial_value(self):
        assert PhaseStatus.PARTIAL.value == "partial"

    def test_from_string(self):
        assert PhaseStatus("partial") == PhaseStatus.PARTIAL


# --- SeedOptimizationResult ---


class TestSeedOptimizationResult:
    def test_defaults(self):
        r = SeedOptimizationResult(status=PhaseStatus.PENDING, judge="agent-b")
        assert r.status == PhaseStatus.PENDING
        assert r.judge == "agent-b"
        assert r.rounds_completed == 0
        assert r.seed_score is None
        assert r.final_score is None
        assert r.output == ""
        assert r.log == ""

    def test_with_values(self):
        r = SeedOptimizationResult(
            status=PhaseStatus.COMPLETE,
            judge="agent-b",
            rounds_completed=10,
            seed_score=5.2,
            final_score=8.3,
            output="phase2/agent-a-optimized.md",
            log="phase2/agent-a-optimization-log.json",
        )
        assert r.final_score == 8.3


# --- AdversarialOptimizationPhase ---


class TestAdversarialOptimizationPhase:
    def test_defaults(self):
        p = AdversarialOptimizationPhase(status=PhaseStatus.PENDING)
        assert p.status == PhaseStatus.PENDING
        assert p.seeds == {}

    def test_with_seeds(self):
        p = AdversarialOptimizationPhase(
            status=PhaseStatus.RUNNING,
            seeds={
                "a": SeedOptimizationResult(status=PhaseStatus.RUNNING, judge="b"),
                "b": SeedOptimizationResult(status=PhaseStatus.PENDING, judge="a"),
            },
        )
        assert len(p.seeds) == 2
        assert p.seeds["a"].judge == "b"


# --- Flags.max_rounds ---


class TestFlagsMaxRounds:
    def test_default_max_rounds(self):
        f = Flags()
        assert f.max_rounds == 10

    def test_custom_max_rounds(self):
        f = Flags(max_rounds=5)
        assert f.max_rounds == 5
