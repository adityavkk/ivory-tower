from __future__ import annotations

from ivory_tower.strategies.judge_scoring import normalize_judge_evaluation


class TestNormalizeJudgeEvaluation:
    def test_uses_overall_score_for_legacy_numeric_payload(self):
        payload = {
            "overall_score": 7.5,
            "dimensions": {
                "factual_accuracy": 8,
                "depth_of_analysis": 7,
                "source_quality": 7,
                "coverage_breadth": 8,
                "analytical_rigor": 7,
            },
            "strengths": ["clear structure"],
            "weaknesses": ["limited sources"],
            "suggestions": ["add primary citations"],
            "critique": "decent",
        }

        normalized = normalize_judge_evaluation(payload)
        assert normalized is not None
        score, asi = normalized
        assert score == 7.5
        assert asi["dimensions"]["factual_accuracy"] == 8.0

    def test_computes_deterministic_score_from_dimension_grades(self):
        payload = {
            "overall_grade": "B-",
            "dimension_grades": {
                "factual_accuracy": "A-",
                "depth_of_analysis": "B",
                "source_quality": "C+",
                "coverage_breadth": "B+",
                "analytical_rigor": "B-",
            },
            "strengths": ["broad coverage"],
            "weaknesses": ["sources are mixed"],
            "suggestions": ["add stronger primary sources"],
            "critique": "good overall",
        }

        normalized = normalize_judge_evaluation(payload)
        assert normalized is not None
        score, asi = normalized
        # (9.0 + 8.0 + 7.0 + 8.5 + 7.5) / 5 = 8.0
        assert score == 8.0
        assert asi["dimensions"]["source_quality"] == 7.0
        assert asi["dimension_grades"]["coverage_breadth"] == "B+"

    def test_grade_based_score_overrides_conflicting_overall_score(self):
        payload = {
            "overall_score": 9.9,
            "dimension_grades": {
                "factual_accuracy": "C",
                "depth_of_analysis": "C",
                "source_quality": "C",
                "coverage_breadth": "C",
                "analytical_rigor": "C",
            },
        }

        normalized = normalize_judge_evaluation(payload)
        assert normalized is not None
        score, _ = normalized
        assert score == 6.5

    def test_returns_none_when_no_score_signal(self):
        assert normalize_judge_evaluation({"strengths": ["x"]}) is None
