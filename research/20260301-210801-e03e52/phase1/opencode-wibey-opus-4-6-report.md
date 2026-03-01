This is a deep research task about Harbor and inspect-harbor for building a general-purpose eval runner. Let me plan this out and then conduct thorough research.
Let me start by researching Harbor's GitHub repo, inspect-harbor, and related documentation in parallel.
Good, I have a good overview of Harbor. Now let me dig deeper into the eval-related components. Let me fetch more specific pages in parallel.
Now let me research Inspect AI and the concept of "inspect-harbor", plus the benchmarks Spider2 and LongMemEval.
I now have comprehensive research data from all sources. Let me update the todos and write the report.
Now let me determine the output path and write the comprehensive report.
The research report has been written to `/Users/auk000v/dev/tools/ivory-tower/research/20260301-210801-e03e52/phase1/20260301-210801-e03e52/report.md`.

Here's a summary of the key findings:

**Critical discovery**: The `inspect-harbor` package bridges Inspect AI with the **Harbor Framework** (harborframework.com) -- a completely separate project from `av/harbor` (the LLM stack tool). There is no existing integration between av/harbor and Inspect AI.

**Recommended architecture**: Use **Inspect AI** as the central eval orchestrator (Tasks/Solvers/Scorers/Datasets), **Harbor (av/harbor)** as the infrastructure layer for managing LLM backends, and custom engineering to bridge them. Key custom work needed:
1. An Inspect AI ModelAPI extension for auto-discovering Harbor backends
2. Agentic solvers with tool-use for benchmarks like Spider2
3. Benchmark-specific scorers (CSV matching for Spider2, LLM-as-judge for LongMemEval)
4. Docker network coordination between Harbor's compose stack and Inspect AI's sandboxes

**Easiest starting points**: Spider2-DBT (already in inspect-harbor, 68 local tasks) and LongMemEval-oracle (self-contained JSON, fits in 128K context).

The report covers all 8 requested topics across ~4,500 words with 17 cited sources.
