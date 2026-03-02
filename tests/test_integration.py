"""End-to-end integration tests -- commit 10.

Tests full pipelines (council + adversarial) through run_pipeline/resume_pipeline,
CLI status/list/strategies commands with adversarial manifests, --dry-run --strategy
adversarial, and backward compatibility with v1 manifests (no strategy field).

Council tests mock at the executor layer (_run_agent, _get_executor, _create_sandbox).
Adversarial tests mock at the same executor layer on the adversarial module.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ivory_tower.cli import app
from ivory_tower.engine import ConfigError, RunConfig, resume_pipeline, run_pipeline
from ivory_tower.executor.types import AgentOutput
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
from ivory_tower.strategies import get_strategy

runner = CliRunner()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fake_run_agent(executor, sandbox, agent_name, prompt, output_dir, verbose=False):
    """Mock _run_agent returning AgentOutput for council tests."""
    # Detect judge/evaluation prompts for adversarial compatibility
    if "judg" in prompt.lower() or "evaluat" in prompt.lower():
        judge_data = {
            "overall_score": 7.0,
            "dimensions": {"factual_accuracy": 7},
            "strengths": ["good"],
            "weaknesses": ["could improve"],
            "suggestions": ["add sources"],
            "critique": "solid",
        }
        return AgentOutput(
            report_path=f"{output_dir}/{agent_name}-report.md",
            raw_output=json.dumps(judge_data),
            duration_seconds=1.0,
            metadata={"protocol": "mock"},
        )
    return AgentOutput(
        report_path=f"{output_dir}/{agent_name}-report.md",
        raw_output=f"Report by {agent_name}",
        duration_seconds=1.0,
        metadata={"protocol": "mock"},
    )


def _fake_get_executor(agent_name):
    """Mock _get_executor returning a MagicMock executor."""
    return MagicMock(name=f"executor-{agent_name}")


def _fake_create_sandbox(run_dir, agent_name, run_id, backend="none"):
    """Mock _create_sandbox returning a MagicMock sandbox."""
    mock = MagicMock(name=f"sandbox-{agent_name}")
    mock.workspace_dir = run_dir
    return mock


# Adversarial mock decorators (same pattern as council)
_adversarial_mocks = [
    patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox),
    patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor),
    patch("ivory_tower.strategies.adversarial._run_agent", side_effect=_fake_run_agent),
]


def _fake_gepa_modules():
    """Create fake gepa + gepa.optimize_anything modules matching the real API.

    Returns (gepa_mod, gepa_oa) where gepa_oa has GEPAConfig, EngineConfig,
    ReflectionConfig, and optimize_anything (initially None -- caller must set it).
    """
    gepa_mod = ModuleType("gepa")
    gepa_oa = ModuleType("gepa.optimize_anything")

    @dataclass
    class EngineConfig:
        max_metric_calls: int = 3
        raise_on_exception: bool = True
        frontier_type: str | None = None

    @dataclass
    class ReflectionConfig:
        custom_candidate_proposer: object = None
        reflection_lm: object = None

    @dataclass
    class GEPAConfig:
        engine: EngineConfig = None
        reflection: ReflectionConfig = None

        def __post_init__(self):
            if self.engine is None:
                self.engine = EngineConfig()
            if self.reflection is None:
                self.reflection = ReflectionConfig()

    gepa_oa.EngineConfig = EngineConfig
    gepa_oa.GEPAConfig = GEPAConfig
    gepa_oa.ReflectionConfig = ReflectionConfig
    gepa_oa.optimize_anything = None  # caller sets this

    gepa_mod.optimize_anything = gepa_oa

    return gepa_mod, gepa_oa


def _make_optimize_result(text: str = "Optimized report", score: float = 8.0):
    """Create a mock GEPAResult matching the real API."""
    result = MagicMock()
    result.val_aggregate_scores = [score - 2.0, score]
    result.best_idx = 1
    result.best_candidate = {"report": text}
    result.candidates = [{"report": "seed"}, {"report": text}]
    result.total_metric_calls = 2
    return result


def _patch_gepa_import(gepa_mod, gepa_oa):
    """Return a context manager that injects fake gepa modules into sys.modules.

    This ensures ``from gepa.optimize_anything import ...`` resolves to our
    fakes even when the real gepa package is installed.
    """
    return patch.dict(sys.modules, {
        "gepa": gepa_mod,
        "gepa.optimize_anything": gepa_oa,
    })


# Council mock decorators (applied to all council tests)
_council_mocks = [
    patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox),
    patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor),
    patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent),
]


def _apply_council_mocks(fn):
    """Apply all council executor mocks to a test function."""
    for decorator in reversed(_council_mocks):
        fn = decorator(fn)
    return fn


# ---------------------------------------------------------------------------
# 1. Full council pipeline with mocked executor
# ---------------------------------------------------------------------------


class TestCouncilPipelineE2E:
    """Full council pipeline through run_pipeline()."""

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_full_council_pipeline(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        config = RunConfig(
            topic="Integration test: AI safety",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            output_dir=tmp_path,
            strategy="council",
        )

        run_dir = run_pipeline(config)

        # Run dir created
        assert run_dir.exists()
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "topic.md").exists()

        # Manifest is complete
        manifest = Manifest.load(run_dir / "manifest.json")
        assert manifest.strategy == "council"
        assert manifest.phases["research"].status == PhaseStatus.COMPLETE
        assert manifest.phases["cross_pollination"].status == PhaseStatus.COMPLETE
        assert manifest.phases["synthesis"].status == PhaseStatus.COMPLETE
        assert manifest.total_duration_seconds is not None

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_council_pipeline_creates_output_files(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        config = RunConfig(
            topic="E2E test",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            output_dir=tmp_path,
            strategy="council",
        )
        run_dir = run_pipeline(config)

        # Phase 1 outputs
        phase1 = run_dir / "phase1"
        assert phase1.exists()

        # Phase 3 final report
        phase3 = run_dir / "phase3"
        assert phase3.exists()


# ---------------------------------------------------------------------------
# 2. Full adversarial pipeline with mocked counselors + GEPA
# ---------------------------------------------------------------------------


class TestAdversarialPipelineE2E:
    """Full adversarial pipeline through run_pipeline()."""

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent", side_effect=_fake_run_agent)
    def test_full_adversarial_pipeline(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        config = RunConfig(
            topic="Integration test: adversarial AI safety",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            output_dir=tmp_path,
            strategy="adversarial",
            max_rounds=2,
        )

        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = MagicMock(
            return_value=_make_optimize_result()
        )

        with _patch_gepa_import(gepa_mod, gepa_oa):
            run_dir = run_pipeline(config)

        assert run_dir.exists()
        manifest = Manifest.load(run_dir / "manifest.json")
        assert manifest.strategy == "adversarial"
        assert manifest.phases["seed_generation"].status == PhaseStatus.COMPLETE
        assert manifest.phases["adversarial_optimization"].status in (
            PhaseStatus.COMPLETE, PhaseStatus.PARTIAL
        )
        assert manifest.phases["synthesis"].status == PhaseStatus.COMPLETE
        assert manifest.total_duration_seconds is not None

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent", side_effect=_fake_run_agent)
    def test_adversarial_pipeline_creates_output_files(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        config = RunConfig(
            topic="File check test",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            output_dir=tmp_path,
            strategy="adversarial",
            max_rounds=1,
        )

        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = MagicMock(
            return_value=_make_optimize_result()
        )

        with _patch_gepa_import(gepa_mod, gepa_oa):
            run_dir = run_pipeline(config)

        # Seed outputs in phase1
        assert (run_dir / "phase1").exists()

        # Optimized reports in phase2
        assert (run_dir / "phase2" / "agent-a-optimized.md").exists()
        assert (run_dir / "phase2" / "agent-b-optimized.md").exists()

        # Optimization logs
        assert (run_dir / "phase2" / "agent-a-optimization-log.json").exists()
        assert (run_dir / "phase2" / "agent-b-optimization-log.json").exists()

        # Final report
        assert (run_dir / "phase3").exists()

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent", side_effect=_fake_run_agent)
    def test_adversarial_pipeline_manifest_serialization_roundtrip(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Manifest saved by adversarial pipeline can be loaded and re-serialized."""
        config = RunConfig(
            topic="Roundtrip test",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            output_dir=tmp_path,
            strategy="adversarial",
            max_rounds=1,
        )

        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = MagicMock(
            return_value=_make_optimize_result()
        )

        with _patch_gepa_import(gepa_mod, gepa_oa):
            run_dir = run_pipeline(config)

        # Load, re-save, load again -- should be identical
        m1 = Manifest.load(run_dir / "manifest.json")
        m1.save(run_dir / "manifest-copy.json")
        m2 = Manifest.load(run_dir / "manifest-copy.json")

        assert m1.strategy == m2.strategy
        assert m1.run_id == m2.run_id
        assert m1.phases["seed_generation"].status == m2.phases["seed_generation"].status


# ---------------------------------------------------------------------------
# 3. Resume partial adversarial run
# ---------------------------------------------------------------------------


class TestResumeAdversarial:
    """Resume a partially-completed adversarial run."""

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent", side_effect=_fake_run_agent)
    def test_resume_partial_adversarial(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Resume where seed gen is done but optimization + synthesis are pending."""
        run_dir = tmp_path / "run-adv-resume"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        # Write seed reports
        (run_dir / "phase1" / "agent-a-seed.md").write_text("Seed report A")
        (run_dir / "phase1" / "agent-b-seed.md").write_text("Seed report B")

        # Create partial manifest: seed gen done, rest pending
        strat = get_strategy("adversarial")
        config = RunConfig(
            topic="Resume test",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            strategy="adversarial",
            max_rounds=2,
            output_dir=tmp_path,
        )
        manifest = strat.create_manifest(config, "run-adv-resume")
        manifest.phases["seed_generation"].status = PhaseStatus.COMPLETE
        manifest.save(run_dir / "manifest.json")
        (run_dir / "topic.md").write_text("Resume test")

        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = MagicMock(
            return_value=_make_optimize_result()
        )

        with _patch_gepa_import(gepa_mod, gepa_oa):
            result_dir = resume_pipeline(run_dir)

        loaded = Manifest.load(result_dir / "manifest.json")
        assert loaded.phases["adversarial_optimization"].status in (
            PhaseStatus.COMPLETE, PhaseStatus.PARTIAL
        )
        assert loaded.phases["synthesis"].status == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent", side_effect=_fake_run_agent)
    def test_resume_fully_complete_adversarial_is_noop(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Resuming a fully complete run doesn't re-run anything."""
        run_dir = tmp_path / "run-adv-complete"
        run_dir.mkdir(parents=True)

        strat = get_strategy("adversarial")
        config = RunConfig(
            topic="Complete test",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            strategy="adversarial",
            max_rounds=2,
            output_dir=tmp_path,
        )
        manifest = strat.create_manifest(config, "run-adv-complete")
        manifest.phases["seed_generation"].status = PhaseStatus.COMPLETE
        manifest.phases["adversarial_optimization"].status = PhaseStatus.COMPLETE
        manifest.phases["synthesis"].status = PhaseStatus.COMPLETE
        manifest.save(run_dir / "manifest.json")
        (run_dir / "topic.md").write_text("Complete test")

        resume_pipeline(run_dir)
        # No agent calls should have been made
        assert mock_run.call_count == 0


# ---------------------------------------------------------------------------
# 4. CLI: ivory status / list / strategies for adversarial
# ---------------------------------------------------------------------------


class TestCLIStatusAdversarial:
    """ivory status for an adversarial run."""

    def test_status_shows_adversarial_strategy(self, tmp_path):
        strat = get_strategy("adversarial")
        config = RunConfig(
            topic="CLI status test adversarial",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            strategy="adversarial",
            max_rounds=3,
        )
        manifest = strat.create_manifest(config, "run-status-adv")
        manifest.phases["seed_generation"].status = PhaseStatus.COMPLETE
        manifest.save(tmp_path / "manifest.json")

        result = runner.invoke(app, ["status", str(tmp_path)])
        assert result.exit_code == 0
        assert "adversarial" in result.output.lower()
        assert "run-status-adv" in result.output
        assert "seed" in result.output.lower()

    def test_status_shows_council_strategy(self, tmp_path):
        manifest = Manifest(
            run_id="run-status-council",
            topic="CLI status test council",
            agents=["a", "b"],
            synthesizer="a",
            flags=Flags(),
            phases={
                "research": ResearchPhase(status=PhaseStatus.COMPLETE),
                "cross_pollination": CrossPollinationPhase(status=PhaseStatus.PENDING),
                "synthesis": SynthesisPhase(
                    status=PhaseStatus.PENDING, agent="a", output="phase3/final-report.md"
                ),
            },
            strategy="council",
        )
        manifest.save(tmp_path / "manifest.json")

        result = runner.invoke(app, ["status", str(tmp_path)])
        assert result.exit_code == 0
        assert "council" in result.output.lower()


class TestCLIListAdversarial:
    """ivory list shows adversarial runs."""

    def test_list_shows_adversarial_and_council(self, tmp_path):
        # Create a council run
        council_dir = tmp_path / "run-council"
        council_dir.mkdir()
        Manifest(
            run_id="run-council",
            topic="Council topic",
            agents=["a", "b"],
            synthesizer="a",
            flags=Flags(),
            phases={
                "research": ResearchPhase(status=PhaseStatus.COMPLETE),
                "cross_pollination": CrossPollinationPhase(status=PhaseStatus.COMPLETE),
                "synthesis": SynthesisPhase(
                    status=PhaseStatus.COMPLETE, agent="a", output="phase3/final-report.md"
                ),
            },
            strategy="council",
        ).save(council_dir / "manifest.json")

        # Create an adversarial run
        adv_dir = tmp_path / "run-adv"
        adv_dir.mkdir()
        strat = get_strategy("adversarial")
        config = RunConfig(
            topic="Adversarial topic",
            agents=["a", "b"],
            synthesizer="a",
            strategy="adversarial",
        )
        adv_manifest = strat.create_manifest(config, "run-adv")
        adv_manifest.save(adv_dir / "manifest.json")

        result = runner.invoke(app, ["list", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "council" in result.output.lower()
        assert "adversarial" in result.output.lower()


class TestCLIStrategies:
    """ivory strategies command."""

    def test_strategies_lists_both(self):
        result = runner.invoke(app, ["strategies"])
        assert result.exit_code == 0
        assert "council" in result.output
        assert "adversarial" in result.output

    def test_strategies_shows_descriptions(self):
        result = runner.invoke(app, ["strategies"])
        assert result.exit_code == 0
        # Both should have descriptions
        lines = result.output.strip().split("\n")
        # Header + separator + at least 2 strategies
        assert len(lines) >= 4


# ---------------------------------------------------------------------------
# 5. --dry-run --strategy adversarial
# ---------------------------------------------------------------------------


class TestDryRunAdversarial:
    """--dry-run --strategy adversarial via CLI."""

    @patch("ivory_tower.cli.validate_agent_configs", return_value=[])
    def test_dry_run_adversarial(self, mock_validate):
        result = runner.invoke(app, [
            "research",
            "Test adversarial dry run",
            "--agents", "a,b",
            "--synthesizer", "a",
            "--strategy", "adversarial",
            "--max-rounds", "5",
            "--dry-run",
        ])
        assert result.exit_code == 0
        out = result.output.lower()
        assert "adversarial" in out
        assert "5" in result.output  # max rounds

    @patch("ivory_tower.cli.validate_agent_configs", return_value=[])
    def test_dry_run_council(self, mock_validate):
        result = runner.invoke(app, [
            "research",
            "Test council dry run",
            "--agents", "a,b",
            "--synthesizer", "a",
            "--strategy", "council",
            "--dry-run",
        ])
        assert result.exit_code == 0
        out = result.output.lower()
        assert "dry run" in out

    @patch("ivory_tower.cli.validate_agent_configs", return_value=[])
    def test_dry_run_unknown_strategy_errors(self, mock_validate):
        result = runner.invoke(app, [
            "research",
            "Test unknown strategy",
            "--agents", "a,b",
            "--synthesizer", "a",
            "--strategy", "unknown",
            "--dry-run",
        ])
        assert result.exit_code != 0
        assert "unknown" in result.output.lower()


# ---------------------------------------------------------------------------
# 6. Backward compat: resume a v1 manifest (no strategy field)
# ---------------------------------------------------------------------------


class TestBackwardCompatV1Manifest:
    """Resume a v1 manifest that has no strategy field -- should default to council."""

    @patch("ivory_tower.strategies.council._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.council._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.council._run_agent", side_effect=_fake_run_agent)
    def test_resume_v1_manifest_defaults_to_council(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """A manifest without 'strategy' key should be treated as council."""
        run_dir = tmp_path / "run-v1"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        # Write phase1 reports
        (run_dir / "phase1" / "a-report.md").write_text("Report A")
        (run_dir / "phase1" / "b-report.md").write_text("Report B")

        # Write phase2 cross-pollination reports (for synthesis)
        (run_dir / "phase2" / "a-cross-b.md").write_text("A reviews B")
        (run_dir / "phase2" / "b-cross-a.md").write_text("B reviews A")

        # Build a v1 manifest dict (no strategy field)
        v1_dict = {
            "run_id": "run-v1",
            "topic": "V1 backward compat test",
            "agents": ["a", "b"],
            "synthesizer": "a",
            "flags": {
                "raw": False,
                "instructions": None,
                "verbose": False,
                # no max_rounds
            },
            "phases": {
                "research": {
                    "status": "complete",
                    "started_at": None,
                    "completed_at": None,
                    "duration_seconds": None,
                    "agents": {
                        "a": {"status": "complete", "duration_seconds": 1.0, "output": "phase1/a-report.md"},
                        "b": {"status": "complete", "duration_seconds": 1.0, "output": "phase1/b-report.md"},
                    },
                },
                "cross_pollination": {
                    "status": "complete",
                    "started_at": None,
                    "completed_at": None,
                    "duration_seconds": None,
                    "sessions": {
                        "a-cross-b": {"status": "complete", "duration_seconds": 1.0, "output": "phase2/a-cross-b.md"},
                        "b-cross-a": {"status": "complete", "duration_seconds": 1.0, "output": "phase2/b-cross-a.md"},
                    },
                },
                "synthesis": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "duration_seconds": None,
                    "agent": "a",
                    "output": "phase3/final-report.md",
                },
            },
            "total_duration_seconds": None,
        }

        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(v1_dict, indent=2))
        (run_dir / "topic.md").write_text("V1 backward compat test")

        # Resume should work: defaults to council strategy
        result_dir = resume_pipeline(run_dir)
        loaded = Manifest.load(result_dir / "manifest.json")
        assert loaded.strategy == "council"
        assert loaded.phases["synthesis"].status == PhaseStatus.COMPLETE

    def test_load_v1_manifest_defaults_strategy_to_council(self, tmp_path):
        """Manifest.from_dict() without strategy key defaults to 'council'."""
        v1_dict = {
            "run_id": "run-v1-load",
            "topic": "Load test",
            "agents": ["a", "b"],
            "synthesizer": "a",
            "flags": {"raw": False, "instructions": None, "verbose": False},
            "phases": {
                "research": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "duration_seconds": None,
                    "agents": {},
                },
                "cross_pollination": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "duration_seconds": None,
                    "sessions": {},
                },
                "synthesis": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "duration_seconds": None,
                    "agent": "a",
                    "output": "phase3/final-report.md",
                },
            },
        }

        m = Manifest.from_dict(v1_dict)
        assert m.strategy == "council"
        assert m.flags.max_rounds == 10  # default

    def test_v1_manifest_flags_default_max_rounds(self, tmp_path):
        """V1 flags without max_rounds should default to 10."""
        v1_dict = {
            "run_id": "run-v1-flags",
            "topic": "Flags test",
            "agents": ["a", "b"],
            "synthesizer": "a",
            "flags": {"raw": False, "instructions": None, "verbose": False},
            "phases": {
                "research": {"status": "pending", "started_at": None, "completed_at": None, "duration_seconds": None, "agents": {}},
                "cross_pollination": {"status": "pending", "started_at": None, "completed_at": None, "duration_seconds": None, "sessions": {}},
                "synthesis": {"status": "pending", "started_at": None, "completed_at": None, "duration_seconds": None, "agent": "a", "output": "phase3/final-report.md"},
            },
        }

        m = Manifest.from_dict(v1_dict)
        assert m.flags.max_rounds == 10


# ---------------------------------------------------------------------------
# 7. Config validation through run_pipeline
# ---------------------------------------------------------------------------


class TestConfigValidation:
    """run_pipeline raises ConfigError on invalid config."""

    def test_council_rejects_1_agent(self, tmp_path):
        config = RunConfig(
            topic="test",
            agents=["only-one"],
            synthesizer="only-one",
            output_dir=tmp_path,
            strategy="council",
        )
        with pytest.raises(ConfigError):
            run_pipeline(config)

    def test_unknown_strategy_raises(self, tmp_path):
        config = RunConfig(
            topic="test",
            agents=["a", "b"],
            synthesizer="a",
            output_dir=tmp_path,
            strategy="nonexistent",
        )
        with pytest.raises(ValueError, match="Unknown strategy"):
            run_pipeline(config)


# ---------------------------------------------------------------------------
# 8. CLI resume for adversarial
# ---------------------------------------------------------------------------


class TestCLIResumeAdversarial:
    """ivory resume on adversarial manifests."""

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent", side_effect=_fake_run_agent)
    def test_cli_resume_adversarial(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        run_dir = tmp_path / "run-cli-resume"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)

        # Seed reports
        (run_dir / "phase1" / "agent-a-seed.md").write_text("Seed A")
        (run_dir / "phase1" / "agent-b-seed.md").write_text("Seed B")

        strat = get_strategy("adversarial")
        config = RunConfig(
            topic="CLI resume test",
            agents=["agent-a", "agent-b"],
            synthesizer="agent-a",
            strategy="adversarial",
            max_rounds=1,
        )
        manifest = strat.create_manifest(config, "run-cli-resume")
        # Mark seed_generation and adversarial_optimization as done
        manifest.phases["seed_generation"].status = PhaseStatus.COMPLETE
        manifest.phases["adversarial_optimization"].status = PhaseStatus.PARTIAL
        # Write optimized reports (fallback from partial)
        (run_dir / "phase2" / "agent-a-optimized.md").write_text("Partial A")
        (run_dir / "phase2" / "agent-b-optimized.md").write_text("Partial B")

        manifest.save(run_dir / "manifest.json")
        (run_dir / "topic.md").write_text("CLI resume test")

        result = runner.invoke(app, ["resume", str(run_dir)])
        assert result.exit_code == 0
        assert "resumed" in result.output.lower() or "report" in result.output.lower()
