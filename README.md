# ivory-tower

Multi-agent deep research from the terminal.

Orchestrates [counselors](https://github.com/anomalyco/counselors) agents to research a topic in parallel, challenge each other's work, and synthesize a final report.

Five strategies. **Council** and **adversarial** are battle-tested. **Debate**, **map-reduce**, and **red-blue** are implemented via the YAML template engine but not yet live-tested.

#### Council

Each agent researches independently, then skeptically cross-reviews every peer's report through new web searches, then a synthesizer merges the refined reports.

```mermaid
graph TD
    T((Topic)) --> A[Agent A] & B[Agent B] & C[Agent C]

    subgraph "Phase 1 · Independent Research"
        A --> RA[Report A]
        B --> RB[Report B]
        C --> RC[Report C]
    end

    subgraph "Phase 2 · Cross-Pollination"
        RA & RB & RC --> XA[A reviews B + C] & XB[B reviews A + C] & XC[C reviews A + B]
        XA --> RA2[Refined A]
        XB --> RB2[Refined B]
        XC --> RC2[Refined C]
    end

    subgraph "Phase 3 · Synthesis"
        RA2 & RB2 & RC2 --> SYN[Synthesizer]
        SYN --> FR((Final Report))
    end
```

#### Adversarial

Two agents produce seed reports, then two parallel [GEPA](https://github.com/anomalyco/gepa) optimization loops run -- each agent iteratively improves its own report while the opposing agent scores it. A synthesizer merges the two battle-tested reports.

```mermaid
graph TD
    T((Topic)) --> A1[Agent A] & B1[Agent B]

    subgraph "Phase 1 · Seed Generation"
        A1 --> SA[Seed A]
        B1 --> SB[Seed B]
    end

    subgraph "Phase 2 · Adversarial Optimization"
        SA --> JA{B judges A}
        JA -- feedback --> IA[A improves]
        IA --> JA

        SB --> JB{A judges B}
        JB -- feedback --> IB[B improves]
        IB --> JB
    end

    JA -. best .-> OA[Optimized A]
    JB -. best .-> OB[Optimized B]

    subgraph "Phase 3 · Synthesis"
        OA & OB --> SYN[Synthesizer]
        SYN --> FR((Final Report))
    end
```

---

### Installation

```bash
# requires: python 3.12+, uv, counselors
uv tool install ivory-tower

# with adversarial strategy support (GEPA)
uv tool install "ivory-tower[adversarial]"
```

### Quick start

```bash
# council (default) -- 3 agents research, cross-review, then synthesize
ivory research "state of WebAssembly in 2026" \
  -a claude-opus,codex-5.3-xhigh,amp-deep \
  -s claude-opus

# adversarial -- 2 agents produce seed reports, iteratively optimize via GEPA judging
ivory research "state of WebAssembly in 2026" \
  --strategy adversarial \
  -a claude-opus,codex-5.3-xhigh \
  -s claude-opus \
  --max-rounds 5

# read topic from file, pipe from stdin
ivory research -f topic.md -a claude-opus,codex-5.3-xhigh -s claude-opus
cat topic.md | ivory research -a claude-opus,codex-5.3-xhigh -s claude-opus
```

### Strategies

| Strategy | Agents | Status | Description |
|----------|--------|--------|-------------|
| **council** | 2+ | stable | Independent research, skeptical cross-review, synthesis |
| **adversarial** | 2 | stable | Iterative optimization scored by opposing agent via [GEPA](https://github.com/anomalyco/gepa) |
| **debate** | 2-6 | alpha | Turn-based argumentation with shared blackboard transcript |
| **map-reduce** | 2-20 | alpha | Decompose topic into subtopics, one agent per subtopic, merge |
| **red-blue** | 3-10 | alpha | Red team critiques, blue team defends, synthesizer reconciles |

> Council and adversarial have custom Python implementations and have been live-tested. Debate, map-reduce, and red-blue run through the `GenericTemplateExecutor` (YAML-driven) and have unit/integration tests but no live runs yet.

Strategies are defined as YAML templates. Drop a `.yml` in `~/.ivory-tower/strategies/` to create your own, or pass `--template path/to/strategy.yml`.

### Commands

```
ivory research TOPIC [OPTIONS]    Run a research pipeline
ivory resume   RUN_DIR            Resume a partially-completed run
ivory status   RUN_DIR            Print status summary
ivory list                        List all runs in output directory
ivory strategies                  List available strategies
ivory templates                   List strategy templates
ivory profiles                    List agent profiles
ivory audit    RUN_DIR [AGENT]    Query sandbox audit trail
```

### Options

| Flag | Short | Description |
|------|-------|-------------|
| `--agents` | `-a` | Comma-separated agent IDs (required) |
| `--synthesizer` | `-s` | Agent ID for final synthesis (required) |
| `--strategy` | | Strategy name (default: `council`) |
| `--template` | `-t` | Strategy template (built-in name or YAML path) |
| `--file` | `-f` | Read topic from a file |
| `--instructions` | `-i` | Append custom instructions to the prompt |
| `--raw` | | Send topic as-is with no prompt wrapping |
| `--output-dir` | `-o` | Override output directory (default: `./research`) |
| `--max-rounds` | | Max GEPA optimization rounds (adversarial, default: 10) |
| `--rounds` | | Number of rounds for iterative phases |
| `--sandbox` | | Sandbox backend: `none`, `local`, `agentfs`, `daytona` |
| `--red-team` | | Agent specs for red team (red-blue strategy) |
| `--blue-team` | | Agent specs for blue team (red-blue strategy) |
| `--dry-run` | | Show the execution plan without running |
| `--json` | | Print manifest JSON on completion |
| `--verbose` | `-v` | Rich logging with animated spinners and debug output |

### Agent profiles

Reusable agent identities stored as YAML in `~/.ivory-tower/profiles/`:

```yaml
# ~/.ivory-tower/profiles/deep-researcher.yml
model: claude-opus
role: researcher
system_prompt: "You are a thorough researcher..."
```

Reference profiles on the CLI with `@name`:

```bash
ivory research "topic" -a @deep-researcher,@fast-scanner -s claude-opus
```

```bash
ivory profiles           # list all profiles
```

### Sandboxing

Agent isolation for template-based strategies (debate, map-reduce, red-blue). Four backends:

| Backend | Requires | Description |
|---------|----------|-------------|
| `none` | nothing | No isolation (default) |
| `local` | nothing | Directory-based isolation per agent |
| `agentfs` | [agentfs](https://agentfs.ai) CLI | SQLite copy-on-write filesystem with encryption and audit trail |
| `daytona` | [daytona](https://daytona.io) SDK | Full Docker container isolation with resource limits |

```bash
ivory research "topic" --template debate -a a,b,c -s a --sandbox local
```

> Sandbox support is wired into the template executor used by debate, map-reduce, and red-blue. Council and adversarial use direct filesystem paths and currently ignore `--sandbox`.

### Output

Each run produces a self-contained directory:

```
./research/20260301-143000-a1b2c3/
    manifest.json          # run metadata, timing, status
    topic.md               # original topic
    research-prompt.md     # generated prompt
    phase1/                # initial research / seed reports
    phase2/                # cross-review / optimization artifacts
    phase3/final-report.md # synthesized report
```

### Logging

All pipeline output flows through a single logging system built on Python's `logging` module with [Rich](https://github.com/Textualize/rich) rendering. Call `setup_logging()` once at CLI startup; every module then uses `logging.getLogger(__name__)`.

#### Architecture

```
src/ivory_tower/log.py          # shared console, symbols, formatters, spinners
    console                     # Rich Console(theme=_THEME, stderr=True)
    setup_logging()             # configures root logger with RichHandler
    fmt_phase / fmt_ok / ...    # markup formatters
    phase_spinner()             # context-manager spinner with auto-duration
    create_agent_progress()     # multi-agent progress bar
```

All logging goes to stderr via the shared themed `Console`. The `RichHandler` renders timestamps, levels, and Rich markup automatically. Third-party loggers (httpx, openai, anthropic, etc.) are quietened to WARNING.

#### Visual Language

Every strategy follows the same visual pattern:

```
[HH:MM:SS] INFO  ▶ Research Pipeline                    # engine header
[HH:MM:SS] INFO    ▸ Strategy: council
[HH:MM:SS] INFO    ▸ Agents: agent-a, agent-b
[HH:MM:SS] INFO    ▸ Synthesizer: synth
[HH:MM:SS] INFO    ▸ Topic: "..."
[HH:MM:SS] INFO    ▸ Run ID: 20260301-...

[HH:MM:SS] INFO  ▶ Phase 1 -- Independent Research      # phase header
[HH:MM:SS] INFO    ▸ Agents: agent-a, agent-b
              ▸ Agents researching: agent-a, agent-b     # animated spinner
              ✔ Agents researching: agent-a, agent-b (45.2s)
[HH:MM:SS] INFO    ▸ Counselors session complete, normalizing output
[HH:MM:SS] INFO  ✔ Phase 1 complete (45.2s)             # phase footer

[HH:MM:SS] INFO  ▶ Phase 2 -- Cross-Pollination
[HH:MM:SS] INFO    ▸ 2 agents refining reports concurrently
              agent-a refining... ████████████ 0:00:32   # progress bar
              ✔ agent-a refined (32.1s)
              ✔ agent-b refined (28.7s)
[HH:MM:SS] INFO  ✔ Phase 2 complete (32.1s)

[HH:MM:SS] INFO  ▶ Phase 3 -- Synthesis
[HH:MM:SS] INFO    ▸ Synthesizer: synth combining 2 refined reports
              ▸ Synthesizer synth working...
              ✔ Synthesizer synth working... (18.0s)
[HH:MM:SS] INFO  ✔ Phase 3 complete (18.0s) -- final report: 14832 bytes

[HH:MM:SS] INFO  ✔ Council pipeline complete (1m 35s)   # pipeline footer
```

#### Per-Strategy Logging

| Strategy | Pipeline Header | Phase Headers | Step Detail | Spinners/Progress | Phase Footers | Pipeline Footer |
|----------|----------------|---------------|-------------|-------------------|---------------|-----------------|
| **council** | `run()` | Each `_run_phase{1,2,3}` | Agent lists, normalization | `phase_spinner`, `create_agent_progress` | Duration per phase | Duration total |
| **adversarial** | `_run_adversarial_optimization` | Each `_run_*` method | Per-round scores, feedback, optimization progress | `phase_spinner` per judge/improve/optimize | Duration per phase | Duration total |
| **debate** | `run()` | `GenericTemplateExecutor` per phase | Agent lists, isolation mode, round counts | `phase_spinner` per agent turn | Duration per phase | Duration total |
| **map-reduce** | `run()` | `GenericTemplateExecutor` per phase | Agent lists, isolation mode, concurrency | `phase_spinner` for single-agent phases | Duration per phase | Duration total |
| **red-blue** | `run()` | `GenericTemplateExecutor` per phase | Team assignments, isolation mode | `phase_spinner` per agent turn | Duration per phase | Duration total |

Council and adversarial have custom Python logging at each step. Debate, map-reduce, and red-blue delegate phase execution to `GenericTemplateExecutor`, which logs phase headers/footers, round progress, agent dispatch, and timing for every phase defined in their YAML templates.

#### Log Levels

- `INFO` -- phase boundaries, scores, timing, completion messages. Visible by default.
- `DEBUG` -- JSON extraction strategies, proposer/evaluator internals, round-level file paths. Enable with `--verbose` / `-v`.
- `WARNING` -- parse failures, score 0.0 warnings, missing agent output, fallback paths.
- `ERROR` -- optimization failures with full tracebacks (when verbose).

#### Symbols

| Symbol | Name | Usage |
|--------|------|-------|
| `▶` | `SYM_PHASE` | Phase headers |
| `✔` | `SYM_OK` | Success / completion |
| `✘` | `SYM_FAIL` | Failure |
| `▸` | `SYM_ARROW` | Bullet / step detail |
| `★` | `SYM_SCORE` | Score display |
| `⟳` | `SYM_ROUND` | Round markers |
| `✦` | `SYM_SPARK` | Highlights |

#### Theme

Rich markup tags used in log messages:

| Tag | Style | Usage |
|-----|-------|-------|
| `[phase]` | bold cyan | Phase names, strategy headers |
| `[agent]` | bold magenta | Agent names |
| `[score]` | bold yellow | Scores, ratings |
| `[ok]` | bold green | Success markers |
| `[warn]` | bold yellow | Warnings |
| `[fail]` | bold red | Failures |
| `[dim]` | dim | Secondary info (run IDs, paths, topic previews) |
| `[duration]` | cyan | Timing values |

### Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- [counselors](https://github.com/anomalyco/counselors) installed and configured with at least 2 agents
- [gepa](https://github.com/anomalyco/gepa) for the adversarial strategy (`uv tool install "ivory-tower[adversarial]"`)

### Inspired by

[hamelsmu/research-council](https://github.com/hamelsmu/research-council) · [counselors](https://github.com/anomalyco/counselors) · [GEPA](https://github.com/anomalyco/gepa) · [clig.dev](https://clig.dev/)
