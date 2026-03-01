# Building a General-Purpose Eval Runner with Harbor and inspect-harbor

## Research Report — March 1, 2026

---

## Executive Summary

This report investigates how to use **Harbor** (the Laude Institute's agent evaluation framework) and **inspect-harbor** (the bridge to Inspect AI) to build a general-purpose eval runner capable of mixing and matching different agent solvers against different benchmarks like Spider2 and LongMemEval.

A critical disambiguation uncovered during research: there are **two unrelated projects called "Harbor"**. The one relevant to this research is the **Laude Institute's Harbor** (`laude-institute/harbor`), an agent evaluation and RL environment framework — not `av/harbor`, which is a Docker Compose orchestration tool for local LLM stacks. The `inspect-harbor` package bridges the Laude Institute's Harbor with Inspect AI.

The research finds that Harbor + inspect-harbor provide a solid foundation for a general-purpose eval runner, with Harbor handling containerized task environments and agent execution, and inspect-harbor enabling use of Inspect AI's solver ecosystem and evaluation infrastructure. However, integrating non-containerized benchmarks like Spider2 (which requires cloud database access) and LongMemEval (which requires long-context conversation management) would require significant custom adapter engineering.

---

## 1. Harbor's Architecture

### Overview

Harbor (v0.1.45, Feb 2026) is an open-source (Apache-2.0) framework for evaluating AI agents in sandboxed container environments. Created by the Laude Institute (the team behind Terminal-Bench), it provides infrastructure for running agent evaluations, generating training data (SFT and RL), and conducting experiments at scale.

**Source**: https://github.com/laude-institute/harbor (816 stars, 551 commits, Python 86.4%)

### Layered Architecture

```
User Interface (CLI / Web Viewer)
    → Orchestration (Job → Orchestrator → TrialConfigs)
        → Execution Runtime (Agent + Environment + Verifier)
            → Configuration & Tasks (TaskConfig, Registry)
                → Persistent Storage (TrialResult, JobResult, Trajectories)
```

### Core Concepts

| Concept | Description |
|---------|-------------|
| **Task** | A single evaluation unit: instruction, environment, tests, optional solution |
| **Dataset** | A collection of tasks, local or from the registry |
| **Agent** | A program that attempts to complete tasks (e.g., Claude Code, OpenHands, custom) |
| **Environment** | A sandboxed container runtime (Docker, Daytona, Modal, E2B, GKE) |
| **Trial** | A single agent attempt at a single task, producing a trajectory and reward |
| **Job** | A collection of trials (Cartesian product of tasks × agents × attempts) |

### Task Definition Format

Each task is a directory containing:

```
my_task/
├── instruction.md          # Natural language instructions for the agent
├── task.toml               # Configuration: timeouts, resources, metadata, env vars
├── environment/            # Dockerfile or docker-compose.yaml
│   ├── Dockerfile          # (or docker-compose.yaml for multi-container)
├── tests/                  # Verification
│   └── test.sh             # Produces /logs/verifier/reward.txt or reward.json
└── solution/               # Optional reference solution
    └── solve.sh            # For Oracle agent validation
```

The `task.toml` configuration supports:
- **Metadata**: author, difficulty, category, tags
- **Verifier settings**: timeout, environment variables
- **Agent settings**: timeout, environment variables
- **Environment settings**: CPU, memory, storage, GPU (count and types), internet access, build timeout, Docker image override, MCP server definitions

**Source**: https://harborframework.com/ (official docs)

### Service Orchestration

Harbor manages the full lifecycle through its CLI (`harbor` command, built with Typer):

1. **Job creation**: `harbor run -d "dataset@version" -a agent-name -m provider/model`
2. **Task download**: Git sparse checkout with LFS support from registry
3. **Environment provisioning**: Docker build/pull, resource allocation
4. **Agent execution**: Setup + run phases with timeout enforcement
5. **Verification**: Test script execution, reward file parsing
6. **Result collection**: Trajectories (ATIF v1.4 format), logs, artifacts
7. **Cleanup**: Container teardown

The orchestrator uses `asyncio.Semaphore` for concurrency control, enabling parallel trial execution up to a configurable limit.

### Environment Runtimes

| Environment | Type | Mounted FS | GPU | Internet Control | Multi-Container |
|-------------|------|------------|-----|------------------|-----------------|
| `docker` | Local | Yes | No | Yes | Yes (compose) |
| `daytona` | Cloud | No | No | Yes | Yes (compose) |
| `modal` | Cloud | No | Yes | Yes | No |
| `e2b` | Cloud | No | No | Yes | No |
| `gke` | Cloud (K8s) | No | Yes | Yes | No |

Cloud environments make trials I/O-bounded rather than CPU-bounded, enabling 100+ concurrent trials from a single laptop.

**Source**: https://github.com/laude-institute/harbor, DeepWiki analysis

### Registry System

Harbor maintains a curated registry (`registry.json`) of 45+ benchmark datasets totaling ~21,000+ individual task instances. Registry entries specify:

```json
{
    "name": "terminal-bench",
    "version": "2.0",
    "description": "...",
    "metrics": [{"type": "mean"}, {"type": "max"}],
    "tasks": [
        {
            "name": "task-1",
            "git_url": "https://github.com/...",
            "git_commit_id": "abc123...",
            "path": "task-1"
        }
    ]
}
```

Tasks in a single dataset can span multiple Git repositories. Custom registries are supported via `--registry-path` or `--registry-url` flags.

**Source**: https://harborframework.com/registry

---

## 2. inspect-harbor: The Inspect AI Bridge

### Overview

**inspect-harbor** (v0.4.5, Feb 25, 2026) bridges Harbor's evaluation framework with Inspect AI (UK AISI's LLM evaluation framework). Published by Meridian Labs, maintained by J.J. Allaire (creator of RStudio/Posit, also an Inspect AI maintainer).

**Source**: https://pypi.org/project/inspect-harbor/, https://github.com/meridianlabs-ai/inspect_harbor

### Dependencies

```
inspect-ai >= 0.3.176
harbor >= 0.1.44
pyyaml
```

### Concept Mapping

| Harbor Concept | Inspect AI Concept | How It Maps |
|---|---|---|
| Task directory | `Sample` | One evaluation instance with input, sandbox, metadata |
| Dataset (collection of tasks) | `Task` (with `dataset=list[Sample]`) | Collection of Samples with solver + scorer |
| `instruction.md` | `Sample.input` | Prompt given to the agent/solver |
| `environment/` | `SandboxEnvironmentSpec` + `ComposeConfig` | Docker sandbox configuration |
| `tests/test.sh` | `Scorer` (`harbor_scorer`) | Produces reward.txt/reward.json |
| `solution/solve.sh` | `Solver` (`oracle`) | Reference solution for sanity checking |
| `task.toml[metadata]` | `Sample.metadata` | Author, difficulty, category, tags |
| `task.toml[environment]` | `ComposeConfig` resource limits | CPU, memory, GPU, internet |

### How It Works

The `harbor()` function is the core `@task` entry point that supports four loading patterns:

1. **Registry dataset**: `harbor(dataset_name_version="terminal-bench@2.0")` — downloads from Harbor's registry
2. **Git task**: `harbor(path="task-id", task_git_url="https://...")` — clones specific task from Git
3. **Local task**: `harbor(path="/path/to/single/task")` — loads single local task
4. **Local dataset**: `harbor(path="/path/to/dataset/")` — enumerates local task directories

The conversion pipeline (`harbor_task_to_sample()`):
1. Reads `instruction.md` → `Sample.input`
2. Builds Docker Compose configuration from the environment directory
3. Enforces minimum 6 GB memory (overrides Harbor's 2 GB default)
4. Stores all metadata needed by scorer/solver on the Sample

### The Scorer: `harbor_scorer`

The scorer is registered with `@scorer(metrics=[accuracy(), stderr()])` and executes:

1. Copies test files from local cache into sandbox at `/tests/`
2. Creates log directories (`/logs/agent/`, `/logs/verifier/`)
3. Resolves environment variable templates (e.g., `${ANTHROPIC_API_KEY}`) from host
4. Runs `bash -l test.sh` with configurable timeout (default: 600s)
5. Parses reward file: `reward.txt` (single float) or `reward.json` (dict with metrics)
6. Produces `Score(value=reward, answer="PASS"/"FAIL")`
7. Cleans up test files and verifier logs from sandbox

The scorer is **always** used regardless of solver choice — it's baked into the Task definition.

### The Oracle Solver

Runs the task's reference solution (`solution/solve.sh`) for validating that tasks are correctly configured:

```bash
inspect eval inspect_harbor/hello_world --solver inspect_harbor/oracle
```

### Default Agent Scaffold

When no custom solver is provided, inspect-harbor uses:

```python
solver=react(
    tools=[bash(timeout=300), python(timeout=300), update_plan()],
    compaction=CompactionEdit(),
)
```

This provides a ReAct agent with 5-minute-timeout bash and python tools, plan tracking, and context window compaction.

### Pre-built Dataset Tasks

inspect-harbor auto-generates `@task` functions for all 45+ Harbor registry datasets. Each gets both versioned and unversioned variants:

```python
from inspect_harbor import terminal_bench, terminal_bench_2_0
from inspect_harbor import swebench_verified, swebench_verified_1_0
```

**Source**: https://github.com/meridianlabs-ai/inspect_harbor (source analysis)

---

## 3. Defining and Registering New Agent Solvers

### In Harbor (Native)

Harbor provides two agent interfaces:

**BaseAgent** (external agents — communicate via `exec()` commands):
```python
class MyAgent(BaseAgent):
    def name() -> str: ...
    def version() -> str | None: ...
    async def setup(self, environment: BaseEnvironment) -> None: ...
    async def run(self, instruction, environment, context) -> None: ...
```

**BaseInstalledAgent** (installed into the container, run in headless mode):
```python
class MyInstalledAgent(BaseInstalledAgent):
    @property
    def _install_agent_template_path(self) -> Path: ...
    def create_run_agent_commands(self, instruction) -> list[ExecInput]: ...
```

Registration requires adding to the `AgentName` enum and (for installed agents) providing a Jinja2 installation template (`install-{agent-name}.sh.j2`). Custom agents can also be loaded at runtime via `--agent-import-path module:Class`.

**Built-in agents**: claude-code, codex, openhands, gemini-cli, aider, goose, mini-swe-agent, qwen-coder, cursor-cli, cline-cli, opencode, terminus-2, oracle, nop.

### In Inspect AI (via inspect-harbor)

Any Inspect AI solver can be used with Harbor tasks. The solver is the execution plan:

```python
# Built-in solvers
from inspect_ai.solver import generate, chain_of_thought, self_critique

# Custom solver
@solver
def my_agent():
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # Custom agent logic using tools
        ...
    return solve

# Use with Harbor tasks
eval(terminal_bench(), solver=my_agent(), model="anthropic/claude-sonnet-4-5")
```

CLI override:
```bash
inspect eval inspect_harbor/terminal_bench --solver path/to/agent.py@my_agent --model openai/gpt-5
```

The key advantage: inspect-harbor lets you swap solvers freely while Harbor's `harbor_scorer` handles verification consistently.

**Source**: https://inspect.ai-safety-institute.org.uk/, https://github.com/meridianlabs-ai/inspect_harbor

---

## 4. Defining and Registering New Benchmarks/Datasets

### Harbor's Adapter System

Harbor has a formal process for integrating third-party benchmarks:

```bash
harbor adapters init  # Interactive wizard
```

The adapter converts external benchmark tasks into Harbor's standardized format:

```
adapters/<benchmark-name>/
├── adapter.py              # Main conversion logic
├── run_adapter.py          # Entry point
├── parity_experiment.json  # Parity results vs. original harness
├── run_<name>.yaml         # Reference job config
├── adapter_metadata.json   # Metadata
├── README.md
└── template/               # Task templates
    ├── task.toml
    ├── instruction.md
    ├── Dockerfile
    └── test.sh
```

The adapter reads the original benchmark data and generates Harbor task directories. After creation:

1. Run `uv run run_adapter.py --output-dir ../../datasets/<name>` to generate tasks
2. Validate with Oracle solver (100% pass rate expected)
3. Run parity experiments against original benchmark harness
4. Upload to HuggingFace dataset repo
5. Register in `registry.json`
6. Submit PR with documentation

Existing adapters include: BixBench, ARC-AGI-2, AutoCodeBench, SLDBench, SWE-Bench, Terminal-Bench, and many more.

### Via inspect-harbor

Once tasks are in Harbor format, inspect-harbor can load them:

```python
# Local dataset
harbor(path="/path/to/my-benchmark/")

# Custom registry
harbor(dataset_name_version="my-benchmark@1.0", registry_path="./my-registry.json")
```

### Spider2 Integration Assessment

**Spider2** (Lei et al., 2024, ICLR 2025 Oral) evaluates LLMs on enterprise text-to-SQL workflows. Key challenges for Harbor integration:

| Aspect | Spider2 Reality | Harbor Compatibility |
|--------|----------------|---------------------|
| Data format | JSONL questions + CSV gold answers | Needs adapter to create instruction.md per task |
| Databases | BigQuery, Snowflake, SQLite | Cloud DBs require internet access + credentials |
| Evaluation | CSV output comparison | Can be wrapped as test.sh |
| Agent framework | Custom Spider-Agent (Docker-based) | Could become installed agent or solver |
| Self-contained subset | Spider 2.0-Lite SQLite (135 tasks) | Most feasible starting point |

**Recommended approach**: Start with Spider 2.0-Lite (SQLite subset) which is self-contained. Each task would get a Docker environment with SQLite + database files, `instruction.md` with the NL question + schema, and `test.sh` that compares CSV output against gold. The BigQuery/Snowflake tasks would require `allow_internet=true` and credential injection via `task.toml[environment].env`.

**Source**: https://spider2-sql.github.io/, https://github.com/xlang-ai/Spider2, arXiv:2411.07763

### LongMemEval Integration Assessment

**LongMemEval** (Wu et al., 2024, ICLR 2025) benchmarks long-term memory capabilities across 500 questions with multi-session conversation histories (~115K to ~1.5M tokens).

| Aspect | LongMemEval Reality | Harbor Compatibility |
|--------|---------------------|---------------------|
| Data format | JSON with nested chat sessions | Needs adapter to create instruction.md |
| Context | ~115K-1.5M tokens of conversation history | Challenge: must inject into agent context |
| Evaluation | GPT-4o automated QA scoring | Can be wrapped as test.sh (needs API key) |
| Infrastructure | OpenAI API key for eval | Via `task.toml[verifier].env` |
| No container needed | Pure text/API task | Lightweight environment sufficient |

**Recommended approach**: Each task becomes a Harbor task where `instruction.md` contains the conversation history + question, the environment is a minimal Python container, and `test.sh` uses the LongMemEval evaluation script (GPT-4o judge) to score the agent's response. The `LongMemEval_oracle` subset (500 questions with only evidence sessions) would be the most practical starting point. The challenge is that the ~1.5M token histories in `LongMemEval_M` exceed most context windows, requiring the agent to implement its own RAG or memory strategy.

**Source**: https://github.com/xiaowu0162/LongMemEval, https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned, arXiv:2410.10813

---

## 5. The Eval Execution Pipeline

### Harbor Native Pipeline

```
harbor run -d "dataset@version" -a agent-name -m provider/model -n 32
```

**Lifecycle**:

1. **Job Initialization**: Parse `JobConfig`, resolve registry dataset, download tasks
2. **Trial Configuration**: Generate `TrialConfig` for each task × agent × attempt combination
3. **Orchestration**: `LocalOrchestrator` manages concurrency via `asyncio.Semaphore(n_concurrent_trials)`
4. **For each trial**:
   a. **Environment Start**: Build/pull Docker image, start container(s), allocate resources
   b. **Agent Setup**: Install agent tools, configure credentials
   c. **Agent Run**: Execute agent against `instruction.md`, enforce timeout
   d. **Verification**: Copy `tests/` to container, run `test.sh`, parse `reward.txt`/`reward.json`
   e. **Artifact Collection**: Gather `/logs/artifacts/`, agent logs, trajectories
   f. **Environment Teardown**: Stop and optionally delete container(s)
5. **Result Aggregation**: Compute metrics (mean, max, sum, min, custom uv-script metrics)
6. **Output**: `jobs/<name>/result.json`, `summary.md`, per-trial trajectories

### inspect-harbor Pipeline (via Inspect AI)

```bash
inspect eval inspect_harbor/terminal_bench_sample --model openai/gpt-5
```

**Lifecycle**:

1. **Task Loading**: `harbor()` downloads dataset, converts Harbor Tasks to Inspect Samples
2. **Sandbox Setup**: Inspect AI's sandbox system provisions Docker containers per `ComposeConfig`
3. **Solver Execution**: The configured solver (default: ReAct with bash+python) interacts with the sandbox
4. **Scoring**: `harbor_scorer` copies tests into sandbox, runs `test.sh`, parses rewards
5. **Logging**: Inspect AI's logging system records all interactions, tool calls, scores
6. **Results**: Inspect log files (.eval format), viewable in VS Code extension or Inspect View

### Key Difference

Harbor native runs agents as external processes that send `exec()` commands to containers. Inspect AI runs solvers as Python coroutines that use tool abstractions (`bash()`, `python()`) which map to sandbox execution. The inspect-harbor bridge handles this translation.

---

## 6. Practical Architecture for a General-Purpose Eval Runner

### Recommended Architecture: Harbor + inspect-harbor as Foundation

```
┌─────────────────────────────────────────────────┐
│                  Eval Runner CLI                 │
│  (Orchestrates benchmark × solver combinations)  │
├─────────────────────────────────────────────────┤
│                                                   │
│  ┌─────────────────┐   ┌──────────────────────┐ │
│  │  Benchmark       │   │  Solver Registry     │ │
│  │  Registry        │   │                      │ │
│  │  ┌─────────────┐│   │  ┌────────────────┐  │ │
│  │  │Terminal-Bench││   │  │ ReAct (default)│  │ │
│  │  │SWE-Bench    ││   │  │ Claude Code    │  │ │
│  │  │Spider2-Lite ││   │  │ OpenHands      │  │ │
│  │  │LongMemEval  ││   │  │ Custom agents  │  │ │
│  │  │Custom...    ││   │  │ ...            │  │ │
│  │  └─────────────┘│   │  └────────────────┘  │ │
│  └─────────────────┘   └──────────────────────┘ │
│                                                   │
├─────────────────────────────────────────────────┤
│            inspect-harbor Bridge Layer            │
│  (Harbor Tasks → Inspect Samples, Scoring)       │
├─────────────────────────────────────────────────┤
│                                                   │
│  ┌─────────────────┐   ┌──────────────────────┐ │
│  │  Harbor          │   │  Inspect AI          │ │
│  │  (Tasks, Envs,   │   │  (Solvers, Logging,  │ │
│  │   Registry,      │   │   Model providers,   │ │
│  │   Adapters)      │   │   VS Code, View)     │ │
│  └─────────────────┘   └──────────────────────┘ │
│                                                   │
├─────────────────────────────────────────────────┤
│               Execution Layer                    │
│  Docker (local) | Daytona | Modal | E2B | GKE   │
└─────────────────────────────────────────────────┘
```

### Option A: Use Harbor Native + inspect-harbor (Recommended)

**For benchmarks that fit Harbor's containerized task model** (Terminal-Bench, SWE-Bench, code-based tasks):

```python
# eval_runner.py
from inspect_ai import eval
from inspect_harbor import harbor

# Mix and match: different benchmarks × different solvers
benchmarks = [
    ("terminal-bench@2.0", None),  # Uses default ReAct solver
    ("swebench-verified@1.0", "inspect_swe/claude_code"),
    ("my-spider2-lite@1.0", "my_agents/sql_agent"),
]

for dataset, solver_path in benchmarks:
    task = harbor(dataset_name_version=dataset)
    results = eval(task, solver=solver_path, model="anthropic/claude-sonnet-4-5")
```

**For benchmarks requiring custom adapters** (Spider2, LongMemEval):

1. Write a Harbor adapter (under `adapters/spider2-lite/`)
2. Generate Harbor task directories
3. Register in custom registry
4. Use via `harbor(dataset_name_version="spider2-lite@1.0", registry_path="./my-registry.json")`

### Option B: Use Harbor Native CLI for Agent-Level Evals

When testing Harbor-native agents (Claude Code, OpenHands, etc.) rather than Inspect solvers:

```bash
# Run multiple agents against same benchmark
harbor run -d "terminal-bench@2.0" -a claude-code -m anthropic/claude-opus-4-1 -n 32
harbor run -d "terminal-bench@2.0" -a openhands -m openai/gpt-5 -n 32
harbor run -d "terminal-bench@2.0" -a codex -m openai/gpt-5 -n 32

# Compare with viewer
harbor view jobs
```

### Option C: Hybrid Approach

Use Harbor native for agent evals and inspect-harbor for solver evals, with a unified results pipeline:

```python
# Unified runner
class EvalRunner:
    def run_harbor_native(self, dataset, agent, model, n_concurrent=32):
        """For Harbor-native agents (claude-code, openhands, etc.)"""
        # Calls harbor.Job programmatically
        
    def run_inspect(self, dataset, solver, model):
        """For Inspect AI solvers"""
        # Uses inspect_harbor.harbor() + eval()
        
    def compare_results(self, job_dirs):
        """Unified comparison across both execution modes"""
```

---

## 7. Existing Examples and Patterns

### Harbor Registry Datasets (45+ curated)

Major benchmarks already adapted:
- **terminal-bench@2.0** (89 tasks) — Terminal agent tasks
- **swebench-verified@1.0** (500 tasks) — SWE-Bench Verified
- **swebenchpro@1.0** (731 tasks) — Multi-language SWE
- **code-contests@1.0** (44,220 tasks) — Competitive programming
- **simpleqa@1.0** (4,326 tasks) — Simple QA
- **gpqa-diamond@1.0** (198 tasks) — Graduate-level QA
- **aime@1.0** (60 tasks) — Competition math
- **arc_agi_2@1.0** (167 tasks) — Abstract reasoning
- **bixbench@1.5** (205 tasks) — Bioinformatics
- **algotune@1.0** (154 tasks) — Algorithm optimization

### Adapter Examples

Existing adapters provide patterns for new benchmark integration:
- **BixBench adapter**: Converts bioinformatics tasks, each with custom Docker environments containing specific data/tools
- **ARC-AGI-2 adapter**: Converts abstract reasoning puzzles, with JSON-based test verification
- **AutoCodeBench adapter**: Converts code generation tasks from various sources

### inspect-harbor Usage Patterns

```bash
# Basic eval with default solver
inspect eval inspect_harbor/terminal_bench_sample --model openai/gpt-5

# Oracle validation
inspect eval inspect_harbor/hello_world --solver inspect_harbor/oracle

# Custom solver
inspect eval inspect_harbor/terminal_bench --solver inspect_swe/claude_code --model anthropic/claude-sonnet-4-5

# Filter tasks
from inspect_harbor import harbor
task = harbor(
    dataset_name_version="terminal-bench@2.0",
    dataset_task_names=["task-1", "task-2"],  # Include filter (supports globs)
    n_tasks=10,  # Max tasks
)
```

### Harbor Parameter Sweeps

```bash
harbor sweeps run  # Run parameter sweeps across configurations
```

### Training Data Generation

Harbor supports exporting successful trajectories:
```bash
harbor traces export --path trials --recursive --episodes last --filter success \
  --sharegpt --push --repo my-org/harbor-sft-data
```

---

## 8. Gaps, Limitations, and Custom Engineering Needed

### Gap 1: Non-Containerized Benchmarks

Harbor's task model assumes each task runs in a Docker container. Benchmarks that are purely API-based (like LongMemEval with GPT-4o judging) or require cloud database access (Spider2 with BigQuery/Snowflake) need creative adapter engineering:

- **LongMemEval**: Could use a minimal Alpine/Python container, but the core challenge is injecting ~1.5M tokens of conversation history. The container is almost incidental.
- **Spider2 (cloud databases)**: Requires `allow_internet=true`, credential injection, and potentially external DB setup before eval runs.
- **Spider2-Lite (SQLite)**: Most adaptable — self-contained databases can be baked into the Docker image.

### Gap 2: Context Window and Memory Management

Harbor/inspect-harbor's default ReAct solver has basic context compaction (`CompactionEdit`), but benchmarks like LongMemEval that deliberately test memory capabilities need solvers with sophisticated RAG, memory management, or very long context windows. This is a solver-level concern, not a framework limitation — but it means you need to implement memory-aware solvers.

### Gap 3: Evaluation Metrics Beyond Binary

Harbor's native reward system (`reward.txt`) is simple: typically a binary 0/1 or a single float. Some benchmarks require:
- **Multi-metric evaluation** (partially supported via `reward.json`)
- **Partial credit scoring** (supported if test.sh outputs fractional rewards)
- **LLM-as-judge scoring** (supported — test.sh can call an LLM API for evaluation)
- **CSV comparison** (Spider2's evaluation approach, needs custom test.sh)

### Gap 4: Spider2 Adapter Engineering

Building a Spider2 adapter requires:
1. Converting JSONL questions to `instruction.md` format with schema context
2. Packaging SQLite databases + external knowledge files into Docker environments
3. Implementing CSV comparison in `test.sh` (can port Spider2's evaluation suite)
4. For cloud databases: managing BigQuery/Snowflake credentials, setup, and teardown
5. Handling the 547 diverse database schemas

Estimated effort: **Medium** for Spider2-Lite SQLite subset, **High** for full Spider2 with cloud databases.

### Gap 5: LongMemEval Adapter Engineering

Building a LongMemEval adapter requires:
1. Converting JSON chat histories to `instruction.md` — challenge is the sheer size (up to ~1.5M tokens)
2. Implementing GPT-4o QA judging in `test.sh` (requires API key injection)
3. Deciding whether the agent gets raw conversation history or must implement its own retrieval
4. Handling the different subsets (oracle, S, M) as separate datasets
5. Managing temporal metadata and question types

Estimated effort: **Medium** for LongMemEval_oracle (500 questions, pre-filtered evidence), **High** for LongMemEval_M (requires agent to handle ~1.5M tokens).

### Gap 6: No Unified Leaderboard

Harbor and inspect-harbor don't provide a unified comparison dashboard across different benchmark types. You can use:
- Harbor's web viewer (`harbor view`) for native runs
- Inspect AI's log viewer / VS Code extension for inspect-harbor runs
- Custom aggregation for cross-benchmark comparison

### Gap 7: inspect-harbor is New and Rapidly Evolving

inspect-harbor went from v0.1.0 to v0.4.5 in ~2 weeks (Feb 10-25, 2026), with 12 releases. The API surface may still be unstable. The package has only 3 GitHub stars, suggesting limited community adoption so far.

### Gap 8: Mixed Execution Modes

If you want to compare Harbor-native agents (claude-code via `harbor run`) with Inspect AI solvers (custom solver via `inspect eval`), you'll need custom engineering to normalize results into a common format. Harbor's `result.json` and Inspect AI's `.eval` log format are different.

### Gap 9: Cost Management

Running evals at scale involves significant costs:
- LLM API calls (model under test + judge models for LLM-as-judge scoring)
- Cloud sandbox compute (Modal, Daytona)
- Cloud database access (Spider2 BigQuery/Snowflake)
- inspect-harbor enforces minimum 6 GB RAM per container

No built-in cost tracking or budget enforcement exists in either framework.

---

## Summary: What to Build

For a general-purpose eval runner that mixes and matches solvers and benchmarks:

1. **Use Harbor + inspect-harbor as the foundation** — they handle the hardest parts (container management, task format, scoring, agent scaffolding)

2. **Write Harbor adapters** for Spider2-Lite and LongMemEval using the existing adapter system (`harbor adapters init`)

3. **Register custom solvers** as Inspect AI solvers (for inspect-harbor) and/or Harbor agents (for native execution)

4. **Create a thin orchestration layer** that:
   - Reads a configuration file specifying benchmark × solver × model combinations
   - Dispatches to either `harbor run` (native agents) or `inspect eval` (Inspect solvers)
   - Aggregates results into a unified comparison format

5. **Start with the path of least resistance**:
   - Terminal-Bench and SWE-Bench: already in Harbor's registry, ready to use
   - Spider2-Lite (SQLite): self-contained, moderate adapter effort
   - LongMemEval_oracle: manageable context, moderate adapter effort

---

## Sources

| Source | URL | Date Accessed |
|--------|-----|--------------|
| Harbor (Laude Institute) GitHub | https://github.com/laude-institute/harbor | Mar 1, 2026 |
| Harbor Framework Website | https://harborframework.com/ | Mar 1, 2026 |
| Harbor Registry | https://harborframework.com/registry | Mar 1, 2026 |
| inspect-harbor PyPI | https://pypi.org/project/inspect-harbor/ | Mar 1, 2026 |
| inspect-harbor GitHub | https://github.com/meridianlabs-ai/inspect_harbor | Mar 1, 2026 |
| Inspect AI Documentation | https://inspect.ai-safety-institute.org.uk/ | Mar 1, 2026 |
| Inspect AI PyPI | https://pypi.org/project/inspect-ai/ | Mar 1, 2026 |
| Spider2 Project | https://spider2-sql.github.io/ | Mar 1, 2026 |
| Spider2 GitHub | https://github.com/xlang-ai/Spider2 | Mar 1, 2026 |
| Spider2 Paper | arXiv:2411.07763 (Lei et al., 2024) | Mar 1, 2026 |
| LongMemEval GitHub | https://github.com/xiaowu0162/LongMemEval | Mar 1, 2026 |
| LongMemEval HuggingFace | https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned | Mar 1, 2026 |
| LongMemEval Paper | arXiv:2410.10813 (Wu et al., 2024) | Mar 1, 2026 |
| Harbor (av/harbor) — different project | https://github.com/av/harbor | Mar 1, 2026 |
| DeepWiki (laude-institute/harbor) | DeepWiki analysis | Mar 1, 2026 |

### Note on Disambiguation

The original research prompt referenced `https://github.com/av/harbor`, which is a **different project** — a Docker Compose orchestration tool for local LLM stacks (Ollama, Open WebUI, etc.) with 2.5K stars. It includes its own `harbor bench` (LLM-as-judge benchmarking), `lm-evaluation-harness` integration, and Promptfoo integration, but these are unrelated to the Laude Institute's Harbor framework. The `inspect-harbor` package bridges to the **Laude Institute's Harbor** (`laude-institute/harbor`), not av/harbor.

---

## Research Gaps

1. **inspect-harbor source code**: I could not directly read the full Python source files from GitHub (repository rendering limitations). My understanding is based on package metadata, README content, and structural analysis.

2. **Harbor's programmatic API stability**: While Harbor exports Python classes for programmatic use, documentation on API stability guarantees is sparse. The framework is actively evolving (v0.1.x).

3. **inspect-harbor custom solver examples**: I found documentation on how to override solvers but no detailed examples of building complex custom solvers specifically for Harbor tasks.

4. **Cost benchmarks**: No public data on typical costs for running full benchmark suites at scale using Harbor's cloud environments.

5. **Community adapters**: The adapter system is well-documented but I found limited evidence of community-contributed adapters (most appear to be from the core team).
