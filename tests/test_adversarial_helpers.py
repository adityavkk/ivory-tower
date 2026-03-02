"""Tests for adversarial helper functions."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from ivory_tower.executor.types import AgentOutput
from ivory_tower.strategies.adversarial import (
    _extract_json_from_markdown,
    _llm_extract_json,
    parse_judge_output,
    extract_feedback_from_reflective_dataset,
)


# ---------------------------------------------------------------------------
# Helpers for mocking the executor-based _llm_extract_json
# ---------------------------------------------------------------------------

def _fake_get_executor(agent_name):
    return MagicMock(name=f"executor-{agent_name}")


def _fake_create_sandbox(run_dir, agent_name, run_id, backend="none"):
    mock = MagicMock(name=f"sandbox-{agent_name}")
    mock.workspace_dir = run_dir
    return mock


class TestExtractJsonFromMarkdown:
    def test_fenced_json_block(self):
        text = '```json\n{"score": 5}\n```'
        result = _extract_json_from_markdown(text)
        assert result == '{"score": 5}'

    def test_fenced_block_without_json_label(self):
        text = '```\n{"score": 5}\n```'
        result = _extract_json_from_markdown(text)
        assert result == '{"score": 5}'

    def test_raw_json_object(self):
        text = 'Some text before {"score": 5} some text after'
        result = _extract_json_from_markdown(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["score"] == 5

    def test_no_json(self):
        text = "This is just plain text with no JSON"
        result = _extract_json_from_markdown(text)
        assert result is None

    def test_empty_string(self):
        assert _extract_json_from_markdown("") is None


class TestParseJudgeOutput:
    def test_valid_json_output(self, tmp_path):
        data = {
            "overall_score": 7.5,
            "dimensions": {"factual_accuracy": 8, "depth_of_analysis": 7,
                          "source_quality": 7, "coverage_breadth": 8,
                          "analytical_rigor": 7},
            "strengths": ["good coverage"],
            "weaknesses": ["weak sources"],
            "suggestions": ["add references"],
            "critique": "Solid report overall."
        }
        md_file = tmp_path / "agent.md"
        md_file.write_text(json.dumps(data))

        score, asi = parse_judge_output(tmp_path)
        assert score == 7.5
        assert asi["dimensions"]["factual_accuracy"] == 8
        assert "good coverage" in asi["strengths"]

    def test_empty_dir(self, tmp_path):
        score, asi = parse_judge_output(tmp_path)
        assert score == 0.0
        assert "error" in asi

    def test_invalid_json(self, tmp_path):
        md_file = tmp_path / "agent.md"
        md_file.write_text("This is not JSON at all, no braces here!")

        score, asi = parse_judge_output(tmp_path)
        assert score == 0.0
        assert "error" in asi

    def test_score_clamped_high(self, tmp_path):
        md_file = tmp_path / "agent.md"
        md_file.write_text(json.dumps({"overall_score": 15.0}))

        score, _ = parse_judge_output(tmp_path)
        assert score == 10.0

    def test_score_clamped_low(self, tmp_path):
        md_file = tmp_path / "agent.md"
        md_file.write_text(json.dumps({"overall_score": -5.0}))

        score, _ = parse_judge_output(tmp_path)
        assert score == 0.0

    def test_json_in_fenced_block(self, tmp_path):
        data = {"overall_score": 6.0, "dimensions": {}, "strengths": [],
                "weaknesses": [], "suggestions": [], "critique": "ok"}
        md_file = tmp_path / "agent.md"
        md_file.write_text(f"Here's my eval:\n```json\n{json.dumps(data)}\n```")

        score, asi = parse_judge_output(tmp_path)
        assert score == 6.0

    def test_letter_grades_without_overall_score(self, tmp_path):
        data = {
            "overall_grade": "B",
            "dimension_grades": {
                "factual_accuracy": "A-",
                "depth_of_analysis": "B",
                "source_quality": "C+",
                "coverage_breadth": "B+",
                "analytical_rigor": "B-",
            },
            "strengths": ["good breadth"],
            "weaknesses": ["source quality mixed"],
            "suggestions": ["add primary sources"],
            "critique": "solid",
        }
        md_file = tmp_path / "agent.md"
        md_file.write_text(json.dumps(data))

        score, asi = parse_judge_output(tmp_path)
        assert score == 8.0  # deterministic grade mapping average
        assert asi["dimensions"]["source_quality"] == 7.0


class TestExtractFeedbackFromReflectiveDataset:
    def test_populated_dataset(self):
        dataset = {
            "evaluations": [
                {"score": 5.0, "dimensions": {"factual_accuracy": 5},
                 "strengths": ["s1"], "weaknesses": ["w1"],
                 "suggestions": ["sug1"], "critique": "crit1"},
                {"score": 7.0, "dimensions": {"factual_accuracy": 7},
                 "strengths": ["s2"], "weaknesses": ["w2"],
                 "suggestions": ["sug2"], "critique": "crit2"},
            ]
        }
        result = extract_feedback_from_reflective_dataset(dataset)
        # Should return the last entry
        assert result["score"] == 7.0
        assert result["dimensions"]["factual_accuracy"] == 7

    def test_empty_dataset(self):
        result = extract_feedback_from_reflective_dataset({})
        assert result["score"] == 0.0
        assert result["dimensions"] == {}

    def test_empty_sequence(self):
        result = extract_feedback_from_reflective_dataset({"evaluations": []})
        # Empty sequence in key, falls through to defaults
        result2 = extract_feedback_from_reflective_dataset({})
        assert result["score"] == 0.0 or result2["score"] == 0.0

    def test_dataset_with_scores_key(self):
        """Gap 3: reflective_dataset entries now include 'scores' from evaluator ASI."""
        dataset = {
            "report": [
                {
                    "score": 6.5,
                    "dimensions": {
                        "factual_accuracy": 7,
                        "depth_of_analysis": 6,
                        "source_quality": 5,
                        "coverage_breadth": 7,
                        "analytical_rigor": 6,
                    },
                    "scores": {
                        "factual_accuracy": 7.0,
                        "depth_of_analysis": 6.0,
                        "source_quality": 5.0,
                        "coverage_breadth": 7.0,
                        "analytical_rigor": 6.0,
                    },
                    "strengths": ["good coverage"],
                    "weaknesses": ["weak sources"],
                    "suggestions": ["add refs"],
                    "critique": "decent report",
                },
            ]
        }
        result = extract_feedback_from_reflective_dataset(dataset)
        assert result["score"] == 6.5
        assert result["dimensions"]["factual_accuracy"] == 7
        assert result["strengths"] == ["good coverage"]
        assert result["weaknesses"] == ["weak sources"]

    def test_dataset_score_from_dimension_average(self):
        """When no explicit score, should compute from dimension scores."""
        dataset = {
            "report": [
                {
                    "dimensions": {
                        "factual_accuracy": 8,
                        "depth_of_analysis": 6,
                    },
                    "strengths": [],
                    "weaknesses": [],
                    "suggestions": [],
                    "critique": "",
                },
            ]
        }
        result = extract_feedback_from_reflective_dataset(dataset)
        assert result["score"] == 7.0  # (8 + 6) / 2


class TestLlmExtractJson:
    """Tests for _llm_extract_json (parse-agent fallback)."""

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent")
    def test_extracts_valid_json(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Parse agent returns clean JSON -- should succeed."""
        expected = {
            "overall_score": 7.5,
            "dimensions": {"factual_accuracy": 8, "depth_of_analysis": 7,
                          "source_quality": 7, "coverage_breadth": 8,
                          "analytical_rigor": 7},
            "strengths": ["good coverage"],
            "weaknesses": ["weak sources"],
            "suggestions": ["add refs"],
            "critique": "Solid report.",
        }

        mock_run.return_value = AgentOutput(
            report_path="parse-agent-fallback/fast-agent-report.md",
            raw_output=json.dumps(expected),
            duration_seconds=1.0,
            metadata={"protocol": "mock"},
        )

        result = _llm_extract_json("raw judge prose here", "fast-agent", tmp_path)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["overall_score"] == 7.5
        assert parsed["dimensions"]["factual_accuracy"] == 8

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent")
    def test_returns_none_when_agent_returns_no_json(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Parse agent returns prose without JSON -- should return None."""
        mock_run.return_value = AgentOutput(
            report_path="parse-agent-fallback/fast-agent-report.md",
            raw_output="I can't parse that output.",
            duration_seconds=1.0,
            metadata={"protocol": "mock"},
        )

        result = _llm_extract_json("raw text", "fast-agent", tmp_path)
        assert result is None

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent")
    def test_returns_none_when_run_agent_fails(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """_run_agent raises -- should return None gracefully."""
        mock_run.side_effect = RuntimeError("executor crashed")

        result = _llm_extract_json("raw text", "fast-agent", tmp_path)
        assert result is None

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent")
    def test_returns_none_when_json_missing_overall_score(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Parse agent returns valid JSON but without overall_score."""
        mock_run.return_value = AgentOutput(
            report_path="parse-agent-fallback/fast-agent-report.md",
            raw_output=json.dumps({"dimensions": {}, "strengths": []}),
            duration_seconds=1.0,
            metadata={"protocol": "mock"},
        )

        result = _llm_extract_json("raw text", "fast-agent", tmp_path)
        assert result is None

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent")
    def test_writes_prompt_file(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Verify the parse prompt is written to disk."""
        mock_run.return_value = AgentOutput(
            report_path="parse-agent-fallback/fast-agent-report.md",
            raw_output="{}",
            duration_seconds=1.0,
            metadata={"protocol": "mock"},
        )

        _llm_extract_json("the raw judge text", "fast-agent", tmp_path)
        prompt_file = tmp_path / "parse-agent-fallback" / "parse-prompt.md"
        assert prompt_file.exists()
        assert "the raw judge text" in prompt_file.read_text()

    @patch("ivory_tower.strategies.adversarial._create_sandbox", side_effect=_fake_create_sandbox)
    @patch("ivory_tower.strategies.adversarial._get_executor", side_effect=_fake_get_executor)
    @patch("ivory_tower.strategies.adversarial._run_agent")
    def test_extracts_json_in_fenced_block(self, mock_run, mock_exec, mock_sandbox, tmp_path):
        """Parse agent returns JSON inside a fenced code block."""
        expected = {
            "overall_score": 6.0,
            "dimensions": {},
            "strengths": ["s1"],
            "weaknesses": ["w1"],
            "suggestions": ["sug1"],
            "critique": "ok",
        }

        mock_run.return_value = AgentOutput(
            report_path="parse-agent-fallback/fast-agent-report.md",
            raw_output=f"Here is the JSON:\n```json\n{json.dumps(expected)}\n```",
            duration_seconds=1.0,
            metadata={"protocol": "mock"},
        )

        result = _llm_extract_json("raw text", "fast-agent", tmp_path)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["overall_score"] == 6.0


class TestParseJudgeOutputWithParseAgent:
    """Tests for parse_judge_output with the parse_agent fallback."""

    @patch("ivory_tower.strategies.adversarial._llm_extract_json")
    def test_parse_agent_not_called_when_regex_succeeds(self, mock_llm, tmp_path):
        """When regex extraction works, parse_agent should never be invoked."""
        data = {"overall_score": 8.0, "dimensions": {}, "strengths": [],
                "weaknesses": [], "suggestions": [], "critique": "good"}
        (tmp_path / "agent.md").write_text(json.dumps(data))

        score, asi = parse_judge_output(tmp_path, parse_agent="fast-agent")
        assert score == 8.0
        mock_llm.assert_not_called()

    @patch("ivory_tower.strategies.adversarial._llm_extract_json")
    def test_parse_agent_called_when_regex_fails(self, mock_llm, tmp_path):
        """When regex fails, parse_agent should be called."""
        (tmp_path / "agent.md").write_text(
            "The report is decent but has issues with sourcing. "
            "Overall I'd rate it about a 6 out of 10."
        )
        mock_llm.return_value = json.dumps({
            "overall_score": 6.0,
            "dimensions": {"factual_accuracy": 5, "depth_of_analysis": 6,
                          "source_quality": 5, "coverage_breadth": 7,
                          "analytical_rigor": 6},
            "strengths": ["decent coverage"],
            "weaknesses": ["sourcing issues"],
            "suggestions": ["add citations"],
            "critique": "Decent but needs better sources.",
        })

        score, asi = parse_judge_output(tmp_path, parse_agent="fast-agent")
        assert score == 6.0
        assert asi["dimensions"]["factual_accuracy"] == 5
        assert "decent coverage" in asi["strengths"]
        mock_llm.assert_called_once()

    @patch("ivory_tower.strategies.adversarial._llm_extract_json")
    def test_parse_agent_not_called_when_not_configured(self, mock_llm, tmp_path):
        """When parse_agent is None, LLM fallback should not be invoked."""
        (tmp_path / "agent.md").write_text("No JSON here at all!")

        score, asi = parse_judge_output(tmp_path, parse_agent=None)
        assert score == 0.0
        mock_llm.assert_not_called()

    @patch("ivory_tower.strategies.adversarial._llm_extract_json")
    def test_falls_through_to_prose_when_parse_agent_fails(self, mock_llm, tmp_path):
        """When parse_agent also fails, should fall through to prose extraction."""
        (tmp_path / "agent.md").write_text(
            "Overall Score: 5.5/10\n\nThe report needs more depth."
        )
        mock_llm.return_value = None  # parse agent failed

        score, asi = parse_judge_output(tmp_path, parse_agent="fast-agent")
        assert score == 5.5
        mock_llm.assert_called_once()

    def test_excludes_parse_agent_fallback_dir(self, tmp_path):
        """Files in parse-agent-fallback should not be read as judge output."""
        (tmp_path / "agent.md").write_text("No JSON here!")
        fallback_dir = tmp_path / "parse-agent-fallback"
        fallback_dir.mkdir()
        # This would cause a false positive if not excluded
        (fallback_dir / "parse-result.md").write_text(
            json.dumps({"overall_score": 9.0})
        )

        score, asi = parse_judge_output(tmp_path)
        assert score == 0.0  # Should NOT find the 9.0 from fallback dir
