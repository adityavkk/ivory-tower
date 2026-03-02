# Research Report Evaluation

You are an expert research evaluator. Your job is to evaluate the report below
and then provide your scores as structured JSON.

## Research Topic
Compare WebSocket vs Server-Sent Events (SSE) for real-time web applications. Cover: protocol differences, browser support, scalability trade-offs, and when to choose each.

## Report to Evaluate
I'll read the file you specified.
I'll now create a comprehensive plan to improve this research report based on the judge's feedback. The main priority is fixing the **Source Quality** dimension (6/10), while preserving strengths and addressing all weaknesses.

Let me start by setting up a task plan:
Now I'll conduct focused web research to verify and strengthen the sources. Let me start with the key factual claims that were flagged:
Now let me mark the first research todo as in_progress and continue searching for additional sources:
Good. Let me fetch additional sources on Shopify and Slack case studies:
Excellent. Now I have strong source material to work with. Let me mark this task as complete and move to the next step. Let me search for more info on HTTP/2, HTTP/3, and edge computing impacts:
Now let me write the improved report. Based on my research and the judge's feedback, I'll create a comprehensive, enhanced version that:

1. **Fixes source quality issues** with inline citations and precise claims
2. **Adds a comparison matrix** for workload profiles
3. **Refines scalability analysis** with better precision on connection state
4. **Includes deployment/intermediaries section** on network behavior
5. **Nuances SSE statelessness** claims
6. **Adds operational risks section** on backpressure, HTTP/2/3, reconnection

Let me write this comprehensive improved report:


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