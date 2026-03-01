# Research Report Evaluation

You are an expert research evaluator. Score the following research report
on a 1-10 scale across five dimensions. Be rigorous and critical.

## Research Topic
Compare WebSocket vs Server-Sent Events (SSE) for real-time web applications. Cover: protocol differences, browser support, scalability trade-offs, and when to choose each.

## Report to Evaluate
## Goal

- Deliver a much better version of a prior research report comparing WebSocket vs Server-Sent Events (SSE) for real-time web apps.
- The required report format is fixed:  
  1) Executive Summary (2–3 dense paragraphs)  
  2) Background & Context  
  3) Key Findings (theme-based, evidence-backed)  
  4) Analysis (tradeoffs, implications, recommendations)  
  5) Open Questions & Gaps  
  6) Sources (URL list, inline citations in body)

- User’s prompt explicitly asked for strict quality improvements: use primary sources, include publication dates, compare conflicting evidence, cite inline for each claim, preserve strengths, and address prior gaps/failures.

## Instructions

- Must follow `/Users/auk000v/dev/tools/ivory-tower/research/20260301-212129-06e860/phase2/opencode-openai-fast-improve-round-03/opencode-openai-fast-improve-round-03/prompt.md` instructions.
- Follow “research + synthesis” workflow (no code changes unless asked), and avoid introducing web/SEO-only content; prioritize protocol behavior, browser support, scaling, and deployment implications.
- Explicitly requested: do **not** mention judge/feedback process in final deliverable.
- No files were modified before handoff.
- Important constraint from the user’s previous report task: address all listed weaknesses, preserve prior strengths, improve with new sources where needed, and do not produce shallow/bloated content.

## Discoveries

- The source file `prompt.md` confirms this is in phase-2 iterative refinement, with very poor prior score (0/10) and a “do new research” requirement.
- Baseline protocol source pulls:
  - MDN:
    - `WebSocket` page: bidirectional API, events + buffering semantics, no built-in backpressure, browser support baseline, last modified Sep 25, 2024.
    - `EventSource` page: one-way, text/event-stream, browser-supported, includes warning for HTTP/1.1: practical per-origin/per-browser connection limit of 6 in many browsers, HTTP 204 to stop reconnect, MDN last modified Mar 13, 2025.
    - `Server-sent events` page: overview + links, confirms one-way stream model.
    - `EventSource.readyState` shows states CONNECTING/OPEN/CLOSED with codes 0/1/2.
    - `WebSocketStream` page: experimental, stream-based, explicitly marked experimental and not fully standardized.
- Standards:
  - WHATWG HTML SSE section (`server-sent-events`): detailed event parsing (`text/event-stream`), reconnection model, `Last-Event-ID`, UTF-8 event stream decoding.
  - WHATWG WebSocket spec (living): constructor semantics, protocol handshakes, binaryType, bufferedAmount behavior, backpressure caveats, close/error semantics, readyState lifecycle, API details.
  - RFC 6455 (WebSocket Protocol): full handshake and framing model, Upgrade semantics, masking, close semantics, multiplexing mention, and design rationale.
  - RFC 8441: WebSockets over HTTP/2 via extended CONNECT (`:protocol` websocket) and `SETTINGS_ENABLE_CONNECT_PROTOCOL`.
  - RFC 7230: HTTP/1.1 message/connection semantics and Upgrade framing context.
- Browser support snapshots:
  - caniuse `websockets`: global usage ~96.73% (Jan 2026 snapshot), modern partiality details.
  - caniuse `eventsource`: global usage ~96.44% (Jan 2026 snapshot), support caveats and legacy engine notes.
- Operational/deployment inputs:
  - NGINX websocket proxying docs: must pass `Upgrade` and `Connection` hop-by-hop headers explicitly, `proxy_http_version 1.1`, typical config snippet with `$http_upgrade`/map.
  - Node.js HTTP docs: `upgrade` event for handling 101 handshakes and `connect` event for tunneling; useful for server-side architecture notes.
  - AWS API Gateway docs:
    - WebSocket APIs are bidirectional and suitable for push without polling (general overview).
    - Quotas captured for account-level RPS and management API throttles; useful for scalability trade-offs and managed-service constraints.

- Some `webfetch` outputs were truncated (notably full RFC/HTML pages and some large Node.js/AWS content). Tool noted cached truncated outputs in:
  - `/Users/auk000v/.local/share/opencode/tool-output/` (various `tool_cab4a...` files) for later line-level extraction if needed.

## Accomplished

- Read and interpreted the governing prompt/instructions from the provided file.
- Executed extensive web research across primary protocol/docs and compatibility sources:
  - MDN WebSocket/EventSource/EventSource ready state/WebSocketStream
  - WHATWG HTML SSE and WebSockets specs
  - RFC 6455, RFC 8441, RFC 7230
  - caniuse WebSockets and SSE support
  - nginx websocket proxying docs
  - Node.js HTTP module docs (`upgrade`/`connect` behavior)
  - AWS API Gateway WebSocket/limits pages
- Consolidated what was previously known in prompt’s “Discoveries” plus additional confirmations from live fetches.
- No local file creation/editing yet; no repository state changes.
- Final improved report has **not** been written yet.
- Remaining work:
  - finish the report synthesis and produce the final stand-alone comparative document in required structure.
  - explicitly resolve practical trade-offs with citations, include open questions with evidence-backed gaps.
  - incorporate conflicting evidence side-by-side (especially HTTP/1.1 connection limits vs practical mitigations, stream persistence/reconnection behavior, proxy/L7 constraints).

## Relevant files / directories

- Read:
  - ` /Users/auk000v/dev/tools/ivory-tower/research/20260301-212129-06e860/phase2/opencode-openai-fast-improve-round-03/opencode-openai-fast-improve-round-03/prompt.md `
  - (Prompt also references earlier phase prompt and local context under `.../phase1/...`)

- No files edited/created.

- External references used (inline source corpus for continuation):
  - `https://developer.mozilla.org/en-US/docs/Web/API/WebSocket`
  - `https://developer.mozilla.org/en-US/docs/Web/API/EventSource`
  - `https://developer.mozilla.org/en-US/docs/Web/API/EventSource/readyState`
  - `https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events`
  - `https://developer.mozilla.org/en-US/docs/Web/API/WebSocketStream`
  - `https://www.rfc-editor.org/rfc/rfc6455`
  - `https://www.rfc-editor.org/rfc/rfc8441`
  - `https://www.rfc-editor.org/rfc/rfc7230`
  - `https://html.spec.whatwg.org/multipage/web-sockets.html`
  - `https://html.spec.whatwg.org/multipage/server-sent-events.html`
  - `https://caniuse.com/websockets`
  - `https://caniuse.com/eventsource`
  - `https://nginx.org/en/docs/http/websocket.html`
  - `https://nodejs.org/api/http.html#http_event_upgrade`
  - `https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api.html`
  - `https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html`


## Scoring Rubric

Rate each dimension from 1 (poor) to 10 (excellent):

1. **Factual Accuracy** -- Are claims well-sourced and verifiable? Any errors or unsupported assertions?
2. **Depth of Analysis** -- Does the report go beyond surface-level description into genuine insight?
3. **Source Quality** -- Are sources authoritative, current, and primary? Or mostly secondary/outdated?
4. **Coverage Breadth** -- Does the report cover all important aspects of the topic? Any major gaps?
5. **Analytical Rigor** -- Is reasoning sound? Are conclusions supported by evidence? Are counterarguments considered?

## Output Format (JSON)

Respond with ONLY a JSON object (no markdown fencing, no extra text):

{"overall_score": <float 1-10, weighted average>, "dimensions": {"factual_accuracy": <int 1-10>, "depth_of_analysis": <int 1-10>, "source_quality": <int 1-10>, "coverage_breadth": <int 1-10>, "analytical_rigor": <int 1-10>}, "strengths": ["<strength 1>", "<strength 2>"], "weaknesses": ["<weakness 1>", "<weakness 2>"], "suggestions": ["<specific improvement 1>", "<specific improvement 2>"], "critique": "<2-3 paragraph detailed critique explaining the scores>"}

Be specific in your critique. Vague feedback like "could be better" is useless.
Point to specific claims, sections, or gaps. Your feedback will be used to
iteratively improve this report.