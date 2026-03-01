# Building a General-Purpose Eval Runner with Harbor, Inspect AI, and inspect-harbor

**Research Report -- March 2026**

---

## 1. Executive Summary

Building a general-purpose eval runner that can mix-and-match different agent solvers against different benchmarks like Spider2 and LongMemEval is achievable, but requires integrating components from three distinct ecosystems that were not originally designed to work together. The key pieces are: **Harbor (av/harbor)** for LLM infrastructure orchestration, **Inspect AI** as the eval execution framework, and **inspect-harbor** as a bridge to containerized evaluation tasks -- though critically, the "Harbor" in `inspect-harbor` refers to the **Harbor Framework** (harborframework.com), a separate project from `av/harbor`, the LLM stack management tool.

Harbor (av/harbor) excels at spinning up and managing LLM backends (Ollama, vLLM, llama.cpp, etc.) through Docker Compose orchestration, and includes three built-in eval capabilities: **Harbor Bench** (LLM-as-judge benchmarking), **Promptfoo** (prompt testing and red-teaming), and **lm-evaluation-harness** (standard NLP benchmarks). However, none of these natively support agentic evaluation workflows where a solver must interact with external tools, databases, or sandboxed environments. Inspect AI fills this gap with its Task/Solver/Scorer/Dataset architecture, Docker/Kubernetes sandbox support, and an agent bridge system that can wrap third-party agents into its evaluation pipeline. The `inspect-harbor` package (v0.4.5, Feb 2026) provides 40+ containerized evaluation datasets through the Harbor Framework registry, including a `spider2-dbt@1.0` adapter.

The most practical architecture for a general-purpose eval runner would use Inspect AI as the central orchestration framework (defining Tasks that pair Solvers with benchmark Datasets and Scorers), Harbor (av/harbor) as the LLM backend provider (serving models via OpenAI-compatible APIs), and custom engineering to wrap benchmarks like Spider2 and LongMemEval as Inspect AI Tasks. Significant custom work would be needed for: (a) building an Inspect AI ModelAPI provider that auto-discovers Harbor's running backends, (b) writing agentic solvers with tool-use capabilities for benchmarks like Spider2, (c) creating benchmark-specific scorers, and (d) managing the additional infrastructure (Snowflake/BigQuery credentials for Spider2, RAG pipelines for LongMemEval).

---

## 2. Background & Context

### 2.1 Harbor (av/harbor)

Harbor is an open-source CLI and companion desktop app (Apache-2.0 license, 2.5k GitHub stars, v0.4.1 as of Feb 2026) that orchestrates a complete local LLM stack using Docker Compose. Created by developer `av`, it manages 50+ services across three categories:

- **Backends**: Inference engines like Ollama, llama.cpp, vLLM, TabbyAPI, Aphrodite Engine, SGLang, KTransformers, mistral.rs
- **Frontends**: Web UIs like Open WebUI, ComfyUI, LibreChat
- **Satellites**: Auxiliary services like SearXNG (search), Dify (workflows), LiteLLM (API gateway), LangFuse (observability), and evaluation tools

The core of Harbor is a 13,000+ line Bash script (`harbor.sh`) that resolves Docker Compose files based on requested services, detects hardware capabilities (NVIDIA/AMD GPUs), and manages a multi-layer configuration system (default profile -> active `.env` -> per-service overrides). Services are automatically wired together through "cross-compose" files (e.g., `compose.x.webui.ollama.yml` sets `OLLAMA_BASE_URL` when both are running).

Source: [GitHub av/harbor README](https://github.com/av/harbor), [Harbor Wiki](https://github.com/av/harbor/wiki)

### 2.2 Inspect AI

Inspect AI is an open-source Python framework (MIT license) developed by the UK AI Safety Institute (AISI) for evaluating LLMs. It provides a structured approach to evaluations with four core abstractions:

- **Task**: The fundamental unit of evaluation, bundling a Dataset, Solver, and Scorer
- **Dataset**: A collection of `Sample` objects with `input`, `target`, `metadata`, etc.
- **Solver**: An async function that transforms a `TaskState` by interacting with the model
- **Scorer**: Evaluates the solver's output against the expected target

Inspect AI supports Docker and Kubernetes sandboxes, an agent bridge for wrapping third-party agents (OpenAI Agents SDK, LangChain, Claude Code, etc.), MCP tool integration, and over 100 pre-built benchmarks via the `inspect_evals` companion repo. Tasks are registered via setuptools entry points and can be run from the CLI (`inspect eval`) or programmatically.

Source: [Inspect AI Documentation](https://inspect.ai-safety-institute.org.uk/), [GitHub UKGovernmentBEIS/inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai)

### 2.3 inspect-harbor

The `inspect-harbor` package (v0.4.5, MIT license, maintained by Meridian Labs / jjallaire) bridges **Inspect AI** with the **Harbor Framework** (harborframework.com) -- a separate project from av/harbor that focuses on containerized agent evaluation. It maps Harbor Framework concepts to Inspect AI concepts:

| Harbor Framework Concept | Inspect AI Concept |
|---|---|
| Harbor Task | `Sample` |
| Harbor Dataset | `Task` |
| `instruction.md` | `Sample.input` |
| `environment/` (Dockerfile) | `SandboxEnvironmentSpec` |
| `tests/test.sh` | `Scorer` (harbor_scorer) |
| `solution/solve.sh` | `Solver` (oracle) |

It provides 40+ datasets including terminal-bench, swebenchpro, swe-lancer-diamond, compilebench, replicationbench, and spider2-dbt@1.0.

Source: [PyPI inspect-harbor](https://pypi.org/project/inspect-harbor/), [GitHub meridianlabs-ai/inspect_harbor](https://github.com/meridianlabs-ai/inspect_harbor)

### 2.4 Target Benchmarks

**Spider 2.0** (arXiv:2411.07763, ICLR 2025 Oral) evaluates LLMs on real-world enterprise text-to-SQL workflows across Snowflake, BigQuery, SQLite, and DuckDB. It contains 547 tasks in the main settings (Snow/Lite) and 68 in the DBT setting. GPT-4o achieves only ~10-13% accuracy, reflecting the difficulty of multi-statement SQL over 1000+ column enterprise databases. Source: [GitHub xlang-ai/Spider2](https://github.com/xlang-ai/Spider2)

**LongMemEval** (arXiv:2410.10813, ICLR 2025) benchmarks long-term memory capabilities of chat assistants across 500 questions spanning five abilities: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention. It uses an LLM-as-judge scoring approach. Source: [GitHub xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval)

---

## 3. Key Findings

### 3.1 Harbor's Architecture for Service Orchestration

Harbor's architecture is built around Docker Compose file resolution. When a user runs `harbor up ollama vllm`, the CLI:

1. Parses the service list and appends any configured defaults
2. Scans for matching `compose.SERVICE.yml` files (base definitions)
3. Finds `compose.x.A.B.yml` cross-compose files where both A and B are in the service list
4. Detects hardware capabilities (NVIDIA GPU, ROCm) and adds matching capability overlays
5. Passes all resolved files to `docker compose -f file1 -f file2 ... up -d --wait`

This resolution happens in the `compose_with_options()` function (harbor.sh:402-520) or, when `HARBOR_LEGACY_CLI=false`, delegates to a TypeScript routine (`routines/mergeComposeFiles.ts`) running on Deno.

Services communicate over a shared `harbor-network` Docker network. Backend services expose OpenAI-compatible APIs that frontends and satellites can consume. Harbor's configuration system uses `HARBOR_*` environment variables managed through `.env` files, with a `profiles/default.env` template containing ~800 variables.

The key architectural insight for eval purposes is that Harbor treats all LLM backends uniformly through OpenAI-compatible APIs. Any eval tool that can hit an OpenAI-compatible endpoint can use any Harbor-managed backend. Harbor Bench, Promptfoo, and lm-evaluation-harness all work this way.

Source: [Harbor Wiki - Core Architecture](https://github.com/av/harbor/wiki), [DeepWiki av/harbor](https://deepwiki.com/av/harbor)

### 3.2 Harbor's Built-in Eval Capabilities

Harbor includes three evaluation-related services, each with different strengths:

#### Harbor Bench (Built-in, handle: `bench`)

Harbor Bench is a custom Deno-based benchmarking tool (`bench/` directory) focused on LLM-as-judge evaluation. It:

- Works against any OpenAI-compatible API
- Uses YAML-defined tasks with free-form `criteria` evaluated by a judge LLM
- Supports a **variants** permutation system (temperature, model, API URL combinations)
- Produces HTML reports, JSON, and CSV results
- Runs in a Docker container

Task format:
```yaml
- tags: [easy, area]
  question: How to eat an elephant?
  criteria:
    bites: Response mentions one bite at a time
    context: Response mentions it's a metaphor
```

Configuration is entirely via `harbor bench` commands that set `HARBOR_BENCH_*` variables. There is no concept of "solvers" in Harbor Bench -- it simply sends prompts to an API and evaluates responses.

Source: [Harbor Wiki - Harbor Bench](https://github.com/av/harbor/wiki/5.1.-Harbor-Bench)

#### lm-evaluation-harness (Satellite, handle: `lmeval`)

EleutherAI's lm-evaluation-harness integration, optimized for running against OpenAI-compatible APIs (`--model local-completions`). Provides access to standard NLP benchmarks (GSM8K, MMLU, etc.). Configuration via `harbor lmeval` commands.

Source: [Harbor Wiki - lm-evaluation-harness](https://github.com/av/harbor/wiki/2.3.17-Satellite:-lm-evaluation-harness)

#### Promptfoo (Satellite, handle: `promptfoo`/`pf`)

Promptfoo integration for testing, evaluating, and red-teaming LLM applications. Uses its own YAML config format. Pre-configured to work with Ollama. Includes built-in examples.

Source: [Harbor Wiki - Promptfoo](https://github.com/av/harbor/wiki/2.3.28-Satellite:-Promptfoo)

**None of these three tools support agentic evaluation** -- that is, evaluations where the agent must use tools, interact with external systems, or operate in a sandboxed environment.

### 3.3 inspect-harbor: The Critical Naming Confusion

A crucial finding is that `inspect-harbor` (the Python package) bridges Inspect AI with the **Harbor Framework** (harborframework.com), which is a **completely separate project** from av/harbor (the LLM stack tool). The Harbor Framework is focused on containerized agent evaluation tasks with:

- A registry of datasets (40+ as of Feb 2026)
- Docker-based sandbox environments per task
- Test scripts (`test.sh`) for automated verification
- Instruction files and solution scripts

This means there is **no existing integration** between Inspect AI and av/harbor's LLM stack management. Connecting them would need to be built. However, inspect-harbor is still highly relevant because:

1. It demonstrates the pattern for wrapping containerized benchmarks as Inspect AI tasks
2. It already includes `spider2-dbt@1.0` (68 tasks, local DuckDB, no cloud credentials needed)
3. Its architecture (mapping Docker environments to Inspect sandboxes, test scripts to scorers) is the model to follow

Source: [PyPI inspect-harbor 0.4.5](https://pypi.org/project/inspect-harbor/), [GitHub meridianlabs-ai/inspect_harbor](https://github.com/meridianlabs-ai/inspect_harbor)

### 3.4 Inspect AI's Solver Architecture

Inspect AI solvers are async functions with the signature `async def solve(state: TaskState, generate: Generate) -> TaskState`. The `@solver` decorator registers them for CLI resolution and logging. Key aspects:

- **Composition**: Solvers chain sequentially via `chain()` or by passing a list to `Task`
- **Tool use**: Solvers can equip models with tools (`bash()`, `python()`, `text_editor()`, `web_search()`, custom `@tool` functions, MCP tools)
- **Agent bridge**: `agent_bridge()` wraps Python-based agents; `sandbox_agent_bridge()` wraps CLI-based agents via a proxy server on port 13131
- **Runtime override**: `--solver` CLI flag lets you swap solvers at eval time
- **Early termination**: Solvers can set `state.completed = True`

The default solver in inspect-harbor is a ReAct agent with `bash(timeout=300)`, `python(timeout=300)`, `update_plan()`, and `CompactionEdit()` -- demonstrating what a "general agent solver" looks like.

Source: [Inspect AI Solvers Documentation](https://inspect.ai-safety-institute.org.uk/)

### 3.5 How to Define and Register New Agent Solvers

To wrap a custom agent as a solver for the eval runner, you have several paths:

**Path 1: Native Inspect Solver** -- Write a `@solver` decorated function that implements your agent's logic using Inspect's tool system:
```python
@solver
def my_agent_solver(tools: list[str] = ["bash", "python"]):
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # Configure tools
        state.tools = [bash(), python()]
        # Agent loop
        while not state.completed:
            state = await generate(state)
            # Process tool calls, check completion
        return state
    return solve
```

**Path 2: Agent Bridge (Python agents)** -- Use `agent_bridge()` with `model="inspect"` to route API calls through Inspect's model provider:
```python
@solver
def my_langchain_agent():
    return agent_bridge(agent_fn, model="inspect")
```

**Path 3: Sandbox Agent Bridge (CLI agents)** -- For agents that run as CLI tools in a container:
```python
@solver
def my_cli_agent():
    return sandbox_agent_bridge(
        command="my-agent --api-url http://localhost:13131"
    )
```

**Registration**: Solvers register via setuptools entry points in `pyproject.toml`:
```toml
[project.entry-points.inspect_ai]
my_solvers = "my_package._registry"
```

Source: [Inspect AI Agent API](https://inspect.ai-safety-institute.org.uk/), [inspect-harbor default solver](https://github.com/meridianlabs-ai/inspect_harbor)

### 3.6 How to Define and Register New Benchmarks/Datasets

#### For Inspect AI Tasks:

Benchmarks become Inspect AI `Task` objects that bundle a Dataset, Solver, and Scorer:

```python
@task
def spider2_dbt():
    return Task(
        dataset=load_spider2_dbt_dataset(),
        solver=[my_sql_agent_solver()],
        scorer=spider2_csv_scorer(),
        sandbox=("docker", "spider2-env")
    )
```

Datasets can be loaded from JSON/JSONL (`json_dataset()`), CSV (`csv_dataset()`), Hugging Face Hub (`hf_dataset()`), or programmatic construction (`MemoryDataset`). Complex record-to-sample transformations use `record_to_sample` functions.

#### Spider2 Integration:

Spider2 has three settings with different integration difficulty:

| Setting | Tasks | Infrastructure | Difficulty |
|---|---|---|---|
| Spider2-DBT | 68 | Local DuckDB only | Low (already in inspect-harbor) |
| Spider2-Snow | 547 | Snowflake account | Medium |
| Spider2-Lite | 547 | BigQuery + Snowflake + SQLite | High |

For Spider2-DBT, `inspect-harbor` already has `spider2-dbt@1.0`. For Snow/Lite, you'd need to:
1. Load instances from `spider2-snow.jsonl` or `spider2-lite.jsonl`
2. Create an agentic solver with SQL execution tools (`SNOWFLAKE_EXEC_SQL`, `BIGQUERY_EXEC_SQL`, etc.)
3. Build a custom scorer that compares output CSVs using pandas DataFrame matching (porting Spider2's `compare_pandas_table`)
4. Inject database credentials into the sandbox environment

#### LongMemEval Integration:

LongMemEval is more straightforward to wrap:
1. Load from `longmemeval_oracle.json` (or S/M variants) on Hugging Face (`xiaowu0162/longmemeval-cleaned`)
2. Map to `Sample` objects: `input` = formatted chat history + question, `target` = expected answer
3. For solvers: long-context approach (stuff all sessions) or RAG approach (index + retrieve + generate)
4. Scorer: custom scorer replicating LongMemEval's per-type-specific LLM-as-judge prompts (off-by-one tolerance for temporal, latest-answer for knowledge-update, abstention detection)

The M variant (~1.5M tokens per instance) exceeds most model context windows; the oracle variant fits in 128K context.

Source: [Spider2 GitHub](https://github.com/xlang-ai/Spider2), [LongMemEval GitHub](https://github.com/xiaowu0162/LongMemEval), [arXiv:2411.07763](https://arxiv.org/abs/2411.07763), [arXiv:2410.10813](https://arxiv.org/abs/2410.10813)

### 3.7 The Eval Execution Pipeline

The end-to-end pipeline for running a solver against a benchmark in the proposed architecture:

**Phase 1: Infrastructure Setup (Harbor)**
1. `harbor up ollama vllm litellm` -- Start LLM backends
2. `harbor config set ...` -- Configure models, quantization, GPU allocation
3. Models are now accessible via OpenAI-compatible APIs on the Docker network

**Phase 2: Eval Execution (Inspect AI)**
1. **Task Resolution**: `inspect eval my_package/spider2_dbt --model openai/gpt-4o --solver my_agent` resolves the task, model, and solver
2. **Dataset Preparation**: Samples loaded, field-mapped, filtered, shuffled. Epochs cause sample duplication
3. **TaskState Creation**: Each sample becomes a `TaskState` with initial messages, target, metadata
4. **Sandbox Setup**: Docker containers created per-task (for benchmarks requiring isolated environments)
5. **Solver Execution**: For each `TaskState`, the solver chain executes. The solver calls `generate()` (hitting the LLM API), processes tool results, and iterates
6. **Scoring**: Configured Scorer evaluates output against target. For Spider2: CSV comparison. For LongMemEval: LLM-as-judge
7. **Metrics Aggregation**: Scores aggregated across samples and epochs
8. **Logging**: Results written to `EvalLog` (JSON format with `EvalSpec`, `EvalPlan`, `EvalSample`, `EvalResults`)
9. **Cleanup**: Sandbox containers torn down

**Parallelism**: Inspect AI uses async execution with `anyio.Semaphore` for concurrency control. `--max-samples` limits per-task parallelism; `--max-tasks` limits inter-task parallelism.

Source: [Inspect AI Documentation](https://inspect.ai-safety-institute.org.uk/)

### 3.8 Existing Examples and Patterns

#### Pattern 1: Harbor Bench against multiple backends
```bash
harbor up ollama vllm
harbor bench variants --model llama3.1:8b --apiUrl http://ollama:11434 --apiUrl http://vllm:8000
harbor bench run --name multi-backend
```
This demonstrates Harbor's ability to run the same eval across different backends, but is limited to simple prompt-response evaluation.

#### Pattern 2: inspect-harbor default agent
```bash
pip install inspect-harbor
inspect eval inspect_harbor/terminal_bench_sample --model openai/gpt-4o
```
The default solver is a ReAct agent with bash, python, plan management, and compaction -- a good template for building custom agentic solvers.

#### Pattern 3: lm-evaluation-harness against Harbor backends
```bash
harbor up vllm
harbor lmeval model meta-llama/Meta-Llama-3-8B-Instruct
harbor lmeval api $(harbor url -i vllm)
harbor lmeval --tasks gsm8k --limit 10
```
Demonstrates Harbor providing the LLM backend for an external eval framework.

#### Pattern 4: Inspect AI custom ModelAPI
Inspect AI's extension system allows registering custom model providers. A `harbor` ModelAPI could auto-discover running backends:
```python
@modelapi(name="harbor")
class HarborModelAPI(ModelAPI):
    async def generate(self, input, tools, config):
        # Hit Harbor's LiteLLM or direct backend API
        ...
```

Source: [Harbor Wiki - Harbor Bench](https://github.com/av/harbor/wiki/5.1.-Harbor-Bench), [inspect-harbor docs](https://meridianlabs-ai.github.io/inspect_harbor/)

---

## 4. Analysis

### 4.1 Recommended Architecture

The most viable architecture for a general-purpose eval runner uses **Inspect AI as the central orchestrator** with **Harbor (av/harbor) as the infrastructure layer**:

```
┌──────────────────────────────────────────────────────────┐
│                    Eval Runner CLI                        │
│  (orchestrates eval configurations, reports results)     │
├──────────────────────────────────────────────────────────┤
│                      Inspect AI                          │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Tasks    │  │   Solvers    │  │    Scorers       │  │
│  │          │  │              │  │                  │  │
│  │ spider2  │  │ react_agent  │  │ csv_match        │  │
│  │ longmem  │  │ cot_solver   │  │ llm_judge        │  │
│  │ custom   │  │ cli_bridge   │  │ exact_match      │  │
│  └──────────┘  └──────────────┘  └──────────────────┘  │
├──────────────────────────────────────────────────────────┤
│                Harbor (av/harbor)                         │
│  ┌─────────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌─────────┐ │
│  │ Ollama  │ │ vLLM │ │llama │ │LiteLLM │ │LangFuse │ │
│  │         │ │      │ │ .cpp │ │(router)│ │(observe)│ │
│  └─────────┘ └──────┘ └──────┘ └────────┘ └─────────┘ │
├──────────────────────────────────────────────────────────┤
│              Benchmark Infrastructure                     │
│  ┌───────────┐ ┌─────────────┐ ┌────────────────────┐  │
│  │ Docker    │ │ Snowflake/  │ │ HuggingFace Hub    │  │
│  │ Sandboxes │ │ BigQuery    │ │ (datasets)         │  │
│  └───────────┘ └─────────────┘ └────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 4.2 Why Inspect AI as the Orchestrator (Not Harbor Bench)

Harbor Bench is too limited for this use case:
- **No tool use**: It only sends prompts and evaluates responses
- **No sandbox support**: Cannot run agents in isolated environments
- **No solver abstraction**: No way to swap different agent strategies
- **YAML-only tasks**: Cannot represent complex benchmarks with multi-step evaluation
- **Deno-based**: Less ecosystem compatibility than Python

Inspect AI provides all of these plus an established extension system, 100+ pre-built benchmarks, and active development by AISI.

### 4.3 Role of Harbor (av/harbor)

Harbor serves as the **infrastructure management layer** -- not the eval orchestrator. Its value in this architecture is:

1. **Backend lifecycle management**: `harbor up vllm ollama` starts inference engines with correct GPU configuration
2. **Model management**: `harbor ollama pull`, `harbor hf download` for model acquisition
3. **API routing**: LiteLLM integration for unified API endpoint across backends
4. **Configuration profiles**: Save and switch between different hardware/model configurations
5. **Observability**: LangFuse integration for tracing eval calls
6. **Reproducibility**: `harbor eject` generates standalone Docker Compose for reproducible setups

The connection between Harbor and Inspect AI would be through Inspect AI's model configuration pointing at Harbor-managed endpoints:
```bash
# Start infrastructure
harbor up vllm litellm

# Run eval against Harbor backend
inspect eval my_benchmark \
  --model openai/meta-llama/Meta-Llama-3-8B-Instruct \
  -M base_url=$(harbor url litellm)/v1
```

### 4.4 Tradeoffs

**Using Inspect AI + Harbor vs. building from scratch:**
- Pro: Established abstractions, 100+ benchmarks, sandbox support, active maintenance
- Pro: Inspect AI's agent bridge can wrap arbitrary agents without modification
- Con: Two distinct "Harbor" ecosystems create confusion
- Con: No native integration between av/harbor and Inspect AI exists
- Con: Inspect AI's Docker sandbox and Harbor's Docker Compose orchestration may conflict

**Using inspect-harbor for benchmarks vs. wrapping directly:**
- Pro: spider2-dbt already available, demonstrates the pattern
- Pro: 40+ other benchmarks included
- Con: The Harbor Framework registry is a separate system from av/harbor
- Con: Some benchmarks may not have the solver flexibility you need

**Using Harbor Bench for simpler evaluations:**
- Pro: Already integrated with Harbor, zero setup for basic LLM quality testing
- Pro: Variant permutation system is excellent for A/B testing backends
- Con: Only suitable for prompt-response evaluation, not agentic benchmarks

### 4.5 Recommendations

1. **Start with inspect-harbor's spider2-dbt** as a proof-of-concept -- it's already working with 68 tasks, no cloud credentials needed
2. **Build an Inspect AI ModelAPI extension** for auto-discovering Harbor backends via `harbor url` commands
3. **Wrap LongMemEval as an Inspect AI Task** -- it's self-contained JSON data requiring only LLM API access, making it the lowest-friction new benchmark to integrate
4. **For Spider2-Snow/Lite, use the inspect-harbor pattern** of Docker sandboxes with credential injection rather than trying to run database clients directly
5. **Use Harbor profiles** to manage different backend configurations for systematic comparison
6. **Invest in a thin CLI wrapper** that coordinates `harbor up`, `inspect eval`, and results collection into a single workflow

---

## 5. Open Questions & Gaps

### 5.1 No Existing av/harbor + Inspect AI Integration

The most significant gap is that there is no bridge between av/harbor (the LLM stack tool) and Inspect AI. While Inspect AI can point at any OpenAI-compatible endpoint, there's no automated discovery of Harbor's running services, no lifecycle coordination (ensuring backends are running before eval starts), and no shared configuration. Building this would require:
- A custom Inspect AI `ModelAPI` provider that queries Harbor's service registry
- A pre-eval hook that starts required Harbor services
- Configuration mapping between Harbor's `HARBOR_*` variables and Inspect AI's model configs

### 5.2 Docker Compose Conflicts

Both Harbor and Inspect AI use Docker. Harbor manages its own Docker Compose orchestration (harbor-network, shared volumes), while Inspect AI's sandbox creates separate Docker containers per evaluation sample. How these coexist -- particularly around GPU allocation, network connectivity, and volume mounts -- needs careful engineering. Can an Inspect AI sandbox container reach Harbor's inference backends on harbor-network? This likely requires custom Docker network configuration.

### 5.3 Spider2-Snow/Lite Credential Management

Spider2's Snowflake and BigQuery settings require cloud credentials. How to securely inject these into Inspect AI sandboxes while maintaining reproducibility across different environments is unresolved. The Spider2 team provides a credential access form, but integration with automated eval pipelines is not documented.

### 5.4 LongMemEval Scale Challenges

LongMemEval's M variant requires ~1.5M tokens of context per instance. No current open-weight model supports this context length. The practical approach is the oracle variant (evidence sessions only, ~128K tokens), but this doesn't test the full memory challenge. Integrating a RAG pipeline as part of the solver adds significant complexity.

### 5.5 Solver Portability

While Inspect AI's `@solver` decorator provides a clean abstraction, most real-world agents (OpenHands, Aider, AutoGPT -- all available as Harbor satellites) have their own execution models. The agent bridge system helps, but each agent needs its own integration work. There's no "universal adapter" that makes any Harbor satellite agent into an Inspect AI solver.

### 5.6 Results Aggregation Across Frameworks

If you use Harbor Bench for simple quality tests, Inspect AI for agentic benchmarks, and lm-evaluation-harness for standard NLP tasks, results end up in three different formats (Harbor Bench HTML/CSV, Inspect AI JSON logs, lm-eval JSON). A unified dashboard or results format would need custom engineering. Harbor's LangFuse integration could serve as a common observability layer, but it doesn't aggregate benchmark scores.

### 5.7 Cost and Resource Management

Running agentic evaluations (especially Spider2 with cloud database queries) incurs costs per sample. Neither Harbor nor Inspect AI provides built-in cost tracking across a full eval suite. Budget management, cost-per-benchmark estimation, and automatic stopping when budgets are exceeded would need to be built.

### 5.8 Contradictory Information

During research, no significant contradictions were found in primary sources. However, the naming overlap between Harbor (av/harbor, the LLM stack tool) and Harbor Framework (harborframework.com, the eval task framework) is genuinely confusing and is not well-clarified in the inspect-harbor documentation. The inspect-harbor README describes itself as bridging "Harbor tasks" to Inspect AI without immediately clarifying which "Harbor" it means. This could lead implementers down the wrong path.

---

## 6. Sources

### Primary Repositories
1. **Harbor (av/harbor)**: https://github.com/av/harbor -- LLM stack orchestration tool (Apache-2.0, v0.4.1, Feb 2026)
2. **Inspect AI**: https://github.com/UKGovernmentBEIS/inspect_ai -- Eval framework by UK AISI (MIT)
3. **inspect-harbor**: https://github.com/meridianlabs-ai/inspect_harbor -- Bridge between Inspect AI and Harbor Framework (MIT, v0.4.5, Feb 2026)
4. **Spider2**: https://github.com/xlang-ai/Spider2 -- Enterprise text-to-SQL benchmark (MIT, 740 stars)
5. **LongMemEval**: https://github.com/xiaowu0162/LongMemEval -- Long-term memory benchmark (MIT, 417 stars)

### Documentation
6. **Harbor Wiki**: https://github.com/av/harbor/wiki -- Full service catalog, CLI reference, architecture docs
7. **Harbor Bench Wiki**: https://github.com/av/harbor/wiki/5.1.-Harbor-Bench -- Benchmarking documentation
8. **Harbor lm-evaluation-harness Wiki**: https://github.com/av/harbor/wiki/2.3.17-Satellite:-lm-evaluation-harness
9. **Harbor Promptfoo Wiki**: https://github.com/av/harbor/wiki/2.3.28-Satellite:-Promptfoo
10. **Inspect AI Documentation**: https://inspect.ai-safety-institute.org.uk/
11. **inspect-harbor Documentation**: https://meridianlabs-ai.github.io/inspect_harbor/
12. **inspect-harbor PyPI**: https://pypi.org/project/inspect-harbor/

### Papers
13. **Spider 2.0**: "Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows" -- arXiv:2411.07763 (ICLR 2025 Oral)
14. **LongMemEval**: "LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory" -- arXiv:2410.10813 (ICLR 2025)

### Datasets
15. **LongMemEval Dataset**: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
16. **Spider2 Leaderboard**: https://spider2-sql.github.io/

### DeepWiki Analysis
17. **DeepWiki av/harbor**: https://deepwiki.com/av/harbor -- AI-generated architecture analysis
