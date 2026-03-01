"""Adversarial strategy: GEPA-based iterative optimization with cross-agent judging."""

from __future__ import annotations

import json
import logging
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

from ivory_tower.counselors import run_counselors
from ivory_tower.models import (
    AdversarialOptimizationPhase,
    AgentResult,
    Flags,
    Manifest,
    PhaseStatus,
    ResearchPhase,
    SeedOptimizationResult,
    SynthesisPhase,
)
from ivory_tower.log import (
    SYM_OK,
    SYM_ROUND,
    SYM_SCORE,
    create_agent_progress,
    fmt_agent,
    fmt_bullet,
    fmt_duration,
    fmt_fail,
    fmt_ok,
    fmt_phase,
    fmt_score,
    phase_spinner,
)
from ivory_tower.prompts import (
    build_adversarial_synthesis_prompt,
    build_improvement_prompt,
    build_judging_prompt,
    build_research_prompt,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_counselors_output(
    output_dir: Path, agents: list[str], suffix: str = "-report.md"
) -> None:
    """Copy agent outputs from counselors slug subdirectory to expected paths.

    Searches ALL slug subdirectories (not just the most recent) for each
    agent's output file using progressively looser matching:

    1. Exact ``{agent}.md``
    2. ``report.md`` fallback (single-agent case)
    3. Substring match: any ``.md`` file whose stem contains the agent name
    4. Sole ``.md`` file in the slug dir (single-agent case)
    """
    slug_dirs = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not slug_dirs:
        return

    for agent in agents:
        dst = output_dir / f"{agent}{suffix}"
        if dst.exists():
            continue

        src: Path | None = None

        for slug_dir in slug_dirs:
            # 1. Exact match
            candidate = slug_dir / f"{agent}.md"
            if candidate.exists():
                src = candidate
                break

            # 2. report.md fallback (any number of agents)
            fallback = slug_dir / "report.md"
            if fallback.exists():
                src = fallback
                break

            # 3. Substring match: filename stem contains the agent name
            md_files = list(slug_dir.glob("*.md"))
            for md in md_files:
                if agent in md.stem:
                    src = md
                    break
            if src is not None:
                break

            # 4. Sole .md file when there's only one unmatched agent
            if len(agents) == 1 and len(md_files) == 1:
                src = md_files[0]
                break

        if src is not None:
            src = _find_best_report_file(src.parent, src)
            shutil.copy2(src, dst)
            logger.debug("Normalized %s -> %s", src, dst)
        else:
            logger.warning(
                "Could not find output for agent %s in %s", agent, output_dir
            )


def _find_best_report_file(slug_dir: Path, initial_file: Path) -> Path:
    """Pick the best report file from a counselors slug directory.

    If another .md file in *slug_dir* is substantially larger (>2x) than
    *initial_file*, assume it is the real report (agents often write their
    actual output to a separate file like ``research_report.md``).

    Files excluded from consideration: ``prompt.md``, ``summary.md``.
    """
    EXCLUDED = {"prompt.md", "summary.md"}
    try:
        initial_size = initial_file.stat().st_size
    except OSError:
        return initial_file

    best = initial_file
    best_size = initial_size

    for md in slug_dir.glob("*.md"):
        if md.name in EXCLUDED:
            continue
        if md == initial_file:
            continue
        try:
            sz = md.stat().st_size
        except OSError:
            continue
        if sz > best_size:
            best = md
            best_size = sz

    # Only switch if the better candidate is substantially larger (>2x)
    if best != initial_file and best_size > initial_size * 2:
        logger.debug(
            "Best-file heuristic: %s (%d bytes) -> %s (%d bytes)",
            initial_file.name, initial_size, best.name, best_size,
        )
        return best

    return initial_file


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _extract_json_from_markdown(text: str) -> str | None:
    """Extract JSON from markdown text, trying multiple strategies.

    Handles:
    - Format A: Clean JSON on the full text (OpenAI agents)
    - Format B: JSON in a ```json fenced code block (Anthropic agents)
    - Format C: JSON in any ``` fenced code block
    - Format D: Raw JSON object containing "overall_score" in the text
    """
    if not text or not text.strip():
        return None

    # Strategy 1: Try parsing the full text as JSON directly (Format A)
    logger.debug("Trying JSON extraction strategy 1: full text as JSON")
    stripped = text.strip()
    try:
        json.loads(stripped)
        return stripped
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 1b: Repair common JSON malformations from LLM output.
    # Some agents produce multi-paragraph critique as:
    #   "critique":"paragraph 1" ,"paragraph 2"}
    # which is invalid JSON (the second " terminates the string too early).
    # Fix by merging split string fragments:  " ," -> \\n\\n
    if stripped.startswith("{") and stripped.endswith("}"):
        repaired = re.sub(r'" ,"', r'\\n\\n', stripped)
        if repaired != stripped:
            try:
                json.loads(repaired)
                logger.debug("JSON repair succeeded (merged split string fragments)")
                return repaired
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 2: Extract from ```json fenced code blocks (Format B)
    logger.debug("Trying JSON extraction strategy 2: ```json fenced blocks")
    # Try ALL matches (last one is often the valid JSON for Anthropic agents)
    json_block_matches = re.findall(
        r'```json\s*\n?(.*?)\n?\s*```', text, re.DOTALL
    )
    for candidate in reversed(json_block_matches):
        candidate = candidate.strip()
        if candidate:
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, ValueError):
                continue

    # Strategy 3: Extract from any ``` fenced code block
    logger.debug("Trying JSON extraction strategy 3: any fenced block")
    any_block_matches = re.findall(
        r'```\s*\n?(.*?)\n?\s*```', text, re.DOTALL
    )
    for candidate in reversed(any_block_matches):
        candidate = candidate.strip()
        if candidate:
            try:
                json.loads(candidate)
                return candidate
            except (json.JSONDecodeError, ValueError):
                continue

    # Strategy 4: Find a raw JSON object containing "overall_score"
    logger.debug("Trying JSON extraction strategy 4: raw JSON with overall_score")
    # Use a greedy match from { to the last } to handle nested objects
    for match in re.finditer(r'\{[^{}]*"overall_score"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL):
        candidate = match.group(0).strip()
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            continue

    # Strategy 5: Find any raw JSON object {...} and try to parse it
    logger.debug("Trying JSON extraction strategy 5: any raw JSON object")
    for match in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL):
        candidate = match.group(0).strip()
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            continue

    logger.warning("All JSON extraction strategies failed for text of length %d", len(text))
    return None


def _extract_score_from_text(text: str) -> float | None:
    """Extract a score from natural language prose as a last-resort fallback.

    Looks for patterns like:
    - "Overall Score: 7.4/10"
    - "overall_score: 7.4"
    - "**Overall: 7/10**"
    - "Overall ... 8.5 / 10"
    """
    if not text:
        return None

    patterns = [
        # "overall_score: 7.4" or "overall_score : 7.4"
        r'overall_score\s*:\s*(\d+\.?\d*)',
        # "Overall Score: 7.4/10" or "Overall Score: 7.4 / 10"
        r'[Oo]verall\s+[Ss]core\s*:\s*(\d+\.?\d*)\s*/\s*10',
        # "**Overall: 7/10**" or "**Overall: 7.5/10**"
        r'\*\*[Oo]verall\s*:\s*(\d+\.?\d*)\s*/\s*10\s*\*\*',
        # "Overall ... 8.5/10" (more general)
        r'[Oo]verall.*?(\d+\.?\d*)\s*/\s*10',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                score = float(match.group(1))
                if 0.0 <= score <= 10.0:
                    return score
            except (ValueError, IndexError):
                continue

    return None


def parse_judge_output(judging_dir: Path) -> tuple[float, dict]:
    """Parse judge output from a counselors output directory.

    Reads agent output ``.md`` files recursively and tries multiple
    extraction strategies.  Excludes known non-output files (prompts,
    summaries) that may contain template/example JSON.

    1. JSON extraction from each file (via ``_extract_json_from_markdown``)
    2. Score extraction from natural language prose (via ``_extract_score_from_text``)
    3. Returns raw text as ``critique`` so the proposer still gets feedback

    Returns ``(score, asi_dict)``.
    """
    _EXCLUDED_NAMES = {"prompt.md", "judge-prompt.md", "summary.md"}
    md_files = [
        f for f in judging_dir.glob("**/*.md")
        if f.name not in _EXCLUDED_NAMES
    ]
    if not md_files:
        logger.warning("No .md files found in %s", judging_dir)
        return 0.0, {"error": f"No output files found in {judging_dir}"}

    # Collect all raw text for fallback
    all_texts: list[str] = []
    for md_file in md_files:
        try:
            all_texts.append(md_file.read_text())
        except OSError:
            continue

    if not all_texts:
        return 0.0, {"error": f"Could not read any files in {judging_dir}"}

    # Strategy 1: Try JSON extraction from each file
    for raw_text in all_texts:
        json_str = _extract_json_from_markdown(raw_text)
        if json_str is not None:
            try:
                data = json.loads(json_str)
                if isinstance(data, dict) and "overall_score" in data:
                    score = float(data.get("overall_score", 0.0))
                    score = max(0.0, min(10.0, score))

                    asi = {
                        "dimensions": data.get("dimensions", {}),
                        "strengths": data.get("strengths", []),
                        "weaknesses": data.get("weaknesses", []),
                        "suggestions": data.get("suggestions", []),
                        "critique": data.get("critique", ""),
                    }
                    logger.info("Judge score from %s: %.1f (JSON parsed)", judging_dir.name, score)
                    return score, asi
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("JSON decode failed for candidate from %s", judging_dir.name)
                continue

    # Strategy 2: Try extracting score from natural language prose
    logger.warning("No parseable JSON in %s, falling back to text extraction", judging_dir.name)
    combined_text = "\n\n".join(all_texts)
    prose_score = _extract_score_from_text(combined_text)
    if prose_score is not None:
        logger.info("Judge score from %s: %.1f (extracted from prose)", judging_dir.name, prose_score)
        return prose_score, {
            "dimensions": {},
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
            "critique": combined_text,
        }

    # Strategy 3: Return error but include raw text as critique for feedback
    logger.warning("Could not extract any score from %s, returning 0.0", judging_dir.name)
    return 0.0, {
        "error": "Failed to parse judge output as JSON",
        "raw_output": combined_text,
        "critique": combined_text,
    }


def extract_feedback_from_reflective_dataset(
    reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]]
) -> dict:
    """Extract feedback from GEPA's reflective_dataset format.

    GEPA stores evaluator results as ``(score, asi_dict)`` tuples.  The
    reflective_dataset maps component names to sequences of ASI dicts.
    The *score* may live in the ASI dict under ``"score"`` or
    ``"overall_score"``, or it may be absent (GEPA tracks it separately).
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
        logger.debug("[feedback] reflective_dataset is empty")
        return defaults

    logger.debug(
        "[feedback] reflective_dataset keys=%s, sizes=%s",
        list(reflective_dataset.keys()),
        {k: len(v) for k, v in reflective_dataset.items()},
    )

    for key in reflective_dataset:
        entries = reflective_dataset[key]
        if not entries:
            continue
        last_entry = entries[-1]
        logger.debug(
            "[feedback] key=%s, last_entry keys=%s, sample=%s",
            key,
            list(last_entry.keys()) if isinstance(last_entry, dict) else type(last_entry).__name__,
            str(last_entry)[:500] if last_entry else "empty",
        )

        if not isinstance(last_entry, dict):
            continue

        # Try multiple paths to find the score
        score = 0.0
        for score_key in ("score", "overall_score"):
            val = last_entry.get(score_key)
            if val is not None:
                try:
                    score = float(val)
                    break
                except (TypeError, ValueError):
                    pass

        # Check nested "dimensions" for dimension scores if top-level score missing
        dimensions = last_entry.get("dimensions", {})
        if score == 0.0 and isinstance(dimensions, dict) and dimensions:
            # Compute average of dimension scores as fallback
            dim_scores = []
            for v in dimensions.values():
                try:
                    dim_scores.append(float(v))
                except (TypeError, ValueError):
                    pass
            if dim_scores:
                score = sum(dim_scores) / len(dim_scores)
                logger.debug(
                    "[feedback] No explicit score, computed %.1f from %d dimension scores",
                    score, len(dim_scores),
                )

        return {
            "score": score,
            "dimensions": dimensions,
            "strengths": last_entry.get("strengths", []),
            "weaknesses": last_entry.get("weaknesses", []),
            "suggestions": last_entry.get("suggestions", []),
            "critique": last_entry.get("critique", ""),
        }

    logger.debug("[feedback] No usable entries found in reflective_dataset")
    return defaults


def read_counselors_output(output_dir: Path, agent: str) -> str:
    """Read agent's output text from a counselors output directory."""
    slug_dirs = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for slug_dir in slug_dirs:
        candidate: Path | None = None
        # 1. Exact match
        agent_file = slug_dir / f"{agent}.md"
        if agent_file.exists():
            candidate = agent_file
        if candidate is None:
            # 2. Substring match: any .md whose stem contains the agent name
            md_files = list(slug_dir.glob("*.md"))
            for md in md_files:
                if agent in md.stem:
                    candidate = md
                    break
        if candidate is None:
            # 3. Any .md file as last resort for this slug dir
            md_files = list(slug_dir.glob("*.md"))
            if md_files:
                candidate = md_files[0]
        if candidate is not None:
            best = _find_best_report_file(slug_dir, candidate)
            return best.read_text()

    # Fallback: files directly in output_dir
    agent_file = output_dir / f"{agent}.md"
    if agent_file.exists():
        return agent_file.read_text()
    # Substring match in output_dir
    md_files = list(output_dir.glob("*.md"))
    for md in md_files:
        if agent in md.stem:
            return md.read_text()
    if md_files:
        return md_files[0].read_text()
    raise FileNotFoundError(f"No output found for agent '{agent}' in {output_dir}")


# ---------------------------------------------------------------------------
# AdversarialStrategy
# ---------------------------------------------------------------------------


class AdversarialStrategy:
    """Adversarial optimization: 2 agents produce seed reports, then each is
    iteratively optimized via GEPA while the opposing agent judges."""

    name: str = "adversarial"
    description: str = "Adversarial optimization with cross-agent judging via GEPA"

    def validate(self, config: Any) -> list[str]:
        """Validate config for adversarial strategy."""
        errors: list[str] = []
        if len(config.agents) != 2:
            errors.append(
                f"Adversarial strategy requires exactly 2 agents, got {len(config.agents)}"
            )
        if not config.synthesizer:
            errors.append("Synthesizer agent is required.")

        # Check gepa availability
        try:
            from gepa.optimize_anything import optimize_anything  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            errors.append(
                "The adversarial strategy requires the gepa package. "
                "Install with: uv add gepa"
            )

        return errors

    def create_manifest(self, config: Any, run_id: str) -> Manifest:
        """Create initial manifest with adversarial-shaped phases."""
        agents = config.agents
        agent_a, agent_b = agents[0], agents[1]

        # Phase 1: Seed generation (same as council Phase 1)
        research_agents = {
            agent: AgentResult(
                status=PhaseStatus.PENDING,
                output=f"phase1/{agent}-seed.md",
            )
            for agent in agents
        }

        # Phase 2: Adversarial optimization
        seeds = {
            agent_a: SeedOptimizationResult(
                status=PhaseStatus.PENDING,
                judge=agent_b,
                output=f"phase2/{agent_a}-optimized.md",
                log=f"phase2/{agent_a}-optimization-log.json",
            ),
            agent_b: SeedOptimizationResult(
                status=PhaseStatus.PENDING,
                judge=agent_a,
                output=f"phase2/{agent_b}-optimized.md",
                log=f"phase2/{agent_b}-optimization-log.json",
            ),
        }

        return Manifest(
            run_id=run_id,
            topic=config.topic,
            agents=agents,
            synthesizer=config.synthesizer,
            flags=Flags(
                raw=config.raw,
                instructions=config.instructions,
                verbose=config.verbose,
                max_rounds=config.max_rounds,
            ),
            phases={
                "seed_generation": ResearchPhase(
                    status=PhaseStatus.PENDING,
                    agents=research_agents,
                ),
                "adversarial_optimization": AdversarialOptimizationPhase(
                    status=PhaseStatus.PENDING,
                    seeds=seeds,
                ),
                "synthesis": SynthesisPhase(
                    status=PhaseStatus.PENDING,
                    agent=config.synthesizer,
                    output="phase3/final-report.md",
                ),
            },
            strategy="adversarial",
        )

    def run(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Execute the full adversarial pipeline."""
        t0 = time.monotonic()

        manifest = self._run_seed_generation(run_dir, config, manifest)
        manifest = self._run_adversarial_optimization(run_dir, config, manifest)
        manifest = self._run_synthesis(run_dir, config, manifest)

        manifest.total_duration_seconds = time.monotonic() - t0

        logger.info("")
        logger.info(
            fmt_ok("Adversarial pipeline complete [duration](%s)[/duration]"),
            fmt_duration(manifest.total_duration_seconds),
        )

        manifest.save(run_dir / "manifest.json")
        return manifest

    def resume(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Resume a partially-completed adversarial run."""
        seed_done = manifest.phases["seed_generation"].status == PhaseStatus.COMPLETE
        opt_phase = manifest.phases["adversarial_optimization"]
        opt_done = opt_phase.status in (PhaseStatus.COMPLETE, PhaseStatus.PARTIAL)
        synth_done = manifest.phases["synthesis"].status == PhaseStatus.COMPLETE

        if seed_done and opt_done and synth_done:
            return manifest

        t0 = time.monotonic()

        if not seed_done:
            manifest = self._run_seed_generation(run_dir, config, manifest)

        if not opt_done:
            manifest = self._run_adversarial_optimization(run_dir, config, manifest)

        if not synth_done:
            manifest = self._run_synthesis(run_dir, config, manifest)

        manifest.total_duration_seconds = time.monotonic() - t0
        manifest.save(run_dir / "manifest.json")
        return manifest

    def dry_run(self, config: Any) -> None:
        """Print adversarial execution plan."""
        agents = config.agents
        n = len(agents)

        print("=== Dry Run: Adversarial Execution Plan ===")
        print()
        print(f"Strategy: adversarial")
        print(f"Topic: {config.topic}")
        print()
        print(f"Agents ({n}): {', '.join(agents)}")
        print(f"Synthesizer: {config.synthesizer}")
        print(f"Max Rounds: {config.max_rounds}")
        print()
        print("Phases:")
        print(f"  1. Seed Generation: {n} agents research independently")
        if n == 2:
            print(f"  2. Adversarial Optimization ({config.max_rounds} rounds per seed):")
            print(f"       {agents[0]}'s seed judged by {agents[1]}")
            print(f"       {agents[1]}'s seed judged by {agents[0]}")
        print(f"  3. Synthesis: {config.synthesizer} merges both optimized reports")

    def format_status(self, manifest: Manifest) -> list[tuple[str, str]]:
        """Return status tuples for each adversarial phase."""
        result = [
            ("Seed generation", manifest.phases["seed_generation"].status.value),
        ]
        opt = manifest.phases["adversarial_optimization"]
        opt_label = opt.status.value
        if hasattr(opt, "seeds") and opt.seeds:
            summaries = []
            for agent, seed in opt.seeds.items():
                s = f"{agent}: {seed.rounds_completed}r"
                if seed.final_score is not None:
                    s += f" ({seed.final_score:.1f})"
                summaries.append(s)
            opt_label += f" [{'; '.join(summaries)}]"
        result.append(("Adversarial optimization", opt_label))
        result.append(("Synthesis", manifest.phases["synthesis"].status.value))
        return result

    def phases_to_dict(self, phases: dict) -> dict:
        """Serialize adversarial phases to dict."""
        # Seed generation (ResearchPhase)
        sg = phases["seed_generation"]
        sg_dict = {
            "status": sg.status.value,
            "started_at": sg.started_at,
            "completed_at": sg.completed_at,
            "duration_seconds": sg.duration_seconds,
            "agents": {
                name: {
                    "status": ar.status.value,
                    "duration_seconds": ar.duration_seconds,
                    "output": ar.output,
                }
                for name, ar in sg.agents.items()
            },
        }

        # Adversarial optimization
        opt = phases["adversarial_optimization"]
        opt_dict = {
            "status": opt.status.value,
            "started_at": opt.started_at,
            "completed_at": opt.completed_at,
            "duration_seconds": opt.duration_seconds,
            "seeds": {
                name: {
                    "status": s.status.value,
                    "judge": s.judge,
                    "rounds_completed": s.rounds_completed,
                    "seed_score": s.seed_score,
                    "final_score": s.final_score,
                    "output": s.output,
                    "log": s.log,
                }
                for name, s in opt.seeds.items()
            },
        }

        # Synthesis
        sp = phases["synthesis"]
        sp_dict = {
            "status": sp.status.value,
            "started_at": sp.started_at,
            "completed_at": sp.completed_at,
            "duration_seconds": sp.duration_seconds,
            "agent": sp.agent,
            "output": sp.output,
        }

        return {
            "seed_generation": sg_dict,
            "adversarial_optimization": opt_dict,
            "synthesis": sp_dict,
        }

    def phases_from_dict(self, data: dict) -> dict:
        """Deserialize adversarial phases from dict."""
        # Seed generation
        sg_d = data["seed_generation"]
        seed_gen = ResearchPhase(
            status=PhaseStatus(sg_d["status"]),
            started_at=sg_d.get("started_at"),
            completed_at=sg_d.get("completed_at"),
            duration_seconds=sg_d.get("duration_seconds"),
            agents={
                name: AgentResult(
                    status=PhaseStatus(ar["status"]),
                    duration_seconds=ar.get("duration_seconds"),
                    output=ar["output"],
                )
                for name, ar in sg_d.get("agents", {}).items()
            },
        )

        # Adversarial optimization
        opt_d = data["adversarial_optimization"]
        opt = AdversarialOptimizationPhase(
            status=PhaseStatus(opt_d["status"]),
            started_at=opt_d.get("started_at"),
            completed_at=opt_d.get("completed_at"),
            duration_seconds=opt_d.get("duration_seconds"),
            seeds={
                name: SeedOptimizationResult(
                    status=PhaseStatus(s["status"]),
                    judge=s["judge"],
                    rounds_completed=s.get("rounds_completed", 0),
                    seed_score=s.get("seed_score"),
                    final_score=s.get("final_score"),
                    output=s.get("output", ""),
                    log=s.get("log", ""),
                )
                for name, s in opt_d.get("seeds", {}).items()
            },
        )

        # Synthesis
        sp_d = data["synthesis"]
        synthesis = SynthesisPhase(
            status=PhaseStatus(sp_d["status"]),
            agent=sp_d["agent"],
            output=sp_d["output"],
            started_at=sp_d.get("started_at"),
            completed_at=sp_d.get("completed_at"),
            duration_seconds=sp_d.get("duration_seconds"),
        )

        return {
            "seed_generation": seed_gen,
            "adversarial_optimization": opt,
            "synthesis": synthesis,
        }

    # -- Private phase execution --

    def _run_seed_generation(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Phase 1: Both agents independently research the topic."""
        logger.info(fmt_phase("Phase 1 -- Seed Generation"))
        agents_str = ", ".join(fmt_agent(a) for a in config.agents)
        logger.info(fmt_bullet("Agents: %s"), agents_str)
        sg: ResearchPhase = manifest.phases["seed_generation"]
        sg.status = PhaseStatus.RUNNING
        sg.started_at = _now_iso()

        prompt_text = build_research_prompt(
            config.topic, instructions=config.instructions, raw=config.raw
        )
        prompt_file = run_dir / "research-prompt.md"
        prompt_file.write_text(prompt_text)

        phase1_dir = run_dir / "phase1"
        phase1_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.monotonic()
        agents_label = ", ".join(config.agents)
        with phase_spinner(f"Agents researching: [agent]{agents_label}[/agent]"):
            run_counselors(
                prompt_file=prompt_file,
                agents=config.agents,
                output_dir=phase1_dir,
                verbose=config.verbose,
            )

        # Normalize: <slug>/<agent>.md -> <agent>-seed.md
        _normalize_counselors_output(phase1_dir, config.agents, suffix="-seed.md")

        elapsed = time.monotonic() - t0
        sg.status = PhaseStatus.COMPLETE
        sg.completed_at = _now_iso()
        sg.duration_seconds = elapsed

        for agent in config.agents:
            sg.agents[agent] = AgentResult(
                status=PhaseStatus.COMPLETE,
                duration_seconds=elapsed,
                output=f"phase1/{agent}-seed.md",
            )

        logger.info(
            fmt_ok("Phase 1 complete [duration](%s)[/duration]"),
            fmt_duration(elapsed),
        )
        manifest.save(run_dir / "manifest.json")
        return manifest

    def _run_adversarial_optimization(
        self, run_dir: Path, config: Any, manifest: Manifest
    ) -> Manifest:
        """Phase 2: Optimize each seed via GEPA with cross-agent judging."""
        try:
            from gepa.optimize_anything import (
                optimize_anything,
                GEPAConfig,
                EngineConfig,
                ReflectionConfig,
            )
        except ImportError:
            raise RuntimeError(
                "The adversarial strategy requires the gepa package. "
                "Install with: uv add gepa"
            )

        opt: AdversarialOptimizationPhase = manifest.phases["adversarial_optimization"]
        opt.status = PhaseStatus.RUNNING
        opt.started_at = _now_iso()

        phase1_dir = run_dir / "phase1"
        phase2_dir = run_dir / "phase2"
        phase2_dir.mkdir(parents=True, exist_ok=True)
        judging_dir = phase2_dir / "judging"
        judging_dir.mkdir(parents=True, exist_ok=True)

        agents = config.agents
        agent_a, agent_b = agents[0], agents[1]
        max_rounds = config.max_rounds

        logger.info("")
        logger.info(fmt_phase("Phase 2 -- Adversarial Optimization"))
        logger.info(fmt_bullet("Agent A: %s  |  Agent B: %s"), fmt_agent(agents[0]), fmt_agent(agents[1]))
        logger.info(fmt_bullet("Max rounds: %d"), max_rounds)

        t0 = time.monotonic()

        def optimize_seed(agent: str, judge: str) -> None:
            """Optimize one agent's seed report."""
            logger.info("Starting optimization for %s (judge: %s, max_rounds: %d)", agent, judge, max_rounds)
            seed_file = phase1_dir / f"{agent}-seed.md"
            seed_text = seed_file.read_text()

            seed_result = opt.seeds[agent]
            seed_result.status = PhaseStatus.RUNNING

            round_counter = [0]

            def evaluator(candidate: dict) -> tuple[float, dict]:
                """Send candidate to opposing agent for judging."""
                round_num = round_counter[0] + 1
                round_counter[0] = round_num

                report_text = candidate.get("report", "")
                logger.debug(
                    "[%s] evaluator round %d: candidate report length=%d, first 200 chars: %s",
                    agent, round_num, len(report_text), report_text[:200],
                )

                # Write judging prompt
                judge_prompt = build_judging_prompt(config.topic, report_text)
                round_dir = judging_dir / f"round-{round_num:02d}-{judge}-judges-{agent}"
                round_dir.mkdir(parents=True, exist_ok=True)

                prompt_file = round_dir / "judge-prompt.md"
                prompt_file.write_text(judge_prompt)

                # Run judge
                with phase_spinner(f"{fmt_agent(judge)} judging {fmt_agent(agent)} (round {round_num})"):
                    run_counselors(
                        prompt_file=prompt_file,
                        agents=[judge],
                        output_dir=round_dir,
                        verbose=config.verbose,
                    )

                # Parse output
                score, asi = parse_judge_output(round_dir)

                # Save judge output as readable file
                judge_md = judging_dir / f"round-{round_num:02d}-{judge}-judges-{agent}.md"
                judge_text = None
                try:
                    judge_text = read_counselors_output(round_dir, judge)
                    judge_md.write_text(judge_text)
                except FileNotFoundError:
                    pass

                # If ASI has an error key (JSON parsing failed), ensure the
                # raw judge prose is stuffed into critique so the proposer
                # still gets natural-language feedback (Fix 3).
                if "error" in asi and not asi.get("critique"):
                    if judge_text:
                        asi["critique"] = judge_text
                    else:
                        # Try reading all md files as fallback
                        md_files = list(round_dir.glob("**/*.md"))
                        texts = []
                        for f in md_files:
                            try:
                                texts.append(f.read_text())
                            except OSError:
                                pass
                        if texts:
                            asi["critique"] = "\n\n".join(texts)

                # Track seed score on first round
                if round_num == 1:
                    seed_result.seed_score = score

                seed_result.rounds_completed = round_num

                logger.info(
                    fmt_bullet("%s Round %d  %s [score]%s[/score]"),
                    SYM_ROUND, round_num, fmt_agent(agent), fmt_score(score),
                )
                if score == 0.0:
                    logger.warning("[%s] Round %d returned score 0.0 -- judge output may have failed to parse", agent, round_num)

                return score, asi

            def proposer(
                candidate: dict,
                reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
                components_to_update: list[str],
            ) -> dict[str, str]:
                """Send feedback to original agent to produce improved report."""
                logger.info(
                    fmt_bullet("%s %s proposer called (round %d)"),
                    SYM_ROUND, fmt_agent(agent), seed_result.rounds_completed + 1,
                )
                logger.debug(
                    "[%s] proposer: reflective_dataset keys=%s, candidate report length=%d",
                    agent,
                    list(reflective_dataset.keys()) if isinstance(reflective_dataset, dict) else type(reflective_dataset).__name__,
                    len(candidate.get("report", "")),
                )
                # Primary path: read judge output directly from disk.
                # GEPA's reflective_dataset is unreliable -- it may contain
                # template/example values from the judging prompt rather than
                # the evaluator's actual ASI dict.  Disk files are the
                # ground truth written by parse_judge_output() in evaluator().
                feedback: dict | None = None
                judge_round_dirs = sorted(
                    judging_dir.glob(f"round-*-{judge}-judges-{agent}"),
                    key=lambda d: d.name,
                    reverse=True,
                )
                if judge_round_dirs:
                    disk_score, disk_asi = parse_judge_output(judge_round_dirs[0])
                    if disk_score > 0.0 or disk_asi.get("critique"):
                        feedback = {
                            "score": disk_score,
                            "dimensions": disk_asi.get("dimensions", {}),
                            "strengths": disk_asi.get("strengths", []),
                            "weaknesses": disk_asi.get("weaknesses", []),
                            "suggestions": disk_asi.get("suggestions", []),
                            "critique": disk_asi.get("critique", ""),
                        }
                        logger.info(
                            "[%s] Read judge feedback from disk: score=%.1f (round dir: %s)",
                            agent, disk_score, judge_round_dirs[0].name,
                        )

                # Fallback: try GEPA's reflective_dataset if disk read failed
                if feedback is None:
                    logger.info(
                        "[%s] No judge output on disk, falling back to reflective_dataset",
                        agent,
                    )
                    feedback = extract_feedback_from_reflective_dataset(
                        reflective_dataset if isinstance(reflective_dataset, dict) else {}
                    )

                logger.info(
                    fmt_bullet("  Feedback: [score]%s[/score]  strengths=%d  weaknesses=%d"),
                    fmt_score(feedback.get("score", 0.0)),
                    len(feedback.get("strengths", [])),
                    len(feedback.get("weaknesses", [])),
                )

                improvement_prompt = build_improvement_prompt(
                    topic=config.topic,
                    current_report=candidate.get("report", ""),
                    judge_feedback=feedback,
                    round_num=seed_result.rounds_completed + 1,
                )

                improve_dir = phase2_dir / f"{agent}-improve-round-{seed_result.rounds_completed + 1:02d}"
                improve_dir.mkdir(parents=True, exist_ok=True)

                prompt_file = improve_dir / "improve-prompt.md"
                prompt_file.write_text(improvement_prompt)

                # Write debug info for this round
                debug_file = improve_dir / "round-debug.json"
                try:
                    debug_file.write_text(json.dumps({
                        "agent": agent,
                        "round": seed_result.rounds_completed + 1,
                        "feedback_score": feedback.get("score", 0.0),
                        "feedback_dimensions": feedback.get("dimensions", {}),
                        "feedback_strengths": feedback.get("strengths", []),
                        "feedback_weaknesses": feedback.get("weaknesses", []),
                        "candidate_report_length": len(candidate.get("report", "")),
                    }, indent=2))
                except Exception:
                    logger.debug("[%s] Failed to write round debug file", agent, exc_info=True)

                with phase_spinner(f"{fmt_agent(agent)} improving report (round {seed_result.rounds_completed + 1})"):
                    run_counselors(
                        prompt_file=prompt_file,
                        agents=[agent],
                        output_dir=improve_dir,
                        verbose=config.verbose,
                    )

                try:
                    improved_text = read_counselors_output(improve_dir, agent)
                except FileNotFoundError:
                    improved_text = candidate.get("report", "")

                return {"report": improved_text}

            # No-op LM stub: GEPA defaults reflection_lm to "openai/gpt-5.1"
            # (a string), which triggers ``make_litellm_lm()`` ->
            # ``import litellm`` even when a custom_candidate_proposer fully
            # replaces the LLM reflection path.  Passing a callable skips the
            # string->LM conversion entirely, avoiding the litellm dependency.
            def _unused_lm(prompt):  # pragma: no cover
                raise RuntimeError("reflection_lm should never be called when custom_candidate_proposer is set")

            gepa_config = GEPAConfig(
                engine=EngineConfig(
                    # +1 because GEPA uses one metric call to evaluate the
                    # seed before any improvement rounds begin.
                    max_metric_calls=max_rounds + 1,
                    raise_on_exception=False,
                ),
                reflection=ReflectionConfig(
                    custom_candidate_proposer=proposer,
                    reflection_lm=_unused_lm,
                ),
            )

            try:
                with phase_spinner(f"Optimizing {fmt_agent(agent)}..."):
                    result = optimize_anything(
                        seed_candidate={"report": seed_text},
                        evaluator=evaluator,
                        objective=(
                            "Optimize this research report for accuracy, depth, "
                            "coverage, source quality, and analytical rigor"
                        ),
                        config=gepa_config,
                    )

                # Save optimized report
                best = result.best_candidate
                if isinstance(best, dict):
                    optimized_text = best.get("report", seed_text)
                elif isinstance(best, str):
                    optimized_text = best
                else:
                    optimized_text = seed_text
                optimized_file = phase2_dir / f"{agent}-optimized.md"
                optimized_file.write_text(optimized_text)

                # Extract best score from val_aggregate_scores
                best_score = result.val_aggregate_scores[result.best_idx] if result.val_aggregate_scores else None
                seed_result.final_score = best_score
                seed_result.status = PhaseStatus.COMPLETE

                # Save optimization log
                seed_score = seed_result.seed_score or 0.0
                final_score = best_score if best_score is not None else 0.0
                logger.info(
                    fmt_ok("%s optimization done: [score]%s[/score] -> [score]%s[/score]"),
                    fmt_agent(agent),
                    fmt_score(seed_score),
                    fmt_score(final_score),
                )
                self._save_optimization_log(run_dir, agent, result)
                logger.info("Optimization complete for %s: best_score=%s, rounds=%s",
                            agent, best_score, getattr(result, "total_metric_calls", "?"))

                # Fix 6: Warn when optimization produced no improvement
                if best_score is not None and seed_result.seed_score is not None:
                    if best_score == seed_result.seed_score == 0.0:
                        logger.warning(
                            "[%s] Optimization ended with seed_score=0.0 and final_score=0.0 -- "
                            "judge output likely failed to parse in all rounds", agent
                        )

            except Exception:
                # Graceful degradation: fall back to seed
                logger.error("Optimization failed for %s, falling back to seed", agent, exc_info=True)
                seed_result.status = PhaseStatus.PARTIAL
                optimized_file = phase2_dir / f"{agent}-optimized.md"
                if not optimized_file.exists():
                    shutil.copy2(seed_file, optimized_file)

        # Run both optimizations concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(optimize_seed, agent_a, agent_b)
            future_b = executor.submit(optimize_seed, agent_b, agent_a)

            errors = []
            for future in as_completed([future_a, future_b]):
                try:
                    future.result()
                except Exception as e:
                    errors.append(e)

        elapsed = time.monotonic() - t0

        # Determine overall phase status
        all_complete = all(
            s.status == PhaseStatus.COMPLETE for s in opt.seeds.values()
        )
        any_failed = any(
            s.status in (PhaseStatus.FAILED, PhaseStatus.PARTIAL) for s in opt.seeds.values()
        )

        if all_complete:
            opt.status = PhaseStatus.COMPLETE
        elif any_failed:
            opt.status = PhaseStatus.PARTIAL
        else:
            opt.status = PhaseStatus.COMPLETE

        opt.completed_at = _now_iso()
        opt.duration_seconds = elapsed

        manifest.save(run_dir / "manifest.json")
        return manifest

    def _run_synthesis(self, run_dir: Path, config: Any, manifest: Manifest) -> Manifest:
        """Phase 3: Synthesize both optimized reports."""
        logger.info("")
        logger.info(fmt_phase("Phase 3 -- Synthesis"))
        logger.info(
            fmt_bullet("Synthesizer: %s combining optimized reports"),
            fmt_agent(config.synthesizer),
        )
        sp: SynthesisPhase = manifest.phases["synthesis"]
        sp.status = PhaseStatus.RUNNING
        sp.started_at = _now_iso()

        phase2_dir = run_dir / "phase2"
        phase3_dir = run_dir / "phase3"
        phase3_dir.mkdir(parents=True, exist_ok=True)

        agents = config.agents
        agent_a, agent_b = agents[0], agents[1]
        opt = manifest.phases["adversarial_optimization"]

        # Read optimized reports (fall back to seeds if needed)
        def _read_report(agent: str) -> str:
            optimized = phase2_dir / f"{agent}-optimized.md"
            if optimized.exists():
                return optimized.read_text()
            seed = run_dir / "phase1" / f"{agent}-seed.md"
            if seed.exists():
                return seed.read_text()
            return f"(no report available for {agent})"

        report_a = _read_report(agent_a)
        report_b = _read_report(agent_b)

        score_a = opt.seeds[agent_a].final_score or opt.seeds[agent_a].seed_score
        score_b = opt.seeds[agent_b].final_score or opt.seeds[agent_b].seed_score

        # Fix 8: If scores are 0.0 (likely parse failure), pass None so the
        # synthesis prompt can omit misleading "scored 0.0/10" text.
        if score_a == 0.0:
            logger.warning("Agent %s has score 0.0 -- likely a judge parse failure, omitting from synthesis prompt", agent_a)
            score_a = None
        if score_b == 0.0:
            logger.warning("Agent %s has score 0.0 -- likely a judge parse failure, omitting from synthesis prompt", agent_b)
            score_b = None

        prompt_text = build_adversarial_synthesis_prompt(
            topic=config.topic,
            agent_a=agent_a,
            optimized_report_a=report_a,
            score_a=score_a,
            agent_b=agent_b,
            optimized_report_b=report_b,
            score_b=score_b,
            total_rounds=config.max_rounds,
        )

        prompt_file = phase3_dir / "synthesis-prompt.md"
        prompt_file.write_text(prompt_text)

        t0 = time.monotonic()
        with phase_spinner(f"Synthesizer [agent]{config.synthesizer}[/agent] working..."):
            run_counselors(
                prompt_file=prompt_file,
                agents=[config.synthesizer],
                output_dir=phase3_dir,
                verbose=config.verbose,
            )

        _normalize_counselors_output(phase3_dir, [config.synthesizer], suffix=".md")
        synth_out = phase3_dir / f"{config.synthesizer}.md"
        final_report = phase3_dir / "final-report.md"
        if synth_out.exists() and not final_report.exists():
            shutil.copy2(synth_out, final_report)

        elapsed = time.monotonic() - t0
        sp.status = PhaseStatus.COMPLETE
        sp.completed_at = _now_iso()
        sp.duration_seconds = elapsed

        logger.info(
            fmt_ok("Phase 3 complete [duration](%s)[/duration]"),
            fmt_duration(elapsed),
        )
        manifest.save(run_dir / "manifest.json")
        return manifest

    def _save_optimization_log(self, run_dir: Path, agent: str, result: Any) -> None:
        """Save optimization log JSON for one agent.

        Works with real GEPAResult (val_aggregate_scores, candidates, best_idx)
        and with mock results that may use different attribute names.
        """
        phase2_dir = run_dir / "phase2"

        # Extract scores -- real GEPAResult uses val_aggregate_scores
        scores = getattr(result, "val_aggregate_scores", None) or []
        score_history = [
            {"round": i + 1, "score": s}
            for i, s in enumerate(scores)
        ]

        seed_score = scores[0] if scores else 0.0
        best_idx = getattr(result, "best_idx", len(scores) - 1 if scores else 0)
        final_score = scores[best_idx] if scores and best_idx < len(scores) else 0.0
        total_calls = getattr(result, "total_metric_calls", len(scores)) or len(scores)

        log_data = {
            "agent": agent,
            "judge": "",  # filled later from manifest
            "seed_score": seed_score,
            "final_score": final_score,
            "rounds": total_calls,
            "score_history": score_history,
            "best_round": best_idx + 1,
            "improvement": f"+{final_score - seed_score:.1f} ({seed_score:.1f} -> {final_score:.1f})",
        }

        log_file = phase2_dir / f"{agent}-optimization-log.json"
        log_file.write_text(json.dumps(log_data, indent=2))
