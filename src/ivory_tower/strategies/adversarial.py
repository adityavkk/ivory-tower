"""Adversarial strategy: GEPA-based iterative optimization with cross-agent judging."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


def _extract_json_from_markdown(text: str) -> str | None:
    """Extract JSON from a markdown-fenced code block or raw JSON object.
    
    Tries ```json ``` block first, then raw {...} object, then None.
    """
    # Try fenced json block
    match = re.search(r'```(?:json)?\s*\n(.*?)\n\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Try raw JSON object
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        return match.group(0).strip()
    
    return None


def parse_judge_output(judging_dir: Path) -> tuple[float, dict]:
    """Parse judge output from a counselors output directory.
    
    Returns (score, asi_dict) where asi has keys: dimensions, strengths, 
    weaknesses, suggestions, critique.
    
    Edge cases:
    - Empty dir: (0.0, {"error": ...})
    - Invalid JSON: (0.0, {"error": ..., "raw_output": ...})
    - Score clamped to [0, 10]
    """
    # Find the output file
    md_files = list(judging_dir.glob("**/*.md"))
    if not md_files:
        return 0.0, {"error": f"No output files found in {judging_dir}"}
    
    # Read the most recent one
    raw_text = md_files[0].read_text()
    
    # Extract JSON
    json_str = _extract_json_from_markdown(raw_text)
    if json_str is None:
        # Try the raw text itself
        json_str = raw_text.strip()
    
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return 0.0, {"error": "Failed to parse judge output as JSON", "raw_output": raw_text}
    
    score = float(data.get("overall_score", 0.0))
    score = max(0.0, min(10.0, score))  # clamp
    
    asi = {
        "dimensions": data.get("dimensions", {}),
        "strengths": data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "suggestions": data.get("suggestions", []),
        "critique": data.get("critique", ""),
    }
    
    return score, asi


def extract_feedback_from_reflective_dataset(
    reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]]
) -> dict:
    """Extract feedback from GEPA's reflective_dataset format.
    
    Returns dict with keys: score, dimensions, strengths, weaknesses, 
    suggestions, critique.
    
    Empty dataset: returns zero/empty defaults.
    Reads most recent entry (last in sequence).
    """
    defaults = {
        "score": 0.0,
        "dimensions": {},
        "strengths": [],
        "weaknesses": [],
        "suggestions": [],
        "critique": "",
    }
    
    if not reflective_dataset:
        return defaults
    
    # Get the first key's sequence and take the last entry
    for key in reflective_dataset:
        entries = reflective_dataset[key]
        if entries:
            last_entry = entries[-1]
            return {
                "score": float(last_entry.get("score", last_entry.get("overall_score", 0.0))),
                "dimensions": last_entry.get("dimensions", {}),
                "strengths": last_entry.get("strengths", []),
                "weaknesses": last_entry.get("weaknesses", []),
                "suggestions": last_entry.get("suggestions", []),
                "critique": last_entry.get("critique", ""),
            }
    
    return defaults


def read_counselors_output(output_dir: Path, agent: str) -> str:
    """Read agent's output text from a counselors output directory.
    
    Checks <slug_dir>/<agent>.md first, falls back to any .md file.
    Raises FileNotFoundError if nothing found.
    """
    # Check for slug subdirectories first
    slug_dirs = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    
    for slug_dir in slug_dirs:
        agent_file = slug_dir / f"{agent}.md"
        if agent_file.exists():
            return agent_file.read_text()
        
        # Fall back to any .md file in slug dir
        md_files = list(slug_dir.glob("*.md"))
        if md_files:
            return md_files[0].read_text()
    
    # Check output_dir directly
    agent_file = output_dir / f"{agent}.md"
    if agent_file.exists():
        return agent_file.read_text()
    
    md_files = list(output_dir.glob("*.md"))
    if md_files:
        return md_files[0].read_text()
    
    raise FileNotFoundError(f"No output found for agent '{agent}' in {output_dir}")
