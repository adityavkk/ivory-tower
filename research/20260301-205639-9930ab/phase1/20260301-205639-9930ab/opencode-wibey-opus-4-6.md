This is a deep research task comparing WebSocket vs Server-Sent Events (SSE). Let me plan this out and then conduct thorough research.
Let me start by gathering research from multiple authoritative sources in parallel.
Good, I have substantial data from the primary sources. Now let me gather more recent comparative information and scalability data.
Excellent. Now let me get additional information on scalability and recent developments.
Let me get the Ably comparison article and some additional scalability research.
I now have comprehensive data from authoritative sources. Let me update my progress and write the research report.
Now let me verify the output directory exists and write the report.
The research report has been written to:

`/Users/auk000v/dev/tools/ivory-tower/research/20260301-205639-9930ab/phase1/20260301-205639-9930ab/report.md`

The report covers all requested areas across six sections:

1. **Executive Summary** -- WebSocket provides full-duplex bidirectional communication; SSE provides simpler unidirectional server-to-client push over standard HTTP. Both have ~96%+ browser support in 2026. The choice hinges on data flow direction.

2. **Background & Context** -- History of real-time web (polling, long polling, HTTP streaming), followed by the origin and design of both WebSocket (RFC 6455) and SSE (WHATWG HTML Living Standard).

3. **Key Findings** organized by theme:
   - Protocol differences (detailed comparison table)
   - Browser support (January 2026 data from Can I Use)
   - Scalability trade-offs (HTTP/1.1 vs HTTP/2 connection limits, server architecture, horizontal scaling patterns, production case studies from LinkedIn, Shopify, Split.io)
   - Development complexity (server and client implementation comparison)
   - Security considerations
   - The WebTransport horizon

4. **Analysis** -- Decision framework for when to choose SSE vs WebSocket, the emerging "SSE + HTTP POST" pattern, and a cost-benefit summary table.

5. **Open Questions & Gaps** -- Lack of rigorous benchmarks, HTTP/3 impact on SSE, EventSource API header limitations, RFC 8441 adoption uncertainty, WebTransport timeline.

6. **Sources** -- 19 cited references including RFCs, WHATWG spec, MDN docs, Can I Use data, and engineering blogs from LinkedIn, Shopify, and Ably.
