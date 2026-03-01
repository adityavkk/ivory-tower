"""Adversarial strategy: GEPA-based iterative optimization with cross-agent judging."""

from __future__ import annotations

import json
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

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

    Some agents (e.g. OpenCode) write to ``report.md`` instead of
    ``{agent}.md``.  When there is exactly one agent and the expected
    file is missing, fall back to ``report.md``.
    """
    slug_dirs = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not slug_dirs:
        return
    slug_dir = slug_dirs[0]
    for agent in agents:
        src = slug_dir / f"{agent}.md"
        dst = output_dir / f"{agent}{suffix}"
        if not src.exists() and len(agents) == 1:
            fallback = slug_dir / "report.md"
            if fallback.exists():
                src = fallback
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _extract_json_from_markdown(text: str) -> str | None:
    """Extract JSON from a markdown-fenced code block or raw JSON object."""
    match = re.search(r'```(?:json)?\s*\n(.*?)\n\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return None


def parse_judge_output(judging_dir: Path) -> tuple[float, dict]:
    """Parse judge output from a counselors output directory.

    Returns (score, asi_dict).
    """
    md_files = list(judging_dir.glob("**/*.md"))
    if not md_files:
        return 0.0, {"error": f"No output files found in {judging_dir}"}

    raw_text = md_files[0].read_text()
    json_str = _extract_json_from_markdown(raw_text)
    if json_str is None:
        json_str = raw_text.strip()

    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return 0.0, {"error": "Failed to parse judge output as JSON", "raw_output": raw_text}

    score = float(data.get("overall_score", 0.0))
    score = max(0.0, min(10.0, score))

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
    """Extract feedback from GEPA's reflective_dataset format."""
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
    """Read agent's output text from a counselors output directory."""
    slug_dirs = sorted(
        (d for d in output_dir.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for slug_dir in slug_dirs:
        agent_file = slug_dir / f"{agent}.md"
        if agent_file.exists():
            return agent_file.read_text()
        md_files = list(slug_dir.glob("*.md"))
        if md_files:
            return md_files[0].read_text()

    agent_file = output_dir / f"{agent}.md"
    if agent_file.exists():
        return agent_file.read_text()
    md_files = list(output_dir.glob("*.md"))
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

        t0 = time.monotonic()

        def optimize_seed(agent: str, judge: str) -> None:
            """Optimize one agent's seed report."""
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

                # Write judging prompt
                judge_prompt = build_judging_prompt(config.topic, report_text)
                round_dir = judging_dir / f"round-{round_num:02d}-{judge}-judges-{agent}"
                round_dir.mkdir(parents=True, exist_ok=True)

                prompt_file = round_dir / "judge-prompt.md"
                prompt_file.write_text(judge_prompt)

                # Run judge
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
                try:
                    judge_text = read_counselors_output(round_dir, judge)
                    judge_md.write_text(judge_text)
                except FileNotFoundError:
                    pass

                # Track seed score on first round
                if round_num == 1:
                    seed_result.seed_score = score

                seed_result.rounds_completed = round_num

                return score, asi

            def proposer(
                candidate: dict,
                reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
                components_to_update: list[str],
            ) -> dict[str, str]:
                """Send feedback to original agent to produce improved report."""
                feedback = extract_feedback_from_reflective_dataset(
                    reflective_dataset if isinstance(reflective_dataset, dict) else {}
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
            # (a string), which triggers ``make_litellm_lm()`` →
            # ``import litellm`` even when a custom_candidate_proposer fully
            # replaces the LLM reflection path.  Passing a callable skips the
            # string→LM conversion entirely, avoiding the litellm dependency.
            def _unused_lm(prompt):  # pragma: no cover
                raise RuntimeError("reflection_lm should never be called when custom_candidate_proposer is set")

            gepa_config = GEPAConfig(
                engine=EngineConfig(
                    max_metric_calls=max_rounds,
                    raise_on_exception=False,
                ),
                reflection=ReflectionConfig(
                    custom_candidate_proposer=proposer,
                    reflection_lm=_unused_lm,
                ),
            )

            try:
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
                self._save_optimization_log(run_dir, agent, result)

            except Exception:
                # Graceful degradation: fall back to seed
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

        score_a = opt.seeds[agent_a].final_score or opt.seeds[agent_a].seed_score or 0.0
        score_b = opt.seeds[agent_b].final_score or opt.seeds[agent_b].seed_score or 0.0

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
