# 02 · Architecture

> One process, two concerns. The browser talks only to Next.js `/api/*`, which rewrites to the FastAPI backend. The same backend process also serves the concierge LLM endpoint at `/llm`, which Agora cloud calls directly over a public tunnel.

## Topology

```
Browser (localhost:3000)
  │  fetch /api/*
  ▼
Next.js (web/)  ──rewrite──▶  Agent backend (server/, :8000)
                                 │  builds agent session with CustomLLM vendor
                                 ▼
                              Agora ConvoAI Cloud
                                 │  user speech → Deepgram STT (managed)
                                 │  POST <CUSTOM_LLM_URL>   (Authorization: Bearer)
                                 ▼
                              Concierge LLM endpoint  (mounted at /llm in server/, :8000)
                                 │  public via ngrok tunnel
                                 │  derive_persona() → persona handler
                                 │  reads/writes SQLite itinerary.db
                                 │  streams OpenAI SSE reply (no tool_call chunks)
                                 ▼
                              Agora ConvoAI Cloud → MiniMax TTS (managed) → user hears speech
                                                  → RTM transcript / metrics → web UI
```

- **`web/`** — Next.js 16 / React 19 / TypeScript. Owns UI plus the RTC/RTM client lifecycle. Calls only `/api/*`.
- **`server/`** — Python FastAPI (:8000). Owns Agora token generation and agent session lifecycle. SDK: `agora-agents>=2.3.0` (`import agora_agent`). Also mounts the concierge LLM endpoint at `/llm`.
- **`server/src/llm.py`** — provider-agnostic OpenAI-compatible endpoint; no `agora_agent` import. The component you replace with your own model.

## Request lifecycle

1. Browser `GET /api/get_config` → Next rewrites to backend `/get_config`; backend mints a Token007 and returns channel + UIDs.
2. Browser joins the RTC channel, then `POST /api/startAgent`; backend builds a `CustomLLM` vendor pointed at `CUSTOM_LLM_URL`, an STT (`DeepgramSTT nova-3`), and a TTS (`MiniMaxTTS`), then starts an async agent session.
3. User speaks. Agora runs STT, then `POST <CUSTOM_LLM_URL>/chat/completions` to the mounted concierge endpoint.
4. `run_agent_turn()` calls `derive_persona()` — `trip_support` if a booking row exists in SQLite, `booking` if booking keywords are present, else `triage`. The handler streams only the spoken reply in OpenAI SSE format. Agora cloud never sees a `tool_call`.
5. Agora runs TTS (MiniMax) and plays it back. RTM delivers transcript + metrics to the web UI.
6. `POST /api/stopAgent { agentId }` ends the session.

## One process, two concerns

`server.py` imports `llm.app` and mounts it at `/llm`. The dependency is one-directional: `server.py` imports `llm`, never the reverse. `llm.py` has no `agora_agent` import — it is the provider-agnostic part you replace.

Co-locating makes the public `/llm` route reachable at the same port as token endpoints. The App Certificate is only used in-memory to mint tokens and never crosses a wire. Token endpoints are unauthenticated — add auth/rate-limiting before any real deployment.

## The persona handoff FSM

`derive_persona(conn, user_text)` inspects two signals per turn (no session id, no stored persona field):

1. **SQLite itinerary state** — if a booking row exists → `trip_support`.
2. **Intent keywords** — if booking keyword found → `booking`.
3. Otherwise → `triage`.

A pending destination is cached in a `context` table (key `pending_dest`) between turns so multi-turn booking flows work.

## Key abstractions

- **`Agent`** (`server/src/agent.py`) — async wrapper around `AgoraAgent`; builds the `CustomLLM` + STT + TTS vendor chain, owns the `AsyncAgora` client, and the in-memory `_sessions` map keyed by `agent_id`.
- **`run_agent_turn(conn, messages)`** (`server/src/llm.py`) — top-level FSM dispatcher; materialises the reply before the SSE generator streams it.
- **Rewrite proxy** (`web/next.config.ts`) — the only browser→backend boundary; no Next Route Handlers for agent/token logic.

## Tech decisions

- **Rewrites, not Route Handlers** — hides backend placement behind `/api/*`.
- **Single process, two mounts** — avoids a second process while keeping `llm.py` agora-free and replaceable.
- **Zero-key mock** — no external LLM key needed; replace `llm.py` with a real model when ready.
- **Stateless persona derivation** — persona derived fresh every turn; restart-safe and testable in isolation.

## Related Deep Dives

- [handoff_flow](L2/handoff_flow.md) — full persona FSM, SQLite schema, derive/dispatch path, and SSE streaming contract.
- [session_lifecycle](L2/session_lifecycle.md) — browser orchestration of config + start/stop, RTC/RTM, transcript mapping.
