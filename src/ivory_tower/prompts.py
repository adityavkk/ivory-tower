"""Prompt templates for the three research phases."""

_RESEARCH_TEMPLATE = """\
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
{custom_instructions}"""

_REFINEMENT_TEMPLATE = """\
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
{peer_report_content}"""

_SYNTHESIS_TEMPLATE = """\
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

Be thorough. This is the final deliverable."""


def build_research_prompt(
    topic: str,
    instructions: str | None = None,
    raw: bool = False,
) -> str:
    """Build the Phase 1 research prompt."""
    if raw:
        return topic

    custom = ""
    if instructions:
        custom = f"\n## Additional Instructions\n{instructions}"

    return _RESEARCH_TEMPLATE.format(
        topic_content=topic,
        custom_instructions=custom,
    )


def build_refinement_prompt(
    topic: str,
    own_report: str,
    peer_report: str,
    peer_agent_name: str,
) -> str:
    """Build a Phase 2 cross-pollination prompt for one agent-peer pair."""
    return _REFINEMENT_TEMPLATE.format(
        topic_content=topic,
        own_report_content=own_report,
        peer_report_content=peer_report,
        peer_agent_name=peer_agent_name,
    )


def build_synthesis_prompt(
    topic: str,
    agent_count: int,
    all_refinement_reports: str,
) -> str:
    """Build the Phase 3 synthesis prompt."""
    return _SYNTHESIS_TEMPLATE.format(
        topic_content=topic,
        agent_count=agent_count,
        all_refinement_reports=all_refinement_reports,
    )
