"""Tests for ivory_tower.engine -- phase orchestration engine."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# ---------------------------------------------------------------------------
# Stub models so tests work even if models.py isn't merged yet
# ---------------------------------------------------------------------------
try:
    from ivory_tower.models import (
        Manifest,
        Flags,
        PhaseStatus,
        ResearchPhase,
        CrossPollinationPhase,
        CrossPollinationSession,
        SynthesisPhase,
        AgentResult,
    )
except ImportError:
    from enum import Enum

    class PhaseStatus(Enum):
        PENDING = "pending"
        RUNNING = "running"
        COMPLETE = "complete"
        FAILED = "failed"

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
    class Flags:
        raw: bool = False
        instructions: str | None = None
        verbose: bool = False

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
    class Manifest:
        run_id: str
        topic: str
        agents: list[str]
        synthesizer: str
        flags: Flags
        phases: dict
        total_duration_seconds: float | None = None

        def to_dict(self):
            return {}

        def save(self, path: Path):
            path.write_text(json.dumps({"run_id": self.run_id}))

        @classmethod
        def load(cls, path: Path):
            return cls(**json.loads(path.read_text()))

        @classmethod
        def from_dict(cls, d):
            return cls(**d)


# Stub CounselorsError if needed
try:
    from ivory_tower.counselors import CounselorsError
except ImportError:

    class CounselorsError(Exception):
        pass


from ivory_tower.engine import (
    RunConfig,
    run_phase1,
    run_phase2,
    run_phase3,
    run_pipeline,
    print_dry_run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENTS = ["claude-opus", "codex-5.3-xhigh", "amp-deep"]
TOPIC = "AI safety techniques in 2026"


def _make_manifest(agents: list[str] | None = None, synthesizer: str = "claude-opus") -> Manifest:
    agents = agents or AGENTS
    return Manifest(
        run_id="20260301-143000-a1b2c3",
        topic=TOPIC,
        agents=agents,
        synthesizer=synthesizer,
        flags=Flags(),
        phases={
            "research": ResearchPhase(status=PhaseStatus.PENDING),
            "cross_pollination": CrossPollinationPhase(status=PhaseStatus.PENDING),
            "synthesis": SynthesisPhase(
                status=PhaseStatus.PENDING,
                agent=synthesizer,
                output="phase3/final-report.md",
            ),
        },
        total_duration_seconds=None,
    )


def _make_config(
    agents: list[str] | None = None,
    synthesizer: str = "claude-opus",
    **kwargs,
) -> RunConfig:
    return RunConfig(
        topic=TOPIC,
        agents=agents or AGENTS,
        synthesizer=synthesizer,
        **kwargs,
    )


def _create_phase1_outputs(run_dir: Path, agents: list[str]) -> None:
    """Simulate phase1 output files existing on disk."""
    phase1 = run_dir / "phase1"
    phase1.mkdir(parents=True, exist_ok=True)
    for agent in agents:
        (phase1 / f"{agent}-report.md").write_text(
            f"# Research Report by {agent}\n\nFindings about {TOPIC}..."
        )


def _create_phase2_outputs(run_dir: Path, agents: list[str]) -> None:
    """Simulate phase2 output files existing on disk."""
    phase2 = run_dir / "phase2"
    phase2.mkdir(parents=True, exist_ok=True)
    for agent in agents:
        for peer in agents:
            if agent != peer:
                fname = f"{agent}-cross-{peer}.md"
                (phase2 / fname).write_text(
                    f"# Refinement by {agent} reviewing {peer}\n\nRefined findings..."
                )


# ---------------------------------------------------------------------------
# 1. RunConfig defaults
# ---------------------------------------------------------------------------


class TestRunConfig:
    def test_run_config_defaults(self):
        cfg = RunConfig(topic="test", agents=["a"], synthesizer="a")
        assert cfg.raw is False
        assert cfg.instructions is None
        assert cfg.verbose is False
        assert cfg.output_dir == Path("./research")
        assert cfg.dry_run is False

    def test_run_config_custom(self):
        cfg = RunConfig(
            topic="test",
            agents=["a", "b"],
            synthesizer="a",
            raw=True,
            instructions="focus on cost",
            verbose=True,
            output_dir=Path("/tmp/out"),
            dry_run=True,
        )
        assert cfg.raw is True
        assert cfg.instructions == "focus on cost"
        assert cfg.output_dir == Path("/tmp/out")


# ---------------------------------------------------------------------------
# 2-5. Phase 1 tests
# ---------------------------------------------------------------------------


class TestRunPhase1:
    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_research_prompt")
    def test_run_phase1_writes_prompt_file(
        self, mock_build, mock_counselors, tmp_path
    ):
        """research-prompt.md is written to run_dir."""
        mock_build.return_value = "# Deep Research Task\n\nMy research prompt"

        def _create_outputs(*args, **kwargs):
            _create_phase1_outputs(tmp_path, AGENTS)

        mock_counselors.side_effect = _create_outputs

        manifest = _make_manifest()
        config = _make_config()
        run_phase1(tmp_path, config, manifest)

        prompt_file = tmp_path / "research-prompt.md"
        assert prompt_file.exists()
        assert "Deep Research Task" in prompt_file.read_text()

    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_research_prompt")
    def test_run_phase1_calls_counselors_with_all_agents(
        self, mock_build, mock_counselors, tmp_path
    ):
        """run_counselors is called with all agents from config."""
        mock_build.return_value = "prompt text"

        def _create_outputs(*args, **kwargs):
            _create_phase1_outputs(tmp_path, AGENTS)

        mock_counselors.side_effect = _create_outputs

        manifest = _make_manifest()
        config = _make_config()
        run_phase1(tmp_path, config, manifest)

        mock_counselors.assert_called_once()
        call_kwargs = mock_counselors.call_args
        # Verify agents list passed to run_counselors
        assert call_kwargs.kwargs.get("agents") == AGENTS or (
            len(call_kwargs.args) > 1 and call_kwargs.args[1] == AGENTS
        )

    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_research_prompt")
    def test_run_phase1_updates_manifest_status(
        self, mock_build, mock_counselors, tmp_path
    ):
        """Manifest research phase status -> 'complete' on success."""
        mock_build.return_value = "prompt text"

        def _create_outputs(*args, **kwargs):
            _create_phase1_outputs(tmp_path, AGENTS)

        mock_counselors.side_effect = _create_outputs

        manifest = _make_manifest()
        config = _make_config()
        result = run_phase1(tmp_path, config, manifest)

        research = result.phases["research"]
        assert research.status is PhaseStatus.COMPLETE
        assert research.duration_seconds is not None
        assert research.duration_seconds >= 0
        # Per-agent results populated
        for agent in AGENTS:
            assert agent in research.agents
            assert research.agents[agent].status is PhaseStatus.COMPLETE

    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_research_prompt")
    def test_run_phase1_failure_marks_failed(
        self, mock_build, mock_counselors, tmp_path
    ):
        """On CounselorsError, manifest status -> 'failed' and error re-raised."""
        mock_build.return_value = "prompt text"
        mock_counselors.side_effect = CounselorsError("agent crashed")

        manifest = _make_manifest()
        config = _make_config()

        with pytest.raises(CounselorsError, match="agent crashed"):
            run_phase1(tmp_path, config, manifest)

        research = manifest.phases["research"]
        assert research.status is PhaseStatus.FAILED


# ---------------------------------------------------------------------------
# 6-7. Phase 2 tests
# ---------------------------------------------------------------------------


class TestRunPhase2:
    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_refinement_prompt")
    def test_run_phase2_generates_correct_session_count(
        self, mock_build_ref, mock_counselors, tmp_path
    ):
        """For 3 agents, 6 sessions (N*(N-1))."""
        _create_phase1_outputs(tmp_path, AGENTS)
        mock_build_ref.return_value = "refinement prompt"

        invocation_count = 0

        def _create_outputs(*args, **kwargs):
            nonlocal invocation_count
            invocation_count += 1
            # Create the output file based on the prompt_file name or output_dir
            _create_phase2_outputs(tmp_path, AGENTS)

        mock_counselors.side_effect = _create_outputs

        manifest = _make_manifest()
        # Mark phase1 as complete so phase2 can proceed
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        config = _make_config()

        result = run_phase2(tmp_path, config, manifest)

        cp = result.phases["cross_pollination"]
        # N*(N-1) = 3*2 = 6 sessions
        assert len(cp.sessions) == 6

    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_refinement_prompt")
    def test_run_phase2_writes_refinement_prompts(
        self, mock_build_ref, mock_counselors, tmp_path
    ):
        """Refinement prompt files are created for each agent-peer pair."""
        _create_phase1_outputs(tmp_path, AGENTS)
        mock_build_ref.return_value = "refinement prompt content"

        def _create_outputs(*args, **kwargs):
            _create_phase2_outputs(tmp_path, AGENTS)

        mock_counselors.side_effect = _create_outputs

        manifest = _make_manifest()
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        config = _make_config()

        run_phase2(tmp_path, config, manifest)

        # build_refinement_prompt called 6 times (3*2)
        assert mock_build_ref.call_count == 6

        # Check that all agent-peer combinations were used
        called_pairs = set()
        for c in mock_build_ref.call_args_list:
            # peer_agent_name is the 4th positional arg
            args = c.args if c.args else ()
            kwargs = c.kwargs if c.kwargs else {}
            peer = kwargs.get("peer_agent_name") or (args[3] if len(args) > 3 else None)
            called_pairs.add(peer)

        # All agents appear as peers
        for agent in AGENTS:
            assert agent in called_pairs


# ---------------------------------------------------------------------------
# 8-9. Phase 3 tests
# ---------------------------------------------------------------------------


class TestRunPhase3:
    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_synthesis_prompt")
    def test_run_phase3_reads_all_refinements(
        self, mock_build_synth, mock_counselors, tmp_path
    ):
        """All phase2 refinement files are read and passed to synthesis prompt."""
        _create_phase2_outputs(tmp_path, AGENTS)
        mock_build_synth.return_value = "synthesis prompt"

        def _create_outputs(*args, **kwargs):
            phase3 = tmp_path / "phase3"
            phase3.mkdir(parents=True, exist_ok=True)
            (phase3 / "final-report.md").write_text("# Final Report\n\nSynthesis...")

        mock_counselors.side_effect = _create_outputs

        manifest = _make_manifest()
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        manifest.phases["cross_pollination"].status = PhaseStatus.COMPLETE
        config = _make_config()

        run_phase3(tmp_path, config, manifest)

        mock_build_synth.assert_called_once()
        synth_call = mock_build_synth.call_args
        # The all_refinement_reports arg should contain content from all 6 files
        all_reports = synth_call.kwargs.get("all_refinement_reports") or synth_call.args[2]
        for agent in AGENTS:
            for peer in AGENTS:
                if agent != peer:
                    assert agent in all_reports

    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_synthesis_prompt")
    def test_run_phase3_uses_synthesizer_agent(
        self, mock_build_synth, mock_counselors, tmp_path
    ):
        """run_counselors called with synthesizer agent, not research agents."""
        _create_phase2_outputs(tmp_path, AGENTS)
        mock_build_synth.return_value = "synthesis prompt"

        def _create_outputs(*args, **kwargs):
            phase3 = tmp_path / "phase3"
            phase3.mkdir(parents=True, exist_ok=True)
            (phase3 / "final-report.md").write_text("# Final Report")

        mock_counselors.side_effect = _create_outputs

        manifest = _make_manifest(synthesizer="codex-5.3-xhigh")
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        manifest.phases["cross_pollination"].status = PhaseStatus.COMPLETE
        config = _make_config(synthesizer="codex-5.3-xhigh")

        run_phase3(tmp_path, config, manifest)

        mock_counselors.assert_called_once()
        call_kwargs = mock_counselors.call_args
        agents_arg = call_kwargs.kwargs.get("agents") or call_kwargs.args[1]
        assert agents_arg == ["codex-5.3-xhigh"]
        # Must NOT contain the research agents
        for agent in AGENTS:
            if agent != "codex-5.3-xhigh":
                assert agent not in agents_arg


# ---------------------------------------------------------------------------
# 10. Pipeline end-to-end
# ---------------------------------------------------------------------------


class TestRunPipeline:
    @patch("ivory_tower.engine.generate_run_id")
    @patch("ivory_tower.engine.create_run_directory")
    @patch("ivory_tower.strategies.council.CouncilStrategy.run")
    @patch("ivory_tower.strategies.council.CouncilStrategy.create_manifest")
    def test_run_pipeline_creates_directory_and_manifest(
        self,
        mock_create_manifest,
        mock_strategy_run,
        mock_create_dir,
        mock_gen_id,
        tmp_path,
    ):
        """End-to-end: pipeline creates dir, manifest, delegates to strategy."""
        run_dir = tmp_path / "research" / "20260301-143000-abc123"
        run_dir.mkdir(parents=True)

        mock_gen_id.return_value = "20260301-143000-abc123"
        mock_create_dir.return_value = run_dir

        manifest = _make_manifest()
        mock_create_manifest.return_value = manifest
        mock_strategy_run.return_value = manifest

        config = _make_config(output_dir=tmp_path / "research")
        result_path = run_pipeline(config)

        # Directory was created
        mock_gen_id.assert_called_once()
        mock_create_dir.assert_called_once()
        mock_create_manifest.assert_called_once()

        # Strategy run was called
        mock_strategy_run.assert_called_once()

        # Returns the run directory
        assert result_path == run_dir

        # topic.md written
        topic_file = run_dir / "topic.md"
        assert topic_file.exists()
        assert TOPIC in topic_file.read_text()


# ---------------------------------------------------------------------------
# 11. Dry run
# ---------------------------------------------------------------------------


class TestDryRun:
    @patch("ivory_tower.engine.run_counselors")
    @patch("ivory_tower.engine.build_research_prompt")
    def test_dry_run_does_not_call_counselors(
        self, mock_build, mock_counselors, capsys
    ):
        """Dry run prints plan but does NOT call counselors."""
        mock_build.return_value = "# Deep Research Task\n\nPrompt preview text here"

        config = _make_config(dry_run=True)
        print_dry_run(config)

        mock_counselors.assert_not_called()

        captured = capsys.readouterr()
        # Should mention agents and synthesizer
        for agent in AGENTS:
            assert agent in captured.out
        assert "claude-opus" in captured.out  # synthesizer
        # Should show prompt preview (first 200 chars)
        assert "Deep Research Task" in captured.out


# ---------------------------------------------------------------------------
# 12-15. Resume pipeline tests
# ---------------------------------------------------------------------------


class TestResumePipeline:
    @patch("ivory_tower.strategies.council.CouncilStrategy.resume")
    def test_resume_skips_completed_research(self, mock_resume, tmp_path):
        """Resume delegates to strategy.resume()."""
        manifest = _make_manifest()
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        manifest.save(tmp_path / "manifest.json")
        (tmp_path / "topic.md").write_text(TOPIC)

        mock_resume.return_value = manifest

        from ivory_tower.engine import resume_pipeline

        resume_pipeline(tmp_path)

        mock_resume.assert_called_once()

    @patch("ivory_tower.strategies.council.CouncilStrategy.resume")
    def test_resume_skips_completed_research_and_cp(self, mock_resume, tmp_path):
        """Resume delegates to strategy even when only synthesis remains."""
        manifest = _make_manifest()
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        manifest.phases["cross_pollination"].status = PhaseStatus.COMPLETE
        manifest.save(tmp_path / "manifest.json")
        (tmp_path / "topic.md").write_text(TOPIC)

        mock_resume.return_value = manifest

        from ivory_tower.engine import resume_pipeline

        resume_pipeline(tmp_path)

        mock_resume.assert_called_once()

    @patch("ivory_tower.strategies.council.CouncilStrategy.resume")
    def test_resume_all_complete_returns_early(self, mock_resume, tmp_path):
        """If all phases complete, strategy.resume() still called (it handles early return)."""
        manifest = _make_manifest()
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        manifest.phases["cross_pollination"].status = PhaseStatus.COMPLETE
        manifest.phases["synthesis"].status = PhaseStatus.COMPLETE
        manifest.save(tmp_path / "manifest.json")
        (tmp_path / "topic.md").write_text(TOPIC)

        mock_resume.return_value = manifest

        from ivory_tower.engine import resume_pipeline

        result = resume_pipeline(tmp_path)

        assert result == tmp_path
        mock_resume.assert_called_once()

    @patch("ivory_tower.strategies.council.CouncilStrategy.resume")
    def test_resume_from_scratch_if_research_incomplete(self, mock_resume, tmp_path):
        """If research not complete, strategy.resume() is called."""
        manifest = _make_manifest()
        manifest.save(tmp_path / "manifest.json")
        (tmp_path / "topic.md").write_text(TOPIC)

        mock_resume.return_value = manifest

        from ivory_tower.engine import resume_pipeline

        resume_pipeline(tmp_path)

        mock_resume.assert_called_once()

    def test_resume_missing_manifest_raises(self, tmp_path):
        """resume_pipeline on dir without manifest -> FileNotFoundError."""
        from ivory_tower.engine import resume_pipeline

        with pytest.raises(FileNotFoundError):
            resume_pipeline(tmp_path)

    @patch("ivory_tower.strategies.council.CouncilStrategy.resume")
    def test_resume_reconstructs_config_from_manifest(self, mock_resume, tmp_path):
        """RunConfig is reconstructed from manifest fields."""
        manifest = _make_manifest()
        manifest.flags = Flags(raw=True, instructions="focus on safety")
        manifest.save(tmp_path / "manifest.json")
        (tmp_path / "topic.md").write_text(TOPIC)

        mock_resume.return_value = manifest

        from ivory_tower.engine import resume_pipeline

        resume_pipeline(tmp_path, verbose=True)

        # Check config passed to strategy.resume()
        call_args = mock_resume.call_args
        config = call_args[0][1]  # second positional arg (run_dir, config, manifest)
        assert config.topic == TOPIC
        assert config.agents == AGENTS
        assert config.synthesizer == "claude-opus"
        assert config.raw is True
        assert config.instructions == "focus on safety"
        assert config.verbose is True
