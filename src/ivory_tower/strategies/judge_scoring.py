from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

DIMENSION_KEYS = (
    "factual_accuracy",
    "depth_of_analysis",
    "source_quality",
    "coverage_breadth",
    "analytical_rigor",
)

GRADE_TO_SCORE = {
    "A": 9.5,
    "A-": 9.0,
    "B+": 8.5,
    "B": 8.0,
    "B-": 7.5,
    "C+": 7.0,
    "C": 6.5,
    "C-": 6.0,
    "D": 5.0,
    "F": 3.0,
}


def _clamp_score(value: float) -> float:
    return max(0.0, min(10.0, value))


def _normalize_grade(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    grade = value.strip().upper().replace(" ", "")
    if grade in GRADE_TO_SCORE:
        return grade
    return None


def _score_to_grade(score: float) -> str:
    score = _clamp_score(score)
    # Deterministic nearest-neighbor mapping.
    return min(GRADE_TO_SCORE.items(), key=lambda kv: abs(kv[1] - score))[0]


def normalize_judge_evaluation(data: Mapping[str, Any]) -> tuple[float, dict[str, Any]] | None:
    """Normalize evaluator payload into deterministic score + ASI.

    Accepts old numeric format (overall_score/dimensions) and new grade format
    (dimension_grades/overall_grade). When grades are present, grade-derived
    dimension scores take precedence over numeric dimensions.
    """
    if not isinstance(data, Mapping):
        return None

    dimension_grades_raw = data.get("dimension_grades", {})
    parsed_grades: dict[str, str] = {}
    if isinstance(dimension_grades_raw, Mapping):
        for key in DIMENSION_KEYS:
            grade = _normalize_grade(dimension_grades_raw.get(key))
            if grade is not None:
                parsed_grades[key] = grade

    dimensions_raw = data.get("dimensions", {})
    parsed_dimensions: dict[str, float] = {}
    if isinstance(dimensions_raw, Mapping):
        for key in DIMENSION_KEYS:
            val = dimensions_raw.get(key)
            if isinstance(val, (int, float)):
                parsed_dimensions[key] = _clamp_score(float(val))

    # Prefer deterministic grade mapping when available.
    for key, grade in parsed_grades.items():
        parsed_dimensions[key] = GRADE_TO_SCORE[grade]

    score: float | None = None
    overall_score = data.get("overall_score")
    if parsed_grades:
        # Stable mode: score is deterministically computed from letter grades.
        score = sum(parsed_dimensions.values()) / len(parsed_dimensions)
    elif isinstance(overall_score, (int, float)):
        # Backward compatibility for legacy numeric-only judge outputs.
        score = float(overall_score)
    elif parsed_dimensions:
        # Fallback when only dimensions are provided.
        score = sum(parsed_dimensions.values()) / len(parsed_dimensions)

    if score is None:
        return None
    score = _clamp_score(score)

    # Ensure every numeric dimension has a corresponding grade label.
    derived_grades = dict(parsed_grades)
    for key, val in parsed_dimensions.items():
        if key not in derived_grades:
            derived_grades[key] = _score_to_grade(val)

    overall_grade = _normalize_grade(data.get("overall_grade"))
    if overall_grade is None:
        overall_grade = _score_to_grade(score)

    strengths = data.get("strengths", [])
    weaknesses = data.get("weaknesses", [])
    suggestions = data.get("suggestions", [])

    asi = {
        "dimensions": parsed_dimensions,
        "dimension_grades": derived_grades,
        "overall_grade": overall_grade,
        "strengths": strengths if isinstance(strengths, list) else [],
        "weaknesses": weaknesses if isinstance(weaknesses, list) else [],
        "suggestions": suggestions if isinstance(suggestions, list) else [],
        "critique": data.get("critique", ""),
    }
    return score, asi
