## Goal

- Produce a comprehensive research report comparing **WebSocket vs Server-Sent Events (SSE)** for real-time web applications.
- Cover: protocol differences, browser support, scalability trade-offs, and clear “when to choose each” guidance.
- Final deliverable requested: standalone report with sections:
  1. Executive Summary (2–3 substantive paragraphs)
  2. Background & Context
  3. Key Findings (theme-based, with cited evidence)
  4. Analysis (tradeoffs, implications, recommendations)
  5. Open Questions & Gaps
  6. Sources (URL list, inline citations in body)

## Instructions

- User-provided task file read at `.../prompt.md` explicitly required:
  - Use web search extensively and prefer primary sources.
  - Prefer primary docs (RFCs, official specs/docs) over secondary commentary.
  - Note publication dates and prefer last 2 years where relevant.
  - Cite source inline for each claim.
  - Present conflicting evidence side-by-side if contradictory.
  - Write in-depth, non-bullet-heavy sections with practical standalone value.
- No additional user file edits were requested yet; no explicit coding constraints besides generating the report content.
- Current context expectation:
  - We are in “research + synthesis” mode, not implementation mode.
  - No files have been modified so far.

## Discoveries

- **Prompt/requirements loaded successfully**
  - Read `research/.../prompt.md` and extracted required structure and evidence quality constraints.

- **WebSocket API basics (MDN + spec sources)**
  - MDN confirms `WebSocket` is bidirectional, supports text/binary, events (`open`, `message`, `error`, `close`), and notes no built-in backpressure; `bufferedAmount` exists and MDN points readers to WebSocketStream for stream backpressure.
  - MDN notes WebSocket is widely available “since July 2015” and broadly supported.
  - MDN `EventSource` pages confirm SSE is browser-supported one-way from server to client, text/event-stream based, and unidirectional.
  - MDN EventSource pages include `readyState` constants: CONNECTING=0, OPEN=1, CLOSED=2.
  - Both MDN pages include last modified dates and compatibility tables for grounding.

- **Primary protocol/docs**
  - RFC6455 (WebSocket Protocol): key mechanics include HTTP/1.1 upgrade handshake (`Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key`, etc.), bidirectional framed communication, masking rules, close semantics.
  - WHATWG WebSocket spec (living standard): browser-level behavior and API semantics (connection state, open/message/error/close events, constructor validation, allowed schemes, etc.).
  - HTML Living Standard SSE section: EventSource processing model, parsing algorithm (`text/event-stream`), reconnection semantics, `Last-Event-ID`, event dispatch behavior, and per-connection close/reconnect state machine.
  - RFC8441 (Bootstrapping WebSockets with HTTP/2): explains extended CONNECT with `:protocol websocket`, eliminating HTTP/1 Upgrade/Connection header semantics for H2 transport; includes interoperability/security notes.

- **Browser support and operational constraints**
  - Can I Use snapshots fetched:
    - WebSocket global usage ~96.73% (recent Jan 2026 table), broad modern support.
    - SSE global usage ~96.44%, broadly supported in modern ecosystems but older Safari/IE-era limitations noted.
  - WebSocket pages mention older browser support caveats (partial support in legacy versions); SSE similarly has legacy partial/non-support in old Safari/IE-era entries.
  - MDN and caniuse provide practical compatibility context but are not substitute for primary protocol specs.

- **Scalability & deployment observations (important practical findings)**
  - MDN EventSource/MDN/W3C discuss SSE reconnection and long-lived stream behavior; notes default per-domain connection limit around 6 in HTTP/1 contexts (MDN and related docs mention this repeatedly for SSE; can be severe for many tabs).
  - MDN’s EventSource page and community knowledge align: SSE connection-per-browser per-origin limitations are operationally relevant.
  - MDN WebSocket page + WebSocketStream mention stream/backpressure concerns.
  - Node.js `http` docs and upgrade/connect events provide practical server-side handling references for upgrade-based protocols.
  - NGINX docs show required proxy config for WebSocket tunneling (`proxy_set_header Upgrade` + `Connection`), and mention `proxy_http_version 1.1` and keep-alive/read-timeout considerations.
  - AWS API Gateway docs were fetched mainly for high-level WebSocket API/limits, but the fetched pages were partially truncated and need re-fetching for usable detail if we include managed-platform specifics.

- **Tooling/session caveat**
  - Several fetches returned truncated output (large RFC/docs pages); the tool suggested using a task-based segmented read approach, which was not yet executed.
  - `webfetch` on Cloudflare docs returned 404 and was not useful.
  - `dev.to` homepage was fetched accidentally/irrelevant.

## Accomplished

- ✅ Read and interpreted user instructions from prompt file.
- ✅ Gathered a substantial set of sources for both technologies:
  - MDN WebSocket, EventSource, EventSource readyState, WebSocketStream
  - WHATWG WebSockets spec
  - WHATWG HTML (SSE/EventSource section)
  - RFC6455 (WebSocket), RFC8441 (WebSockets over HTTP/2), RFC7230 (HTTP/1.1)
  - Can I Use WebSocket + SSE compatibility tables
  - NGINX proxying guidance for WebSockets
  - Node.js `http` upgrade/connect event docs
  - AWS API Gateway docs (overview + quotas pages), though not fully extracted
- ✅ Started identifying the main comparison dimensions relevant to the requested report:
  - Directionality
  - Protocol handshake/transport
  - Browser behavior and reconnection semantics
  - Backpressure and flow control limitations
  - Proxy/load-balancer behavior
  - Connection persistence/scalability ceilings
  - Tooling/managed service implications
- ⏳ Not yet done:
  - Synthesized final report text in required structure.
  - Structured, inline-cited analysis and recommendations.
  - Clear “when to choose WebSocket vs SSE” section in final deliverable.
  - Complete, concise Open Questions section with source-backed gaps.

- No files were modified.
- No code changes were made.

## Relevant files / directories

### Read
- ` /Users/auk000v/dev/tools/ivory-tower/research/20260301-212129-06e860/phase1/20260301-212129-06e860/prompt.md `

### No files edited/created
- No local file writes or patches have been performed yet.

### External sources (not local files, but important for continuation)
- MDN:
  - https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
  - https://developer.mozilla.org/en-US/docs/Web/API/EventSource
  - https://developer.mozilla.org/en-US/docs/Web/API/EventSource/readyState
  - https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
  - https://developer.mozilla.org/en-US/docs/Web/API/WebSocketStream
- Standards:
  - https://www.rfc-editor.org/rfc/rfc6455
  - https://www.rfc-editor.org/rfc/rfc8441
  - https://html.spec.whatwg.org/multipage/web-sockets.html
  - https://html.spec.whatwg.org/multipage/server-sent-events.html
  - https://www.rfc-editor.org/rfc/rfc7230
- Support/comparisons:
  - https://caniuse.com/websockets
  - https://caniuse.com/eventsource
- Operational docs:
  - https://nginx.org/en/docs/http/websocket.html
  - https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
  - https://nodejs.org/api/http.html#http_event_upgrade
  - https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api.html
  - https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html
