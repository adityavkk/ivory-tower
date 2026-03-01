"""Tests for DebateStrategy -- Commit 13."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.strategies.debate import DebateStrategy
from ivory_tower.engine import RunConfig
from ivory_tower.models import Flags, Manifest, PhaseStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEBATE_PHASE_NAMES = {"opening", "rounds", "closing", "verdict"}


def _make_config(**overrides) -> RunConfig:
    """Create a minimal debate RunConfig."""
    defaults = dict(
        topic="Should AI be regulated?",
        agents=["agent-a", "agent-b"],
        synthesizer="judge-agent",
        strategy="debate",
    )
    defaults.update(overrides)
    return RunConfig(**defaults)


def _make_manifest(config: RunConfig | None = None, run_id: str = "run-debate-001") -> Manifest:
    """Create a debate manifest via the strategy."""
    s = DebateStrategy()
    if config is None:
        config = _make_config()
    return s.create_manifest(config, run_id)


# ---------------------------------------------------------------------------
# 1. name attribute
# ---------------------------------------------------------------------------


class TestDebateAttributes:

    def test_name_is_debate(self):
        s = DebateStrategy()
        assert s.name == "debate"

    def test_description_is_non_empty(self):
        s = DebateStrategy()
        assert s.description
        assert len(s.description) > 5


# ---------------------------------------------------------------------------
# 3-5. validate()
# ---------------------------------------------------------------------------


class TestDebateValidate:

    def test_rejects_fewer_than_2_agents(self):
        s = DebateStrategy()
        config = _make_config(agents=["only-one"])
        errors = s.validate(config)
        assert len(errors) > 0
        assert any("2" in e or "least" in e.lower() for e in errors)

    def test_rejects_empty_agents(self):
        s = DebateStrategy()
        config = _make_config(agents=[])
        errors = s.validate(config)
        assert len(errors) > 0

    def test_rejects_missing_synthesizer(self):
        s = DebateStrategy()
        config = _make_config(synthesizer="")
        errors = s.validate(config)
        assert len(errors) > 0
        assert any("synthesizer" in e.lower() or "judge" in e.lower() for e in errors)

    def test_accepts_valid_config(self):
        s = DebateStrategy()
        config = _make_config()
        errors = s.validate(config)
        assert errors == []

    def test_accepts_3_agents(self):
        s = DebateStrategy()
        config = _make_config(agents=["a", "b", "c"])
        errors = s.validate(config)
        assert errors == []

    def test_multiple_errors_returned(self):
        s = DebateStrategy()
        config = _make_config(agents=["only-one"], synthesizer="")
        errors = s.validate(config)
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# 6-7. create_manifest()
# ---------------------------------------------------------------------------


class TestDebateCreateManifest:

    def test_strategy_field_is_debate(self):
        m = _make_manifest()
        assert m.strategy == "debate"

    def test_has_correct_phase_names(self):
        m = _make_manifest()
        assert set(m.phases.keys()) == DEBATE_PHASE_NAMES

    def test_all_phases_pending(self):
        m = _make_manifest()
        for phase_name, phase_data in m.phases.items():
            assert phase_data["status"] == PhaseStatus.PENDING, (
                f"Phase '{phase_name}' should be PENDING"
            )

    def test_manifest_agents_and_synthesizer(self):
        m = _make_manifest()
        assert m.agents == ["agent-a", "agent-b"]
        assert m.synthesizer == "judge-agent"

    def test_manifest_run_id(self):
        m = _make_manifest(run_id="my-run-42")
        assert m.run_id == "my-run-42"

    def test_manifest_topic(self):
        config = _make_config(topic="Debate about cats")
        m = _make_manifest(config)
        assert m.topic == "Debate about cats"

    def test_phases_have_isolation_mode(self):
        m = _make_manifest()
        assert m.phases["opening"]["isolation"] == "full"
        assert m.phases["rounds"]["isolation"] == "blackboard"
        assert m.phases["closing"]["isolation"] == "read-blackboard"
        assert m.phases["verdict"]["isolation"] == "read-all"

    def test_manifest_flags(self):
        config = _make_config(raw=True, verbose=True, instructions="be concise")
        m = _make_manifest(config)
        assert m.flags.raw is True
        assert m.flags.verbose is True
        assert m.flags.instructions == "be concise"


# ---------------------------------------------------------------------------
# 8-9. run() -- mocked GenericTemplateExecutor
# ---------------------------------------------------------------------------


class TestDebateRun:

    @patch("ivory_tower.strategies.debate.GenericTemplateExecutor")
    def test_run_calls_executor(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = DebateStrategy()
        config = _make_config()
        m = _make_manifest(config)

        run_dir = tmp_path / "run-debate-001"
        run_dir.mkdir(parents=True)

        result = s.run(run_dir, config, m)

        # Executor should have been instantiated with the template
        MockExecutor.assert_called_once()
        # .run() should have been called
        mock_instance.run.assert_called_once()

    @patch("ivory_tower.strategies.debate.GenericTemplateExecutor")
    def test_run_marks_all_phases_complete(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = DebateStrategy()
        config = _make_config()
        m = _make_manifest(config)

        run_dir = tmp_path / "run-debate-001"
        run_dir.mkdir(parents=True)

        result = s.run(run_dir, config, m)

        for phase_name, phase_data in result.phases.items():
            assert phase_data["status"] == PhaseStatus.COMPLETE, (
                f"Phase '{phase_name}' should be COMPLETE after run()"
            )

    @patch("ivory_tower.strategies.debate.GenericTemplateExecutor")
    def test_run_saves_manifest(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = DebateStrategy()
        config = _make_config()
        m = _make_manifest(config)

        run_dir = tmp_path / "run-debate-001"
        run_dir.mkdir(parents=True)

        s.run(run_dir, config, m)

        assert (run_dir / "manifest.json").exists()

    @patch("ivory_tower.strategies.debate.GenericTemplateExecutor")
    def test_run_records_duration(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = DebateStrategy()
        config = _make_config()
        m = _make_manifest(config)

        run_dir = tmp_path / "run-debate-001"
        run_dir.mkdir(parents=True)

        result = s.run(run_dir, config, m)

        assert result.total_duration_seconds is not None
        assert result.total_duration_seconds >= 0

    @patch("ivory_tower.strategies.debate.GenericTemplateExecutor")
    def test_run_passes_correct_args_to_executor(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = DebateStrategy()
        config = _make_config(verbose=True)
        m = _make_manifest(config)

        run_dir = tmp_path / "run-debate-001"
        run_dir.mkdir(parents=True)

        s.run(run_dir, config, m)

        call_kwargs = mock_instance.run.call_args
        assert call_kwargs.kwargs["agents"] == ["agent-a", "agent-b"]
        assert call_kwargs.kwargs["synthesizer"] == "judge-agent"
        assert call_kwargs.kwargs["topic"] == "Should AI be regulated?"
        assert call_kwargs.kwargs["verbose"] is True


# ---------------------------------------------------------------------------
# 10. dry_run() -- capture output
# ---------------------------------------------------------------------------


class TestDebateDryRun:

    def test_prints_strategy_name(self, capsys):
        s = DebateStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "debate" in out.lower()

    def test_prints_agents(self, capsys):
        s = DebateStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "agent-a" in out
        assert "agent-b" in out

    def test_prints_synthesizer(self, capsys):
        s = DebateStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "judge-agent" in out

    def test_prints_rounds(self, capsys):
        s = DebateStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "3" in out  # default rounds from template

    def test_prints_phase_names(self, capsys):
        s = DebateStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        for phase_name in DEBATE_PHASE_NAMES:
            assert phase_name in out

    def test_prints_blackboard_info(self, capsys):
        s = DebateStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "transcript" in out.lower() or "blackboard" in out.lower()

    def test_no_exception(self):
        """dry_run should not raise any exception."""
        s = DebateStrategy()
        config = _make_config()
        s.dry_run(config)  # should not raise


# ---------------------------------------------------------------------------
# 11. format_status()
# ---------------------------------------------------------------------------


class TestDebateFormatStatus:

    def test_returns_tuples_for_all_phases(self):
        s = DebateStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        assert len(result) == len(DEBATE_PHASE_NAMES)
        for label, value in result:
            assert isinstance(label, str)
            assert isinstance(value, str)

    def test_includes_phase_names(self):
        s = DebateStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        labels = {label for label, _ in result}
        assert labels == DEBATE_PHASE_NAMES

    def test_pending_status_values(self):
        s = DebateStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        for _, value in result:
            assert value == "pending"

    def test_complete_status_values(self):
        s = DebateStrategy()
        m = _make_manifest()
        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE
        result = s.format_status(m)
        for _, value in result:
            assert value == "complete"


# ---------------------------------------------------------------------------
# 12. phases_to_dict() / phases_from_dict() roundtrip
# ---------------------------------------------------------------------------


class TestDebatePhaseSerialization:

    def test_roundtrip_pending(self):
        s = DebateStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        assert set(restored.keys()) == DEBATE_PHASE_NAMES
        for phase_name, phase_data in restored.items():
            assert phase_data["status"] == PhaseStatus.PENDING

    def test_roundtrip_complete(self):
        s = DebateStrategy()
        m = _make_manifest()
        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE

        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        for phase_name, phase_data in restored.items():
            assert phase_data["status"] == PhaseStatus.COMPLETE

    def test_to_dict_serializes_status_as_string(self):
        s = DebateStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        for phase_name, phase_data in d.items():
            assert isinstance(phase_data["status"], str)
            assert phase_data["status"] == "pending"

    def test_from_dict_deserializes_status_as_enum(self):
        s = DebateStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)
        for phase_name, phase_data in restored.items():
            assert isinstance(phase_data["status"], PhaseStatus)

    def test_roundtrip_preserves_isolation(self):
        s = DebateStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        assert restored["opening"]["isolation"] == "full"
        assert restored["rounds"]["isolation"] == "blackboard"

    def test_manifest_save_load_roundtrip(self, tmp_path):
        """Full Manifest serialization roundtrip with debate phases."""
        m = _make_manifest()
        m.phases["opening"]["status"] = PhaseStatus.COMPLETE
        m.phases["rounds"]["status"] = PhaseStatus.RUNNING

        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = Manifest.load(path)

        assert loaded.strategy == "debate"
        assert loaded.phases["opening"]["status"] == PhaseStatus.COMPLETE
        assert loaded.phases["rounds"]["status"] == PhaseStatus.RUNNING
        assert loaded.phases["closing"]["status"] == PhaseStatus.PENDING
        assert loaded.phases["verdict"]["status"] == PhaseStatus.PENDING


# ---------------------------------------------------------------------------
# 13. resume()
# ---------------------------------------------------------------------------


class TestDebateResume:

    def test_resume_all_complete_is_noop(self, tmp_path):
        s = DebateStrategy()
        config = _make_config()
        m = _make_manifest(config)

        # Mark all phases complete
        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE

        run_dir = tmp_path / "run-debate-001"
        run_dir.mkdir(parents=True)

        result = s.resume(run_dir, config, m)

        # Should return immediately -- no manifest.json written
        assert not (run_dir / "manifest.json").exists()
        # All still complete
        for phase_data in result.phases.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.debate.GenericTemplateExecutor")
    def test_resume_incomplete_reruns(self, MockExecutor, tmp_path):
        mock_instance = MagicMock()
        mock_instance.run.return_value = {}
        MockExecutor.return_value = mock_instance

        s = DebateStrategy()
        config = _make_config()
        m = _make_manifest(config)

        # Leave opening as PENDING -- should trigger full rerun
        m.phases["opening"]["status"] = PhaseStatus.PENDING

        run_dir = tmp_path / "run-debate-001"
        run_dir.mkdir(parents=True)

        result = s.resume(run_dir, config, m)

        # Executor should have been called
        mock_instance.run.assert_called_once()
        # All phases should now be complete
        for phase_data in result.phases.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE


# ---------------------------------------------------------------------------
# Strategy registration
# ---------------------------------------------------------------------------


class TestDebateRegistration:

    def test_get_strategy_returns_debate(self):
        from ivory_tower.strategies import get_strategy
        s = get_strategy("debate")
        assert isinstance(s, DebateStrategy)

    def test_list_strategies_includes_debate(self):
        from ivory_tower.strategies import list_strategies
        names = [n for n, _d in list_strategies()]
        assert "debate" in names
