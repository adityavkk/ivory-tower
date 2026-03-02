## Goal

- Continue from the user’s instruction to generate a **strictly better, standalone research report** on **WebSocket vs Server-Sent Events (SSE)** for real-time web applications.
- The report must:
  - Preserve strengths of the current version,
  - Address all judge-identified weaknesses,
  - Implement specific suggestions (ops perspective, cost, ecosystem, citations, etc.),
  - Use new web research to improve evidence quality,
  - Increase analytical depth without unnecessary bloat.

## Instructions

- Source of truth is the user’s task file at:
  - `prompt.md` which contains:
    - Topic and scope,
    - Existing report draft,
    - Detailed judge feedback and scoring breakdown,
    - Required rewrite requirements.
- Required rewrite constraints from that file:
  - Compare protocol design, browser support, scalability, and decision criteria.
  - Preserve existing strengths and improve weak areas before any new additions.
  - Follow specific suggestions:
    - Add operational implications (monitoring, debugging, error recovery),
    - Include cost comparison across scale bands,
    - Expand client library ecosystem across languages/frameworks,
    - Improve citations with full URLs and publication dates,
    - Add hybrid and alternative patterns discussion (e.g., SSE + WebSocket fallback, gRPC-web),
  - Conduct additional web research (already started) and avoid padding/text bloat.
- No files have been edited yet; next agent should create the improved report document from scratch (likely overwrite/replace in same location used by user workflow or another agreed path).
- Developer instruction in this session: use non-destructive behavior and no revert of unrelated work; maintain ASCII by default.

## Discoveries

- The existing report in `prompt.md` is very comprehensive on protocol mechanics and case studies but had explicit gaps:
  - Weak operational/DevOps lens,
  - Weak explicit cost/scale modeling,
  - Unclear citations on some Ably entries (missing direct URLs + publication context),
  - Limited client library ecosystem comparison.
- Relevant webfetches performed (research collected):
  - `https://www.rfc-editor.org/rfc/rfc6455` (WebSocket RFC) — includes protocol architecture, handshake, framing, close handshake, security model, extensibility, and key design principles.
  - `https://html.spec.whatwg.org/multipage/server-sent-events.html` (WHATWG SSE) — authoritative details on `EventSource`, reconnection, `Last-Event-ID`, stream parsing, event interpretation, and diagnostics guidance.
  - MDN WebSocket page (`https://developer.mozilla.org/en-US/docs/Web/API/WebSocket`) and MDN SSE page (`https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events`) for practical API summaries and baseline support context.
  - Ably pages:
    - WebSockets overview (`https://www.ably.io/topic/websockets`)
    - SSE overview (`https://www.ably.io/topic/server-sent-events`)
    - Challenge of scaling WebSockets (`https://www.ably.io/topic/the-challenge-of-scaling-websockets`)
  - Shopify real-time SSE migration case study:
    - `https://shopify.engineering/server-sent-events-data-streaming`
  - Slack WebSocket scalability case study:
    - `https://slack.engineering/migrating-millions-of-concurrent-websockets-to-envoy/`
  - LinkedIn architecture page requested via URL redirected to an infra listing page with broader engineering context (not the exact desired article); useful for future if needed but not yet a precise case study source.
- Additional ecosystem/library research already collected:
  - Socket.IO client API (`https://socket.io/docs/v4/client-api/`) for reconnection/event/transport abstractions.
  - Python websockets docs (`https://websockets.readthedocs.io/`).
  - Go WebSocket implementations:
    - `https://github.com/coder/websocket`
    - `https://github.com/gorilla/websocket`
  - SSE ecosystem/clients:
    - `https://github.com/rexxars/eventsource-parser`
    - `https://github.com/Yaffle/EventSource`
    - `https://github.com/Azure/fetch-event-source`
  - `aiohttp` docs confirm built-in client websocket support and operational timeout model (`https://docs.aiohttp.org/.../client_quickstart.html#websocket-client`).
- One webfetch failed/404 and should be retried if needed:
  - `https://learn.microsoft.com/en-us/aspnet/core/signalr/diagnostic-metrics` (currently returning 404 in this session).

## Accomplished

- Located and read the authoritative task prompt and current report content from `/Users/auk000v/dev/tools/ivory-tower-gepa-fixes/research/20260302-023901-d0a99b/phase2/opencode-openai-fast-improve-round-03/opencode-openai-fast-improve-round-03/prompt.md`.
- Confirmed complete current report content, existing score/weaknesses, and user-defined improvement tasks.
- Performed extensive supporting web research and pulled major source materials for:
  - protocol/spec references,
  - operational behavior,
  - scaling case studies,
  - library/client ecosystem.
- No report rewrite has been authored yet in file output; no file edits/commits yet.

## Relevant files / directories

- ` /Users/auk000v/dev/tools/ivory-tower-gepa-fixes/research/20260302-023901-d0a99b/phase2/opencode-openai-fast-improve-round-03/opencode-openai-fast-improve-round-03/prompt.md `
  - Contains:
    - Current report draft,
    - Judge feedback (scores, strengths, weaknesses, priority fixes),
    - Rewrite constraints and success criteria.
- Tool output cache for large fetched content:
  - ` /Users/auk000v/.local/share/opencode/tool-output/ ... ` (RFC 6455 fetch was truncated and stored here; path noted in output: `tool_cac6c9cfb0012lJaZJC0nTLVMN`)
