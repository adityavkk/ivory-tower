"""Tests for strategy template loading and validation."""

from __future__ import annotations

import pytest
import yaml

from ivory_tower.templates import (
    BlackboardConfig,
    PhaseConfig,
    StrategyDefaults,
    StrategyTemplate,
    TeamConfig,
    list_template_names,
    list_templates,
    load_template,
    validate_template,
)


# ---------------------------------------------------------------------------
# Loading built-in templates
# ---------------------------------------------------------------------------


class TestLoadBuiltinTemplates:
    """Test loading each of the 5 built-in YAML templates."""

    def test_load_council(self):
        t = load_template("council")
        assert t.name == "council"
        assert t.source_path is not None
        assert t.source_path.name == "council.yml"

    def test_load_debate(self):
        t = load_template("debate")
        assert t.name == "debate"
        assert t.source_path is not None
        assert t.source_path.name == "debate.yml"

    def test_load_map_reduce(self):
        t = load_template("map-reduce")
        assert t.name == "map-reduce"
        assert t.source_path is not None
        assert t.source_path.name == "map-reduce.yml"

    def test_load_red_blue(self):
        t = load_template("red-blue")
        assert t.name == "red-blue"
        assert t.source_path is not None
        assert t.source_path.name == "red-blue.yml"

    def test_load_adversarial(self):
        t = load_template("adversarial")
        assert t.name == "adversarial"
        assert t.source_path is not None
        assert t.source_path.name == "adversarial.yml"


# ---------------------------------------------------------------------------
# Loading from file path
# ---------------------------------------------------------------------------


class TestLoadFromPath:
    """Test loading templates by file path."""

    def test_load_from_absolute_path(self, tmp_path):
        """load_template with an absolute path loads from that file."""
        yml = tmp_path / "custom.yml"
        yml.write_text(yaml.dump({
            "strategy": {"name": "custom", "description": "A custom template", "version": 1},
            "phases": [
                {
                    "name": "work",
                    "description": "Do the work",
                    "isolation": "full",
                    "agents": "all",
                    "output": "result.md",
                }
            ],
        }))
        t = load_template(str(yml))
        assert t.name == "custom"
        assert t.source_path == yml

    def test_load_nonexistent_name_raises(self):
        """load_template with unknown name raises FileNotFoundError with Available: list."""
        with pytest.raises(FileNotFoundError, match="Available:"):
            load_template("nonexistent")

    def test_load_nonexistent_file_raises(self):
        """load_template with absolute path to nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Template file not found"):
            load_template("/nonexistent.yml")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Test validate_template catches various errors."""

    def test_all_builtins_valid(self):
        """All 5 built-in templates must pass validation."""
        for name in ["council", "debate", "map-reduce", "red-blue", "adversarial"]:
            t = load_template(name)
            errors = validate_template(t)
            assert errors == [], f"Template '{name}' has errors: {errors}"

    def test_reject_missing_name(self):
        t = StrategyTemplate(name="", description="desc", version=1, phases=[
            PhaseConfig(name="p1", description="d", isolation="full", agents="all", output="o.md"),
        ])
        errors = validate_template(t)
        assert any("strategy.name" in e for e in errors)

    def test_reject_missing_phases(self):
        t = StrategyTemplate(name="test", description="desc", version=1, phases=[])
        errors = validate_template(t)
        assert any("at least one phase" in e for e in errors)

    def test_reject_unknown_isolation_mode(self):
        t = StrategyTemplate(name="test", description="desc", version=1, phases=[
            PhaseConfig(name="p1", description="d", isolation="banana", agents="all", output="o.md"),
        ])
        errors = validate_template(t)
        assert any("unknown isolation mode" in e for e in errors)

    def test_reject_input_from_nonexistent_phase(self):
        t = StrategyTemplate(name="test", description="desc", version=1, phases=[
            PhaseConfig(name="p1", description="d", isolation="full", agents="all", output="o.md",
                        input_from="ghost"),
        ])
        errors = validate_template(t)
        assert any("references unknown phase 'ghost'" in e for e in errors)

    def test_reject_blackboard_without_name(self):
        t = StrategyTemplate(name="test", description="desc", version=1, phases=[
            PhaseConfig(
                name="p1", description="d", isolation="blackboard", agents="all", output="o.md",
                blackboard=BlackboardConfig(name=""),
            ),
        ])
        errors = validate_template(t)
        assert any("blackboard missing required field 'name'" in e for e in errors)

    def test_reject_duplicate_phase_names(self):
        t = StrategyTemplate(name="test", description="desc", version=1, phases=[
            PhaseConfig(name="dup", description="d", isolation="full", agents="all", output="o1.md"),
            PhaseConfig(name="dup", description="d", isolation="full", agents="all", output="o2.md"),
        ])
        errors = validate_template(t)
        assert any("Duplicate phase name: 'dup'" in e for e in errors)


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class TestListing:
    """Test list_templates and list_template_names."""

    def test_list_templates_returns_builtins(self):
        results = list_templates()
        names = [name for name, _desc, _source in results]
        assert "council" in names
        assert "debate" in names
        assert "adversarial" in names
        assert "map-reduce" in names
        assert "red-blue" in names
        # All built-in
        for _name, _desc, source in results:
            if _name in {"council", "debate", "adversarial", "map-reduce", "red-blue"}:
                assert source == "built-in"

    def test_list_template_names(self):
        names = list_template_names()
        assert isinstance(names, list)
        for expected in ["adversarial", "council", "debate", "map-reduce", "red-blue"]:
            assert expected in names


# ---------------------------------------------------------------------------
# Template structure details
# ---------------------------------------------------------------------------


class TestTemplateStructure:
    """Test that parsed templates have correct structure."""

    def test_council_has_3_phases(self):
        t = load_template("council")
        assert len(t.phases) == 3
        phase_names = [p.name for p in t.phases]
        assert phase_names == ["research", "cross-pollinate", "synthesize"]

    def test_debate_has_blackboard_on_rounds(self):
        t = load_template("debate")
        rounds_phase = next(p for p in t.phases if p.name == "rounds")
        assert rounds_phase.blackboard is not None
        assert rounds_phase.blackboard.name == "transcript"
        assert rounds_phase.blackboard.file == "debate-transcript.md"
        assert rounds_phase.blackboard.access == "append"

    def test_map_reduce_has_fan_out(self):
        t = load_template("map-reduce")
        map_phase = next(p for p in t.phases if p.name == "map")
        assert map_phase.fan_out == "decompose"

    def test_red_blue_has_2_teams(self):
        t = load_template("red-blue")
        assert len(t.teams) == 2
        team_names = {team.name for team in t.teams}
        assert team_names == {"red", "blue"}

    def test_adversarial_has_engine_field(self):
        t = load_template("adversarial")
        assert t.engine == "ivory_tower.strategies.adversarial.AdversarialStrategy"

    def test_defaults_parsed_correctly(self):
        t = load_template("adversarial")
        assert t.defaults.agents_min == 2
        assert t.defaults.agents_max == 2
        assert t.defaults.rounds == 10

    def test_debate_defaults_sandbox_backend(self):
        t = load_template("debate")
        assert t.defaults.sandbox_backend == "local"
        assert t.defaults.agents_min == 2
        assert t.defaults.agents_max == 6
        assert t.defaults.rounds == 3
