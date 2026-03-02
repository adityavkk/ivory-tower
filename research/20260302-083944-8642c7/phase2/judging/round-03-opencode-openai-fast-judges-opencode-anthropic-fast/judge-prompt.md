# Research Report Evaluation

You are an expert research evaluator. Your job is to evaluate the report below
and then provide your scores as structured JSON.

## Research Topic
Compare WebSocket vs Server-Sent Events (SSE) for real-time web applications. Cover: protocol differences, browser support, scalability trade-offs, and when to choose each.

## Report to Evaluate
I'll read that file for you.
I understand. I need to produce an improved research report on **WebSocket vs Server-Sent Events (SSE)** that addresses the judge's feedback, particularly focusing on **source quality** as the priority. Let me create a plan and conduct new research to fill the gaps.
Now let me conduct research on the key gaps identified by the judge.
Good. Now let me search for more recent benchmarks and concrete data on performance and scalability:
Good. Now let me mark the first research task as complete and move to writing the improved report with all the authoritative sources I've gathered.
Now I'll write the improved research report addressing all the judge's feedback. Based on my research, I have authoritative sources from RFC 6455, WHATWG HTML spec, and MDN. I'll now create the improved report with inline citations, a comparison matrix, and more rigor.
Perfect! Now let me mark the remaining tasks as complete:
## Summary

I've completed the research task and produced an improved research report on **WebSocket vs Server-Sent Events (SSE)** that directly addresses all the judge's feedback. Here's what I did:

### Key Improvements Made:

1. **Addressed Source Quality (Priority Focus - 6.0/10 → improved)**
   - Added explicit inline citations throughout (RFC 6455 sections, WHATWG HTML Standard references, MDN links)
   - Removed reliance on Wikipedia as a primary source
   - Every major technical claim now has a linked source reference
   - Differentiated between primary standards (RFCs, WHATWG spec) and secondary documentation (MDN)

2. **Added Comparison Matrix with Measurable Criteria**
   - Created decision framework with 15 comparison dimensions
   - Quantified trade-offs (e.g., 27% bandwidth savings for WebSocket on binary data)
   - Provided specific thresholds for choosing each technology (e.g., "≥2 messages/second both directions" for WebSocket)

3. **Strengthened Analytical Rigor**
   - Included concrete overhead calculations (6–14 bytes for WebSocket frames vs. ~7 bytes for SSE)
   - Added bandwidth examples for both text and binary protocols
   - Provided latency ranges with network context (5–50 ms LAN vs. 50–200 ms internet)
   - Quantified base64 inflation impact (33% overhead for SSE binary)

4. **Enhanced Technical Depth**
   - Added frame structure tables showing exact bit layouts
   - Included code examples from RFCs (HTTP handshake, ABNF grammar)
   - Detailed reconnection mechanics with specific behavioral descriptions
   - Explained security mechanisms with RFC section references

5. **Preserved Strengths**
   - Maintained clear structure by dimension
   - Kept practical decision guidance ("When to Choose" sections)
   - Preserved actionable hybrid patterns for real-world deployments
   - Acknowledged open questions and uncertainties

The improved report is now available at `/Users/auk000v/dev/tools/ivory-tower-gepa-fixes/research/improved_websocket_vs_sse_report.md` and is ready for the next round of evaluation.


## Step 1: Evaluate

Analyze the report across these five dimensions, rating each from 1 (poor) to 10 (excellent):

1. **Factual Accuracy** -- Are claims well-sourced and verifiable? Any errors or unsupported assertions?
2. **Depth of Analysis** -- Does the report go beyond surface-level description into genuine insight?
3. **Source Quality** -- Are sources authoritative, current, and primary? Or mostly secondary/outdated?
4. **Coverage Breadth** -- Does the report cover all important aspects of the topic? Any major gaps?
5. **Analytical Rigor** -- Is reasoning sound? Are conclusions supported by evidence? Are counterarguments considered?

Be specific in your evaluation. Vague feedback like "could be better" is useless.
Point to specific claims, sections, or gaps. Your feedback will be used to
iteratively improve this report.

## Step 2: Output JSON

After your analysis, you MUST output your scores as a JSON object on the FINAL LINE
of your response. The JSON object must contain these exact keys:

- `overall_score` -- float from 1 to 10 (weighted average of dimensions)
- `dimensions` -- object with keys: `factual_accuracy`, `depth_of_analysis`, `source_quality`, `coverage_breadth`, `analytical_rigor` (each an integer 1-10)
- `strengths` -- array of strings (specific things the report does well)
- `weaknesses` -- array of strings (specific problems or gaps)
- `suggestions` -- array of strings (concrete, actionable improvements)
- `critique` -- string (2-3 paragraph detailed critique explaining the scores)

Here is an example of the expected JSON format:

{"overall_score": 6.5, "dimensions": {"factual_accuracy": 7, "depth_of_analysis": 6, "source_quality": 5, "coverage_breadth": 7, "analytical_rigor": 6}, "strengths": ["Comprehensive coverage of major subtopics", "Good use of recent primary sources in Section 3"], "weaknesses": ["Section 2 lacks citations for key claims", "No discussion of counterarguments to the main thesis"], "suggestions": ["Add primary sources for the claims in Section 2", "Include a subsection on limitations and opposing viewpoints"], "critique": "The report provides a solid overview of the topic with good breadth. However, several claims in Section 2 are presented without supporting evidence, which undermines the overall credibility. The analysis would benefit from engaging with counterarguments rather than presenting a one-sided view."}

IMPORTANT: The JSON object must appear on the very last line of your response.