# WebSocket vs Server-Sent Events (SSE) for Real-Time Web Applications

## 1. Executive Summary

WebSocket and Server-Sent Events (SSE) are the two primary browser-native technologies for real-time communication between web servers and clients, each designed for fundamentally different communication patterns. WebSocket, defined by RFC 6455 (December 2011), provides a full-duplex, bidirectional communication channel over a single TCP connection, making it the standard choice for applications requiring low-latency two-way data exchange such as chat, gaming, and collaborative editing. SSE, standardized as part of the WHATWG HTML Living Standard via the `EventSource` interface, offers a simpler, unidirectional server-to-client push mechanism that operates over standard HTTP, with built-in automatic reconnection and event ID tracking.

The practical choice between these technologies comes down to whether the application requires bidirectional communication. If the server needs to push updates to the client and the client only occasionally sends data back (via standard HTTP requests), SSE provides a simpler, more HTTP-friendly solution that works seamlessly with existing infrastructure -- proxies, CDNs, load balancers, and HTTP/2 multiplexing. If the application needs persistent, low-latency bidirectional communication where both client and server frequently send messages, WebSocket is the appropriate choice, despite its higher implementation complexity and infrastructure requirements.

Both technologies enjoy near-universal browser support in 2026 (96.7% for WebSocket, 96.4% for SSE per Can I Use data from January 2026), with the notable exception that SSE was never supported in Internet Explorer (all versions) while WebSocket was supported from IE 10. For modern applications targeting current browsers, both are reliably available. The emergence of HTTP/2 and HTTP/3 has particularly benefited SSE by eliminating its historical per-browser connection limit, while RFC 8441 (September 2018) extended WebSocket to work over HTTP/2 streams.

## 2. Background & Context

### The Problem Both Technologies Solve

Before WebSocket and SSE, web applications requiring real-time updates relied on workarounds built atop HTTP's request-response model. These included:

- **Short polling**: The client repeatedly sends HTTP requests at intervals to check for updates. This creates significant overhead, as most responses may contain no new data, yet each incurs the full cost of an HTTP request/response cycle with headers (RFC 6455, Section 1.1).
- **Long polling (Comet/Hanging GET)**: The server holds an open HTTP request until new data is available, then responds and the client immediately reconnects. This reduces latency compared to short polling but still requires a new HTTP connection for each message exchange and creates complications with timeouts and resource usage (web.dev, "Stream updates with server-sent events").
- **Streaming via iframes or XMLHttpRequest**: Various hacks using hidden iframes with server-pushed script tags, or multipart XHR responses. These were fragile and non-standard.

RFC 6202 ("Known Issues and Best Practices for the Use of Long Polling and Streaming in Bidirectional HTTP") documented the problems with these approaches, which directly motivated the development of WebSocket.

### WebSocket: Protocol Origins and Design

The WebSocket Protocol (RFC 6455) was published as a Proposed Standard by the IETF in December 2011, authored by Ian Fette (Google) and Alexey Melnikov (Isode). It was designed to provide "a mechanism for browser-based applications that need two-way communication with servers that does not rely on opening multiple HTTP connections" (RFC 6455, Abstract).

Key design principles from the RFC include:
- **Minimal framing**: The protocol adds as little overhead as possible on top of TCP, with only enough framing to support message-based (rather than stream-based) communication and to distinguish text from binary data (RFC 6455, Section 1.5).
- **HTTP compatibility**: The handshake is a valid HTTP Upgrade request, allowing WebSocket to share ports 80 and 443 with HTTP servers and to work through HTTP proxies and intermediaries (RFC 6455, Section 1.7).
- **Origin-based security**: The protocol uses the browser's origin model to prevent unauthorized cross-origin connections (RFC 6455, Section 1.6).

The protocol uses URI schemes `ws://` (port 80) and `wss://` (port 443, over TLS).

### SSE: A Simpler Model

Server-Sent Events are defined in Section 9.2 of the WHATWG HTML Living Standard (last updated February 27, 2026). Unlike WebSocket, SSE was not designed as a separate protocol -- it is a standard HTTP response with a `text/event-stream` MIME type that the browser interprets through the `EventSource` API.

SSE's design philosophy is one of deliberate simplicity. As the web.dev article by Eric Bidelman explains: "Server-sent events have been designed from the ground up to be efficient. When communicating with SSEs, a server can push data to your app whenever it wants, without the need to make an initial request. In other words, updates can be streamed from server to client as they happen. SSEs open a single unidirectional channel between server and client."

The `EventSource` interface was originally part of the HTML5 specification before being incorporated into the WHATWG HTML Living Standard. It has been available across all major browser engines since approximately 2020 (MDN notes it as "Baseline Widely available").

## 3. Key Findings

### 3.1 Protocol Differences

#### Communication Direction

The most fundamental difference between the two technologies is the communication model:

- **WebSocket**: Full-duplex bidirectional communication. Either party (client or server) can send data at any time independently of the other, over a single persistent TCP connection. After the handshake, both sides can initiate messages at will (RFC 6455, Section 1.2).
- **SSE**: Unidirectional server-to-client push. The server streams events to the client over a standard HTTP response. The client cannot send data to the server over the same connection -- if the client needs to communicate with the server, it uses separate HTTP requests (e.g., `fetch()` or `XMLHttpRequest`) (WHATWG HTML Living Standard, Section 9.2.1; MDN "Using server-sent events").

#### Connection Establishment

**WebSocket** initiates with an HTTP Upgrade handshake. The client sends a standard HTTP GET request with `Upgrade: websocket` and `Connection: Upgrade` headers, along with a `Sec-WebSocket-Key` header containing a base64-encoded nonce. The server responds with HTTP 101 Switching Protocols and a `Sec-WebSocket-Accept` header containing a hash of the client's key concatenated with a GUID. After this handshake, the connection "upgrades" from HTTP to the WebSocket protocol, and all further communication uses WebSocket framing (RFC 6455, Sections 1.2-1.3).

```
Client:
GET /chat HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13

Server:
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

**SSE** uses a standard HTTP GET request. The client creates an `EventSource` object pointing at a URL, the browser issues a normal HTTP request, and the server responds with `Content-Type: text/event-stream` and a `200 OK` status. The connection remains open as a long-lived HTTP response. There is no protocol switch -- it remains HTTP throughout (WHATWG HTML Living Standard, Section 9.2.2).

```
Client: GET /events HTTP/1.1
Server: HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

data: Hello, world
```

#### Data Format and Framing

**WebSocket** uses a binary framing protocol. Messages are composed of one or more frames, each beginning with a 2-14 byte header indicating the frame type (text/binary/control), whether the message is masked, and the payload length. Client-to-server frames are masked with a 32-bit masking key to prevent cache poisoning attacks on intermediaries (RFC 6455, Section 5.2). The protocol supports text frames (UTF-8), binary frames (arbitrary data), and control frames (close, ping, pong). Messages can be fragmented across multiple frames (RFC 6455, Section 5.4).

**SSE** uses a plain-text format, always encoded as UTF-8. Events are delineated by blank lines (double newline). Each event consists of field-value pairs:
- `data:` -- the event payload
- `event:` -- a custom event type name (defaults to "message")
- `id:` -- a unique event identifier used for reconnection
- `retry:` -- server-specified reconnection timeout in milliseconds
- Lines beginning with `:` are comments (useful as keep-alive heartbeats)

(WHATWG HTML Living Standard, Section 9.2.5; MDN "Using server-sent events")

#### Connection Management and Reconnection

**WebSocket** has a defined closing handshake: either peer sends a Close control frame, the other responds with a Close frame, and the underlying TCP connection is closed (RFC 6455, Section 1.4). The WebSocket API does not provide automatic reconnection -- if the connection drops, application code must detect the closure (via the `onclose` event) and re-establish the connection manually.

**SSE** includes automatic reconnection as a core feature. When the connection is lost, the browser automatically attempts to reconnect after a default interval (typically ~3 seconds), which the server can control via the `retry:` field. On reconnection, the browser sends a `Last-Event-ID` HTTP header containing the ID of the last received event, allowing the server to replay any missed events (WHATWG HTML Living Standard, Sections 9.2.3-9.2.4; web.dev, "Stream updates with server-sent events"). The server can permanently terminate the connection by responding with HTTP 204 No Content.

#### Data Types

**WebSocket** supports both UTF-8 text and arbitrary binary data (RFC 6455, Section 5.6). This makes it suitable for streaming binary protocols, file transfers, or any data format.

**SSE** only supports UTF-8 text data. Binary data must be encoded (e.g., as Base64) before transmission, which adds overhead (WHATWG HTML Living Standard, Section 9.2.5).

### 3.2 Browser Support

As of January 2026 (Can I Use data via StatCounter GlobalStats):

| Feature | Global Support | Chrome | Firefox | Safari | Edge | IE |
|---------|---------------|--------|---------|--------|------|----|
| **WebSocket** | 96.76% | 16+ | 11+ | 7+ | 12+ | 10-11 |
| **SSE (EventSource)** | 96.44% | 6+ | 6+ | 5+ | 79+ (Chromium) | Never supported |

Key observations:

- **WebSocket** has been supported in all major browsers for over a decade. Even Internet Explorer supported it from version 10 (2012). Early implementations (Chrome 4-14, Firefox 4-10, Safari 5-6.1) had partial support using older protocol drafts.
- **SSE** was never supported in any version of Internet Explorer or in legacy Edge (pre-Chromium, versions 12-18). For legacy IE/Edge scenarios, polyfills exist (e.g., the Yaffle EventSource polyfill). Since Edge moved to Chromium (version 79+, January 2020), SSE is universally supported in all actively updated browsers.
- **Opera Mini** supports neither technology.
- **Mobile**: Both technologies are widely supported on mobile browsers. WebSocket support on Android Browser started with 4.4; SSE support on Safari iOS started at version 4.

For any modern application that does not need to support Internet Explorer, both technologies have equivalent, near-universal browser support.

### 3.3 Scalability Trade-offs

#### Connection Overhead

**WebSocket** maintains a persistent TCP connection for each client. After the initial HTTP handshake, the protocol overhead per message is minimal (2-14 bytes of framing), making it highly efficient for high-frequency messaging. However, each connection consumes a TCP socket on the server, and the connection is "upgraded" away from HTTP, meaning it cannot benefit from standard HTTP caching, CDN, or load balancing infrastructure without specialized support (RFC 6455, Section 1.7).

**SSE** also maintains a persistent HTTP connection per client, but the connection remains a standard HTTP response. This means it works naturally with HTTP/2 multiplexing, CDNs, reverse proxies, and load balancers. However, the text-based format has higher per-message overhead than WebSocket's binary framing (each message includes field names like `data:` as text), and the unidirectional nature means client messages require separate HTTP requests.

#### The HTTP/1.1 Connection Limit Problem

A critical scalability concern for SSE over HTTP/1.1 is the browser's per-domain connection limit. Browsers limit the number of simultaneous HTTP/1.1 connections to a single domain to 6 (per the de facto industry consensus). Since each `EventSource` holds one connection open, a user with multiple tabs open to the same domain can quickly exhaust this limit, blocking all other HTTP traffic.

MDN's documentation explicitly warns: "When not used over HTTP/2, SSE suffers from a limitation to the maximum number of open connections, which can be especially painful when opening multiple tabs, as the limit is per browser and is set to a very low number (6). The issue has been marked as 'Won't fix' in Chrome and Firefox" (MDN, "Using server-sent events").

This is a per browser + domain limit, meaning 6 SSE connections across all tabs to `www.example1.com` and another 6 to `www.example2.com`.

**HTTP/2 largely eliminates this problem.** Under HTTP/2, multiple SSE streams are multiplexed over a single TCP connection as separate streams, with a negotiable limit (default 100 concurrent streams per connection) (MDN, "Using server-sent events"). Since HTTP/2 is now the dominant protocol for HTTPS connections, this historical limitation is less relevant in 2026 for applications served over HTTPS.

WebSocket connections are not subject to the HTTP/1.1 connection limit because they are "upgraded" out of HTTP. However, they still consume a TCP socket each.

#### HTTP/2 and HTTP/3 Considerations

**SSE and HTTP/2**: SSE benefits naturally from HTTP/2. Multiple SSE streams can share a single TCP connection via HTTP/2 multiplexing. This eliminates the connection limit issue and reduces TCP handshake and TLS negotiation overhead. No protocol changes are needed -- SSE works over HTTP/2 identically to HTTP/1.1 from the application perspective.

**WebSocket and HTTP/2**: RFC 8441 ("Bootstrapping WebSockets with HTTP/2", September 2018, authored by Patrick McManus of Mozilla) defines a mechanism to tunnel WebSocket connections over HTTP/2 streams using an Extended CONNECT method. This allows WebSocket connections to share a single TCP connection with other HTTP/2 traffic, providing the same multiplexing benefits. The server opts in by sending a `SETTINGS_ENABLE_CONNECT_PROTOCOL` parameter (RFC 8441, Sections 3-5). However, browser and server adoption of RFC 8441 has been gradual, and not all WebSocket server implementations or proxies support it.

#### Server Resource Consumption

Both technologies hold connections open, so the primary server-side scalability challenge is the same: managing a large number of concurrent long-lived connections. The key differences in practice are:

- **SSE servers** are standard HTTP servers, so existing HTTP infrastructure (process models, load balancers, health checks, etc.) works without modification. Many web frameworks support SSE natively or with minimal configuration.
- **WebSocket servers** require explicit WebSocket support. While major web servers and frameworks now support WebSocket, it is an additional capability that must be configured. Some hosting environments, WAFs, and reverse proxies may not support WebSocket or may require special configuration (MDN, "The WebSocket API").

#### Bandwidth Efficiency

For server-to-client push scenarios, SSE and WebSocket have comparable bandwidth usage -- both hold a connection open and send data as it becomes available. WebSocket has a slight edge in per-message overhead (binary framing headers of 2-14 bytes vs. SSE's text-based `data:` field names), but for typical message sizes this difference is negligible.

For bidirectional scenarios, WebSocket is significantly more efficient than SSE + separate HTTP requests, because each HTTP request carries full headers (cookies, authentication, etc.), whereas WebSocket messages have minimal framing.

### 3.4 API Design and Developer Experience

#### Client-Side API

The **WebSocket API** (`new WebSocket(url)`) provides event handlers for `open`, `message`, `error`, and `close`. Messages are sent via `ws.send(data)`. The API supports both text and binary (`ArrayBuffer`, `Blob`) data. MDN notes that a newer `WebSocketStream` API exists that integrates with the Streams API for backpressure handling, but it is currently non-standard and only supported in one rendering engine (MDN, "The WebSocket API").

The **EventSource API** (`new EventSource(url)`) provides event handlers for `open`, `message`, and `error`, plus the ability to listen for custom named events via `addEventListener()`. It is deliberately simple -- there is no send method because it is receive-only. The API automatically handles reconnection and event ID tracking (WHATWG HTML Living Standard, Section 9.2.2).

MDN also notes that the WebTransport API "is expected to replace the WebSocket API for many applications" in the future, offering backpressure, unidirectional streams, out-of-order delivery, and unreliable datagram transmission, though with more complexity and less mature browser support (MDN, "The WebSocket API").

#### Server-Side Implementation

**SSE servers** are trivial to implement in any language that can write HTTP responses. A minimal implementation sets `Content-Type: text/event-stream`, writes events in the prescribed text format, and flushes output. No special libraries are required. The web.dev article provides complete working examples in both PHP and Node.js/Express in under 20 lines each.

**WebSocket servers** require implementing the WebSocket handshake and binary framing protocol, which typically means using a dedicated library (e.g., `ws` for Node.js, `gorilla/websocket` for Go, Django Channels for Python). While mature libraries exist for every major language, there is a higher baseline implementation cost than SSE.

### 3.5 Security Considerations

**WebSocket** uses the Origin header during the handshake for the browser's same-origin check, but the server must explicitly validate it. The `Sec-WebSocket-*` headers prevent non-WebSocket HTTP clients from initiating connections. Client-to-server frames are masked to prevent cache poisoning of intermediary proxies (RFC 6455, Section 10). Authentication is typically handled via cookies sent during the handshake or via the first message after connection, since there is no standard mechanism to send custom headers during the WebSocket handshake from the browser API.

**SSE** operates over standard HTTP and benefits from the full HTTP security model: cookies, CORS, standard authentication headers, and TLS/HTTPS. CORS policies apply to EventSource requests in the same way as to fetch requests (web.dev, "Stream updates with server-sent events"). The `EventSource` constructor supports a `withCredentials` option for cross-origin requests with cookies (WHATWG HTML Living Standard, Section 9.2.2).

## 4. Analysis

### When to Choose SSE

SSE is the better choice when:

1. **The communication pattern is predominantly server-to-client.** News feeds, stock tickers, social media timeline updates, notification streams, live sports scores, log tailing, CI/CD build status, and AI/LLM token streaming are all natural fits for SSE. The client can still send data to the server via standard HTTP requests when needed.

2. **Simplicity is valued.** SSE requires no special server infrastructure, works with any HTTP server, and the client API is straightforward. The automatic reconnection with `Last-Event-ID` resumption is a significant convenience that WebSocket applications must implement manually.

3. **HTTP infrastructure compatibility matters.** SSE works through corporate proxies, CDNs, load balancers, and API gateways without any special configuration. This is a substantial practical advantage in enterprise environments.

4. **HTTP/2 is available.** With HTTP/2, the historical connection limit problem is eliminated, making SSE viable for applications with many concurrent streams.

### When to Choose WebSocket

WebSocket is the better choice when:

1. **True bidirectional, low-latency communication is required.** Chat applications, multiplayer games, collaborative editing (e.g., Google Docs-style real-time cursors), financial trading platforms with order submission, and interactive drawing applications all need both the client and server to send data frequently and with minimal latency.

2. **Binary data must be transmitted.** WebSocket natively supports binary frames, making it appropriate for streaming audio/video, binary protocols, or any scenario where encoding binary as Base64 text would be unacceptable overhead.

3. **Message frequency is very high in both directions.** When both client and server are sending dozens or hundreds of messages per second, the overhead of separate HTTP requests for the client-to-server direction (as SSE would require) becomes significant.

4. **Custom subprotocols are needed.** WebSocket's subprotocol negotiation mechanism (`Sec-WebSocket-Protocol` header) provides a standard way to layer application-specific protocols on top of WebSocket (RFC 6455, Section 1.9).

### The "SSE + HTTP POST" Pattern

A common middle ground is to use SSE for server-to-client push combined with regular HTTP POST/PUT requests for client-to-server communication. This is not a hack -- it is the design pattern SSE was intended for. It combines the simplicity and HTTP compatibility of SSE with the well-understood semantics of REST APIs for client-initiated operations. This pattern works well for applications like:

- Real-time dashboards where the server pushes metrics and the user occasionally changes configuration
- AI chat interfaces where the server streams token responses via SSE and the client submits prompts via HTTP POST
- Notification systems where the server pushes alerts and the client marks them as read via HTTP PATCH

### Looking Forward: WebTransport

MDN's documentation on the WebSocket API notes that "the WebTransport API is expected to replace the WebSocket API for many applications." WebTransport, built on HTTP/3 and QUIC, offers features neither WebSocket nor SSE can match: unreliable datagram delivery (for gaming/media), multiple simultaneous unidirectional and bidirectional streams, built-in backpressure via the Streams API, and lower connection establishment latency. As of early 2026, WebTransport has narrower browser support than either WebSocket or SSE, but it represents the likely long-term evolution of real-time web communication.

## 5. Open Questions & Gaps

1. **Quantitative performance benchmarks.** Authoritative, recent (2024-2026) benchmarks comparing WebSocket and SSE throughput, latency, and memory consumption under controlled conditions are surprisingly scarce in the public literature. Most performance claims in blog posts and articles are anecdotal or based on synthetic microbenchmarks that may not reflect real-world conditions. A rigorous comparison accounting for HTTP/2 SSE multiplexing vs. RFC 8441 WebSocket-over-HTTP/2 would be valuable.

2. **RFC 8441 adoption.** The extent to which browsers, servers, and intermediaries have adopted WebSocket-over-HTTP/2 (RFC 8441) and its HTTP/3 equivalent is not well documented. Without widespread adoption, WebSocket connections may still require dedicated TCP connections even when the rest of the application uses HTTP/2 or HTTP/3.

3. **SSE connection limits in practice.** While the HTTP/2 specification negotiates a default of 100 concurrent streams, the real-world behavior of browsers and servers with many SSE streams on a single HTTP/2 connection (e.g., dozens of `EventSource` instances) has limited public documentation.

4. **WebSocket backpressure.** MDN notes that the standard `WebSocket` interface "doesn't support backpressure" -- "when messages arrive faster than the application can process them it will either fill up the device's memory by buffering those messages, become unresponsive due to 100% CPU usage, or both." The `WebSocketStream` API addresses this but remains non-standard. SSE has no formal backpressure mechanism either, but its simpler unidirectional model may make this less critical in practice.

5. **Mobile battery and network impact.** The WHATWG specification mentions that SSE's design enables "push proxy" optimizations on mobile networks that can result in "significant savings in battery life on portable devices" (WHATWG HTML Living Standard, Section 9.2.8). Whether modern mobile browsers and carriers actually implement such optimizations is unclear.

6. **Edge cases with intermediaries.** Both technologies can encounter problems with certain proxies, firewalls, and network middleware. Anecdotal reports suggest SSE can be disrupted by proxies that buffer HTTP responses (the WHATWG spec warns about HTTP chunking issues in Section 9.2.7), while WebSocket can be blocked by firewalls that don't recognize the Upgrade handshake. Systematic data on these failure modes across different enterprise network configurations is lacking.

## 6. Sources

1. **RFC 6455 -- The WebSocket Protocol** (December 2011). Fette, I. and A. Melnikov. IETF Standards Track. https://datatracker.ietf.org/doc/html/rfc6455

2. **RFC 8441 -- Bootstrapping WebSockets with HTTP/2** (September 2018). McManus, P. IETF Standards Track. https://datatracker.ietf.org/doc/html/rfc8441

3. **WHATWG HTML Living Standard -- Section 9.2: Server-sent events** (Last updated February 27, 2026). https://html.spec.whatwg.org/multipage/server-sent-events.html

4. **MDN Web Docs -- The WebSocket API (WebSockets)** (Last modified December 15, 2025). Mozilla Contributors. https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API

5. **MDN Web Docs -- Server-sent events** (Last modified March 20, 2025). Mozilla Contributors. https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events

6. **MDN Web Docs -- Using server-sent events** (Last modified May 15, 2025). Mozilla Contributors. https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events

7. **Can I Use -- Web Sockets** (January 2026 data). https://caniuse.com/websockets

8. **Can I Use -- Server-sent events** (January 2026 data). https://caniuse.com/eventsource

9. **web.dev -- Stream updates with server-sent events** (Updated 2010, content reviewed 2024). Eric Bidelman. https://web.dev/articles/eventsource-basics

10. **RFC 6202 -- Known Issues and Best Practices for the Use of Long Polling and Streaming in Bidirectional HTTP**. Referenced in RFC 6455 as motivation for the WebSocket protocol. https://datatracker.ietf.org/doc/html/rfc6202
