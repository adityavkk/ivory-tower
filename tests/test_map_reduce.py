"""Tests for MapReduceStrategy -- Commit 13."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.strategies.map_reduce import MapReduceStrategy
from ivory_tower.engine import RunConfig
from ivory_tower.models import Flags, Manifest, PhaseStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> RunConfig:
    """Create a minimal map-reduce RunConfig."""
    defaults = dict(
        topic="test topic",
        agents=["agent-a", "agent-b"],
        synthesizer="agent-s",
        strategy="map-reduce",
    )
    defaults.update(overrides)
    return RunConfig(**defaults)


def _make_manifest(config: RunConfig | None = None, run_id: str = "run-mr-001") -> Manifest:
    """Create a map-reduce manifest via the strategy."""
    s = MapReduceStrategy()
    if config is None:
        config = _make_config()
    return s.create_manifest(config, run_id)


# ---------------------------------------------------------------------------
# 1. name
# ---------------------------------------------------------------------------


class TestMapReduceName:
    def test_name_is_map_reduce(self):
        s = MapReduceStrategy()
        assert s.name == "map-reduce"

    def test_description_is_non_empty(self):
        s = MapReduceStrategy()
        assert s.description
        assert len(s.description) > 10


# ---------------------------------------------------------------------------
# 2-4. validate
# ---------------------------------------------------------------------------


class TestMapReduceValidate:
    def test_rejects_fewer_than_2_agents(self):
        s = MapReduceStrategy()
        config = _make_config(agents=["only-one"])
        errors = s.validate(config)
        assert any("2" in e or "agent" in e.lower() for e in errors)

    def test_rejects_missing_synthesizer(self):
        s = MapReduceStrategy()
        config = _make_config(synthesizer="")
        errors = s.validate(config)
        assert any("synthesizer" in e.lower() for e in errors)

    def test_accepts_valid_config(self):
        s = MapReduceStrategy()
        config = _make_config()
        errors = s.validate(config)
        assert errors == []

    def test_multiple_errors_returned(self):
        s = MapReduceStrategy()
        config = _make_config(agents=["only-one"], synthesizer="")
        errors = s.validate(config)
        assert len(errors) == 2


# ---------------------------------------------------------------------------
# 5-6. create_manifest
# ---------------------------------------------------------------------------


class TestMapReduceCreateManifest:
    def test_strategy_field(self):
        m = _make_manifest()
        assert m.strategy == "map-reduce"

    def test_has_three_phases(self):
        m = _make_manifest()
        assert "decompose" in m.phases
        assert "map" in m.phases
        assert "reduce" in m.phases

    def test_all_phases_pending(self):
        m = _make_manifest()
        for phase_data in m.phases.values():
            assert phase_data["status"] == PhaseStatus.PENDING

    def test_phases_have_isolation(self):
        m = _make_manifest()
        assert m.phases["decompose"]["isolation"] == "full"
        assert m.phases["map"]["isolation"] == "full"
        assert m.phases["reduce"]["isolation"] == "read-all"

    def test_manifest_agents_and_synthesizer(self):
        m = _make_manifest()
        assert m.agents == ["agent-a", "agent-b"]
        assert m.synthesizer == "agent-s"

    def test_manifest_flags(self):
        config = _make_config(raw=True, instructions="custom", verbose=True)
        m = _make_manifest(config)
        assert m.flags.raw is True
        assert m.flags.instructions == "custom"
        assert m.flags.verbose is True

    def test_manifest_run_id(self):
        m = _make_manifest(run_id="run-mr-042")
        assert m.run_id == "run-mr-042"


# ---------------------------------------------------------------------------
# 7-8. run
# ---------------------------------------------------------------------------


class TestMapReduceRun:
    @patch("ivory_tower.strategies.map_reduce.GenericTemplateExecutor")
    def test_run_calls_executor(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = MapReduceStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        result = s.run(run_dir, config, m)

        MockExecutor.assert_called_once()
        mock_instance.run.assert_called_once()

    @patch("ivory_tower.strategies.map_reduce.GenericTemplateExecutor")
    def test_run_marks_all_phases_complete(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = MapReduceStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        result = s.run(run_dir, config, m)

        for phase_data in result.phases.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.map_reduce.GenericTemplateExecutor")
    def test_run_records_total_duration(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = MapReduceStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        result = s.run(run_dir, config, m)

        assert result.total_duration_seconds is not None
        assert result.total_duration_seconds >= 0

    @patch("ivory_tower.strategies.map_reduce.GenericTemplateExecutor")
    def test_run_saves_manifest(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = MapReduceStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        s.run(run_dir, config, m)

        assert (run_dir / "manifest.json").exists()

    @patch("ivory_tower.strategies.map_reduce.GenericTemplateExecutor")
    def test_run_passes_correct_args_to_executor(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = MapReduceStrategy()
        config = _make_config(verbose=True)
        m = _make_manifest(config)
        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        s.run(run_dir, config, m)

        call_kwargs = mock_instance.run.call_args
        assert call_kwargs.kwargs["agents"] == ["agent-a", "agent-b"]
        assert call_kwargs.kwargs["synthesizer"] == "agent-s"
        assert call_kwargs.kwargs["topic"] == "test topic"
        assert call_kwargs.kwargs["verbose"] is True


# ---------------------------------------------------------------------------
# 9. dry_run
# ---------------------------------------------------------------------------


class TestMapReduceDryRun:
    def test_prints_plan(self, capsys):
        s = MapReduceStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "map-reduce" in out
        assert "agent-a" in out
        assert "agent-b" in out
        assert "agent-s" in out

    def test_prints_phases(self, capsys):
        s = MapReduceStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "decompose" in out
        assert "map" in out
        assert "reduce" in out

    def test_prints_isolation(self, capsys):
        s = MapReduceStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "full" in out
        assert "read-all" in out


# ---------------------------------------------------------------------------
# 10. format_status
# ---------------------------------------------------------------------------


class TestMapReduceFormatStatus:
    def test_returns_tuples(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        assert len(result) == 3
        for label, value in result:
            assert isinstance(label, str)
            assert isinstance(value, str)

    def test_includes_phase_names(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        labels = [label for label, _ in result]
        assert "decompose" in labels
        assert "map" in labels
        assert "reduce" in labels

    def test_shows_pending_status(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        for _, value in result:
            assert value == "pending"

    def test_shows_complete_status(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE
        result = s.format_status(m)
        for _, value in result:
            assert value == "complete"


# ---------------------------------------------------------------------------
# 11. phases_to_dict / phases_from_dict roundtrip
# ---------------------------------------------------------------------------


class TestMapReducePhaseSerialization:
    def test_roundtrip_pending(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        for phase_data in restored.values():
            assert phase_data["status"] == PhaseStatus.PENDING

    def test_roundtrip_complete(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE

        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        for phase_data in restored.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE

    def test_roundtrip_preserves_isolation(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        assert restored["decompose"]["isolation"] == "full"
        assert restored["map"]["isolation"] == "full"
        assert restored["reduce"]["isolation"] == "read-all"

    def test_to_dict_serializes_status_to_string(self):
        s = MapReduceStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)

        for phase_data in d.values():
            assert isinstance(phase_data["status"], str)
            assert phase_data["status"] == "pending"

    def test_from_dict_deserializes_status_to_enum(self):
        s = MapReduceStrategy()
        raw = {
            "decompose": {"status": "complete", "isolation": "full"},
            "map": {"status": "running", "isolation": "full"},
            "reduce": {"status": "pending", "isolation": "read-all"},
        }
        restored = s.phases_from_dict(raw)

        assert restored["decompose"]["status"] == PhaseStatus.COMPLETE
        assert restored["map"]["status"] == PhaseStatus.RUNNING
        assert restored["reduce"]["status"] == PhaseStatus.PENDING


# ---------------------------------------------------------------------------
# 12. resume
# ---------------------------------------------------------------------------


class TestMapReduceResume:
    def test_resume_all_complete_is_noop(self, tmp_path):
        s = MapReduceStrategy()
        config = _make_config()
        m = _make_manifest(config)

        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE

        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        # Should return immediately without calling run
        with patch.object(s, "run") as mock_run:
            result = s.resume(run_dir, config, m)
            mock_run.assert_not_called()

        for phase_data in result.phases.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.map_reduce.GenericTemplateExecutor")
    def test_resume_incomplete_calls_run(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = MapReduceStrategy()
        config = _make_config()
        m = _make_manifest(config)

        # Leave phases as pending
        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        result = s.resume(run_dir, config, m)

        # Executor should have been called (via run)
        mock_instance.run.assert_called_once()

    @patch("ivory_tower.strategies.map_reduce.GenericTemplateExecutor")
    def test_resume_partial_complete_calls_run(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = MapReduceStrategy()
        config = _make_config()
        m = _make_manifest(config)

        # Mark only decompose as complete
        m.phases["decompose"]["status"] = PhaseStatus.COMPLETE

        run_dir = tmp_path / "run-mr-001"
        run_dir.mkdir(parents=True)

        result = s.resume(run_dir, config, m)

        mock_instance.run.assert_called_once()
