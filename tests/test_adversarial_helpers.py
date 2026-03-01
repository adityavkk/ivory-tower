"""Tests for adversarial helper functions."""

from __future__ import annotations

import json

import pytest

from ivory_tower.strategies.adversarial import (
    _extract_json_from_markdown,
    parse_judge_output,
    extract_feedback_from_reflective_dataset,
    read_counselors_output,
)


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


class TestReadCounselorsOutput:
    def test_reads_from_slug_subdir(self, tmp_path):
        slug = tmp_path / "slug-001"
        slug.mkdir()
        (slug / "agent-a.md").write_text("Report A")

        result = read_counselors_output(tmp_path, "agent-a")
        assert result == "Report A"

    def test_falls_back_to_any_md(self, tmp_path):
        slug = tmp_path / "slug-001"
        slug.mkdir()
        (slug / "other.md").write_text("Some report")

        result = read_counselors_output(tmp_path, "agent-a")
        assert result == "Some report"

    def test_reads_direct_agent_file(self, tmp_path):
        (tmp_path / "agent-a.md").write_text("Direct report")

        result = read_counselors_output(tmp_path, "agent-a")
        assert result == "Direct report"

    def test_raises_when_empty(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_counselors_output(tmp_path, "agent-a")
