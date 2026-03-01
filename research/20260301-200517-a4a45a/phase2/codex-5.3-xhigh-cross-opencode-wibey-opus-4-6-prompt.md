# Cross-Pollination Review

You previously conducted deep research and produced a report. Another AI agent
independently researched the SAME topic. You now have access to both reports.

## Your Task

1. **Read YOUR report** carefully -- understand what you covered well and where you went shallow
2. **Read the OTHER report with healthy skepticism** -- look for:
   - Ideas and angles they explored that you completely missed
   - Areas where they went deeper than you did
   - Claims that seem plausible but lack strong sourcing -- verify these independently
   - Contradictions or disagreements between the reports
   - Unique sources or evidence you didn't find
   - Reasoning or conclusions that don't follow from the evidence
3. **Conduct NEW research** (web searches) on:
   - Avenues inspired by the other report that go BEYOND what either covered
   - Contradictions that need resolution through additional evidence
   - Gaps that both reports share
4. **Write a REFINED analysis** that captures what this peer review uncovered

## Critical Rules

- Do NOT simply copy content from the other report into yours
- Do NOT accept claims from the other report at face value -- verify key facts independently via web search
- Use the other report as a SPRINGBOARD for NEW investigation
- The goal is to explore territory that NEITHER report adequately covered
- Your refined analysis should contain substantial NEW content, not just reorganized old content
- If the other report makes a strong claim your research contradicts, investigate further and present evidence for both sides
- Maintain your unique perspective -- don't homogenize with the other report

## Topic
How can I use Harbor (https://github.com/av/harbor) and inspect-harbor (the Inspect AI integration/bridge for Harbor) to build a general-purpose eval runner that can run different agent solvers against different benchmarks like Spider2, LongMemEval, and others? Specifically research: (1) Harbor's architecture - how it orchestrates agent backends, services, and eval tasks; (2) inspect-harbor's role as the bridge between Inspect AI's eval framework and Harbor's service management; (3) how to define and register new agent solvers (e.g. wrapping a custom agent as a Harbor-compatible solver); (4) how to define and register new benchmarks/datasets (e.g. integrating Spider2 and LongMemEval task suites); (5) the eval execution pipeline - how Harbor manages the lifecycle of running a solver against a benchmark; (6) practical architecture for a general-purpose eval runner that can mix-and-match solvers and benchmarks; (7) existing examples and patterns from Harbor's built-in eval support; (8) gaps, limitations, and areas where custom engineering would be needed.

## Your Original Report
**Research Report: Building a General-Purpose Eval Runner with Harbor + inspect-harbor**

## 1. Harbor architecture (what is orchestrating what)

There are two closely related but operationally different “Harbor” layers in your source set:

1. `av/harbor` is an infrastructure/tooling project centered on Docker Compose service orchestration, service templates/handles, profiles, and tool wrappers (`harbor`, `harbor bench`, `harbor compose setup`). It gives you runtime service control and repeatable eval command automation. [1][2][3][4][5]  
2. `harbor-python` / Harbor Framework docs describe typed registries and evaluation primitives (benchmarks, solvers, jobs/trials, adapters, evaluator/task runner hooks). This is the model/eval abstraction layer used by `inspect-harbor`. [18][19][20][21][22][23][24][25][26][30]

This split matters: the strongest architecture is to use `av/harbor` for service/runtime management and Harbor Framework + `inspect-harbor` for typed eval execution.

## 2. inspect-harbor’s role as Inspect AI bridge

`inspect-harbor` is an Inspect AI plugin package (latest shown: `0.2.5`, released **January 13, 2026**) that integrates Harbor benchmark/solver concepts into Inspect tasks/solvers/scorers. [6][7]

Bridge responsibilities:

1. `default_harness` manages service lifecycle (local compose or hosted SDK) and then invokes `inspect_ai.eval(...)`. [8]  
2. `HarborServiceManager` handles local Docker-compose-driven service startup/teardown and service URL discovery. [9]  
3. `SDKServiceManager` handles hosted Harbor SDK service loading/unloading. [10]  
4. `harbor_task` / `sample_setup` build Inspect `Task` objects from Harbor benchmark specs and service requirements. [14]  
5. `harbor_solver` maps Inspect solver calls to Harbor solver specifications. [12]  
6. `harbor_scorer` evaluates samples via Harbor benchmark evaluation flow and returns Inspect `Score`/metrics. [13][11]

So `inspect-harbor` is the glue between Inspect AI execution and Harbor service/benchmark/solver semantics.

## 3. How to define/register new agent solvers

You have two extension points:

1. Harbor-native solver registration: define function/class solver and register with Harbor (`@solver` patterns, registry loading, optional CLI/module registration). [22][23]  
2. Agent registration for custom backends: implement `BaseAgent` (`call`, optional async/batch), then register (`@register_agent`) so solvers can reference it. [27][28][29]

In `inspect-harbor`, you then reference the Harbor solver through `harbor_solver(solver=..., prompt=..., agent=..., tool_choice=..., solver_kwargs=...)`. [12]

Practical pattern:
1. Implement/register agent backend in Harbor Framework.
2. Implement/register solver that targets that agent contract.
3. In Inspect eval config, pass the Harbor solver name + kwargs through `harbor_solver(...)`.

## 4. How to define/register new benchmarks/datasets (Spider2, LongMemEval, others)

Harbor Framework benchmark path:

1. Create benchmark class (subclass benchmark base, implement sample evaluation logic). [24]  
2. Register benchmark (`@benchmark`) and optional wrappers for standardized variants. [25]  
3. Use adapters to normalize dataset shape into Harbor data bundle format (`@adapter`, built-in and custom adapter workflows). [26]

`inspect-harbor` task path:

1. Build Inspect task via `harbor_task(...)` and `sample_setup(...)`. [14]  
2. Existing registry tasks show the pattern for Spider2 and LongMemEval, including args like `difficulty`, `benchmark_kwargs`, `sample_kwargs`, `solver`, `service`, `limit`. [15][16][17]

So for a new benchmark suite:
1. Implement Harbor benchmark + adapter.
2. Register benchmark/wrapper in Harbor registry.
3. Add an `inspect-harbor` task factory (or reuse generic `harbor_task`) that maps dataset samples to Inspect states and scorer.

## 5. Eval execution pipeline (solver vs benchmark lifecycle)

End-to-end lifecycle (Inspect-first with `inspect-harbor`):

1. Harness enters context, starts services (local compose or hosted). [8][9][10]  
2. Inspect task starts; solver step resolves Harbor solver spec and executes solver call path. [12][14]  
3. Scorer step creates Harbor benchmark instance/spec and evaluates samples (`evaluate_sample`, polling completion if needed). [13][11]  
4. Metrics/scores are aggregated in Inspect output. [13]  
5. Harness exits and tears down/unloads services. [8][9][10]

Harbor-native runner lifecycle (Framework-first):

1. `harbor run` loads `JobConfig` and `TrialConfig`. [19][20][21]  
2. Evaluator coordinates tasks/trials/batch runs with configurable task runner hooks (`before_task`, `after_task`, custom runner). [30]  
3. Results are persisted/aggregated per run settings. [19][20][21]

`av/harbor` built-in `harbor bench` lifecycle is command-templated orchestration:
1. Setup command once (often `harbor up`).
2. Expand targets matrix and run per-target eval command.
3. Teardown cleanup. [3][4][5]

## 6. Practical architecture for a general-purpose mix-and-match eval runner

Recommended architecture:

1. **Control plane:** one runner service that owns experiment manifests (`solver_id`, `benchmark_id`, `service_stack`, params, seeds, limits).  
2. **Runtime plane:** `av/harbor` profiles + compose for local backends; optional hosted mode via SDK manager. [2][9][10]  
3. **Registry plane:** Harbor registries for solvers/benchmarks/adapters; enforce stable IDs and versioned metadata. [22][23][24][25][26]  
4. **Execution plane:** Inspect AI + `inspect-harbor` harness/task/solver/scorer for standardized logs and scoring. [8][12][13][14]  
5. **Matrix engine:** generate cross-product of solver x benchmark x service profile x difficulty; run in isolated trials using either Inspect loop or Harbor Job/Trial configs. [19][20][21]  
6. **Results plane:** normalize output schema (run_id, solver_id, benchmark_id, dataset_version, service_digest, metrics, artifacts).

Key design choice:
- If you want strongest Inspect observability and custom Python control, make Inspect + `inspect-harbor` the top orchestrator.
- If you want Harbor-native job/trial config governance, make Harbor runner primary and invoke Inspect tasks where needed.
- Avoid dual orchestration for a single run (pick one top-level executor).

## 7. Existing examples/patterns to copy

1. `harbor-bench` Inspect template shows practical environment templating + setup/teardown for `inspect eval`. [4]  
2. `harbor-bench` core execution code shows setup -> target loop -> teardown orchestration pattern. [5]  
3. `inspect-harbor` registry includes ready task suites (including Spider2, LongMemEval) with consistent argument surfaces. [15][16][17]  
4. Harbor adapters docs show reusable ingestion strategy for heterogeneous datasets. [26]

## 8. Gaps, limitations, and custom engineering needed

1. Documentation split: explicit official mapping between `av/harbor` and Harbor Framework internals is not clearly centralized; you will likely define your own integration boundary. [1][2][18]  
2. Overlapping orchestration layers (`harbor bench`, Harbor jobs/trials, Inspect eval) can duplicate responsibilities unless you standardize ownership. [3][19][30]  
3. Benchmark integration still needs task-specific engineering (dataset prep, sample mapping, benchmark kwargs conventions). [16][17][24][26]  
4. Metric harmonization across benchmarks is not automatic; you need a unifying result schema for cross-benchmark comparison. [13][16][17]  
5. Service reproducibility (exact model backend/image/profile/version pinning) must be enforced by your runner metadata; defaults are not enough for strict reproducibility. [2][9][20]

## Sources

[1] https://github.com/av/harbor  
[2] https://github.com/av/harbor/wiki/1.-Harbor-User-Guide  
[3] https://github.com/av/harbor/tree/main/harbor-bench  
[4] https://github.com/av/harbor/blob/main/harbor-bench/templates/inspect-eval-template.yaml  
[5] https://github.com/av/harbor/blob/main/harbor-bench/src/harbor_bench/core.py  
[6] https://pypi.org/project/inspect-harbor/  
[7] https://github.com/meridianlabs-ai/inspect_harbor  
[8] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/default_harness  
[9] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/HarborServiceManager  
[10] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/SDKServiceManager  
[11] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/HarborBenchmark  
[12] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/harbor_solver  
[13] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/harbor_scorer  
[14] https://meridianlabs-ai.github.io/inspect_harbor/reference/inspect_harbor/task  
[15] https://meridianlabs-ai.github.io/inspect_harbor/registry/tasks/  
[16] https://meridianlabs-ai.github.io/inspect_harbor/registry/tasks/spider2/  
[17] https://meridianlabs-ai.github.io/inspect_harbor/registry/tasks/longmemeval/  
[18] https://harborframework.com/docs/core-concepts  
[19] https://harborframework.com/docs/running-jobs  
[20] https://harborframework.com/docs/running-jobs/job-configuration  
[21] https://harborframework.com/docs/running-jobs/trial-configuration  
[22] https://harborframework.com/docs/solvers/custom-solvers  
[23] https://harborframework.com/docs/solvers/registering-solvers  
[24] https://harborframework.com/docs/benchmarks/benchmarking-tasks  
[25] https://harborframework.com/docs/benchmarks/registering-benchmarks  
[26] https://harborframework.com/docs/adapters/  
[27] https://harborframework.com/docs/agents/base-agents  
[28] https://harborframework.com/docs/agents/registering-agents  
[29] https://harborframework.com/docs/agents/custom-agent-example  
[30] https://harborframework.com/reference/core_api/


## Peer Report (opencode-wibey-opus-4-6)
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
