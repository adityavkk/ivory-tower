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
                max_rounds=3,
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

    # -- GEPA prompt feature verification ------------------------------------

    def test_manifest_has_dimension_history(self, run_dir: Path):
        """dimension_history should be persisted in the manifest for each seed."""
        m = Manifest.load(run_dir / "manifest.json")
        opt_phase = m.phases["adversarial_optimization"]
        for agent in (AGENT_A, AGENT_B):
            seed = opt_phase.seeds[agent]
            assert hasattr(seed, "dimension_history"), (
                f"{agent} SeedOptimizationResult missing dimension_history"
            )
            assert isinstance(seed.dimension_history, list), (
                f"{agent} dimension_history is not a list"
            )
            # With max_rounds=3, metric_budget=10: 1 seed + up to 3 iterations * 3 calls
            assert len(seed.dimension_history) >= 1, (
                f"{agent} dimension_history is empty -- evaluator didn't record rounds"
            )

    def test_dimension_history_has_per_dimension_scores(self, run_dir: Path):
        """Each dimension_history entry should have round, score, and dimensions."""
        m = Manifest.load(run_dir / "manifest.json")
        opt_phase = m.phases["adversarial_optimization"]
        for agent in (AGENT_A, AGENT_B):
            seed = opt_phase.seeds[agent]
            for entry in seed.dimension_history:
                assert "round" in entry, f"{agent} dim history missing 'round'"
                assert "score" in entry, f"{agent} dim history missing 'score'"
                assert "dimensions" in entry, f"{agent} dim history missing 'dimensions'"
                assert isinstance(entry["score"], (int, float)), (
                    f"{agent} dim history score is not numeric"
                )
                # If score > 0, dimensions should be populated
                if entry["score"] > 0:
                    dims = entry["dimensions"]
                    assert isinstance(dims, dict), f"{agent} dimensions is not a dict"
                    assert len(dims) > 0, (
                        f"{agent} scored {entry['score']} but dimensions dict is empty"
                    )

    def test_dimension_history_shows_score_movement(self, run_dir: Path):
        """With max_rounds=3 (metric_budget=10), we should see multiple rounds."""
        m = Manifest.load(run_dir / "manifest.json")
        opt_phase = m.phases["adversarial_optimization"]
        any_multi_round = False
        for agent in (AGENT_A, AGENT_B):
            seed = opt_phase.seeds[agent]
            if len(seed.dimension_history) > 1:
                any_multi_round = True
                rounds = [e["round"] for e in seed.dimension_history]
                assert rounds == sorted(rounds), (
                    f"{agent} dimension_history rounds are not in order: {rounds}"
                )
        # At least one agent should have multiple rounds of scoring
        assert any_multi_round, (
            "Neither agent had more than 1 round of dimension scoring -- "
            "GEPA optimization may not be running improvement rounds"
        )

    def test_improvement_prompts_exist(self, run_dir: Path):
        """Improvement prompt files should be written for each improvement round."""
        phase2 = run_dir / "phase2"
        for agent in (AGENT_A, AGENT_B):
            improve_dirs = sorted(phase2.glob(f"{agent}-improve-round-*"))
            # With max_rounds=3 (metric_budget=10) we expect multiple improvement
            # rounds.  Each iteration costs 2-3 metric calls.
            if not improve_dirs:
                # If no improvement dirs, check if this agent had non-zero seed score
                # (agents with 0.0 seed may not get improvement rounds)
                continue
            for d in improve_dirs:
                prompt_file = d / "improve-prompt.md"
                assert prompt_file.exists(), (
                    f"Missing improvement prompt in {d.name}"
                )
                prompt_text = prompt_file.read_text()
                assert len(prompt_text) > 100, (
                    f"Improvement prompt in {d.name} too short"
                )

    def test_improvement_prompt_has_trajectory(self, run_dir: Path):
        """Second and later improvement prompts should contain a Score Trajectory.

        With the corrected metric budget (1 + max_rounds * 3), max_rounds=3
        gives 10 metric calls -- enough for 3 GEPA iterations, meaning up to
        3 proposer calls.  The second proposer call should include trajectory
        data from the first round.  May still skip if GEPA exhausts its budget
        early due to accept/reject dynamics.
        """
        phase2 = run_dir / "phase2"
        found_trajectory = False
        for agent in (AGENT_A, AGENT_B):
            improve_dirs = sorted(phase2.glob(f"{agent}-improve-round-*"))
            if len(improve_dirs) < 2:
                # Need at least 2 improvement dirs to test trajectory
                continue
            # Skip the first improvement dir (no trajectory), check the rest
            for d in improve_dirs[1:]:
                prompt_file = d / "improve-prompt.md"
                if prompt_file.exists():
                    prompt_text = prompt_file.read_text()
                    if "Score Trajectory" in prompt_text:
                        found_trajectory = True
                        assert "Round" in prompt_text, (
                            f"Score Trajectory in {d.name} has no Round entries"
                        )
        if not found_trajectory:
            # Check if any agent had 2+ improvement dirs
            any_multi = any(
                len(list(phase2.glob(f"{a}-improve-round-*"))) >= 2
                for a in (AGENT_A, AGENT_B)
            )
            if any_multi:
                pytest.fail(
                    "Multiple improvement rounds exist but none after the "
                    "first contain a 'Score Trajectory' section"
                )
            else:
                pytest.skip(
                    "No agent had 2+ improvement rounds -- "
                    "trajectory requires at least 2 proposer calls"
                )

    def test_improvement_prompt_has_dimension_focus(self, run_dir: Path):
        """Improvement prompts should highlight the weakest dimension."""
        phase2 = run_dir / "phase2"
        found_focus = False
        for agent in (AGENT_A, AGENT_B):
            improve_dirs = sorted(phase2.glob(f"{agent}-improve-round-*"))
            for d in improve_dirs:
                prompt_file = d / "improve-prompt.md"
                if prompt_file.exists():
                    prompt_text = prompt_file.read_text()
                    if "Priority Focus" in prompt_text:
                        found_focus = True
                        assert "weakest dimension" in prompt_text.lower(), (
                            f"Priority Focus section in {d.name} doesn't mention weakest dimension"
                        )
        if not found_focus:
            # This is acceptable only if all scores were 0 (no dimensions parsed)
            m = Manifest.load(run_dir / "manifest.json")
            opt_phase = m.phases["adversarial_optimization"]
            all_zero = all(
                (opt_phase.seeds[a].seed_score or 0) == 0
                for a in (AGENT_A, AGENT_B)
            )
            if all_zero:
                pytest.skip(
                    "All seed scores were 0 -- no dimensions available for focus targeting"
                )
            else:
                pytest.fail(
                    "No improvement prompt contained a 'Priority Focus' section "
                    "despite non-zero scores"
                )

    def test_round_debug_captures_dimension_data(self, run_dir: Path):
        """round-debug.json files should capture evaluator dimension breakdown."""
        phase2 = run_dir / "phase2"
        found_debug = False
        for agent in (AGENT_A, AGENT_B):
            improve_dirs = sorted(phase2.glob(f"{agent}-improve-round-*"))
            for d in improve_dirs:
                debug_file = d / "round-debug.json"
                if debug_file.exists():
                    found_debug = True
                    data = json.loads(debug_file.read_text())
                    assert "feedback_score" in data, (
                        f"round-debug.json in {d.name} missing feedback_score"
                    )
                    assert "feedback_dimensions" in data, (
                        f"round-debug.json in {d.name} missing feedback_dimensions"
                    )
                    assert isinstance(data["feedback_dimensions"], dict)
        if not found_debug:
            # Acceptable only if no improvement rounds happened at all
            any_improve = any(
                list(phase2.glob(f"{a}-improve-round-*"))
                for a in (AGENT_A, AGENT_B)
            )
            if any_improve:
                pytest.fail("Improvement dirs exist but no round-debug.json files found")
            else:
                pytest.skip("No improvement rounds occurred")

    def test_judging_round_dirs_contain_judge_prompt(self, run_dir: Path):
        """Each judging round directory should have a judge-prompt.md file."""
        phase2 = run_dir / "phase2"
        # Filter to directories only -- the judging dir also contains .md
        # summary files alongside the round directories.
        judging_dirs = sorted(
            d for d in phase2.glob("judging/round-*") if d.is_dir()
        )
        assert len(judging_dirs) >= 2, (
            f"Expected at least 2 judging round dirs, found {len(judging_dirs)}"
        )
        for d in judging_dirs:
            prompt = d / "judge-prompt.md"
            assert prompt.exists(), f"Missing judge-prompt.md in {d.name}"
            text = prompt.read_text()
            assert len(text) > 100, f"Judge prompt in {d.name} too short"

    def test_optimization_log_has_dimension_history(self, run_dir: Path):
        """Optimization log should include per-round dimension breakdowns."""
        for agent in (AGENT_A, AGENT_B):
            path = run_dir / "phase2" / f"{agent}-optimization-log.json"
            if not path.exists():
                continue
            log = json.loads(path.read_text())
            assert "dimension_history" in log, (
                f"{agent} optimization log missing dimension_history"
            )
            dim_hist = log["dimension_history"]
            assert isinstance(dim_hist, list)
            # Should have at least 1 entry (seed evaluation)
            if log.get("seed_score", 0) > 0 or log.get("final_score", 0) > 0:
                assert len(dim_hist) >= 1, (
                    f"{agent} has non-zero scores but empty dimension_history in log"
                )


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
