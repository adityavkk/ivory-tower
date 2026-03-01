"""Tests for RedBlueStrategy -- Commit 13."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ivory_tower.models import Flags, Manifest, PhaseStatus
from ivory_tower.strategies.red_blue import RedBlueStrategy


# ---------------------------------------------------------------------------
# Mock config helper
# ---------------------------------------------------------------------------


@dataclass
class _MockConfig:
    topic: str = "test topic"
    agents: list[str] = field(default_factory=lambda: ["agent-a", "agent-b", "agent-c"])
    synthesizer: str = "agent-c"
    raw: bool = False
    instructions: str | None = None
    verbose: bool = False
    strategy: str = "red-blue"
    red_team: list[str] = field(default_factory=lambda: ["agent-a"])
    blue_team: list[str] = field(default_factory=lambda: ["agent-b"])
    sandbox_backend: str = "none"


def _make_config(**overrides) -> _MockConfig:
    return _MockConfig(**overrides)


def _make_manifest(config: _MockConfig | None = None, run_id: str = "run-rb-001") -> Manifest:
    s = RedBlueStrategy()
    if config is None:
        config = _make_config()
    return s.create_manifest(config, run_id)


# ---------------------------------------------------------------------------
# 1. name
# ---------------------------------------------------------------------------


class TestRedBlueName:
    def test_name_is_red_blue(self):
        s = RedBlueStrategy()
        assert s.name == "red-blue"


# ---------------------------------------------------------------------------
# 2–6. validate
# ---------------------------------------------------------------------------


class TestRedBlueValidate:
    def test_rejects_fewer_than_3_agents(self):
        s = RedBlueStrategy()
        config = _make_config(agents=["a", "b"])
        errors = s.validate(config)
        assert any("3 agents" in e for e in errors)

    def test_rejects_missing_synthesizer(self):
        s = RedBlueStrategy()
        config = _make_config(synthesizer="")
        errors = s.validate(config)
        assert any("synthesizer" in e.lower() for e in errors)

    def test_rejects_missing_red_team(self):
        s = RedBlueStrategy()
        config = _make_config(red_team=[], blue_team=["agent-b"])
        errors = s.validate(config)
        assert any("red-team" in e.lower() or "red_team" in e.lower() for e in errors)

    def test_rejects_missing_blue_team(self):
        s = RedBlueStrategy()
        config = _make_config(red_team=["agent-a"], blue_team=[])
        errors = s.validate(config)
        assert any("blue-team" in e.lower() or "blue_team" in e.lower() for e in errors)

    def test_rejects_both_teams_missing(self):
        s = RedBlueStrategy()
        config = _make_config(red_team=[], blue_team=[])
        errors = s.validate(config)
        assert any("red-team" in e.lower() or "red_team" in e.lower() for e in errors)
        assert any("blue-team" in e.lower() or "blue_team" in e.lower() for e in errors)

    def test_accepts_valid_config(self):
        s = RedBlueStrategy()
        config = _make_config()
        errors = s.validate(config)
        assert errors == []


# ---------------------------------------------------------------------------
# 7–8. create_manifest
# ---------------------------------------------------------------------------


class TestRedBlueCreateManifest:
    def test_strategy_is_red_blue(self):
        m = _make_manifest()
        assert m.strategy == "red-blue"

    def test_has_expected_phases(self):
        m = _make_manifest()
        expected = {"blue-research", "red-critique", "blue-defense", "synthesize"}
        assert set(m.phases.keys()) == expected

    def test_all_phases_pending(self):
        m = _make_manifest()
        for phase_data in m.phases.values():
            assert phase_data["status"] == PhaseStatus.PENDING

    def test_phases_have_isolation(self):
        m = _make_manifest()
        assert m.phases["blue-research"]["isolation"] == "team"
        assert m.phases["red-critique"]["isolation"] == "cross-team-read"
        assert m.phases["blue-defense"]["isolation"] == "cross-team-read"
        assert m.phases["synthesize"]["isolation"] == "read-all"


# ---------------------------------------------------------------------------
# 9–10. run
# ---------------------------------------------------------------------------


class TestRedBlueRun:
    @patch("ivory_tower.strategies.red_blue.GenericTemplateExecutor")
    def test_run_calls_executor_with_teams(self, MockExecutor, tmp_path):
        s = RedBlueStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-rb-001"
        run_dir.mkdir(parents=True)

        mock_instance = MagicMock()
        MockExecutor.return_value = mock_instance

        result = s.run(run_dir, config, m)

        # Verify executor.run was called
        mock_instance.run.assert_called_once()
        call_kwargs = mock_instance.run.call_args
        # Check teams mapping was passed
        teams = call_kwargs.kwargs.get("teams") or call_kwargs[1].get("teams")
        assert teams == {"agent-a": "red", "agent-b": "blue"}

    @patch("ivory_tower.strategies.red_blue.GenericTemplateExecutor")
    def test_run_marks_all_phases_complete(self, MockExecutor, tmp_path):
        s = RedBlueStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-rb-001"
        run_dir.mkdir(parents=True)

        mock_instance = MagicMock()
        MockExecutor.return_value = mock_instance

        result = s.run(run_dir, config, m)

        for phase_data in result.phases.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE

    @patch("ivory_tower.strategies.red_blue.GenericTemplateExecutor")
    def test_run_records_duration(self, MockExecutor, tmp_path):
        s = RedBlueStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-rb-001"
        run_dir.mkdir(parents=True)

        mock_instance = MagicMock()
        MockExecutor.return_value = mock_instance

        result = s.run(run_dir, config, m)

        assert result.total_duration_seconds is not None
        assert result.total_duration_seconds >= 0

    @patch("ivory_tower.strategies.red_blue.GenericTemplateExecutor")
    def test_run_saves_manifest(self, MockExecutor, tmp_path):
        s = RedBlueStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-rb-001"
        run_dir.mkdir(parents=True)

        mock_instance = MagicMock()
        MockExecutor.return_value = mock_instance

        s.run(run_dir, config, m)

        assert (run_dir / "manifest.json").exists()


# ---------------------------------------------------------------------------
# 11. dry_run
# ---------------------------------------------------------------------------


class TestRedBlueDryRun:
    def test_prints_plan_with_team_assignments(self, capsys):
        s = RedBlueStrategy()
        config = _make_config()
        s.dry_run(config)
        out = capsys.readouterr().out
        assert "red-blue" in out.lower()
        assert "agent-a" in out
        assert "agent-b" in out
        assert "agent-c" in out
        assert "blue-research" in out
        assert "red-critique" in out
        assert "blue-defense" in out
        assert "synthesize" in out


# ---------------------------------------------------------------------------
# 12. format_status
# ---------------------------------------------------------------------------


class TestRedBlueFormatStatus:
    def test_returns_tuples(self):
        s = RedBlueStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        assert len(result) == 4
        for label, value in result:
            assert isinstance(label, str)
            assert isinstance(value, str)

    def test_status_values_are_strings(self):
        s = RedBlueStrategy()
        m = _make_manifest()
        result = s.format_status(m)
        for _, value in result:
            assert value == "pending"

    def test_reflects_complete_status(self):
        s = RedBlueStrategy()
        m = _make_manifest()
        m.phases["blue-research"]["status"] = PhaseStatus.COMPLETE
        result = s.format_status(m)
        status_map = dict(result)
        assert status_map["blue-research"] == "complete"
        assert status_map["red-critique"] == "pending"


# ---------------------------------------------------------------------------
# 13. phases_to_dict / phases_from_dict roundtrip
# ---------------------------------------------------------------------------


class TestRedBluePhaseSerialization:
    def test_roundtrip_pending(self):
        s = RedBlueStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        for phase_data in restored.values():
            assert phase_data["status"] == PhaseStatus.PENDING

    def test_roundtrip_preserves_isolation(self):
        s = RedBlueStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        assert restored["blue-research"]["isolation"] == "team"
        assert restored["synthesize"]["isolation"] == "read-all"

    def test_roundtrip_complete(self):
        s = RedBlueStrategy()
        m = _make_manifest()
        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE

        d = s.phases_to_dict(m.phases)
        restored = s.phases_from_dict(d)

        for phase_data in restored.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE

    def test_to_dict_serializes_status_as_string(self):
        s = RedBlueStrategy()
        m = _make_manifest()
        d = s.phases_to_dict(m.phases)
        for phase_data in d.values():
            assert isinstance(phase_data["status"], str)
            assert phase_data["status"] == "pending"

    def test_manifest_save_load_roundtrip(self, tmp_path):
        m = _make_manifest()
        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = Manifest.load(path)
        assert loaded.strategy == "red-blue"
        assert set(loaded.phases.keys()) == {
            "blue-research", "red-critique", "blue-defense", "synthesize",
        }
        for phase_data in loaded.phases.values():
            assert phase_data["status"] == PhaseStatus.PENDING


# ---------------------------------------------------------------------------
# 14. resume
# ---------------------------------------------------------------------------


class TestRedBlueResume:
    def test_all_complete_is_noop(self, tmp_path):
        s = RedBlueStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-rb-001"
        run_dir.mkdir(parents=True)

        for phase_data in m.phases.values():
            phase_data["status"] = PhaseStatus.COMPLETE

        result = s.resume(run_dir, config, m)
        # Should return immediately without re-running
        assert all(
            p["status"] == PhaseStatus.COMPLETE for p in result.phases.values()
        )

    @patch("ivory_tower.strategies.red_blue.GenericTemplateExecutor")
    def test_incomplete_triggers_run(self, MockExecutor, tmp_path):
        s = RedBlueStrategy()
        config = _make_config()
        m = _make_manifest(config)
        run_dir = tmp_path / "run-rb-001"
        run_dir.mkdir(parents=True)

        # Leave phases as PENDING (incomplete)
        mock_instance = MagicMock()
        MockExecutor.return_value = mock_instance

        result = s.resume(run_dir, config, m)

        # Should have called executor.run
        mock_instance.run.assert_called_once()
        # All phases should be complete
        for phase_data in result.phases.values():
            assert phase_data["status"] == PhaseStatus.COMPLETE


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRedBlueRegistration:
    def test_get_strategy_returns_red_blue(self):
        from ivory_tower.strategies import get_strategy
        s = get_strategy("red-blue")
        assert isinstance(s, RedBlueStrategy)

    def test_list_strategies_includes_red_blue(self):
        from ivory_tower.strategies import list_strategies
        names = [n for n, _d in list_strategies()]
        assert "red-blue" in names
