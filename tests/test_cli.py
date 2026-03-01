"""Tests for ivory_tower.cli -- CLI layer."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from ivory_tower.cli import app
from ivory_tower.models import (
    Manifest,
    Flags,
    PhaseStatus,
    ResearchPhase,
    CrossPollinationPhase,
    SynthesisPhase,
)

runner = CliRunner()

AGENTS = ["claude-opus", "codex-5.3-xhigh", "amp-deep"]
AVAILABLE_AGENTS = ["claude-opus", "codex-5.3-xhigh", "amp-deep", "gemini-2.5-pro"]
TOPIC = "AI safety techniques in 2026"


def _make_manifest(
    agents: list[str] | None = None,
    synthesizer: str = "claude-opus",
    research_status: PhaseStatus = PhaseStatus.PENDING,
    cp_status: PhaseStatus = PhaseStatus.PENDING,
    synthesis_status: PhaseStatus = PhaseStatus.PENDING,
) -> Manifest:
    agents = agents or AGENTS
    return Manifest(
        run_id="20260301-143000-a1b2c3",
        topic=TOPIC,
        agents=agents,
        synthesizer=synthesizer,
        flags=Flags(),
        phases={
            "research": ResearchPhase(status=research_status),
            "cross_pollination": CrossPollinationPhase(status=cp_status),
            "synthesis": SynthesisPhase(
                status=synthesis_status,
                agent=synthesizer,
                output="phase3/final-report.md",
            ),
        },
        total_duration_seconds=None,
    )


# ---------------------------------------------------------------------------
# 1. Help commands
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_exits_zero(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_research_help(self):
        result = runner.invoke(app, ["research", "--help"])
        assert result.exit_code == 0
        assert "topic" in result.output.lower() or "TOPIC" in result.output


# ---------------------------------------------------------------------------
# 2. Research command -- error cases
# ---------------------------------------------------------------------------


class TestResearchErrors:
    @patch("ivory_tower.cli.sys")
    @patch("ivory_tower.cli.resolve_counselors_cmd", return_value=["counselors"])
    @patch("ivory_tower.cli.list_available_agents", return_value=AVAILABLE_AGENTS)
    def test_research_no_topic_errors(self, mock_list, mock_resolve, mock_sys):
        """No positional, no --file, isatty=True -> exit 1."""
        mock_sys.stdin.isatty.return_value = True
        result = runner.invoke(app, [
            "research",
            "--agents", "claude-opus,codex-5.3-xhigh",
            "--synthesizer", "claude-opus",
        ])
        assert result.exit_code != 0
        assert "topic" in result.output.lower()

    def test_research_agents_required(self):
        """Missing --agents -> error."""
        result = runner.invoke(app, [
            "research", "some topic",
            "--synthesizer", "claude-opus",
        ])
        assert result.exit_code != 0

    def test_research_synthesizer_required(self):
        """Missing --synthesizer -> error."""
        result = runner.invoke(app, [
            "research", "some topic",
            "--agents", "claude-opus",
        ])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 3. Research command -- success paths
# ---------------------------------------------------------------------------


class TestResearchSuccess:
    @patch("ivory_tower.cli.run_pipeline")
    @patch("ivory_tower.cli.validate_agents", return_value=[])
    @patch("ivory_tower.cli.list_available_agents", return_value=AVAILABLE_AGENTS)
    @patch("ivory_tower.cli.resolve_counselors_cmd", return_value=["counselors"])
    def test_research_from_file(
        self, mock_resolve, mock_list, mock_validate, mock_pipeline, tmp_path
    ):
        """Topic loaded from --file."""
        topic_file = tmp_path / "topic.txt"
        topic_file.write_text("Research quantum computing breakthroughs")

        run_dir = tmp_path / "research" / "run-123"
        run_dir.mkdir(parents=True)
        (run_dir / "phase3" / "final-report.md").parent.mkdir(parents=True)
        (run_dir / "phase3" / "final-report.md").write_text("report")
        mock_pipeline.return_value = run_dir

        result = runner.invoke(app, [
            "research",
            "--file", str(topic_file),
            "--agents", "claude-opus",
            "--synthesizer", "claude-opus",
        ])
        assert result.exit_code == 0
        # Verify pipeline was called with correct topic
        config = mock_pipeline.call_args[0][0]
        assert "quantum computing" in config.topic

    @patch("ivory_tower.cli.print_dry_run")
    @patch("ivory_tower.cli.run_pipeline")
    @patch("ivory_tower.cli.validate_agents", return_value=[])
    @patch("ivory_tower.cli.list_available_agents", return_value=AVAILABLE_AGENTS)
    @patch("ivory_tower.cli.resolve_counselors_cmd", return_value=["counselors"])
    def test_research_dry_run(
        self, mock_resolve, mock_list, mock_validate, mock_pipeline, mock_dry_run
    ):
        """--dry-run calls print_dry_run, not run_pipeline."""
        result = runner.invoke(app, [
            "research", "some topic",
            "--agents", "claude-opus",
            "--synthesizer", "claude-opus",
            "--dry-run",
        ])
        assert result.exit_code == 0
        mock_dry_run.assert_called_once()
        mock_pipeline.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Resume command
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_no_manifest_errors(self, tmp_path):
        """Resume on dir without manifest.json -> error."""
        result = runner.invoke(app, ["resume", str(tmp_path)])
        assert result.exit_code != 0
        assert "manifest" in result.output.lower()

    @patch("ivory_tower.cli.resume_pipeline")
    def test_resume_skips_completed_phases(self, mock_resume, tmp_path):
        """Resume delegates to resume_pipeline."""
        manifest = _make_manifest(
            research_status=PhaseStatus.COMPLETE,
            cp_status=PhaseStatus.PENDING,
            synthesis_status=PhaseStatus.PENDING,
        )
        manifest.save(tmp_path / "manifest.json")
        (tmp_path / "topic.md").write_text(TOPIC)

        mock_resume.return_value = tmp_path

        result = runner.invoke(app, ["resume", str(tmp_path)])
        assert result.exit_code == 0
        mock_resume.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Status command
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_command(self, tmp_path):
        """Load manifest, print summary."""
        manifest = _make_manifest(research_status=PhaseStatus.COMPLETE)
        manifest.save(tmp_path / "manifest.json")

        result = runner.invoke(app, ["status", str(tmp_path)])
        assert result.exit_code == 0
        assert "20260301-143000-a1b2c3" in result.output
        assert "complete" in result.output.lower()


# ---------------------------------------------------------------------------
# 6. List command
# ---------------------------------------------------------------------------


class TestList:
    def test_list_command(self, tmp_path):
        """With mock research dirs, lists them."""
        # Create two fake run dirs with manifests
        for run_id in ["20260301-100000-aaaaaa", "20260301-110000-bbbbbb"]:
            run_dir = tmp_path / run_id
            run_dir.mkdir()
            m = _make_manifest()
            m.run_id = run_id
            m.save(run_dir / "manifest.json")

        result = runner.invoke(app, ["list", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "aaaaaa" in result.output
        assert "bbbbbb" in result.output
