"""Live end-to-end tests that call real external agents and APIs.

These are NEVER run as part of the normal test suite.  They require
working credentials and network access.

Run with:
    uv run pytest -m live -v               # all live tests
    uv run pytest -m live -k adversarial    # just adversarial

Output is written to the project's ``research/`` directory (not tmp_path)
because some agents (e.g. opencode) reject file reads outside the project
tree.  Each run gets its own timestamped subdirectory so nothing is
overwritten.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ivory_tower.engine import RunConfig, run_pipeline
from ivory_tower.models import Manifest, PhaseStatus

# ---------------------------------------------------------------------------
# Constants -- edit these to match your counselors configuration.
# ---------------------------------------------------------------------------

AGENT_A = "opencode-anthropic-fast"
AGENT_B = "opencode-openai-fast"
SYNTHESIZER = AGENT_A

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESEARCH_DIR = PROJECT_ROOT / "research"

TOPIC = (
    "Compare WebSocket vs Server-Sent Events (SSE) for real-time web "
    "applications. Cover: protocol differences, browser support, "
    "scalability trade-offs, and when to choose each."
)


def _agents_available() -> bool:
    """Quick check that counselors CLI is on PATH."""
    return shutil.which("counselors") is not None


def _gepa_available() -> bool:
    try:
        from gepa.optimize_anything import optimize_anything  # noqa: F401

        return True
    except ImportError:
        return False


skip_no_agents = pytest.mark.skipif(
    not _agents_available(), reason="counselors CLI not on PATH"
)
skip_no_gepa = pytest.mark.skipif(
    not _gepa_available(), reason="gepa package not installed"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_file_nonempty(p: Path, label: str = "") -> str:
    """Assert a file exists, is non-empty, and return its text."""
    assert p.exists(), f"Expected {label or p.name} at {p}"
    text = p.read_text()
    assert len(text.strip()) > 0, f"{label or p.name} is empty"
    return text


# ---------------------------------------------------------------------------
# Live tests -- adversarial
# ---------------------------------------------------------------------------


@pytest.mark.live
@skip_no_agents
@skip_no_gepa
class TestAdversarialLiveE2E:
    """Real adversarial pipeline with live agents and GEPA.

    The pipeline runs once (session-scoped fixture) and all tests in this
    class share the same run directory.
    """

    _run_dir: Path | None = None

    @pytest.fixture(autouse=True)
    def run_dir(self) -> Path:
        """Run the adversarial pipeline once per class, reuse across tests."""
        if TestAdversarialLiveE2E._run_dir is None:
            config = RunConfig(
                topic=TOPIC,
                agents=[AGENT_A, AGENT_B],
                synthesizer=SYNTHESIZER,
                output_dir=RESEARCH_DIR,
                strategy="adversarial",
                max_rounds=2,
                verbose=True,
            )
            TestAdversarialLiveE2E._run_dir = run_pipeline(config)
        return TestAdversarialLiveE2E._run_dir

    # -- directory structure -------------------------------------------------

    def test_run_dir_created(self, run_dir: Path):
        assert run_dir.exists()
        assert run_dir.is_dir()

    def test_topic_file(self, run_dir: Path):
        text = _assert_file_nonempty(run_dir / "topic.md", "topic.md")
        assert "WebSocket" in text or "SSE" in text

    def test_manifest_valid_json(self, run_dir: Path):
        text = _assert_file_nonempty(run_dir / "manifest.json", "manifest.json")
        data = json.loads(text)
        assert data["strategy"] == "adversarial"

    # -- manifest state ------------------------------------------------------

    def test_manifest_strategy(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert m.strategy == "adversarial"

    def test_manifest_agents(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert set(m.agents) == {AGENT_A, AGENT_B}

    def test_seed_generation_complete(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert m.phases["seed_generation"].status == PhaseStatus.COMPLETE

    def test_optimization_finished(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert m.phases["adversarial_optimization"].status in (
            PhaseStatus.COMPLETE,
            PhaseStatus.PARTIAL,
        )

    def test_synthesis_complete(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert m.phases["synthesis"].status == PhaseStatus.COMPLETE

    def test_total_duration_recorded(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert m.total_duration_seconds is not None
        assert m.total_duration_seconds > 0

    # -- phase 1: seed reports -----------------------------------------------

    def test_seed_reports_exist(self, run_dir: Path):
        for agent in (AGENT_A, AGENT_B):
            _assert_file_nonempty(
                run_dir / "phase1" / f"{agent}-seed.md",
                f"{agent} seed report",
            )

    def test_seed_reports_substantial(self, run_dir: Path):
        """Seed reports should be real research, not stubs."""
        for agent in (AGENT_A, AGENT_B):
            text = (run_dir / "phase1" / f"{agent}-seed.md").read_text()
            assert len(text) > 200, (
                f"{agent} seed report too short ({len(text)} chars)"
            )

    # -- phase 2: optimization artifacts -------------------------------------

    def test_optimized_reports_exist(self, run_dir: Path):
        for agent in (AGENT_A, AGENT_B):
            _assert_file_nonempty(
                run_dir / "phase2" / f"{agent}-optimized.md",
                f"{agent} optimized report",
            )

    def test_optimized_reports_substantial(self, run_dir: Path):
        for agent in (AGENT_A, AGENT_B):
            text = (run_dir / "phase2" / f"{agent}-optimized.md").read_text()
            assert len(text) > 200, (
                f"{agent} optimized report too short ({len(text)} chars)"
            )

    def test_optimization_logs_exist(self, run_dir: Path):
        for agent in (AGENT_A, AGENT_B):
            path = run_dir / "phase2" / f"{agent}-optimization-log.json"
            text = _assert_file_nonempty(path, f"{agent} opt log")
            log = json.loads(text)
            assert "seed_score" in log
            assert "final_score" in log
            assert "score_history" in log

    def test_optimization_scores_are_numeric(self, run_dir: Path):
        for agent in (AGENT_A, AGENT_B):
            path = run_dir / "phase2" / f"{agent}-optimization-log.json"
            log = json.loads(path.read_text())
            assert isinstance(log["seed_score"], (int, float))
            assert isinstance(log["final_score"], (int, float))
            assert 0.0 <= log["final_score"] <= 10.0

    # -- phase 3: synthesis --------------------------------------------------

    def test_final_report_exists(self, run_dir: Path):
        _assert_file_nonempty(
            run_dir / "phase3" / "final-report.md",
            "final synthesis report",
        )

    def test_final_report_substantial(self, run_dir: Path):
        text = (run_dir / "phase3" / "final-report.md").read_text()
        assert len(text) > 500, f"Final report too short ({len(text)} chars)"

    def test_final_report_on_topic(self, run_dir: Path):
        """Final report should mention key topic terms."""
        text = (run_dir / "phase3" / "final-report.md").read_text().lower()
        assert any(
            term in text
            for term in ("websocket", "sse", "server-sent", "real-time", "realtime")
        ), "Final report doesn't appear to be on topic"


# ---------------------------------------------------------------------------
# Live tests -- council
# ---------------------------------------------------------------------------


@pytest.mark.live
@skip_no_agents
class TestCouncilLiveE2E:
    """Real council pipeline with live agents (no GEPA needed)."""

    _run_dir: Path | None = None

    @pytest.fixture(autouse=True)
    def run_dir(self) -> Path:
        if TestCouncilLiveE2E._run_dir is None:
            config = RunConfig(
                topic=TOPIC,
                agents=[AGENT_A, AGENT_B],
                synthesizer=SYNTHESIZER,
                output_dir=RESEARCH_DIR,
                strategy="council",
                verbose=True,
            )
            TestCouncilLiveE2E._run_dir = run_pipeline(config)
        return TestCouncilLiveE2E._run_dir

    def test_manifest_strategy(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert m.strategy == "council"

    def test_all_phases_complete(self, run_dir: Path):
        m = Manifest.load(run_dir / "manifest.json")
        assert m.phases["research"].status == PhaseStatus.COMPLETE
        assert m.phases["cross_pollination"].status == PhaseStatus.COMPLETE
        assert m.phases["synthesis"].status == PhaseStatus.COMPLETE

    def test_final_report_exists(self, run_dir: Path):
        _assert_file_nonempty(
            run_dir / "phase3" / "final-report.md",
            "final synthesis report",
        )

    def test_final_report_on_topic(self, run_dir: Path):
        text = (run_dir / "phase3" / "final-report.md").read_text().lower()
        assert any(
            term in text
            for term in ("websocket", "sse", "server-sent", "real-time", "realtime")
        ), "Final report doesn't appear to be on topic"
