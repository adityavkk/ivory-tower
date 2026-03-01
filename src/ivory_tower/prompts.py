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
{custom_instructions}"""

_REFINEMENT_TEMPLATE = """\
# Cross-Pollination: Produce Your Definitive Report

You previously conducted deep research and produced a report on the topic below.
Other AI agents independently researched the SAME topic. You now have access to
your report and all peer reports.

## Your Task

Produce a **complete, standalone research report** -- your definitive version on this
topic. This is NOT a review or commentary. It is a full rewrite of your report that
incorporates the best of what you and the other agents found.

### Process

1. **Audit your own report** -- identify where you went deep, where you were shallow,
   and where you may have errors or unsupported claims
2. **Read all peer reports with healthy skepticism** -- look for:
   - Ideas, angles, and findings they covered that you missed entirely
   - Areas where they went deeper or found better sources than you
   - Claims that seem plausible but lack strong sourcing -- verify these independently
   - Contradictions between your report and theirs
   - Unique sources or evidence you didn't find
   - Reasoning or conclusions that don't follow from evidence
3. **Conduct NEW web research** to:
   - Verify peer claims before incorporating them -- do not accept anything at face value
   - Resolve contradictions between reports with additional evidence
   - Fill gaps that ALL reports share
   - Explore avenues inspired by peer reports that go beyond what anyone covered
4. **Write your complete, refined report** using the structure below

## Output Structure

Write your report with this structure:

1. **Executive Summary** -- the most important findings in 2-3 paragraphs
2. **Background & Context** -- what the reader needs to know to understand the topic
3. **Key Findings** -- organized by theme, with evidence and source citations for each claim
4. **Analysis** -- your interpretation of the findings: tradeoffs, implications, and
   recommendations where appropriate
5. **Open Questions & Gaps** -- what remains uncertain or under-explored
6. **Sources** -- comprehensive list of all URLs and references cited

## Critical Rules

- The output must be a **complete standalone report**, not a diff, review, or commentary
- Do NOT reference the other agents, the cross-pollination process, or "the peer report"
   in your output -- write as if this is your original work
- Do NOT simply copy content from peer reports -- verify claims independently and rewrite
   in your own analysis
- When peer reports contradict your findings, investigate further and present the
   evidence-backed conclusion (or both sides if genuinely unresolved)
- Incorporate the BEST insights from all sources but maintain your own analytical voice
- Your report should be substantially richer and more accurate than your original --
   if the peer reports didn't add anything, you aren't reading them critically enough

## Topic
{topic_content}

## Your Original Report
{own_report_content}

## Peer Reports
{peer_reports}"""

_SYNTHESIS_TEMPLATE = """\
# Research Synthesis

{agent_count} AI agents independently researched a topic, then each produced a refined
report after cross-pollinating findings by skeptically reviewing each other's work. You
have all their refined reports below. Each report is already a comprehensive standalone
document -- your job is to produce the definitive final version.

## Topic
{topic_content}

## Refined Reports
{all_refinement_reports}

## Your Task

Synthesize these reports into a single, comprehensive final report. Since each input
report is already a full research document, focus on:

- **Resolving contradictions** -- where reports disagree, weigh the evidence and reach a
  conclusion (or explain why the question is genuinely unresolved)
- **Combining depth** -- each agent may have gone deepest on different subtopics; merge
  the best analysis from each into a unified treatment
- **Deduplicating without losing nuance** -- remove redundancy but preserve distinct
  analytical perspectives where they add value
- **Identifying what everyone missed** -- gaps that persist across ALL reports are the
  most important open questions

Write the final report with this structure:

1. **Executive Summary** -- the most important findings across all investigations
2. **Background & Context** -- unified context that the reader needs
3. **Key Findings** -- organized by THEME (not by source agent), combining the strongest
   evidence from all reports. Go deep. This is the most important section.
4. **Areas of Consensus** -- where agents independently reached the same conclusions,
   with combined supporting evidence
5. **Areas of Disagreement** -- where agents differed, with analysis of why and which
   view is better supported by evidence
6. **Open Questions** -- what remains uncertain even after multiple independent investigations
7. **Sources** -- comprehensive, deduplicated list of all URLs and references
8. **Methodology** -- brief description of the multi-agent research process (agents used,
   phases, timing)

Be thorough and write in depth. This is the final deliverable -- it should be the
definitive reference document on this topic."""


_JUDGING_TEMPLATE = """\
# Research Report Evaluation

You are an expert research evaluator. Score the following research report
on a 1-10 scale across five dimensions. Be rigorous and critical.

## Research Topic
{topic}

## Report to Evaluate
{candidate_report}

## Scoring Rubric

Rate each dimension from 1 (poor) to 10 (excellent):

1. **Factual Accuracy** -- Are claims well-sourced and verifiable? Any errors or unsupported assertions?
2. **Depth of Analysis** -- Does the report go beyond surface-level description into genuine insight?
3. **Source Quality** -- Are sources authoritative, current, and primary? Or mostly secondary/outdated?
4. **Coverage Breadth** -- Does the report cover all important aspects of the topic? Any major gaps?
5. **Analytical Rigor** -- Is reasoning sound? Are conclusions supported by evidence? Are counterarguments considered?

## Output Format (JSON)

Respond with ONLY a JSON object (no markdown fencing, no extra text):

{{"overall_score": <float 1-10, weighted average>, "dimensions": {{"factual_accuracy": <int 1-10>, "depth_of_analysis": <int 1-10>, "source_quality": <int 1-10>, "coverage_breadth": <int 1-10>, "analytical_rigor": <int 1-10>}}, "strengths": ["<strength 1>", "<strength 2>"], "weaknesses": ["<weakness 1>", "<weakness 2>"], "suggestions": ["<specific improvement 1>", "<specific improvement 2>"], "critique": "<2-3 paragraph detailed critique explaining the scores>"}}

Be specific in your critique. Vague feedback like "could be better" is useless.
Point to specific claims, sections, or gaps. Your feedback will be used to
iteratively improve this report."""

_IMPROVEMENT_TEMPLATE = """\
# Research Report Improvement -- Round {round_num}

You previously wrote a research report. An independent AI agent has evaluated it
and provided detailed feedback. Your job is to produce a STRICTLY BETTER version.

## Research Topic
{topic}

## Your Current Report
{current_report}

## Judge's Feedback

### Overall Score: {score}/10

### Dimension Scores
- Factual Accuracy: {factual_accuracy}/10
- Depth of Analysis: {depth_of_analysis}/10
- Source Quality: {source_quality}/10
- Coverage Breadth: {coverage_breadth}/10
- Analytical Rigor: {analytical_rigor}/10

### Strengths
{strengths}

### Weaknesses
{weaknesses}

### Specific Suggestions
{suggestions}

### Detailed Critique
{critique}

## Your Task

Produce an improved version of your research report that:

1. **Addresses every weakness** the judge identified
2. **Preserves every strength** -- don't regress on what's already good
3. **Follows every specific suggestion** where feasible
4. **Conducts NEW web research** to fix flagged errors, fill coverage gaps, find stronger sources, deepen shallow analysis
5. **Does not pad or bloat** -- higher information density, not more words

Write the complete improved report as a standalone document. Do not reference
the judge or this improvement process in the output."""

_ADVERSARIAL_SYNTHESIS_TEMPLATE = """\
# Research Synthesis (Adversarial)

2 AI agents independently researched a topic, then each report was iteratively
optimized through {total_rounds} rounds of adversarial evaluation by the opposing
agent. You have both optimized reports below.

## Topic
{topic_content}

## Optimized Report A ({agent_a}, scored {score_a}/10 by {agent_b})
{optimized_report_a}

## Optimized Report B ({agent_b}, scored {score_b}/10 by {agent_a})
{optimized_report_b}

## Your Task

Synthesize both optimized reports into a comprehensive final report:

1. **Executive Summary** -- most important findings across both investigations
2. **Key Findings** -- organized by THEME, combining strongest evidence from both
3. **Areas of Consensus** -- where both agents converged after optimization
4. **Areas of Disagreement** -- where agents still differ, with analysis of which view is better supported
5. **Novel Insights** -- unique findings from the adversarial optimization process
6. **Open Questions** -- what remains uncertain even after iterative refinement
7. **Sources** -- comprehensive, deduplicated list of all URLs and references
8. **Methodology** -- brief description of the adversarial optimization process

Be thorough. This is the final deliverable."""


def _format_list(items: list[str]) -> str:
    """Format a list of strings as markdown bullet points."""
    if not items:
        return "- (none provided)"
    return "\n".join(f"- {item}" for item in items)


def build_judging_prompt(topic: str, candidate_report: str) -> str:
    """Build the adversarial judging prompt."""
    return _JUDGING_TEMPLATE.format(topic=topic, candidate_report=candidate_report)


def build_improvement_prompt(
    topic: str,
    current_report: str,
    judge_feedback: dict,
    round_num: int,
) -> str:
    """Build the adversarial improvement prompt."""
    dims = judge_feedback.get("dimensions", {})
    return _IMPROVEMENT_TEMPLATE.format(
        round_num=round_num,
        topic=topic,
        current_report=current_report,
        score=judge_feedback.get("score", 0),
        factual_accuracy=dims.get("factual_accuracy", 0),
        depth_of_analysis=dims.get("depth_of_analysis", 0),
        source_quality=dims.get("source_quality", 0),
        coverage_breadth=dims.get("coverage_breadth", 0),
        analytical_rigor=dims.get("analytical_rigor", 0),
        strengths=_format_list(judge_feedback.get("strengths", [])),
        weaknesses=_format_list(judge_feedback.get("weaknesses", [])),
        suggestions=_format_list(judge_feedback.get("suggestions", [])),
        critique=judge_feedback.get("critique", "(no critique provided)"),
    )


def build_adversarial_synthesis_prompt(
    topic: str,
    agent_a: str,
    optimized_report_a: str,
    score_a: float,
    agent_b: str,
    optimized_report_b: str,
    score_b: float,
    total_rounds: int,
) -> str:
    """Build the adversarial synthesis prompt."""
    return _ADVERSARIAL_SYNTHESIS_TEMPLATE.format(
        total_rounds=total_rounds,
        topic_content=topic,
        agent_a=agent_a,
        optimized_report_a=optimized_report_a,
        score_a=score_a,
        agent_b=agent_b,
        optimized_report_b=optimized_report_b,
        score_b=score_b,
    )


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
    peer_reports: str,
) -> str:
    """Build a Phase 2 cross-pollination prompt for one agent reviewing all peers."""
    return _REFINEMENT_TEMPLATE.format(
        topic_content=topic,
        own_report_content=own_report,
        peer_reports=peer_reports,
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
