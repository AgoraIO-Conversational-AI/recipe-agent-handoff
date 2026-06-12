# Agora Conversational AI — Tool Calling Recipe (Python)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](https://www.python.org/)
[![Bun](https://img.shields.io/badge/bun-latest-black)](https://bun.sh/)

The **tool-calling** recipe in the Agora Conversational AI recipes family. Bring
your own LLM endpoint to Agora's voice pipeline and add tool execution to it:
the agent's LLM stage is pointed at your own OpenAI-compatible
`POST /chat/completions` endpoint, which internally runs tools — `log_message`
to save a note and `list_messages` to read your notes back — when the user's
intent warrants it, and streams back only the final spoken reply. Notes persist
in a small SQLite database, so they survive restarts. Agora cloud never sees a
`tool_call` — the tool loop is entirely inside the `llm/` endpoint. STT
(Deepgram nova-3) and TTS (MiniMax) stay Agora-managed.

This repo ships a **zero-key mock** LLM endpoint so you can run the full
STT → tool-calling LLM → TTS pipeline immediately, then replace the mock with
your own model and tool registry.

## Prerequisites

- [Python 3.10+](https://www.python.org/)
- [Bun](https://bun.sh/)
- [Agora CLI](https://github.com/AgoraIO/cli) — makes generating an App ID + App Certificate easy
- [ngrok](https://ngrok.com/) — this is a bundled recipe; the mock LLM endpoint must be publicly reachable so Agora cloud can call it

## Run It

```bash
# 1. Install + create both Python venvs
bun run setup

# 2. Add Agora credentials (CLI), or edit server/.env.local by hand
agora login
agora project use <your-project>          # select which project to use (you may have several)
agora project env write server/.env.local # writes App ID/Certificate; keeps your CUSTOM_LLM_* lines

# 3. Expose the tool-calling LLM endpoint publicly (Agora cloud calls it directly)
ngrok http 8001

# 4. Add the tunnel URL to server/.env.local (use whatever domain ngrok prints —
#    today that is usually *.ngrok-free.dev)
#    CUSTOM_LLM_URL=https://<your-tunnel>.ngrok-free.dev/chat/completions

# 5. Run all three services
bun run dev
```

Open [http://localhost:3000](http://localhost:3000) → **Start Conversation** → speak.

### Working from a clone

If you cloned this repo (rather than scaffolding via the Agora CLI), the steps
above are complete as written: `bun run setup` creates both Python venvs and
installs web dependencies, then `bun run dev` brings up all three services. You
still need Agora credentials in `server/.env.local` and a public
`CUSTOM_LLM_URL` tunnel before a conversation can connect.

Services:

- Frontend — http://localhost:3000
- Backend — http://localhost:8000
- API docs — http://localhost:8000/docs

## Deploy

Deploy `web` (Next.js), `server` (a reachable FastAPI backend), and `llm` (a
publicly reachable FastAPI endpoint). Set `AGENT_BACKEND_URL` in the web
deployment so the Next rewrites reach the backend.

A multi-process Docker image is published to
`ghcr.io/AgoraIO-Conversational-AI/recipe-agent-tool-calling` on `v*` tags. It
bundles the agent backend (:8000) **and** the mock LLM endpoint (:8001) in one
image. To host the single-image demo, expose :8001 publicly and point
`CUSTOM_LLM_URL` at it. A local `docker run` still needs a tunnel, because Agora
cloud cannot reach `localhost`. The bundled mock is a development stand-in you
replace with your own model and tool registry in production.

## Environment variables

Backend env file: [`server/.env.example`](server/.env.example).

| Variable | Required | Default | Notes |
| --- | :---: | :---: | --- |
| `AGORA_APP_ID` | ✅ | — | Agora Console → Project → App ID |
| `AGORA_APP_CERTIFICATE` | ✅ | — | Agora Console → Project → App Certificate (server only) |
| `CUSTOM_LLM_URL` | ✅ | — | **Public** chat-completions URL of your `llm/` endpoint. Agora cloud calls it; cannot be `localhost`. |
| `CUSTOM_LLM_API_KEY` | ✅ | `any-key-here` | Forwarded by Agora cloud as `Authorization: Bearer`. Required by the `CustomLLM` vendor. |
| `CUSTOM_LLM_MODEL` |  | `tool-mock` | Model name passed to your endpoint |
| `AGENT_GREETING` |  | built-in | Optional opening line override |
| `PORT` |  | `8000` | Agent backend port |
| `CUSTOM_LLM_PORT` |  | `8001` | Port for the tool-calling LLM endpoint — lives in **`llm/.env.local`**, not `server/`'s |
| `MESSAGE_DB_PATH` |  | `messages.db` | SQLite file the `llm/` endpoint stores notes in (relative to `llm/`). Optional; lives in **`llm/.env.local`** |
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
`bun run verify` in `web/`. CI runs them on Linux/macOS/Windows × Python 3.10 & 3.13.

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
                       Tool-calling LLM endpoint  (llm/, localhost:8001)
                          ▲  public via ngrok tunnel
                          │  runs log_message / list_messages (SQLite), streams reply
```

The browser only ever calls Next `/api/*`, which rewrites to the agent backend.
The agent backend owns Agora tokens and agent lifecycle. The **tool-calling LLM
endpoint** is separate because Agora cloud — not the browser — calls it, so it
must be publicly reachable. See [ARCHITECTURE.md](./ARCHITECTURE.md).

## What You Get

- A **Next.js** web client (:3000) that drives the RTC/RTM lifecycle and only
  ever calls `/api/*`.
- A **FastAPI** agent backend (:8000) that owns Agora token generation and the
  agent session lifecycle.
- The `/api/get_config` · `/api/startAgent` · `/api/stopAgent` contract between
  the web client and the backend (Next rewrites, no Route Handlers).
- An internal **tool loop** — `log_message` / `list_messages` over SQLite —
  that streams only the spoken reply back to Agora (Agora never sees a
  `tool_call`).
- A **zero-key mock** LLM endpoint so the full pipeline runs with no LLM API key.

## How It Works

1. The browser calls `/api/get_config`, which Next rewrites to the backend; the
   backend mints an Agora token from `AGORA_APP_ID` + `AGORA_APP_CERTIFICATE`.
2. The browser joins the RTC channel, then calls `/api/startAgent`; the backend
   starts an agent session using the `CustomLLM` vendor pointed at
   `CUSTOM_LLM_URL`.
3. The user speaks. Agora runs STT (Deepgram nova-3), then sends the transcript
   to your `llm/` endpoint as an OpenAI `POST /chat/completions` request,
   forwarding `CUSTOM_LLM_API_KEY` as `Authorization: Bearer`.
4. Inside the endpoint, `run_agent_turn()` decides whether the turn warrants a
   tool. It runs `log_message()` to persist a note or `list_messages()` to read
   notes back from SQLite, then streams **only** the final spoken reply in the
   OpenAI SSE chunk format.
5. Agora runs TTS (MiniMax) on the streamed reply and plays it back in the
   channel. Agora cloud never observes the internal `tool_call` loop.
6. `/api/stopAgent` ends the session.

### Replacing the mock

Edit `run_agent_turn()` / `log_message()` / `list_messages()` in
[`llm/src/custom_llm_server.py`](llm/src/custom_llm_server.py). The endpoint must
keep speaking the OpenAI streaming `/chat/completions` contract (see
[`llm/README.md`](llm/README.md)). A production endpoint should also validate the
`Authorization: Bearer` header.

## Repo Map

- `web/` — Next.js frontend (:3000); RTC/RTM lifecycle and UI.
- `server/` — FastAPI agent backend (:8000); Agora tokens + agent lifecycle, `CustomLLM` vendor.
- `llm/` — OpenAI-compatible mock `/chat/completions` endpoint at :8001 that Agora cloud calls; internal `log_message` / `list_messages` tool loop over SQLite.
- `ARCHITECTURE.md` — system shape and component boundaries.
- `AGENTS.md` — guide for coding agents working in this repo.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Agent starts but never speaks | `CUSTOM_LLM_URL` is not public or omits `/chat/completions`. Use your ngrok URL. |
| `doctor:local` warns about localhost | Replace the local URL with your public tunnel URL. |
| Local calls fail / hang under a global proxy (Clash, etc.) | Your proxy is routing loopback through itself. Configure it to send `127.0.0.1`, `localhost`, and RFC-1918 ranges DIRECT (don't disable the proxy entirely). |
| `Missing llm/venv` during verify | Run `bun run setup` (creates both venvs). |

## More Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [AGENTS.md](./AGENTS.md)

## License

Released under the [MIT License](./LICENSE).
