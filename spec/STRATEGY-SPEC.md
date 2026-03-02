---
title: "ivory-tower: strategy abstraction + adversarial optimization"
author: "human:aditya"
version: 1
created: 2026-03-01
depends_on: "SPEC.md v1"
---

# Ivory Tower v2 -- Strategy Abstraction + Adversarial Optimization

## HOW

- **Worktree**: All implementation work happens in a git worktree branched from `strategy-abstraction`. Not in the main working tree.
- **Red-Green TDD**: Every commit starts with failing tests (RED), then implementation until green (GREEN). Tests and implementation are committed together. Every commit leaves the suite green.
- **Commits**: 11 logical commits, each covering one end-to-end feature slice. See [Commit Plan](#commit-plan) for the full breakdown.
- **Merge**: After all tests pass and regression is clean, merge `strategy-abstraction` into `main`, remove the worktree, delete the branch.

```bash
# Setup
git worktree add ../ivory-tower-impl strategy-abstraction
cd ../ivory-tower-impl

# ... 11 commits, each red-green ...

# Merge
uv run pytest tests/ -v
cd ../ivory-tower
git checkout main
git merge strategy-abstraction
git worktree remove ../ivory-tower-impl
git branch -d strategy-abstraction
```

- **Test conventions**: All `counselors` calls mocked via `unittest.mock.patch`. GEPA calls mocked similarly. File-based tests use `tmp_path`. No real network calls.

## WANT

- Refactor `ivory` from a hardcoded 3-phase pipeline into an **orchestrator of research strategies**. The CLI dispatches to a strategy; strategies define their own phases, agent requirements, and execution flow.
- The existing 3-phase workflow becomes the **`council`** strategy -- the first of many.
- Introduce a new **`adversarial`** strategy: 2 agents each produce a seed report, then each seed is iteratively optimized by GEPA's `optimize_anything` while the _opposite_ agent scores and critiques each iteration. A final synthesis merges both optimized reports.
- Deliverables from adversarial: both optimized reports + a synthesized final report.
- Use `gepa` Python package directly. The custom evaluator shells out to `counselors run` for adversarial judging.
- Default optimization budget: **10 rounds per seed**. Configurable via `--max-rounds`.
- Strategy selection via `--strategy` flag. Default: `council`.

## DON'T

- Break the existing `council` strategy. It must work identically to v1 after the refactor.
- Implement agent execution directly. All agent dispatch goes through `counselors run`.
- Reimplement GEPA's optimization loop. Use `gepa.optimize_anything` as a library.
- Require `gepa` for the `council` strategy. It is only a dependency for `adversarial`.
- Merge optimized reports without also delivering them individually.
- Add config files. Strategy selection and configuration remain CLI flags.
- Support more than 2 agents for `adversarial` in v1. The pairing is inherently dyadic.
- Auto-select agents or strategies. User must specify.
- Hardcode GEPA optimization parameters. Budget comes from `--max-rounds`.

## LIKE

- [gepa-ai/gepa](https://github.com/gepa-ai/gepa) -- `optimize_anything` API, evaluator contract (score + ASI), Pareto-efficient search, `GEPAConfig`/`EngineConfig`.
- [hamelsmu/research-council](https://github.com/hamelsmu/research-council) -- skeptical cross-pollination, file-mediated agent communication, graceful degradation.
- [SPEC.md](./SPEC.md) -- the v1 spec this builds on.
- [Strategy pattern](https://refactoring.guru/design-patterns/strategy) -- encapsulate a family of algorithms, make them interchangeable.

## FOR

- **Who**: Developers/researchers willing to spend more compute for higher-quality multi-agent research.
- **Environment**: macOS, Python 3.12+, uv, `counselors` CLI installed globally. `gepa` required only for `adversarial`.
- **Domain**: Deep research where quality matters more than speed.
- **Tech stack**: Python, typer, uv, `counselors` (subprocess), `gepa` (Python library, optional dependency).

## ENSURE

### Strategy Abstraction

- `ivory research "topic" --strategy council --agents a,b --synthesizer a` runs identically to v1.
- `ivory research "topic" --strategy adversarial --agents a,b --synthesizer a` runs the adversarial pipeline.
- `ivory strategies` lists available strategies with one-line descriptions.
- Omitting `--strategy` defaults to `council`.
- Strategy implementations live in `src/ivory_tower/strategies/` as separate modules. Adding a new strategy means adding a module and registering it -- no changes to `cli.py` or `engine.py`.
- Each strategy implements: `name`, `description`, `validate(config) -> list[str]`, `create_manifest(config, run_id) -> Manifest`, `run(run_dir, config, manifest) -> Manifest`, `resume(run_dir, config, manifest) -> Manifest`, `dry_run(config)`, `format_status(manifest) -> list[tuple[str, str]]`.
- `adversarial` rejects `--agents` lists with != 2 agents.
- `council` accepts 2+ agents (same as v1).

### Adversarial Pipeline

- **Phase 1 -- Seed Generation**: Both agents independently research the topic (identical to council Phase 1). Outputs: `phase1/<agent>-seed.md`.
- **Phase 2 -- Adversarial Optimization**: For each seed, `optimize_anything` is called with:
  - `seed_candidate`: `{"report": "<text>"}`
  - `evaluator`: sends candidate to _opposite_ agent via `counselors run` with judging prompt; parses score (1-10) and critique; returns `(score, asi_dict)`
  - `custom_candidate_proposer`: sends judge feedback to _original_ agent via `counselors run` to produce an improved report (retains web search and tool capabilities every round)
  - `objective`: "Optimize this research report for accuracy, depth, coverage, source quality, and analytical rigor"
  - `config`: `GEPAConfig(engine=EngineConfig(max_metric_calls=<max_rounds>))`. No `reflection_lm` needed.
- Both seeds optimize concurrently (two GEPA loops in parallel via threading).
- Outputs: `phase2/<agent>-optimized.md`, `phase2/<agent>-optimization-log.json`.
- **Phase 3 -- Synthesis**: Synthesizer reads both optimized reports, produces `phase3/final-report.md`.

### Adversarial Judging

- Judging prompt instructs the opposing agent to score on 5 dimensions (1-10): factual accuracy, depth of analysis, source quality, coverage breadth, analytical rigor.
- Judge returns structured JSON: overall score (float), per-dimension scores, strengths, weaknesses, suggestions, critique.
- Judge's critique is returned as ASI. GEPA passes it via `reflective_dataset` to the proposer, which forwards it to the original agent.
- Judge invocations use `counselors run`.

### CLI Changes

- `--strategy` flag (choices: `council`, `adversarial`; default: `council`).
- `--max-rounds` flag (integer, default: 10, adversarial only).
- `--reflection-model` is NOT needed (we use `custom_candidate_proposer` instead of GEPA's reflection LM).
- `ivory strategies` lists available strategies.
- `ivory resume` reads strategy from manifest and dispatches accordingly.
- All existing flags work unchanged.

### Manifest Changes

- `manifest.json` gains `"strategy"` field.
- Adversarial phases: `"seed_generation"`, `"adversarial_optimization"`, `"synthesis"`.
- Adversarial optimization phase tracks per-seed: current round, best score, score history, final score.
- Resume reads `strategy` from manifest to dispatch correctly.
- v1 manifests lacking `"strategy"` default to `"council"`. v1 manifests lacking `"max_rounds"` in flags default to `10`.

### Output Structure (Adversarial)

```
./research/20260301-143000-a1b2c3/
    manifest.json
    topic.md
    phase1/
        claude-opus-seed.md
        codex-5.3-xhigh-seed.md
    phase2/
        claude-opus-optimized.md
        codex-5.3-xhigh-optimized.md
        claude-opus-optimization-log.json
        codex-5.3-xhigh-optimization-log.json
        judging/
            round-01-claude-opus-judges-codex-5.3-xhigh.md
            round-01-codex-5.3-xhigh-judges-claude-opus.md
            ...
    phase3/
        final-report.md
    logs/
```

### Dry Run

- `--dry-run` for adversarial shows: agents, seed generation plan, optimization config (max rounds), judging setup (who judges whom), synthesis plan.

## TRUST

- [autonomous] GEPA configuration parameters (batch size, parallelism, candidate selection strategy).
- [autonomous] Judging prompt format and structure.
- [autonomous] Optimization log JSON format.
- [autonomous] GEPA evaluator implementation details.
- [autonomous] Strategy registry/discovery mechanism.
- [autonomous] Threading model for parallel optimization loops.
- [ask] New strategies beyond `council` and `adversarial`.
- [ask] Changing the judging rubric (5 dimensions, 1-10 scale).
- [ask] Changing the adversarial pairing constraint (exactly 2 agents).
- [ask] Adding GEPA-specific config flags beyond `--max-rounds`.
- [ask] Changing GEPA's candidate selection strategy from default (Pareto).
- [ask] Multi-round adversarial debate (agents respond to each other's optimized reports).

---

# Architecture

## Module Structure

```
src/ivory_tower/
    __init__.py
    cli.py                          # Modified: --strategy, --max-rounds, ivory strategies
    counselors.py                   # Unchanged
    models.py                       # Extended: strategy field, PARTIAL status, adversarial types
    prompts.py                      # Extended: judging + improvement prompt templates
    run.py                          # Minor: manifest creation becomes strategy-specific
    engine.py                       # Simplified: thin dispatcher to strategy.run/resume
    strategies/
        __init__.py                 # Registry + get_strategy()
        base.py                     # ResearchStrategy Protocol
        council.py                  # Extracted from engine.py
        adversarial.py              # GEPA-based strategy
```

## Strategy Protocol

```python
class ResearchStrategy(Protocol):
    name: str
    description: str

    def validate(self, config: RunConfig) -> list[str]: ...
    def create_manifest(self, config: RunConfig, run_id: str) -> Manifest: ...
    def run(self, run_dir: Path, config: RunConfig, manifest: Manifest) -> Manifest: ...
    def resume(self, run_dir: Path, config: RunConfig, manifest: Manifest) -> Manifest: ...
    def dry_run(self, config: RunConfig) -> None: ...
    def format_status(self, manifest: Manifest) -> list[tuple[str, str]]: ...
    def phases_to_dict(self, phases: dict) -> dict: ...
    def phases_from_dict(self, data: dict) -> dict: ...
```

## Strategy Registry

```python
STRATEGIES: dict[str, type[ResearchStrategy]] = {
    "council": CouncilStrategy,
    "adversarial": AdversarialStrategy,
}

def get_strategy(name: str) -> ResearchStrategy: ...
def list_strategies() -> list[tuple[str, str]]: ...
```

`get_strategy` raises `ValueError` for unknown names. `list_strategies` returns `[(name, description)]` from all registered strategies.

## Data Types

### RunConfig

```python
@dataclass
class RunConfig:
    topic: str
    agents: list[str]
    synthesizer: str
    strategy: str = "council"
    raw: bool = False
    instructions: str | None = None
    verbose: bool = False
    output_dir: Path = field(default_factory=lambda: Path("./research"))
    dry_run: bool = False
    max_rounds: int = 10
```

### PhaseStatus

```python
class PhaseStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    PARTIAL = "partial"         # NEW: some sub-tasks succeeded, others failed
```

### Flags

```python
@dataclass
class Flags:
    raw: bool = False
    instructions: str | None = None
    verbose: bool = False
    max_rounds: int = 10        # NEW
```

### Manifest

```python
@dataclass
class Manifest:
    run_id: str
    topic: str
    agents: list[str]
    synthesizer: str
    flags: Flags
    phases: dict[str, Any]      # Strategy defines the phase structure
    strategy: str = "council"   # NEW
    total_duration_seconds: float | None = None
```

Serialization: `to_dict()` writes `"strategy"` and delegates phases to the strategy's `phases_to_dict`. `from_dict()` reads `data.get("strategy", "council")` for backward compat, then delegates to the strategy's `phases_from_dict`.

### Adversarial Phase Types

```python
@dataclass
class SeedOptimizationResult:
    status: PhaseStatus
    judge: str
    rounds_completed: int = 0
    seed_score: float | None = None
    final_score: float | None = None
    output: str = ""
    log: str = ""

@dataclass
class AdversarialOptimizationPhase:
    status: PhaseStatus
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    seeds: dict[str, SeedOptimizationResult] = field(default_factory=dict)
```

The adversarial strategy uses `ResearchPhase` for Phase 1, `AdversarialOptimizationPhase` for Phase 2, `SynthesisPhase` for Phase 3.

## Prompt Templates

All templates live in `prompts.py`. One copy each.

### Judging Prompt

```markdown
# Research Report Evaluation

You are an expert research evaluator. Score the following research report
on a 1-10 scale across five dimensions. Be rigorous and critical.

## Research Topic
{topic}

## Report to Evaluate
{candidate_report}

## Scoring Rubric

Rate each dimension from 1 (poor) to 10 (excellent):

1. **Factual Accuracy** -- Are claims well-sourced and verifiable? Any errors or unsupported assertions?
2. **Depth of Analysis** -- Does the report go beyond surface-level description into genuine insight?
3. **Source Quality** -- Are sources authoritative, current, and primary? Or mostly secondary/outdated?
4. **Coverage Breadth** -- Does the report cover all important aspects of the topic? Any major gaps?
5. **Analytical Rigor** -- Is reasoning sound? Are conclusions supported by evidence? Are counterarguments considered?

## Output Format (JSON)

Respond with ONLY a JSON object (no markdown fencing, no extra text):

{
  "overall_score": <float 1-10, weighted average>,
  "dimensions": {
    "factual_accuracy": <int 1-10>,
    "depth_of_analysis": <int 1-10>,
    "source_quality": <int 1-10>,
    "coverage_breadth": <int 1-10>,
    "analytical_rigor": <int 1-10>
  },
  "strengths": ["<strength 1>", "<strength 2>", ...],
  "weaknesses": ["<weakness 1>", "<weakness 2>", ...],
  "suggestions": ["<specific improvement 1>", "<specific improvement 2>", ...],
  "critique": "<2-3 paragraph detailed critique explaining the scores>"
}

Be specific in your critique. Vague feedback like "could be better" is useless.
Point to specific claims, sections, or gaps. Your feedback will be used to
iteratively improve this report.
```

### Improvement Prompt

```markdown
# Research Report Improvement -- Round {round_num}

You previously wrote a research report. An independent AI agent has evaluated it
and provided detailed feedback. Your job is to produce a STRICTLY BETTER version.

## Research Topic
{topic}

## Your Current Report
{current_report}

## Judge's Feedback

### Overall Score: {score}/10

### Dimension Scores
- Factual Accuracy: {factual_accuracy}/10
- Depth of Analysis: {depth_of_analysis}/10
- Source Quality: {source_quality}/10
- Coverage Breadth: {coverage_breadth}/10
- Analytical Rigor: {analytical_rigor}/10

### Strengths
{strengths}

### Weaknesses
{weaknesses}

### Specific Suggestions
{suggestions}

### Detailed Critique
{critique}

## Your Task

Produce an improved version of your research report that:

1. **Addresses every weakness** the judge identified
2. **Preserves every strength** -- don't regress on what's already good
3. **Follows every specific suggestion** where feasible
4. **Conducts NEW web research** to fix flagged errors, fill coverage gaps, find stronger sources, deepen shallow analysis
5. **Does not pad or bloat** -- higher information density, not more words

Write the complete improved report as a standalone document. Do not reference
the judge or this improvement process in the output.
```

### Adversarial Synthesis Prompt

```markdown
# Research Synthesis (Adversarial)

2 AI agents independently researched a topic, then each report was iteratively
optimized through {total_rounds} rounds of adversarial evaluation by the opposing
agent. You have both optimized reports below.

## Topic
{topic_content}

## Optimized Report A ({agent_a}, scored {score_a}/10 by {agent_b})
{optimized_report_a}

## Optimized Report B ({agent_b}, scored {score_b}/10 by {agent_a})
{optimized_report_b}

## Your Task

Synthesize both optimized reports into a comprehensive final report:

1. **Executive Summary** -- most important findings across both investigations
2. **Key Findings** -- organized by THEME, combining strongest evidence from both
3. **Areas of Consensus** -- where both agents converged after optimization
4. **Areas of Disagreement** -- where agents still differ, with analysis of which view is better supported
5. **Novel Insights** -- unique findings from the adversarial optimization process
6. **Open Questions** -- what remains uncertain even after iterative refinement
7. **Sources** -- comprehensive, deduplicated list of all URLs and references
8. **Methodology** -- brief description of the adversarial optimization process

Be thorough. This is the final deliverable.
```

### Prompt Builder Signatures

| Function | Inputs | Output |
|----------|--------|--------|
| `build_judging_prompt` | `topic: str, candidate_report: str` | Formatted judging template |
| `build_improvement_prompt` | `topic: str, current_report: str, judge_feedback: dict, round_num: int` | Formatted improvement template |
| `build_adversarial_synthesis_prompt` | `topic: str, agent_a: str, optimized_report_a: str, score_a: float, agent_b: str, optimized_report_b: str, score_b: float, total_rounds: int` | Formatted synthesis template |
| `_format_list` | `items: list[str]` | `"- (none provided)"` if empty, else `"- item"` per line |

## Helper Function Contracts

| Function | Signature | Returns | Edge Cases |
|----------|-----------|---------|------------|
| `parse_judge_output` | `(judging_dir: Path) -> tuple[float, dict]` | `(score, asi_dict)` where asi has keys: `dimensions`, `strengths`, `weaknesses`, `suggestions`, `critique` | Empty dir: `(0.0, {"error": ...})`. Invalid JSON: `(0.0, {"error": ..., "raw_output": ...})`. Score clamped to [0, 10]. |
| `_extract_json_from_markdown` | `(text: str) -> str \| None` | JSON string or `None` | Tries ` ```json ``` ` block first, then raw `{...}` object, then `None`. |
| `extract_feedback_from_reflective_dataset` | `(reflective_dataset: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict` | Dict with keys: `score`, `dimensions`, `strengths`, `weaknesses`, `suggestions`, `critique` | Empty dataset: returns zero/empty defaults. Reads most recent entry (last in sequence). |
| `read_counselors_output` | `(output_dir: Path, agent: str) -> str` | Agent's output text | Checks `<slug_dir>/<agent>.md` first, falls back to any `.md` file. Raises `FileNotFoundError` if nothing found. |
| `_save_optimization_log` | `(self, run_dir: Path, agent: str, result) -> None` | Writes JSON to `phase2/<agent>-optimization-log.json` | Extracts score history from GEPA result's `history` attribute. |

## Optimization Log Schema

```json
{
  "agent": "claude-opus",
  "judge": "codex-5.3-xhigh",
  "seed_score": 5.2,
  "final_score": 8.3,
  "rounds": 10,
  "score_history": [
    {"round": 1, "score": 5.2, "dimensions": {"factual_accuracy": 5, "depth_of_analysis": 6, "source_quality": 4, "coverage_breadth": 5, "analytical_rigor": 6}},
    {"round": 2, "score": 6.1, "dimensions": {"factual_accuracy": 6, "depth_of_analysis": 7, "source_quality": 5, "coverage_breadth": 6, "analytical_rigor": 7}}
  ],
  "best_round": 8,
  "improvement": "+3.1 (5.2 -> 8.3)"
}
```

## Manifest Examples

### Council (backward compatible with v1)

```json
{
  "run_id": "20260301-143000-a1b2c3",
  "strategy": "council",
  "topic": "...",
  "agents": ["claude-opus", "codex-5.3-xhigh"],
  "synthesizer": "claude-opus",
  "flags": {"raw": false, "instructions": null, "verbose": false, "max_rounds": 10},
  "phases": {
    "research": { "status": "complete", "...": "same as v1" },
    "cross_pollination": { "status": "complete", "...": "same as v1" },
    "synthesis": { "status": "complete", "...": "same as v1" }
  },
  "total_duration_seconds": 500
}
```

### Adversarial

```json
{
  "run_id": "20260301-143000-a1b2c3",
  "strategy": "adversarial",
  "topic": "...",
  "agents": ["claude-opus", "codex-5.3-xhigh"],
  "synthesizer": "claude-opus",
  "flags": {"raw": false, "instructions": null, "verbose": false, "max_rounds": 10},
  "phases": {
    "seed_generation": {
      "status": "complete",
      "started_at": "2026-03-01T14:30:00Z",
      "completed_at": "2026-03-01T14:35:00Z",
      "duration_seconds": 300,
      "agents": {
        "claude-opus": {"status": "complete", "duration_seconds": 280, "output": "phase1/claude-opus-seed.md"},
        "codex-5.3-xhigh": {"status": "complete", "duration_seconds": 300, "output": "phase1/codex-5.3-xhigh-seed.md"}
      }
    },
    "adversarial_optimization": {
      "status": "complete",
      "started_at": "2026-03-01T14:35:00Z",
      "completed_at": "2026-03-01T14:45:00Z",
      "duration_seconds": 600,
      "seeds": {
        "claude-opus": {
          "status": "complete",
          "judge": "codex-5.3-xhigh",
          "rounds_completed": 10,
          "seed_score": 5.2,
          "final_score": 8.3,
          "output": "phase2/claude-opus-optimized.md",
          "log": "phase2/claude-opus-optimization-log.json"
        },
        "codex-5.3-xhigh": {
          "status": "complete",
          "judge": "claude-opus",
          "rounds_completed": 10,
          "seed_score": 4.8,
          "final_score": 7.9,
          "output": "phase2/codex-5.3-xhigh-optimized.md",
          "log": "phase2/codex-5.3-xhigh-optimization-log.json"
        }
      }
    },
    "synthesis": {
      "status": "complete",
      "started_at": "2026-03-01T14:45:00Z",
      "completed_at": "2026-03-01T14:47:00Z",
      "duration_seconds": 120,
      "agent": "claude-opus",
      "output": "phase3/final-report.md"
    }
  },
  "total_duration_seconds": 1020
}
```

## CLI Interface

```
ivory research <topic>
    --strategy         council | adversarial (default: council)
    --agents, -a       Comma-separated agent IDs (required)
    --synthesizer, -s  Agent ID for synthesis (required)
    --file, -f         Read topic from markdown file
    --instructions, -i Append instructions to auto-generated prompt
    --raw              Send topic as-is (no prompt wrapping)
    --output-dir, -o   Override default output directory
    --verbose, -v      Stream agent logs to terminal
    --dry-run          Show plan without executing
    --json             Output manifest as JSON on completion
    --max-rounds       Max optimization rounds per seed (adversarial only, default: 10)

ivory resume <run-dir>
    --verbose, -v

ivory status <run-dir>
    Delegates to strategy.format_status()

ivory list
    Shows strategy name in table output

ivory strategies
    List available strategies with descriptions
```

## pyproject.toml Changes

```toml
[project]
dependencies = [
    "typer>=0.15",
    "rich>=13",
]

[project.optional-dependencies]
adversarial = ["gepa>=0.1.0"]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "gepa>=0.1.0",
]
```

## Error Handling

| Condition | Behavior |
|-----------|----------|
| `gepa` not installed + `--strategy adversarial` | Print `"The adversarial strategy requires the gepa package. Install with: uv add gepa"`, exit 1 |
| `--max-rounds` with `--strategy council` | Warning printed, flag ignored |
| `--agents` with != 2 agents + `--strategy adversarial` | `"Adversarial strategy requires exactly 2 agents, got N"`, exit 1 |
| `--strategy unknown` | `"Unknown strategy 'unknown'. Available: council, adversarial"`, exit 1 |
| GEPA `optimize_anything` raises | Save `result.best_candidate` if available, fall back to seed, mark phase `PARTIAL`, continue to synthesis |
| Judge returns unparseable JSON | Score 0.0, ASI includes raw output |
| One seed optimization fails completely | Synthesize from optimized report + original seed of failed agent |
| `counselors` not on PATH | Print install instructions, exit 1 |
| Resume adversarial run | Read `"strategy": "adversarial"` from manifest, dispatch to `AdversarialStrategy.resume()` |
| Resume v1 manifest (no strategy field) | Default to `"council"`, dispatch to `CouncilStrategy.resume()` |

---

# Commit Plan

See [HOW](#how) for worktree setup, TDD workflow, merge process, and test conventions.

### Commit 1: Strategy protocol + registry + `ivory strategies`

**RED:**
- `get_strategy("council")` returns CouncilStrategy instance
- `get_strategy("unknown")` raises ValueError
- `list_strategies()` returns `[(name, description)]`
- `ivory strategies` prints available strategies

**GREEN:**
- `strategies/__init__.py` -- registry
- `strategies/base.py` -- `ResearchStrategy` Protocol
- `strategies/council.py` -- stub with `name` and `description` only
- `cli.py` -- `ivory strategies` command

**Commit:** `feat: add strategy protocol, registry, and ivory strategies command`

---

### Commit 2: Extract CouncilStrategy from engine.py

**RED:**
- `validate()` rejects < 2 agents, rejects missing synthesizer, returns `[]` for valid config
- `create_manifest()` produces council-shaped manifest with `strategy="council"`
- `run()` calls phase1/2/3 in order (mocked)
- `resume()` skips completed phases
- `dry_run()` prints plan without executing
- `format_status()` returns 3 tuples

**GREEN:**
- Move phase functions into `strategies/council.py` (or import -- implementer's choice)
- Implement all `ResearchStrategy` methods on `CouncilStrategy`

**Regression:** All existing `test_engine.py` tests still pass.

**Commit:** `refactor: extract CouncilStrategy from engine, all v1 tests pass`

---

### Commit 3: Engine dispatcher + RunConfig changes + Manifest strategy field

**RED:**
- `run_pipeline(strategy="council")` delegates to CouncilStrategy
- `run_pipeline(strategy="unknown")` raises ConfigError
- `resume_pipeline()` reads strategy from manifest
- `Manifest.to_dict()` includes `"strategy"`, `from_dict()` reads it (defaults `"council"`)
- `Flags` gains `max_rounds` (default 10), backward compat on deserialize
- `PhaseStatus.PARTIAL` exists
- `RunConfig` has `strategy` and `max_rounds`

**GREEN:**
- `models.py`: add fields, backward compat in `from_dict()`
- `engine.py`: simplify to delegate to strategy

**Regression:** `ivory research` with no `--strategy` works identically.

**Commit:** `feat: engine dispatches to strategy, manifest gains strategy field with v1 backward compat`

---

### Commit 4: CLI -- `--strategy` and `--max-rounds` flags

**RED:**
- `--strategy council` / `--strategy adversarial` / `--strategy unknown` parsed correctly
- `--max-rounds 5` parsed into RunConfig
- `ivory status` shows strategy name, delegates to `format_status`
- `ivory list` shows strategy column
- Resume reads strategy from manifest

**GREEN:**
- `cli.py`: add flags, update `status`/`list`/`resume`

**Commit:** `feat: CLI gains --strategy, --max-rounds flags; status/list are strategy-aware`

---

### Commit 5: Adversarial prompt templates + builders

**RED:**
- `build_judging_prompt(topic, report)` returns string containing topic and report
- `build_improvement_prompt(topic, report, feedback, round)` returns string with all feedback fields
- `build_adversarial_synthesis_prompt(...)` returns string with both reports and scores
- `_format_list([])` returns `"- (none provided)"`; `_format_list(["a", "b"])` returns `"- a\n- b"`

**GREEN:**
- `prompts.py`: add templates and builder functions

**Commit:** `feat: add judging, improvement, and adversarial synthesis prompt templates`

---

### Commit 6: Adversarial helper functions

**RED:**
- `_extract_json_from_markdown`: extracts from fenced blocks, raw JSON, returns None for no JSON
- `parse_judge_output`: valid dir -> (score, asi); empty dir -> (0.0, error); invalid JSON -> (0.0, error); clamps [0, 10]
- `extract_feedback_from_reflective_dataset`: populated -> extracted; empty -> defaults
- `read_counselors_output`: reads from slug subdir; raises FileNotFoundError when empty

**GREEN:**
- `strategies/adversarial.py`: implement all helpers

**Commit:** `feat: adversarial helper functions for judge parsing, feedback extraction, output reading`

---

### Commit 7: Adversarial model dataclasses + manifest serialization

**RED:**
- `SeedOptimizationResult` and `AdversarialOptimizationPhase` create with expected fields
- Adversarial manifest `to_dict()` / `from_dict()` roundtrip correctly
- `format_status()` returns adversarial phase labels

**GREEN:**
- `models.py`: add dataclasses
- Strategy-aware serialization via `phases_to_dict` / `phases_from_dict`

**Commit:** `feat: adversarial model dataclasses and manifest serialization`

---

### Commit 8: AdversarialStrategy -- validate, create_manifest, dry_run, resume, format_status

**RED:**
- `validate()` rejects != 2 agents, missing synthesizer, missing gepa (mock import failure)
- `validate()` returns `[]` for valid 2-agent config
- `create_manifest()` produces adversarial-shaped manifest
- `dry_run()` prints adversarial plan
- `resume()` skips completed phases
- `format_status()` returns adversarial labels

**GREEN:**
- `strategies/adversarial.py`: implement all non-run methods

**Commit:** `feat: AdversarialStrategy validation, manifest creation, dry run, resume, status`

---

### Commit 9: AdversarialStrategy.run() -- full pipeline

**RED:**
- `run()` calls seed generation for both agents (mock counselors)
- `run()` calls `optimize_anything` twice (mock GEPA)
- Evaluator and proposer shell out to counselors correctly
- Optimized reports saved to correct paths
- Optimization logs saved
- Synthesis called with both optimized reports
- Correct manifest state on success
- Graceful degradation: GEPA failure falls back to seed, one seed failing uses original, bad judge JSON -> score 0

**GREEN:**
- `strategies/adversarial.py`: implement `run()`, `_build_evaluator()`, `_build_proposer()`, `_optimize_seed()`

**Commit:** `feat: AdversarialStrategy.run() with GEPA integration, evaluator, proposer`

---

### Commit 10: End-to-end integration tests

**Tests:**
- Full council pipeline with mocked counselors
- Full adversarial pipeline with mocked counselors + GEPA
- `ivory resume` on partial adversarial run
- `ivory status` / `ivory list` / `ivory strategies` for adversarial
- `--dry-run --strategy adversarial`
- Backward compat: resume a v1 manifest (no strategy field)

**Full suite:** `uv run pytest tests/ -v`

**Commit:** `test: end-to-end integration tests for both strategies + backward compat`

---

### Commit 11: Final cleanup

- Remove dead code from `engine.py` moved to strategies
- Clean `__init__.py` exports
- `uv run pytest tests/ -v`

**Commit:** `chore: remove dead code from engine.py, clean exports`


