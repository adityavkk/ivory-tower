---
title: "ivory-tower: GEPA integration -- gaps and Pareto-optimal evolution"
author: "human:aditya + agent:opencode"
version: 2
created: 2026-03-02
updated: 2026-03-02
depends_on: "02-STRATEGY-SPEC.md v1, 04-FIXES.md"
branch: "gepa-fixes"
---

# GEPA Integration -- Gaps & Pareto-Optimal Evolution

## Context

The adversarial strategy delegates iterative optimization to GEPA's
`optimize_anything` API. GEPA is designed as a Pareto-efficient search engine:
it maintains a frontier of candidates optimal across different quality axes,
uses an LLM reflector to diagnose *why* specific dimensions scored low, and
evolves candidates with targeted mutations. The initial integration bypassed
nearly all of this machinery. GEPA was reduced to an iteration counter with
accept/reject logic.

This document catalogues what GEPA offers, what we were using, the gaps
between the two, and what has been resolved.

---

## GEPA's Optimization Architecture (as understood)

Source: `gepa-ai/gepa` via DeepWiki analysis + adversarial.py usage patterns.

### The Core Loop

GEPA's `optimize_anything` runs a reflect-mutate-evaluate cycle:

```
INIT
  evaluate seed on valset → (score, ASI)
  initialize Pareto frontiers

EACH ITERATION
  1. SELECT candidate from Pareto frontier pool (not just current-best)
  2. SAMPLE minibatch from trainset
  3. EVALUATE candidate on minibatch with capture_traces=True
     → EvaluationBatch(outputs, scores, trajectories)
  4. BUILD reflective_dataset from EvaluationBatch
     → dict[component_name → list[{Inputs, Generated Outputs, Feedback}]]
  5. PROPOSE new candidate via reflection_lm (or custom_candidate_proposer)
     → reflection LLM analyzes traces, identifies failure modes, proposes fixes
  6. SUBSAMPLE EVALUATE new candidate on same minibatch
  7. ACCEPT if sum(new_scores) > sum(old_scores) on minibatch
  8. FULL VALIDATE if accepted → update Pareto frontiers
  9. STOP CHECK via stop_callback(state)
```

Three-stage internal pipeline within the proposer:
- **Executor**: runs candidate on a minibatch, capturing traces
- **Reflector**: powerful LLM analyzes traces + ASI to diagnose failure modes
- **Curator**: generates improved candidate with targeted text mutations

### Multi-Objective Pareto Optimization

GEPA recognizes a `"scores"` key in the evaluator's ASI dict:

```python
return score, {"scores": {"accuracy": 8.0, "depth": 7.0, "coverage": 6.0}}
```

Four frontier strategies track Pareto optimality differently:

| `frontier_type` | Tracks best candidate per... |
|-----------------|------------------------------|
| `instance`      | Each validation example       |
| `objective`     | Each named metric             |
| `hybrid`        | Both instance and objective   |
| `cartesian`     | Each (example × objective)    |

The `ParetoCandidateSelector` samples uniformly from Pareto-optimal candidates.
A candidate excelling on accuracy but mediocre on depth survives alongside one
with the opposite profile. The `MergeProposer` can combine two Pareto-optimal
candidates into a hybrid.

### Component-Level Targeting

GEPA supports multi-component candidates (e.g., `{"system_prompt": ...,
"query_rewriter": ..., "report": ...}`). A `ReflectionComponentSelector`
chooses which components to mutate:

- `"all"` -- mutate everything each round
- `"round_robin"` -- cycle through components one at a time

### The reflective_dataset Contract

Built by `GEPAAdapter.make_reflective_dataset()` from evaluation traces:

```python
{
    "report": [
        {
            "Inputs": "...",
            "Generated Outputs": "...",
            "Feedback": "..."  # ASI serialized to text
        },
        ...
    ]
}
```

This is what the reflection LLM (or custom proposer) receives to understand
what went wrong and why.

---

## What Ivory-Tower Does With GEPA (current, post-fixes)

References: `src/ivory_tower/strategies/adversarial.py`

### GEPAConfig setup (line ~1271)

```python
gepa_config = GEPAConfig(
    engine=EngineConfig(
        max_metric_calls=max_rounds + 1,
        raise_on_exception=False,
        frontier_type="objective",  # NEW: per-dimension Pareto tracking
    ),
    reflection=ReflectionConfig(
        custom_candidate_proposer=proposer,
        reflection_lm=_unused_lm,  # no-op stub
    ),
)
```

`frontier_type="objective"` enables per-dimension Pareto frontiers. No merge
proposer. No component selector.

### Evaluator closure (line ~1046)

Returns `(score, asi)` where `asi` now contains:

```python
{
    "dimensions": {"factual_accuracy": 8, "depth_of_analysis": 7, ...},
    "scores": {"factual_accuracy": 8.0, "depth_of_analysis": 7.0, ...},  # NEW
    "strengths": [...],
    "weaknesses": [...],
    "suggestions": [...],
    "critique": "...",
}
```

The `"scores"` key (line ~1117) mirrors `"dimensions"` as floats so GEPA
recognizes them for multi-objective Pareto frontier tracking. Per-round
dimension scores are also recorded to `seed_result.dimension_history`
(line ~1129) for manifest persistence.

### Proposer closure (line ~1148)

A `custom_candidate_proposer` that:

1. Reads judge feedback **from disk** (primary path, ground truth)
2. Falls back to `extract_feedback_from_reflective_dataset()` if disk read fails
   (now reliable since ASI includes proper `"scores"` key)
3. Builds an **evolving** improvement prompt via `build_improvement_prompt()`
   with `feedback_history` from prior rounds (line ~1217)
4. Appends current feedback to `feedback_history` for future rounds (line ~1221)
5. Dispatches the original authoring agent via `counselors run`
6. Returns `{"report": improved_text}`

### optimize_anything call (line ~1286)

```python
result = optimize_anything(
    seed_candidate={"report": seed_text},
    evaluator=evaluator,
    objective="Optimize this research report for accuracy, depth, ...",
    config=gepa_config,
)
```

Single component (`"report"`). No dataset/valset provided. No trainset for
minibatch sampling.

---

## Gap Analysis

### Gap 1: Pareto frontiers are single-dimensional -- RESOLVED

**What GEPA offers:** Multi-objective Pareto tracking via `asi["scores"]`. A
candidate scoring `{accuracy: 9, depth: 4}` and one scoring `{accuracy: 5,
depth: 9}` both survive on the frontier. Subsequent mutations can be selected
from either, and the merge proposer can combine them.

**What we did:** Return dimension scores under `asi["dimensions"]`, a key GEPA
did not inspect for Pareto tracking. GEPA saw only the single `float` score.

**Resolution:** Two changes:

1. The evaluator now injects `asi["scores"]` mirroring dimension values as
   floats (`adversarial.py:1117`). GEPA recognizes this key for Pareto
   frontier tracking.
2. `GEPAConfig` sets `frontier_type="objective"` (`adversarial.py:1280`) so
   GEPA maintains a frontier entry per named dimension.

**Tests:** `TestEvaluatorParetoScores` (2 tests), `TestGEPAConfigFrontierType`
(1 test) in `tests/test_adversarial_strategy.py`.

### Gap 2: Reflection LLM is stubbed out -- OPEN (by design)

**What GEPA offers:** A three-stage Executor -> Reflector -> Curator pipeline.
The Reflector (a powerful LLM) analyzes evaluation traces and ASI to produce a
causal diagnosis of *why* specific dimensions scored low. The Curator then
proposes targeted text mutations based on that diagnosis.

**What we do:** The `reflection_lm` is a no-op callable that raises
`RuntimeError`. All reflection logic is replaced by a `custom_candidate_proposer`
that dispatches a full agent session. However, the improvement prompt now
includes dimension-specific targeting (Gap 4 fix) which partially compensates
for the missing causal diagnosis.

**Status:** Intentionally open. The DON'T section explicitly says not to rip
out the custom_candidate_proposer. The agent-dispatch model via counselors is
fundamental. The prompt evolution (Gap 4) gives the agent dimension-level
guidance that approximates what GEPA's reflector would provide.

**Files involved:**
- `src/ivory_tower/strategies/adversarial.py` -- `_unused_lm` stub (~line 1268)

### Gap 3: reflective_dataset is bypassed -- RESOLVED

**What GEPA offers:** A structured, per-component, per-example dataset derived
from evaluation traces.

**What we did:** The proposer read judge output directly from disk and ignored
GEPA's `reflective_dataset`. Issue 12 in `spec/04-FIXES.md` documented why:
the dataset contained template/example values instead of actual judge feedback.

**Resolution:** The evaluator now returns proper structured ASI with the
`"scores"` key (Gap 1 fix). This flows into GEPA's reflective_dataset,
making `extract_feedback_from_reflective_dataset()` (~line 526) a reliable
fallback when disk-read fails. The disk-read path remains primary (ground
truth), but the fallback now gets correct data instead of template artifacts.

**Tests:** `TestExtractFeedbackFromReflectiveDataset::test_dataset_with_scores_key`
and `test_dataset_score_from_dimension_average` in `tests/test_adversarial_helpers.py`.

### Gap 4: Improvement prompts are static -- RESOLVED

**What GEPA offers:** The reflection LLM evolves its diagnosis across rounds.

**What we did:** Every improvement round used the same static template. No
round-over-round history. No score trajectory. No dimension-specific targeting.

**Resolution:** Three improvements to `build_improvement_prompt()` in
`src/ivory_tower/prompts.py`:

1. **Score trajectory** (`_build_score_trajectory()`, line 327): When
   `feedback_history` is provided, the prompt shows round-by-round score
   progression so the agent sees whether it's improving or regressing.

2. **Dimension targeting** (`_build_dimension_focus()`, line 342): Identifies
   the weakest dimension and adds a "Priority Focus" section directing the
   agent to prioritize that area above others.

3. **Failure-mode framing** (`_IMPROVEMENT_TASK_FAILURE`, line 239): When
   score < 4.0 (`_FAILURE_SCORE_THRESHOLD`, line 257), the prompt uses
   entirely different language -- "start fresh" instead of "STRICTLY BETTER"
   -- addressing the observed failure where agents producing workflow notes
   were told to incrementally improve a "research report" they never wrote.

The proposer in `adversarial.py` accumulates a `feedback_history` list
(line 1146) across rounds and passes it to `build_improvement_prompt()`
(line 1217). The first round gets no trajectory; subsequent rounds see
all prior scores.

**Tests:** `TestBuildImprovementPromptEvolution` (5 tests) in
`tests/test_prompts.py`; `TestProposerFeedbackHistory` (2 tests) in
`tests/test_adversarial_strategy.py`.

### Gap 5: No dataset/valset structure -- OPEN (structural)

**What GEPA offers:** Minibatch sampling from a trainset for efficient
evaluation, plus a valset for full validation of accepted candidates.

**What we do:** No dataset or valset is provided. `optimize_anything` operates
in single-candidate mode. Each evaluation is a single judge call on the full
report.

**Status:** Intentionally open. Research report optimization is genuinely a
single-instance problem. The DON'T section says not to over-engineer the
dataset/valset mapping. Multi-aspect evaluation (each dimension as a separate
"example") could be explored in the future, but the per-dimension Pareto
tracking via `frontier_type="objective"` already captures much of the benefit
without forcing an artificial dataset structure.

### Gap 6: Accept/reject is opaque to ivory-tower -- OPEN (mitigated)

**What GEPA does:** Accepts a candidate only if `sum(new_subsample_scores) >
sum(old_subsample_scores)`. Rejected candidates are discarded.

**What we see:** The proposer returns a candidate to GEPA and gets no direct
feedback on whether it was accepted or rejected.

**Status:** Partially mitigated. The `feedback_history` accumulated by the
proposer (Gap 4 fix) gives indirect signal -- if the proposer sees the same
score in consecutive rounds, it implies the prior attempt was rejected. The
score trajectory in the prompt makes this visible to the agent. Full
accept/reject awareness would require GEPA API changes or state inspection
hooks that aren't currently available.

---

## Observed Behavior From Live Runs

### Run `20260302-014225-adb65f` (WebSocket vs SSE, --max-rounds 2)

**opencode-anthropic-fast** (improved):
- Seed: 6.6/10 (15K chars, complete report)
- Round 2: 7.3/10 (same report, no improvement round yet -- GEPA's seed re-eval?)
- Round 3: 7.4/10 (after first improvement)
- Round 4: 7.2/10 (after second improvement -- slight regression)
- Final: 7.2/10 (GEPA selected last evaluation, not best)

Improvement was marginal (+0.6). The static prompt gave all feedback at once;
the agent made broad edits but couldn't target specific weak dimensions.

**opencode-openai-fast** (failed to improve):
- Seed: 7.4/10 (12K chars, but was workflow metadata not a report)
- Round 2: 2.0/10 (judge correctly identified "not a report")
- Round 3: 2.0/10 (agent submitted more workflow notes)
- Final: 7.4/10 (GEPA correctly preserved seed over degraded candidates)

The static prompt said "You previously wrote a research report" to an agent
that had never written one. No escalation. The agent's failure mode (producing
planning metadata instead of a report) was never addressed in the prompt.

### Parse-agent fallback (implemented in this session)

Two of seven judging rounds required the `--parse-agent` fallback because all 5
regex strategies failed to extract JSON from judge output. The fallback
dispatched a fast agent to re-format the prose into structured JSON. Both
extractions succeeded, recovering scores of 7.2 and 2.0 that would have been
0.0 without the fallback.

---

## WANT

- Leverage GEPA's multi-objective Pareto optimization so candidates evolve
  along quality axes (accuracy, depth, coverage, source quality, rigor)
  independently, preserving diverse high-quality candidates.

- Feed dimension scores through GEPA's recognized `"scores"` key so the Pareto
  frontier tracks per-dimension optimality, not just aggregate score.

- Understand whether GEPA's reflective_dataset can be made reliable for
  ivory-tower's use case, or whether the disk-read workaround should remain
  the primary path with reflective_dataset as a structured supplement.

- Evolve improvement prompts across rounds -- score trajectory, prior feedback
  history, dimension-specific targeting for the weakest axis, failure-mode
  awareness.

- Explore whether GEPA's merge proposer could combine a high-accuracy candidate
  with a high-depth candidate into a stronger hybrid.

- Investigate whether the judging dimensions map naturally to GEPA's
  dataset/valset model (e.g., each dimension as a separate evaluation
  "example").

## DON'T

- Rip out the custom_candidate_proposer. Ivory-tower's agent-dispatch model
  (counselors run) is fundamental. The question is how to feed GEPA's
  structured feedback into that dispatch, not whether to replace it with
  GEPA's internal LLM.

- Assume GEPA's internals are stable. The `gepa` package is third-party and
  WIP. Any deeper integration should be defensive and tested against actual
  GEPA behavior, not just documentation.

- Over-engineer the dataset/valset mapping. Research report optimization may
  genuinely be a single-instance problem. Don't force a dataset structure
  that doesn't fit.

- Couple the improvement prompt evolution too tightly to GEPA's round
  numbering. The prompt template should be the orchestrator's concern, not
  GEPA's.

## FOR

- The adversarial strategy in ivory-tower, specifically the GEPA integration
  in `src/ivory_tower/strategies/adversarial.py` and the prompt templates in
  `src/ivory_tower/prompts.py`.

- Users running `ivory research --strategy adversarial` who expect iterative
  improvement to produce meaningfully better reports, not marginal gains on
  already-decent seeds.

## ENSURE

- [x] Existing tests pass after any changes (`uv run pytest tests/ -x -v`).
      624 tests pass as of v2.
- [x] The evaluator's ASI includes a `"scores"` dict that GEPA recognizes.
      `TestEvaluatorParetoScores::test_evaluator_asi_contains_scores_key`
- [x] A live adversarial run with `--max-rounds 3` shows dimension-level score
      movement (not just aggregate) in the optimization log.
      Run `20260302-083944-8642c7`: both agents show 4 rounds of per-dimension
      scores in `dimension_history`. Anthropic: 7.6 -> 6.8 -> 7.4 -> 3.8 with
      dimension-level breakdowns. OpenAI: 8.4 -> 8.1 -> 7.8 -> 7.4.
      Live tests: `TestAdversarialLiveE2E` (25 pass, 1 skip).
- [x] The improvement prompt for round N references feedback from round N-1
      specifically, not a generic dump of all feedback.
      `TestProposerFeedbackHistory::test_improvement_prompt_contains_score_trajectory`
- [x] When a candidate scores below a threshold (e.g., < 4.0), the improvement
      prompt adapts its framing to address the failure mode.
      `TestBuildImprovementPromptEvolution::test_failure_mode_framing_when_score_below_4`
- [x] Parse-agent fallback (`--parse-agent`) continues to work alongside any
      GEPA integration changes. All existing parse-agent tests pass.

## TRUST

- GEPA's `optimize_anything` API contract: evaluator returns `(score, asi)`,
  `asi["scores"]` enables multi-objective Pareto, `custom_candidate_proposer`
  receives `(candidate, reflective_dataset, components_to_update)`.
- GEPA's accept/reject logic is correct (greedy hill-climbing on subsample).
- The counselors CLI continues to work as the agent dispatch mechanism.
- The `--parse-agent` fallback handles JSON extraction failures.

---

## File Reference

| File | Key locations |
|------|---------------|
| `src/ivory_tower/strategies/adversarial.py` | Evaluator (~1046), `asi["scores"]` injection (~1117), `dimension_history` recording (~1129), `feedback_history` accumulation (~1146), proposer (~1148), `build_improvement_prompt` call with history (~1217), `_unused_lm` stub (~1268), GEPAConfig with `frontier_type` (~1271), `optimize_anything` call (~1286), `phases_to_dict` with `dimension_history` (~866), `phases_from_dict` with `dimension_history` (~924) |
| `src/ivory_tower/prompts.py` | `_IMPROVEMENT_HEADER` (~190), `_IMPROVEMENT_TASK_NORMAL` (~225), `_IMPROVEMENT_TASK_FAILURE` (~239), `_FAILURE_SCORE_THRESHOLD` = 4.0 (~257), `_DIMENSION_LABELS` (~259), `_find_weakest_dimension()` (~311), `_build_score_trajectory()` (~327), `_build_dimension_focus()` (~342), `build_improvement_prompt()` with `feedback_history` kwarg (~357), `_JUDGING_TEMPLATE` (~146) |
| `src/ivory_tower/models.py` | `SeedOptimizationResult.dimension_history` (~71) |
| `src/ivory_tower/engine.py` | `RunConfig` -- carries `parse_agent` and config fields |
| `src/ivory_tower/cli.py` | CLI flags for configuration surface |
| `spec/04-FIXES.md` | Issues 11-16: related parsing/feedback bugs |
| `tests/test_adversarial_helpers.py` | `TestExtractFeedbackFromReflectiveDataset` (5 tests including new scores-key and dimension-average tests) |
| `tests/test_adversarial_strategy.py` | `TestEvaluatorParetoScores` (2 tests), `TestGEPAConfigFrontierType` (1 test), `TestProposerFeedbackHistory` (2 tests), `TestAdversarialPhaseSerialization::test_roundtrip_preserves_dimension_history` |
| `tests/test_prompts.py` | `TestBuildImprovementPromptEvolution` (5 tests: trajectory, weakest dimension, failure mode, no-history, backward compat) |
| `tests/test_models.py` | `TestSeedOptimizationResult::test_dimension_history_*` (2 tests) |
| `tests/test_integration.py` | Fake `EngineConfig` updated with `frontier_type` field |
| `tests/test_live_e2e.py` | `TestAdversarialLiveE2E` (27 tests: 15 structural + 10 GEPA feature verification + 2 skippable) |

## Implementation Summary (v3)

Branch: `gepa-fixes` (10 commits)

| Commit | Gap | Description |
|--------|-----|-------------|
| `003c91b` | 1 | Inject `asi["scores"]` in evaluator for GEPA Pareto tracking |
| `094e9de` | 4 | Evolve improvement prompts: trajectory, dimension targeting, failure-mode framing |
| `f7fbeb5` | 4 | Wire proposer to accumulate `feedback_history` across rounds |
| `4f57b0b` | 3 | Validate reflective_dataset works with new ASI scores format |
| `d50fa02` | -- | Track per-dimension score history in `SeedOptimizationResult` |
| `67ae6c4` | 1 | Set `frontier_type="objective"` on GEPAConfig |
| `789b3d9` | -- | Live GEPA feature tests + `dimension_history` in optimization log |
| `17bd228` | -- | Bump live test to `max_rounds=3` for trajectory verification |
| `ed399f6` | -- | Fix judging dir glob to filter directories only |

### What changed

**`adversarial.py`**: ASI `"scores"` injection after `parse_judge_output`;
`dimension_history` appended per round; `feedback_history` list accumulated
in proposer closure and passed to `build_improvement_prompt`;
`frontier_type="objective"` in `EngineConfig`; serialization of
`dimension_history` in `phases_to_dict`/`phases_from_dict`;
`_save_optimization_log` now includes `dimension_history` kwarg.

**`prompts.py`**: Static `_IMPROVEMENT_TEMPLATE` split into composable parts:
`_IMPROVEMENT_HEADER` (feedback display), `_IMPROVEMENT_TASK_NORMAL` (standard
instructions), `_IMPROVEMENT_TASK_FAILURE` (low-score reframing). New helpers:
`_find_weakest_dimension()`, `_build_score_trajectory()`,
`_build_dimension_focus()`. `build_improvement_prompt()` gains optional
`feedback_history` kwarg; assembles prompt dynamically based on score level
and available history.

**`models.py`**: `dimension_history: list[dict]` field on
`SeedOptimizationResult` with `field(default_factory=list)`.

**`test_live_e2e.py`**: 10 new live tests verifying GEPA prompt features:
dimension_history persistence, per-dimension scores, score movement,
improvement prompts, trajectory (skips at max_rounds=3, needs >=5),
dimension focus, round-debug.json, judging dirs, optimization log
dimension_history.

**Unit tests**: 15 new test methods across 4 files covering all changes.

### Live Run Observations (v3)

**Run `20260302-083944-8642c7`** (WebSocket vs SSE, `--max-rounds 3`):

| Agent | Seed | Round 2 | Round 3 | Round 4 | Final |
|-------|------|---------|---------|---------|-------|
| opencode-anthropic-fast | 7.6 | 6.8 | 7.4 | 3.8 | 7.6 (seed preserved) |
| opencode-openai-fast | 8.4 | 8.1 | 7.8 | 7.4 | 8.4 (seed preserved) |

**Features verified live:**
- `dimension_history` persisted in manifest with per-dimension breakdowns
- `Priority Focus` section present in improvement prompts (Source Quality, Depth of Analysis)
- `round-debug.json` captures evaluator feedback dimensions
- `dimension_history` in optimization log JSON
- Judging round dirs contain `judge-prompt.md` files
- GEPA Pareto tracking logs show per-objective frontier updates

**Features not exercised (by design):**
- Score Trajectory: requires 2+ proposer calls, but GEPA's metric budget
  allows only ~1 iteration per 2 `max_metric_calls`. At `max_rounds=3`
  (4 metric calls), only 1 proposer call occurs. Needs `max_rounds>=5`.
- Failure-mode framing: no seed scored below 4.0 in this run. The
  anthropic agent's round 4 scored 3.8 but that was a post-improvement
  eval, not a seed. The feature is unit-tested.

**Key insight:** GEPA uses ~2 evaluator calls per iteration (subsample +
full valset). So `max_rounds=N` gives `(N+1)/2` GEPA iterations, meaning
the proposer is called at most `floor((N+1)/2)` times.

### Remaining open gaps

| Gap | Status | Notes |
|-----|--------|-------|
| 2 (Reflection LLM) | Open (by design) | custom_candidate_proposer is fundamental; prompt evolution partially compensates |
| 5 (dataset/valset) | Open (structural) | Single-instance problem; `frontier_type="objective"` captures most benefit |
| 6 (accept/reject) | Open (mitigated) | Score trajectory gives indirect signal; full awareness requires GEPA API changes |
