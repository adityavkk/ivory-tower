# AGENTS.md -- ivory-tower

Multi-agent deep research orchestrator. Python CLI (`ivory`) coordinating AI coding agents via external `counselors` CLI, with optional direct LLM execution via litellm. Orchestrator only -- never an agent runtime.

## What This Is

Ivory-tower dispatches N agents to research a topic in parallel, challenges them against each other, and synthesizes a final report. Five strategies: council (3-phase), adversarial (GEPA optimization), debate, map-reduce, red-blue. YAML template system for declarative strategy definitions. Pluggable sandbox providers for agent isolation.

## Current Focus

New features + multi-agent harness with sandboxes/blackboards for isolated agent interaction (active worktree branch). The current `sandbox/` and `templates/` code is being **replaced** by this new system. Adversarial strategy has known issues tracked in `spec/FIXES.md` (issues 11-16); some fixed, some open.

## Tech Stack

- Python 3.12+ (`from __future__ import annotations` everywhere; match/case; `X | Y` unions)
- CLI: typer >= 0.15; Terminal UI: rich >= 13; YAML: PyYAML >= 6
- Build: hatchling (`src/` layout); Package manager: uv
- Testing: pytest >= 8, pytest-asyncio >= 0.24
- External: `counselors` CLI (third-party, WIP -- API may shift); `gepa` (third-party, treat as black box)
- Optional: litellm (DirectExecutor), agentfs (Rust CLI, SQLite CoW sandbox), daytona (Docker sandbox)

## Project Layout

```
src/ivory_tower/
  cli.py              # typer entry point; all commands
  engine.py           # RunConfig + pipeline dispatch
  models.py           # dataclasses: Manifest, phases, serialization
  prompts.py          # all prompt templates + builders
  counselors.py       # counselors CLI wrapper (resolve binary, run, validate)
  log.py              # rich logging, spinners, formatters
  run.py              # run ID generation + directory setup
  executor/           # AgentExecutor Protocol; counselors_exec, direct
  profiles/           # AgentProfile loading from ~/.ivory-tower/profiles/
  sandbox/            # SandboxProvider Protocol; null, local, agentfs, daytona, blackboard
  strategies/         # ResearchStrategy Protocol; council, adversarial, debate, map_reduce, red_blue
  templates/          # YAML strategy templates; loader + GenericTemplateExecutor
  data/strategies/    # bundled .yml templates (council, adversarial, debate, map-reduce, red-blue)
spec/                 # specs + known issues
  SPEC.md             # v1: 3-phase pipeline
  STRATEGY-SPEC.md    # v2: strategy abstraction + adversarial
  SANDBOX-SPEC.md     # v3: pluggable sandboxing
  FIXES.md            # adversarial strategy known issues (11-16)
tests/                # mirrors source; 26 test files
research/             # output from real runs (disposable)
```

## Commands

```bash
ivory research "topic" -a agent1,agent2 -s synthesizer     # council (default)
ivory research "topic" --strategy adversarial -a a,b -s a   # adversarial
ivory research "topic" --strategy adversarial --executor direct --model openai/claude-haiku-4-5 -a a,b -s a
ivory research "topic" --template debate -a a,b -s a        # YAML template
ivory resume <run-dir>                                       # resume partial
ivory status <run-dir>                                       # show status
ivory list                                                   # list runs
ivory strategies / templates / profiles / audit              # introspection
```

## Build / Test / Run

```bash
uv tool install ivory-tower                         # standard install
uv tool install "ivory-tower[adversarial]"          # with GEPA
uv tool install "ivory-tower[direct]"               # with direct executor (litellm)
uv run pytest tests/ -x -v                          # mocked tests (excludes @live)
uv run pytest tests/ -m live -v -s                  # live e2e (calls real agents)
uv run pytest tests/test_sandbox_integration.py     # sandbox integration
```

Entry point: `ivory = ivory_tower.cli:app`

## Architecture Patterns

| Pattern | Where | Notes |
|---------|-------|-------|
| Strategy | `strategies/` | `ResearchStrategy` Protocol; 5 implementations; runtime registry |
| Protocol typing | `sandbox/types.py`, `executor/types.py`, `strategies/base.py` | `@runtime_checkable`; no ABCs |
| Registry | `strategies/__init__.py`, `sandbox/__init__.py`, `executor/__init__.py` | `dict[str, type]` + `get_*()` factory |
| Template method | `templates/executor.py` | YAML-defined phase sequencing |
| Orchestrator-mediated IO | `sandbox/blackboard.py`, `templates/executor.py` | Agents never write shared state directly |
| Concurrent execution | `strategies/council.py`, `strategies/adversarial.py` | `ThreadPoolExecutor` + `as_completed` |

## Fragile Areas -- Tread Carefully

- **`strategies/adversarial.py`** (~1300 lines): most complex file. GEPA integration, 5 JSON extraction strategies, score parsing from prose, feedback extraction. Known open issues in `spec/FIXES.md`.
- **Counselors output parsing**: `counselors` is third-party WIP. Output structure (`<slug>/<agent>.md`) may contain conversational meta-commentary instead of actual report artifacts. The `_find_best_report_file()` heuristic and `_normalize_counselors_output()` compensate for this. Any changes here need defensive handling.

## Counselors Output Structure

```
<output_dir>/
  <slug>/
    prompt.md           # input prompt copy
    run.json            # metadata (timestamp, tools, duration, wordCount, outputFile)
    summary.md          # human-readable summary
    <agent>.md          # agent's conversational/session output
    <agent>.stderr      # stderr
    [extra files]       # agents may write additional files via file-write tools
```

The `{agent}.md` is conversational output -- NOT necessarily the artifact. Real reports may be in separate files (e.g., `research_report.md`). Heuristic: pick largest `.md` excluding `prompt.md`, `summary.md`.

## Code Conventions

- `from __future__ import annotations` in every file
- `logging.getLogger(__name__)` in every module
- dataclasses for all data types (no Pydantic)
- Protocols with `@runtime_checkable` for interfaces
- `match/case` for isolation mode dispatch
- Rich markup in log messages (`[agent]`, `[phase]`, `[score]`)
- Files < ~500 LOC; split/refactor as needed
- Test files mirror source: `test_{module}.py`
- `tmp_path` fixture for all file-based tests

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/private: `snake_case` / `_prefixed`
- Constants: `UPPER_SNAKE_CASE`

## Testing

- **Unit tests**: mock all external calls (`unittest.mock.patch`). Counselors, GEPA, filesystem -- everything mocked.
- **Live/integration tests**: marked `@pytest.mark.live`; call real agents; expected for integration verification.
- Default pytest run excludes live: `addopts = "-m 'not live'"`
- TDD: write failing tests first when building new features.

## Spec Format

New specs and feature designs use the WANT/DON'T/LIKE/FOR/ENSURE/TRUST format from the existing specs. Brief guide:

| Section | Purpose |
|---------|---------|
| **WANT** | What the feature does; functional requirements; behaviors |
| **DON'T** | Explicit non-goals; things to avoid; scope limits |
| **LIKE** | Inspirations; reference implementations; prior art |
| **FOR** | Target user; environment; domain; tech constraints |
| **ENSURE** | Acceptance criteria; testable assertions; CLI examples |
| **TRUST** | Assumptions; things delegated to external systems |

See `spec/SPEC.md`, `spec/STRATEGY-SPEC.md`, `spec/SANDBOX-SPEC.md` as templates.

## Git Workflow

- **Worktree branches**: feature branches developed in separate git worktrees. Create branch, add worktree, implement + test in worktree, merge back to main, remove worktree.
- Conventional commits: `feat|fix|refactor|build|ci|chore|docs|style|perf|test`
- Concise messages: 1-2 sentences. No collaborator attributions. No emojis.
- Commit working code incrementally.

## Domain Knowledge

Agents working on this codebase should research these concepts before diving in:
- Multi-agent debate/deliberation protocols
- GEPA (Generalized Evolutionary Prompt Adjustment) / `optimize_anything` API
- Copy-on-write filesystem sandboxing patterns
- Orchestrator-mediated vs. direct agent communication

## Rules

**NEVER:**
- Implement ad-hoc execution paths outside strategy/executor abstractions -- dispatch through `counselors` or the approved direct executor path
- Skip tests; disable tests instead of fixing them
- Commit code that doesn't pass `uv run pytest tests/ -x -v`
- Use `--no-verify` on commits
- Reimplement features from scratch without asking first
- Guess at counselors output format -- verify against real output or existing parsing code

**ALWAYS:**
- Match surrounding code style (consistency > external standards)
- Stop after 3 failed attempts and reassess
- Prefer end-to-end verify; if blocked, say what's missing
- Update plan docs as you go
- Run the full test suite before considering work done
