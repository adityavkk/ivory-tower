# ivory-tower

Multi-agent deep research from the terminal.

Orchestrates [counselors](https://github.com/anomalyco/counselors) to fan out research across multiple AI agents, have them challenge each other's work, then synthesize a final report. Ships with two strategies: **council** (collaborative cross-pollination) and **adversarial** (iterative optimization via [GEPA](https://github.com/anomalyco/gepa)).

---

### How it works

**Council** -- agents research independently, skeptically review each other's findings through new web searches, then a synthesizer merges everything into one report.

**Adversarial** -- two agents produce seed reports, then each report is iteratively improved while the opposing agent scores it. A synthesizer merges the two battle-tested reports.

```
council:       research --> cross-pollinate --> synthesize
adversarial:   seed --> optimize (GEPA loop) --> synthesize
```

### Installation

```bash
# requires: python 3.12+, uv, counselors
uv tool install ivory-tower

# with adversarial strategy support
uv tool install "ivory-tower[adversarial]"
```

### Quick start

```bash
# council strategy (default) -- 3 agents + synthesizer
ivory research "state of WebAssembly in 2026" \
  -a claude-opus,codex-5.3-xhigh,amp-deep \
  -s claude-opus

# adversarial strategy -- exactly 2 agents
ivory research "state of WebAssembly in 2026" \
  --strategy adversarial \
  -a claude-opus,codex-5.3-xhigh \
  -s claude-opus \
  --max-rounds 5
```

### Usage

```bash
ivory research TOPIC [OPTIONS]
ivory resume RUN_DIR [--verbose]
ivory status RUN_DIR
ivory list [--output-dir DIR]
ivory strategies
```

| Flag | Short | Description |
|------|-------|-------------|
| `--agents` | `-a` | Comma-separated agent IDs (required) |
| `--synthesizer` | `-s` | Agent ID for final synthesis (required) |
| `--strategy` | | `council` (default) or `adversarial` |
| `--file` | `-f` | Read topic from a file |
| `--instructions` | `-i` | Append custom instructions to the prompt |
| `--raw` | | Send topic as-is with no prompt wrapping |
| `--output-dir` | `-o` | Override output directory (default: `./research`) |
| `--max-rounds` | | Max GEPA optimization rounds (adversarial only, default: 10) |
| `--dry-run` | | Show the execution plan without running |
| `--json` | | Print manifest JSON on completion |
| `--verbose` | `-v` | Stream agent output to terminal |

### Examples

```bash
# read topic from file
ivory research -f topic.md -a claude-opus,codex-5.3-xhigh -s claude-opus

# pipe from stdin
cat topic.md | ivory research -a claude-opus,codex-5.3-xhigh -s claude-opus

# dry run
ivory research "topic" -a claude-opus,codex-5.3-xhigh -s claude-opus --dry-run

# resume an interrupted run
ivory resume ./research/20260301-143000-a1b2c3/

# check status
ivory status ./research/20260301-143000-a1b2c3/

# list all runs
ivory list
```

### Output

```
./research/20260301-143000-a1b2c3/
    manifest.json          # run metadata, timing, status
    topic.md               # original topic
    research-prompt.md     # generated prompt

    # council strategy
    phase1/                # independent research reports
    phase2/                # cross-pollination reports
    phase3/final-report.md

    # adversarial strategy
    phase1/                # seed reports
    phase2/                # optimized reports + judging artifacts
    phase3/final-report.md
```

### Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- [counselors](https://github.com/anomalyco/counselors) installed and configured with at least 2 agents
- [gepa](https://github.com/anomalyco/gepa) for the adversarial strategy (`pip install "ivory-tower[adversarial]"`)

### Architecture

```
ivory_tower/
    cli.py            # typer CLI
    engine.py         # pipeline dispatcher + RunConfig
    counselors.py     # counselors CLI wrapper
    models.py         # manifest, phase models
    prompts.py        # all prompt templates
    run.py            # run directory management
    strategies/
        base.py       # ResearchStrategy protocol
        __init__.py   # strategy registry
        council.py    # CouncilStrategy
        adversarial.py# AdversarialStrategy (GEPA integration)
```

Strategies implement the `ResearchStrategy` protocol (`validate`, `create_manifest`, `run`, `resume`, `dry_run`, `format_status`, `phases_to_dict`, `phases_from_dict`). New strategies are registered in `strategies/__init__.py`.

### Inspired by

- [hamelsmu/research-council](https://github.com/hamelsmu/research-council)
- [counselors](https://github.com/anomalyco/counselors)
- [GEPA](https://github.com/anomalyco/gepa)
- [clig.dev](https://clig.dev/)
