## Goal

Produce a comprehensive, standalone research report comparing WebSocket and Server-Sent Events (SSE) for real-time web applications, covering:
- Protocol differences
- Browser support
- Scalability trade-offs
- When to choose each

The report must follow the exact structure from the instruction file and be evidence-based with inline citations and sources list.

## Instructions

- User-provided task file to follow: `/Users/auk000v/dev/tools/ivory-tower-gepa-fixes/research/20260302-083944-8642c7/phase1/20260302-083944-8642c7/prompt.md`
- Must use web search extensively and prioritize authoritative / primary sources (RFCs, official specs, vendor docs, standards bodies).
- Prefer recent sources (last 2 years where relevant).
- Every nontrivial claim needs a source citation.
- If findings conflict, present both sides with sources.
- Report must be in five+ sections: Executive Summary, Background & Context, Key Findings (theme-based), Analysis, Open Questions & Gaps, Sources.
- Depth should be substantial (substantive prose, not bullet-only).

## Discoveries

- Task scope is a write-up task (no coding yet), centered on **WebSocket vs SSE**.
- Source mix pulled so far gives:
  - Standards-level protocol definitions:  
    - RFC 6455 (WebSocket protocol)  
    - RFC 8441 (WebSockets over HTTP/2 via extended CONNECT)
  - Browser/API docs and implementation behavior:
    - MDN WebSocket API
    - MDN EventSource/Server-sent events API pages
    - MDN Using server-sent events guide
    - WHATWG HTML SSE sections (EventSource interface, processing model, reconnection, parsing, etc.)
  - Practical/proxy behavior:
    - NGINX WebSocket proxying guide + `ngx_http_proxy_module` (including upgrade/headers and timeouts)
  - Deployment constraints and limits:
    - Cloudflare Workers WebSockets API docs + Worker platform limits (notably connections/subrequests/simultaneous open connections)
    - Cloudflare Workers limits page gives useful quotas relevant to long-lived SSE/WebSocket usage
    - AWS ALB target group docs (HTTP/2/gRPC and routing behavior; output was long and partially truncated but includes useful request routing context)
  - Browser support snapshots:
    - Can I Use pages for WebSockets and SSE (global support percentages, per-browser tables)
- Additional practical points already observed from sources:
  - SSE is inherently one-way (server→client), EventSource reconnect behavior, UTF-8 stream format, reconnection semantics.
  - WebSocket is bidirectional, lower-level framing, binary/text messages, subprotocols/extensions, masking, close handling.
  - MDN mentions WebSocket lacks backpressure support while Stream-based alternatives do.
  - Cloudflare and Nginx docs confirm operational constraints can dominate protocol choice (connection limits, header behavior, proxy config).
- Some fetched pages were long and truncated by tool output; full content saved in tool cache files if needed for deeper quoting.
- No edits or code changes have been made in the repository yet.

## Accomplished

- ✅ Read and extracted the user’s governing task instructions from `prompt.md`.
- ✅ Collected a wide set of references across standards, browser docs, compatibility tables, and infra platform docs.
- ✅ Confirmed required section structure and sourcing expectations.
- 🔄 Not yet generated the final written report itself.
- ⏳ Remaining work:
  - Synthesize findings into required sections with balanced analysis.
  - Add explicit protocol-comparison insights (handshake flow, transport layers, directionality, reconnection, security, proxies, scaling).
  - Include scalability trade-off matrix and “when to choose” recommendations.
  - Add open questions/gaps with unresolved or conflicting evidence.
  - Compile clean source list with URLs/refs.

## Relevant files / directories

- ` /Users/auk000v/dev/tools/ivory-tower-gepa-fixes/research/20260302-083944-8642c7/phase1/20260302-083944-8642c7/prompt.md`  
  - Primary instruction file already read and followed.
- Working files currently modified/created: **none** (no repository writes yet).
- External captured web fetch artifacts (tool cache, for reference only):  
  - `/Users/auk000v/.local/share/opencode/tool-output/` (multiple files with full fetched content for truncated pages).
