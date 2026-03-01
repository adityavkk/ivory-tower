I don't have write access in this session — I can't save to the file. I'll present the full research report here instead. You can save it to `amp-deep.md`.

---

# Research Report: Building a General-Purpose Eval Runner with Harbor and Inspect-Harbor

## Critical Preliminary Finding: Two Different "Harbor" Projects

A crucial discovery from this research is that there are **two entirely distinct open-source projects named "Harbor"**, and they serve very different purposes. Understanding which one is relevant is essential before proceeding with any architecture.

### 1. av/harbor — LLM Service Stack Orchestrator
- **Repository**: [github.com/av/harbor](https://github.com/av/harbor)
- **Purpose**: A CLI tool that spins up a complete local LLM stack — inference backends (Ollama, vLLM, llama.cpp), frontends (Open WebUI, LibreChat), and satellite services (SearXNG, LangFuse, etc.) — all pre-wired via Docker Compose with a single `harbor up` command.
- **Eval capability**: Includes **Harbor Bench**, a built-in LLM benchmarking tool that evaluates models against YAML-defined tasks using an LLM judge, and integrates **lm-evaluation-harness** as a satellite service.

### 2. laude-institute/harbor — Agent Evaluation & RL Framework
- **Repository**: [github.com/laude-institute/harbor](https://github.com/laude-institute/harbor)
- **Website**: [harborframework.com](https://harborframework.com/)
- **Purpose**: A framework from the creators of Terminal-Bench for evaluating and optimizing **AI agents** (Claude Code, OpenHands, Codex CLI, etc.) in containerized environments at scale, with support for cloud providers (Daytona, Modal, E2B), RL rollouts, and SFT data generation.
- **Eval capability**: Full agent evaluation pipeline with standardized task format (`task.toml`, `instruction.md`, `environment/`, `tests/`, `solution/`), a benchmark registry, and statistical evaluation across multiple trials.

### 3. inspect-harbor — Bridge to laude-institute/harbor (NOT av/harbor)
- **Repository**: [github.com/meridianlabs-ai/inspect_harbor](https://github.com/meridianlabs-ai/inspect_harbor)
- **Purpose**: Bridges **laude-institute/harbor** tasks to the **Inspect AI** evaluation framework. It maps Harbor tasks to Inspect AI Samples, Harbor datasets to Inspect AI Tasks, and provides solver/agent support.

**The `inspect-harbor` package is designed for `laude-institute/harbor`, not `av/harbor`.** These are fundamentally different systems. The rest of this report covers both projects in depth so you can determine which best fits your use case, and how to build a general-purpose eval runner with the appropriate tools.

---

## 1. av/harbor Architecture: Service Orchestration and Eval

### Service Model

av/harbor organizes its services into three categories ([av/harbor Wiki: Services](https://github.com/av/harbor/wiki/2.-Services)):

- **Frontends**: User-facing interfaces (Open WebUI, LibreChat, Lobe Chat, ChatUI, etc.)
- **Backends**: LLM inference engines (Ollama, vLLM, llama.cpp, TabbyAPI, Aphrodite, SGLang, mistral.rs, KTransformers, etc.)
- **Satellites**: Auxiliary services (SearXNG, Speaches, Dify, n8n, LiteLLM, LangFuse, Harbor Bench, lm-evaluation-harness, OpenHands, Aider, AutoGPT, JupyterLab, etc.)

All services are orchestrated via Docker Compose with automatic cross-service connectivity. Backends expose OpenAI-compatible APIs, allowing frontends and tools to interact interchangeably.

### Harbor Bench (av/harbor's eval tool)

Harbor Bench ([av/harbor Wiki: Harbor Bench](https://github.com/av/harbor/wiki/5.1.-Harbor-Bench)) is a **model-level** (not agent-level) evaluation tool:

**Task Format** — YAML files with this structure:
```yaml
- tags: [medium, reasoning]
  question: "Explain the trolley problem and its variations"
  criteria:
    basic_scenario: "Mentions the original trolley dilemma"
    variations: "Describes at least two common variations"
    ethical_frameworks: "References relevant philosophical frameworks"
```

**Judge-based evaluation** — Uses a separate LLM as judge to evaluate whether responses meet each criterion independently. The judge model is configured separately from the model being tested.

**Permutation testing** — Can test multiple model configurations simultaneously:
```
harbor bench variants --temperature 0 --temperature 0.5 --model modelA --model modelB
```
This creates 4 permutations (2 temperatures × 2 models).

**Output** — Produces `report.html`, `tasks.html`, `results.json`, `results.csv`, `runs.json`, and `config.json`.

**Limitation**: Harbor Bench evaluates **LLM completions**, not **agent behavior in environments**. It sends a prompt, gets a response, and judges the response. It does not support sandboxed execution, tool use, multi-turn agent interaction, or containerized environments.

### Harbor Boost

Harbor Boost is a scriptable Python wrapper that can inject custom workflows (e.g., Chain of Thought) into an existing LLM API. It could theoretically be used to add pre/post-processing to an eval pipeline, but it's not an agent evaluation framework.

### lm-evaluation-harness integration

av/harbor can run EleutherAI's lm-evaluation-harness as a satellite service for standardized few-shot LLM evaluation. This provides access to many established benchmarks (MMLU, HellaSwag, ARC, etc.) but again at the model level, not the agent level.

---

## 2. laude-institute/harbor Architecture: Agent Evaluation

### Core Concepts

laude-institute/harbor is purpose-built for **agent evaluation**. Its architecture centers on these abstractions ([harborframework.com/docs](https://harborframework.com/docs)):

- **Task**: A self-contained evaluation unit with an instruction, execution environment, scoring criteria, and optional reference solution
- **Dataset**: A collection of tasks registered in the Harbor registry
- **Agent**: The system being evaluated (Claude Code, OpenHands, Codex, custom agents)
- **Trial**: A single execution of an agent against a task in a sandboxed container
- **Verifier**: The scoring mechanism that produces a reward (0 or 1) written to `/logs/verifier/reward.txt`

### Task Structure

Every task follows this directory convention ([harborframework.com/docs](https://harborframework.com/docs), [CompileBench migration blog](https://quesma.com/blog/compilebench-in-harbor/)):

```
<task-id>/
├── task.toml           # metadata: author, labels, timeout, resource limits
├── instruction.md      # prompt presented to the agent
├── environment/        # container definition
│   ├── Dockerfile
│   └── ...            # any input files
├── solution/           # optional reference implementation
│   └── solve.sh
└── tests/              # grading logic
    ├── test.sh         # saves reward to /logs/verifier/reward.txt
    └── test_*.py       # optional pytest files
```

The `task.toml` includes configuration like `[agent].timeout_sec`, resource requirements (CPU, memory, GPU), and optional verifier environment variables (e.g., for LLM judges):
```toml
[verifier.env]
MODEL_NAME = "claude-haiku-4-5"
ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"
```

### Execution Pipeline

1. **Environment starts** — Docker container built from `environment/Dockerfile`
2. **Agent sets up** — Agent installed/configured in the container
3. **Agent runs** — Agent receives `instruction.md` and works in the sandboxed environment
4. **Verifier checks** — `tests/test.sh` runs, writes reward to `/logs/verifier/reward.txt`
5. **Environment stops** — Container torn down, results collected

For statistical rigor, Harbor runs **multiple trials** per task. As described by [tessl.io](https://tessl.io/blog/how-to-evaluate-ai-agents-an-introduction-to-harbor/): "Not 'did it pass?' but 'what's the pass rate over N trials?'"

### Agent Types

Harbor supports two agent integration patterns ([Opik/Harbor integration docs](https://www.comet.com/docs/opik/integrations/harbor)):

1. **External agents** — Interface through `BaseEnvironment` via bash commands
2. **Installed agents** — Installed directly into the container and executed in headless mode

Built-in agents include Terminus-2 (Harbor's reference agent), Claude Code, OpenHands, Codex CLI, and MiniSweAgent. Custom agents extend `BaseAgent` from `src/harbor/agents/base.py`.

### Scaling

- **Local**: Docker containers, sequential or low concurrency
- **Cloud**: Daytona, Modal, E2B, Runloop, or self-managed GKE Kubernetes clusters — up to thousands of parallel containers via `--env` flag

### Agent Trajectory Format (ATIF)

Harbor includes a standardized data format ([ATIF docs](https://harborframework.com/docs/agents/trajectory-format)) that captures complete interaction history, tool calls, LLM metrics (token usage, costs, logprobs), and multi-agent system data — usable for debugging, SFT, and RL pipelines.

### Benchmark Registry

Harbor maintains a registry of datasets at [harborframework.com/registry](https://harborframework.com/registry), including Terminal-Bench Pro, SWE-bench Pro, GPQA Diamond, USACO, AlgoTune, BixBench, SWE-Lancer Diamond, and 40+ others.

---

## 3. inspect-harbor: The Inspect AI Bridge

### Architecture and Role

[inspect-harbor](https://github.com/meridianlabs-ai/inspect_harbor) (`pip install inspect-harbor`) maps laude-institute/harbor concepts to Inspect AI concepts:

| Harbor Concept | Inspect AI Concept |
|---|---|
| Task (`instruction.md`) | `Sample.input` |
| Dataset (collection of tasks) | `Task` (Inspect AI task function) |
| Environment (`Dockerfile`) | `SandboxEnvironmentSpec` |
| Verifier (`tests/test.sh`) | Custom `Scorer` |
| Reference solution (`solve.sh`) | Oracle `Solver` |

### Default Agent Scaffold

When no solver is specified, inspect-harbor provides:
- **Agent type**: ReAct agent
- **Tools**: `bash(timeout=300)`, `python(timeout=300)`, `update_plan()`
- **Context management**: `CompactionEdit()` for token window optimization

### Custom Solver Integration

Custom solvers are provided via CLI flag:
```
--solver path/to/custom/agent.py@custom_agent
```

Or programmatically:
```python
from inspect_swe import claude_code
eval(terminal_bench_sample(), solver=claude_code())
```

### Oracle Solver

The Oracle solver executes reference solutions (`solution/solve.sh`) to validate that tasks are correctly configured and solvable — essential for dataset quality assurance.

### Available Dataset Functions

inspect-harbor exposes 40+ Python functions for registered Harbor datasets:
- `terminal_bench()`, `terminal_bench_2_0()` (versioned)
- `swebenchpro()`, `swebench_verified()`
- `swe_lancer_diamond()`
- And many more listed in `REGISTRY.md`

### Task Parameters

Key configuration options:
- `n_tasks` — Maximum number of tasks
- `dataset_task_names` / `dataset_exclude_task_names` — Glob-based filtering
- `sandbox_env_name` — Environment type (default: "docker")
- `override_cpus`, `override_memory_mb`, `override_gpus` — Resource overrides
- `registry_url`, `registry_path` — Custom registry sources
- `path` — Local task directory loading

---

## 4. Defining and Registering New Agent Solvers

### In Inspect AI (via inspect-harbor)

Inspect AI solvers are Python functions decorated with `@solver` ([Inspect AI Solvers docs](https://inspect.aisi.org.uk/solvers.html)):

```python
from inspect_ai.solver import solver, Solver, TaskState, Generate

@solver
def my_custom_agent() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # Custom agent logic: tool use, multi-turn dialog, etc.
        return state
    return solve
```

For agent-style solvers, Inspect AI provides the `@agent` decorator and `react()` for ReAct tool loops:

```python
from inspect_ai.solver import agent
from inspect_ai.solver._agent import react
from inspect_ai.tool import bash, python

@agent
def my_agent():
    return react(tools=[bash(timeout=300), python(timeout=300)])
```

Agents can be converted to solvers with `as_solver()`, and Inspect AI supports bridging agents from third-party frameworks (OpenAI Agents SDK, LangChain, Pydantic AI).

### In laude-institute/harbor (native)

Custom agents extend `BaseAgent` in `src/harbor/agents/base.py`. The framework supports:
- **Installed agents**: A Jinja2 template defines installation into Docker containers, specifying dependencies, agent binary, and authentication ([mixster.dev guide](https://mixster.dev/2026/01/15/terminal-bench-docker/))
- **External agents**: Interface through `BaseEnvironment` via bash commands

Harbor uses LiteLLM for model communication, enabling easy switching between models and providers.

---

## 5. Defining and Registering New Benchmarks/Datasets

### Creating a Harbor Adapter (for laude-institute/harbor)

The [Harbor Adapters documentation](https://harborframework.com/docs/adapters) defines a 9-step process:

1. **Understand the original benchmark** — Identify task instructions, environments, tests, and solutions
2. **Develop adapter code** — Python code that parses original benchmark format and generates Harbor task directories
3. **Create task directories** — Each task gets `task.toml`, `instruction.md`, `environment/`, `tests/`, `solution/`
4. **Verify oracle solutions** — Run Harbor harness to confirm 100% oracle success rate
5. **Run parity experiments** — Validate adapter output matches original benchmark baseline
6. **Document findings** in `parity_experiment.json`
7. **Upload to HuggingFace**
8. **Register in Harbor registry** (JSON index with dataset URLs/versions)
9. **Write comprehensive README**

The adapter code lives in `adapters/<adapter-name>/` with `adapter.py`, `run_adapter.py`, `template/`, and documentation.

### Adding to inspect-harbor

After registering in Harbor's registry, create a wrapper function in inspect-harbor:

```python
def spider2(n_tasks=None, dataset_task_names=None, ...):
    return harbor_task(dataset_name_version="spider2/1.0", ...)
```

The `registry_url` and `registry_path` parameters in inspect-harbor's generic interface allow loading from custom registries without modifying the core package.

### For av/harbor's Harbor Bench

Simply create a YAML tasks file:
```yaml
- tags: [hard, sql]
  question: "Given the following database schema..."
  criteria:
    correct_query: "The SQL query returns the correct result"
    efficiency: "The query uses appropriate joins and indexing"
```
Then point Harbor Bench to it: `harbor bench tasks /path/to/tasks.yml`

---

## 6. Integrating Spider2 and LongMemEval Specifically

### Spider2

[Spider 2.0](https://github.com/xlang-ai/Spider2) (ICLR 2025 Oral) evaluates text-to-SQL workflows across 632 real-world enterprise tasks using databases in BigQuery, Snowflake, and local systems. Key challenges for Harbor/Inspect integration:

- **External dependencies**: Tasks require live database connections (BigQuery, Snowflake), which complicates containerization
- **No existing Harbor adapter**: Spider2 is not in the Harbor registry as of this research
- **Custom harness**: Spider2 has its own eval agents (`spider-agent-lite`, `spider-agent-snow`, `spider-agent-dbt`)
- **Integration path**: Would require writing a Harbor adapter that either (a) containerizes local database tasks with SQLite/DuckDB or (b) provisions cloud database credentials via environment variables in `task.toml`

### LongMemEval

[LongMemEval](https://github.com/xiaowu0162/LongMemEval) (ICLR 2025) benchmarks long-term memory in chat assistants across 500 questions with scalable histories (115K to 1.5M tokens). Integration challenges:

- **Stateful evaluation**: Requires maintaining conversation histories across sessions, which doesn't map cleanly to Harbor's per-task container model
- **Plug-and-play design**: LongMemEval's framework breaks down into indexing, retrieval, and reading stages — designed for integration into existing chat systems
- **No existing Harbor adapter**: Not in the Harbor registry
- **Integration path**: Would require (a) pre-generating conversation histories as part of the task environment, (b) custom verifier scripts that use LLM judges (supported by Harbor via `task.toml` verifier env vars), and (c) careful handling of the multi-session nature

Neither benchmark has an existing Inspect AI eval in the [inspect_evals](https://github.com/UKGovernmentBEIS/inspect_evals) collection either.

---

## 7. Practical Architecture for a General-Purpose Eval Runner

Given the research findings, here are two viable architectures:

### Option A: laude-institute/harbor + inspect-harbor (Recommended for Agent Evals)

This is the purpose-built path for agent evaluation:

```
┌─────────────────────────────────────────────────┐
│              Your Eval Runner CLI                │
│  (orchestrates benchmark selection + solver)     │
├─────────────────────────────────────────────────┤
│              inspect-harbor                      │
│  (bridges Harbor tasks → Inspect AI framework)   │
├─────────────────────────────────────────────────┤
│              Inspect AI                          │
│  (solver execution, scoring, logging)            │
├───────────────┬─────────────────────────────────┤
│  Solvers      │  Datasets                       │
│  ┌──────────┐ │  ┌───────────────┐              │
│  │ ReAct    │ │  │ Terminal-Bench │              │
│  │ClaudeCode│ │  │ SWE-bench Pro │              │
│  │ Custom   │ │  │ Spider2*      │              │
│  │ Oracle   │ │  │ LongMemEval*  │              │
│  └──────────┘ │  └───────────────┘              │
├───────────────┴─────────────────────────────────┤
│          laude-institute/harbor                  │
│  (task registry, container orchestration,        │
│   cloud scaling, ATIF trajectories)              │
├─────────────────────────────────────────────────┤
│          Docker / Cloud (Daytona, Modal)         │
└─────────────────────────────────────────────────┘
* = requires custom adapter
```

**Workflow**:
1. Define benchmarks as Harbor task directories (write adapters for Spider2, LongMemEval)
2. Register them in a custom Harbor registry (JSON)
3. Write Inspect AI solver wrappers for your custom agents
4. Use inspect-harbor to run: `inspect eval my_benchmark --solver my_agent`
5. Results in `./logs` with Inspect AI's standard log format

### Option B: av/harbor + lm-evaluation-harness (For Model-Level Evals Only)

If your focus is on model-level evaluation (not agent behavior in environments):

```
┌──────────────────────────────────────┐
│        av/harbor CLI                 │
│  harbor up ollama webui ...          │
├──────────────────────────────────────┤
│  Harbor Bench (YAML tasks + judge)   │
│  lm-evaluation-harness               │
│  LiteLLM (proxy)                     │
├──────────────────────────────────────┤
│       Docker Compose                 │
└──────────────────────────────────────┘
```

This is simpler but fundamentally limited: no sandboxed execution, no agent tool use, no multi-turn interaction.

### Option C: Hybrid

Use av/harbor for infrastructure (LiteLLM proxy, model serving) alongside laude-institute/harbor + inspect-harbor for the actual agent evaluation pipeline. av/harbor's LiteLLM integration could serve as the model backend that laude-institute/harbor agents call.

---

## 8. Existing Examples and Patterns

### CompileBench → Harbor Migration
[Quesma's CompileBench migration](https://quesma.com/blog/compilebench-in-harbor/) is the best documented example of adapting an existing benchmark to Harbor format. Key takeaway: the migration resulted in a "massive reduction in lines of code" and reduced running the benchmark to a single command.

### Terminal-Bench 2.0
The original benchmark that motivated Harbor's creation. Ships 89 tasks in the Harbor registry. Uses Terminus-2 as the reference agent.

### pi-terminal-bench
[badlogic/pi-terminal-bench](https://github.com/badlogic/pi-terminal-bench) is an example of creating a custom Harbor agent adapter for a specific coding agent ("pi"), demonstrating the plugin pattern.

### inspect-harbor + inspect-swe
The inspect-harbor README shows using `inspect_swe`'s Claude Code solver against Harbor datasets — a working example of the mix-and-match solver/benchmark pattern:
```python
from inspect_swe import claude_code
eval(terminal_bench_sample(), solver=claude_code())
```

### HAL Harness (Alternative)
[princeton-pli/hal-harness](https://github.com/princeton-pli/hal-harness) is a related framework that also supports both custom agents and Inspect AI solvers, with parallel cloud execution on Azure VMs. It could serve as an alternative or complement.

---

## 9. Gaps, Limitations, and Custom Engineering Needed

### Gaps in Research

1. **av/harbor ↔ inspect-harbor relationship**: Despite the original framing, inspect-harbor does NOT bridge to av/harbor. It bridges to laude-institute/harbor. These are entirely separate codebases with different maintainers and different purposes.

2. **laude-institute/harbor internal architecture**: The `BaseAgent` API, `TaskConfig` schema, and detailed `task.toml` specification are not fully documented publicly. The docs site covers usage but not API-level details. Examining `src/harbor/agents/base.py` and `src/harbor/models/task/config.py` directly would be needed.

3. **inspect-harbor internals**: The exact mapping logic, scorer implementation, and sandbox environment setup are not fully documented beyond the README. The PyPI page shows version 0.4.5, indicating active but early-stage development.

4. **Spider2 containerization feasibility**: Spider2 tasks that require BigQuery/Snowflake access present a significant containerization challenge. The credential management and network access requirements conflict with Harbor's sandboxed model.

5. **LongMemEval statefulness**: Harbor's per-task, per-container model doesn't naturally accommodate LongMemEval's multi-session conversation state. Significant adapter engineering would be needed.

### Limitations

1. **av/harbor's Harbor Bench** is model-level only (prompt → response → judge). No agent loop, no tool use, no sandboxed execution.

2. **laude-institute/harbor** is young (released Nov 2025 alongside Terminal-Bench 2.0). The adapter ecosystem is growing but not yet large.

3. **inspect-harbor** is at version 0.4.5 — functional but evolving. Breaking changes are possible.

4. **Platform constraints**: Harbor's Docker-based approach may have issues on Apple Silicon (M1/M2/M3) due to x86/ARM architecture conflicts ([mixster.dev guide](https://mixster.dev/2026/01/15/terminal-bench-docker/)).

5. **LLM judge reliability**: Both Harbor Bench (av/harbor) and Harbor task verifiers (laude-institute/harbor) can use LLM judges, but the judge's own performance is a limiting factor.

### Custom Engineering Required

To build a general-purpose eval runner with mix-and-match solvers and benchmarks:

1. **Harbor adapters** for Spider2 and LongMemEval (Python code converting each benchmark's format to Harbor task directories)
2. **Inspect AI solver wrappers** for each custom agent you want to evaluate
3. **Custom registry** (JSON) if not contributing to the official Harbor registry
4. **Orchestration layer** — a CLI or script that combines benchmark selection, solver selection, and resource configuration into a single command
5. **Result aggregation** — Inspect AI provides logging, but cross-benchmark comparison dashboards would need custom tooling
6. **Credential management** — For benchmarks like Spider2 that need cloud database access, and for LLM judges that need API keys

---

## Sources

### Primary Repositories
- [av/harbor — LLM Service Stack](https://github.com/av/harbor)
- [laude-institute/harbor — Agent Evaluation Framework](https://github.com/laude-institute/harbor)
- [meridianlabs-ai/inspect_harbor — Inspect AI Bridge](https://github.com/meridianlabs-ai/inspect_harbor)
- [UKGovernmentBEIS/inspect_ai — Inspect AI Framework](https://github.com/UKGovernmentBEIS/inspect_ai)
- [UKGovernmentBEIS/inspect_evals — Community Evals](https://github.com/UKGovernmentBEIS/inspect_evals)

### Documentation
- [Harbor Framework Docs](https://harborframework.com/docs)
- [Harbor Adapters Guide](https://harborframework.com/docs/adapters)
- [Harbor Registry](https://harborframework.com/registry)
- [Harbor ATIF Specification](https://harborframework.com/docs/agents/trajectory-format)
- [av/harbor Wiki: Harbor Bench](https://github.com/av/harbor/wiki/5.1.-Harbor-Bench)
- [av/harbor Wiki: Services](https://github.com/av/harbor/wiki/2.-Services)
- [Inspect AI Solvers Reference](https://inspect.aisi.org.uk/solvers.html)
- [Inspect AI Agents Reference](https://inspect.aisi.org.uk/agents.html)
- [inspect-harbor on PyPI](https://libraries.io/pypi/inspect-harbor)

### Benchmarks
- [xlang-ai/Spider2 (ICLR 2025)](https://github.com/xlang-ai/Spider2)
- [xiaowu0162/LongMemEval (ICLR 2025)](https://github.com/xiaowu0162/LongMemEval)
- [Terminal-Bench 2.0 Announcement](https://www.tbench.ai/news/announcement-2-0)

### Blog Posts and Articles
- [Migrating CompileBench to Harbor (Quesma)](https://quesma.com/blog/compilebench-in-harbor/)
- [How to Evaluate AI Agents: Intro to Harbor (tessl.io)](https://tessl.io/blog/how-to-evaluate-ai-agents-an-introduction-to-harbor/)
- [Terminal-Bench 2.0: Raising the Bar (Snorkel AI)](https://snorkel.ai/blog/terminal-bench-2-0-raising-the-bar-for-ai-agent-evaluation/)
- [Terminal-Bench 2.0 on MacOS (mixster.dev)](https://mixster.dev/2026/01/15/terminal-bench-docker/)
- [Evaluate LLM Agents with Harbor (Opik/Comet)](https://www.comet.com/docs/opik/integrations/harbor)
- [Terminal-Bench 2.0 (VentureBeat)](https://venturebeat.com/ai/terminal-bench-2-0-launches-alongside-harbor-a-new-framework-for-testing)

### Related Frameworks
- [princeton-pli/hal-harness](https://github.com/princeton-pli/hal-harness)
- [badlogic/pi-terminal-bench](https://github.com/badlogic/pi-terminal-bench)

### Research Papers
- [Spider 2.0 (ICLR 2025 Oral)](https://openreview.net/forum?id=XmProj9cPs)
- [LongMemEval (ICLR 2025)](https://arxiv.org/abs/2410.10813)
