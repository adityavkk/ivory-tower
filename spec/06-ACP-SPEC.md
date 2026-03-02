---
title: "ivory-tower: ACP-native agent invocation"
author: "human:aditya"
version: 1
created: 2026-03-01
depends_on: "03-SANDBOX-SPEC.md v1"
---

# Ivory Tower v4 -- ACP-Native Agent Invocation

Replace the `counselors` CLI dependency with direct Agent Client Protocol (ACP) invocation. Every agent that implements ACP becomes a first-class ivory-tower participant with no intermediary wrapper, no filesystem-convention coupling, and no output-format guessing.

## Problem Statement

### What counselors does today

`counselors` is a third-party Node.js CLI that wraps multiple coding agents behind a uniform `counselors run -f prompt.md --tools agent1,agent2 -o output/` interface. ivory-tower shells out to it via `subprocess.run()`. The integration has compounding fragility:

1. **Filesystem-convention coupling.** counselors writes output to `<output_dir>/<slug>/<agent>.md`. Three separate `_normalize_counselors_output()` implementations (council.py, adversarial.py, counselors_exec.py) parse this structure with 4-tier fallback heuristics. When agents write their real report to a different filename (e.g., `research_report.md` instead of `<agent>.md`), a `_find_best_report_file()` heuristic guesses which file is the actual output by comparing sizes. This is structurally unsound.

2. **Two divergent execution paths.** council and adversarial strategies call `run_counselors()` directly (bypassing the executor/sandbox layer). debate, map-reduce, and red-blue go through `CounselorsExecutor` + `Sandbox`. The direct path ignores `--sandbox` entirely (spec/05-SANDBOX-FIXES.md Issue 4). Unifying these paths means rewriting the two most complex strategies.

3. **Opaque error propagation.** When an agent fails inside counselors, ivory-tower sees only a nonzero exit code and stderr text. No structured error types, no partial output recovery, no distinction between agent-refused-task and agent-crashed.

4. **No streaming.** All counselors invocations are blocking `subprocess.run()` calls. A 10-minute research task produces zero progress signal until completion. The adversarial strategy's GEPA loop calls counselors dozens of times sequentially with no intermediate visibility.

5. **Binary resolution fragility.** `resolve_counselors_cmd()` tries `counselors`, then `bunx counselors`, then `npx counselors`. This assumes counselors is published as an npm package and that Node.js is installed. Python-native agents (which are becoming the majority) go through an unnecessary Node.js intermediary.

6. **Agent validation coupling.** `counselors ls --json` returns the set of known agents. ivory-tower validates requested agents against this set at startup. Adding a new agent means configuring it in counselors first, then in ivory-tower profiles. The agent registry is duplicated across two systems.

### What ACP changes

The Agent Client Protocol (ACP) is a JSON-RPC 2.0 protocol over stdio for bidirectional communication between clients and AI agents. It is the emerging standard for programmatic agent invocation, with 30+ compatible agents including Claude Code, Gemini CLI, Codex CLI, OpenCode, Goose, Cline, Kiro CLI, and others.

ACP gives ivory-tower:
- **Structured input/output.** Prompts go in as typed `ContentBlock[]`, responses stream back as `AgentMessageChunk` notifications. No filesystem-convention parsing.
- **Streaming.** `session/update` notifications deliver text chunks, tool call progress, and execution plans in real-time.
- **Bidirectional tool control.** The orchestrator implements `readTextFile`, `writeTextFile`, `createTerminal` -- sandbox isolation becomes a first-class enforcement point rather than a filesystem convention.
- **Structured errors.** JSON-RPC error codes distinguish method-not-found from internal-error from resource-not-found.
- **Direct subprocess management.** `spawn_agent_process()` launches agents as stdio subprocesses. No npm, no Node.js, no intermediary CLI.
- **Session continuity.** Multi-turn conversations within a single session enable refinement and challenge phases without re-prompting from scratch.

## Protocol Landscape Assessment

Three protocols were evaluated:

| Protocol | Transport | Primary Use Case | Fit for ivory-tower |
|----------|-----------|-----------------|---------------------|
| **ACP** | stdio (subprocess) | Client <-> coding agent | **Best fit.** Direct subprocess invocation, bidirectional tool control, streaming, session continuity. Matches ivory-tower's local-execution model exactly. |
| **A2A** | HTTP | Agent <-> agent delegation | Partial fit. Excellent task lifecycle model, but requires HTTP servers for local agents. Adds network overhead for what are fundamentally local subprocesses. Better suited for remote/distributed agent meshes. |
| **AG-UI** | SSE/WebSocket | Agent <-> user frontend | Poor fit. UI-centric event model. Would only be relevant for a future web dashboard. |

**Decision: ACP as the primary protocol.** A2A support can be layered on top as a future executor for remote agents, but the core replacement for counselors is ACP over stdio.

### Why ACP over A2A

- ivory-tower runs agents as local subprocesses. ACP's stdio transport is zero-overhead for this model. A2A would require spinning up an HTTP server per agent, adding ~100ms latency per invocation plus port management complexity.
- ACP's bidirectional tool calls (`readTextFile`, `writeTextFile`, `createTerminal`) map directly to the `Sandbox` protocol. The orchestrator can enforce isolation at the protocol level -- agents literally cannot read files outside their sandbox because the orchestrator controls the `readTextFile` handler. This is stronger isolation than filesystem conventions.
- ACP sessions support multi-turn prompting. ivory-tower's refinement phases (council Phase 2: "here's your report and your peers' reports, now refine") become follow-up prompts in the same session rather than new agent invocations with concatenated context.
- Every major coding agent already speaks ACP. counselors exists precisely because this protocol didn't exist when ivory-tower was built. Now it does.

### Why not A2A

A2A is the right protocol for a different architecture -- one where agents are long-running services on the network. If ivory-tower evolves toward a distributed deployment model (agents running on remote servers, cloud functions, or container orchestrators), A2A becomes relevant. The design below preserves a clean path to adding an `A2AExecutor` alongside the `ACPExecutor` without architectural changes.

## WANT

### ACP Executor

- A new `ACPExecutor` that implements the existing `AgentExecutor` protocol. It replaces `CounselorsExecutor` as the default executor.
- Agent invocation via `acp.spawn_agent_process()`: launch agent as a subprocess, communicate over stdio JSON-RPC. No filesystem conventions, no output-directory parsing, no slug heuristics.
- The executor manages the full ACP lifecycle per invocation: `initialize` -> `session/new` -> `session/prompt` -> collect response -> cleanup.
- Agent output is the accumulated text from `AgentMessageChunk` session updates. No filesystem scraping.
- Agent-produced files (code, reports) are captured via the `writeTextFile` handler. The orchestrator writes them into the sandbox, giving it full control over where files land.
- Tool calls from agents are routed through the sandbox: `readTextFile` -> `sandbox.read_file()`, `writeTextFile` -> `sandbox.write_file()`, `createTerminal` -> `sandbox.execute()`. This makes sandbox isolation enforceable at the protocol level rather than relying on filesystem permissions alone.

### Agent Registry

- Agent configuration moves from counselors' internal registry to ivory-tower's own `~/.ivory-tower/agents/` directory (YAML files, one per agent).
- Each agent config specifies: `command` (the binary to spawn, e.g., `claude`, `codex`, `gemini`), `args` (additional CLI flags), `env` (environment variables), `protocol` (default `acp`, future: `a2a`), and optional `capabilities` (declared tool support).
- `ivory agents` CLI command lists configured agents. `ivory agents add <name>` scaffolds a new agent config. `ivory agents check <name>` verifies the agent binary exists and responds to ACP `initialize`.
- Agent profiles (`~/.ivory-tower/profiles/`) gain an `agent` field that references a registered agent by name. The profile's existing `executor` field is replaced by the agent reference.
- `validate_agents()` checks agent configs exist and binaries are resolvable. No more `counselors ls`.

### Streaming and Progress

- The `ACPExecutor` streams agent output in real-time via `session/update` notifications. The `AgentOutput` dataclass gains an optional `chunks: list[str]` field for incremental text.
- Strategies can optionally consume a streaming callback: `on_chunk: Callable[[str, str], None] | None` (agent_name, text_chunk). This enables live progress display via Rich.
- The `log.py` module gains a `StreamingPanel` component that displays live agent output during execution. Controlled by `--verbose` / `--stream` flag.
- Non-streaming mode (default) accumulates all chunks and returns the full text in `AgentOutput.raw_output`, identical to current behavior. Streaming is opt-in, not a breaking change.

### Session Continuity for Multi-Turn Strategies

- The `ACPExecutor` supports keeping sessions alive across multiple prompts within a strategy phase. This is critical for:
  - **Council Phase 2 (refinement):** Instead of launching a new agent process for each refinement prompt, the executor reuses the Phase 1 session. The agent retains context from its initial research.
  - **Adversarial GEPA loop:** The evaluator and proposer closures reuse sessions across rounds. Each judge scoring and each improvement prompt is a follow-up turn, not a cold start.
  - **Debate rounds:** Each agent maintains a persistent session across all debate rounds. Turn-based prompting within the same session.
- Session reuse is managed by the executor, not the strategy. Strategies call `executor.run()` with an optional `session_id` parameter. The executor creates sessions on first call and reuses on subsequent calls with the same ID.
- Session cleanup happens when the executor's `close_session(session_id)` is called, or automatically when the agent process is terminated.

### Sandbox-Enforced Tool Control

- When an agent calls `readTextFile(path)`, the orchestrator's ACP client handler resolves the path relative to the agent's sandbox workspace and calls `sandbox.read_file(resolved_path)`. Paths outside the sandbox are rejected with a JSON-RPC error.
- When an agent calls `writeTextFile(path, content)`, the orchestrator writes via `sandbox.write_file(resolved_path, content)`. The sandbox backend controls where the file actually lands (local dir, AgentFS overlay, Daytona container).
- When an agent calls `createTerminal(command, args)`, the orchestrator routes through `sandbox.execute([command, *args])`. The sandbox backend controls execution context (bare host, sandboxed namespace, Docker container).
- `requestPermission` calls are handled by a configurable policy: `auto-approve` (default for batch runs), `approve-reads-reject-writes` (conservative mode), or `reject-all` (pure-LLM mode, no tool use). Configurable per-agent-profile.
- Blackboard access is enforced through tool control: an agent in a `read-blackboard` isolation mode gets `readTextFile` handlers that include the blackboard path but `writeTextFile` handlers that reject writes to blackboard paths. This is stronger than the current orchestrator-mediated-copy approach because it prevents agents from even attempting writes they shouldn't make.

### Unified Execution Path

- council and adversarial strategies are migrated from direct `run_counselors()` calls to the `AgentExecutor` protocol. This eliminates the two-path architecture.
- `run_counselors()`, `_normalize_counselors_output()`, `read_counselors_output()`, `_find_best_report_file()` are deleted. All ~200 lines of output-scraping heuristics disappear.
- council.py drops from ~545 lines to ~300 lines. adversarial.py drops from ~1460 lines to ~900 lines (the GEPA integration, prompt building, and JSON extraction remain; the counselors I/O plumbing disappears).
- All five strategies use the same execution path: `strategy -> executor.run(sandbox, agent, prompt, ...) -> AgentOutput`. The template-based strategies already do this; council and adversarial are brought in line.

### Backward Compatibility

- A `LegacyCounselorsExecutor` is preserved as an optional executor for users who need counselors for agents that don't yet speak ACP. It wraps the current `run_counselors()` logic with the same heuristics. It is not the default; users opt in via agent config: `protocol: counselors`.
- The migration path: install ACP-compatible agent binaries (most coding agents already are), create agent configs in `~/.ivory-tower/agents/`, switch profiles from `executor: counselors` to referencing an ACP agent. Existing counselors-based setups continue to work with the legacy executor.
- `ivory migrate` CLI command auto-generates agent configs from existing counselors agents, creating one YAML file per `counselors ls` entry with the correct binary path and protocol.

## DON'T

- Implement an A2A executor in this spec. A2A is a valid future addition but is out of scope. The `AgentExecutor` protocol remains the extension point; adding `A2AExecutor` later requires no changes to strategies or the engine.
- Implement agent-side ACP compliance. ivory-tower is an ACP **client**, not an ACP agent. It invokes agents that already implement ACP. It does not help agents become ACP-compliant.
- Implement custom JSON-RPC framing. Use the `agent-client-protocol` Python SDK (`pip install agent-client-protocol`) for all protocol handling. Don't reimplement the wire format.
- Remove the `DirectExecutor`. It remains useful for simple LLM-only tasks (no tool use, no agent runtime). It becomes the third executor alongside `ACPExecutor` and `LegacyCounselorsExecutor`.
- Force streaming on users. Streaming is opt-in. Default behavior accumulates output and returns it as a single string, identical to current behavior. Strategies that don't need streaming shouldn't pay for it in complexity.
- Implement ACP server mode. ivory-tower is not an ACP agent and will not become one. It is an orchestrator that consumes agents, not one itself.
- Support ACP's Streamable HTTP transport in v4. stdio is sufficient for local agents. If remote agent support is needed, A2A (over HTTP) is the better protocol for that layer.
- Break the `Sandbox` protocol. ACP tool handlers route through the existing sandbox interface. No new sandbox methods are needed. The current `execute()`, `read_file()`, `write_file()`, `list_files()` surface is sufficient.

## LIKE

- [Agent Client Protocol](https://agentclientprotocol.com) -- The protocol spec. JSON-RPC 2.0 over stdio. Bidirectional tool calls. Session management. 30+ compatible agents.
- [ACP Python SDK](https://github.com/agentclientprotocol/python-sdk) -- `pip install agent-client-protocol`. Pydantic models for all message types. `spawn_agent_process()` for subprocess management. `Client` interface for implementing tool handlers.
- [A2A Protocol](https://a2a-protocol.org) -- Agent-to-agent delegation over HTTP. Task lifecycle, artifacts, streaming. Good reference for structured task management. Future executor candidate.
- [LSP](https://microsoft.github.io/language-server-protocol/) -- The architectural ancestor. ACP is "LSP for AI agents." Same JSON-RPC-over-stdio pattern, same capability negotiation, same bidirectional request model.
- [03-SANDBOX-SPEC.md](./03-SANDBOX-SPEC.md) -- The sandbox architecture this builds on. ACP tool handlers are the enforcement mechanism for sandbox isolation.

## FOR

- Python 3.12+. The `agent-client-protocol` SDK requires Python 3.10+; ivory-tower already requires 3.12+.
- macOS and Linux. ACP stdio transport works on both. No Windows support (consistent with v3).
- Developers who already have ACP-compatible agent binaries installed (`claude`, `codex`, `gemini`, `goose`, `opencode`, etc.). The value proposition is: stop installing and configuring counselors as an intermediary; point ivory-tower directly at your agents.
- The adversarial strategy's GEPA integration. Session continuity means the evaluator and proposer can reuse agent sessions across GEPA rounds, reducing cold-start overhead from ~30 invocations to ~4 persistent sessions.

## ENSURE

### Agent Config and Registry

```bash
# Agent configs live in ~/.ivory-tower/agents/
cat ~/.ivory-tower/agents/claude.yml
```
```yaml
name: claude
command: claude
args: ["--no-ui"]
env:
  ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
protocol: acp
capabilities:
  tools: [read, write, execute]
```

```bash
# List configured agents
ivory agents
# Output:
#   claude     acp    /usr/local/bin/claude
#   codex      acp    /usr/local/bin/codex
#   gemini     acp    /usr/local/bin/gemini
#   legacy-gpt counselors  (via counselors)

# Verify agent responds to ACP initialize
ivory agents check claude
# Output:
#   claude: OK (ACP v1, capabilities: fs.read, fs.write, terminal)

# Auto-migrate from counselors
ivory migrate
# Output:
#   Discovered 3 counselors agents: claude, codex, gemini
#   Created ~/.ivory-tower/agents/claude.yml
#   Created ~/.ivory-tower/agents/codex.yml
#   Created ~/.ivory-tower/agents/gemini.yml
```

### Basic Research (Drop-in Replacement)

```bash
# Before (counselors):
ivory research "quantum computing" -a claude,codex -s claude
# Internally: subprocess.run("counselors run -f prompt.md --tools claude,codex -o ...")

# After (ACP):
ivory research "quantum computing" -a claude,codex -s claude
# Internally: spawn_agent_process("claude"), send session/prompt, collect AgentMessageChunk
# Identical output format. Identical manifest. Identical file structure in run dir.
```

### Streaming Progress

```bash
# Stream agent output live
ivory research "quantum computing" -a claude -s claude --stream
# Output:
#   [phase1:research] claude >>>
#   Quantum computing leverages quantum mechanical phenomena...
#   [tool] readTextFile: /workspace/notes.md
#   [tool] writeTextFile: /workspace/quantum_report.md (4,230 bytes)
#   ...
#   [phase1:research] claude completed in 47.3s

# Without --stream (default): same behavior as today, just a spinner
ivory research "quantum computing" -a claude -s claude
# Output:
#   [phase1:research] Running 1 agent...  [spinner]
#   [phase1:research] claude completed in 47.3s
```

### Session Reuse in Multi-Turn Strategies

```python
# Council Phase 2 -- executor keeps session alive from Phase 1
# Phase 1: initial research
result1 = executor.run(sandbox, "claude", research_prompt, "output/phase1")
session_id = result1.metadata["session_id"]

# Phase 2: refinement (reuses session -- agent has context)
result2 = executor.run(sandbox, "claude", refinement_prompt, "output/phase2",
                       session_id=session_id)

# Phase 3: synthesis (new agent, new session)
result3 = executor.run(sandbox, "claude", synthesis_prompt, "output/phase3")
```

### Sandbox-Enforced Isolation

```python
# Agent calls readTextFile("/etc/passwd") -- orchestrator rejects
# Agent calls readTextFile("peers/codex-report.md") in full-isolation mode -- rejected
# Agent calls readTextFile("peers/codex-report.md") in read-peers mode -- allowed
# Agent calls writeTextFile("blackboard/transcript.md") in read-blackboard mode -- rejected
```

### Test Expectations

```bash
# Unit tests -- all ACP calls mocked
uv run pytest tests/test_executor_acp.py -v
# Tests: spawn_agent_process mocked, verify initialize/session/prompt sequence
# Tests: tool call handlers route through sandbox correctly
# Tests: streaming accumulation produces correct AgentOutput
# Tests: session reuse sends prompts to existing session
# Tests: path traversal in tool handlers is rejected

# Integration tests -- real ACP agents
uv run pytest tests/test_acp_integration.py -v -m integration
# Requires: at least one ACP agent binary on PATH
# Tests: full lifecycle (spawn, initialize, prompt, collect, cleanup)
# Tests: agent tool calls hit sandbox filesystem

# Legacy compatibility
uv run pytest tests/test_executor_counselors.py -v
# Existing tests still pass -- LegacyCounselorsExecutor preserves behavior

# All existing strategy tests pass with ACPExecutor mocked in place of CounselorsExecutor
uv run pytest tests/ -x -v
```

## TRUST

- The `agent-client-protocol` Python SDK handles JSON-RPC framing, message serialization, and subprocess lifecycle. We do not reimplement any wire-level protocol handling.
- ACP-compatible agents correctly implement the protocol spec: they respond to `initialize`, create sessions, stream `session/update` notifications, and handle `session/cancel`. If an agent's ACP implementation is buggy, that is the agent's problem, not ivory-tower's.
- `spawn_agent_process()` correctly manages subprocess cleanup (signal handling, pipe closure) via its async context manager. We do not implement our own subprocess lifecycle management.
- GEPA's `optimize_anything` API is unchanged. The evaluator and proposer closures still return the same types (`(score, asi)` and `dict`). Only the internal I/O mechanism changes from `run_counselors()` to `executor.run()`.
- Agent binaries are installed and configured by the user. ivory-tower does not install, update, or manage agent runtimes.

## Architecture

### Module Changes

```
src/ivory_tower/
  agents.py              # NEW: AgentConfig dataclass, load/list/validate agents
  acp_client.py          # NEW: HeadlessACPClient (Client subclass), tool handlers
  executor/
    acp_exec.py          # NEW: ACPExecutor (AgentExecutor implementation)
    counselors_exec.py   # RENAMED: legacy_counselors_exec.py (kept for compat)
    types.py             # MODIFIED: AgentOutput gains session_id, chunks fields
    __init__.py          # MODIFIED: registry adds "acp", renames "counselors" -> "legacy-counselors"
  counselors.py          # DEPRECATED: kept for LegacyCounselorsExecutor only
  cli.py                 # MODIFIED: agent commands, drop counselors validation
  strategies/
    council.py           # MODIFIED: use executor.run() instead of run_counselors()
    adversarial.py       # MODIFIED: use executor.run() instead of run_counselors()
```

### New Files

**`agents.py`** (~120 lines)

```python
@dataclass
class AgentConfig:
    name: str
    command: str                          # binary name or path
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    protocol: str = "acp"                 # "acp" | "legacy-counselors" | "direct"
    capabilities: dict[str, Any] = field(default_factory=dict)

def load_agents() -> dict[str, AgentConfig]: ...
def resolve_agent_binary(config: AgentConfig) -> Path: ...
def validate_agent_configs(names: list[str]) -> list[str]: ...  # returns invalid names
```

**`acp_client.py`** (~250 lines)

```python
class SandboxACPClient(Client):
    """ACP Client that routes all agent tool calls through a Sandbox."""

    def __init__(self, sandbox: Sandbox, isolation_mode: str, permissions: str):
        self.sandbox = sandbox
        self.isolation_mode = isolation_mode
        self.permissions = permissions  # "auto-approve" | "reads-only" | "reject-all"
        self.accumulated_text: list[str] = []

    async def sessionUpdate(self, params: SessionNotification) -> None:
        # Accumulate AgentMessageChunk text
        # Forward to optional streaming callback
        ...

    async def readTextFile(self, params: ReadTextFileRequest) -> ReadTextFileResponse:
        resolved = self._resolve_sandbox_path(params.path)
        self._check_read_allowed(resolved)
        content = self.sandbox.read_file(resolved)
        return ReadTextFileResponse(content=content)

    async def writeTextFile(self, params: WriteTextFileRequest) -> WriteTextFileResponse:
        resolved = self._resolve_sandbox_path(params.path)
        self._check_write_allowed(resolved)
        self.sandbox.write_file(resolved, params.content)
        return WriteTextFileResponse()

    async def createTerminal(self, params: CreateTerminalRequest) -> CreateTerminalResponse:
        # Route through sandbox.execute()
        ...

    async def requestPermission(self, params: RequestPermissionRequest) -> RequestPermissionResponse:
        # Apply permission policy
        ...

    def _resolve_sandbox_path(self, path: str) -> str:
        # Resolve relative to sandbox workspace, reject traversal
        ...

    def _check_read_allowed(self, path: str) -> None:
        # Enforce isolation mode for reads
        ...

    def _check_write_allowed(self, path: str) -> None:
        # Enforce isolation mode for writes (reject blackboard writes in read-blackboard mode, etc.)
        ...
```

**`executor/acp_exec.py`** (~200 lines)

```python
class ACPExecutor:
    """AgentExecutor that invokes agents via ACP over stdio."""

    name = "acp"

    def __init__(self):
        self._sessions: dict[str, tuple[ClientSideConnection, asyncio.subprocess.Process]] = {}

    def run(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
        session_id: str | None = None,
        on_chunk: Callable[[str, str], None] | None = None,
    ) -> AgentOutput:
        """Invoke an agent via ACP. Blocks until agent completes."""
        return asyncio.run(self._run_async(
            sandbox, agent_name, prompt, output_dir,
            model, system_prompt, verbose, session_id, on_chunk,
        ))

    async def _run_async(self, ...) -> AgentOutput:
        config = load_agents()[agent_name]
        cmd = [str(resolve_agent_binary(config)), *config.args]

        client = SandboxACPClient(sandbox, isolation_mode="full", permissions="auto-approve")

        async with spawn_agent_process(lambda _: client, *cmd) as (conn, proc):
            await conn.initialize(InitializeRequest(protocolVersion=1))
            session = await conn.newSession(NewSessionRequest(
                cwd=str(sandbox.workspace_dir),
            ))
            response = await conn.prompt(PromptRequest(
                sessionId=session.sessionId,
                prompt=[text_block(prompt)],
            ))
            return AgentOutput(
                report_path=f"{output_dir}/{agent_name}-report.md",
                raw_output="".join(client.accumulated_text),
                duration_seconds=...,
                metadata={"session_id": session.sessionId, "stop_reason": response.stopReason},
            )

    def close_session(self, session_id: str) -> None:
        """Terminate a persistent session and its agent process."""
        ...
```

### Migration Path for council.py

Current (direct `run_counselors()`):
```python
# Phase 1
run_counselors(prompt_file, config.agents, phase1_dir, verbose)
_normalize_counselors_output(phase1_dir, config.agents, suffix="-report.md")
report_text = (phase1_dir / f"{agent}-report.md").read_text()
```

After (via `AgentExecutor`):
```python
# Phase 1
for agent in config.agents:
    result = executor.run(sandbox, agent, prompt_text, f"phase1/{agent}")
    (phase1_dir / f"{agent}-report.md").write_text(result.raw_output)
```

All `_normalize_counselors_output()` calls are deleted. `result.raw_output` is the agent's response text, captured from ACP streaming -- no filesystem scraping.

### Migration Path for adversarial.py

The most complex migration. Key changes:

1. **Seed generation**: Same as council Phase 1. `run_counselors()` -> `executor.run()`.
2. **GEPA evaluator**: The evaluator closure calls `executor.run()` with the judge agent instead of `run_counselors()`. `parse_judge_output()` reads `result.raw_output` instead of scraping the filesystem. The 5-strategy JSON extraction still applies to the text, but the text source is now reliable.
3. **GEPA proposer**: The proposer closure calls `executor.run()` with the original agent. `read_counselors_output()` is replaced by reading `result.raw_output`.
4. **Parse agent fallback**: `_llm_extract_json()` calls `executor.run()` instead of `run_counselors()`.
5. **Synthesis**: Same as council Phase 3.

Session continuity: the adversarial strategy can optionally keep evaluator and proposer sessions alive across GEPA rounds. This is a performance optimization, not a correctness requirement. The strategy works correctly with cold-start sessions too.

### Executor Registry Change

```python
# Before
EXECUTORS = {"counselors": CounselorsExecutor, "direct": DirectExecutor}

# After
EXECUTORS = {
    "acp": ACPExecutor,
    "direct": DirectExecutor,
    "legacy-counselors": LegacyCounselorsExecutor,
}
DEFAULT_EXECUTOR = "acp"
```

### CLI Changes

```python
# Before (cli.py)
resolve_counselors_cmd()          # fails if counselors not installed
available = list_available_agents()  # calls counselors ls
invalid = validate_agents(all_agents, available)

# After (cli.py)
invalid = validate_agent_configs(all_agents)  # checks ~/.ivory-tower/agents/ configs
# No binary resolution at startup -- agents are spawned on demand
# Binary existence is checked when the executor first tries to spawn

# New commands
@app.command()
def agents(check: str | None = None): ...

@app.command()
def migrate(): ...
```

## Implementation Plan

### Commit Sequence (Red-Green TDD)

**Commit 1: Agent config system**
- `agents.py`: `AgentConfig` dataclass, `load_agents()`, `resolve_agent_binary()`, `validate_agent_configs()`
- `tests/test_agents.py`: YAML loading, binary resolution, validation
- No behavioral changes to existing code

**Commit 2: ACP client with sandbox routing**
- `acp_client.py`: `SandboxACPClient` with all tool handlers
- `tests/test_acp_client.py`: path resolution, isolation enforcement, permission policies, text accumulation
- Mocks: `acp` SDK types

**Commit 3: ACP executor**
- `executor/acp_exec.py`: `ACPExecutor` class
- `executor/__init__.py`: register `"acp"` executor
- `executor/types.py`: add `session_id` and `chunks` to `AgentOutput.metadata`
- `tests/test_executor_acp.py`: mock `spawn_agent_process`, verify lifecycle
- Default executor remains `"counselors"` (not switched yet)

**Commit 4: Migrate council strategy**
- `strategies/council.py`: replace `run_counselors()` with `executor.run()`
- Delete `_normalize_counselors_output()` from council.py
- `tests/test_integration.py`: update mocks from `run_counselors` to `executor.run`
- Existing tests must pass with mocked `ACPExecutor`

**Commit 5: Migrate adversarial strategy**
- `strategies/adversarial.py`: replace all `run_counselors()` calls with `executor.run()`
- Delete `_normalize_counselors_output()`, `read_counselors_output()`, `_find_best_report_file()` from adversarial.py
- Simplify `parse_judge_output()` to read from `AgentOutput.raw_output`
- `tests/test_adversarial_strategy.py`, `tests/test_adversarial_helpers.py`: update mocks

**Commit 6: CLI migration**
- `cli.py`: replace `resolve_counselors_cmd()` / `list_available_agents()` / `validate_agents()` with `validate_agent_configs()`
- Add `agents` and `migrate` commands
- `counselors.py`: mark deprecated, keep for `LegacyCounselorsExecutor`
- `executor/counselors_exec.py` -> `executor/legacy_counselors_exec.py`
- Update all imports

**Commit 7: Streaming support**
- `acp_client.py`: add streaming callback support
- `log.py`: add `StreamingPanel`
- `cli.py`: add `--stream` flag
- `tests/test_streaming.py`: verify chunk delivery and accumulation

**Commit 8: Session continuity**
- `executor/acp_exec.py`: persistent session management
- `strategies/council.py`: pass `session_id` for Phase 2 refinement
- `strategies/adversarial.py`: pass `session_id` for GEPA loop sessions
- `tests/test_session_continuity.py`: verify session reuse across prompts

**Commit 9: Integration tests + cleanup**
- `tests/test_acp_integration.py`: live ACP agent tests (marked `@pytest.mark.live`)
- Full test suite pass: `uv run pytest tests/ -x -v`
- Remove dead code, update docstrings, update README

### Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "agent-client-protocol >= 0.8",   # ACP Python SDK (new)
    "typer >= 0.15",
    "rich >= 13",
    "pyyaml >= 6",
]

[project.optional-dependencies]
adversarial = ["gepa >= 0.1"]
legacy = ["counselors >= 0.1"]         # for LegacyCounselorsExecutor (new optional group)
direct = ["litellm >= 1.0"]
```

The `agent-client-protocol` package becomes a core dependency (it has only one dependency: `pydantic>=2.7`, which is lightweight). counselors moves to an optional dependency group.

## Appendix A: Agent Compatibility Matrix and Wrapping Strategy

The ACP ecosystem is young. Not every coding agent speaks ACP natively. ivory-tower needs to handle three tiers of agents through a single `AgentExecutor` interface: native ACP agents, agents with their own headless protocols, and legacy agents with only text I/O.

### Tier 1: Native ACP Agents (First-Class)

These agents implement the ACP JSON-RPC protocol over stdio. ivory-tower spawns them via `acp.spawn_agent_process()` and communicates using the standard ACP lifecycle (`initialize` -> `session/new` -> `session/prompt` -> `session/update` stream).

| Agent | ACP Command | Install | Notes |
|-------|-------------|---------|-------|
| **OpenCode** | `opencode acp` | `npm i -g opencode-ai` / `brew install anomalyco/tap/opencode` | Full ACP support. All tools available. Pass `--cwd` for working dir. |
| **Goose** | `goose acp` | `curl -fsSL .../download_cli.sh \| bash` / `brew install block-goose-cli` | Native ACP. `--with-builtin developer,memory` for extensions. |
| **Gemini CLI** | `gemini --experimental-acp` | `npm i -g @google/gemini-cli` | ACP support is experimental. Free tier: 1000 req/day. |
| **Kiro CLI** | `kiro-cli acp` | `curl -fsSL https://cli.kiro.dev/install \| bash` | Native ACP with Kiro-specific extensions. Supports `loadSession`. |
| **Cline** | `cline --acp` | `npm i -g cline` | ACP via ndJSON over stdio. Newer CLI (VS Code extension heritage). |
| **GitHub Copilot** | *(via editor)* | *(built into VS Code/JetBrains)* | ACP support in public preview. Not available as standalone subprocess. |

Agent config examples for native ACP:

```yaml
# ~/.ivory-tower/agents/opencode.yml
name: opencode
command: opencode
args: ["acp", "--cwd", "{workspace}"]
protocol: acp
env:
  OPENCODE_CONFIG_CONTENT: '{"model": "anthropic/claude-sonnet-4-5"}'
capabilities:
  tools: [read, write, execute, glob, grep, webfetch]

# ~/.ivory-tower/agents/goose.yml
name: goose
command: goose
args: ["acp", "--with-builtin", "developer"]
protocol: acp
env: {}
capabilities:
  tools: [read, write, execute]

# ~/.ivory-tower/agents/gemini.yml
name: gemini
command: gemini
args: ["--experimental-acp"]
protocol: acp
env:
  GEMINI_API_KEY: "${GEMINI_API_KEY}"
capabilities:
  tools: [read, write, execute]

# ~/.ivory-tower/agents/kiro.yml
name: kiro
command: kiro-cli
args: ["acp"]
protocol: acp
env: {}
capabilities:
  tools: [read, write, execute]

# ~/.ivory-tower/agents/cline.yml
name: cline
command: cline
args: ["--acp"]
protocol: acp
env: {}
capabilities:
  tools: [read, write, execute]
```

### Tier 2: Non-ACP Agents with Headless Protocols (Adapted)

These agents don't speak ACP but have structured headless/non-interactive modes with machine-readable output. ivory-tower wraps them behind the `AgentExecutor` interface using a `HeadlessExecExecutor` that invokes the agent's native CLI, captures output, and returns it as `AgentOutput`.

This is a subprocess executor (like the current `CounselorsExecutor`) but with per-agent command templates rather than routing everything through a single intermediary CLI.

| Agent | Headless Command | Output Format | Session Support |
|-------|-----------------|---------------|-----------------|
| **Claude Code** | `claude -p "prompt" --output-format stream-json --verbose` | Streaming JSON (ndJSON events) | Yes (`--continue`, `--resume $ID`) |
| **Codex CLI** | `codex exec "prompt" --json` | JSONL event stream | Yes (`codex exec resume --last "prompt"`) |
| **Amp** | `amp -x "prompt" --stream-json` | Streaming JSON | No |
| **Aider** | `aider --message "prompt" --yes` | Plain text | No |

For these agents, the `HeadlessExecExecutor` does the adaptation work:

1. **Builds the command** from agent config: binary + args + prompt injection
2. **Runs the subprocess** (async, with streaming if the agent supports it)
3. **Parses the output** format (JSON events, JSONL, or plain text) into `AgentOutput`
4. **Handles session continuity** where available (Claude Code's `--continue`, Codex's `resume`)

Agent config examples for headless agents:

```yaml
# ~/.ivory-tower/agents/claude.yml
name: claude
command: claude
args:
  - "-p"
  - "{prompt}"
  - "--output-format"
  - "stream-json"
  - "--verbose"
  - "--dangerously-skip-permissions"
  - "--max-turns"
  - "50"
protocol: headless
output_format: stream-json        # "stream-json" | "jsonl" | "json" | "text"
session:
  continue_flag: "--continue"     # flag for multi-turn within same session
  resume_flag: "--resume"         # flag + session ID for resuming
env:
  ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
capabilities:
  tools: [read, write, execute]

# ~/.ivory-tower/agents/codex.yml
name: codex
command: codex
args:
  - "exec"
  - "{prompt}"
  - "--json"
  - "--full-auto"
  - "--sandbox"
  - "workspace-write"
protocol: headless
output_format: jsonl
session:
  resume_command: ["codex", "exec", "resume", "--last", "{prompt}"]
env:
  CODEX_API_KEY: "${CODEX_API_KEY}"
capabilities:
  tools: [read, write, execute]

# ~/.ivory-tower/agents/amp.yml
name: amp
command: amp
args:
  - "-x"
  - "{prompt}"
  - "--stream-json"
  - "--dangerously-allow-all"
protocol: headless
output_format: stream-json
env:
  AMP_API_KEY: "${AMP_API_KEY}"
capabilities:
  tools: [read, write, execute]

# ~/.ivory-tower/agents/aider.yml
name: aider
command: aider
args:
  - "--message"
  - "{prompt}"
  - "--yes"
  - "--no-auto-commits"
protocol: headless
output_format: text
env:
  ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
capabilities:
  tools: [read, write, execute]
```

### Tier 3: Claude Code ACP Adapter (Third-Party Bridge)

Claude Code has an official ACP adapter maintained by Zed Industries: `claude-agent-acp`. This wraps the Claude Agent SDK's `stream-json` output into ACP JSON-RPC, letting ivory-tower treat Claude Code as a native ACP agent.

```yaml
# ~/.ivory-tower/agents/claude-acp.yml
name: claude-acp
command: claude-agent-acp          # from @zed-industries/claude-agent-acp
args: []
protocol: acp
env:
  ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
capabilities:
  tools: [read, write, execute]
```

Install: `npm i -g @zed-industries/claude-agent-acp` or download pre-built binaries from the [releases page](https://github.com/zed-industries/claude-agent-acp/releases).

This is the recommended path for Claude Code. It gives full ACP semantics (bidirectional tool control, session management, structured streaming) without ivory-tower needing to parse Claude Code's native `stream-json` format. The tradeoff: an extra npm dependency and a third-party adapter that may lag behind Claude Code releases.

For users who don't want the adapter dependency, the Tier 2 headless config (`claude -p`) works as a simpler fallback.

### Executor Architecture: Three Executors

The three tiers map to three executors, all implementing the same `AgentExecutor` protocol:

```
AgentExecutor (Protocol)
  |
  |-- ACPExecutor              # Tier 1: native ACP (spawn_agent_process, JSON-RPC)
  |-- HeadlessExecExecutor     # Tier 2: non-ACP headless (subprocess, parse output)
  |-- DirectExecutor           # existing: raw litellm calls, no agent runtime
  |-- LegacyCounselorsExecutor # compat: existing counselors wrapper
```

The engine selects the executor based on the agent config's `protocol` field:

```python
def get_executor_for_agent(agent_name: str) -> AgentExecutor:
    config = load_agents()[agent_name]
    match config.protocol:
        case "acp":
            return ACPExecutor()
        case "headless":
            return HeadlessExecExecutor()
        case "direct":
            return DirectExecutor()
        case "legacy-counselors":
            return LegacyCounselorsExecutor()
        case _:
            raise ValueError(f"Unknown protocol: {config.protocol}")
```

Strategies don't care which executor is used. They call `executor.run(sandbox, agent_name, prompt, output_dir)` and get `AgentOutput` back regardless of whether the agent is native ACP, headless subprocess, or raw LLM.

### HeadlessExecExecutor Design

The `HeadlessExecExecutor` is the adapter layer for Tier 2 agents. It handles the diversity of headless CLI interfaces behind a uniform API.

```python
class HeadlessExecExecutor:
    """AgentExecutor for non-ACP agents with headless CLI modes."""

    name = "headless"

    def run(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
        session_id: str | None = None,
        on_chunk: Callable[[str, str], None] | None = None,
    ) -> AgentOutput:
        config = load_agents()[agent_name]
        cmd = self._build_command(config, prompt, session_id)
        env = self._resolve_env(config)

        result = sandbox.execute(cmd, env=env)

        raw_output = self._parse_output(result.stdout, config.output_format)

        return AgentOutput(
            report_path=f"{output_dir}/{agent_name}-report.md",
            raw_output=raw_output,
            duration_seconds=result.duration_seconds,
            metadata={"protocol": "headless", "exit_code": result.exit_code},
        )

    def _build_command(
        self, config: AgentConfig, prompt: str, session_id: str | None
    ) -> list[str]:
        """Substitute {prompt} and {session_id} placeholders in args."""
        cmd = [config.command]
        for arg in config.args:
            cmd.append(
                arg.replace("{prompt}", prompt)
                   .replace("{workspace}", str(sandbox.workspace_dir))
            )
        if session_id and config.session:
            cmd.append(config.session.continue_flag)
        return cmd

    def _parse_output(self, stdout: str, output_format: str) -> str:
        """Extract the agent's final response text from its output format."""
        match output_format:
            case "text":
                return stdout
            case "json":
                data = json.loads(stdout)
                return self._extract_text_from_json(data)
            case "jsonl" | "stream-json":
                return self._extract_text_from_jsonl(stdout)
        return stdout

    def _extract_text_from_jsonl(self, stdout: str) -> str:
        """Parse ndJSON event stream, extract assistant message text."""
        chunks = []
        for line in stdout.strip().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            # Claude Code stream-json format
            if event.get("type") == "assistant" and "message" in event:
                for block in event["message"].get("content", []):
                    if block.get("type") == "text":
                        chunks.append(block["text"])
            # Codex JSONL format
            elif event.get("type") == "item.message.completed":
                for part in event.get("item", {}).get("content", []):
                    if part.get("type") == "output_text":
                        chunks.append(part["text"])
        return "\n".join(chunks) if chunks else stdout
```

### Output Format Parsing Details

Each Tier 2 agent has a different output format. The `HeadlessExecExecutor` handles these:

**Claude Code (`stream-json`)**:
```jsonl
{"type":"system","subtype":"init","apiKeySource":"env","cwd":"/workspace","sessionId":"abc"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Here is my analysis..."}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Read","input":{"path":"src/main.py"}}]}}
{"type":"tool_result","content":"file contents..."}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Based on the code..."}]}}
{"type":"result","subtype":"success","session_id":"abc","cost_usd":0.05,"duration_ms":12000,"turns":3}
```
Extract: concatenate all `type=assistant` -> `content[].type=text` -> `.text` fields.

**Codex CLI (`jsonl`)**:
```jsonl
{"type":"thread.started","thread":{"id":"thread_123"}}
{"type":"turn.started","turn":{"id":"turn_1"}}
{"type":"item.message.completed","item":{"role":"assistant","content":[{"type":"output_text","text":"The analysis shows..."}]}}
{"type":"turn.completed","turn":{"id":"turn_1","status":"completed"}}
```
Extract: concatenate all `type=item.message.completed` -> `item.content[].type=output_text` -> `.text` fields.

**Amp (`stream-json`)**:
```jsonl
{"type":"assistant","content":{"type":"text","text":"My findings are..."}}
{"type":"tool_use","tool":"read","input":{"path":"src/main.py"}}
{"type":"tool_result","content":"..."}
{"type":"assistant","content":{"type":"text","text":"In conclusion..."}}
```
Extract: concatenate all `type=assistant` -> `content.text` fields.

**Aider (`text`)**:
Plain text stdout. The entire output is the response. Aider writes file changes directly to disk (controlled by sandbox).

### Sandbox Interaction Differences by Tier

| Concern | Tier 1 (ACP) | Tier 2 (Headless) | Tier 3 (Adapter) |
|---------|-------------|-------------------|-------------------|
| **File reads** | Orchestrator serves via `readTextFile` handler -> `sandbox.read_file()` | Agent reads directly from sandbox workspace dir | Same as Tier 1 |
| **File writes** | Orchestrator serves via `writeTextFile` handler -> `sandbox.write_file()` | Agent writes directly to sandbox workspace dir | Same as Tier 1 |
| **Command execution** | Orchestrator serves via `createTerminal` handler -> `sandbox.execute()` | Agent runs commands inside sandbox (via `sandbox.execute()` of the outer command) | Same as Tier 1 |
| **Isolation enforcement** | Protocol-level: orchestrator rejects disallowed paths in tool handlers | Filesystem-level: sandbox backend restricts what agent process can access | Protocol-level |
| **Streaming** | Native: `session/update` notifications | Parse agent's stdout stream format | Native via ACP adapter |
| **Session continuity** | Native: multiple `session/prompt` calls in same session | Per-agent: `--continue` / `--resume` flags where available | Native |

Key implication: Tier 1 (ACP) agents get the strongest isolation because every file and command operation goes through the orchestrator's handlers. Tier 2 (headless) agents execute inside the sandbox but have direct filesystem access within it -- isolation is only as strong as the sandbox backend. For `local` and `none` backends this means no real isolation. For `agentfs` and `daytona` backends, OS-level sandboxing still applies.

### Recommended Agent Configuration for New Users

For a user setting up ivory-tower for the first time, the recommended agent set:

```bash
# Install agents
brew install anomalyco/tap/opencode    # or: npm i -g opencode-ai
npm i -g @zed-industries/claude-agent-acp
npm i -g @google/gemini-cli

# Generate configs
ivory agents init
# This auto-detects installed agent binaries and creates configs:
#   ~/.ivory-tower/agents/opencode.yml   (ACP)
#   ~/.ivory-tower/agents/claude.yml     (ACP via adapter)
#   ~/.ivory-tower/agents/gemini.yml     (ACP)

# Verify
ivory agents check
# opencode:  OK (ACP v1, tools: read, write, execute, glob, grep, webfetch)
# claude:    OK (ACP v1, tools: read, write, execute)
# gemini:    OK (ACP v1, tools: read, write, execute)

# Run research
ivory research "quantum computing advances in 2026" \
  -a opencode,gemini -s claude
```

### Future: ACP Adoption Trajectory

ACP is becoming the LSP of AI agents. The trajectory favors Tier 1 (native ACP) for all major agents:

- **Claude Code**: Zed's `claude-agent-acp` adapter exists today. Anthropic is likely to ship native ACP support given the protocol's adoption.
- **Codex CLI**: No ACP today, but Zed has a `codex-acp` adapter. OpenAI's `app-server` protocol (JSON-RPC over stdio) is structurally similar to ACP -- a bridge would be thin.
- **Amp**: No ACP, but Sourcegraph's `stream-json` format is close to ACP's streaming model.
- **Aider**: Unlikely to adopt ACP (Python-native, no JSON-RPC infra). The headless executor is the long-term path for Aider.

The `HeadlessExecExecutor` is a bridge for the current ecosystem state. As agents adopt ACP, their configs migrate from `protocol: headless` to `protocol: acp` with no strategy-level changes.
