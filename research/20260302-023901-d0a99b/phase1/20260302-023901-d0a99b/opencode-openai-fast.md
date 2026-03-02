## Goal

- Deliver a standalone research report comparing **WebSocket** and **Server-Sent Events (SSE)** for real-time web applications.
- Cover protocol differences, browser/platform support, scalability trade-offs, and practical guidance on when to choose each.
- Use authoritative/primary sources, preferably recent, with inline citations and a full sources list.
- Keep the output in the exact structure requested in `prompt.md`:
  1. Executive Summary  
  2. Background & Context  
  3. Key Findings (theme-based, evidence-backed)  
  4. Analysis  
  5. Open Questions & Gaps  
  6. Sources (comprehensive list)

## Instructions

- Primary user instruction came from `prompt.md` at:
  - ` /Users/auk000v/dev/tools/ivory-tower-gepa-fixes/research/20260302-023901-d0a99b/phase1/20260302-023901-d0a99b/prompt.md`
- Required methodology:
  - Use web search/primary sources (specs, official docs) heavily.
  - Prefer publication date 2 years or less when relevant; note when older but still important.
  - Cite sources inline for every claim.
  - Present contradictory information if found, with citations.
- Output requirements from prompt:
  - In-depth, all sections substantive (not bullet-only).
  - Evidence-rich, standalone reference-quality report.
- Additional working constraints from system/developer context:
  - No source code edits or file changes were made yet.
  - We were asked to proceed with work and summarize state, not ask further clarifying questions.

## Discoveries

- `prompt.md` explicitly requests a deep comparative research report on WebSocket vs SSE, including:
  - protocol differences
  - browser support
  - scalability trade-offs
  - usage guidance.
- I collected a substantial set of sources (mostly MDN/specs/standards) but **haven’t synthesized them into the final report yet**.
- Reliable sources already pulled:
  - MDN WebSocket API + EventSource pages (overview, API semantics, reconnection behavior, browser support, limitations).
  - RFCs:
    - RFC 6455 (WebSocket Protocol, handshake, framing, masking, framing details, scaling/connection behavior, etc.)
    - RFC 8441 (WebSockets over HTTP/2 bootstrapping via extended CONNECT)
  - WHATWG HTML spec sections on SSE/EventSource (stream parsing, reconnection, line/event format, last-event-id behavior).
- AWS/Cloudflare sources were partially explored:
  - Multiple Cloudflare pages loaded successfully (Runtime API WebSockets, Streams).
  - Some Cloudflare and AWS URLs returned 404 (not enough reliable content yet), so managed-service tradeoff coverage is incomplete.
- Additional implementation-oriented sources pulled:
  - MDN WebSocketStream (experimental status, backpressure concept).
  - MDN Writing WebSocket servers (handshake, masking, pings/pongs, extensions/subprotocols, framing details).
  - NGINX WebSocket proxying docs (critical for infrastructure scaling and reverse-proxy setup).
- Gaps/notes from sources:
  - SSE page contains the key browser limitation note: HTTP/1.x per-browser/domain connection cap (~6) and HTTP/2 negotiated stream limits.
  - MDN reiterates SSE is one-way (server→client only).
  - WebSocket MDN and RFCs provide full-duplex framing, masking, and custom message patterns.
  - NGINX docs indicate special proxy config required for Upgrade/Connection headers (relevant for production scaling).

## Accomplished

- Read `prompt.md` and extracted exact required output structure and constraints.
- Collected primary reference data for both protocols:
  - protocol-level specs and API docs.
  - browser/platform behavior and caveats.
  - server-side and proxying considerations.
- Attempted and partially explored cloud platform docs (Cloudflare, AWS) to understand managed-service posture:
  - Cloudflare basics available.
  - Some requested URLs were invalid/404 (needs follow-up with corrected endpoints if needed).
- No final report has been produced yet.
- No repository files were modified, created, or deleted during this phase.

## What’s in progress / next

- Remaining work:
  - Final synthesis into the requested 6-section standalone report.
  - Add inline citations per claim from gathered sources.
  - Expand and finalize Sources section with full URLs.
  - Optionally continue source collection for:
    - Correct AWS managed WebSocket/SSE API Gateway docs (current fetch attempts hit 404).
    - A stable Cloudflare SSE strategy page if needed.
    - Any current benchmarks/performance data (if available) for richer scalability comparison.

## Relevant files / directories

- ` /Users/auk000v/dev/tools/ivory-tower-gepa-fixes/research/20260302-023901-d0a99b/phase1/20260302-023901-d0a99b/prompt.md` (read only; task spec/instructions)
- No other local project files were edited.
