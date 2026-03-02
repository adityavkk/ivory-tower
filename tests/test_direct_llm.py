"""Tests for the direct LLM evaluator and proposer (strategies/direct_llm.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ivory_tower.strategies.direct_llm import (
    _llm_completion,
    _parse_evaluation_json,
    make_direct_evaluator,
    make_direct_proposer,
)


# ---------------------------------------------------------------------------
# _parse_evaluation_json tests
# ---------------------------------------------------------------------------


class TestParseEvaluationJson:
    """Test JSON extraction from LLM evaluation responses."""

    def test_json_on_last_line(self):
        text = (
            "Here is my evaluation.\n\n"
            '{"overall_score": 7.5, "dimensions": {"factual_accuracy": 8}}'
        )
        result = _parse_evaluation_json(text)
        assert result is not None
        assert result["overall_score"] == 7.5
        assert result["dimensions"]["factual_accuracy"] == 8

    def test_json_in_fenced_block(self):
        text = (
            "Analysis goes here.\n\n"
            "```json\n"
            '{"overall_score": 6.0, "dimensions": {"depth": 7}}\n'
            "```"
        )
        result = _parse_evaluation_json(text)
        assert result is not None
        assert result["overall_score"] == 6.0

    def test_raw_json_with_overall_score(self):
        text = (
            "Some text before. "
            '{"overall_score": 8.2, "dimensions": {"factual_accuracy": 9}} '
            "some text after."
        )
        result = _parse_evaluation_json(text)
        assert result is not None
        assert result["overall_score"] == 8.2

    def test_empty_text_returns_none(self):
        assert _parse_evaluation_json("") is None
        assert _parse_evaluation_json("   ") is None
        assert _parse_evaluation_json("no json here") is None

    def test_json_without_overall_score_ignored(self):
        text = '{"some_key": "value"}'
        assert _parse_evaluation_json(text) is None

    def test_multiple_json_blocks_picks_one_with_overall_score(self):
        text = (
            "```json\n"
            '{"irrelevant": true}\n'
            "```\n\n"
            "```json\n"
            '{"overall_score": 5.5, "dimensions": {}}\n'
            "```"
        )
        result = _parse_evaluation_json(text)
        assert result is not None
        assert result["overall_score"] == 5.5

    def test_multiline_json_in_fenced_block(self):
        text = (
            "```json\n"
            "{\n"
            '  "overall_score": 7.0,\n'
            '  "dimensions": {\n'
            '    "factual_accuracy": 7,\n'
            '    "depth_of_analysis": 8\n'
            "  },\n"
            '  "strengths": ["good"],\n'
            '  "weaknesses": ["bad"]\n'
            "}\n"
            "```"
        )
        result = _parse_evaluation_json(text)
        assert result is not None
        assert result["overall_score"] == 7.0
        assert result["dimensions"]["depth_of_analysis"] == 8


# ---------------------------------------------------------------------------
# _llm_completion tests
# ---------------------------------------------------------------------------


class TestLlmCompletion:
    """Test the litellm wrapper function."""

    @patch("litellm.completion")
    def test_basic_call(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_completion.return_value = mock_response

        result = _llm_completion("openai/test-model", "Say hi")
        assert result == "Hello!"
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args
        assert call_kwargs.kwargs["model"] == "openai/test-model"

    @patch("litellm.completion")
    def test_with_api_base(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hi"
        mock_completion.return_value = mock_response

        _llm_completion(
            "openai/test", "hello",
            api_base="http://localhost:8112/v1",
        )
        call_kwargs = mock_completion.call_args
        assert call_kwargs.kwargs["api_base"] == "http://localhost:8112/v1"
        assert call_kwargs.kwargs["api_key"] == "not-needed"

    @patch("litellm.completion")
    def test_empty_response(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_completion.return_value = mock_response

        result = _llm_completion("openai/test", "hello")
        assert result == ""


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeSeedResult:
    seed_score: float | None = None
    final_score: float | None = None
    rounds_completed: int = 0
    status: str = "running"
    dimension_history: list = field(default_factory=list)


GOOD_EVAL_JSON = json.dumps({
    "overall_score": 7.5,
    "dimensions": {
        "factual_accuracy": 8,
        "depth_of_analysis": 7,
        "source_quality": 7,
        "coverage_breadth": 8,
        "analytical_rigor": 7,
    },
    "strengths": ["Good coverage", "Well structured"],
    "weaknesses": ["Limited sources"],
    "suggestions": ["Add more primary sources"],
    "critique": "Solid report with room for improvement.",
})


# ---------------------------------------------------------------------------
# make_direct_evaluator tests
# ---------------------------------------------------------------------------


class TestMakeDirectEvaluator:
    """Test the GEPA evaluator factory."""

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_evaluator_returns_score_and_asi(self, mock_completion, tmp_path):
        mock_completion.return_value = (
            "Here is my evaluation.\n\n" + GOOD_EVAL_JSON
        )

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        seed_result = FakeSeedResult()

        evaluator = make_direct_evaluator(
            agent="agent-a",
            judge="agent-b",
            model="openai/test",
            api_base=None,
            topic="test topic",
            judging_dir=judging_dir,
            round_counter=[0],
            seed_result=seed_result,
            build_judging_prompt=lambda topic, report: f"Judge: {topic}\n{report}",
        )

        score, asi = evaluator({"report": "test report content"})

        assert score == 7.5
        assert asi["dimensions"]["factual_accuracy"] == 8
        assert "Good coverage" in asi["strengths"]
        assert asi["scores"]["factual_accuracy"] == 8.0
        assert seed_result.seed_score == 7.5
        assert seed_result.rounds_completed == 1
        assert len(seed_result.dimension_history) == 1

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_evaluator_handles_parse_failure(self, mock_completion, tmp_path):
        mock_completion.return_value = "I cannot evaluate this. No JSON here."

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        seed_result = FakeSeedResult()

        evaluator = make_direct_evaluator(
            agent="agent-a",
            judge="agent-b",
            model="openai/test",
            api_base=None,
            topic="test topic",
            judging_dir=judging_dir,
            round_counter=[0],
            seed_result=seed_result,
            build_judging_prompt=lambda topic, report: f"Judge: {topic}",
        )

        score, asi = evaluator({"report": "test"})
        assert score == 0.0
        assert "error" in asi
        assert "critique" in asi

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_evaluator_persists_files(self, mock_completion, tmp_path):
        mock_completion.return_value = GOOD_EVAL_JSON

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        seed_result = FakeSeedResult()

        evaluator = make_direct_evaluator(
            agent="agent-a",
            judge="agent-b",
            model="openai/test",
            api_base=None,
            topic="test topic",
            judging_dir=judging_dir,
            round_counter=[0],
            seed_result=seed_result,
            build_judging_prompt=lambda topic, report: f"Judge: {topic}",
        )

        evaluator({"report": "test"})

        # Check files were written
        round_dir = judging_dir / "round-01-agent-b-judges-agent-a"
        assert round_dir.exists()
        assert (round_dir / "judge-prompt.md").exists()
        assert (round_dir / "round-debug.json").exists()

        # Check judge summary md
        judge_md = judging_dir / "round-01-agent-b-judges-agent-a.md"
        assert judge_md.exists()

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_evaluator_clamps_score(self, mock_completion, tmp_path):
        """Score should be clamped to 0-10."""
        mock_completion.return_value = json.dumps({
            "overall_score": 15.0,
            "dimensions": {},
        })

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        seed_result = FakeSeedResult()

        evaluator = make_direct_evaluator(
            agent="agent-a", judge="agent-b",
            model="openai/test", api_base=None,
            topic="test", judging_dir=judging_dir,
            round_counter=[0], seed_result=seed_result,
            build_judging_prompt=lambda t, r: "judge",
        )

        score, _ = evaluator({"report": "test"})
        assert score == 10.0

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_evaluator_increments_round_counter(self, mock_completion, tmp_path):
        mock_completion.return_value = GOOD_EVAL_JSON

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        seed_result = FakeSeedResult()
        round_counter = [0]

        evaluator = make_direct_evaluator(
            agent="agent-a", judge="agent-b",
            model="openai/test", api_base=None,
            topic="test", judging_dir=judging_dir,
            round_counter=round_counter, seed_result=seed_result,
            build_judging_prompt=lambda t, r: "judge",
        )

        evaluator({"report": "r1"})
        evaluator({"report": "r2"})

        assert round_counter[0] == 2
        assert seed_result.rounds_completed == 2
        assert len(seed_result.dimension_history) == 2


# ---------------------------------------------------------------------------
# make_direct_proposer tests
# ---------------------------------------------------------------------------


class TestMakeDirectProposer:
    """Test the GEPA proposer factory."""

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_proposer_returns_improved_report(self, mock_completion, tmp_path):
        mock_completion.return_value = "# Improved Report\n\nBetter content."

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        phase2_dir = tmp_path / "phase2"
        phase2_dir.mkdir()
        seed_result = FakeSeedResult(rounds_completed=1)
        feedback_history: list[dict] = []

        # Write a judge output so proposer can read feedback
        round_dir = judging_dir / "round-01-agent-b-judges-agent-a"
        round_dir.mkdir(parents=True)
        (round_dir / "round-debug.json").write_text(json.dumps({
            "agent": "agent-a",
            "judge": "agent-b",
            "round": 1,
            "score": 7.0,
            "dimensions": {"factual_accuracy": 7},
        }))

        proposer = make_direct_proposer(
            agent="agent-a",
            judge="agent-b",
            model="openai/test",
            api_base=None,
            topic="test topic",
            judging_dir=judging_dir,
            phase2_dir=phase2_dir,
            seed_result=seed_result,
            feedback_history=feedback_history,
            config=MagicMock(),
            build_judging_prompt=lambda t, r: "judge",
            build_improvement_prompt=lambda **kw: f"Improve: {kw['topic']}",
        )

        result = proposer(
            {"report": "original report"},
            {},
            ["report"],
        )

        assert "report" in result
        assert "Improved Report" in result["report"]
        assert len(feedback_history) == 1

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_proposer_persists_files(self, mock_completion, tmp_path):
        mock_completion.return_value = "improved text"

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        phase2_dir = tmp_path / "phase2"
        phase2_dir.mkdir()
        seed_result = FakeSeedResult(rounds_completed=1)

        # Write a round debug file
        round_dir = judging_dir / "round-01-agent-b-judges-agent-a"
        round_dir.mkdir(parents=True)
        (round_dir / "round-debug.json").write_text(json.dumps({
            "score": 6.5, "dimensions": {},
        }))

        proposer = make_direct_proposer(
            agent="agent-a",
            judge="agent-b",
            model="openai/test",
            api_base=None,
            topic="test",
            judging_dir=judging_dir,
            phase2_dir=phase2_dir,
            seed_result=seed_result,
            feedback_history=[],
            config=MagicMock(),
            build_judging_prompt=lambda t, r: "judge",
            build_improvement_prompt=lambda **kw: "improve",
        )

        proposer({"report": "orig"}, {}, ["report"])

        improve_dir = phase2_dir / "agent-a-improve-round-02"
        assert improve_dir.exists()
        assert (improve_dir / "improve-prompt.md").exists()
        assert (improve_dir / "round-debug.json").exists()
        assert (improve_dir / "agent-a-improved.md").exists()

    @patch("ivory_tower.strategies.direct_llm._llm_completion")
    def test_proposer_reads_judge_md_fallback(self, mock_completion, tmp_path):
        """When round-debug.json has score=0, proposer falls back to judge .md."""
        mock_completion.return_value = "improved"

        judging_dir = tmp_path / "judging"
        judging_dir.mkdir()
        phase2_dir = tmp_path / "phase2"
        phase2_dir.mkdir()
        seed_result = FakeSeedResult(rounds_completed=1)

        # Write round dir with 0 score debug
        round_dir = judging_dir / "round-01-agent-b-judges-agent-a"
        round_dir.mkdir(parents=True)
        (round_dir / "round-debug.json").write_text(json.dumps({
            "score": 0.0, "dimensions": {},
        }))

        # Write judge md file with valid evaluation
        judge_md = judging_dir / "round-01-agent-b-judges-agent-a.md"
        judge_md.write_text(GOOD_EVAL_JSON)

        feedback_history: list[dict] = []
        proposer = make_direct_proposer(
            agent="agent-a",
            judge="agent-b",
            model="openai/test",
            api_base=None,
            topic="test",
            judging_dir=judging_dir,
            phase2_dir=phase2_dir,
            seed_result=seed_result,
            feedback_history=feedback_history,
            config=MagicMock(),
            build_judging_prompt=lambda t, r: "judge",
            build_improvement_prompt=lambda **kw: "improve",
        )

        proposer({"report": "orig"}, {}, ["report"])

        # Feedback should have been read from the judge md
        assert len(feedback_history) == 1
        assert feedback_history[0]["score"] == 7.5
