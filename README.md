# Agora Conversational AI — Agent Handoff Recipe (Python)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](https://www.python.org/)
[![Bun](https://img.shields.io/badge/bun-latest-black)](https://bun.sh/)

The **agent-handoff** recipe in the Agora Conversational AI recipes family. It
demonstrates a **3-persona Travel Concierge** that transitions automatically
between **Triage → Booking → Trip Support** as the conversation progresses:

- **Triage** — greets the user and determines destination intent.
- **Booking** — presents deterministic flight options and books the chosen one.
- **Trip Support** — manages the confirmed trip (show, change, or cancel).

The active persona is derived on every turn from the user's intent keywords and
the contents of a local SQLite itinerary database — there is no session id and
no stored persona field. The trip persists across restarts (SQLite). Agora cloud
never sees a `tool_call`; the persona logic lives entirely inside the `llm/`
endpoint.

STT (Deepgram nova-3) and TTS (MiniMax) stay Agora-managed. This repo ships a
**zero-key mock** LLM endpoint so the full pipeline runs immediately without an
LLM API key.

## Prerequisites

- [Python 3.10+](https://www.python.org/)
- [Bun](https://bun.sh/)
- [Agora CLI](https://github.com/AgoraIO/cli) — makes generating an App ID + App Certificate easy
- [ngrok](https://ngrok.com/) — the mock LLM endpoint must be publicly reachable so Agora cloud can call it

## Run It

```bash
# 1. Install + create both Python venvs
bun run setup

# 2. Add Agora credentials (CLI), or edit server/.env.local by hand
agora login
agora project use <your-project>          # select which project to use
agora project env write server/.env.local # writes App ID/Certificate

# 3. Expose the concierge LLM endpoint publicly (Agora cloud calls it directly)
ngrok http 8001

# 4. Add the tunnel URL to server/.env.local
#    CUSTOM_LLM_URL=https://<your-tunnel>.ngrok-free.dev/chat/completions

# 5. Run all three services
bun run dev
```

Open [http://localhost:3000](http://localhost:3000) → **Start Conversation** → speak.

Try: "I want to fly to Paris" → "book the morning one" → "what's my itinerary"
→ "cancel my trip".

### Working from a clone

`bun run setup` creates both Python venvs and installs web dependencies.
`bun run dev` brings up all three services. You still need Agora credentials in
`server/.env.local` and a public `CUSTOM_LLM_URL` before a conversation can connect.

Services:

- Frontend — http://localhost:3000
- Backend — http://localhost:8000
- API docs — http://localhost:8000/docs

## Deploy

Deploy `web` (Next.js), `server` (a reachable FastAPI backend), and `llm` (a
publicly reachable FastAPI endpoint). Set `AGENT_BACKEND_URL` in the web
deployment so Next rewrites reach the backend.

## Environment variables

Backend env file: [`server/.env.example`](server/.env.example).

| Variable | Required | Default | Notes |
| --- | :---: | :---: | --- |
| `AGORA_APP_ID` | ✅ | — | Agora Console → Project → App ID |
| `AGORA_APP_CERTIFICATE` | ✅ | — | Agora Console → Project → App Certificate (server only) |
| `CUSTOM_LLM_URL` | ✅ | — | **Public** chat-completions URL of your `llm/` endpoint. Agora cloud calls it; cannot be `localhost`. |
| `CUSTOM_LLM_API_KEY` | ✅ | `any-key-here` | Forwarded by Agora cloud as `Authorization: Bearer`. Required by the `CustomLLM` vendor. |
| `CUSTOM_LLM_MODEL` |  | `handoff-mock` | Model name passed to your endpoint |
| `AGENT_GREETING` |  | built-in | Optional opening line override |
| `PORT` |  | `8000` | Agent backend port |
| `CUSTOM_LLM_PORT` |  | `8001` | Port for the concierge LLM endpoint — lives in **`llm/.env.local`**, not `server/`'s |
| `ITINERARY_DB_PATH` |  | `itinerary.db` | SQLite file the `llm/` endpoint stores the booked trip in (relative to `llm/`). Optional; lives in **`llm/.env.local`** |
| `AGENT_BACKEND_URL` (web deploy) | ✅ | — | Required in a deployed `web` app when proxying to the backend |

## Commands

```bash
bun run setup            # install web deps + create server/ and llm/ venvs
bun run dev              # run llm (:8001) + backend (:8000) + web (:3000)

bun run doctor           # prerequisite check (no creds needed)
bun run doctor:local     # + .env.local + credentials + CUSTOM_LLM_URL checks

bun run verify           # web-only gate (no Agora creds needed)
bun run verify:local     # full local gate: backend compile + smoke tests + web build
bun run clean            # remove venvs and build artifacts
```

Tests run standalone (no Agora cloud needed): `pytest` in `llm/`, plus
`bun run verify` in `web/`.

## Architecture

```
Browser (localhost:3000)
  │  fetch /api/*
  ▼
Next.js  ──rewrite──▶  Agent backend  (server/, localhost:8000)
                          │  starts agent session (CustomLLM vendor)
                          ▼
                       Agora ConvoAI Cloud
                          │  POST <CUSTOM_LLM_URL>   (Authorization: Bearer)
                          ▼
                       Concierge LLM endpoint  (llm/, localhost:8001)
                          ▲  public via ngrok tunnel
                          │  derives persona, runs FSM, streams reply
                          │  reads/writes SQLite itinerary.db
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full detail.

## What You Get

- A **Next.js** web client (:3000) that drives the RTC/RTM lifecycle and only
  ever calls `/api/*`.
- A **FastAPI** agent backend (:8000) that owns Agora token generation and the
  agent session lifecycle.
- A **3-persona handoff FSM** — Triage, Booking, Trip Support — with persona
  derived at every turn from intent keywords + SQLite itinerary state.
- Deterministic flight options (Paris, Tokyo, Rome) and `_match_choice` for slot
  selection ("the morning one", "the cheapest").
- A **zero-key mock** LLM endpoint so the full pipeline runs with no LLM API key.

## How It Works

1. The browser calls `/api/get_config`; the backend mints an Agora token.
2. The browser joins the RTC channel, then calls `/api/startAgent`; the backend
   starts a session using the `CustomLLM` vendor pointed at `CUSTOM_LLM_URL`.
3. The user speaks. Agora runs STT (Deepgram nova-3), then sends the transcript
   to your `llm/` endpoint as `POST /chat/completions`.
4. `run_agent_turn()` calls `derive_persona()` — if a booking exists in SQLite
   the persona is `trip_support`; if the text contains booking keywords it is
   `booking`; otherwise `triage`. The function then dispatches to the right
   handler and streams only the final spoken reply in OpenAI SSE format.
5. Agora runs TTS (MiniMax) and plays it back. The persona transition is
   invisible to Agora cloud.
6. `/api/stopAgent` ends the session.

### Replacing the mock

Edit `llm/src/custom_llm_server.py`. The key surface area is `derive_persona()`,
`run_agent_turn()`, and the handler functions (`search_trips`, `book_trip`,
`get_itinerary`, `cancel_booking`, `modify_booking`). The endpoint must keep the
OpenAI streaming `/chat/completions` contract. See [`llm/README.md`](llm/README.md).

## Repo Map

- `web/` — Next.js frontend (:3000); RTC/RTM lifecycle and UI.
- `server/` — FastAPI agent backend (:8000); Agora tokens + agent lifecycle, `CustomLLM` vendor.
- `llm/` — OpenAI-compatible mock `/chat/completions` endpoint (:8001) that Agora cloud calls; 3-persona handoff FSM over SQLite itinerary.
- `ARCHITECTURE.md` — system shape and component boundaries.
- `AGENTS.md` — guide for coding agents working in this repo.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Agent starts but never speaks | `CUSTOM_LLM_URL` is not public or omits `/chat/completions`. Use your ngrok URL. |
| `doctor:local` warns about localhost | Replace the local URL with your public tunnel URL. |
| Local calls fail under a global proxy | Configure your proxy to send `127.0.0.1` and `localhost` DIRECT. |
| `Missing llm/venv` during verify | Run `bun run setup` (creates both venvs). |

## More Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [AGENTS.md](./AGENTS.md)

## License

Released under the [MIT License](./LICENSE).
