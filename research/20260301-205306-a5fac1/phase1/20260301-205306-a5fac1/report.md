# WebSocket vs Server-Sent Events (SSE) for Real-Time Web Applications

## Executive Summary

WebSocket and Server-Sent Events (SSE) are the two primary technologies for delivering real-time data from servers to web clients. WebSocket provides full-duplex bidirectional communication over a single TCP connection using a custom protocol. SSE provides unidirectional server-to-client streaming over standard HTTP. The right choice depends on whether the application requires bidirectional communication, the infrastructure constraints, and scalability needs.

---

## 1. Protocol Differences

### 1.1 WebSocket

WebSocket is defined by **RFC 6455** (December 2011) and the **WHATWG WebSockets Living Standard**. It is an independent TCP-based protocol whose only relationship to HTTP is that its handshake is interpreted by HTTP servers as an Upgrade request. [Source: RFC 6455, Section 1.7]

**Connection lifecycle:**

1. The client sends an HTTP GET request with `Upgrade: websocket` and `Connection: Upgrade` headers, along with a `Sec-WebSocket-Key` nonce.
2. The server responds with HTTP 101 Switching Protocols, including a `Sec-WebSocket-Accept` header derived from the client's key.
3. After the handshake, the connection is "upgraded" -- it is no longer HTTP. Both sides can send data independently at any time over a single TCP connection.
4. Either peer can initiate a closing handshake via a Close control frame.

[Source: RFC 6455, Sections 1.2-1.4]

**Data framing:** Messages are composed of one or more frames. Frame types include text (UTF-8), binary, and control frames (Close, Ping, Pong). Client-to-server frames are masked (XOR with a 32-bit key) to prevent cache poisoning attacks on intermediaries. [Source: RFC 6455, Section 5]

**Protocol characteristics:**
- Uses `ws://` (port 80) and `wss://` (port 443) URI schemes
- Full-duplex: both client and server can send messages independently at any time
- Binary and text data supported
- Supports subprotocols and extensions negotiated during handshake
- No built-in reconnection logic -- applications must implement this themselves
- No native message ID or replay mechanism

### 1.2 Server-Sent Events (SSE)

SSE is defined in the **WHATWG HTML Living Standard, Section 9.2**. It is not a new protocol -- it runs over standard HTTP using the `text/event-stream` MIME type. [Source: WHATWG HTML Spec, Section 9.2]

**Connection lifecycle:**

1. The client creates an `EventSource` object, which opens a standard HTTP GET request to a URL.
2. The server responds with `Content-Type: text/event-stream` and a `200 OK` status.
3. The server streams events as UTF-8 encoded text, with events delimited by double newlines (`\n\n`).
4. If the connection drops, the browser automatically reconnects (with configurable retry delay and `Last-Event-ID` header).

[Source: WHATWG HTML Spec, Section 9.2.2-9.2.3]

**Event stream format (ABNF):**
```
stream = [ bom ] *event
event  = *( comment / field ) end-of-line
field  = 1*name-char [ colon [ space ] *any-char ] end-of-line
```

Fields: `data`, `event` (custom event type), `id` (event ID for reconnection), `retry` (reconnection time in ms). Comments (lines starting with `:`) can be used as keep-alive pings.

[Source: WHATWG HTML Spec, Section 9.2.5]

**Protocol characteristics:**
- Uses standard HTTP/HTTPS (no protocol upgrade)
- Unidirectional: server-to-client only
- Text only (UTF-8); binary data must be Base64-encoded
- Built-in automatic reconnection with `Last-Event-ID` header for missed-message recovery
- Built-in event typing (`event` field)
- Server-controlled reconnection timing (`retry` field)

### 1.3 Head-to-Head Protocol Comparison

| Feature | WebSocket | SSE |
|---|---|---|
| Direction | Full-duplex (bidirectional) | Unidirectional (server → client) |
| Underlying protocol | Custom TCP-based (RFC 6455) | Standard HTTP |
| Data format | Text (UTF-8) + Binary | Text (UTF-8) only |
| Connection setup | HTTP Upgrade handshake → protocol switch | Standard HTTP request |
| Framing | Binary frames with opcodes | Text-based `field: value\n\n` |
| Auto-reconnect | No (must implement manually) | Yes (built-in with `Last-Event-ID`) |
| Message IDs | No (application layer) | Yes (built-in `id` field) |
| Keep-alive | Ping/Pong control frames | Comment lines (`:` prefix) |
| Compression | Per-message deflate extension (RFC 7692) | Standard HTTP compression (gzip, etc.) |

---

## 2. Browser Support

### 2.1 WebSocket

As of January 2026, WebSocket has **96.76% global browser support** per Can I Use data.

- **Chrome:** Supported since v16 (full), partial since v4
- **Firefox:** Supported since v11, partial from v4-10
- **Safari:** Supported since v7, partial from v5-6.1
- **Edge:** Supported since v12 (including legacy Edge)
- **IE:** Supported in IE 10-11
- **Opera Mini:** Not supported
- **Mobile:** Supported across Chrome Android, Safari iOS (v6+), Samsung Internet, Firefox Android

[Source: Can I Use - WebSockets, January 2026]

### 2.2 Server-Sent Events (EventSource)

SSE has **96.44% global browser support** as of January 2026.

- **Chrome:** Supported since v6
- **Firefox:** Supported since v6
- **Safari:** Supported since v5
- **Edge:** Supported since v79 (Chromium-based). **Not supported in legacy Edge (v12-18) or IE 11.**
- **IE:** Not supported in any version
- **Opera Mini:** Not supported
- **Mobile:** Supported across Chrome Android, Safari iOS (v4+), Samsung Internet, Firefox Android

[Source: Can I Use - EventSource, January 2026]

### 2.3 Key Difference

The critical gap is **Internet Explorer** and **legacy Edge**: WebSocket works in IE 10/11 and legacy Edge, while SSE does not. In 2026, this matters only for enterprise environments still running legacy browsers. Polyfills exist for SSE (e.g., Yaffle/EventSource) that can bridge this gap using XHR-based long polling. For modern browsers, both technologies have near-universal support.

WebSocket is also available in **Web Workers**; SSE via EventSource is similarly available in Web Workers. [Source: MDN WebSocket API; MDN Server-sent events]

---

## 3. Scalability Trade-offs

### 3.1 Connection Costs

**WebSocket:**
- Each WebSocket connection is a persistent TCP connection that exists outside of standard HTTP. Since it is not HTTP after the handshake, **WebSocket connections are NOT multiplexed over HTTP/2**. Each WebSocket connection is a separate TCP connection. [Source: Smashing Magazine - Martin Chaov, 2018]
- 50 WebSocket connections from a single page = 50 TCP connections. 10 browser tabs with 50 sockets each = 500 connections. This can create serious load balancing challenges.
- Thread-based servers need a thread per connection (or use event-loop architectures). At scale, the memory footprint of maintaining open sockets becomes the bottleneck.
- WebSocket connections must be maintained on both server and client. Moving socket connections during load balancing (e.g., scaling out) requires closing and reopening connections, potentially triggering reconnection storms.

**SSE:**
- SSE connections are standard HTTP connections. Over **HTTP/2, they are automatically multiplexed** -- multiple SSE streams to the same domain share a single TCP connection. This is a significant advantage.
- Over HTTP/1.1, SSE is subject to the **browser per-domain connection limit of 6 concurrent connections**. This is per browser + domain. Opening multiple tabs each with their own EventSource can exhaust this limit. This has been marked "Won't fix" in both Chrome and Firefox. [Source: MDN - Using server-sent events; Chrome bug 275955; Firefox bug 906896]
- Over HTTP/2, this limitation disappears. The max simultaneous HTTP streams is negotiated between client and server (default 100). [Source: MDN - Using server-sent events]
- Workarounds for HTTP/1.1 limits: use unique subdomains per connection, share a single EventSource via a SharedWorker, or allow users to toggle EventSource per tab.

### 3.2 Infrastructure Compatibility

**WebSocket:**
- Requires TCP proxies rather than HTTP proxies. TCP proxies cannot inject headers, rewrite URLs, or perform typical HTTP proxy functions. [Source: Smashing Magazine, 2018]
- Some corporate proxies, firewalls, and ISPs may block WebSocket connections, especially over `ws://` (unencrypted). Using `wss://` (TLS) significantly improves connection success rates. [Source: RFC 6455, Section 1.8]
- Load balancing is more complex -- sticky sessions or connection-aware routing is needed.
- DoS protection is harder because front-end HTTP proxies cannot handle WebSocket traffic; TCP-level proxies must be used instead.

**SSE:**
- Works over standard HTTP, so it is fully compatible with existing HTTP infrastructure: load balancers, CDNs, reverse proxies (NGINX, HAProxy), firewalls, and HTTP caches.
- NGINX can proxy SSE endpoints and provide HTTP/2, SSL termination, and load balancing -- all from a standard HTTP proxy configuration.
- Legacy proxy servers may drop long-lived idle connections. Mitigation: send comment lines (`:`) every ~15 seconds as keep-alive. [Source: WHATWG HTML Spec, Section 9.2.7]
- HTTP chunking by intermediate layers unaware of SSE timing can cause delays. Mitigation: disable chunked transfer encoding for SSE endpoints. [Source: WHATWG HTML Spec, Section 9.2.7]

### 3.3 Bandwidth and Overhead

**WebSocket:**
- After the initial handshake, frame overhead is minimal: 2-14 bytes per frame (depending on payload size and masking).
- No per-message HTTP headers -- this is a significant bandwidth savings for high-frequency small messages.
- Supports binary data natively, avoiding Base64 encoding overhead.

**SSE:**
- Each message carries the `data:`, `id:`, `event:` field prefixes as text overhead. For small payloads, this is still very lightweight.
- Runs over HTTP, so standard HTTP compression (gzip, Brotli) applies to the stream automatically.
- Binary data must be Base64-encoded (33% overhead), or sent via a separate HTTP endpoint.
- However, because SSE multiplexes over HTTP/2, the aggregate TCP connection overhead (memory, OS file descriptors) is much lower.

### 3.4 Mobile and Battery

Both WebSocket and SSE keep a persistent TCP connection alive, which on mobile networks requires the full-duplex radio antenna to remain active, drawing battery power.

SSE has a specification-level advantage here: the WHATWG spec describes a "connectionless push" model where mobile user agents can offload the SSE connection to a network push proxy. The browser disconnects, the push proxy maintains the server connection, and uses technologies like OMA Push to wake the device only when an event arrives. This can result in "considerable power savings." [Source: WHATWG HTML Spec, Section 9.2.8]

WebSocket has no equivalent specification-level power optimization mechanism.

### 3.5 Backpressure

WebSocket's standard `WebSocket` interface does not support backpressure. If messages arrive faster than the application can process them, memory will fill up or CPU will be saturated. The newer `WebSocketStream` interface (non-standard, Chrome only) addresses this using the Streams API, but it is not widely supported. [Source: MDN - WebSocket API]

SSE, being HTTP-based, benefits from HTTP/2 flow control for stream-level backpressure. The client processing speed naturally throttles the TCP receive window.

---

## 4. When to Choose Each

### Choose WebSocket when:

1. **Bidirectional communication is required.** Chat applications, multiplayer games, collaborative editing (e.g., Google Docs-style), and any scenario where the client frequently sends data to the server benefit from WebSocket's full-duplex channel. Sending client messages over a separate HTTP request while receiving via SSE adds complexity and latency.

2. **Binary data transfer is needed.** If you need to stream binary data (audio, video frames, protocol buffers) between client and server, WebSocket handles this natively. SSE is text-only.

3. **Minimal per-message overhead matters at extreme scale.** For very high-frequency messaging (thousands of messages per second per connection), WebSocket's 2-14 byte frame overhead is smaller than SSE's text-based field format.

4. **You control the infrastructure.** If you can configure proxies, load balancers, and firewalls to support WebSocket, the infrastructure concerns are manageable.

### Choose SSE when:

1. **Data flows primarily server-to-client.** Stock tickers, live sports scores, news feeds, notification systems, CI/CD build status, AI/LLM token streaming -- any application where the server pushes updates and the client rarely sends data. Client actions can be sent via standard HTTP requests (POST/PUT).

2. **You need HTTP/2 multiplexing.** If you have many independent data streams (e.g., widgets on a dashboard), SSE over HTTP/2 multiplexes them into a single TCP connection automatically. WebSocket would require one TCP connection per stream, or custom multiplexing logic.

3. **Infrastructure compatibility is a priority.** SSE works with standard HTTP infrastructure -- CDNs, reverse proxies, load balancers, firewalls -- without special configuration. This is particularly important in corporate environments or when deploying behind infrastructure you don't control.

4. **Automatic reconnection with message recovery is valuable.** SSE's built-in `Last-Event-ID` reconnection mechanism means you get fault-tolerant streaming for free. With WebSocket, you must implement reconnection, message buffering, and replay logic yourself.

5. **Mobile battery optimization matters.** SSE's specification allows for push-proxy offloading that can significantly reduce battery consumption on mobile devices.

6. **Simplicity is valued.** SSE has a simpler programming model on both client and server. The server writes text to an HTTP response; the client uses the `EventSource` API. There are no handshake negotiations, no frame masking, and no custom close sequences.

### The Modern Trend: SSE + HTTP/2

A notable pattern in modern web architecture (2024-2026) is the adoption of SSE over HTTP/2 for applications previously assumed to need WebSocket. The combination provides:
- Multiplexed streams over a single connection
- Full HTTP infrastructure compatibility
- Built-in reconnection and recovery
- Standard compression
- Simpler implementation and operations

This has been adopted by OpenAI's streaming API, Anthropic's Messages API, and many other AI/LLM services for streaming token responses. The client sends a request via standard HTTP POST, then receives the streamed response as SSE events. [Note: this is a widely observed industry pattern, not attributable to a single source.]

---

## 5. Emerging Alternative: WebTransport

The **WebTransport API** is a newer technology expected to eventually replace WebSocket for many use cases. Built on HTTP/3 and QUIC, it provides:
- Bidirectional streams
- Unidirectional streams
- Unreliable datagram delivery
- Stream-level backpressure
- Multiplexing without head-of-line blocking

However, as of early 2026, WebTransport's cross-browser support is not as broad as WebSocket or SSE, and the API is more complex. MDN recommends: "If standard WebSocket connections are a good fit for your use case and you need wide browser compatibility, you should employ the WebSockets API. However, if your application requires a non-standard custom solution, then you should use the WebTransport API." [Source: MDN - WebSocket API]

---

## 6. Research Gaps

- **Quantitative benchmarks:** I could not find rigorous, recent (2024-2026) benchmark studies comparing WebSocket vs SSE throughput, latency, and memory usage under identical conditions at scale. Most comparisons are qualitative or from 2018 or earlier.
- **HTTP/3 impact on SSE:** How SSE performs over HTTP/3 (QUIC) vs HTTP/2 is not well documented yet.
- **Push proxy implementations:** The WHATWG spec describes a "connectionless push" model for mobile SSE, but I found no evidence of real-world browser implementations or carrier adoption of this feature. It may remain theoretical.
- **WebSocketStream adoption:** The non-standard `WebSocketStream` interface (backpressure-aware WebSocket) is only in Chrome. Its trajectory toward standardization is unclear.

---

## Sources

1. **RFC 6455 - The WebSocket Protocol** (December 2011). IETF.
   https://datatracker.ietf.org/doc/html/rfc6455

2. **WHATWG HTML Living Standard, Section 9.2 - Server-sent events** (Last updated February 2026).
   https://html.spec.whatwg.org/multipage/server-sent-events.html

3. **MDN Web Docs - The WebSocket API (WebSockets)** (Last modified December 15, 2025).
   https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API

4. **MDN Web Docs - Server-sent events** (Last modified March 20, 2025).
   https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events

5. **MDN Web Docs - Using server-sent events** (Last modified May 15, 2025).
   https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events

6. **Can I Use - Web Sockets** (January 2026 data). 96.76% global support.
   https://caniuse.com/websockets

7. **Can I Use - Server-sent events** (January 2026 data). 96.44% global support.
   https://caniuse.com/eventsource

8. **Martin Chaov, "Using SSE Instead Of WebSockets For Unidirectional Data Flow Over HTTP/2"** (February 12, 2018). Smashing Magazine.
   https://www.smashingmagazine.com/2018/02/sse-websockets-data-flow-http2/

9. **WHATWG WebSockets Living Standard**.
   https://websockets.spec.whatwg.org/

10. **Chrome Bug 275955** - SSE connection limit marked "Won't fix".
    https://crbug.com/275955

11. **Firefox Bug 906896** - SSE connection limit marked "Won't fix".
    https://bugzil.la/906896
