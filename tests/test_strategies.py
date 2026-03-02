"""Tests for the strategy registry and protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from ivory_tower.strategies import get_strategy, list_strategies, STRATEGIES
from ivory_tower.strategies.base import ResearchStrategy
from ivory_tower.strategies.council import CouncilStrategy
from ivory_tower.executor.types import AgentOutput
from ivory_tower.models import (
    Flags,
    Manifest,
    PhaseStatus,
    ResearchPhase,
    CrossPollinationPhase,
    CrossPollinationSession,
    SynthesisPhase,
    AgentResult,
)
from ivory_tower.engine import RunConfig


# ---------------------------------------------------------------------------
# Helpers for mocking the executor-based council
# ---------------------------------------------------------------------------

def _fake_run_agent(executor, sandbox, agent_name, prompt, output_dir, verbose=False):
    """Mock _run_agent that returns an AgentOutput with synthetic report text."""
    return AgentOutput(
        report_path=f"{output_dir}/{agent_name}-report.md",
        raw_output=f"Report by {agent_name}",
        duration_seconds=1.0,
        metadata={"protocol": "mock"},
    )


def _fake_get_executor(agent_name):
    """Mock _get_executor that returns a MagicMock executor."""
    return MagicMock(name=f"executor-{agent_name}")


def _fake_create_sandbox(run_dir, agent_name, run_id, backend="none"):
    """Mock _create_sandbox that returns a MagicMock sandbox."""
    mock = MagicMock(name=f"sandbox-{agent_name}")
    mock.workspace_dir = run_dir
    return mock


class TestGetStrategy:
    """Tests for get_strategy()."""

    def test_get_council_returns_council_strategy(self):
        strategy = get_strategy("council")
        assert isinstance(strategy, CouncilStrategy)

    def test_get_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown strategy 'unknown'"):
            get_strategy("unknown")

    def test_error_message_lists_available(self):
        with pytest.raises(ValueError, match="Available: "):
            get_strategy("nonexistent")

    def test_returns_fresh_instance_each_call(self):
        a = get_strategy("council")
        b = get_strategy("council")
        assert a is not b


class TestListStrategies:
    """Tests for list_strategies()."""

    def test_returns_list_of_tuples(self):
        result = list_strategies()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_council_in_list(self):
        result = list_strategies()
        names = [name for name, _desc in result]
        assert "council" in names

    def test_descriptions_are_non_empty(self):
        result = list_strategies()
        for _name, desc in result:
            assert desc  # non-empty string


class TestCouncilStrategyAttributes:
    """Tests for CouncilStrategy stub attributes."""

    def test_name(self):
        s = CouncilStrategy()
        assert s.name == "council"

    def test_description(self):
        s = CouncilStrategy()
        assert s.description  # non-empty


# ---------------------------------------------------------------------------
# CouncilStrategy method tests
# ---------------------------------------------------------------------------


class TestCouncilValidate:
    """Tests for CouncilStrategy.validate()."""

    def test_valid_config_returns_empty(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a"
        )
        assert s.validate(config) == []

    def test_rejects_fewer_than_2_agents(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a"], synthesizer="a"
        )
        errors = s.validate(config)
        assert len(errors) > 0
        assert any("2" in e for e in errors)

    def test_rejects_empty_agents(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=[], synthesizer="a"
        )
        errors = s.validate(config)
        assert len(errors) > 0

    def test_rejects_missing_synthesizer(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer=""
        )
        errors = s.validate(config)
        assert len(errors) > 0


class TestCouncilCreateManifest:
    """Tests for CouncilStrategy.create_manifest()."""

    def test_creates_manifest_with_strategy_field(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test topic", agents=["a", "b"], synthesizer="a"
        )
        manifest = s.create_manifest(config, "run-123")
        assert manifest.strategy == "council"

    def test_creates_pending_phases(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test topic", agents=["a", "b"], synthesizer="a"
        )
        manifest = s.create_manifest(config, "run-123")
        assert manifest.phases["research"].status == PhaseStatus.PENDING
        assert manifest.phases["cross_pollination"].status == PhaseStatus.PENDING
        assert manifest.phases["synthesis"].status == PhaseStatus.PENDING

    def test_manifest_has_correct_agents(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test topic", agents=["a", "b"], synthesizer="a"
        )
        manifest = s.create_manifest(config, "run-123")
        assert manifest.agents == ["a", "b"]
        assert manifest.synthesizer == "a"


class TestCouncilRun:
    """Tests for CouncilStrategy.run() with mocked executor."""

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_run_calls_all_three_phases(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a",
            output_dir=tmp_path
        )
        manifest = s.create_manifest(config, "run-123")

        # Setup directories
        run_dir = tmp_path / "run-123"
        for d in ("phase1", "phase2", "phase3", "logs"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        (run_dir / "topic.md").write_text("test")

        result = s.run(run_dir, config, manifest)

        # All phases should be complete
        assert result.phases["research"].status == PhaseStatus.COMPLETE
        assert result.phases["cross_pollination"].status == PhaseStatus.COMPLETE
        assert result.phases["synthesis"].status == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_run_saves_manifest(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a",
            output_dir=tmp_path
        )
        manifest = s.create_manifest(config, "run-123")

        run_dir = tmp_path / "run-123"
        for d in ("phase1", "phase2", "phase3", "logs"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        s.run(run_dir, config, manifest)

        # Manifest should have been saved
        assert (run_dir / "manifest.json").exists()

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_run_writes_reports_from_agent_output(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Agent reports are written from AgentOutput.raw_output, not filesystem scraping."""
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a",
            output_dir=tmp_path
        )
        manifest = s.create_manifest(config, "run-123")

        run_dir = tmp_path / "run-123"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        s.run(run_dir, config, manifest)

        # Phase 1 reports should contain agent output text
        assert (run_dir / "phase1" / "a-report.md").read_text() == "Report by a"
        assert (run_dir / "phase1" / "b-report.md").read_text() == "Report by b"

        # Phase 3 final report should exist
        assert (run_dir / "phase3" / "final-report.md").exists()

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_run_agent_called_for_each_agent_and_phase(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """_run_agent is called for each agent in each phase."""
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a",
            output_dir=tmp_path
        )
        manifest = s.create_manifest(config, "run-123")

        run_dir = tmp_path / "run-123"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        s.run(run_dir, config, manifest)

        # Phase 1: 2 agents, Phase 2: 2 refinements, Phase 3: 1 synthesis
        assert mock_run.call_count == 5


class TestCouncilResume:
    """Tests for CouncilStrategy.resume()."""

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_resume_skips_completed_phases(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a",
            output_dir=tmp_path
        )

        # Create a manifest where research + cross_pollination are done
        manifest = s.create_manifest(config, "run-123")
        manifest.phases["research"].status = PhaseStatus.COMPLETE
        manifest.phases["cross_pollination"].status = PhaseStatus.COMPLETE

        run_dir = tmp_path / "run-123"
        for d in ("phase1", "phase2", "phase3", "logs"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        # Write needed files for synthesis
        (run_dir / "phase2" / "a-cross-b.md").write_text("cross report")

        result = s.resume(run_dir, config, manifest)
        assert result.phases["synthesis"].status == PhaseStatus.COMPLETE

        # Should only have been called once (for synthesis only)
        assert mock_run.call_count == 1


class TestCouncilDryRun:
    """Tests for CouncilStrategy.dry_run()."""

    def test_dry_run_prints_plan(self, capsys):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test topic", agents=["a", "b", "c"], synthesizer="a"
        )
        s.dry_run(config)
        captured = capsys.readouterr()
        assert "Dry Run" in captured.out
        assert "a" in captured.out
        assert "b" in captured.out
        assert "c" in captured.out

    def test_dry_run_shows_session_count(self, capsys):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test topic", agents=["a", "b", "c"], synthesizer="a"
        )
        s.dry_run(config)
        captured = capsys.readouterr()
        # 3 agents = 3 refinement sessions (one per agent)
        assert "3 agents refine reports" in captured.out


class TestCouncilFormatStatus:
    """Tests for CouncilStrategy.format_status()."""

    def test_returns_3_tuples(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a"
        )
        manifest = s.create_manifest(config, "run-123")
        result = s.format_status(manifest)
        assert len(result) == 3
        for label, value in result:
            assert isinstance(label, str)
            assert isinstance(value, str)

    def test_includes_phase_names(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a"
        )
        manifest = s.create_manifest(config, "run-123")
        result = s.format_status(manifest)
        labels = [label.lower() for label, _ in result]
        assert any("research" in l for l in labels)
        assert any("cross" in l or "pollination" in l for l in labels)
        assert any("synthesis" in l for l in labels)


class TestCouncilPhaseSerialization:
    """Tests for CouncilStrategy.phases_to_dict() / phases_from_dict()."""

    def test_roundtrip(self):
        s = CouncilStrategy()
        config = RunConfig(
            topic="test", agents=["a", "b"], synthesizer="a"
        )
        manifest = s.create_manifest(config, "run-123")
        d = s.phases_to_dict(manifest.phases)
        restored = s.phases_from_dict(d)
        assert restored["research"].status == PhaseStatus.PENDING
        assert restored["cross_pollination"].status == PhaseStatus.PENDING
        assert restored["synthesis"].status == PhaseStatus.PENDING
