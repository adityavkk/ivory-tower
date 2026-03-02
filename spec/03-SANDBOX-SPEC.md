---
title: "ivory-tower: pluggable multi-agent sandboxing"
author: "human:aditya"
version: 1
created: 2026-03-01
depends_on: "02-STRATEGY-SPEC.md v1"
---

# Ivory Tower v3 -- Pluggable Multi-Agent Sandboxing

## HOW

### Git Worktree -- Mandatory

All implementation work MUST happen in a **git worktree**. Do NOT modify files in the main working tree. The worktree isolates this feature branch from the main codebase, preventing accidental pollution of the working copy.

```bash
# Setup -- do this FIRST before any implementation work
git branch sandbox-abstraction    # create branch from current HEAD
git worktree add ../ivory-tower-sandbox sandbox-abstraction
cd ../ivory-tower-sandbox

# ALL implementation happens here in ../ivory-tower-sandbox
# The main working tree at ../ivory-tower remains untouched

# ... 16 commits, each red-green ...

# Merge -- only after ALL tests pass
uv run pytest tests/ -v           # full suite must be green
cd ../ivory-tower                 # back to main working tree
git checkout main
git merge sandbox-abstraction
git worktree remove ../ivory-tower-sandbox
git branch -d sandbox-abstraction
```

**Critical rules:**
- NEVER commit to `main` directly. All commits go to the `sandbox-abstraction` branch inside the worktree.
- NEVER modify files outside the worktree directory (`../ivory-tower-sandbox/`). The main working tree is read-only during implementation.
- Before the final merge, run the FULL test suite from inside the worktree: `uv run pytest tests/ -v`. Every test must pass.
- If the worktree gets into a bad state, it is safe to `git worktree remove` and re-add from scratch. The branch preserves all commits.

### Subagent Parallelism -- Rules of Engagement

The implementing agent (whether human or AI) SHOULD use **subagents for parallel work** to maximize throughput. Many commits in the plan have independent components that can be built concurrently. However, parallel subagents introduce file conflict risks that MUST be managed.

**Parallelism strategy:**

1. **Partition by file, not by function.** Each subagent owns a disjoint set of files. Two subagents MUST NEVER write to the same file. If two tasks both need to modify `cli.py`, they are NOT parallelizable -- do them sequentially.

2. **Safe parallel groups** (subagents can work on these simultaneously):

   | Group | Files Owned | Can Parallel With |
   |-------|-------------|-------------------|
   | Sandbox types | `sandbox/types.py` | All other groups |
   | Local provider | `sandbox/local.py`, `tests/test_sandbox_local.py` | AgentFS provider, Daytona provider, Blackboard |
   | AgentFS provider | `sandbox/agentfs.py`, `tests/test_sandbox_agentfs.py` | Local provider, Daytona provider, Blackboard |
   | Daytona provider | `sandbox/daytona.py`, `tests/test_sandbox_daytona.py` | Local provider, AgentFS provider, Blackboard |
   | Blackboard | `sandbox/blackboard.py`, `tests/test_blackboard.py` | All provider groups |
   | Agent profiles | `profiles/__init__.py`, `tests/test_profiles.py` | All provider groups, Templates |
   | Templates loader | `templates/loader.py`, `templates/__init__.py`, `tests/test_templates.py` | Agent profiles, All provider groups |
   | Counselors executor | `executor/counselors_exec.py`, `tests/test_counselors_exec.py` | Direct executor, All provider groups |
   | Direct executor | `executor/direct.py`, `tests/test_direct_exec.py` | Counselors executor, All provider groups |
   | YAML data files | `data/strategies/*.yml` | All groups (YAML files are write-once) |

3. **NEVER-parallel files** (only one subagent touches these at a time):
   - `cli.py` -- single writer, accumulates all CLI changes
   - `engine.py` -- single writer, accumulates orchestration changes
   - `models.py` -- single writer, accumulates dataclass extensions
   - `strategies/__init__.py` -- single writer, accumulates registry changes
   - `pyproject.toml` -- single writer
   - Any existing file from v2 that multiple tasks need to modify

4. **Sequencing protocol for shared files:**
   - When a subagent needs to modify a shared file (e.g., `strategies/__init__.py`), it MUST wait until all other subagents working on that commit are done.
   - The lead agent collects subagent outputs, then makes the shared-file edits itself.
   - Alternatively, schedule shared-file modifications as a final sequential step after all parallel work completes.

5. **Subagent handoff format:**
   - Each subagent receives: (a) the files it owns, (b) the interfaces it must implement (protocols, type signatures), (c) the test expectations.
   - Each subagent returns: (a) the implementation files, (b) passing tests, (c) a list of any public API changes other subagents need to know about.
   - The lead agent is responsible for: (a) verifying no file conflicts, (b) running the combined test suite, (c) committing.

6. **Conflict detection:**
   - Before committing, run `git diff --name-only` and verify each modified file was owned by exactly one subagent.
   - If two subagents touched the same file, STOP. Manually review and merge changes. Do NOT blindly commit.

7. **Recommended parallel execution plan:**

   ```
   Phase A (parallel -- all new files, no conflicts possible):
     Subagent 1: sandbox/types.py + sandbox/local.py + tests
     Subagent 2: sandbox/agentfs.py + tests
     Subagent 3: sandbox/daytona.py + tests
     Subagent 4: sandbox/blackboard.py + tests
     Lead agent: sandbox/__init__.py (registry, imports subagent outputs)

   Phase B (parallel -- all new files):
     Subagent 5: profiles/__init__.py + tests
     Subagent 6: templates/loader.py + templates/__init__.py + data/strategies/*.yml + tests
     Subagent 7: executor/counselors_exec.py + executor/direct.py + tests
     Lead agent: executor/__init__.py, executor/types.py

   Phase C (parallel with care -- modifies existing files):
     Subagent 8: strategies/debate.py + strategies/map_reduce.py + strategies/red_blue.py + tests
     Lead agent: strategies/__init__.py (registry update), templates/executor.py

   Phase D (sequential -- shared files):
     Lead agent only: models.py extensions, engine.py changes, cli.py changes
     These touch existing v2 code and must be done carefully, one file at a time.

   Phase E (sequential):
     Lead agent only: integration tests, final cleanup, full test suite run
   ```

### Red-Green TDD

- Every commit starts with failing tests (RED), then implementation until green (GREEN). Tests and implementation are committed together. Every commit leaves the suite green.
- When subagents work in parallel, each subagent writes and runs its own tests independently. The lead agent runs the combined suite before committing.

### Test Conventions

- All `counselors` calls mocked via `unittest.mock.patch`. Sandbox providers tested with real tmp dirs. AgentFS tested with real `.db` files in `tmp_path`. No real network calls. No real container launches in unit tests.
- **Integration tests**: Marked `@pytest.mark.integration`. Test real sandbox creation/teardown with local and AgentFS backends. Can be skipped in CI with `-m "not integration"`.
- **Subagent test isolation**: Each subagent's tests MUST be runnable independently: `uv run pytest tests/test_sandbox_local.py -v` should pass without requiring other subagent outputs. Use `conftest.py` fixtures for shared test infrastructure, but do NOT have subagents write to `conftest.py` in parallel -- the lead agent owns `conftest.py`.

## WANT

### Clean Interface

- A single command: `ivory research "topic" --strategy council --agents claude,openai --synthesizer claude` produces a fully sandboxed research run. Every agent executes in its own isolated environment. No extra setup.
- YAML strategy templates define isolation topology, agent roles, phase flow, and sandbox configuration. Ship sensible defaults; users create custom templates; CLI flags override anything.
- Agent profiles define identity independent of strategy: model, role, system prompt, tool permissions, sandbox overrides. Reusable across strategies.
- `ivory research "topic" --template my-debate.yml` runs a user-defined strategy template without writing Python.
- `ivory templates` lists available strategy templates (built-in + user-defined).
- `ivory profiles` lists available agent profiles.

### Pluggable Sandbox Backends

- A `SandboxProvider` protocol abstracts the isolation mechanism. Three backends ship in v3:
  - **`local`**: Directory-based isolation. Each agent gets a private workspace directory under the run directory. No external dependencies. Zero-config. The default when nothing else is configured.
  - **`agentfs`**: AgentFS-backed isolation. Each agent gets a SQLite-backed virtual filesystem with OS-level sandboxing (FUSE + namespaces on Linux, NFS + sandbox-exec on macOS). Copy-on-write overlay on the project directory. Full tool-call audit trail. Instant snapshots. Requires `agentfs` CLI installed.
  - **`daytona`**: Docker container isolation via Daytona SDK. Each agent runs in its own container with configurable resource limits and network firewall. Shared state via FUSE volumes. Requires Daytona account or self-hosted runner.
- The sandbox backend is configured per-strategy (in the YAML template) or per-run (via `--sandbox` CLI flag). Different strategies can use different backends. A single strategy cannot mix backends within one run.
- All backends implement the same `SandboxProvider` protocol. Adding a new backend means implementing the protocol -- no changes to strategies, engine, or CLI.

### Pluggable Agent Executors

- An `AgentExecutor` protocol abstracts how LLM agents are invoked within a sandbox. Two executors ship in v3:
  - **`counselors`**: Wraps `counselors run` inside the sandbox. Current behavior, preserved.
  - **`direct`**: Calls LLM APIs directly via `litellm`. No `counselors` dependency. More control over tool configuration and output parsing. Optional dependency.
- Executor is configured per-agent-profile or per-strategy. Default: `counselors`.

### Isolation Topologies

- Each strategy phase declares an **isolation mode** that specifies what each agent can see:
  - `full` -- Agent sees only its own workspace and the prompt. No access to peer outputs. Used for independent research phases.
  - `read-peers` -- Agent gets read-only copies of peer outputs from a previous phase. Used for cross-pollination.
  - `read-all` -- Agent reads all outputs from all prior phases. Used for synthesis.
  - `blackboard` -- Agent has its own private workspace plus read/append or read/write access to a shared blackboard. Used for debate, swarm.
  - `read-blackboard` -- Read-only view of the blackboard. Used for judging.
  - `team` -- Agents on the same team share a blackboard. Isolated from other teams. Used for red/blue team.
  - `cross-team-read` -- Reads opposing team's outputs (read-only). Writes privately. Used for red team attack, blue team defense.
  - `none` -- No isolation. Legacy mode. All agents share the run directory directly.
- The orchestrator implements isolation modes by: creating sandboxes, copying phase outputs into readable paths, mounting shared volumes with the declared access mode, and tearing down sandboxes after phase completion.
- Blackboard writes are **orchestrator-mediated** by default. Agents write to their private workspace. The orchestrator reads the agent's output and appends it to the shared blackboard. Agents never have direct write access to the shared state. This is the strongest guarantee and works with every backend.
- For backends that support filesystem-level enforcement (AgentFS, Daytona), blackboard access can additionally use POSIX permissions or append-only flags as defense-in-depth.

### New Strategies

- **Debate**: Structured turn-based argumentation. Agents present opening statements, conduct N rounds of debate with a shared transcript (append-only blackboard), submit closing statements, and a judge evaluates.
- **Map/Reduce**: A planner decomposes the topic into subtopics. Specialist agents research each subtopic independently (fully isolated). A reducer synthesizes all specialist reports.
- **Red/Blue Team**: Blue team researches and builds arguments (team-internal blackboard). Red team critiques (reads blue output, writes privately). Blue team defends (reads red critiques). Final synthesis.
- Template-defined strategies (debate, map/reduce, red/blue) use the generic template executor. No custom Python code needed. Complex strategies (adversarial, swarm) use Python classes that inherit sandbox/isolation infrastructure from the template.

### State Management

- AgentFS backend provides: SQL-queryable audit trail of all agent tool calls, instant single-file snapshots (`cp agent.db snapshot.db`), `agentfs diff` to review agent changes, built-in KV store for metadata/scores/intermediate state.
- All backends persist agent outputs to the run directory. The manifest tracks sandbox configuration alongside phase state.
- Snapshots are taken after each phase (configurable). On failure, the agent's sandbox state is preserved for debugging.

## DON'T

- Break the existing `council` or `adversarial` strategies. They must work identically to v2 when `--sandbox none` or when no sandbox configuration is provided. Full backward compatibility.
- Force sandbox dependencies on users who don't need them. `local` backend has zero external dependencies. `agentfs` is an optional dependency. `daytona` is an optional dependency. Core ivory-tower installs with `pip install ivory-tower` and works.
- Mix sandbox backends within a single run. All agents in a run use the same backend. Keeps the mental model simple.
- Implement real-time inter-agent communication (pub/sub, websockets). Agents are batch processes. They run, produce output, and stop. The orchestrator coordinates. File-based blackboards are the communication primitive.
- Implement agent tool execution within ivory-tower. Agents use whatever tools their runtime provides (counselors/opencode/claude has web search, file I/O, code execution). Ivory-tower sandboxes the runtime, not individual tools.
- Auto-detect or auto-install sandbox backends. Users explicitly choose their backend. Clear error messages when a backend's dependency is missing.
- Support Windows. macOS and Linux only. AgentFS uses FUSE/NFS + namespaces/sandbox-exec. These are Unix primitives.
- Implement fine-grained ACLs within a single sandbox. Isolation is per-sandbox (one sandbox per agent). Access control between agents is handled by the orchestrator's copy/mount decisions, not by in-sandbox permission systems.
- Build a GUI, TUI, or interactive mode. Batch CLI only. YAML templates are the configuration surface.

## LIKE

- [tursodatabase/agentfs](https://github.com/tursodatabase/agentfs) -- SQLite-backed virtual filesystem for agents. OS-level sandboxing via FUSE + namespaces (Linux) and NFS + sandbox-exec (macOS). Copy-on-write overlay. KV store. Tool call audit trail. Single-file portability.
- [Daytona](https://www.daytona.io/) -- Docker container sandboxes for AI agents. SDK (Python, TypeScript). FUSE volumes for shared state. Per-sandbox network firewall. Sub-90ms warm boot.
- [anthropic-ai/sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) -- Claude Code's open-source OS-level sandbox (Seatbelt/bubblewrap). Domain-allowlisting proxy for network isolation. Apache-2.0.
- [02-STRATEGY-SPEC.md](./02-STRATEGY-SPEC.md) -- The v2 spec this builds on. Strategy protocol, registry, adversarial optimization.
- [Strategy pattern](https://refactoring.guru/design-patterns/strategy) -- Encapsulate a family of algorithms, make them interchangeable.
- [12-factor app config](https://12factor.net/config) -- Defaults in code, overrides via files, final overrides via CLI flags.
- [Kubernetes pod security](https://kubernetes.io/docs/concepts/security/pod-security-standards/) -- Declarative security profiles (privileged, baseline, restricted) as precedent for isolation modes.
- [clig.dev](https://clig.dev/) -- CLI design principles.

## FOR

- **Who**: Developers and researchers running multi-agent research who want (a) confidence that agents don't contaminate each other's work, (b) auditable records of what each agent did, (c) the ability to define custom research strategies without writing Python.
- **Environment**: macOS (primary), Linux (CI/server). Python 3.12+, uv for packaging. Optional: `agentfs` CLI (Rust, installed via curl), `daytona` Python SDK.
- **Domain**: Deep research, technology evaluations, adversarial fact-checking, structured debate, decomposed specialist research.
- **Tech stack**: Python, typer, rich, PyYAML, `counselors` (subprocess), `gepa` (optional), `agentfs` (optional CLI + Python SDK), `daytona` (optional Python SDK), `litellm` (optional).

## ENSURE

### Backward Compatibility

- `ivory research "topic" --strategy council --agents a,b --synthesizer a` runs identically to v2. No sandbox, no YAML, no new dependencies required.
- `ivory resume <run-dir>` on a v2 manifest (no sandbox fields) works without error.
- `ivory status <run-dir>` and `ivory list` display sandbox information when present, omit it when absent.
- All existing tests pass without modification.

### Sandbox Backend Selection

- `ivory research "topic" --agents a,b --synthesizer a --sandbox local` uses directory-based isolation. No external dependencies.
- `ivory research "topic" --agents a,b --synthesizer a --sandbox agentfs` uses AgentFS-backed isolation. Requires `agentfs` CLI on PATH.
- `ivory research "topic" --agents a,b --synthesizer a --sandbox daytona` uses Daytona containers. Requires `daytona` Python SDK installed.
- `ivory research "topic" --agents a,b --synthesizer a --sandbox none` disables sandboxing. Identical to v2 behavior.
- Omitting `--sandbox` defaults to `none` (backward compat). When a YAML template specifies a sandbox backend, the template's setting is used unless overridden by `--sandbox`.
- `--sandbox agentfs` when `agentfs` CLI is not installed: prints `"The agentfs sandbox backend requires AgentFS. Install with: curl -fsSL https://agentfs.ai/install | bash"`, exit 1.
- `--sandbox daytona` when `daytona` SDK is not installed: prints `"The daytona sandbox backend requires the daytona SDK. Install with: uv add daytona"`, exit 1.

### YAML Strategy Templates

- `ivory research "topic" --template council` loads the built-in `strategies/council.yml`.
- `ivory research "topic" --template debate` loads the built-in `strategies/debate.yml`.
- `ivory research "topic" --template ~/.ivory-tower/strategies/my-strategy.yml` loads a user-defined template.
- `ivory research "topic" --template debate --agents a,b --rounds 5 --sandbox agentfs` -- CLI flags override template defaults.
- `ivory templates` prints a table of available templates (built-in from package + user-defined from `~/.ivory-tower/strategies/`).
- Template validation: missing required fields produce specific error messages. Invalid isolation modes produce specific error messages. Unknown phase references produce specific error messages.
- Templates without an `engine` field use the generic template executor. Templates with `engine: ivory_tower.strategies.adversarial.AdversarialStrategy` delegate to that Python class.

### Agent Profiles

- `ivory research "topic" --agents claude:researcher,openai:critic --synthesizer claude:synthesizer` -- colon syntax assigns roles.
- `ivory research "topic" --agents @deep-researcher,@fast-scanner --synthesizer @deep-researcher` -- `@` prefix loads from `~/.ivory-tower/profiles/<name>.yml`.
- `ivory profiles` prints a table of available profiles (from `~/.ivory-tower/profiles/`).
- Agent profiles are optional. Plain agent names (`claude`, `openai`) work as before, using defaults.

### Isolation Enforcement

- **`full` isolation**: Agent A cannot read any file produced by Agent B. Agent A's sandbox contains only the prompt and its own workspace. Verified by: running 2 agents in `full` mode, checking that neither agent's output directory contains files from the other.
- **`read-peers` isolation**: Agent A's sandbox contains read-only copies of all peer outputs from the previous phase. Agent A cannot modify peer outputs. Verified by: checking that peer output files in A's sandbox are identical to originals, and that any modifications by A do not appear in the original locations.
- **`blackboard` isolation**: Agent A's sandbox contains a shared blackboard directory. In `append` mode, A can read all blackboard content and append new files but cannot modify or delete existing files. Verified by: running 2 agents with append-mode blackboard, confirming each can read the other's contributions but not overwrite them.
- **`team` isolation**: Agents on the same team share a blackboard. Agents on different teams cannot see each other's blackboard. Verified by: running a red/blue team scenario, confirming red team agents cannot read blue team's blackboard and vice versa.
- **`none` isolation**: No sandboxing applied. Agents run in the shared run directory exactly as in v2. Verified by: running with `--sandbox none` and confirming identical output to v2.

### AgentFS Backend Specifics

- `agentfs` backend creates `.agentfs/<run-id>-<agent-name>.db` for each agent.
- Each agent runs via `agentfs run --session <run-id>-<agent-name>` which provides OS-level copy-on-write sandbox.
- `--allow` paths are configured from the agent profile's sandbox section.
- After each phase, `agentfs diff <agent-id>` output is saved to `<run-dir>/sandboxes/<agent>/diff.txt`.
- Snapshots: `<run-id>-<agent-name>-phase1.db`, `<run-id>-<agent-name>-phase2.db` etc. saved when `snapshot_after_phase: true`.
- Shared blackboard uses a separate AgentFS database exposed via `agentfs serve mcp` or direct SDK KV operations. The orchestrator mediates all writes.
- `ivory audit <run-dir> <agent>` queries the agent's AgentFS tool call audit trail. Shows tool name, duration, status.

### Daytona Backend Specifics

- `daytona` backend creates one Daytona sandbox per agent via `daytona.create()`.
- Resource limits (CPU, memory, disk) configurable via template or agent profile.
- Network firewall: `network_block_all=True` for untrusted agents. Default: allow outbound (agents need web search).
- Shared blackboard uses Daytona FUSE volumes mounted to each participating sandbox.
- Sandboxes are auto-stopped after phase completion. Auto-deleted after run completion (configurable).
- Labels: `{"ivory-tower": "true", "run-id": "<id>", "agent": "<name>"}` for discovery.

### Local Backend Specifics

- Each agent gets `<run-dir>/sandboxes/<agent-name>/workspace/` as its private workspace.
- `counselors run` is invoked with `cwd` set to the agent's workspace directory and output directed within it.
- Peer outputs are copied (not symlinked) into the sandbox for `read-peers` and `read-all` modes.
- Shared blackboard is a directory under `<run-dir>/volumes/<blackboard-name>/`. Orchestrator copies agent contributions into it between turns.
- No OS-level enforcement. Isolation is conventional (separate directories, separate process invocations). Sufficient for the primary threat model (information isolation, not adversarial security).

### New Strategies

- `ivory research "topic" --template debate --agents a,b --synthesizer a` runs a 4-phase debate: opening statements (full isolation), N debate rounds (blackboard with append-only transcript), closing statements (read-blackboard), judge verdict (read-all).
- `ivory research "topic" --template map-reduce --agents a,b,c --synthesizer a` runs: decompose (single planner), map (one agent per subtopic, full isolation), reduce (synthesizer reads all).
- `ivory research "topic" --template red-blue --agents a,b,c,d --synthesizer a --red-team a,b --blue-team c,d` runs: blue research (team blackboard), red critique (cross-team-read), blue defense (cross-team-read), synthesis (read-all).

### Dry Run

- `--dry-run` with any template shows: strategy name, phases with isolation modes, agent assignments per phase, sandbox backend, blackboard configuration, estimated sandbox count.
- `--dry-run` with `--sandbox agentfs` additionally shows: AgentFS database paths that would be created.
- `--dry-run` with `--sandbox daytona` additionally shows: sandbox resource configuration, network policy.

### Output Structure

```
./research/20260301-143000-a1b2c3/
    manifest.json                          # Includes sandbox config + isolation topology
    topic.md
    strategy.yml                           # Copy of resolved strategy template (if used)

    sandboxes/                             # Per-agent sandbox state (backend-dependent)
        claude/
            workspace/                     # Agent's private working directory
            diff.txt                       # AgentFS diff (agentfs backend only)
            audit.json                     # Tool call audit (agentfs backend only)
        openai/
            workspace/
            diff.txt
            audit.json

    volumes/                               # Shared state (blackboards, phase outputs)
        blackboard/                        # Strategy-defined shared blackboard
            transcript.md                  # Debate transcript, etc.
        phase-outputs/                     # Orchestrator-managed phase output copies
            phase1/
                claude-report.md
                openai-report.md

    phase1/                                # Canonical phase outputs (same as v2)
        claude-report.md
        openai-report.md
    phase2/
        claude-refined.md
        openai-refined.md
    phase3/
        final-report.md

    snapshots/                             # AgentFS snapshots (agentfs backend only)
        claude-after-phase1.db
        claude-after-phase2.db
        openai-after-phase1.db
        openai-after-phase2.db

    logs/                                  # Debug logs
```

## TRUST

- [autonomous] Sandbox directory layout and naming conventions.
- [autonomous] YAML template schema (field names, nesting, defaults).
- [autonomous] Agent profile schema and loading logic.
- [autonomous] Generic template executor implementation (phase sequencing, isolation mode dispatch).
- [autonomous] Local backend implementation (directory creation, file copying, process invocation).
- [autonomous] AgentFS backend implementation (database creation, `agentfs run` invocation, snapshot logic).
- [autonomous] Blackboard implementation (orchestrator-mediated append, file-based transcript).
- [autonomous] Manifest extensions for sandbox state.
- [autonomous] CLI flag parsing for `--sandbox`, `--template`, `--profile`, `--rounds`.
- [autonomous] Built-in YAML templates for council, adversarial, debate, map-reduce, red-blue.
- [autonomous] Test structure and mock strategies.
- [ask] New sandbox backends beyond local/agentfs/daytona.
- [ask] Changing isolation modes or adding new ones.
- [ask] Changing blackboard enforcement from orchestrator-mediated to direct agent access.
- [ask] Adding real-time inter-agent communication (websockets, message queues).
- [ask] Adding network isolation to the local backend (via sandbox-runtime).
- [ask] Adding a web UI or TUI for strategy visualization.
- [ask] Changing the YAML template schema in ways that break existing templates.
- [ask] Adding non-research use cases (code generation, pair programming).

---

# User Stories

## US-1: Basic sandboxed research (local backend)

**As** a researcher, **I want** to run a council strategy with directory-based isolation **so that** each agent's research is independent and cannot leak into other agents' work.

```bash
ivory research "Impact of quantum computing on cryptography" \
  --strategy council \
  --agents claude,openai,gemini \
  --synthesizer claude \
  --sandbox local
```

**Acceptance criteria:**
- Each agent's `counselors run` executes with `cwd` set to `sandboxes/<agent>/workspace/`.
- Phase 1 outputs land in each agent's sandbox, then are copied to `phase1/` by the orchestrator.
- Phase 2: each agent's sandbox receives read-only copies of all peer Phase 1 outputs. The originals are not modified.
- Phase 3: synthesizer's sandbox receives read-only copies of all Phase 2 outputs.
- `manifest.json` records `"sandbox": {"backend": "local"}` and per-agent sandbox paths.
- Final `phase3/final-report.md` is identical in content quality to an unsandboxed run.

## US-2: AgentFS-backed research with audit trail

**As** a researcher who wants full observability, **I want** to run adversarial optimization with AgentFS **so that** I get SQL-queryable audit logs, instant snapshots, and `agentfs diff` for every agent.

```bash
ivory research "AI safety approaches compared" \
  --strategy adversarial \
  --agents claude,openai \
  --synthesizer claude \
  --sandbox agentfs
```

**Acceptance criteria:**
- `.agentfs/<run-id>-claude.db` and `.agentfs/<run-id>-openai.db` are created.
- Each GEPA optimization round runs inside `agentfs run --session <id>`.
- After Phase 1 (seed), snapshots are saved: `snapshots/<agent>-after-seed.db`.
- After Phase 2 (optimization), snapshots are saved: `snapshots/<agent>-after-optimize.db`.
- `ivory audit <run-dir> claude` prints the tool call timeline from Claude's AgentFS database.
- `sandboxes/claude/diff.txt` shows all files Claude created/modified relative to the base.
- Optimization log includes AgentFS session IDs for reproducibility.

## US-3: Custom debate strategy via YAML template

**As** a power user, **I want** to define a structured debate strategy in YAML without writing any Python **so that** I can experiment with different multi-agent interaction patterns.

```yaml
# ~/.ivory-tower/strategies/my-debate.yml
strategy:
  name: my-debate
  description: "3-round structured debate with strict transcript"
  version: 1

phases:
  - name: opening
    description: "Each agent presents their initial position"
    isolation: full
    agents: all
    output: "{agent}-opening.md"

  - name: rounds
    description: "Debate rounds with shared transcript"
    isolation: blackboard
    agents: all
    rounds: 3
    blackboard:
      name: transcript
      file: "debate-transcript.md"
      access: append
    output: "{agent}-round-{round}.md"

  - name: closing
    description: "Final positions"
    isolation: read-blackboard
    agents: all
    blackboard:
      name: transcript
      access: read
    output: "{agent}-closing.md"

  - name: verdict
    description: "Judge evaluates the full debate"
    isolation: read-all
    agents: [synthesizer]
    input_from: [opening, rounds, closing]
    output: "verdict.md"

defaults:
  sandbox:
    backend: local
  agents:
    min: 2
    max: 4
```

```bash
ivory research "Is Rust better than Go for systems programming?" \
  --template ~/.ivory-tower/strategies/my-debate.yml \
  --agents claude,openai \
  --synthesizer gemini
```

**Acceptance criteria:**
- Template is parsed and validated before execution begins.
- 4 phases execute in order: opening, 3 rounds, closing, verdict.
- During rounds, each agent sees the growing `debate-transcript.md` but cannot delete or overwrite previous entries.
- The orchestrator appends each agent's round output to the transcript between turns.
- The verdict agent reads the complete transcript plus all opening/closing statements.
- `manifest.json` records the resolved template, all phases, and their isolation modes.

## US-4: Map/Reduce decomposition

**As** a researcher studying a broad topic, **I want** the system to decompose it into subtopics and assign specialist agents **so that** each subtopic gets deep, focused research.

```bash
ivory research "Comprehensive survey of modern database architectures" \
  --template map-reduce \
  --agents claude,openai,gemini \
  --synthesizer claude \
  --sandbox agentfs
```

**Acceptance criteria:**
- Phase 1 (decompose): A single planner agent produces `subtopics.json` -- a JSON array of subtopic strings.
- Phase 2 (map): One sandbox is created per subtopic. Agents are assigned round-robin across subtopics. Each mapper agent researches its subtopic in full isolation.
- Phase 3 (reduce): The synthesizer reads all mapper outputs and produces a unified report.
- If the planner produces 6 subtopics with 3 agents, each agent handles 2 subtopics (sequentially or in parallel, configurable).

## US-5: Red/Blue team with team-internal collaboration

**As** a researcher investigating a controversial topic, **I want** a red team to attack and a blue team to defend **so that** the final report is stress-tested from multiple angles.

```bash
ivory research "Should companies adopt microservices over monoliths?" \
  --template red-blue \
  --agents claude,openai,gemini,deepseek \
  --synthesizer claude \
  --red-team claude,openai \
  --blue-team gemini,deepseek \
  --sandbox local
```

**Acceptance criteria:**
- Blue team agents share a team blackboard during initial research. They can coordinate.
- Red team agents share a separate team blackboard. They can coordinate their attack.
- Red team reads blue team's published research (cross-team-read) but cannot read blue's internal blackboard.
- Blue team reads red team's critiques (cross-team-read) but cannot read red's internal blackboard.
- Final synthesis reads everything from all phases.

## US-6: Agent profiles for repeated use

**As** a frequent user, **I want** to define agent profiles once and reuse them across strategies **so that** I don't repeat configuration.

```yaml
# ~/.ivory-tower/profiles/deep-researcher.yml
name: deep-researcher
role: researcher
model: claude-sonnet-4-20250514
system_prompt: |
  You are a meticulous researcher. Always cite primary sources.
  Cross-reference claims from multiple sources before including them.
  When uncertain, explicitly state your confidence level.
executor: counselors
tools:
  - web_search
  - file_read
  - file_write
sandbox:
  allow_paths:
    - "~/.config"
  resources:
    timeout_seconds: 900
```

```bash
ivory research "topic" \
  --agents @deep-researcher,@fast-scanner \
  --synthesizer @deep-researcher \
  --sandbox agentfs
```

**Acceptance criteria:**
- `@deep-researcher` loads the YAML profile and applies model, system prompt, executor, tools, and sandbox overrides.
- The agent's system prompt is passed to `counselors run` (or the direct executor).
- The agent's sandbox `allow_paths` are passed to the backend (e.g., `agentfs run --allow ~/.config`).
- `ivory profiles` lists all profiles from `~/.ivory-tower/profiles/`.

## US-7: Daytona backend for full container isolation

**As** a team lead running research in CI/CD, **I want** each agent in a Docker container with resource limits and network firewall **so that** agents cannot interfere with each other or the host.

```bash
ivory research "topic" \
  --strategy council \
  --agents claude,openai \
  --synthesizer claude \
  --sandbox daytona
```

**Acceptance criteria:**
- Each agent runs in a separate Daytona sandbox (Docker container).
- Default resources: 2 vCPU, 4GB RAM, 8GB disk per sandbox.
- Network: outbound allowed by default (for web search). Configurable per template.
- Shared phase outputs transferred via Daytona FUSE volumes.
- Sandboxes auto-stop after phase completion. Auto-delete after run completion.
- `manifest.json` records Daytona sandbox IDs and resource configuration.

## US-8: Backward compatibility -- no sandbox

**As** an existing user, **I want** `ivory research` to work exactly as before when I don't specify any sandbox options **so that** upgrading doesn't break my workflow.

```bash
ivory research "topic" --strategy council --agents a,b --synthesizer a
# Identical to v2. No sandboxing. No new directories.
```

**Acceptance criteria:**
- No `sandboxes/`, `volumes/`, or `snapshots/` directories created.
- No sandbox-related fields in `manifest.json` (or present but null).
- Output structure identical to v2.
- All v2 tests pass unmodified.

## US-9: Audit an AgentFS-sandboxed run

**As** a researcher debugging unexpected results, **I want** to query what tools each agent used and what files they modified **so that** I can understand agent behavior after the fact.

```bash
# After a completed run
ivory audit research/20260301-143000-a1b2c3/ claude

# Output:
# Agent: claude (session: 20260301-143000-a1b2c3-claude)
# Database: .agentfs/20260301-143000-a1b2c3-claude.db
#
# Tool Call Timeline:
# ID  TOOL          STATUS   DURATION  STARTED
# 12  web_search    success    1200ms  2026-03-01 14:30:45
# 11  read_file     success      50ms  2026-03-01 14:30:40
# 10  write_file    success      30ms  2026-03-01 14:30:38
# ...
#
# Files Modified (vs base):
# M  src/analysis.md
# A  output/report.md
# A  output/sources.json
```

**Acceptance criteria:**
- `ivory audit` reads the AgentFS database for the specified agent.
- Displays tool call timeline (name, status, duration, timestamp).
- Displays file diff summary (added, modified, deleted).
- Errors gracefully if the run was not sandboxed with AgentFS.

---

# Architecture

## Module Structure

```
src/ivory_tower/
    __init__.py
    cli.py                             # Extended: --sandbox, --template, --profile flags
    engine.py                          # Extended: sandbox lifecycle, template resolution
    counselors.py                      # Unchanged
    models.py                          # Extended: sandbox config, agent profiles in manifest
    prompts.py                         # Unchanged (strategies define their own prompts)
    run.py                             # Minor: sandbox directory creation

    sandbox/
        __init__.py                    # SandboxProvider registry + get_provider()
        types.py                       # Protocol definitions, dataclasses
        local.py                       # LocalSandboxProvider
        agentfs.py                     # AgentFSSandboxProvider
        daytona.py                     # DaytonaSandboxProvider
        blackboard.py                  # Blackboard (shared state management)

    executor/
        __init__.py                    # AgentExecutor registry + get_executor()
        types.py                       # Protocol definitions
        counselors_exec.py             # CounselorsExecutor (wraps counselors CLI)
        direct.py                      # DirectExecutor (litellm API calls)

    templates/
        __init__.py                    # Template loading, validation, resolution
        loader.py                      # YAML loading + schema validation
        executor.py                    # GenericTemplateExecutor (runs YAML-defined strategies)

    profiles/
        __init__.py                    # Profile loading from ~/.ivory-tower/profiles/

    strategies/
        __init__.py                    # Registry (unchanged, plus template-based strategies)
        base.py                        # ResearchStrategy Protocol (unchanged)
        council.py                     # CouncilStrategy (refactored to use sandbox)
        adversarial.py                 # AdversarialStrategy (refactored to use sandbox)
        debate.py                      # DebateStrategy (template-backed, thin wrapper)
        map_reduce.py                  # MapReduceStrategy (template-backed, thin wrapper)
        red_blue.py                    # RedBlueStrategy (template-backed, thin wrapper)

    data/                              # Bundled YAML templates (shipped with package)
        strategies/
            council.yml
            adversarial.yml
            debate.yml
            map-reduce.yml
            red-blue.yml

~/.ivory-tower/                        # User configuration (created on first use)
    strategies/                        # User-defined strategy templates
    profiles/                          # User-defined agent profiles
```

## Sandbox Protocol

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass
class NetworkPolicy:
    allow_outbound: bool = True
    allowed_domains: list[str] | None = None    # None = unrestricted
    blocked_domains: list[str] = field(default_factory=list)


@dataclass
class ResourceLimits:
    cpu_cores: float = 1.0
    memory_mb: int = 1024
    disk_mb: int = 512
    timeout_seconds: int = 600


@dataclass
class SandboxConfig:
    backend: str = "none"                       # "none", "local", "agentfs", "daytona"
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    resources: ResourceLimits | None = None
    allow_paths: list[str] = field(default_factory=list)
    snapshot_after_phase: bool = False
    snapshot_on_failure: bool = True
    encryption_key: str | None = None           # AgentFS only
    encryption_cipher: str | None = None        # AgentFS only


@runtime_checkable
class Sandbox(Protocol):
    """An isolated execution environment for a single agent."""
    id: str
    agent_name: str
    workspace_dir: Path

    def execute(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> ExecutionResult: ...

    def write_file(self, path: str, content: str | bytes) -> None: ...
    def read_file(self, path: str) -> str: ...
    def list_files(self, path: str = "/") -> list[str]: ...
    def file_exists(self, path: str) -> bool: ...
    def copy_in(self, src: Path, dst: str) -> None: ...
    def copy_out(self, src: str, dst: Path) -> None: ...
    def snapshot(self, label: str) -> Path | None: ...
    def diff(self) -> str | None: ...
    def destroy(self) -> None: ...


@runtime_checkable
class SharedVolume(Protocol):
    """A shared filesystem region mountable into multiple sandboxes."""
    id: str
    path: Path

    def write_file(self, path: str, content: str | bytes) -> None: ...
    def read_file(self, path: str) -> str: ...
    def append_file(self, path: str, content: str) -> None: ...
    def list_files(self, path: str = "/") -> list[str]: ...


@runtime_checkable
class SandboxProvider(Protocol):
    """Factory for creating sandboxes and shared volumes."""
    name: str

    def create_sandbox(
        self,
        agent_name: str,
        run_id: str,
        run_dir: Path,
        config: SandboxConfig,
        base_dir: Path | None = None,           # For CoW overlay (agentfs)
    ) -> Sandbox: ...

    def create_shared_volume(
        self,
        name: str,
        run_id: str,
        run_dir: Path,
    ) -> SharedVolume: ...

    def destroy_all(self, run_id: str) -> None: ...

    @staticmethod
    def is_available() -> bool: ...


@dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
```

## Sandbox Provider Registry

```python
PROVIDERS: dict[str, type[SandboxProvider]] = {
    "none": NullSandboxProvider,
    "local": LocalSandboxProvider,
    "agentfs": AgentFSSandboxProvider,
    "daytona": DaytonaSandboxProvider,
}

def get_provider(name: str) -> SandboxProvider:
    """Return an instantiated sandbox provider by name.

    Raises ValueError for unknown providers.
    Raises RuntimeError if the provider's dependencies are not installed.
    """
    cls = PROVIDERS.get(name)
    if cls is None:
        available = ", ".join(sorted(PROVIDERS.keys()))
        raise ValueError(f"Unknown sandbox backend '{name}'. Available: {available}")
    if not cls.is_available():
        raise RuntimeError(_install_message(name))
    return cls()
```

## Agent Executor Protocol

```python
@runtime_checkable
class AgentExecutor(Protocol):
    """Abstraction over how LLM agents are invoked within a sandbox."""
    name: str

    def run(
        self,
        sandbox: Sandbox,
        agent_name: str,
        prompt: str,
        output_dir: str,
        model: str | None = None,
        system_prompt: str | None = None,
        verbose: bool = False,
    ) -> AgentOutput: ...


@dataclass
class AgentOutput:
    report_path: str           # Relative path within sandbox to the agent's output
    raw_output: str            # Full text of the agent's response
    duration_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)
```

### CounselorsExecutor

```python
class CounselorsExecutor:
    name = "counselors"

    def run(self, sandbox, agent_name, prompt, output_dir, **kwargs):
        # Write prompt to sandbox
        sandbox.write_file("prompt.md", prompt)

        # Execute counselors inside the sandbox
        result = sandbox.execute([
            *resolve_counselors_cmd(),
            "run", "-f", "/workspace/prompt.md",
            "--tools", agent_name,
            "--json",
            "-o", f"/workspace/{output_dir}/",
        ], env={"COUNSELORS_VERBOSE": "1"} if kwargs.get("verbose") else None)

        # Read and normalize output
        report_path = _normalize_output(sandbox, output_dir, agent_name)
        report_text = sandbox.read_file(report_path)

        return AgentOutput(
            report_path=report_path,
            raw_output=report_text,
            duration_seconds=result.duration_seconds,
        )
```

### DirectExecutor

```python
class DirectExecutor:
    name = "direct"

    def run(self, sandbox, agent_name, prompt, output_dir, **kwargs):
        # Call LLM API directly (no counselors dependency)
        import litellm

        messages = []
        if kwargs.get("system_prompt"):
            messages.append({"role": "system", "content": kwargs["system_prompt"]})
        messages.append({"role": "user", "content": prompt})

        response = litellm.completion(
            model=kwargs.get("model", agent_name),
            messages=messages,
        )
        report_text = response.choices[0].message.content

        # Write result to sandbox
        report_path = f"{output_dir}/{agent_name}-report.md"
        sandbox.write_file(report_path, report_text)

        return AgentOutput(
            report_path=report_path,
            raw_output=report_text,
            duration_seconds=0,  # litellm doesn't expose timing
        )
```

## Agent Profile Schema

```yaml
# ~/.ivory-tower/profiles/<name>.yml
name: deep-researcher                    # Profile identifier
role: researcher                         # Semantic role (researcher, critic, synthesizer, planner)
model: claude-sonnet-4-20250514                  # LLM model identifier
system_prompt: |                         # Custom system prompt (optional)
  You are a meticulous researcher...
executor: counselors                     # "counselors" or "direct"
tools:                                   # Available tools (informational, passed to executor)
  - web_search
  - file_read
  - file_write
sandbox:                                 # Per-agent sandbox overrides
  allow_paths:                           # Additional writable paths (agentfs --allow)
    - "~/.config"
  resources:                             # Resource limits (daytona backend)
    cpu_cores: 2.0
    memory_mb: 4096
    timeout_seconds: 900
  network:                               # Network policy overrides
    allowed_domains:
      - "api.openai.com"
      - "arxiv.org"
```

### AgentProfile Dataclass

```python
@dataclass
class AgentProfile:
    name: str
    role: str = "researcher"
    model: str | None = None              # None = use agent name as model
    system_prompt: str | None = None
    executor: str = "counselors"
    tools: list[str] = field(default_factory=list)
    sandbox: SandboxConfig | None = None  # Per-agent overrides

    @classmethod
    def from_yaml(cls, path: Path) -> AgentProfile: ...

    @classmethod
    def from_cli_shorthand(cls, spec: str) -> AgentProfile:
        """Parse CLI shorthand: 'model:role', 'model', or '@profile-name'."""
        if spec.startswith("@"):
            return cls.load_named(spec[1:])
        if ":" in spec:
            model, role = spec.split(":", 1)
            return cls(name=model, role=role, model=model)
        return cls(name=spec, model=spec)

    @classmethod
    def load_named(cls, name: str) -> AgentProfile:
        """Load from ~/.ivory-tower/profiles/<name>.yml."""
        path = Path.home() / ".ivory-tower" / "profiles" / f"{name}.yml"
        if not path.exists():
            raise FileNotFoundError(f"Agent profile not found: {path}")
        return cls.from_yaml(path)
```

## YAML Strategy Template Schema

```yaml
# Full schema with all fields shown

strategy:
  name: string                           # REQUIRED. Unique strategy identifier.
  description: string                    # REQUIRED. One-line description.
  version: int                           # REQUIRED. Schema version (currently 1).
  engine: string | null                  # OPTIONAL. Python class path for custom execution logic.
                                         # e.g., "ivory_tower.strategies.adversarial.AdversarialStrategy"
                                         # When absent, the generic template executor handles all phases.

teams:                                   # OPTIONAL. Team definitions for team-based strategies.
  <team-name>:
    role: string                         # Team role identifier (e.g., "attacker", "defender")
    description: string                  # Human-readable description

phases:                                  # REQUIRED. Ordered list of execution phases.
  - name: string                         # REQUIRED. Phase identifier (unique within strategy).
    description: string                  # REQUIRED. Human-readable description.
    isolation: enum                      # REQUIRED. One of: full, read-peers, read-all,
                                         #   blackboard, read-blackboard, team, cross-team-read, none
    agents: enum | list                  # REQUIRED. Who participates:
                                         #   "all" -- all agents
                                         #   [synthesizer] -- only the synthesizer
                                         #   [planner] -- only the first agent (map/reduce decompose)
                                         #   [<team-name>] -- only agents on that team
                                         #   "dynamic" -- agents determined at runtime (fan-out)
    output: string                       # REQUIRED. Output filename pattern.
                                         #   Supports: {agent}, {round}, {subtopic}, {peer}
    rounds: int | null                   # OPTIONAL. Number of rounds (for iterative phases).
    input_from: string | list | null     # OPTIONAL. Phase name(s) whose outputs feed into this phase.
    fan_out: string | null               # OPTIONAL. Phase whose output determines dynamic agent count.
    blackboard:                          # OPTIONAL. Shared state configuration.
      name: string                       # Blackboard identifier
      file: string | null                # Single shared file (for transcript-style blackboards)
      dir: string | null                 # Shared directory (for multi-file blackboards)
      access: enum                       # "read", "append", "rw"
    sandbox:                             # OPTIONAL. Per-phase sandbox overrides.
      snapshot_after: bool
      resources: ...

defaults:                                # OPTIONAL. Default values for the strategy.
  sandbox:
    backend: string                      # Default sandbox backend
    network: NetworkPolicy
    resources: ResourceLimits
    snapshot_after_phase: bool
    snapshot_on_failure: bool
  agents:
    min: int                             # Minimum number of agents required
    max: int | null                      # Maximum (null = unlimited)
    executor: string                     # Default executor
    tools: list[string]                  # Default tool set
  rounds: int                            # Default round count for iterative phases
```

## Template Resolution Order

Configuration is resolved in this priority order (highest to lowest):

1. **CLI flags** (`--sandbox agentfs`, `--agents a,b`, `--rounds 5`)
2. **Agent profile overrides** (`@deep-researcher` profile's sandbox section)
3. **YAML template** (`--template debate` or `--template path/to/file.yml`)
4. **Strategy class defaults** (hardcoded in Python strategy implementations)
5. **Global defaults** (`--sandbox none`, executor `counselors`, no isolation)

```python
def resolve_config(
    cli_args: dict,
    template: StrategyTemplate | None,
    agent_profiles: dict[str, AgentProfile],
    strategy_defaults: dict,
) -> ResolvedConfig:
    """Merge configuration from all sources."""
    # Start with global defaults
    config = deepcopy(GLOBAL_DEFAULTS)
    # Layer strategy class defaults
    config = deep_merge(config, strategy_defaults)
    # Layer template
    if template:
        config = deep_merge(config, template.to_config())
    # Layer agent profile overrides (per-agent, not global)
    for name, profile in agent_profiles.items():
        if profile.sandbox:
            config.agent_overrides[name] = profile.sandbox
    # Layer CLI flags (highest priority)
    config = deep_merge(config, cli_args_to_config(cli_args))
    return config
```

## Isolation Mode Implementation

The orchestrator translates isolation modes into sandbox operations:

```python
def setup_phase_isolation(
    phase: PhaseConfig,
    sandboxes: dict[str, Sandbox],
    volumes: dict[str, SharedVolume],
    previous_outputs: dict[str, dict[str, Path]],  # phase_name -> {agent: output_path}
) -> None:
    """Configure sandbox isolation for a phase."""

    match phase.isolation:
        case "full":
            # Nothing to do -- sandboxes are already isolated
            pass

        case "read-peers":
            # Copy previous phase outputs into each agent's sandbox
            prev = previous_outputs[phase.input_from]
            for agent_name, sandbox in sandboxes.items():
                for peer_name, output_path in prev.items():
                    if peer_name != agent_name:
                        sandbox.copy_in(output_path, f"peers/{peer_name}.md")

        case "read-all":
            # Copy all previous outputs into the sandbox
            for phase_name in (phase.input_from if isinstance(phase.input_from, list)
                               else [phase.input_from]):
                for agent_name, output_path in previous_outputs[phase_name].items():
                    for sandbox in sandboxes.values():
                        sandbox.copy_in(output_path, f"inputs/{phase_name}/{agent_name}.md")

        case "blackboard":
            bb_config = phase.blackboard
            volume = volumes[bb_config.name]
            # Orchestrator manages writes -- agents write to private workspace,
            # orchestrator appends to volume after each turn.
            # Pre-populate sandbox with current blackboard state (read-only copy)
            for sandbox in sandboxes.values():
                bb_content = volume.read_file(bb_config.file) if bb_config.file else ""
                sandbox.write_file(f"blackboard/{bb_config.file}", bb_content)

        case "read-blackboard":
            bb_config = phase.blackboard
            volume = volumes[bb_config.name]
            for sandbox in sandboxes.values():
                bb_content = volume.read_file(bb_config.file) if bb_config.file else ""
                sandbox.write_file(f"blackboard/{bb_config.file}", bb_content)

        case "team":
            # Mount team-specific volume; team members share, others excluded
            for agent_name, sandbox in sandboxes.items():
                team = _get_agent_team(agent_name, phase)
                if team:
                    team_volume = volumes[f"team-{team}"]
                    # Copy current team blackboard into sandbox
                    for f in team_volume.list_files():
                        sandbox.copy_in(Path(team_volume.path / f), f"team-board/{f}")

        case "cross-team-read":
            # Copy opposing team's phase outputs as read-only
            prev = previous_outputs[phase.input_from]
            for agent_name, sandbox in sandboxes.items():
                agent_team = _get_agent_team(agent_name, phase)
                for peer_name, output_path in prev.items():
                    peer_team = _get_agent_team(peer_name, phase)
                    if peer_team != agent_team:
                        sandbox.copy_in(output_path, f"opposing/{peer_name}.md")

        case "none":
            pass
```

## Blackboard Implementation

```python
@dataclass
class FileBlackboard:
    """Orchestrator-mediated file-based blackboard."""
    volume: SharedVolume
    file_name: str | None        # Single file (transcript mode)
    access_mode: str             # "read", "append", "rw"

    def get_content(self) -> str:
        """Read current blackboard content."""
        if self.file_name:
            return self.volume.read_file(self.file_name)
        # Directory mode: concatenate all files
        files = sorted(self.volume.list_files())
        return "\n\n---\n\n".join(
            self.volume.read_file(f) for f in files
        )

    def append(self, agent_name: str, round_num: int, content: str) -> None:
        """Orchestrator appends agent's contribution to the blackboard.

        This is the ONLY write path. Agents never write directly.
        """
        if self.access_mode == "read":
            raise PermissionError("Blackboard is read-only in this phase")

        if self.file_name:
            # Transcript mode: append to single file
            header = f"\n\n## {agent_name} -- Round {round_num}\n\n"
            self.volume.append_file(self.file_name, header + content)
        else:
            # Directory mode: write a new file
            fname = f"{round_num:02d}-{agent_name}.md"
            self.volume.write_file(fname, content)

    def snapshot(self, label: str) -> str:
        """Return current content for archival."""
        return self.get_content()
```

## GenericTemplateExecutor

Template-defined strategies (those without a custom `engine` class) use this executor:

```python
class GenericTemplateExecutor:
    """Executes a strategy defined entirely in YAML.

    Handles phase sequencing, isolation setup, blackboard management,
    round iteration, and dynamic fan-out. No custom Python needed.
    """

    def __init__(self, template: StrategyTemplate):
        self.template = template

    def run(self, run_dir: Path, config: RunConfig, manifest: Manifest) -> Manifest:
        provider = get_provider(config.sandbox_backend)
        executor = get_executor(config.executor)

        sandboxes: dict[str, Sandbox] = {}
        volumes: dict[str, SharedVolume] = {}
        outputs: dict[str, dict[str, Path]] = {}   # phase -> {agent: output_path}

        try:
            # Create agent sandboxes
            for agent in config.agents:
                sandboxes[agent] = provider.create_sandbox(
                    agent_name=agent, run_id=manifest.run_id,
                    run_dir=run_dir, config=config.sandbox_config,
                )

            # Create shared volumes for blackboards
            for phase in self.template.phases:
                if phase.blackboard:
                    bb = phase.blackboard
                    if bb.name not in volumes:
                        volumes[bb.name] = provider.create_shared_volume(
                            name=bb.name, run_id=manifest.run_id, run_dir=run_dir,
                        )
                        # Initialize blackboard file if specified
                        if bb.file:
                            volumes[bb.name].write_file(bb.file, "")

            # Execute phases in order
            for phase in self.template.phases:
                phase_agents = self._resolve_phase_agents(phase, config, outputs)
                phase_sandboxes = {a: sandboxes[a] for a in phase_agents}

                if phase.rounds:
                    outputs[phase.name] = self._run_iterative_phase(
                        phase, phase_sandboxes, volumes, outputs,
                        executor, config, run_dir, manifest,
                    )
                else:
                    outputs[phase.name] = self._run_single_phase(
                        phase, phase_sandboxes, volumes, outputs,
                        executor, config, run_dir, manifest,
                    )

        finally:
            # Cleanup
            for sandbox in sandboxes.values():
                sandbox.destroy()
            provider.destroy_all(manifest.run_id)

        return manifest

    def _run_single_phase(self, phase, sandboxes, volumes, outputs,
                          executor, config, run_dir, manifest):
        """Run a non-iterative phase (research, synthesis, etc.)."""
        setup_phase_isolation(phase, sandboxes, volumes, outputs)

        phase_outputs = {}
        prompt = self._build_phase_prompt(phase, config, outputs)

        # Run all agents in parallel (ThreadPoolExecutor)
        with ThreadPoolExecutor(max_workers=len(sandboxes)) as pool:
            futures = {}
            for agent_name, sandbox in sandboxes.items():
                agent_prompt = self._personalize_prompt(prompt, agent_name, sandbox)
                futures[agent_name] = pool.submit(
                    executor.run, sandbox, agent_name, agent_prompt,
                    f"output/{phase.name}",
                )
            for agent_name, future in futures.items():
                result = future.result()
                # Copy output from sandbox to canonical location
                output_filename = phase.output.format(agent=agent_name)
                canonical = run_dir / phase.name / output_filename
                canonical.parent.mkdir(parents=True, exist_ok=True)
                sandboxes[agent_name].copy_out(result.report_path, canonical)
                phase_outputs[agent_name] = canonical

        return phase_outputs

    def _run_iterative_phase(self, phase, sandboxes, volumes, outputs,
                             executor, config, run_dir, manifest):
        """Run a round-based phase (debate rounds, optimization loops)."""
        blackboard = FileBlackboard(
            volume=volumes[phase.blackboard.name],
            file_name=phase.blackboard.file,
            access_mode=phase.blackboard.access,
        ) if phase.blackboard else None

        phase_outputs = {}
        num_rounds = phase.rounds or config.rounds or 3

        for round_num in range(1, num_rounds + 1):
            # Refresh blackboard content in each sandbox
            if blackboard:
                current_bb = blackboard.get_content()
                for sandbox in sandboxes.values():
                    sandbox.write_file(
                        f"blackboard/{phase.blackboard.file}",
                        current_bb,
                    )

            # Run agents sequentially within each round (turn-based for debate)
            for agent_name, sandbox in sandboxes.items():
                prompt = self._build_round_prompt(
                    phase, config, agent_name, round_num, outputs, blackboard
                )
                result = executor.run(
                    sandbox, agent_name, prompt, f"output/{phase.name}/round-{round_num:02d}",
                )

                # Copy output to canonical location
                output_filename = phase.output.format(agent=agent_name, round=round_num)
                canonical = run_dir / phase.name / output_filename
                canonical.parent.mkdir(parents=True, exist_ok=True)
                sandbox.copy_out(result.report_path, canonical)

                # Orchestrator appends to blackboard (agent never writes directly)
                if blackboard and phase.blackboard.access in ("append", "rw"):
                    report_text = canonical.read_text()
                    blackboard.append(agent_name, round_num, report_text)

                phase_outputs[f"{agent_name}-round-{round_num}"] = canonical

        return phase_outputs
```

## Local Sandbox Provider

```python
class LocalSandboxProvider:
    name = "local"

    def create_sandbox(self, agent_name, run_id, run_dir, config, base_dir=None):
        workspace = run_dir / "sandboxes" / agent_name / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        return LocalSandbox(
            id=f"{run_id}-{agent_name}",
            agent_name=agent_name,
            workspace_dir=workspace,
        )

    def create_shared_volume(self, name, run_id, run_dir):
        vol_dir = run_dir / "volumes" / name
        vol_dir.mkdir(parents=True, exist_ok=True)
        return LocalSharedVolume(id=f"{run_id}-{name}", path=vol_dir)

    def destroy_all(self, run_id):
        pass  # Directories persist for inspection

    @staticmethod
    def is_available():
        return True


class LocalSandbox:
    def __init__(self, id, agent_name, workspace_dir):
        self.id = id
        self.agent_name = agent_name
        self.workspace_dir = workspace_dir

    def execute(self, command, env=None, cwd=None):
        import subprocess, time
        start = time.monotonic()
        work_dir = Path(cwd) if cwd else self.workspace_dir
        result = subprocess.run(
            command, cwd=work_dir, capture_output=True, text=True,
            env={**os.environ, **(env or {})},
        )
        elapsed = time.monotonic() - start
        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=elapsed,
        )

    def write_file(self, path, content):
        full = self.workspace_dir / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            full.write_bytes(content)
        else:
            full.write_text(content)

    def read_file(self, path):
        return (self.workspace_dir / path).read_text()

    def list_files(self, path="/"):
        target = self.workspace_dir / path.lstrip("/")
        if not target.exists():
            return []
        return [str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()]

    def file_exists(self, path):
        return (self.workspace_dir / path).exists()

    def copy_in(self, src, dst):
        full_dst = self.workspace_dir / dst
        full_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, full_dst)

    def copy_out(self, src, dst):
        full_src = self.workspace_dir / src
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full_src, dst)

    def snapshot(self, label):
        return None  # Local backend doesn't support snapshots

    def diff(self):
        return None  # Local backend doesn't support diffs

    def destroy(self):
        pass  # Keep for inspection
```

## AgentFS Sandbox Provider

```python
class AgentFSSandboxProvider:
    name = "agentfs"

    def create_sandbox(self, agent_name, run_id, run_dir, config, base_dir=None):
        agent_id = f"{run_id}-{agent_name}"

        # Initialize AgentFS with CoW overlay on base directory
        cmd = ["agentfs", "init", agent_id]
        if base_dir:
            cmd.extend(["--base", str(base_dir)])
        if config.encryption_key:
            cmd.extend(["--key", config.encryption_key])
        if config.encryption_cipher:
            cmd.extend(["--cipher", config.encryption_cipher])
        subprocess.run(cmd, check=True)

        return AgentFSSandbox(
            id=agent_id,
            agent_name=agent_name,
            workspace_dir=Path(f".agentfs/{agent_id}.db"),
            config=config,
            run_dir=run_dir,
        )

    def create_shared_volume(self, name, run_id, run_dir):
        vol_id = f"{run_id}-shared-{name}"
        subprocess.run(["agentfs", "init", vol_id], check=True)
        return AgentFSSharedVolume(
            id=vol_id,
            path=Path(f".agentfs/{vol_id}.db"),
        )

    def destroy_all(self, run_id):
        # AgentFS databases persist for inspection/audit
        pass

    @staticmethod
    def is_available():
        return shutil.which("agentfs") is not None


class AgentFSSandbox:
    def __init__(self, id, agent_name, workspace_dir, config, run_dir):
        self.id = id
        self.agent_name = agent_name
        self.workspace_dir = workspace_dir
        self.config = config
        self.run_dir = run_dir
        self._session_id = id

    def execute(self, command, env=None, cwd=None):
        import time
        start = time.monotonic()

        cmd = ["agentfs", "run", "--session", self._session_id]
        for allow_path in self.config.allow_paths:
            cmd.extend(["--allow", str(Path(allow_path).expanduser())])
        if self.config.encryption_key:
            cmd.extend(["--key", self.config.encryption_key])
        if self.config.encryption_cipher:
            cmd.extend(["--cipher", self.config.encryption_cipher])
        cmd.append("--")
        cmd.extend(command)

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            env={**os.environ, **(env or {})},
        )
        elapsed = time.monotonic() - start
        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=elapsed,
        )

    def write_file(self, path, content):
        subprocess.run(
            ["agentfs", "fs", self.id, "write", path, content],
            check=True,
        )

    def read_file(self, path):
        result = subprocess.run(
            ["agentfs", "fs", self.id, "cat", path],
            capture_output=True, text=True, check=True,
        )
        return result.stdout

    def copy_in(self, src, dst):
        content = Path(src).read_text()
        self.write_file(dst, content)

    def copy_out(self, src, dst):
        content = self.read_file(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content)

    def snapshot(self, label):
        snapshot_dir = self.run_dir / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"{self.agent_name}-{label}.db"
        db_path = Path(f".agentfs/{self.id}.db")
        if db_path.exists():
            shutil.copy2(db_path, snapshot_path)
            return snapshot_path
        return None

    def diff(self):
        result = subprocess.run(
            ["agentfs", "diff", self.id],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            diff_dir = self.run_dir / "sandboxes" / self.agent_name
            diff_dir.mkdir(parents=True, exist_ok=True)
            diff_path = diff_dir / "diff.txt"
            diff_path.write_text(result.stdout)
            return result.stdout
        return None

    def destroy(self):
        pass  # AgentFS databases persist for audit
```

## Daytona Sandbox Provider

```python
class DaytonaSandboxProvider:
    name = "daytona"

    def __init__(self):
        from daytona import Daytona
        self.client = Daytona()
        self._sandboxes: dict[str, Any] = {}

    def create_sandbox(self, agent_name, run_id, run_dir, config, base_dir=None):
        from daytona import CreateSandboxFromSnapshotParams, Resources

        resources = None
        if config.resources:
            resources = Resources(
                cpu=int(config.resources.cpu_cores),
                memory=int(config.resources.memory_mb / 1024),
                disk=int(config.resources.disk_mb / 1024),
            )

        sandbox = self.client.create(CreateSandboxFromSnapshotParams(
            language="python",
            resources=resources,
            network_block_all=not config.network.allow_outbound,
            auto_stop_interval=(config.resources.timeout_seconds // 60
                                if config.resources else 15),
            labels={
                "ivory-tower": "true",
                "run-id": run_id,
                "agent": agent_name,
            },
        ))

        self._sandboxes[f"{run_id}-{agent_name}"] = sandbox
        return DaytonaSandbox(
            id=f"{run_id}-{agent_name}",
            agent_name=agent_name,
            workspace_dir=Path("/workspace"),
            daytona_sandbox=sandbox,
            run_dir=run_dir,
        )

    def create_shared_volume(self, name, run_id, run_dir):
        volume = self.client.volume.get(f"{run_id}-{name}", create=True)
        return DaytonaSharedVolume(
            id=f"{run_id}-{name}",
            path=Path(f"/shared/{name}"),
            volume=volume,
            client=self.client,
        )

    def destroy_all(self, run_id):
        for key, sandbox in self._sandboxes.items():
            if key.startswith(run_id):
                sandbox.delete()

    @staticmethod
    def is_available():
        try:
            import daytona
            return True
        except ImportError:
            return False
```

## CLI Extensions

```
ivory research <topic>
    # Existing flags (unchanged)
    --strategy         council | adversarial (default: council)
    --agents, -a       Comma-separated agent specs (required)
    --synthesizer, -s  Agent spec for synthesis (required)
    --file, -f         Read topic from markdown file
    --instructions, -i Append instructions to auto-generated prompt
    --raw              Send topic as-is (no prompt wrapping)
    --output-dir, -o   Override default output directory
    --verbose, -v      Stream agent logs to terminal
    --dry-run          Show plan without executing
    --json             Output manifest as JSON on completion
    --max-rounds       Max optimization rounds (adversarial only, default: 10)

    # New flags (v3)
    --sandbox          Sandbox backend: none, local, agentfs, daytona (default: none)
    --template, -t     Strategy template: built-in name or path to YAML file
    --rounds           Number of rounds for iterative phases (overrides template)
    --red-team         Comma-separated agent specs for red team (red-blue strategy)
    --blue-team        Comma-separated agent specs for blue team (red-blue strategy)

ivory resume <run-dir>
    --verbose, -v      (unchanged)

ivory status <run-dir>
    Shows sandbox backend and isolation info when present

ivory list
    Shows sandbox column when runs used sandboxing

ivory strategies
    (unchanged -- lists Python-registered strategies)

ivory templates
    List available strategy templates (built-in + user-defined)

ivory profiles
    List available agent profiles (from ~/.ivory-tower/profiles/)

ivory audit <run-dir> [agent]
    Query AgentFS tool call audit trail for a sandboxed run
    --format table|json    Output format (default: table)
    --filter <tool>        Filter by tool name
    --limit <n>            Limit entries (default: 100)
```

## Manifest Extensions

```json
{
  "run_id": "20260301-143000-a1b2c3",
  "strategy": "council",
  "topic": "...",
  "agents": ["claude", "openai"],
  "synthesizer": "claude",
  "flags": {
    "raw": false,
    "instructions": null,
    "verbose": false,
    "max_rounds": 10
  },
  "sandbox": {
    "backend": "agentfs",
    "config": {
      "snapshot_after_phase": true,
      "snapshot_on_failure": true,
      "allow_paths": [],
      "network": {"allow_outbound": true}
    },
    "agents": {
      "claude": {
        "sandbox_id": "20260301-143000-a1b2c3-claude",
        "database": ".agentfs/20260301-143000-a1b2c3-claude.db"
      },
      "openai": {
        "sandbox_id": "20260301-143000-a1b2c3-openai",
        "database": ".agentfs/20260301-143000-a1b2c3-openai.db"
      }
    },
    "volumes": {
      "blackboard": {
        "volume_id": "20260301-143000-a1b2c3-shared-blackboard",
        "database": ".agentfs/20260301-143000-a1b2c3-shared-blackboard.db"
      }
    }
  },
  "template": "council",
  "agent_profiles": {
    "claude": {"role": "researcher", "executor": "counselors"},
    "openai": {"role": "researcher", "executor": "counselors"}
  },
  "phases": { "...": "strategy-specific, same as v2" },
  "total_duration_seconds": 500
}
```

Backward compatibility: `"sandbox"` and `"template"` and `"agent_profiles"` fields are optional. Absent or null means no sandboxing, no template, default profiles. `from_dict()` uses `.get()` with defaults.

## pyproject.toml Changes

```toml
[project]
dependencies = [
    "typer>=0.15",
    "rich>=13",
    "pyyaml>=6",
]

[project.optional-dependencies]
adversarial = ["gepa>=0.1.0"]
agentfs = ["agentfs-sdk>=0.6"]
daytona = ["daytona>=0.1"]
direct = ["litellm>=1.0"]
all = ["gepa>=0.1.0", "agentfs-sdk>=0.6", "daytona>=0.1", "litellm>=1.0"]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "gepa>=0.1.0",
]
```

Note: `pyyaml` becomes a core dependency (for YAML template loading). `agentfs-sdk` is the Python SDK for programmatic access (audit queries, KV operations). The `agentfs` CLI binary is a separate install for OS-level sandboxing.

## Error Handling

| Condition | Behavior |
|-----------|----------|
| `--sandbox agentfs` + `agentfs` not on PATH | `"The agentfs sandbox backend requires AgentFS CLI. Install: curl -fsSL https://agentfs.ai/install \| bash"`, exit 1 |
| `--sandbox daytona` + `daytona` not installed | `"The daytona sandbox backend requires the daytona SDK. Install: uv add daytona"`, exit 1 |
| `--template unknown` + not a file path | `"Template 'unknown' not found. Available: council, adversarial, debate, map-reduce, red-blue"`, exit 1 |
| `--template path/to/file.yml` + file doesn't exist | `"Template file not found: path/to/file.yml"`, exit 1 |
| Template YAML validation fails | Specific error: `"Template 'debate': phase 'rounds' references unknown blackboard 'transcript'"`, exit 1 |
| `@profile-name` + profile file doesn't exist | `"Agent profile not found: ~/.ivory-tower/profiles/profile-name.yml"`, exit 1 |
| Sandbox creation fails | Log error, fall back to `none` sandbox with warning if `--sandbox` was not explicitly set. Hard fail if `--sandbox` was explicit. |
| Agent execution fails inside sandbox | Mark phase as FAILED, save sandbox state (snapshot if agentfs), preserve all outputs, exit non-zero. |
| AgentFS `agentfs run` fails (FUSE error, namespace error) | `"AgentFS sandbox failed: {error}. Try --sandbox local as fallback."`, exit 1 |
| Daytona sandbox creation fails (API error, quota) | `"Daytona sandbox creation failed: {error}. Check daytona dashboard or try --sandbox local."`, exit 1 |
| Blackboard append fails | Log warning, continue. Agent's output is still saved in its sandbox. |
| Template phase references nonexistent phase in `input_from` | Validation error before execution: `"Phase 'synthesize' references unknown phase 'debate-rounds' in input_from"` |
| `--red-team` / `--blue-team` used without red-blue strategy | Warning: `"--red-team and --blue-team are only used by team-based strategies."` |
| Resume on sandboxed run + sandbox backend changed/unavailable | Warning: `"Original run used agentfs sandbox but it is not available. Resuming without sandboxing."` |

## Built-in Strategy Templates

### strategies/council.yml

```yaml
strategy:
  name: council
  description: "Independent research, cross-pollination, synthesis"
  version: 1

phases:
  - name: research
    description: "Independent parallel research"
    isolation: full
    agents: all
    output: "{agent}-report.md"

  - name: cross-pollinate
    description: "Each agent refines using all peers' work"
    isolation: read-peers
    agents: all
    input_from: research
    output: "{agent}-refined.md"

  - name: synthesize
    description: "Single synthesizer merges all refined reports"
    isolation: read-all
    agents: [synthesizer]
    input_from: cross-pollinate
    output: "final-report.md"

defaults:
  agents:
    min: 2
    max: 10
```

### strategies/adversarial.yml

```yaml
strategy:
  name: adversarial
  description: "GEPA-optimized adversarial research with cross-evaluation"
  version: 1
  engine: ivory_tower.strategies.adversarial.AdversarialStrategy

phases:
  - name: seed
    description: "Independent seed report generation"
    isolation: full
    agents: all
    output: "{agent}-seed.md"

  - name: optimize
    description: "Iterative adversarial optimization via GEPA"
    isolation: full
    agents: all
    output: "{agent}-optimized.md"

  - name: synthesize
    description: "Merge both optimized reports"
    isolation: read-all
    agents: [synthesizer]
    input_from: optimize
    output: "final-report.md"

defaults:
  agents:
    min: 2
    max: 2
  rounds: 10
```

### strategies/debate.yml

```yaml
strategy:
  name: debate
  description: "Structured turn-based debate with shared transcript"
  version: 1

phases:
  - name: opening
    description: "Each agent presents initial position"
    isolation: full
    agents: all
    output: "{agent}-opening.md"

  - name: rounds
    description: "Turn-based debate rounds"
    isolation: blackboard
    agents: all
    rounds: 3
    blackboard:
      name: transcript
      file: "debate-transcript.md"
      access: append
    output: "{agent}-round-{round}.md"

  - name: closing
    description: "Final positions after debate"
    isolation: read-blackboard
    agents: all
    blackboard:
      name: transcript
      access: read
    output: "{agent}-closing.md"

  - name: verdict
    description: "Independent judge evaluates the debate"
    isolation: read-all
    agents: [synthesizer]
    input_from: [opening, rounds, closing]
    output: "verdict.md"

defaults:
  sandbox:
    backend: local
  agents:
    min: 2
    max: 6
  rounds: 3
```

### strategies/map-reduce.yml

```yaml
strategy:
  name: map-reduce
  description: "Decompose topic into subtopics, specialist research, synthesize"
  version: 1

phases:
  - name: decompose
    description: "Break topic into subtopics"
    isolation: full
    agents: [planner]
    output: "subtopics.json"

  - name: map
    description: "Specialist research on each subtopic"
    isolation: full
    agents: dynamic
    fan_out: decompose
    output: "{subtopic}-research.md"

  - name: reduce
    description: "Synthesize all specialist reports"
    isolation: read-all
    agents: [synthesizer]
    input_from: map
    output: "final-report.md"

defaults:
  agents:
    min: 2
    max: 20
```

### strategies/red-blue.yml

```yaml
strategy:
  name: red-blue
  description: "Red team attacks, blue team defends, judge synthesizes"
  version: 1

teams:
  red:
    role: attacker
    description: "Find weaknesses, counter-arguments, missing evidence"
  blue:
    role: defender
    description: "Research, build arguments, address critiques"

phases:
  - name: blue-research
    description: "Blue team researches the topic"
    isolation: team
    agents: [blue]
    blackboard:
      name: blue-board
      dir: "blue-workspace"
      access: rw
    output: "{agent}-research.md"

  - name: red-critique
    description: "Red team critiques blue team's research"
    isolation: cross-team-read
    agents: [red]
    input_from: blue-research
    blackboard:
      name: red-board
      dir: "red-workspace"
      access: rw
    output: "{agent}-critique.md"

  - name: blue-defense
    description: "Blue team addresses red team critiques"
    isolation: cross-team-read
    agents: [blue]
    input_from: red-critique
    output: "{agent}-defense.md"

  - name: synthesize
    description: "Judge synthesizes all perspectives"
    isolation: read-all
    agents: [synthesizer]
    input_from: [blue-research, red-critique, blue-defense]
    output: "final-report.md"

defaults:
  agents:
    min: 3
    max: 10
```

---

# Commit Plan

See [HOW](#how) for worktree setup, TDD workflow, merge process, and test conventions.

**IMPORTANT: All commits happen inside the git worktree at `../ivory-tower-sandbox/`, NOT in the main working tree.** Before starting, verify you are in the worktree: `git worktree list` should show your current directory on the `sandbox-abstraction` branch.

**Subagent parallelism annotations:** Each commit below is tagged with `[PARALLEL]` or `[SEQUENTIAL]`. Parallel commits contain independent file sets that subagents can work on simultaneously. Sequential commits touch shared files and must be done by the lead agent alone. See [HOW > Subagent Parallelism](#subagent-parallelism----rules-of-engagement) for conflict-avoidance rules.

---

## Batch 1: Sandbox Infrastructure [PARALLEL -- 5 subagents]

Commits 1-5 create all-new files in the `sandbox/` package. No existing files are modified. Each subagent owns a disjoint set of files. The lead agent creates `sandbox/__init__.py` after collecting all outputs.

**File ownership:**

| Subagent | Owns | Does NOT touch |
|----------|------|----------------|
| Subagent A | `sandbox/types.py`, `sandbox/null.py`, `tests/test_sandbox_types.py` | Everything else |
| Subagent B | `sandbox/local.py`, `tests/test_sandbox_local.py` | Everything else |
| Subagent C | `sandbox/agentfs.py`, `tests/test_sandbox_agentfs.py` | Everything else |
| Subagent D | `sandbox/daytona.py`, `tests/test_sandbox_daytona.py` | Everything else |
| Subagent E | `sandbox/blackboard.py`, `tests/test_blackboard.py` | Everything else |
| Lead agent | `sandbox/__init__.py` (written AFTER all subagents finish) | Subagent files |

**Conflict check before committing:** `git diff --name-only` must show only the files listed above. If any file appears that wasn't assigned, STOP and investigate.

### Commit 1: Sandbox protocol + types + NullSandboxProvider [Subagent A]

**RED:**
- `SandboxConfig`, `NetworkPolicy`, `ResourceLimits` dataclasses instantiate with defaults.
- `ExecutionResult` dataclass stores exit_code, stdout, stderr, duration.
- `NullSandboxProvider` creates sandboxes that delegate directly to the filesystem (no isolation).
- `get_provider("none")` returns `NullSandboxProvider` instance.
- `get_provider("unknown")` raises `ValueError`.
- `NullSandboxProvider.is_available()` returns `True`.

**GREEN:**
- `sandbox/types.py` -- protocols, dataclasses
- `sandbox/null.py` -- `NullSandboxProvider` (pass-through, no isolation)
- `sandbox/__init__.py` -- provider registry (lead agent writes this after collecting all provider modules)

**Commit:** `feat: sandbox protocol, types, and null provider (no-op pass-through)`

---

### Commit 2: LocalSandboxProvider + LocalSharedVolume [Subagent B]

**RED:**
- `LocalSandboxProvider.create_sandbox()` creates `<run-dir>/sandboxes/<agent>/workspace/`.
- `LocalSandbox.write_file()`, `read_file()`, `copy_in()`, `copy_out()` work correctly with `tmp_path`.
- `LocalSandbox.execute()` runs a subprocess with `cwd` set to workspace.
- `LocalSandbox.list_files()` returns files relative to workspace.
- `LocalSharedVolume.write_file()`, `read_file()`, `append_file()`, `list_files()` work correctly.
- `LocalSandboxProvider.create_shared_volume()` creates `<run-dir>/volumes/<name>/`.

**GREEN:**
- `sandbox/local.py` -- full `LocalSandboxProvider`, `LocalSandbox`, `LocalSharedVolume`

**Commit:** `feat: local sandbox provider with directory-based isolation`

---

### Commit 3: AgentFSSandboxProvider [Subagent C]

**RED:**
- `AgentFSSandboxProvider.is_available()` returns `True` when `agentfs` on PATH, `False` otherwise.
- `AgentFSSandboxProvider.create_sandbox()` calls `agentfs init` with correct args (mocked subprocess).
- `AgentFSSandbox.execute()` calls `agentfs run --session <id>` with `--allow` paths (mocked).
- `AgentFSSandbox.write_file()` calls `agentfs fs write` (mocked).
- `AgentFSSandbox.read_file()` calls `agentfs fs cat` (mocked).
- `AgentFSSandbox.snapshot()` copies the `.db` file to `snapshots/` directory.
- `AgentFSSandbox.diff()` calls `agentfs diff` and saves output (mocked).

**GREEN:**
- `sandbox/agentfs.py` -- full `AgentFSSandboxProvider`, `AgentFSSandbox`, `AgentFSSharedVolume`

**Commit:** `feat: AgentFS sandbox provider with CoW overlay and audit support`

---

### Commit 4: DaytonaSandboxProvider [Subagent D]

**RED:**
- `DaytonaSandboxProvider.is_available()` returns `True` when `daytona` importable, `False` otherwise.
- `DaytonaSandboxProvider.create_sandbox()` calls `daytona.create()` with correct params (mocked SDK).
- `DaytonaSandbox.execute()` calls `sandbox.process.exec()` (mocked).
- `DaytonaSandboxProvider.create_shared_volume()` calls `daytona.volume.get()` (mocked).
- `DaytonaSandboxProvider.destroy_all()` calls `sandbox.delete()` for all run sandboxes (mocked).

**GREEN:**
- `sandbox/daytona.py` -- full `DaytonaSandboxProvider`, `DaytonaSandbox`, `DaytonaSharedVolume`

**Commit:** `feat: Daytona sandbox provider with container isolation and FUSE volumes`

---

### Commit 5: Blackboard implementation [Subagent E]

**RED:**
- `FileBlackboard` in transcript mode: `append()` adds header + content to single file. `get_content()` returns full transcript.
- `FileBlackboard` in directory mode: `append()` creates numbered files. `get_content()` concatenates all.
- `FileBlackboard` with `access="read"`: `append()` raises `PermissionError`.
- `FileBlackboard.snapshot()` returns current content.
- Works with `LocalSharedVolume`.

**GREEN:**
- `sandbox/blackboard.py` -- `FileBlackboard` class

**Commit:** `feat: file-based blackboard with orchestrator-mediated append`

---

**Lead agent work after Batch 1:** Write `sandbox/__init__.py` importing all providers, create the `get_provider()` registry function. Run combined test suite: `uv run pytest tests/test_sandbox*.py tests/test_blackboard.py -v`. Commit all Batch 1 files together (or as individual commits per the plan).

---

## Batch 2: Profiles, Templates, Executors [PARALLEL -- 3 subagents]

Commits 6-9 create all-new files in `profiles/`, `templates/`, `executor/`, and `data/`. No existing files are modified. Each subagent owns a disjoint set of files.

**File ownership:**

| Subagent | Owns | Does NOT touch |
|----------|------|----------------|
| Subagent F | `profiles/__init__.py`, `tests/test_profiles.py` | Everything else |
| Subagent G | `templates/loader.py`, `templates/__init__.py`, `data/strategies/*.yml`, `tests/test_templates.py` | Everything else |
| Subagent H | `executor/types.py`, `executor/counselors_exec.py`, `executor/direct.py`, `tests/test_executor*.py` | Everything else |
| Lead agent | `executor/__init__.py` (registry, written AFTER Subagent H finishes) | Subagent files |

### Commit 6: Agent profiles -- dataclass + YAML loading [Subagent F]

**RED:**
- `AgentProfile.from_yaml(path)` loads a YAML profile with all fields.
- `AgentProfile.from_cli_shorthand("claude:researcher")` parses model:role.
- `AgentProfile.from_cli_shorthand("claude")` parses model-only (default role).
- `AgentProfile.from_cli_shorthand("@deep-researcher")` loads from `~/.ivory-tower/profiles/`.
- `AgentProfile.from_cli_shorthand("@nonexistent")` raises `FileNotFoundError`.
- Missing optional fields use defaults.

**GREEN:**
- `profiles/__init__.py` -- `AgentProfile` dataclass, YAML loading, CLI shorthand parsing

**Commit:** `feat: agent profiles with YAML loading and CLI shorthand syntax`

---

### Commit 7: YAML strategy template loading + validation [Subagent G]

**RED:**
- `load_template("council")` loads built-in `data/strategies/council.yml`.
- `load_template("/path/to/file.yml")` loads a file path.
- `load_template("~/.ivory-tower/strategies/my-debate.yml")` loads user-defined template.
- `load_template("nonexistent")` raises `FileNotFoundError`.
- `validate_template()` rejects: missing `strategy.name`, missing `phases`, unknown isolation mode, phase referencing nonexistent phase in `input_from`, blackboard without `name`.
- `validate_template()` accepts all 5 built-in templates.
- `list_templates()` returns built-in + user-defined template names with descriptions.
- Template resolution: CLI flags override template values.

**GREEN:**
- `templates/__init__.py` -- public API
- `templates/loader.py` -- YAML loading, validation, template resolution
- `data/strategies/*.yml` -- all 5 built-in templates

**Commit:** `feat: YAML strategy template loading, validation, and resolution`

---

### Commit 8: AgentExecutor protocol + CounselorsExecutor [Subagent H, part 1]

**RED:**
- `CounselorsExecutor.run()` writes prompt to sandbox, calls `counselors run` via `sandbox.execute()`, reads output (mocked).
- `AgentOutput` contains `report_path`, `raw_output`, `duration_seconds`.
- `get_executor("counselors")` returns `CounselorsExecutor` instance.
- `get_executor("direct")` returns `DirectExecutor` instance.
- `get_executor("unknown")` raises `ValueError`.
- Extracted `_normalize_output()` utility shared between strategies.

**GREEN:**
- `executor/__init__.py` -- registry
- `executor/types.py` -- protocols, dataclasses
- `executor/counselors_exec.py` -- `CounselorsExecutor`

**Commit:** `feat: agent executor protocol and counselors executor`

---

### Commit 9: DirectExecutor (litellm-based) [Subagent H, part 2]

**RED:**
- `DirectExecutor.run()` calls `litellm.completion()` with model and messages (mocked).
- System prompt from agent profile is included when present.
- Output is written to sandbox and returned as `AgentOutput`.
- `DirectExecutor` requires `litellm` importable; graceful error message if not.

**GREEN:**
- `executor/direct.py` -- `DirectExecutor`

**Commit:** `feat: direct LLM API executor via litellm`

---

**Lead agent work after Batch 2:** Write `executor/__init__.py` if not already handled by Subagent H. Run combined test suite: `uv run pytest tests/test_profiles.py tests/test_templates.py tests/test_executor*.py -v`. Commit.

---

## Batch 3: Template Executor + Isolation [SEQUENTIAL -- lead agent only]

Commits 10-11 create the orchestration logic that ties sandbox providers, executors, templates, and isolation modes together. These files import from Batch 1 and Batch 2 outputs. **Only the lead agent works on these.** No subagents.

### Commit 10: Isolation mode implementation [SEQUENTIAL]

**RED:**
- `setup_phase_isolation("full", ...)` -- sandboxes receive no peer data.
- `setup_phase_isolation("read-peers", ...)` -- each sandbox receives copies of peer outputs from the specified phase. Original files are not modified.
- `setup_phase_isolation("read-all", ...)` -- sandbox receives all outputs from specified phases.
- `setup_phase_isolation("blackboard", ...)` -- sandbox receives current blackboard content.
- `setup_phase_isolation("team", ...)` -- team members receive team blackboard; other teams excluded.
- `setup_phase_isolation("cross-team-read", ...)` -- agents receive opposing team outputs only.
- `setup_phase_isolation("none", ...)` -- no-op.

**GREEN:**
- Logic in `templates/executor.py` or `sandbox/isolation.py` -- `setup_phase_isolation()` function

**Commit:** `feat: isolation mode implementation for all 8 modes`

---

### Commit 11: GenericTemplateExecutor [SEQUENTIAL]

**RED:**
- `GenericTemplateExecutor` loads a template (debate) and runs all phases in order.
- Single-phase execution: creates sandboxes, sets up isolation, runs agents in parallel, copies outputs.
- Iterative-phase execution: runs rounds with blackboard append between turns.
- Dynamic fan-out: reads planner output (JSON list), creates one sandbox per subtopic.
- Phase outputs from earlier phases feed into later phases via `input_from`.
- Manifest is updated after each phase.

**GREEN:**
- `templates/executor.py` -- `GenericTemplateExecutor`

**Commit:** `feat: generic template executor for YAML-defined strategies`

---

## Batch 4: Existing Code Modification [SEQUENTIAL -- lead agent only]

Commits 12-15 modify existing v2 files. **These MUST be done sequentially by the lead agent.** No subagents. These files are shared resources that cannot safely be edited in parallel.

**Critical: read each file before editing.** These files have existing code that must not be broken. Every edit is additive (new optional fields, new code paths gated behind `if sandbox_backend != "none"`).

### Commit 12: Refactor CouncilStrategy + AdversarialStrategy to use sandbox [SEQUENTIAL]

**RED:**
- `CouncilStrategy.run()` with `sandbox=local` produces identical output to v2.
- `CouncilStrategy.run()` with `sandbox=none` produces identical output to v2 (backward compat).
- `AdversarialStrategy.run()` with `sandbox=local` produces identical output to v2.
- All existing council + adversarial tests pass without modification.
- New tests: sandboxed council creates `sandboxes/` directory with per-agent workspaces.

**GREEN:**
- Modify `strategies/council.py` to use sandbox abstractions (optional, defaults to none).
- Modify `strategies/adversarial.py` to use sandbox abstractions (optional, defaults to none).
- Extract `_normalize_counselors_output()` into shared utility.

**Commit:** `refactor: council and adversarial strategies use sandbox abstractions, full backward compat`

---

### Commit 13: New strategies -- Debate, Map/Reduce, Red/Blue [PARALLEL -- 3 subagents, with care]

Each new strategy is a separate file. Subagents can write these in parallel. But `strategies/__init__.py` is a shared file -- only the lead agent touches it.

**File ownership:**

| Subagent | Owns | Does NOT touch |
|----------|------|----------------|
| Subagent I | `strategies/debate.py`, `tests/test_debate.py` | `__init__.py`, other strategy files |
| Subagent J | `strategies/map_reduce.py`, `tests/test_map_reduce.py` | `__init__.py`, other strategy files |
| Subagent K | `strategies/red_blue.py`, `tests/test_red_blue.py` | `__init__.py`, other strategy files |
| Lead agent | `strategies/__init__.py` (registry update, AFTER subagents finish) | Subagent files |

**RED:**
- `get_strategy("debate")` returns a strategy backed by `GenericTemplateExecutor` + `debate.yml`.
- `get_strategy("map-reduce")` returns a strategy backed by `GenericTemplateExecutor` + `map-reduce.yml`.
- `get_strategy("red-blue")` returns a strategy backed by `GenericTemplateExecutor` + `red-blue.yml`.
- `ivory strategies` lists all 5 strategies.
- `DebateStrategy.validate()` rejects < 2 agents, rejects missing synthesizer.
- `MapReduceStrategy.validate()` rejects < 2 agents.
- `RedBlueStrategy.validate()` rejects missing `--red-team` or `--blue-team`.

**GREEN:**
- `strategies/debate.py` -- thin wrapper around `GenericTemplateExecutor`
- `strategies/map_reduce.py` -- thin wrapper
- `strategies/red_blue.py` -- thin wrapper
- Update strategy registry in `strategies/__init__.py`

**Commit:** `feat: debate, map-reduce, and red-blue strategies via template executor`

---

### Commit 14: CLI extensions -- `--sandbox`, `--template`, `--profile`, new commands [SEQUENTIAL]

**This commit touches `cli.py` which is a shared file. Lead agent only. No subagents.**

**RED:**
- `--sandbox local` sets `config.sandbox_backend = "local"`.
- `--sandbox agentfs` when `agentfs` not on PATH: prints install message, exit 1.
- `--template debate` loads `debate.yml` and overrides strategy.
- `--template /path/to/file.yml` loads user template.
- `ivory templates` lists built-in + user-defined templates.
- `ivory profiles` lists profiles from `~/.ivory-tower/profiles/`.
- `ivory audit <run-dir> claude` reads AgentFS database and prints timeline.
- Agent spec parsing: `claude:researcher`, `claude`, `@deep-researcher`.
- `--red-team a,b --blue-team c,d` parsed into team assignments.

**GREEN:**
- Update `cli.py` with new flags and commands.
- New `cli.py` commands: `templates`, `profiles`, `audit`.

**Commit:** `feat: CLI gains --sandbox, --template, --profile flags and audit command`

---

### Commit 15: Manifest extensions + backward compat [SEQUENTIAL]

**This commit modifies `models.py` and `engine.py` -- shared v2 files. Lead agent only. No subagents.**

**RED:**
- `Manifest.to_dict()` includes `"sandbox"`, `"template"`, `"agent_profiles"` when present.
- `Manifest.from_dict()` handles v2 manifests (no sandbox fields) without error.
- `Manifest.from_dict()` on a v3 manifest correctly restores sandbox config, agent profiles.
- `ivory status <run-dir>` shows sandbox info when present, omits when absent.
- `ivory list` shows sandbox column when any run used sandboxing.

**GREEN:**
- Update `models.py` with new optional fields.
- Update `engine.py` to pass sandbox config through the pipeline.

**Commit:** `feat: manifest extensions for sandbox state with full v1/v2 backward compat`

---

## Batch 5: Integration Tests + Final Merge [SEQUENTIAL -- lead agent only]

### Commit 16: End-to-end integration tests + final cleanup [SEQUENTIAL]

**This is the final commit. Lead agent only. Run the FULL test suite. No subagents.**

**Pre-commit checklist:**
1. Verify you are in the worktree: `pwd` should show `../ivory-tower-sandbox/`
2. Verify branch: `git branch --show-current` should show `sandbox-abstraction`
3. Run full test suite: `uv run pytest tests/ -v`
4. Run existing v2 tests specifically: `uv run pytest tests/test_engine.py tests/test_strategies.py tests/test_cli.py -v`
5. Check no untracked files from subagent accidents: `git status`

**Tests:**
- Full council pipeline with local sandbox (mocked counselors).
- Full adversarial pipeline with local sandbox (mocked counselors + GEPA).
- Debate strategy with blackboard: 3 agents, 3 rounds, verify transcript grows.
- Map/reduce: planner produces 4 subtopics, 2 agents map, 1 reduces.
- Red/blue: 2v2, verify team isolation.
- AgentFS sandbox creation/teardown (mocked agentfs CLI).
- Daytona sandbox creation/teardown (mocked SDK).
- Template loading from all 5 built-in templates.
- Agent profile loading with shorthand syntax.
- Backward compat: v2 run resumes without sandbox.
- `--dry-run` with `--sandbox agentfs` shows database paths.
- CLI: `ivory templates`, `ivory profiles`.
- Error paths: missing backend, invalid template, missing profile.

**Full suite:** `uv run pytest tests/ -v`

**Commit:** `test: end-to-end integration tests for all sandbox backends, strategies, and templates`

---

## Post-Commit: Merge to Main [SEQUENTIAL -- lead agent only]

After all 16 commits are green:

```bash
# 1. Final verification inside worktree
cd ../ivory-tower-sandbox
uv run pytest tests/ -v                  # MUST be 100% green
git log --oneline sandbox-abstraction    # Verify 16 commits

# 2. Merge into main
cd ../ivory-tower                        # Back to main working tree
git checkout main
git merge sandbox-abstraction            # Fast-forward or merge commit

# 3. Verify main works
uv run pytest tests/ -v                  # MUST still be green

# 4. Cleanup
git worktree remove ../ivory-tower-sandbox
git branch -d sandbox-abstraction
```

**NEVER force-push. NEVER rebase the feature branch after subagents have committed to it.**

---

# Appendix: Sandbox Backend Comparison

| Dimension | `none` | `local` | `agentfs` | `daytona` |
|---|---|---|---|---|
| **Dependencies** | None | None | `agentfs` CLI (Rust binary) | `daytona` Python SDK + account |
| **Isolation level** | None | Directory-based (conventional) | OS-level (FUSE+namespaces / NFS+Seatbelt) | Container (Docker) |
| **Network isolation** | No | No | No | Yes (firewall) |
| **Audit trail** | Manifest only | Manifest only | Full SQL-queryable tool call log | Via Daytona API |
| **Snapshots** | No | No | Instant (`cp .db`) | Container snapshots |
| **Diff** | No | No | `agentfs diff` | No |
| **KV store** | No | No | Built-in SQLite KV | No |
| **Shared state** | Shared directory | Copied files | AgentFS KV / NFS export | FUSE volumes |
| **Startup** | Instant | Instant | Near-instant | ~90ms warm, seconds cold |
| **Cost** | Free | Free | Free (local) | Pay-per-second or self-hosted |
| **Platform** | Any | Any | macOS, Linux | Linux (Docker) |
| **Best for** | Development, backward compat | Simple isolation, no deps | Full observability, local dev | CI/CD, maximum isolation |

# Appendix: Isolation Mode Decision Matrix

| Strategy | Phase | Isolation Mode | What Agent Sees | What Agent Cannot See |
|---|---|---|---|---|
| Council | Research | `full` | Prompt only | All peer work |
| Council | Cross-pollinate | `read-peers` | Own report + peer reports (read-only) | Nothing hidden |
| Council | Synthesize | `read-all` | All refined reports | Nothing hidden |
| Adversarial | Seed | `full` | Prompt only | Opponent's seed |
| Adversarial | Optimize | `full` (orchestrator mediates cross-eval) | Own report + judge feedback | Opponent's optimization state |
| Adversarial | Synthesize | `read-all` | Both optimized reports | Optimization internals |
| Debate | Opening | `full` | Prompt only | Other agents' openings |
| Debate | Rounds | `blackboard` (append) | Transcript + own workspace | Other agents' private workspaces |
| Debate | Closing | `read-blackboard` | Full transcript (read-only) | Other agents' private workspaces |
| Debate | Verdict | `read-all` | Everything | Nothing hidden |
| Map/Reduce | Decompose | `full` | Prompt only | N/A (single agent) |
| Map/Reduce | Map | `full` | Subtopic prompt only | All other subtopics |
| Map/Reduce | Reduce | `read-all` | All mapper outputs | Nothing hidden |
| Red/Blue | Blue research | `team` | Team blackboard | Red team's work |
| Red/Blue | Red critique | `cross-team-read` | Blue's published outputs | Blue's internal blackboard |
| Red/Blue | Blue defense | `cross-team-read` | Red's critiques | Red's internal blackboard |
| Red/Blue | Synthesize | `read-all` | Everything | Nothing hidden |
