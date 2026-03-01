# Deep Research Task

## Topic
How can I use Harbor (https://github.com/av/harbor) and inspect-harbor (the Inspect AI integration/bridge for Harbor) to build a general-purpose eval runner that can run different agent solvers against different benchmarks like Spider2, LongMemEval, and others? Specifically research: (1) Harbor's architecture - how it orchestrates agent backends, services, and eval tasks; (2) inspect-harbor's role as the bridge between Inspect AI's eval framework and Harbor's service management; (3) how to define and register new agent solvers (e.g. wrapping a custom agent as a Harbor-compatible solver); (4) how to define and register new benchmarks/datasets (e.g. integrating Spider2 and LongMemEval task suites); (5) the eval execution pipeline - how Harbor manages the lifecycle of running a solver against a benchmark; (6) practical architecture for a general-purpose eval runner that can mix-and-match solvers and benchmarks; (7) existing examples and patterns from Harbor's built-in eval support; (8) gaps, limitations, and areas where custom engineering would be needed.

## Methodology
- Use web search extensively to find current, authoritative sources
- Prefer primary sources (papers, official docs, original announcements) over secondary commentary
- Check publication dates -- prefer sources from the last 2 years where relevant
- When making claims, note your source
- If you find contradictory information, present both sides with sources

## Output Requirements

Write a comprehensive, standalone research report structured as follows:

1. **Executive Summary** -- the most important findings in 2-3 paragraphs
2. **Background & Context** -- what the reader needs to know to understand the topic
3. **Key Findings** -- organized by theme, with evidence and source citations for each claim
4. **Analysis** -- your interpretation of the findings: tradeoffs, implications, and recommendations where appropriate
5. **Open Questions & Gaps** -- areas where you couldn't find solid information or where evidence is contradictory
6. **Sources** -- comprehensive list of all URLs and references cited

Write in depth. Each section should be substantive, not just bullet points. Support claims
with evidence and cite sources inline. This report should be useful as a standalone
reference document on the topic.
