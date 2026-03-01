This is a deep research task about Harbor and inspect-harbor for building a general-purpose eval runner. Let me plan this out and then conduct thorough research.
Let me start by researching Harbor's architecture and inspect-harbor in parallel.
Good, I have a solid overview of Harbor. Now let me dig deeper into the eval-related functionality, inspect-harbor specifically, and the bench system. Let me run multiple research tasks in parallel.
Excellent -- this is a critical finding. There are **two different projects called "Harbor"**, and `inspect-harbor` bridges to the Laude Institute's Harbor (the eval framework), not av/harbor (the Docker compose tool). Let me now do deeper research on the correct Harbor (Laude Institute) and inspect-harbor.
Now I have comprehensive information on all the key systems. Let me update my progress and write the research report.
Now let me check if there's a specific output location expected:
I can see that my output should go to `phase1/opencode-wibey-opus-4-6-report.md`. Let me write the comprehensive research report now.
The comprehensive research report has been written to `phase1/opencode-wibey-opus-4-6-report.md`. Here's a summary of the key findings:

**Critical Disambiguation**: There are two different "Harbor" projects. The `inspect-harbor` package bridges to the **Laude Institute's Harbor** (`laude-institute/harbor`) — an agent evaluation framework — not `av/harbor` (the Docker Compose tool referenced in the original prompt).

**Key findings across the 8 research areas**:

1. **Harbor's Architecture**: A layered framework with CLI, orchestration (Jobs/Trials), execution runtime (Agents + Docker/cloud Environments + Verifiers), a task registry (45+ curated datasets, ~21K tasks), and persistent storage (ATIF trajectories).

2. **inspect-harbor**: Bridges Harbor tasks to Inspect AI by mapping instruction.md→Sample.input, environment/→SandboxSpec, tests/→Scorer, solution/→Oracle solver. Ships with 45+ pre-built dataset task functions.

3. **New Agent Solvers**: Harbor supports `BaseAgent`/`BaseInstalledAgent` classes with 14+ built-in agents. Inspect AI solvers can override the default ReAct solver via `--solver` flag.

4. **New Benchmarks**: Harbor has a formal adapter system (`harbor adapters init`). Spider2-Lite (SQLite, 135 tasks) is most feasible; LongMemEval_oracle (500 questions) is moderate effort. Both need custom adapters.

5. **Execution Pipeline**: Harbor native uses async orchestration with configurable concurrency. inspect-harbor uses Inspect AI's eval loop with Docker sandbox management.

6. **Practical Architecture**: Recommended a Harbor + inspect-harbor foundation with a thin orchestration layer dispatching to either `harbor run` or `inspect eval`.

7. **Existing Patterns**: 45+ curated datasets, multiple adapter examples (BixBench, ARC-AGI-2), comprehensive CLI and Python APIs.

8. **Gaps**: Non-containerized benchmarks need creative adapters, no unified cross-framework leaderboard, inspect-harbor is very new (2 weeks old), mixed execution modes need result normalization, no built-in cost tracking.
