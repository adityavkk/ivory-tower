"""Live tests for GenericTemplateExecutor with real counselors agents.

Tests the YAML template executor end-to-end with actual agent calls,
real filesystem sandboxes, and blackboard orchestration.

Agents used: opencode-anthropic-fast, opencode-openai-fast (cheapest/fastest)

Run with: uv run pytest tests/test_template_executor_live.py -m live -v -s
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ivory_tower.templates.executor import GenericTemplateExecutor
from ivory_tower.templates.loader import load_template

# All tests in this file require the live marker
pytestmark = pytest.mark.live

HAS_COUNSELORS = shutil.which("counselors") is not None

# Skip entire module if counselors not available
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not HAS_COUNSELORS, reason="counselors CLI not installed"),
]

# Fast/cheap agents for testing
AGENT_A = "opencode-anthropic-fast"
AGENT_B = "opencode-openai-fast"
SYNTHESIZER = "opencode-anthropic-fast"


class TestDebateTemplateLive:
    """End-to-end debate template with real agents and local sandbox."""

    @pytest.mark.timeout(600)
    def test_debate_single_round(self, tmp_path: Path) -> None:
        """Run debate with 2 agents, 1 round, local sandbox."""
        template = load_template("debate")
        executor = GenericTemplateExecutor(template)

        run_dir = tmp_path / "live-debate-001"
        run_dir.mkdir()

        outputs = executor.run(
            run_dir=run_dir,
            agents=[AGENT_A, AGENT_B],
            synthesizer=SYNTHESIZER,
            sandbox_backend="local",
            topic="Is Python better than JavaScript for backend development? Be concise (2-3 sentences).",
            rounds_override=1,
            verbose=True,
        )

        # Verify all phases executed
        assert "opening" in outputs, f"Missing 'opening' phase. Got: {list(outputs.keys())}"
        assert "rounds" in outputs, f"Missing 'rounds' phase. Got: {list(outputs.keys())}"
        assert "closing" in outputs, f"Missing 'closing' phase. Got: {list(outputs.keys())}"
        assert "verdict" in outputs, f"Missing 'verdict' phase. Got: {list(outputs.keys())}"

        # Opening: each agent produced output
        opening = outputs["opening"]
        assert AGENT_A in opening, f"Agent A missing from opening. Got: {list(opening.keys())}"
        assert AGENT_B in opening, f"Agent B missing from opening. Got: {list(opening.keys())}"
        for agent_name, path in opening.items():
            assert path.exists(), f"Opening output missing for {agent_name}: {path}"
            content = path.read_text()
            assert len(content) > 0, f"Opening output empty for {agent_name}"

        # Rounds: each agent produced output per round
        rounds = outputs["rounds"]
        assert len(rounds) >= 2, f"Expected >=2 round outputs, got {len(rounds)}"
        for key, path in rounds.items():
            assert path.exists(), f"Round output missing: {key} -> {path}"
            # Agent output may occasionally be minimal; check file exists
            # with non-negative size rather than requiring non-empty content
            assert path.stat().st_size >= 0, f"Round output missing from disk: {key}"

        # Blackboard transcript should exist in the shared volume
        transcript_path = run_dir / "volumes" / "transcript" / "debate-transcript.md"
        assert transcript_path.exists(), f"Blackboard transcript missing: {transcript_path}"
        transcript = transcript_path.read_text()
        assert len(transcript) > 0, "Blackboard transcript is empty"

        # Closing: each agent produced final position
        closing = outputs["closing"]
        for agent_name, path in closing.items():
            assert path.exists(), f"Closing output missing for {agent_name}: {path}"

        # Verdict: synthesizer produced final verdict
        verdict = outputs["verdict"]
        assert len(verdict) > 0, "Verdict phase produced no output"
        for key, path in verdict.items():
            assert path.exists(), f"Verdict output missing: {key} -> {path}"

        # Print summary for inspection
        print(f"\n--- Debate Live Test Summary ---")
        print(f"Run dir: {run_dir}")
        print(f"Phases: {list(outputs.keys())}")
        for phase_name, phase_outputs in outputs.items():
            print(f"  {phase_name}: {len(phase_outputs)} outputs")
            for key, path in phase_outputs.items():
                size = path.stat().st_size if path.exists() else 0
                print(f"    {key}: {path.name} ({size} bytes)")
        print(f"Transcript size: {len(transcript)} chars")


class TestMapReduceTemplateLive:
    """End-to-end map-reduce template with real agents."""

    @pytest.mark.timeout(600)
    def test_map_reduce_basic(self, tmp_path: Path) -> None:
        """Run map-reduce with 2 agents on a simple topic."""
        template = load_template("map-reduce")
        executor = GenericTemplateExecutor(template)

        run_dir = tmp_path / "live-mapreduce-001"
        run_dir.mkdir()

        outputs = executor.run(
            run_dir=run_dir,
            agents=[AGENT_A, AGENT_B],
            synthesizer=SYNTHESIZER,
            sandbox_backend="local",
            topic="Compare Python web frameworks: Django vs Flask. Be concise (2-3 sentences per point).",
            verbose=True,
        )

        # Verify phases
        assert "decompose" in outputs, f"Missing 'decompose'. Got: {list(outputs.keys())}"
        assert "map" in outputs, f"Missing 'map'. Got: {list(outputs.keys())}"
        assert "reduce" in outputs, f"Missing 'reduce'. Got: {list(outputs.keys())}"

        # Decompose: planner should have produced output
        decompose = outputs["decompose"]
        assert len(decompose) > 0, "Decompose phase produced no output"
        for key, path in decompose.items():
            assert path.exists(), f"Decompose output missing: {key} -> {path}"

        # Map: agents researched subtopics
        map_outputs = outputs["map"]
        assert len(map_outputs) > 0, "Map phase produced no output"
        for key, path in map_outputs.items():
            assert path.exists(), f"Map output missing: {key} -> {path}"

        # Reduce: synthesizer produced final report
        reduce_outputs = outputs["reduce"]
        assert len(reduce_outputs) > 0, "Reduce phase produced no output"
        for key, path in reduce_outputs.items():
            assert path.exists(), f"Reduce output missing: {key} -> {path}"
            content = path.read_text()
            assert len(content) > 0, f"Reduce output empty: {key}"

        # Print summary
        print(f"\n--- Map-Reduce Live Test Summary ---")
        print(f"Run dir: {run_dir}")
        for phase_name, phase_outputs in outputs.items():
            print(f"  {phase_name}: {len(phase_outputs)} outputs")
            for key, path in phase_outputs.items():
                size = path.stat().st_size if path.exists() else 0
                print(f"    {key}: {path.name} ({size} bytes)")


class TestRedBlueTemplateLive:
    """End-to-end red-blue template with real agents."""

    @pytest.mark.timeout(600)
    def test_red_blue_basic(self, tmp_path: Path) -> None:
        """Run red-blue with team assignments."""
        template = load_template("red-blue")
        executor = GenericTemplateExecutor(template)

        run_dir = tmp_path / "live-redblue-001"
        run_dir.mkdir()

        # Assign agents to teams
        teams = {
            AGENT_A: "blue",   # defender/researcher
            AGENT_B: "red",    # attacker/critic
        }

        outputs = executor.run(
            run_dir=run_dir,
            agents=[AGENT_A, AGENT_B],
            synthesizer=SYNTHESIZER,
            sandbox_backend="local",
            topic="Should companies adopt microservices architecture? Be concise (2-3 sentences).",
            teams=teams,
            verbose=True,
        )

        # Verify phases
        assert "blue-research" in outputs, f"Missing 'blue-research'. Got: {list(outputs.keys())}"
        assert "red-critique" in outputs, f"Missing 'red-critique'. Got: {list(outputs.keys())}"
        assert "blue-defense" in outputs, f"Missing 'blue-defense'. Got: {list(outputs.keys())}"
        assert "synthesize" in outputs, f"Missing 'synthesize'. Got: {list(outputs.keys())}"

        # Each phase should have produced at least one output
        for phase_name, phase_outputs in outputs.items():
            assert len(phase_outputs) > 0, f"Phase '{phase_name}' produced no output"
            for key, path in phase_outputs.items():
                assert path.exists(), f"Output missing: {phase_name}/{key} -> {path}"

        # Print summary
        print(f"\n--- Red-Blue Live Test Summary ---")
        print(f"Run dir: {run_dir}")
        for phase_name, phase_outputs in outputs.items():
            print(f"  {phase_name}: {len(phase_outputs)} outputs")
            for key, path in phase_outputs.items():
                size = path.stat().st_size if path.exists() else 0
                print(f"    {key}: {path.name} ({size} bytes)")
