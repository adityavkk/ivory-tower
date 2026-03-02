# AGENTS.md -- ivory-tower

Multi-agent deep research orchestrator. Python CLI (`ivory`) coordinating AI coding agents via ACP (Agent Client Protocol), headless CLI modes, or the legacy `counselors` CLI. Orchestrator only -- never an agent runtime.

## What This Is

Ivory-tower dispatches N agents to research a topic in parallel, challenges them against each other, and synthesizes a final report. Five strategies: council (3-phase), adversarial (GEPA optimization), debate, map-reduce, red-blue. YAML template system for declarative strategy definitions. Pluggable sandbox providers for agent isolation.

## Current Status

ACP integration complete. All strategies (council, adversarial) use `AgentExecutor.run()` -- no direct `run_counselors()` calls remain. Counselors executor preserved as legacy fallback.

Adversarial strategy has known issues tracked in `spec/07-GEPA-FIXES.md`.

## Tech Stack

- Python 3.12+ (`from __future__ import annotations` everywhere; match/case; `X | Y` unions)
- CLI: typer >= 0.15; Terminal UI: rich >= 13; YAML: PyYAML >= 6
- ACP: agent-client-protocol >= 0.8 (Pydantic-based ACP Python SDK)
- Build: hatchling (`src/` layout); Package manager: uv
- Testing: pytest >= 8, pytest-asyncio >= 0.24
- External: `counselors` CLI (legacy, being superseded by ACP); `gepa` (third-party, treat as black box)
- Optional: litellm (DirectExecutor), agentfs (Rust CLI, SQLite CoW sandbox), daytona (Docker sandbox)

## Project Layout

```
src/ivory_tower/
  cli.py              # typer entry point; all commands (incl. `ivory agents`)
  engine.py           # RunConfig + pipeline dispatch
  models.py           # dataclasses: Manifest, phases, serialization
  prompts.py          # all prompt templates + builders
  agents.py           # AgentConfig dataclass, YAML loading from ~/.ivory-tower/agents/
  acp_client.py       # SandboxACPClient -- routes ACP tool calls through Sandbox
  counselors.py       # counselors CLI wrapper (legacy, kept for compat)
  log.py              # rich logging, spinners, formatters
  run.py              # run ID generation + directory setup
  executor/           # AgentExecutor Protocol + 4 implementations
    types.py          #   AgentExecutor Protocol, AgentOutput dataclass
    acp_exec.py       #   ACPExecutor -- ACP over stdio (Tier 1)
    headless_exec.py  #   HeadlessExecExecutor -- non-ACP headless CLIs (Tier 2)
    counselors_exec.py#   CounselorsExecutor -- legacy counselors wrapper
    direct.py         #   DirectExecutor -- raw litellm calls
    __init__.py       #   registry + get_executor() + get_executor_for_agent()
  profiles/           # AgentProfile loading from ~/.ivory-tower/profiles/
  sandbox/            # SandboxProvider Protocol; null, local, agentfs, daytona, blackboard
  strategies/         # ResearchStrategy Protocol; council, adversarial, debate, map_reduce, red_blue
  templates/          # YAML strategy templates; loader + GenericTemplateExecutor
  data/strategies/    # bundled .yml templates (council, adversarial, debate, map-reduce, red-blue)
spec/                 # specs + known issues
  01-SPEC.md          # v1: 3-phase pipeline
  02-STRATEGY-SPEC.md # v2: strategy abstraction + adversarial
  03-SANDBOX-SPEC.md  # v3: pluggable sandboxing
  04-FIXES.md         # adversarial strategy known issues (11-16)
  05-SANDBOX-FIXES.md # sandbox live testing issues
  06-ACP-SPEC.md      # v4: ACP-native agent invocation
  07-GEPA-FIXES.md    # GEPA integration gap analysis
tests/                # mirrors source; 33 test files
research/             # output from real runs (disposable)
```

## Commands

```bash
ivory research "topic" -a agent1,agent2 -s synthesizer     # council (default)
ivory research "topic" --strategy adversarial -a a,b -s a   # adversarial
ivory research "topic" --template debate -a a,b -s a        # YAML template
ivory resume <run-dir>                                       # resume partial
ivory status <run-dir>                                       # show status
ivory list                                                   # list runs
ivory agents                                                 # list configured agents
ivory agents check <name>                                    # verify agent binary + ACP
ivory strategies / templates / profiles / audit              # introspection
```

## Build / Test / Run

```bash
uv tool install ivory-tower                         # standard install
uv tool install "ivory-tower[adversarial]"          # with GEPA
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
| Orchestrator-mediated IO | `sandbox/blackboard.py`, `acp_client.py`, `templates/executor.py` | Agents never write shared state directly; ACP tool calls route through sandbox |
| Concurrent execution | `strategies/council.py`, `strategies/adversarial.py` | `ThreadPoolExecutor` + `as_completed` |
| Protocol-based routing | `executor/__init__.py` | `get_executor_for_agent()` selects executor from agent config's `protocol` field |

## Agent Invocation Tiers

Agents are invoked through the `AgentExecutor` protocol. The executor is selected based on the agent config's `protocol` field (`agents.py`, `executor/__init__.py`):

| Tier | Executor | Protocol field | How it works |
|------|----------|---------------|--------------|
| 1 | `ACPExecutor` (`executor/acp_exec.py`) | `acp` | Spawns agent as stdio subprocess via `acp.spawn_agent_process()`. Full ACP lifecycle: initialize, new_session, prompt, collect response. Tool calls routed through `SandboxACPClient` (`acp_client.py`). |
| 2 | `HeadlessExecExecutor` (`executor/headless_exec.py`) | `headless` | Runs agent CLI via `sandbox.execute()`. Parses output format (`text`, `stream-json`, `jsonl`) to extract response text. For Claude Code, Codex CLI, Aider, etc. |
| -- | `CounselorsExecutor` (`executor/counselors_exec.py`) | `counselors` | Legacy. Wraps `counselors run` subprocess. Filesystem-convention output parsing. |
| -- | `DirectExecutor` (`executor/direct.py`) | `direct` | Raw litellm API calls. No agent runtime. |

Agent configs live in `~/.ivory-tower/agents/<name>.yml`.

### Agent Config Format

```yaml
# ~/.ivory-tower/agents/opencode-fast-1.yml
name: opencode-fast-1
command: opencode
args: ["acp"]
protocol: acp
env:
  OPENCODE_CONFIG_CONTENT: '{"model": "wibey/claude-haiku-4-5-20251001"}'
```

Fields: `name` (must match filename), `command` (binary on PATH or absolute), `args` (CLI args), `protocol` (`acp`|`headless`|`counselors`|`direct`), `env` (supports `${VAR}` expansion), `output_format` (headless only: `text`|`json`|`jsonl`|`stream-json`). The `capabilities` field exists on `AgentConfig` but is not currently used by any executor.

### ACP Data Flow

Strategies never scrape the filesystem for agent output. The flow:

```
Strategy builds prompt (prompts.py templates)
  -> executor.run(sandbox, agent_name, prompt, output_dir)
    -> ACPExecutor spawns agent subprocess via spawn_agent_process()
    -> ACP lifecycle: initialize -> new_session -> prompt
    -> Agent runs (uses its own tools: webfetch, grep, etc.)
    -> Agent text streams back as AgentMessageChunk over stdio
    -> SandboxACPClient.accumulated_text collects all chunks
    -> client.get_full_text() -> AgentOutput.raw_output
  -> Strategy reads result.raw_output (in-memory string)
  -> Strategy writes canonical report to phase1/{agent}-report.md
  -> Next phase bakes prior reports into prompt template text
```

Agent file operations (readTextFile, writeTextFile, createTerminal) route through `SandboxACPClient` which enforces path traversal prevention and isolation modes. Agent's own tools (webfetch, glob, etc.) execute inside the agent process -- ivory-tower sees these as informational `tool_call_update` notifications only.

### Sandbox + ACP Integration

With `--sandbox local`, each agent gets an isolated workspace at `run_dir/sandboxes/{agent}/workspace/`. The `SandboxACPClient` enforces:

| Check | Where | What |
|-------|-------|------|
| Path traversal | `_resolve_sandbox_path()` | `Path.relative_to(workspace)` rejects `../../` escapes |
| Peer isolation | `_check_read_allowed()` | Blocks reads to `peers/` in `full` and `read-blackboard` modes |
| Blackboard isolation | `_check_read_allowed()` | Blocks reads to `blackboard/` in `full` and `read-peers` modes |
| Write restrictions | `_check_write_allowed()` | Blocks writes to `peers/` and `blackboard/` in all modes except `none` |
| Permissions | `request_permission()` | Policy-based: `auto-approve`, `reads-only`, `reject-all` |

The 10MB stdio buffer (`transport_kwargs={"limit": 10*1024*1024}`) in `acp_exec.py` is required because agent tool results (e.g., webfetch of large pages) produce JSON-RPC lines exceeding asyncio's default 64KB `StreamReader` limit.

## Fragile Areas -- Tread Carefully

- **`strategies/adversarial.py`** (~1300 lines): most complex file. GEPA integration, 5 JSON extraction strategies, score parsing from prose, feedback extraction. Known open issues in `spec/07-GEPA-FIXES.md`.
- **Legacy counselors executor**: `executor/counselors_exec.py` still wraps the counselors CLI for backward compatibility. Output parsing lives in that executor. Strategies no longer call `run_counselors()` directly -- they go through the `AgentExecutor` protocol. ACP agents produce structured output (no filesystem scraping).
- **`acp_client.py`**: Path traversal prevention and isolation mode enforcement. Changes to `_resolve_sandbox_path()` or `_check_read_allowed()`/`_check_write_allowed()` affect security boundaries.

## Counselors Output Structure (Legacy)

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

The `{agent}.md` is conversational output -- NOT necessarily the artifact. Real reports may be in separate files (e.g., `research_report.md`). Heuristic: pick largest `.md` excluding `prompt.md`, `summary.md`. ACP eliminates this problem -- agent output is the accumulated text from `AgentMessageChunk` session updates.

## Code Conventions

- `from __future__ import annotations` in every file
- `logging.getLogger(__name__)` in every module
- dataclasses for all data types (except ACP SDK types which use Pydantic)
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

- **Unit tests**: mock all external calls (`unittest.mock.patch`). ACP `spawn_agent_process`, counselors, GEPA, filesystem -- everything mocked.
- **Live/integration tests**: marked `@pytest.mark.live`; call real agents; expected for integration verification.
- Default pytest run excludes live: `addopts = "-m 'not live'"`
- TDD: write failing tests first when building new features.
- ACP executor tests use `AsyncMock` and a custom `_async_context_manager` helper to mock `spawn_agent_process`.

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
- [Agent Client Protocol (ACP)](https://agentclientprotocol.com) -- JSON-RPC 2.0 over stdio. The `agent-client-protocol` Python SDK handles framing and types.
- Multi-agent debate/deliberation protocols
- GEPA (Generalized Evolutionary Prompt Adjustment) / `optimize_anything` API
- Copy-on-write filesystem sandboxing patterns
- Orchestrator-mediated vs. direct agent communication

## Rules

**NEVER:**
- Implement agent execution directly -- all dispatch through `AgentExecutor` (ACP, headless, counselors, or direct)
- Skip tests; disable tests instead of fixing them
- Commit code that doesn't pass `uv run pytest tests/ -x -v`
- Use `--no-verify` on commits
- Reimplement features from scratch without asking first
- Reimplement ACP JSON-RPC framing -- use the `agent-client-protocol` SDK
- Guess at counselors output format -- verify against real output or existing parsing code

**ALWAYS:**
- Match surrounding code style (consistency > external standards)
- Stop after 3 failed attempts and reassess
- Prefer end-to-end verify; if blocked, say what's missing
- Update plan docs as you go
- Run the full test suite before considering work done
