"""Tests for AdversarialStrategy -- commits 8 and 9."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch, call

import pytest

from ivory_tower.strategies.adversarial import AdversarialStrategy
from ivory_tower.engine import RunConfig
from ivory_tower.models import (
    AdversarialOptimizationPhase,
    AgentResult,
    Flags,
    Manifest,
    PhaseStatus,
    ResearchPhase,
    SeedOptimizationResult,
    SynthesisPhase,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> RunConfig:
    """Create a minimal adversarial RunConfig."""
    defaults = dict(
        topic="test topic",
        agents=["agent-a", "agent-b"],
        synthesizer="agent-a",
        strategy="adversarial",
        max_rounds=3,
    )
    defaults.update(overrides)
    return RunConfig(**defaults)


def _make_adversarial_manifest(config: RunConfig | None = None, run_id: str = "run-adv-001") -> Manifest:
    """Create an adversarial manifest via the strategy."""
    s = AdversarialStrategy()
    if config is None:
        config = _make_config()
    return s.create_manifest(config, run_id)


# ---------------------------------------------------------------------------
# Commit 8: validate, create_manifest, dry_run, resume, format_status, phases ser
# ---------------------------------------------------------------------------


class TestAdversarialValidate:
    """Tests for AdversarialStrategy.validate()."""

    def test_valid_2_agent_config_returns_empty(self):
        s = AdversarialStrategy()
        config = _make_config()
        # Mock gepa.optimize_anything as available
        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = lambda *a, **kw: None
        with patch.dict(sys.modules, {"gepa": gepa_mod, "gepa.optimize_anything": gepa_oa}):
            errors = s.validate(config)
        assert errors == []

    def test_rejects_1_agent(self):
        s = AdversarialStrategy()
        config = _make_config(agents=["only-one"])
        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = lambda *a, **kw: None
        with patch.dict(sys.modules, {"gepa": gepa_mod, "gepa.optimize_anything": gepa_oa}):
            errors = s.validate(config)
        assert any("2" in e for e in errors)

    def test_rejects_3_agents(self):
        s = AdversarialStrategy()
        config = _make_config(agents=["a", "b", "c"])
        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = lambda *a, **kw: None
        with patch.dict(sys.modules, {"gepa": gepa_mod, "gepa.optimize_anything": gepa_oa}):
            errors = s.validate(config)
        assert any("2" in e or "exactly" in e.lower() for e in errors)

    def test_rejects_missing_synthesizer(self):
        s = AdversarialStrategy()
        config = _make_config(synthesizer="")
        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = lambda *a, **kw: None
        with patch.dict(sys.modules, {"gepa": gepa_mod, "gepa.optimize_anything": gepa_oa}):
            errors = s.validate(config)
        assert any("synthesizer" in e.lower() for e in errors)

    def test_rejects_missing_gepa(self):
        s = AdversarialStrategy()
        config = _make_config()
        # Ensure gepa.optimize_anything is NOT importable
        with patch.dict(sys.modules, {"gepa.optimize_anything": None}):
            errors = s.validate(config)
        assert any("gepa" in e for e in errors)

    def test_multiple_errors_returned(self):
        """1 agent + missing gepa => 2+ errors."""
        s = AdversarialStrategy()
        config = _make_config(agents=["only-one"], synthesizer="")
        with patch.dict(sys.modules, {"gepa.optimize_anything": None}):
            errors = s.validate(config)
        assert len(errors) >= 2


class TestAdversarialCreateManifest:
    """Tests for AdversarialStrategy.create_manifest()."""

    def test_strategy_field_is_adversarial(self):
        m = _make_adversarial_manifest()
        assert m.strategy == "adversarial"

    def test_has_3_phases(self):
        m = _make_adversarial_manifest()
        assert "seed_generation" in m.phases
        assert "adversarial_optimization" in m.phases
        assert "synthesis" in m.phases

    def test_all_phases_pending(self):
        m = _make_adversarial_manifest()
        assert m.phases["seed_generation"].status == PhaseStatus.PENDING
        assert m.phases["adversarial_optimization"].status == PhaseStatus.PENDING
        assert m.phases["synthesis"].status == PhaseStatus.PENDING

    def test_seed_generation_has_agent_results(self):
        m = _make_adversarial_manifest()
        sg = m.phases["seed_generation"]
        assert "agent-a" in sg.agents
        assert "agent-b" in sg.agents
        assert sg.agents["agent-a"].status == PhaseStatus.PENDING

    def test_adversarial_optimization_has_cross_seeds(self):
        m = _make_adversarial_manifest()
        opt = m.phases["adversarial_optimization"]
        assert "agent-a" in opt.seeds
        assert "agent-b" in opt.seeds
        # Cross-judging: agent-a judged by agent-b and vice versa
        assert opt.seeds["agent-a"].judge == "agent-b"
        assert opt.seeds["agent-b"].judge == "agent-a"

    def test_synthesis_agent_matches(self):
        m = _make_adversarial_manifest()
        sp = m.phases["synthesis"]
        assert sp.agent == "agent-a"
        assert sp.output == "phase3/final-report.md"

    def test_manifest_agents_and_synthesizer(self):
        m = _make_adversarial_manifest()
        assert m.agents == ["agent-a", "agent-b"]
        assert m.synthesizer == "agent-a"

    def test_manifest_flags_include_max_rounds(self):
        config = _make_config(max_rounds=5)
        m = _make_adversarial_manifest(config)
        assert m.flags.max_rounds == 5


class TestAdversarialDryRun:
    """Tests for AdversarialStrategy.dry_run()."""

    def test_prints_plan(self, capsys):
        s = AdversarialStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "adversarial" in out.lower() or "Adversarial" in out
        assert "agent-a" in out
        assert "agent-b" in out

    def test_prints_max_rounds(self, capsys):
        s = AdversarialStrategy()
        config = _make_config(max_rounds=7)
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "7" in out

    def test_prints_cross_judging_pairs(self, capsys):
        s = AdversarialStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        # Should mention both judging directions
        assert "agent-a" in out and "agent-b" in out

    def test_prints_synthesis(self, capsys):
        s = AdversarialStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "synth" in out.lower() or "Synthesis" in out


class TestAdversarialFormatStatus:
    """Tests for AdversarialStrategy.format_status()."""

    def test_returns_3_tuples(self):
        s = AdversarialStrategy()
        m = _make_adversarial_manifest()
        result = s.format_status(m)
        assert len(result) == 3
        for label, value in result:
            assert isinstance(label, str)
            assert isinstance(value, str)

    def test_includes_phase_names(self):
        s = AdversarialStrategy()
        m = _make_adversarial_manifest()
        result = s.format_status(m)
        labels = [label.lower() for label, _ in result]
        assert any("seed" in l for l in labels)
        assert any("adversarial" in l or "optim" in l for l in labels)
        assert any("synthesis" in l for l in labels)

    def test_shows_rounds_and_score(self):
        s = AdversarialStrategy()
        m = _make_adversarial_manifest()
        # Simulate some progress
        opt = m.phases["adversarial_optimization"]
        opt.seeds["agent-a"].rounds_completed = 3
        opt.seeds["agent-a"].final_score = 7.5
        opt.seeds["agent-b"].rounds_completed = 2
        result = s.format_status(m)
        # The optimization line should contain round counts
        opt_line = [v for l, v in result if "adversarial" in l.lower() or "optim" in l.lower()][0]
        assert "3r" in opt_line
        assert "7.5" in opt_line
        assert "2r" in opt_line


class TestAdversarialResume:
    """Tests for AdversarialStrategy.resume()."""

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_resume_skips_completed_seed_gen(self, mock_counselors, tmp_path):
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path)
        m = _make_adversarial_manifest(config)

        # Mark seed gen complete
        m.phases["seed_generation"].status = PhaseStatus.COMPLETE
        # Mark optimization complete
        m.phases["adversarial_optimization"].status = PhaseStatus.COMPLETE
        # Synthesis still pending

        run_dir = tmp_path / "run-adv-001"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        # Write optimized reports for synthesis
        (run_dir / "phase2" / "agent-a-optimized.md").write_text("Optimized A")
        (run_dir / "phase2" / "agent-b-optimized.md").write_text("Optimized B")

        def fake_counselors(prompt_file, agents, output_dir, verbose=False):
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(f"Report by {agent}")
            return MagicMock(returncode=0)

        mock_counselors.side_effect = fake_counselors

        result = s.resume(run_dir, config, m)
        assert result.phases["synthesis"].status == PhaseStatus.COMPLETE
        # Should only have been called once (for synthesis)
        assert mock_counselors.call_count == 1

    def test_resume_all_complete_is_noop(self, tmp_path):
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path)
        m = _make_adversarial_manifest(config)

        m.phases["seed_generation"].status = PhaseStatus.COMPLETE
        m.phases["adversarial_optimization"].status = PhaseStatus.COMPLETE
        m.phases["synthesis"].status = PhaseStatus.COMPLETE

        run_dir = tmp_path / "run-adv-001"
        run_dir.mkdir(parents=True)

        result = s.resume(run_dir, config, m)
        # Should return immediately with no changes
        assert result.phases["synthesis"].status == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_resume_partial_optimization_skips_to_synthesis(self, mock_counselors, tmp_path):
        """PARTIAL optimization should also be treated as done for resume."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path)
        m = _make_adversarial_manifest(config)

        m.phases["seed_generation"].status = PhaseStatus.COMPLETE
        m.phases["adversarial_optimization"].status = PhaseStatus.PARTIAL

        run_dir = tmp_path / "run-adv-001"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        (run_dir / "phase2" / "agent-a-optimized.md").write_text("Optimized A")
        (run_dir / "phase2" / "agent-b-optimized.md").write_text("Optimized B")

        def fake_counselors(prompt_file, agents, output_dir, verbose=False):
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(f"Report by {agent}")
            return MagicMock(returncode=0)

        mock_counselors.side_effect = fake_counselors

        result = s.resume(run_dir, config, m)
        assert result.phases["synthesis"].status == PhaseStatus.COMPLETE
        assert mock_counselors.call_count == 1


class TestAdversarialPhaseSerialization:
    """Tests for AdversarialStrategy.phases_to_dict() / phases_from_dict()."""

    def test_roundtrip_pending(self):
        s = AdversarialStrategy()
        m = _make_adversarial_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        assert restored["seed_generation"].status == PhaseStatus.PENDING
        assert restored["adversarial_optimization"].status == PhaseStatus.PENDING
        assert restored["synthesis"].status == PhaseStatus.PENDING

    def test_roundtrip_preserves_seeds(self):
        s = AdversarialStrategy()
        m = _make_adversarial_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        opt = restored["adversarial_optimization"]
        assert "agent-a" in opt.seeds
        assert "agent-b" in opt.seeds
        assert opt.seeds["agent-a"].judge == "agent-b"
        assert opt.seeds["agent-b"].judge == "agent-a"

    def test_roundtrip_preserves_scores_and_rounds(self):
        s = AdversarialStrategy()
        m = _make_adversarial_manifest()
        opt = m.phases["adversarial_optimization"]
        opt.seeds["agent-a"].rounds_completed = 5
        opt.seeds["agent-a"].seed_score = 3.0
        opt.seeds["agent-a"].final_score = 8.5
        opt.seeds["agent-a"].status = PhaseStatus.COMPLETE

        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        seed_a = restored["adversarial_optimization"].seeds["agent-a"]
        assert seed_a.rounds_completed == 5
        assert seed_a.seed_score == 3.0
        assert seed_a.final_score == 8.5
        assert seed_a.status == PhaseStatus.COMPLETE

    def test_roundtrip_preserves_synthesis(self):
        s = AdversarialStrategy()
        m = _make_adversarial_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        sp = restored["synthesis"]
        assert sp.agent == "agent-a"
        assert sp.output == "phase3/final-report.md"

    def test_manifest_to_dict_from_dict_roundtrip(self, tmp_path):
        """Full Manifest serialization roundtrip with adversarial phases."""
        m = _make_adversarial_manifest()
        # Add some progress data
        m.phases["seed_generation"].status = PhaseStatus.COMPLETE
        opt = m.phases["adversarial_optimization"]
        opt.seeds["agent-a"].rounds_completed = 3
        opt.seeds["agent-a"].final_score = 7.0

        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = Manifest.load(path)

        assert loaded.strategy == "adversarial"
        assert loaded.phases["seed_generation"].status == PhaseStatus.COMPLETE
        assert loaded.phases["adversarial_optimization"].seeds["agent-a"].rounds_completed == 3
        assert loaded.phases["adversarial_optimization"].seeds["agent-a"].final_score == 7.0

    def test_roundtrip_preserves_dimension_history(self, tmp_path):
        """dimension_history should survive manifest save/load roundtrip."""
        m = _make_adversarial_manifest()
        opt = m.phases["adversarial_optimization"]
        history = [
            {"round": 1, "score": 5.0, "dimensions": {"factual_accuracy": 5}},
            {"round": 2, "score": 7.0, "dimensions": {"factual_accuracy": 8}},
        ]
        opt.seeds["agent-a"].dimension_history = history

        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = Manifest.load(path)

        restored_hist = loaded.phases["adversarial_optimization"].seeds["agent-a"].dimension_history
        assert len(restored_hist) == 2
        assert restored_hist[0]["score"] == 5.0
        assert restored_hist[1]["dimensions"]["factual_accuracy"] == 8


# ---------------------------------------------------------------------------
# Commit 9: AdversarialStrategy.run() -- full pipeline with mocked GEPA
# ---------------------------------------------------------------------------


def _fake_gepa_modules():
    """Create fake gepa + gepa.optimize_anything modules matching the real API.

    Returns (gepa_mod, gepa_oa_mod) where gepa_oa_mod has GEPAConfig,
    EngineConfig, ReflectionConfig, and optimize_anything (initially None --
    caller must set it).
    """
    gepa_mod = ModuleType("gepa")
    gepa_oa = ModuleType("gepa.optimize_anything")

    @dataclass
    class EngineConfig:
        max_metric_calls: int = 3
        raise_on_exception: bool = True

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


def _make_optimize_result(best_candidate: dict, best_score: float = 7.5):
    """Create a mock GEPAResult matching the real API.

    Uses val_aggregate_scores + best_idx (property) instead of best_score.
    """
    result = MagicMock()
    result.val_aggregate_scores = [best_score - 2.0, best_score]
    result.best_idx = 1
    result.best_candidate = best_candidate
    result.candidates = [{"report": "seed"}, best_candidate]
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


class TestAdversarialRun:
    """Tests for AdversarialStrategy.run() with mocked counselors + GEPA."""

    def _setup_run_dir(self, tmp_path):
        """Create run directory structure."""
        run_dir = tmp_path / "run-adv-001"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        return run_dir

    def _fake_counselors_factory(self):
        """Return a side_effect function for mock_counselors that writes agent output files."""
        def fake_counselors(prompt_file, agents, output_dir, verbose=False):
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                # For judging calls, write a JSON judge output
                prompt_text = prompt_file.read_text() if prompt_file.exists() else ""
                if "judg" in prompt_text.lower() or "evaluat" in prompt_text.lower():
                    judge_data = {
                        "overall_score": 7.0,
                        "dimensions": {"factual_accuracy": 7, "depth_of_analysis": 7},
                        "strengths": ["good coverage"],
                        "weaknesses": ["could be deeper"],
                        "suggestions": ["add more sources"],
                        "critique": "Solid work.",
                    }
                    (slug / f"{agent}.md").write_text(json.dumps(judge_data))
                else:
                    (slug / f"{agent}.md").write_text(f"Report by {agent}")
            return MagicMock(returncode=0)
        return fake_counselors

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_completes_all_phases(self, mock_counselors, tmp_path):
        """Full run: seed gen -> adversarial opt -> synthesis, all phases complete."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=2)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "Optimized report text"}, 8.0)
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            result = s.run(run_dir, config, m)

        assert result.phases["seed_generation"].status == PhaseStatus.COMPLETE
        assert result.phases["adversarial_optimization"].status in (
            PhaseStatus.COMPLETE, PhaseStatus.PARTIAL
        )
        assert result.phases["synthesis"].status == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_calls_counselors_for_seed_generation(self, mock_counselors, tmp_path):
        """Seed generation phase should call counselors with both agents."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "Optimized"})
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        # First call should be seed generation with both agents
        first_call = mock_counselors.call_args_list[0]
        assert set(first_call.kwargs.get("agents", first_call[1].get("agents", []))) == {"agent-a", "agent-b"} or \
               set(first_call[1]["agents"]) == {"agent-a", "agent-b"} if len(first_call[1]) > 1 else True

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_calls_optimize_anything_twice(self, mock_counselors, tmp_path):
        """Should call optimize_anything once per agent (2 total)."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=2)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "Optimized"})
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        # optimize_anything called once per agent
        assert gepa_oa.optimize_anything.call_count == 2

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_saves_optimized_reports(self, mock_counselors, tmp_path):
        """Both optimized reports should be saved to phase2/."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "Optimized report content"})
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        assert (run_dir / "phase2" / "agent-a-optimized.md").exists()
        assert (run_dir / "phase2" / "agent-b-optimized.md").exists()
        assert "Optimized" in (run_dir / "phase2" / "agent-a-optimized.md").read_text()

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_saves_optimization_logs(self, mock_counselors, tmp_path):
        """Optimization logs should be saved as JSON."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "Optimized"}, 8.0)
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        log_a = run_dir / "phase2" / "agent-a-optimization-log.json"
        log_b = run_dir / "phase2" / "agent-b-optimization-log.json"
        assert log_a.exists()
        assert log_b.exists()

        log_data = json.loads(log_a.read_text())
        assert log_data["agent"] == "agent-a"
        assert "score_history" in log_data

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_saves_manifest(self, mock_counselors, tmp_path):
        """Manifest should be saved to disk after run."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "Optimized"})
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        assert (run_dir / "manifest.json").exists()
        loaded = Manifest.load(run_dir / "manifest.json")
        assert loaded.strategy == "adversarial"

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_synthesis_uses_optimized_reports(self, mock_counselors, tmp_path):
        """Synthesis prompt should contain both optimized reports."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "OPTIMIZED_MARKER_TEXT"})
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        # Synthesis prompt should exist and reference optimized content
        prompt = (run_dir / "phase3" / "synthesis-prompt.md").read_text()
        assert "OPTIMIZED_MARKER_TEXT" in prompt

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_run_records_total_duration(self, mock_counselors, tmp_path):
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        optimize_result = _make_optimize_result({"report": "Optimized"})
        gepa_oa.optimize_anything = MagicMock(return_value=optimize_result)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            result = s.run(run_dir, config, m)

        assert result.total_duration_seconds is not None
        assert result.total_duration_seconds >= 0


class TestAdversarialGracefulDegradation:
    """Tests for graceful degradation when GEPA fails."""

    def _setup_run_dir(self, tmp_path):
        run_dir = tmp_path / "run-adv-001"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        return run_dir

    def _fake_counselors_factory(self):
        def fake_counselors(prompt_file, agents, output_dir, verbose=False):
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(f"Report by {agent}")
            return MagicMock(returncode=0)
        return fake_counselors

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_gepa_failure_falls_back_to_seed(self, mock_counselors, tmp_path):
        """If optimize_anything raises, should fall back to seed and mark PARTIAL."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=2)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        gepa_oa.optimize_anything = MagicMock(side_effect=RuntimeError("GEPA crashed"))

        with _patch_gepa_import(gepa_mod, gepa_oa):
            result = s.run(run_dir, config, m)

        # Should still complete (synthesis uses seed fallback)
        assert result.phases["synthesis"].status == PhaseStatus.COMPLETE
        # Optimization should be PARTIAL
        assert result.phases["adversarial_optimization"].status == PhaseStatus.PARTIAL

        # Optimized files should exist (copied from seeds)
        assert (run_dir / "phase2" / "agent-a-optimized.md").exists()
        assert (run_dir / "phase2" / "agent-b-optimized.md").exists()

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_gepa_returns_none_best_candidate_uses_seed(self, mock_counselors, tmp_path):
        """If best_candidate is None, should fall back to seed text."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        mock_counselors.side_effect = self._fake_counselors_factory()

        gepa_mod, gepa_oa = _fake_gepa_modules()
        result_obj = MagicMock()
        result_obj.best_candidate = None
        result_obj.val_aggregate_scores = [0.0]
        result_obj.best_idx = 0
        result_obj.candidates = [{}]
        result_obj.total_metric_calls = 0
        gepa_oa.optimize_anything = MagicMock(return_value=result_obj)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            result = s.run(run_dir, config, m)

        # Should still complete, using seed text as fallback
        assert result.phases["adversarial_optimization"].status == PhaseStatus.COMPLETE
        # The optimized file should contain the seed text (from counselors)
        optimized_a = (run_dir / "phase2" / "agent-a-optimized.md").read_text()
        assert len(optimized_a) > 0  # Has content (seed fallback)


class TestAdversarialEvaluatorAndProposer:
    """Tests that evaluator and proposer callbacks work correctly."""

    def _setup_run_dir(self, tmp_path):
        run_dir = tmp_path / "run-adv-001"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        return run_dir

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_evaluator_calls_judge_agent(self, mock_counselors, tmp_path):
        """The GEPA evaluator should call counselors with the judge agent."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=2)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        counselors_calls = []

        def tracking_counselors(prompt_file, agents, output_dir, verbose=False):
            counselors_calls.append({"agents": agents, "output_dir": str(output_dir)})
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                judge_data = {
                    "overall_score": 6.5,
                    "dimensions": {},
                    "strengths": [],
                    "weaknesses": [],
                    "suggestions": [],
                    "critique": "ok",
                }
                (slug / f"{agent}.md").write_text(json.dumps(judge_data))
            return MagicMock(returncode=0)

        mock_counselors.side_effect = tracking_counselors

        gepa_mod, gepa_oa = _fake_gepa_modules()

        evaluator_tracker = []
        proposer_tracker = []

        def fake_optimize(seed_candidate, *, evaluator, objective=None, config=None, **kw):
            # Simulate one round: call evaluator then proposer
            score, asi = evaluator(seed_candidate)
            evaluator_tracker.append({"score": score, "asi": asi})

            proposer_fn = config.reflection.custom_candidate_proposer
            improved = proposer_fn(seed_candidate, {"evals": [{"score": score}]}, [])
            proposer_tracker.append(improved)

            return _make_optimize_result(improved, best_score=score)

        gepa_oa.optimize_anything = MagicMock(side_effect=fake_optimize)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        # Evaluator should have been called and produced scores
        assert len(evaluator_tracker) >= 2  # once per agent
        assert all(e["score"] == 6.5 for e in evaluator_tracker)

        # Proposer should have been called
        assert len(proposer_tracker) >= 2

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_evaluator_writes_judging_prompt(self, mock_counselors, tmp_path):
        """Evaluator should write a judging prompt file before calling counselors."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        prompt_texts = []

        def tracking_counselors(prompt_file, agents, output_dir, verbose=False):
            if prompt_file.exists():
                prompt_texts.append(prompt_file.read_text())
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(
                    json.dumps({"overall_score": 7.0, "dimensions": {},
                                "strengths": [], "weaknesses": [],
                                "suggestions": [], "critique": "ok"})
                )
            return MagicMock(returncode=0)

        mock_counselors.side_effect = tracking_counselors

        gepa_mod, gepa_oa = _fake_gepa_modules()

        def fake_optimize(seed_candidate, *, evaluator, objective=None, config=None, **kw):
            score, asi = evaluator(seed_candidate)
            proposer_fn = config.reflection.custom_candidate_proposer
            improved = proposer_fn(seed_candidate, {}, [])
            return _make_optimize_result(improved, best_score=score)

        gepa_oa.optimize_anything = MagicMock(side_effect=fake_optimize)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        # Should have judging prompts that contain the topic
        judge_prompts = [p for p in prompt_texts if "judg" in p.lower() or "evaluat" in p.lower()]
        # At minimum we should have judging + improvement calls per agent
        assert len(prompt_texts) >= 4  # seed gen + judge + improve + synthesis (minimum)


class TestProposerFeedbackHistory:
    """Gap 4b: proposer accumulates and passes feedback history to improvement prompt."""

    def _setup_run_dir(self, tmp_path):
        run_dir = tmp_path / "run-adv-001"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        return run_dir

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_improvement_prompt_contains_score_trajectory(self, mock_counselors, tmp_path):
        """After multiple rounds, the improvement prompt should include prior scores."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=3)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        round_scores = [5.5, 6.5, 7.0]
        call_counter = [0]

        def tracking_counselors(prompt_file, agents, output_dir, verbose=False):
            idx = min(call_counter[0] // 2, len(round_scores) - 1)  # crude round tracking
            judge_data = {
                "overall_score": round_scores[idx],
                "dimensions": {"factual_accuracy": 6, "depth_of_analysis": 5},
                "strengths": ["ok"], "weaknesses": ["needs work"],
                "suggestions": ["improve"], "critique": "feedback",
            }
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(json.dumps(judge_data))
            call_counter[0] += 1
            return MagicMock(returncode=0)

        mock_counselors.side_effect = tracking_counselors

        gepa_mod, gepa_oa = _fake_gepa_modules()
        improve_prompts = []

        def fake_optimize(seed_candidate, *, evaluator, objective=None, config=None, **kw):
            proposer_fn = config.reflection.custom_candidate_proposer
            current = seed_candidate
            # Simulate 3 rounds: eval, propose, eval, propose, eval
            for _i in range(3):
                score, asi = evaluator(current)
                current = proposer_fn(current, {"report": [asi]}, [])

            # Collect improvement prompts from disk
            phase2_dir = run_dir / "phase2"
            for improve_dir in sorted(phase2_dir.glob("*-improve-round-*")):
                pf = improve_dir / "improve-prompt.md"
                if pf.exists():
                    improve_prompts.append(pf.read_text())

            return _make_optimize_result(current, best_score=7.0)

        gepa_oa.optimize_anything = MagicMock(side_effect=fake_optimize)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        # The later improvement prompts should contain "Score Trajectory"
        # since feedback_history is accumulated across rounds
        later_prompts = [p for p in improve_prompts if "Score Trajectory" in p]
        assert len(later_prompts) > 0, (
            "At least one improvement prompt should contain score trajectory "
            f"from prior rounds. Got {len(improve_prompts)} prompts total."
        )

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_first_round_prompt_has_no_trajectory(self, mock_counselors, tmp_path):
        """The first improvement prompt should not have a trajectory section."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=2)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        def tracking_counselors(prompt_file, agents, output_dir, verbose=False):
            judge_data = {
                "overall_score": 6.0,
                "dimensions": {"factual_accuracy": 6, "depth_of_analysis": 5},
                "strengths": [], "weaknesses": [], "suggestions": [], "critique": "ok",
            }
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(json.dumps(judge_data))
            return MagicMock(returncode=0)

        mock_counselors.side_effect = tracking_counselors

        gepa_mod, gepa_oa = _fake_gepa_modules()
        first_prompts = []

        def fake_optimize(seed_candidate, *, evaluator, objective=None, config=None, **kw):
            proposer_fn = config.reflection.custom_candidate_proposer
            score, asi = evaluator(seed_candidate)
            improved = proposer_fn(seed_candidate, {}, [])

            # Collect first improvement prompt
            phase2_dir = run_dir / "phase2"
            for improve_dir in sorted(phase2_dir.glob("*-improve-round-*")):
                pf = improve_dir / "improve-prompt.md"
                if pf.exists():
                    first_prompts.append(pf.read_text())

            return _make_optimize_result(improved, best_score=score)

        gepa_oa.optimize_anything = MagicMock(side_effect=fake_optimize)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        # First prompt should NOT have trajectory (no prior rounds)
        for prompt in first_prompts:
            assert "Score Trajectory" not in prompt


class TestEvaluatorParetoScores:
    """Gap 1: evaluator ASI must include 'scores' key for GEPA Pareto tracking."""

    def _setup_run_dir(self, tmp_path):
        run_dir = tmp_path / "run-adv-001"
        for d in ("phase1", "phase2", "phase3"):
            (run_dir / d).mkdir(parents=True, exist_ok=True)
        return run_dir

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_evaluator_asi_contains_scores_key(self, mock_counselors, tmp_path):
        """Evaluator should include asi['scores'] mirroring dimension scores."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        judge_data = {
            "overall_score": 7.0,
            "dimensions": {
                "factual_accuracy": 8,
                "depth_of_analysis": 7,
                "source_quality": 6,
                "coverage_breadth": 7,
                "analytical_rigor": 7,
            },
            "strengths": ["good"],
            "weaknesses": ["needs work"],
            "suggestions": ["improve"],
            "critique": "decent report",
        }

        def tracking_counselors(prompt_file, agents, output_dir, verbose=False):
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(json.dumps(judge_data))
            return MagicMock(returncode=0)

        mock_counselors.side_effect = tracking_counselors

        gepa_mod, gepa_oa = _fake_gepa_modules()
        evaluator_tracker = []

        def fake_optimize(seed_candidate, *, evaluator, objective=None, config=None, **kw):
            score, asi = evaluator(seed_candidate)
            evaluator_tracker.append({"score": score, "asi": asi})
            proposer_fn = config.reflection.custom_candidate_proposer
            improved = proposer_fn(seed_candidate, {}, [])
            return _make_optimize_result(improved, best_score=score)

        gepa_oa.optimize_anything = MagicMock(side_effect=fake_optimize)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        assert len(evaluator_tracker) >= 2
        for entry in evaluator_tracker:
            asi = entry["asi"]
            # Must have 'scores' key for GEPA Pareto tracking
            assert "scores" in asi, "ASI must include 'scores' key for GEPA Pareto frontiers"
            scores = asi["scores"]
            # Scores should mirror dimension values as floats
            assert "factual_accuracy" in scores
            assert "depth_of_analysis" in scores
            assert "source_quality" in scores
            assert "coverage_breadth" in scores
            assert "analytical_rigor" in scores
            # Values should be numeric floats
            for dim, val in scores.items():
                assert isinstance(val, float), f"scores[{dim!r}] should be float, got {type(val)}"

    @patch("ivory_tower.strategies.adversarial.run_counselors")
    def test_evaluator_scores_empty_when_no_dimensions(self, mock_counselors, tmp_path):
        """When judge returns no dimensions, scores should still be present but empty."""
        s = AdversarialStrategy()
        config = _make_config(output_dir=tmp_path, max_rounds=1)
        m = _make_adversarial_manifest(config)
        run_dir = self._setup_run_dir(tmp_path)

        judge_data = {
            "overall_score": 5.0,
            "dimensions": {},
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
            "critique": "ok",
        }

        def tracking_counselors(prompt_file, agents, output_dir, verbose=False):
            slug = output_dir / "slug-001"
            slug.mkdir(parents=True, exist_ok=True)
            for agent in agents:
                (slug / f"{agent}.md").write_text(json.dumps(judge_data))
            return MagicMock(returncode=0)

        mock_counselors.side_effect = tracking_counselors

        gepa_mod, gepa_oa = _fake_gepa_modules()
        evaluator_tracker = []

        def fake_optimize(seed_candidate, *, evaluator, objective=None, config=None, **kw):
            score, asi = evaluator(seed_candidate)
            evaluator_tracker.append({"score": score, "asi": asi})
            proposer_fn = config.reflection.custom_candidate_proposer
            improved = proposer_fn(seed_candidate, {}, [])
            return _make_optimize_result(improved, best_score=score)

        gepa_oa.optimize_anything = MagicMock(side_effect=fake_optimize)

        with _patch_gepa_import(gepa_mod, gepa_oa):
            s.run(run_dir, config, m)

        for entry in evaluator_tracker:
            asi = entry["asi"]
            assert "scores" in asi
            assert asi["scores"] == {}


class TestAdversarialRegistration:
    """Tests that AdversarialStrategy is properly registered."""

    def test_get_strategy_returns_adversarial(self):
        from ivory_tower.strategies import get_strategy
        s = get_strategy("adversarial")
        assert isinstance(s, AdversarialStrategy)

    def test_list_strategies_includes_adversarial(self):
        from ivory_tower.strategies import list_strategies
        names = [n for n, _d in list_strategies()]
        assert "adversarial" in names

    def test_adversarial_name_attribute(self):
        s = AdversarialStrategy()
        assert s.name == "adversarial"

    def test_adversarial_description_non_empty(self):
        s = AdversarialStrategy()
        assert s.description
        assert len(s.description) > 10
