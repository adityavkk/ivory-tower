# Research Synthesis (Adversarial)

2 AI agents independently researched a topic, then each report was iteratively
optimized through 2 rounds of adversarial evaluation by the opposing
agent. You have both optimized reports below.

## Topic
Compare WebSocket vs Server-Sent Events (SSE) for real-time web applications. Cover: protocol differences, browser support, scalability trade-offs, and when to choose each.

## Optimized Report A (claude-opus, scored 0.0/10 by opencode-wibey-opus-4-6)
I've gathered extensive research from authoritative sources. Here is the comprehensive report:

---

# WebSocket vs Server-Sent Events (SSE) for Real-Time Web Applications

## 1. Executive Summary

WebSocket and Server-Sent Events (SSE) are the two dominant protocols for delivering real-time data in web applications, and the choice between them is more consequential—and more nuanced—than many developers realize. WebSocket (RFC 6455, formalized 2011) provides full-duplex, bidirectional communication over a single persistent TCP connection, supporting both text and binary data. SSE, defined by the WHATWG EventSource specification, provides unidirectional server-to-client streaming over standard HTTP, with built-in automatic reconnection and last-event-ID resumption. The fundamental divide is directionality: WebSocket excels when both client and server need to send messages freely (chat, collaborative editing, multiplayer games), while SSE is purpose-built for the far more common pattern of server-push updates (dashboards, notifications, live feeds, and—critically in 2025/2026—LLM token streaming).

The practical landscape has shifted significantly in favor of SSE over the past two years. The ubiquity of HTTP/2 and HTTP/3 has eliminated SSE's historical connection-limit problem by multiplexing hundreds of SSE streams over a single TCP connection. SSE's alignment with standard HTTP means it works seamlessly through corporate firewalls, proxies, CDNs, and edge infrastructure without special configuration. Meanwhile, WebSocket's operational complexity—stateful connections that complicate load balancing, manual reconnection logic, lack of same-origin policy protection, and OS-level file descriptor limits—has become increasingly visible at scale. Companies like Shopify, Split, and every major LLM provider (OpenAI, Anthropic, Google) have chosen SSE for their high-throughput streaming needs, collectively delivering trillions of events per month.

Performance benchmarks show the two protocols are remarkably close: SSE latency is roughly 5–10ms versus WebSocket's 1–3ms, a difference that is negligible for the vast majority of applications. At 100,000 events/second with 10–30 concurrent connections, throughput is essentially identical. The emerging consensus, supported by multiple 2025–2026 analyses, is that SSE is the correct default for ~80–95% of real-time features, with WebSocket reserved for the minority of cases that genuinely require bidirectional communication. Looking forward, WebTransport over HTTP/3 may eventually subsume both protocols for advanced use cases, but its browser support remains incomplete (approximately 75% as of early 2026) and production adoption is years away.

## 2. Background & Context

### The Problem Space

Real-time web applications require mechanisms to push data from servers to clients without the client repeatedly polling for updates. The traditional HTTP request-response model is fundamentally pull-based: the client asks, the server answers. Three main approaches have emerged to bridge this gap: long polling (holding HTTP requests open until data is available), Server-Sent Events (a standardized server-push mechanism over HTTP), and WebSockets (a separate full-duplex protocol that upgrades from HTTP).

### WebSocket: Protocol Fundamentals

The WebSocket protocol, defined in [RFC 6455](https://datatracker.ietf.org/doc/html/rfc6455) and standardized by the IETF in 2011, operates at the Application Layer (OSI layer 7) atop TCP (layer 4). A WebSocket connection begins as a standard HTTP/1.1 request containing an `Upgrade: websocket` header. If the server agrees, the connection is "upgraded" from HTTP to the WebSocket protocol—a distinct binary framing protocol with its own wire format. From that point forward, both client and server can send messages independently at any time over the same connection ([WebSocket.org](https://websocket.org/comparisons/sse/), [High Performance Browser Networking](https://hpbn.co/websocket/)).

The WebSocket wire protocol consists of two components: the opening HTTP handshake (which negotiates connection parameters) and a binary message framing mechanism that supports both text (UTF-8) and binary data with minimal per-frame overhead—as low as 2 bytes per frame compared to hundreds of bytes of HTTP headers per request ([WebSocket.org](https://websocket.org/comparisons/sse/)). The client-side API is defined by the W3C and is available in all modern browsers.

Critically, WebSocket uses its own URI schemes (`ws://` and `wss://`) and is *not* subject to the browser's same-origin policy—a security characteristic with significant implications discussed later.

### Server-Sent Events: Protocol Fundamentals

SSE is defined by the [WHATWG HTML specification](https://html.spec.whatwg.org/multipage/server-sent-events.html) and relies on two components: the `EventSource` browser API and the `text/event-stream` media type. The client creates an `EventSource` object pointed at an HTTP endpoint; the server responds with `Content-Type: text/event-stream` and keeps the connection open, writing event messages as plain-text lines separated by double newlines. Each event can include a `data` field (the payload), an optional `id` field (for resumption), an optional `event` field (for named event types), and an optional `retry` field (to configure reconnection delay) ([MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)).

SSE's most distinctive built-in features are automatic reconnection (the browser will transparently reconnect if the connection drops) and last-event-ID resumption (the browser sends a `Last-Event-ID` header on reconnection, allowing the server to replay missed events). Because SSE operates over standard HTTP, it inherits all of HTTP's security, caching, and routing infrastructure—including the same-origin policy, CORS, cookie-based authentication, and compatibility with proxies and CDNs ([Ably](https://ably.com/blog/websockets-vs-sse)).

SSE is limited to UTF-8 text data (no binary) and is strictly unidirectional (server to client). The native `EventSource` API only supports GET requests and does not allow setting custom headers—a significant limitation discussed below.

## 3. Key Findings

### 3.1 Protocol & Communication Model

The most fundamental difference is directionality. WebSocket provides full-duplex communication: either side can send a message at any time without waiting for a response. SSE is strictly one-way: the server pushes data to the client, and the client communicates back to the server via separate standard HTTP requests ([freeCodeCamp](https://www.freecodecamp.org/news/server-sent-events-vs-websockets/), [SoftwareMill](https://softwaremill.com/sse-vs-websockets-comparing-real-time-communication-protocols/)).

WebSocket uses a binary framing protocol with very low per-message overhead. SSE uses a simple text-based format with `data:` prefixed lines. WebSocket supports both text and binary data; SSE is limited to UTF-8 text. This means SSE cannot natively stream images, audio, or other binary payloads without base64 encoding (which adds ~33% overhead) ([System Design School](https://systemdesignschool.io/blog/server-sent-events-vs-websocket)).

### 3.2 Browser Support & HTTP/2+ Integration

Both protocols enjoy universal modern browser support. WebSocket support has been effectively 100% across major browsers since approximately 2012 ([Can I Use](https://caniuse.com/websockets)). SSE via EventSource is supported in all major browsers except that Internet Explorer never supported it (now irrelevant).

The critical evolution is HTTP/2 and HTTP/3 multiplexing. Under HTTP/1.1, browsers enforce a limit of approximately 6 concurrent connections per domain. This was a significant problem for SSE: if an application opened multiple SSE streams, it could exhaust the browser's connection budget for that domain, blocking other HTTP requests. This limitation was one of WebSocket's key advantages, since each WebSocket connection is independent of the HTTP connection pool ([Smashing Magazine](https://www.smashingmagazine.com/2018/02/sse-websockets-data-flow-http2/)).

HTTP/2 fundamentally changes this equation. It multiplexes many logical streams over a single TCP connection, with default limits of 100–200 concurrent streams per connection. SSE over HTTP/2 can support hundreds or even thousands of concurrent event streams without exhausting browser connections. As one source puts it: "SSE over HTTP/2 = no connection limit. You can have 1000 SSE streams over one TCP connection" ([DEV Community](https://dev.to/polliog/server-sent-events-beat-websockets-for-95-of-real-time-apps-heres-why-a4l)). HTTP/3 (over QUIC) further improves this with reduced latency and better connection resilience.

WebSocket, by contrast, does *not* benefit from HTTP/2 multiplexing. Because WebSocket upgrades away from HTTP to its own protocol, each WebSocket connection is a separate TCP connection. 50 WebSocket connections from a single tab means 50 TCP connections. The WebSockets over HTTP/2 specification (RFC 8441) exists but has limited adoption, and WebSocket over HTTP/3 (RFC 9220) has no production browser implementations as of early 2026 ([Hemaks](https://hemaks.org/posts/modern-http-stack-in-2026-http3-grpc-websockets-and-when-to-use-what/), [WebSocket.org](https://websocket.org/guides/future-of-websockets/)).

### 3.3 Performance Benchmarks

Multiple 2025–2026 benchmarks show remarkably similar performance between the two protocols:

- **Latency:** SSE message latency is approximately 5–10ms; WebSocket latency is approximately 1–3ms. The difference is attributable to HTTP framing overhead in SSE versus WebSocket's minimal binary framing ([Medium/CodeToDeploy](https://medium.com/codetodeploy/why-server-sent-events-beat-websockets-for-95-of-real-time-cloud-applications-830eff5a1d7c)).
- **Throughput:** At 100,000 events/second with 10–30 concurrent connections, performance is "essentially identical." SSE uses slightly more CPU (negligible), while WebSocket has slightly lower latency ([Timeplus](https://www.timeplus.com/post/websocket-vs-sse)).
- **Resource consumption:** A 2026 Socket.IO benchmark found SSE consumed 30–40% fewer server resources than WebSocket in unidirectional scenarios ([Nimbleway](https://www.nimbleway.com/blog/server-sent-events-vs-websockets-what-is-the-difference-2026-guide)).
- **Recommendation:** Given the relative parity, the consensus is to "focus on functional requirements when selecting" rather than trying to optimize for raw protocol performance ([Timeplus](https://www.timeplus.com/post/websocket-vs-sse)).

### 3.4 Scalability & Infrastructure

**WebSocket scaling challenges** are well-documented and substantial:

- **Stateful connections:** Each WebSocket connection is persistent and stateful, consuming a file descriptor on the server. The default OS limit is typically 1,024 file descriptors; most naive WebSocket demos fail at approximately 10,000 connections due to architectural (not protocol) limitations ([Ably](https://ably.com/topic/the-challenge-of-scaling-websockets), [VideoSDK](https://www.videosdk.live/developer-hub/websocket/websocket-scale)).
- **Load balancing:** Because clients must maintain their connection to a specific server for session continuity, standard round-robin load balancing doesn't work. Sticky sessions or connection-aware routing is required ([WebSocket.org](https://websocket.org/guides/websockets-at-scale/)).
- **Thundering herd:** If a server fails and thousands of clients reconnect simultaneously, the replacement server can be overwhelmed. Exponential backoff with jitter is essential ([DEV Community](https://dev.to/ably/challenges-of-scaling-websockets-3493)).
- **Message distribution:** In multi-server deployments, a message sent to one server must reach clients connected to other servers. This requires a pub/sub backplane (Redis, Kafka, RabbitMQ) to distribute messages across the server fleet ([Ably](https://ably.com/topic/websocket-architecture-best-practices)).

**SSE scaling** faces many of the same connection-statefulness challenges—this is not unique to WebSocket. Any long-lived connection technology requires connection state management and a pub/sub backplane for horizontal scaling ([Roxeem](https://roxeem.com/2025/10/24/a-pragmatic-guide-to-server-sent-events-sse-in-asp-net-core/)). However, SSE has significant operational advantages:

- **Infrastructure compatibility:** SSE connections are standard HTTP traffic. They work through existing proxies, firewalls, CDNs, and load balancers without special configuration. Edge computing platforms have embraced SSE natively ([portalZINE](https://portalzine.de/sses-glorious-comeback-why-2025-is-the-year-of-server-sent-events/)).
- **Serverless compatibility:** SSE works well with serverless functions and Kubernetes ingress controllers. Service meshes like Envoy have excellent SSE support ([portalZINE](https://portalzine.de/sses-glorious-comeback-why-2025-is-the-year-of-server-sent-events/)).
- **Simpler resource footprint:** Because SSE connections are treated as regular HTTP traffic, they can be more efficient for server resource usage and don't require the dedicated connection management infrastructure that WebSocket demands.

A practical benchmark found a single Go server handling approximately 15,400 concurrent SSE connections before hitting OS-level ephemeral port exhaustion on Windows, with CPU and memory well within limits ([blog.pranshu-raj.me](https://blog.pranshu-raj.me/posts/exploring-sse/)).

### 3.5 Production Case Studies

**Shopify** replaced their polling-based Black Friday Cyber Monday (BFCM) Live Map with SSE in 2022. The previous system used a 10-second poll interval; with SSE, data was delivered to clients within milliseconds of availability. During BFCM, Shopify ingested 323 billion rows of data in a four-day window with 100% uptime. End-to-end latency (including Flink pipeline processing) was 21 seconds from data creation to visualization. They chose SSE over WebSocket specifically because they didn't need bidirectional communication and valued SSE's simplicity and automatic reconnection ([Shopify Engineering](https://shopify.engineering/server-sent-events-data-streaming)).

**Split** (feature flagging platform) uses SSE to deliver more than one trillion events per month with an average global latency under 300 milliseconds ([DEV Community](https://dev.to/polliog/server-sent-events-beat-websockets-for-95-of-real-time-apps-heres-why-a4l)).

**Slack, Netflix, and Uber** use WebSocket to power real-time features for millions of users—the canonical examples of applications where bidirectional communication is genuinely necessary ([VideoSDK](https://www.videosdk.live/developer-hub/websocket/websocket-scale)).

**OpenAI, Anthropic, and Google** all use SSE as the primary streaming protocol for their LLM APIs. ChatGPT's token-by-token streaming—arguably the most visible real-time web experience of the past three years—runs on SSE. The format is simple: `data:` prefixed lines containing JSON, terminated by `data: [DONE]` ([OpenAI](https://developers.openai.com/api/docs/guides/streaming-responses/), [Procedure.tech](https://procedure.tech/blogs/the-streaming-backbone-of-llms-why-server-sent-events-(sse)-still-wins-in-2025)).

### 3.6 Security Considerations

The security posture of these protocols differs significantly:

**WebSocket** is *not* subject to the browser's same-origin policy. This makes Cross-Site WebSocket Hijacking (CSWSH) a real threat: a malicious page can open a WebSocket connection to a victim's server, and the browser will attach the victim's cookies automatically. Developers must implement explicit origin checking or anti-CSRF tokens. The WebSocket handshake supports limited headers, and ongoing communication has no per-message header mechanism for authentication. Encrypted communication requires the `wss://` scheme ([Solita](https://dev.solita.fi/2018/11/07/securing-websocket-endpoints.html), [VideoSDK](https://www.videosdk.live/developer-hub/websocket/sse-websocket)).

**SSE** inherits HTTP's full security model. It is subject to the same-origin policy and CORS, making it inherently resistant to the cross-site attacks that plague WebSocket. It benefits from standard HTTP authentication mechanisms (cookies, Bearer tokens via workarounds, etc.) and uses standard HTTPS for encryption. However, long-lived SSE connections require careful token expiration and refresh strategies, and unprotected SSE endpoints can be DoS vectors if connection rate limiting is not implemented ([Treblle](https://treblle.com/blog/sse-stdio-api-security), [Medium](https://medium.com/@moali314/server-sent-events-a-comprehensive-guide-e4b15d147576)).

### 3.7 Developer Experience & Limitations

**SSE's EventSource API limitations** are a notable friction point. The native browser `EventSource` API only supports GET requests, cannot set custom headers (critically, no `Authorization` header), and provides no control over the retry strategy. This means authentication must be done via cookies or query parameters—the latter being a security concern since URLs may be logged ([WHATWG Issue #2177](https://github.com/whatwg/html/issues/2177)).

The community has produced robust workarounds. The most widely adopted is Microsoft's [`@microsoft/fetch-event-source`](https://github.com/Azure/fetch-event-source), which implements the SSE protocol atop the Fetch API, enabling POST requests, custom headers, request bodies, and configurable retry logic. Other options include Sindre Sorhus's [`parse-sse`](https://github.com/sindresorhus/parse-sse) for lightweight SSE parsing from any Response object, and the `eventsource` npm package with custom fetch support. For React applications, `react-eventsource` provides a hook-based API with header support ([Medium/Pon.Tech.Talk](https://medium.com/pon-tech-talk/extend-the-usage-of-the-eventsource-api-with-microsoft-fetch-event-source-a5c83ff95964)).

**WebSocket** has mature tooling (Socket.IO, ws, etc.) but requires developers to implement their own message framing, reconnection logic, heartbeat/ping-pong, and application-level protocol on top of the raw bidirectional channel. This is significantly more code and complexity than SSE's built-in event format and reconnection.

**SSE production gotchas** include: intermediary buffering (proxies like Nginx may buffer SSE responses unless explicitly configured with `X-Accel-Buffering: no` or `proxy_buffering off`), framework-specific issues (Next.js's built-in compression can buffer SSE streams, requiring `compress: false`), and load balancer reconnection routing (a reconnecting client may hit a different server and lose its event context) ([DEV Community](https://dev.to/miketalbot/server-sent-events-are-still-not-production-ready-after-a-decade-a-lesson-for-me-a-warning-for-you-2gie), [Roxeem](https://roxeem.com/2025/10/24/a-pragmatic-guide-to-server-sent-events-sse-in-asp-net-core/)).

### 3.8 The Future: WebTransport

WebTransport, built on HTTP/3 and QUIC, is an emerging protocol that may eventually address limitations of both WebSocket and SSE. It offers multiplexed streams over a single connection, mixed reliable/unreliable delivery (critical for gaming and media), no head-of-line blocking, and better network resilience (survives Wi-Fi-to-cellular handoffs). Browser support is approximately 75% as of early 2026 (Chrome and Edge stable, Firefox partial, Safari in development). The Interop 2026 initiative—a collaboration between Apple, Google, Microsoft, and Mozilla—has prioritized WebTransport, which may accelerate Safari and Firefox support through 2026 ([WebSocket.org](https://websocket.org/comparisons/webtransport/), [WebKit](https://webkit.org/blog/17818/announcing-interop-2026/)).

The consensus timeline for WebTransport adoption is: experimental only in 2025, early adopter production use by 2027, mainstream by 2028. WebSocket will not disappear but will coexist with WebTransport, each serving different use cases ([VideoSDK](https://www.videosdk.live/developer-hub/websocket/what-is-replacing-websockets)).

## 4. Analysis

### When to Choose SSE

SSE is the correct default for the majority of real-time web features. The qualifying question is simple: **does the client need to send frequent, low-latency messages to the server over the same connection?** If no—and for most applications, the answer is no—SSE is the better choice. Specific use cases where SSE excels:

- **Dashboards and monitoring:** Server pushes metrics, logs, or status updates. Client interactions (changing filters, time ranges) are infrequent and well-served by standard HTTP requests.
- **Notifications and activity feeds:** Pure server-push pattern.
- **LLM/AI token streaming:** The defining use case of 2024–2026. Every major LLM provider uses SSE. The unidirectional, text-based nature of token streaming is a perfect fit.
- **Live sports scores, stock tickers, news feeds:** Server-push with occasional client-initiated filter changes via HTTP.
- **Server-side progress updates:** Build progress, file upload status, long-running job status.

The operational advantages are substantial: SSE works through existing HTTP infrastructure without modification, benefits from HTTP/2 multiplexing, inherits HTTP security mechanisms, provides automatic reconnection, and consumes 30–40% fewer server resources than WebSocket for equivalent unidirectional workloads.

### When to Choose WebSocket

WebSocket is the right choice when bidirectional, low-latency communication is a genuine requirement—not a "nice to have," but architecturally necessary. Specific use cases:

- **Chat and messaging:** Both parties send messages unpredictably. While technically achievable with SSE + HTTP POST, the ergonomics of a single bidirectional channel are superior for complex chat protocols.
- **Collaborative editing:** Operational transforms or CRDTs require rapid bidirectional state synchronization. Google Docs, Figma, and similar tools use WebSocket-like protocols.
- **Multiplayer games:** Low-latency bidirectional input/state synchronization. The 1–3ms latency advantage over SSE matters here.
- **Trading platforms:** Sub-millisecond order execution requires the lowest possible latency in both directions.

The key test: if your client sends data to the server only in response to user actions (button clicks, form submissions, navigation), those interactions are perfectly served by standard HTTP requests alongside an SSE stream for server push. You don't need WebSocket.

### The Hidden Cost of Choosing WebSocket by Default

Many teams default to WebSocket for any "real-time" feature and pay a disproportionate infrastructure tax. WebSocket requires:

1. Special proxy/load balancer configuration (connection upgrade support, sticky sessions)
2. Custom reconnection logic with exponential backoff and jitter
3. Application-level message framing and protocol design
4. Explicit security measures (origin checking, CSRF protection)
5. Connection state management and pub/sub backplane for horizontal scaling
6. OS-level tuning (file descriptor limits) at scale
7. Monitoring for idle connections, backpressure, and thundering herd scenarios

SSE eliminates or simplifies items 1, 2, 3, and 4 entirely, and shares the remaining challenges (5, 6, 7) with any long-lived connection technology. The total cost of ownership for an SSE-based system is meaningfully lower.

## 5. Open Questions & Gaps

**EventSource API modernization.** The native `EventSource` API's inability to set custom headers is a well-known deficiency tracked in [WHATWG Issue #2177](https://github.com/whatwg/html/issues/2177), open since 2017. Despite widespread community demand and the proliferation of workaround libraries, there is no clear timeline for the spec to be updated. It's unclear whether the standards bodies consider this a priority or whether the Fetch API-based approach is considered the de facto solution. This gap forces every production SSE deployment to either use cookies for auth (with CSRF implications) or adopt a third-party library.

**SSE intermediary reliability.** One contrarian source ([DEV Community, Mike Talbot](https://dev.to/miketalbot/server-sent-events-are-still-not-production-ready-after-a-decade-a-lesson-for-me-a-warning-for-you-2gie)) argues that SSE is "still not production ready after a decade" specifically because intermediaries (corporate proxies, CDNs, mobile carrier gateways) can silently buffer or drop SSE streams, and developers have no way to detect or control this. Most other sources disagree, but this concern warrants attention for applications where you don't control the network path. The extent to which this remains a problem in 2026 with widespread HTTP/2 deployment is unclear.

**Quantitative scaling comparisons.** While individual benchmarks exist for both protocols, there is a notable absence of rigorous, apples-to-apples comparisons measuring concurrent connections, memory per connection, CPU overhead, and tail latency under identical conditions at scale (100K+ connections). The "30–40% fewer resources for SSE" claim from a 2026 Socket.IO benchmark is widely cited but I could not locate the primary benchmark report to evaluate its methodology.

**WebTransport adoption trajectory.** The timelines for WebTransport readiness are speculative. Safari's implementation progress is not publicly tracked with granularity, and the Interop 2026 inclusion may or may not translate to stable support within 2026. The "WebTransport over WebSocket" fallback draft adds another variable. How quickly the ecosystem shifts is genuinely uncertain.

**Binary data over SSE.** For applications that need to stream binary data (images, audio, video), SSE is categorically unsuitable without encoding overhead. The question of whether base64-encoded binary over SSE is ever practical (versus just using WebSocket) lacks rigorous analysis. For the emerging use case of streaming AI-generated images or audio, this could become increasingly relevant.

## 6. Sources

1. [Ably — WebSockets vs Server-Sent Events (SSE)](https://ably.com/blog/websockets-vs-sse)
2. [WebSocket.org — WebSockets vs SSE: Choosing Your Real-Time Protocol](https://websocket.org/comparisons/sse/)
3. [freeCodeCamp — Server-Sent Events vs WebSockets](https://www.freecodecamp.org/news/server-sent-events-vs-websockets/)
4. [SoftwareMill — SSE vs WebSockets: Comparing Real-Time Communication Protocols](https://softwaremill.com/sse-vs-websockets-comparing-real-time-communication-protocols/)
5. [System Design School — WebSocket vs SSE In-Depth Comparison](https://systemdesignschool.io/blog/server-sent-events-vs-websocket)
6. [Medium/CodeToDeploy — Why Server-Sent Events Beat WebSockets for 95% of Real-Time Cloud Applications (Jan 2026)](https://medium.com/codetodeploy/why-server-sent-events-beat-websockets-for-95-of-real-time-cloud-applications-830eff5a1d7c)
7. [Nimbleway — Server-Sent Events vs WebSockets 2026 Guide](https://www.nimbleway.com/blog/server-sent-events-vs-websockets-what-is-the-difference-2026-guide)
8. [Timeplus — WebSocket vs SSE: A Performance Comparison](https://www.timeplus.com/post/websocket-vs-sse)
9. [Shopify Engineering — Using Server Sent Events to Simplify Real-time Streaming at Scale](https://shopify.engineering/server-sent-events-data-streaming)
10. [DEV Community — Server-Sent Events Beat WebSockets for 95% of Real-Time Apps](https://dev.to/polliog/server-sent-events-beat-websockets-for-95-of-real-time-apps-heres-why-a4l)
11. [portalZINE — SSE's Glorious Comeback: Why 2025 is the Year of Server-Sent Events](https://portalzine.de/sses-glorious-comeback-why-2025-is-the-year-of-server-sent-events/)
12. [blog.pranshu-raj.me — Scaling Server Sent Events: A Practical Guide to 28,000+ Concurrent Connections](https://blog.pranshu-raj.me/posts/exploring-sse/)
13. [DEV Community (Mike Talbot) — Server Sent Events Are Still Not Production Ready After a Decade](https://dev.to/miketalbot/server-sent-events-are-still-not-production-ready-after-a-decade-a-lesson-for-me-a-warning-for-you-2gie)
14. [Smashing Magazine — Using SSE Instead of WebSockets for Unidirectional Data Flow Over HTTP/2](https://www.smashingmagazine.com/2018/02/sse-websockets-data-flow-http2/)
15. [Can I Use — WebSockets](https://caniuse.com/websockets)
16. [Hemaks — Modern HTTP Stack in 2026](https://hemaks.org/posts/modern-http-stack-in-2026-http3-grpc-websockets-and-when-to-use-what/)
17. [Ably — The Challenge of Scaling WebSockets](https://ably.com/topic/the-challenge-of-scaling-websockets)
18. [DEV Community — Challenges of Scaling WebSockets](https://dev.to/ably/challenges-of-scaling-websockets-3493)
19. [VideoSDK — WebSocket Scale in 2025](https://www.videosdk.live/developer-hub/websocket/websocket-scale)
20. [WebSocket.org — WebSockets at Scale: Production Architecture and Best Practices](https://websocket.org/guides/websockets-at-scale/)
21. [Ably — WebSocket Architecture Best Practices](https://ably.com/topic/websocket-architecture-best-practices)
22. [Solita — Securing WebSocket Endpoints Against Cross-Site Attacks](https://dev.solita.fi/2018/11/07/securing-websocket-endpoints.html)
23. [Treblle — How SSE and STDIO Can Ruin Your API Security](https://treblle.com/blog/sse-stdio-api-security)
24. [Medium — Server-Sent Events: A Comprehensive Guide](https://medium.com/@moali314/server-sent-events-a-comprehensive-guide-e4b15d147576)
25. [WHATWG Issue #2177 — Setting Headers for EventSource](https://github.com/whatwg/html/issues/2177)
26. [GitHub/Azure — @microsoft/fetch-event-source](https://github.com/Azure/fetch-event-source)
27. [GitHub/sindresorhus — parse-sse](https://github.com/sindresorhus/parse-sse)
28. [Medium/Pon.Tech.Talk — Extend the EventSource API with @microsoft/fetch-event-source](https://medium.com/pon-tech-talk/extend-the-usage-of-the-eventsource-api-with-microsoft-fetch-event-source-a5c83ff95964)
29. [Roxeem — A Pragmatic Guide to Server-Sent Events in ASP.NET Core](https://roxeem.com/2025/10/24/a-pragmatic-guide-to-server-sent-events-sse-in-asp-net-core/)
30. [SurveySparrow Engineering — Scaling Real-Time Applications with SSE](https://engineering.surveysparrow.com/scaling-real-time-applications-with-server-sent-events-sse-abd91f70a5c9)
31. [OpenAI — Streaming API Responses](https://developers.openai.com/api/docs/guides/streaming-responses/)
32. [Procedure.tech — The Streaming Backbone of LLMs: Why SSE Still Wins in 2026](https://procedure.tech/blogs/the-streaming-backbone-of-llms-why-server-sent-events-(sse)-still-wins-in-2025)
33. [Vercel AI SDK — Stream Protocols](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)
34. [WebSocket.org — The Future of WebSockets: HTTP/3 and WebTransport](https://websocket.org/guides/future-of-websockets/)
35. [WebSocket.org — WebSockets vs WebTransport](https://websocket.org/comparisons/webtransport/)
36. [VideoSDK — What is Replacing WebSockets?](https://www.videosdk.live/developer-hub/websocket/what-is-replacing-websockets)
37. [WebKit — Announcing Interop 2026](https://webkit.org/blog/17818/announcing-interop-2026/)
38. [High Performance Browser Networking (O'Reilly) — WebSocket](https://hpbn.co/websocket/)
39. [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
40. [WHATWG HTML Standard — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
41. [RxDB — WebSockets vs SSE vs Long-Polling vs WebRTC vs WebTransport](https://rxdb.info/articles/websockets-sse-polling-webrtc-webtransport.html)


## Optimized Report B (opencode-wibey-opus-4-6, scored 0.0/10 by claude-opus)
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

Be thorough. This is the final deliverable.