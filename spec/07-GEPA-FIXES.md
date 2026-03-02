---
title: "ivory-tower: GEPA integration -- gaps and Pareto-optimal evolution"
author: "human:aditya + agent:opencode"
version: 1
created: 2026-03-02
depends_on: "02-STRATEGY-SPEC.md v1, 04-FIXES.md"
---

# GEPA Integration -- Gaps & Pareto-Optimal Evolution

## Context

The adversarial strategy delegates iterative optimization to GEPA's
`optimize_anything` API. GEPA is designed as a Pareto-efficient search engine:
it maintains a frontier of candidates optimal across different quality axes,
uses an LLM reflector to diagnose *why* specific dimensions scored low, and
evolves candidates with targeted mutations. The current integration bypasses
nearly all of this machinery. GEPA is reduced to an iteration counter with
accept/reject logic.

This document catalogues what GEPA offers, what we're actually using, and the
gaps between the two. It does not prescribe a specific implementation plan --
the goal is to understand the design space and inform decisions.

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

## What Ivory-Tower Actually Does With GEPA

References: `src/ivory_tower/strategies/adversarial.py`

### GEPAConfig setup (line ~1238)

```python
gepa_config = GEPAConfig(
    engine=EngineConfig(
        max_metric_calls=max_rounds + 1,
        raise_on_exception=False,
    ),
    reflection=ReflectionConfig(
        custom_candidate_proposer=proposer,
        reflection_lm=_unused_lm,  # no-op stub
    ),
)
```

No `frontier_type` set. No merge proposer. No component selector.

### Evaluator closure (line ~1046)

Returns `(score, asi)` where `asi` contains:

```python
{
    "dimensions": {"factual_accuracy": 8, "depth_of_analysis": 7, ...},
    "strengths": [...],
    "weaknesses": [...],
    "suggestions": [...],
    "critique": "...",
}
```

Note: no `"scores"` key. GEPA only recognizes `"scores"` for multi-objective
Pareto tracking.

### Proposer closure (line ~1123)

A `custom_candidate_proposer` that:

1. Reads judge feedback **from disk** (not from GEPA's reflective_dataset)
   - Line ~1140 comment: *"GEPA's reflective_dataset is unreliable"*
2. Falls back to `extract_feedback_from_reflective_dataset()` only if disk read fails
3. Builds an improvement prompt via `build_improvement_prompt()` (static template)
4. Dispatches the original authoring agent via `counselors run`
5. Returns `{"report": improved_text}`

### optimize_anything call (line ~1253)

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

### Gap 1: Pareto frontiers are single-dimensional

**What GEPA offers:** Multi-objective Pareto tracking via `asi["scores"]`. A
candidate scoring `{accuracy: 9, depth: 4}` and one scoring `{accuracy: 5,
depth: 9}` both survive on the frontier. Subsequent mutations can be selected
from either, and the merge proposer can combine them.

**What we do:** Return dimension scores under `asi["dimensions"]`, a key GEPA
does not inspect for Pareto tracking. GEPA sees only the single `float` score.
The frontier degenerates to a single best-score candidate.

**Consequence:** No diversity preservation. No dimension-aware candidate
selection. The merge proposer has nothing to merge. GEPA hill-climbs on a
single aggregate score, missing the opportunity to explore trade-off space.

**Files involved:**
- `src/ivory_tower/strategies/adversarial.py` -- evaluator closure (~line 1121)
- `src/ivory_tower/prompts.py` -- judging template requests dimensions

### Gap 2: Reflection LLM is stubbed out

**What GEPA offers:** A three-stage Executor → Reflector → Curator pipeline.
The Reflector (a powerful LLM) analyzes evaluation traces and ASI to produce a
causal diagnosis of *why* specific dimensions scored low. The Curator then
proposes targeted text mutations based on that diagnosis.

**What we do:** The `reflection_lm` is a no-op callable that raises
`RuntimeError`. All reflection logic is replaced by a `custom_candidate_proposer`
that builds a static improvement template and dispatches a full agent session.

**Consequence:** No causal diagnosis. No targeted mutation. The improvement
prompt dumps all feedback (strengths, weaknesses, suggestions, critique) into a
single template and asks the agent to "produce a STRICTLY BETTER version." The
agent receives no guidance on which dimension to prioritize or what specific
text mutations would address the lowest-scoring axes.

**Files involved:**
- `src/ivory_tower/strategies/adversarial.py` -- `_unused_lm` stub (~line 1235),
  proposer closure (~line 1123)
- `src/ivory_tower/prompts.py` -- `_IMPROVEMENT_TEMPLATE` (~line 190)

### Gap 3: reflective_dataset is bypassed

**What GEPA offers:** A structured, per-component, per-example dataset derived
from evaluation traces. Designed as the input contract for the reflection LLM
to understand what went wrong on specific examples.

**What we do:** The proposer reads judge output directly from disk and ignores
GEPA's `reflective_dataset`. Issue 12 in `spec/04-FIXES.md` documents why: the
dataset contained template/example values instead of actual judge feedback.

**Consequence:** We lose GEPA's structured feedback transformation. The
workaround (disk-read) works but means the proposer operates outside GEPA's
feedback loop. Any GEPA features that depend on the proposer consuming the
reflective_dataset (trace accumulation, lineage-aware reflection) are broken.

**Files involved:**
- `src/ivory_tower/strategies/adversarial.py` -- proposer closure (~line 1140),
  `extract_feedback_from_reflective_dataset()` (~line 555)

### Gap 4: Improvement prompts are static

**What GEPA offers:** The reflection LLM evolves its diagnosis across rounds.
Each candidate inherits accumulated lessons from its ancestors in the search
tree. The `GEPAState` tracks `parent_program_for_candidate` lineage.

**What we do:** Every improvement round uses the same `_IMPROVEMENT_TEMPLATE`
(prompts.py:190). The template contains: current report, latest judge feedback,
and a fixed 5-point instruction. No round-over-round history. No score
trajectory. No delta/diff awareness. No dimension-specific targeting.

**Consequence:** The agent improving a 7.3-scored report receives the same
framing as one improving a 2.0-scored report. An agent that submitted workflow
notes instead of a report gets "You previously wrote a research report" -- no
escalation, no reframing. The prompt doesn't adapt to failure modes.

**Files involved:**
- `src/ivory_tower/prompts.py` -- `_IMPROVEMENT_TEMPLATE` (~line 190),
  `build_improvement_prompt()` (~line 282)

### Gap 5: No dataset/valset structure

**What GEPA offers:** Minibatch sampling from a trainset for efficient
evaluation, plus a valset for full validation of accepted candidates. This
enables GEPA to find candidates that generalize across evaluation criteria
rather than overfitting to a single evaluator call.

**What we do:** No dataset or valset is provided. `optimize_anything` operates
in single-candidate mode. Each evaluation is a single judge call on the full
report.

**Consequence:** No minibatch diversity. No generalization signal. GEPA's
subsample-then-validate strategy (which prevents overfitting to lucky
evaluations) is unused.

**Note:** This gap is structural -- research report optimization may genuinely
be a single-instance problem. But multi-aspect evaluation (accuracy, depth,
coverage as separate "examples") could map naturally to GEPA's dataset model.

### Gap 6: Accept/reject is opaque to ivory-tower

**What GEPA does:** Accepts a candidate only if `sum(new_subsample_scores) >
sum(old_subsample_scores)`. Rejected candidates are discarded.

**What ivory-tower sees:** The proposer returns a candidate to GEPA and gets no
feedback on whether it was accepted or rejected. The proposer doesn't know if
the improvement actually improved anything. If GEPA rejects the candidate,
the proposer is called again with the same (or different, if Pareto selection
changes) base candidate, but with no indication that the previous attempt
failed.

**Consequence:** No learning from rejected proposals. The proposer may make the
same type of unsuccessful mutation repeatedly.

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

- Existing tests pass after any changes (`uv run pytest tests/ -x -v`).
- The evaluator's ASI includes a `"scores"` dict that GEPA recognizes.
- A live adversarial run with `--max-rounds 3` shows dimension-level score
  movement (not just aggregate) in the optimization log.
- The improvement prompt for round N references feedback from round N-1
  specifically, not a generic dump of all feedback.
- When a candidate scores below a threshold (e.g., < 4.0), the improvement
  prompt adapts its framing to address the failure mode.
- Parse-agent fallback (`--parse-agent`) continues to work alongside any
  GEPA integration changes.

## TRUST

- GEPA's `optimize_anything` API contract: evaluator returns `(score, asi)`,
  `asi["scores"]` enables multi-objective Pareto, `custom_candidate_proposer`
  receives `(candidate, reflective_dataset, components_to_update)`.
- GEPA's accept/reject logic is correct (greedy hill-climbing on subsample).
- The counselors CLI continues to work as the agent dispatch mechanism.
- The `--parse-agent` fallback handles JSON extraction failures.

---

## File Reference

| File | Relevance |
|------|-----------|
| `src/ivory_tower/strategies/adversarial.py` | Evaluator (~1046), proposer (~1123), GEPAConfig (~1238), optimize_anything call (~1253) |
| `src/ivory_tower/prompts.py` | `_IMPROVEMENT_TEMPLATE` (~190), `_JUDGING_TEMPLATE` (~140), `build_improvement_prompt()` (~282) |
| `src/ivory_tower/engine.py` | `RunConfig` -- carries `parse_agent` and future config fields |
| `src/ivory_tower/models.py` | `Flags`, `SeedOptimizationResult` -- may need per-dimension score tracking |
| `src/ivory_tower/cli.py` | CLI flags for any new configuration surface |
| `spec/04-FIXES.md` | Issues 11-16: related parsing/feedback bugs, some fixed, some open |
| `tests/test_adversarial_helpers.py` | Unit tests for parse_judge_output, extraction helpers |
| `tests/test_adversarial_strategy.py` | Strategy-level mocked tests |
