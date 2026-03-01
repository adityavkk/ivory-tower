"""Tests for ivory_tower.engine -- pipeline orchestration.

NOTE: Phase-level tests (run_phase1/2/3) were removed as part of the v2
cleanup.  Those functions now live inside CouncilStrategy and are covered
by tests/test_strategies.py.  This file focuses on RunConfig, run_pipeline,
resume_pipeline, print_dry_run, and ConfigError.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

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
from ivory_tower.engine import (
    RunConfig,
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
# 2. Pipeline end-to-end
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
# 3. Dry run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_prints_plan_without_calling_counselors(self, capsys):
        """Dry run delegates to strategy.dry_run() -- no network calls."""
        config = _make_config(dry_run=True)
        print_dry_run(config)

        captured = capsys.readouterr()
        # Should mention agents and synthesizer
        for agent in AGENTS:
            assert agent in captured.out
        assert "claude-opus" in captured.out  # synthesizer


# ---------------------------------------------------------------------------
# 4. Resume pipeline tests
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
