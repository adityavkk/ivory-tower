"""Direct LLM evaluator and proposer for GEPA adversarial optimization.

Replaces the counselors-based agent dispatch with direct litellm API calls,
enabling faster iteration and eliminating agent output parsing failures.
The evaluator calls the LLM with the judging prompt and parses the JSON
response directly.  The proposer calls the LLM with the improvement prompt
and returns the raw text as the improved report.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


def _llm_completion(
    model: str,
    prompt: str,
    *,
    api_base: str | None = None,
    api_key: str = "not-needed",
    max_tokens: int = 16384,
    temperature: float = 0.3,
) -> str:
    """Call litellm.completion and return the response text."""
    import litellm

    messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if api_base:
        kwargs["api_base"] = api_base
        kwargs["api_key"] = api_key

    response = litellm.completion(**kwargs)
    return response.choices[0].message.content or ""


def _parse_evaluation_json(text: str) -> dict[str, Any] | None:
    """Extract evaluation JSON from LLM response.

    Tries multiple strategies mirroring adversarial._extract_json_from_markdown.
    """
    import re

    if not text or not text.strip():
        return None

    # Strategy 1: Last line is JSON (the prompt asks for JSON on final line)
    lines = text.strip().splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if "overall_score" in obj:
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 2: ```json fenced block
    json_blocks = re.findall(r'```json\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    for block in reversed(json_blocks):
        block = block.strip()
        try:
            obj = json.loads(block)
            if "overall_score" in obj:
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    # Strategy 3: Any raw JSON with overall_score
    for match in re.finditer(
        r'\{[^{}]*"overall_score"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        text,
        re.DOTALL,
    ):
        try:
            obj = json.loads(match.group(0))
            if "overall_score" in obj:
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    return None


def make_direct_evaluator(
    *,
    agent: str,
    judge: str,
    model: str,
    api_base: str | None,
    topic: str,
    judging_dir: Path,
    round_counter: list[int],
    seed_result: Any,
    build_judging_prompt: Any,
) -> Any:
    """Build a GEPA evaluator closure that calls the LLM directly.

    Returns a callable matching GEPA's evaluator signature:
        (candidate: dict) -> tuple[float, dict]
    """
    from ivory_tower.log import (
        SYM_ROUND,
        fmt_agent,
        fmt_score,
        fmt_bullet,
        phase_spinner,
    )

    def evaluator(candidate: dict) -> tuple[float, dict]:
        round_num = round_counter[0] + 1
        round_counter[0] = round_num

        report_text = candidate.get("report", "")
        logger.debug(
            "[%s] direct evaluator round %d: report length=%d",
            agent, round_num, len(report_text),
        )

        judge_prompt = build_judging_prompt(topic, report_text)

        # Persist prompt for debugging
        round_dir = judging_dir / f"round-{round_num:02d}-{judge}-judges-{agent}"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "judge-prompt.md").write_text(judge_prompt)

        # Call LLM directly
        with phase_spinner(f"[direct] {fmt_agent(judge)} judging {fmt_agent(agent)} (round {round_num})"):
            start = time.monotonic()
            response_text = _llm_completion(
                model=model,
                prompt=judge_prompt,
                api_base=api_base,
            )
            elapsed = time.monotonic() - start

        # Persist raw response
        judge_md = judging_dir / f"round-{round_num:02d}-{judge}-judges-{agent}.md"
        judge_md.write_text(response_text)

        # Parse JSON evaluation
        evaluation = _parse_evaluation_json(response_text)

        if evaluation:
            score = float(evaluation.get("overall_score", 0.0))
            score = max(0.0, min(10.0, score))
            asi: dict[str, Any] = {
                "dimensions": evaluation.get("dimensions", {}),
                "strengths": evaluation.get("strengths", []),
                "weaknesses": evaluation.get("weaknesses", []),
                "suggestions": evaluation.get("suggestions", []),
                "critique": evaluation.get("critique", ""),
            }
        else:
            logger.warning(
                "[%s] Round %d: failed to parse evaluation JSON from direct LLM response",
                agent, round_num,
            )
            score = 0.0
            asi = {
                "error": "JSON parse failed",
                "critique": response_text,
                "dimensions": {},
                "strengths": [],
                "weaknesses": [],
                "suggestions": [],
            }

        # Inject scores for GEPA Pareto tracking
        dimensions = asi.get("dimensions", {})
        if dimensions and isinstance(dimensions, dict):
            asi["scores"] = {
                k: float(v) for k, v in dimensions.items()
                if isinstance(v, (int, float))
            }
        else:
            asi["scores"] = {}

        # Track seed score on first round
        if round_num == 1:
            seed_result.seed_score = score

        seed_result.rounds_completed = round_num

        # Record per-round dimension scores
        seed_result.dimension_history.append({
            "round": round_num,
            "score": score,
            "dimensions": dict(dimensions) if dimensions else {},
        })

        # Persist round debug info
        try:
            (round_dir / "round-debug.json").write_text(json.dumps({
                "agent": agent,
                "judge": judge,
                "round": round_num,
                "score": score,
                "dimensions": dict(dimensions) if dimensions else {},
                "duration_seconds": elapsed,
                "response_length": len(response_text),
                "parse_success": evaluation is not None,
            }, indent=2))
        except Exception:
            logger.debug("[%s] Failed to write round debug", agent, exc_info=True)

        logger.info(
            fmt_bullet("%s Round %d  %s [score]%s[/score]  (%.1fs)"),
            SYM_ROUND, round_num, fmt_agent(agent), fmt_score(score), elapsed,
        )
        if score == 0.0:
            logger.warning(
                "[%s] Round %d returned score 0.0 -- JSON parse may have failed",
                agent, round_num,
            )

        return score, asi

    return evaluator


def make_direct_proposer(
    *,
    agent: str,
    judge: str,
    model: str,
    api_base: str | None,
    topic: str,
    judging_dir: Path,
    phase2_dir: Path,
    seed_result: Any,
    feedback_history: list[dict],
    config: Any,
    build_judging_prompt: Any,
    build_improvement_prompt: Any,
    parse_evaluation_json: Any = None,
) -> Any:
    """Build a GEPA proposer closure that calls the LLM directly.

    Returns a callable matching GEPA's ProposalFn signature:
        (candidate, reflective_dataset, components_to_update) -> dict[str, str]
    """
    from ivory_tower.log import (
        SYM_ROUND,
        fmt_agent,
        fmt_score,
        fmt_bullet,
        phase_spinner,
    )

    _parse_json = parse_evaluation_json or _parse_evaluation_json

    def proposer(
        candidate: dict,
        reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        logger.info(
            fmt_bullet("%s %s proposer called (round %d)"),
            SYM_ROUND, fmt_agent(agent), seed_result.rounds_completed + 1,
        )

        # Read latest judge feedback from disk (ground truth)
        feedback: dict | None = None
        judge_round_dirs = sorted(
            (
                d for d in judging_dir.glob(f"round-*-{judge}-judges-{agent}")
                if d.is_dir()
            ),
            key=lambda d: d.name,
            reverse=True,
        )
        if judge_round_dirs:
            debug_file = judge_round_dirs[0] / "round-debug.json"
            if debug_file.exists():
                try:
                    debug_data = json.loads(debug_file.read_text())
                    if debug_data.get("score", 0.0) > 0.0:
                        feedback = {
                            "score": debug_data["score"],
                            "dimensions": debug_data.get("dimensions", {}),
                        }
                except (json.JSONDecodeError, KeyError):
                    pass

            # Also try reading the judge .md file for full feedback
            if feedback is None:
                judge_md = judging_dir / f"{judge_round_dirs[0].name}.md"
                if judge_md.exists():
                    response_text = judge_md.read_text()
                    evaluation = _parse_json(response_text)
                    if evaluation:
                        feedback = {
                            "score": float(evaluation.get("overall_score", 0.0)),
                            "dimensions": evaluation.get("dimensions", {}),
                            "strengths": evaluation.get("strengths", []),
                            "weaknesses": evaluation.get("weaknesses", []),
                            "suggestions": evaluation.get("suggestions", []),
                            "critique": evaluation.get("critique", ""),
                        }

        if feedback is None:
            feedback = {"score": 0.0, "dimensions": {}}
            logger.warning("[%s] No feedback found for proposer", agent)

        logger.info(
            fmt_bullet("  Feedback: [score]%s[/score]  strengths=%d  weaknesses=%d"),
            fmt_score(feedback.get("score", 0.0)),
            len(feedback.get("strengths", [])),
            len(feedback.get("weaknesses", [])),
        )

        improvement_prompt = build_improvement_prompt(
            topic=topic,
            current_report=candidate.get("report", ""),
            judge_feedback=feedback,
            round_num=seed_result.rounds_completed + 1,
            feedback_history=feedback_history if feedback_history else None,
        )

        # Append to history for trajectory tracking
        feedback_history.append({
            "round": seed_result.rounds_completed,
            "score": feedback.get("score", 0.0),
            "dimensions": feedback.get("dimensions", {}),
        })

        improve_round = seed_result.rounds_completed + 1
        improve_dir = phase2_dir / f"{agent}-improve-round-{improve_round:02d}"
        improve_dir.mkdir(parents=True, exist_ok=True)
        (improve_dir / "improve-prompt.md").write_text(improvement_prompt)

        # Write debug info
        try:
            (improve_dir / "round-debug.json").write_text(json.dumps({
                "agent": agent,
                "round": improve_round,
                "feedback_score": feedback.get("score", 0.0),
                "feedback_dimensions": feedback.get("dimensions", {}),
                "feedback_strengths": feedback.get("strengths", []),
                "feedback_weaknesses": feedback.get("weaknesses", []),
                "candidate_report_length": len(candidate.get("report", "")),
            }, indent=2))
        except Exception:
            logger.debug("[%s] Failed to write round debug", agent, exc_info=True)

        # Call LLM directly for improvement
        with phase_spinner(f"[direct] {fmt_agent(agent)} improving (round {improve_round})"):
            start = time.monotonic()
            improved_text = _llm_completion(
                model=model,
                prompt=improvement_prompt,
                api_base=api_base,
                max_tokens=16384,
                temperature=0.4,
            )
            elapsed = time.monotonic() - start

        # Persist improved report
        (improve_dir / f"{agent}-improved.md").write_text(improved_text)

        logger.info(
            fmt_bullet("  Improved report: %d chars (%.1fs)"),
            len(improved_text), elapsed,
        )

        return {"report": improved_text}

    return proposer
