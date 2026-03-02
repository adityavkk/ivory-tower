---
title: "ivory-tower"
author: "human:aditya"
version: 1
created: 2026-03-01
---

# Ivory Tower

## WANT

- A Python CLI (`ivory`) that orchestrates multi-agent deep research through three phases: independent research, skeptical cross-pollination, and synthesis.
- Delegates all agent execution to `counselors` CLI -- ivory is an orchestrator, not an agent runtime.
- **Phase 1 -- Independent Research**: N agents research a topic in parallel via `counselors run`. Each produces a standalone research report.
- **Phase 2 -- Cross-Pollination**: For each agent, spawn concurrent sessions -- one per peer report. Agent A gets report B in one session, report C in another, running in parallel. Each session skeptically verifies peer claims via new web research. Outputs are per-peer refinement docs (not merged). All refinements feed directly into synthesis.
- **Phase 3 -- Synthesis**: A single user-selected agent reads all Phase 2 refinements and produces a final report with fixed structure: executive summary, key findings, areas of consensus, areas of disagreement, novel insights, open questions, sources, methodology.
- Same agent set for Phase 1 + 2; user picks a single synthesizer for Phase 3.
- Topic input: positional arg, `--file <path>` (markdown file), or stdin pipe.
- Auto-generated research prompt wraps topic with methodology guidance (use web search, prefer primary sources, check recency). `--raw` sends topic as-is. `--instructions` appends custom instructions to auto-generated prompt.
- Default output: `./research/<YYYYMMDD-HHMMSS-hex6>/` with per-phase reports and final-report.md. Override with `--output-dir`.
- `--dry-run`: show execution plan (agents, phases, prompts) without running.
- Resume interrupted runs: detect completed phases, restart from last incomplete phase.
- Manifest (`manifest.json`): track timing per phase, per agent, total duration, agent names, phase status.
- Clean progress output by default (phase transitions, agent status). `--verbose` for streaming logs.

## DON'T

- Do NOT implement agent execution directly. All agent dispatch goes through `counselors run`.
- Do NOT merge per-peer refinements in Phase 2. Keep them separate; feed all to synthesis.
- Do NOT require a config file. Everything via CLI flags. No TOML/YAML profiles.
- Do NOT support output formats beyond markdown for v1. No PDF, HTML.
- Do NOT implement agent timeouts or iteration limits. Delegate to counselors.
- Do NOT build a TUI or interactive mode. Batch CLI only.
- Do NOT auto-select agents. User must specify which agents to use (or all).

## LIKE

- [hamelsmu/research-council](https://github.com/hamelsmu/research-council) -- three-phase workflow (research, cross-pollination, synthesis), skeptical refinement prompts, output structure.
- [counselors CLI](https://github.com/anomalyco/counselors) -- parallel agent dispatch, `--tools` flag, `--json` structured output, file-based prompt passing.
- [clig.dev](https://clig.dev/) -- CLI design principles: human-readable by default, machine-readable with `--json`, composable, helpful error messages.
- [typer](https://typer.tiangolo.com/) -- CLI framework with auto-generated help.

## FOR

- **Who**: Developers and researchers running multi-agent research from terminal.
- **Environment**: macOS, Python 3.12+, uv for packaging, `counselors` CLI installed globally via bun.
- **Domain**: Deep research on technical topics, architecture decisions, technology evaluations.
- **Tech stack**: Python, typer, uv, shelling out to `counselors` CLI.

## ENSURE

- `ivory --help` prints usage; exit 0.
- `ivory research "topic" --agents claude-opus,codex-5.3-xhigh --synthesizer claude-opus` runs full 3-phase pipeline and produces `final-report.md`.
- `ivory research --file topic.md --agents claude-opus,codex-5.3-xhigh --synthesizer claude-opus` reads topic from file.
- `echo "topic" | ivory research --agents claude-opus,codex-5.3-xhigh --synthesizer claude-opus` reads topic from stdin.
- `--dry-run` prints plan (agents, phases, prompt previews) and exits without calling counselors.
- Phase 1 output: one `<agent>-report.md` per agent in run directory.
- Phase 2 output: `<agent>-cross-<peer>.md` files. For 3 agents (A,B,C): A gets 2 files (cross-B, cross-C), B gets 2 (cross-A, cross-C), C gets 2 (cross-A, cross-B). Total = N*(N-1) files.
- Phase 2 per-peer sessions run concurrently (agent A reviewing B runs at same time as agent A reviewing C).
- Phase 3 output: `final-report.md` with all 8 sections.
- `manifest.json` includes: run_id, topic, agents, synthesizer, phase statuses (pending/running/complete/failed), per-phase timing, per-agent timing, total duration.
- Resume: if run directory exists with completed Phase 1, `ivory resume <run-dir>` skips Phase 1 and starts Phase 2.
- Resume: if Phase 2 also complete, jumps straight to Phase 3.
- `--verbose` streams agent stdout to terminal.
- Non-zero exit on any phase failure; partial results preserved in run directory.
- Error if `counselors` not found on PATH.
- Error if specified agent not in `counselors ls` output.
- `--raw` skips prompt wrapping; sends topic/file content directly to counselors.
- `--instructions "focus on cost"` appends text to auto-generated prompt.

## TRUST

- [autonomous] Generate run IDs (timestamp + hex).
- [autonomous] Construct phase prompts from templates + topic.
- [autonomous] Create output directory structure.
- [autonomous] Parse counselors JSON output and extract report paths.
- [autonomous] Determine resume point from manifest.json state.
- [autonomous] Formatting and structure of progress output.
- [ask] Adding new phases or changing the 3-phase workflow.
- [ask] Changing the synthesis report structure (8 sections).
- [ask] Adding config file support or persistent settings.
- [ask] Adding new output formats beyond markdown.
- [ask] Modifying the refinement/cross-pollination prompt instructions.

---

# Architecture

## CLI Interface

```
ivory research <topic>
    --agents, -a       Comma-separated agent IDs for Phase 1+2 (required)
    --synthesizer, -s  Agent ID for Phase 3 synthesis (required)
    --file, -f         Read topic from markdown file
    --instructions, -i Append instructions to auto-generated prompt
    --raw              Send topic as-is (no prompt wrapping)
    --output-dir, -o   Override default output directory
    --verbose, -v      Stream agent logs to terminal
    --dry-run          Show plan without executing
    --json             Output manifest as JSON on completion

ivory resume <run-dir>
    --verbose, -v      Stream agent logs to terminal

ivory status <run-dir>
    Print manifest status for a run

ivory list
    List all runs in ./research/ with status summary
```

## Output Structure

```
./research/20260301-143000-a1b2c3/
    manifest.json
    topic.md                        # Saved copy of input topic
    phase1/
        claude-opus-report.md
        codex-5.3-xhigh-report.md
        amp-deep-report.md
    phase2/
        claude-opus-cross-codex-5.3-xhigh.md
        claude-opus-cross-amp-deep.md
        codex-5.3-xhigh-cross-claude-opus.md
        codex-5.3-xhigh-cross-amp-deep.md
        amp-deep-cross-claude-opus.md
        amp-deep-cross-codex-5.3-xhigh.md
    phase3/
        final-report.md
    logs/
        (verbose logs if --verbose)
```

## Phase Execution Detail

### Phase 1: Independent Research

For each agent, call:
```bash
counselors run -f <prompt-file> --tools <agent> --json -o <run-dir>/phase1/
```

All agents run in parallel (single `counselors run` with `--tools agent1,agent2,...`).

**Auto-generated prompt template** (written to `<run-dir>/research-prompt.md`):

```markdown
# Deep Research Task

## Topic
{topic_content}

## Methodology
- Use web search extensively to find current, authoritative sources
- Prefer primary sources (papers, official docs, original announcements) over secondary commentary
- Check publication dates -- prefer sources from the last 2 years where relevant
- When making claims, note your source
- If you find contradictory information, present both sides with sources

## Output Requirements
- Write a comprehensive research report
- Include a Sources section with URLs at the end
- Note gaps in your research -- areas where you couldn't find solid information
{custom_instructions}
```

### Phase 2: Cross-Pollination

For N agents, generate N*(N-1) refinement sessions. For each agent A reviewing peer B's report:

```bash
counselors run -f <refinement-prompt-A-B> --tools <agent-A> --json -o <run-dir>/phase2/
```

All N*(N-1) sessions run concurrently via parallel counselors invocations.

**Refinement prompt template** (per agent-peer pair):

```markdown
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
{topic_content}

## Your Original Report
{own_report_content}

## Peer Report ({peer_agent_name})
{peer_report_content}
```

### Phase 3: Synthesis

Single agent reads all Phase 2 refinements:

```bash
counselors run -f <synthesis-prompt> --tools <synthesizer> --json -o <run-dir>/phase3/
```

**Synthesis prompt template**:

```markdown
# Research Synthesis

{agent_count} AI agents independently researched a topic, then cross-pollinated
findings by skeptically reviewing each other's work. You have all their refinement
reports below.

## Topic
{topic_content}

## Refinement Reports
{all_refinement_reports}

## Your Task

Synthesize everything into a comprehensive final report with this structure:

1. **Executive Summary** -- the most important findings across all investigations
2. **Key Findings** -- organized by THEME (not by source agent), combining the strongest evidence
3. **Areas of Consensus** -- where agents agree, with combined supporting evidence
4. **Areas of Disagreement** -- where agents differed, with analysis of why and which view is better supported
5. **Novel Insights** -- unique findings that emerged from the cross-pollination refinement round
6. **Open Questions** -- what remains uncertain even after independent investigations
7. **Sources** -- comprehensive, deduplicated list of all URLs and references
8. **Methodology** -- brief description of the multi-agent research process (agents used, phases, timing)

Be thorough. This is the final deliverable.
```

## Manifest Schema

```json
{
  "run_id": "20260301-143000-a1b2c3",
  "topic": "...",
  "agents": ["claude-opus", "codex-5.3-xhigh", "amp-deep"],
  "synthesizer": "claude-opus",
  "flags": {
    "raw": false,
    "instructions": null,
    "verbose": false
  },
  "phases": {
    "research": {
      "status": "complete",
      "started_at": "2026-03-01T14:30:00Z",
      "completed_at": "2026-03-01T14:35:12Z",
      "duration_seconds": 312,
      "agents": {
        "claude-opus": {"status": "complete", "duration_seconds": 280, "output": "phase1/claude-opus-report.md"},
        "codex-5.3-xhigh": {"status": "complete", "duration_seconds": 312, "output": "phase1/codex-5.3-xhigh-report.md"}
      }
    },
    "cross_pollination": {
      "status": "complete",
      "started_at": "...",
      "completed_at": "...",
      "duration_seconds": 0,
      "sessions": {
        "claude-opus-cross-codex-5.3-xhigh": {"status": "complete", "duration_seconds": 0, "output": "phase2/..."}
      }
    },
    "synthesis": {
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "duration_seconds": null,
      "agent": "claude-opus",
      "output": "phase3/final-report.md"
    }
  },
  "total_duration_seconds": null
}
```

## Error Handling

- `counselors` not on PATH: print install instructions, exit 1.
- Agent ID not in `counselors ls`: print available agents, exit 1.
- Phase failure: mark failed in manifest, preserve partial results, exit non-zero.
- Resume with no manifest: error with message.
- Empty topic (no arg, no file, no stdin): error with usage hint.
- Stdin detection: check `sys.stdin.isatty()` to distinguish pipe from no input.

## Dependencies

- Python 3.12+
- typer (CLI framework)
- rich (progress display)
- counselors (external CLI, must be on PATH)
