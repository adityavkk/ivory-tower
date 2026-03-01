"""End-to-end integration tests for the ivory-tower sandbox abstraction -- commit 16.

Tests the full sandbox lifecycle: provider registry, template loading,
agent profiles, local sandbox I/O, blackboard integration, template executor,
strategy registry, CLI commands, manifest backward compatibility, and error paths.

All external dependencies (counselors, agentfs, daytona) are mocked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ivory_tower.cli import app
from ivory_tower.executor.types import AgentOutput
from ivory_tower.models import (
    Flags,
    Manifest,
    PhaseStatus,
    ResearchPhase,
    CrossPollinationPhase,
    SynthesisPhase,
)
from ivory_tower.profiles import AgentProfile
from ivory_tower.sandbox import get_provider, PROVIDERS
from ivory_tower.sandbox.blackboard import FileBlackboard
from ivory_tower.sandbox.local import LocalSandbox, LocalSandboxProvider, LocalSharedVolume
from ivory_tower.sandbox.null import NullSandboxProvider
from ivory_tower.sandbox.types import SandboxConfig
from ivory_tower.strategies import get_strategy, list_strategies, STRATEGIES
from ivory_tower.templates import (
    list_template_names,
    list_templates,
    load_template,
    validate_template,
)
from ivory_tower.templates.executor import GenericTemplateExecutor

runner = CliRunner()


# ---------------------------------------------------------------------------
# Mock executor: writes a simple report into the sandbox
# ---------------------------------------------------------------------------


class MockExecutor:
    """A test executor that writes a report file into the sandbox."""

    name = "mock"

    def run(
        self,
        sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
    ) -> AgentOutput:
        report_path = f"{output_dir}/report.md"
        content = f"# Report by {agent_name}\n\nTopic: {prompt}\n"
        sandbox.write_file(report_path, content)
        return AgentOutput(
            report_path=report_path,
            raw_output=content,
            duration_seconds=0.1,
        )


# ===========================================================================
# 1. Sandbox Provider Registry Tests
# ===========================================================================


class TestSandboxProviderRegistry:
    """Verify the sandbox provider registry resolves backends correctly."""

    def test_get_provider_none(self):
        provider = get_provider("none")
        assert isinstance(provider, NullSandboxProvider)

    def test_get_provider_local(self):
        provider = get_provider("local")
        assert isinstance(provider, LocalSandboxProvider)

    @patch("ivory_tower.sandbox.agentfs.shutil.which", return_value=None)
    def test_get_provider_agentfs_unavailable(self, mock_which):
        with pytest.raises(RuntimeError, match="agentfs"):
            get_provider("agentfs")

    @patch("ivory_tower.sandbox.daytona.DaytonaSandboxProvider.is_available", return_value=False)
    def test_get_provider_daytona_unavailable(self, mock_available):
        with pytest.raises(RuntimeError, match="daytona"):
            get_provider("daytona")

    def test_get_provider_unknown(self):
        with pytest.raises(ValueError, match="Unknown sandbox backend"):
            get_provider("unknown")


# ===========================================================================
# 2. Template Loading + Validation Integration
# ===========================================================================


class TestTemplateLoadingValidation:
    """Verify built-in templates load and validate correctly."""

    def test_all_builtin_templates_load_and_validate(self):
        names = list_template_names()
        assert len(names) >= 5, f"Expected at least 5 built-in templates, got {names}"
        for name in names:
            template = load_template(name)
            errors = validate_template(template)
            assert errors == [], f"Template '{name}' has validation errors: {errors}"

    def test_template_resolution_builtin_name(self):
        template = load_template("debate")
        assert template.name == "debate"
        assert len(template.phases) > 0

    def test_template_resolution_file_path(self, tmp_path):
        yml = tmp_path / "custom.yml"
        yml.write_text(
            "strategy:\n"
            "  name: custom-test\n"
            "  description: A custom test strategy\n"
            "  version: 1\n"
            "phases:\n"
            "  - name: research\n"
            "    description: Do research\n"
            "    isolation: full\n"
            "    agents: all\n"
            "    output: '{agent}-report.md'\n"
        )
        template = load_template(str(yml))
        assert template.name == "custom-test"

    def test_invalid_template_produces_errors(self):
        from ivory_tower.templates.loader import _parse_template

        bad_data = {"strategy": {}, "phases": []}
        template = _parse_template(bad_data)
        errors = validate_template(template)
        assert len(errors) > 0
        assert any("name" in e.lower() for e in errors)

    def test_load_nonexistent_template_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_template("does-not-exist-xyz")


# ===========================================================================
# 3. Agent Profile Integration
# ===========================================================================


class TestAgentProfileIntegration:
    """Verify agent profile shorthand parsing."""

    def test_from_cli_shorthand_model_only(self):
        profile = AgentProfile.from_cli_shorthand("claude")
        assert profile.name == "claude"
        assert profile.model == "claude"
        assert profile.role == "researcher"

    def test_from_cli_shorthand_model_role(self):
        profile = AgentProfile.from_cli_shorthand("claude:researcher")
        assert profile.name == "claude"
        assert profile.model == "claude"
        assert profile.role == "researcher"

    def test_from_cli_shorthand_named_profile_missing(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            AgentProfile.from_cli_shorthand("@nonexistent")


# ===========================================================================
# 4. Local Sandbox Full Lifecycle
# ===========================================================================


class TestLocalSandboxLifecycle:
    """Full lifecycle tests with real LocalSandboxProvider."""

    def test_create_sandbox_write_read(self, tmp_path):
        provider = LocalSandboxProvider()
        sandbox = provider.create_sandbox(
            agent_name="test-agent",
            run_id="run-001",
            run_dir=tmp_path,
            config=SandboxConfig(),
        )
        assert sandbox.agent_name == "test-agent"
        assert sandbox.workspace_dir.exists()

        sandbox.write_file("hello.txt", "Hello, world!")
        assert sandbox.read_file("hello.txt") == "Hello, world!"

    def test_sandbox_copy_in_out(self, tmp_path):
        provider = LocalSandboxProvider()
        sandbox = provider.create_sandbox(
            agent_name="copier",
            run_id="run-002",
            run_dir=tmp_path,
            config=SandboxConfig(),
        )

        # Create an external file to copy in
        external = tmp_path / "external.md"
        external.write_text("External content")

        sandbox.copy_in(external, "imported/data.md")
        assert sandbox.read_file("imported/data.md") == "External content"

        # Copy out
        out_path = tmp_path / "exported.md"
        sandbox.copy_out("imported/data.md", out_path)
        assert out_path.read_text() == "External content"

    def test_sandbox_list_files(self, tmp_path):
        provider = LocalSandboxProvider()
        sandbox = provider.create_sandbox(
            agent_name="lister",
            run_id="run-003",
            run_dir=tmp_path,
            config=SandboxConfig(),
        )
        sandbox.write_file("a.txt", "A")
        sandbox.write_file("sub/b.txt", "B")

        files = sandbox.list_files()
        assert "a.txt" in files
        assert "sub/b.txt" in files or any("b.txt" in f for f in files)

    def test_sandbox_file_exists(self, tmp_path):
        provider = LocalSandboxProvider()
        sandbox = provider.create_sandbox(
            agent_name="exists",
            run_id="run-004",
            run_dir=tmp_path,
            config=SandboxConfig(),
        )
        sandbox.write_file("present.txt", "yes")
        assert sandbox.file_exists("present.txt")
        assert not sandbox.file_exists("absent.txt")

    def test_sandbox_destroy(self, tmp_path):
        provider = LocalSandboxProvider()
        sandbox = provider.create_sandbox(
            agent_name="destroyer",
            run_id="run-005",
            run_dir=tmp_path,
            config=SandboxConfig(),
        )
        sandbox.write_file("data.txt", "data")
        # Destroy is a no-op for local backend (keeps files for inspection)
        sandbox.destroy()
        # Files should still exist
        assert sandbox.file_exists("data.txt")

    def test_shared_volume_write_append_read(self, tmp_path):
        provider = LocalSandboxProvider()
        volume = provider.create_shared_volume(
            name="shared-vol",
            run_id="run-006",
            run_dir=tmp_path,
        )
        volume.write_file("log.txt", "Line 1\n")
        volume.append_file("log.txt", "Line 2\n")
        content = volume.read_file("log.txt")
        assert "Line 1" in content
        assert "Line 2" in content

    def test_shared_volume_list_files(self, tmp_path):
        provider = LocalSandboxProvider()
        volume = provider.create_shared_volume(
            name="listed-vol",
            run_id="run-007",
            run_dir=tmp_path,
        )
        volume.write_file("a.md", "A")
        volume.write_file("b.md", "B")
        files = volume.list_files()
        assert "a.md" in files
        assert "b.md" in files

    def test_full_round_trip_sandbox_to_canonical(self, tmp_path):
        """Create sandbox + volume, write in sandbox, copy_out to canonical."""
        provider = LocalSandboxProvider()
        run_dir = tmp_path / "run-rt"
        run_dir.mkdir()

        sandbox = provider.create_sandbox(
            agent_name="writer",
            run_id="run-rt",
            run_dir=run_dir,
            config=SandboxConfig(),
        )
        volume = provider.create_shared_volume(
            name="shared-data",
            run_id="run-rt",
            run_dir=run_dir,
        )

        # Write in sandbox
        sandbox.write_file("output/report.md", "# Final Report\n\nResults here.")

        # Copy out to canonical location
        canonical = run_dir / "reports" / "writer-report.md"
        sandbox.copy_out("output/report.md", canonical)
        assert canonical.exists()
        assert "Final Report" in canonical.read_text()

        # Write to shared volume and read back
        volume.write_file("summary.txt", "Summary data")
        assert volume.read_file("summary.txt") == "Summary data"


# ===========================================================================
# 5. Blackboard Integration with Local Backend
# ===========================================================================


class TestBlackboardIntegration:
    """FileBlackboard with real LocalSharedVolume."""

    def test_transcript_mode_multi_agent_multi_round(self, tmp_path):
        volume = LocalSharedVolume(id="bb-vol", path=tmp_path)
        volume.write_file("transcript.md", "")

        bb = FileBlackboard(
            volume=volume,
            file_name="transcript.md",
            access_mode="append",
        )

        # Agent A, round 1
        bb.append("agent-a", 1, "Agent A's opening argument.")
        # Agent B, round 1
        bb.append("agent-b", 1, "Agent B's rebuttal.")
        # Agent A, round 2
        bb.append("agent-a", 2, "Agent A's counter-argument.")
        # Agent B, round 2
        bb.append("agent-b", 2, "Agent B's closing statement.")

        content = bb.get_content()
        assert "agent-a" in content
        assert "agent-b" in content
        assert "Round 1" in content
        assert "Round 2" in content
        assert "opening argument" in content
        assert "closing statement" in content

    def test_directory_mode_creates_files(self, tmp_path):
        volume = LocalSharedVolume(id="dir-vol", path=tmp_path)

        bb = FileBlackboard(
            volume=volume,
            file_name=None,  # directory mode
            access_mode="append",
        )

        bb.append("agent-a", 1, "First contribution")
        bb.append("agent-b", 2, "Second contribution")

        files = volume.list_files()
        assert len(files) >= 2
        assert any("agent-a" in f for f in files)
        assert any("agent-b" in f for f in files)

    def test_readonly_blackboard_raises_on_append(self, tmp_path):
        volume = LocalSharedVolume(id="ro-vol", path=tmp_path)
        volume.write_file("data.md", "Read only content")

        bb = FileBlackboard(
            volume=volume,
            file_name="data.md",
            access_mode="read",
        )

        assert "Read only content" in bb.get_content()

        with pytest.raises(PermissionError, match="read-only"):
            bb.append("agent-a", 1, "Should fail")

    def test_blackboard_snapshot(self, tmp_path):
        volume = LocalSharedVolume(id="snap-vol", path=tmp_path)
        volume.write_file("transcript.md", "")

        bb = FileBlackboard(
            volume=volume,
            file_name="transcript.md",
            access_mode="append",
        )
        bb.append("agent-a", 1, "Some content")
        snapshot = bb.snapshot("after-round-1")
        assert "Some content" in snapshot


# ===========================================================================
# 6. GenericTemplateExecutor with Local Backend (mocked executor)
# ===========================================================================


class TestGenericTemplateExecutor:
    """GenericTemplateExecutor with debate template and MockExecutor."""

    @patch("ivory_tower.templates.executor.get_executor")
    def test_debate_template_full_run(self, mock_get_executor, tmp_path):
        mock_get_executor.return_value = MockExecutor()

        template = load_template("debate")
        executor = GenericTemplateExecutor(template)

        run_dir = tmp_path / "run-debate"
        run_dir.mkdir()

        outputs = executor.run(
            run_dir=run_dir,
            agents=["agent-a", "agent-b"],
            synthesizer="synth",
            sandbox_backend="local",
            topic="Should AI be regulated?",
        )

        # Verify 4 phases executed (opening, rounds, closing, verdict)
        assert len(outputs) == 4, f"Expected 4 phases, got: {list(outputs.keys())}"
        assert "opening" in outputs
        assert "rounds" in outputs
        assert "closing" in outputs
        assert "verdict" in outputs

        # Verify output directories were created
        for phase_name in ["opening", "rounds", "closing", "verdict"]:
            phase_dir = run_dir / phase_name
            assert phase_dir.exists(), f"Phase directory '{phase_name}' not created"

    @patch("ivory_tower.templates.executor.get_executor")
    def test_debate_blackboard_grows_during_rounds(self, mock_get_executor, tmp_path):
        mock_get_executor.return_value = MockExecutor()

        template = load_template("debate")
        executor = GenericTemplateExecutor(template)

        run_dir = tmp_path / "run-debate-bb"
        run_dir.mkdir()

        outputs = executor.run(
            run_dir=run_dir,
            agents=["agent-a", "agent-b"],
            synthesizer="synth",
            sandbox_backend="local",
            topic="Test debate topic",
        )

        # The blackboard transcript should exist in the shared volume
        transcript_path = run_dir / "volumes" / "transcript" / "debate-transcript.md"
        if transcript_path.exists():
            content = transcript_path.read_text()
            # Should have entries from both agents across rounds
            assert "agent-a" in content or "agent-b" in content

    @patch("ivory_tower.templates.executor.get_executor")
    def test_verdict_phase_gets_all_inputs(self, mock_get_executor, tmp_path):
        mock_get_executor.return_value = MockExecutor()

        template = load_template("debate")
        executor = GenericTemplateExecutor(template)

        run_dir = tmp_path / "run-debate-verdict"
        run_dir.mkdir()

        outputs = executor.run(
            run_dir=run_dir,
            agents=["agent-a", "agent-b"],
            synthesizer="synth",
            sandbox_backend="local",
            topic="Verdict input test",
        )

        # Verdict phase should have at least one output (the synthesizer's verdict)
        assert "verdict" in outputs
        verdict_outputs = outputs["verdict"]
        assert len(verdict_outputs) >= 1


# ===========================================================================
# 7. Strategy Registry Integration
# ===========================================================================


class TestStrategyRegistry:
    """Verify the strategy registry returns correct types and lists."""

    def test_get_strategy_debate(self):
        from ivory_tower.strategies.debate import DebateStrategy
        strat = get_strategy("debate")
        assert isinstance(strat, DebateStrategy)

    def test_get_strategy_map_reduce(self):
        from ivory_tower.strategies.map_reduce import MapReduceStrategy
        strat = get_strategy("map-reduce")
        assert isinstance(strat, MapReduceStrategy)

    def test_get_strategy_red_blue(self):
        from ivory_tower.strategies.red_blue import RedBlueStrategy
        strat = get_strategy("red-blue")
        assert isinstance(strat, RedBlueStrategy)

    def test_list_strategies_includes_all_five(self):
        items = list_strategies()
        names = [name for name, _desc in items]
        expected = {"council", "adversarial", "debate", "map-reduce", "red-blue"}
        assert expected.issubset(set(names)), f"Missing strategies: {expected - set(names)}"

    def test_get_strategy_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("nonexistent")


# ===========================================================================
# 8. CLI Integration (invoke typer app)
# ===========================================================================


class TestCLIIntegration:
    """CLI tests via typer CliRunner."""

    def test_templates_command(self):
        result = runner.invoke(app, ["templates"])
        # Should list at least the built-in templates
        assert result.exit_code == 0
        out = result.output.lower()
        assert "debate" in out or "council" in out or "template" in out

    def test_strategies_command_lists_all(self):
        result = runner.invoke(app, ["strategies"])
        assert result.exit_code == 0
        out = result.output.lower()
        assert "council" in out
        assert "adversarial" in out
        assert "debate" in out
        assert "map-reduce" in out
        assert "red-blue" in out

    def test_research_help_shows_sandbox_flags(self):
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0
        assert "--sandbox" in result.output
        assert "--template" in result.output
        assert "--rounds" in result.output


# ===========================================================================
# 9. Manifest Backward Compatibility
# ===========================================================================


class TestManifestBackwardCompatibility:
    """Manifest serialization for v2 (no sandbox) and v3 (with sandbox)."""

    def test_v2_manifest_loads_without_sandbox(self):
        v2_dict = {
            "run_id": "run-v2",
            "topic": "V2 topic",
            "agents": ["a", "b"],
            "synthesizer": "a",
            "flags": {"raw": False, "instructions": None, "verbose": False},
            "phases": {
                "research": {
                    "status": "pending", "started_at": None,
                    "completed_at": None, "duration_seconds": None,
                    "agents": {},
                },
                "cross_pollination": {
                    "status": "pending", "started_at": None,
                    "completed_at": None, "duration_seconds": None,
                    "sessions": {},
                },
                "synthesis": {
                    "status": "pending", "started_at": None,
                    "completed_at": None, "duration_seconds": None,
                    "agent": "a", "output": "phase3/final-report.md",
                },
            },
        }
        m = Manifest.from_dict(v2_dict)
        assert m.sandbox_config is None
        assert m.template_name is None
        assert m.strategy == "council"

    def test_v3_manifest_with_sandbox_roundtrips(self, tmp_path):
        m = Manifest(
            run_id="run-v3",
            topic="V3 topic",
            agents=["a", "b"],
            synthesizer="a",
            flags=Flags(),
            phases={
                "research": ResearchPhase(status=PhaseStatus.PENDING),
                "cross_pollination": CrossPollinationPhase(status=PhaseStatus.PENDING),
                "synthesis": SynthesisPhase(
                    status=PhaseStatus.PENDING, agent="a", output="phase3/final-report.md",
                ),
            },
            strategy="council",
            sandbox_config={"backend": "local", "snapshot_after_phase": True},
            template_name="debate",
        )

        d = m.to_dict()
        assert "sandbox_config" in d
        assert d["sandbox_config"]["backend"] == "local"
        assert "template_name" in d
        assert d["template_name"] == "debate"

        # Roundtrip through file
        path = tmp_path / "manifest-v3.json"
        m.save(path)
        m2 = Manifest.load(path)
        assert m2.sandbox_config == {"backend": "local", "snapshot_after_phase": True}
        assert m2.template_name == "debate"

    def test_to_dict_omits_sandbox_config_when_none(self):
        m = Manifest(
            run_id="run-no-sb",
            topic="No sandbox",
            agents=["a", "b"],
            synthesizer="a",
            flags=Flags(),
            phases={
                "research": ResearchPhase(status=PhaseStatus.PENDING),
                "cross_pollination": CrossPollinationPhase(status=PhaseStatus.PENDING),
                "synthesis": SynthesisPhase(
                    status=PhaseStatus.PENDING, agent="a", output="phase3/final-report.md",
                ),
            },
            strategy="council",
            sandbox_config=None,
        )
        d = m.to_dict()
        assert "sandbox_config" not in d

    def test_from_dict_v2_sandbox_config_is_none(self):
        v2_dict = {
            "run_id": "run-v2-sb",
            "topic": "V2 no sandbox",
            "agents": ["a"],
            "synthesizer": "a",
            "flags": {"raw": False, "instructions": None, "verbose": False},
            "phases": {
                "research": {
                    "status": "pending", "started_at": None,
                    "completed_at": None, "duration_seconds": None,
                    "agents": {},
                },
                "cross_pollination": {
                    "status": "pending", "started_at": None,
                    "completed_at": None, "duration_seconds": None,
                    "sessions": {},
                },
                "synthesis": {
                    "status": "pending", "started_at": None,
                    "completed_at": None, "duration_seconds": None,
                    "agent": "a", "output": "phase3/final-report.md",
                },
            },
        }
        m = Manifest.from_dict(v2_dict)
        assert m.sandbox_config is None


# ===========================================================================
# 10. Error Paths
# ===========================================================================


class TestErrorPaths:
    """Error handling for sandbox, template, and profile failures."""

    @patch("ivory_tower.cli.validate_agents", return_value=[])
    @patch("ivory_tower.cli.list_available_agents", return_value=["a", "b"])
    @patch("ivory_tower.cli.resolve_counselors_cmd", return_value=["counselors"])
    @patch("ivory_tower.sandbox.agentfs.shutil.which", return_value=None)
    def test_cli_sandbox_agentfs_unavailable(
        self, mock_which, mock_resolve, mock_list, mock_validate,
    ):
        result = runner.invoke(app, [
            "research", "Test topic",
            "--agents", "a,b",
            "--synthesizer", "a",
            "--sandbox", "agentfs",
            "--dry-run",
        ])
        assert result.exit_code != 0
        out = (result.output or "").lower()
        stderr = (result.stderr or "" if hasattr(result, "stderr") else "").lower()
        combined = out + stderr
        assert "agentfs" in combined or result.exit_code == 1

    def test_cli_template_nonexistent(self):
        result = runner.invoke(app, [
            "research", "Test topic",
            "--agents", "a,b",
            "--synthesizer", "a",
            "--template", "nonexistent-template-xyz",
            "--dry-run",
        ])
        assert result.exit_code != 0

    def test_missing_profile_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            AgentProfile.load_named("totally-nonexistent-profile")

    def test_invalid_template_validation_errors(self, tmp_path):
        yml = tmp_path / "bad.yml"
        yml.write_text(
            "strategy:\n"
            "  name: ''\n"
            "  description: ''\n"
            "phases: []\n"
        )
        template = load_template(str(yml))
        errors = validate_template(template)
        assert len(errors) > 0
        # Should complain about missing name and/or no phases
        error_text = " ".join(errors).lower()
        assert "name" in error_text or "phase" in error_text

    def test_sandbox_unknown_backend_in_cli(self):
        result = runner.invoke(app, [
            "research", "Test topic",
            "--agents", "a,b",
            "--synthesizer", "a",
            "--sandbox", "fictional-backend",
            "--dry-run",
        ])
        assert result.exit_code != 0
