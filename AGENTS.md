# Agent Development Guide

For coding agents working in `recipe-agent-handoff`. This repository is the
**agent-handoff** recipe (`Recipe Role: handoff`) in the Agora Conversational AI
recipes family, derived from the `recipe-agent-tool-calling` template.

## System shape

- **`server/`** — Python FastAPI agent backend (:8000). Owns Agora token
  generation and agent session lifecycle. Uses the `CustomLLM` vendor to point the
  agent's LLM stage at the concierge LLM endpoint. SDK: `agora-agents>=2.0.0`
  (`import agora_agent`).
- **`llm/`** — Python FastAPI concierge LLM endpoint (:8001). OpenAI-compatible
  `POST /chat/completions` mock that Agora cloud calls. Internally implements a
  3-persona handoff FSM (Triage → Booking → Trip Support) derived from user intent
  keywords and SQLite itinerary state. `run_agent_turn()` dispatches to the active
  persona handler and streams only the spoken reply. Agora cloud never sees a
  `tool_call`. No `agora-agents` dependency. This is the component a developer
  replaces.
- **`web/`** — Next.js 16 / React 19 / TypeScript frontend (:3000), resynced from
  the base quickstart.
- Auth: Token007 from `AGORA_APP_ID` + `AGORA_APP_CERTIFICATE`.

## Persona FSM

Personas are derived at every turn — no stored persona field, no session id:

| Function | Description |
| --- | --- |
| `derive_persona(conn, user_text)` | Returns `"trip_support"` if booked, `"booking"` if booking keyword present, else `"triage"` |
| `search_trips(dest)` | Returns deterministic flight options string |
| `book_trip(conn, dest, choice_text)` | Writes to `itinerary` table; returns confirmation with handoff notice |
| `get_itinerary(conn)` | Reads the latest booking row |
| `cancel_booking(conn)` | Deletes all `itinerary` rows |
| `modify_booking(conn, text)` | Replaces booking with new slot |
| `run_agent_turn(conn, messages)` | Top-level dispatcher |

A pending destination is cached in a `context` table (key `pending_dest`) between
turns so multi-turn booking flows work without full message history.

## Routing / ownership

- UI and RTC/RTM lifecycle live in `web/`.
- Browser-facing `/api/*` paths are Next rewrites (`web/next.config.ts`) to the
  agent backend; do not add `web/app/api/**/route.ts` for agent/token logic.
- Token generation and agent lifecycle live in `server/src/`.
- The OpenAI `/chat/completions` contract and persona FSM live in `llm/src/`.

## Supported modes

- **Local:** `bun run dev` starts `llm` (:8001), `server` (:8000), and `web`
  (:3000). The web app calls `/api/*`; Next rewrites to
  `AGENT_BACKEND_URL=http://localhost:8000`. The concierge LLM endpoint must be
  exposed publicly (ngrok) so Agora cloud can reach it.
- **Deploy:** deploy `web` (Next) + `server` (reachable FastAPI) + `llm` (publicly
  reachable FastAPI). Set `AGENT_BACKEND_URL` in the web deployment.

## Patterns

- Keep the web client calling `/api/*`; hide backend placement behind Next rewrites.
- Keep token generation and the App Certificate in `server/`.
- Keep the `llm/` endpoint free of `agora-agents` — it is provider-agnostic.
- `CUSTOM_LLM_URL` is required and must be public; there is no localhost default.
- Both `CUSTOM_LLM_URL` and `CUSTOM_LLM_API_KEY` are required by the `CustomLLM`
  vendor (the SDK rejects one without the other).
- The persona FSM and SQLite itinerary belong in `llm/`; do not move them into
  `server/` or expose as a separate service.
- Persona is always derived from DB + intent; never store persona in a session.

## Anti-patterns

- Do not reintroduce Next Route Handlers for agent/token logic.
- Do not add `agora-agents` to `llm/`.
- Do not default `CUSTOM_LLM_URL` to localhost.
- Do not put `PORT` in `server/.env.example` (it would clobber the random port
  that `verify:local:fastapi` injects via `load_dotenv(override=True)`).
- Do not store persona as a DB field or session variable — derive it every turn.

## Commands

```bash
bun run setup
bun run dev
bun run doctor
bun run doctor:local
bun run verify         # web-only, no creds
bun run verify:local   # full local gate
```

Narrower checks: `bun run verify:backend`, `bun run verify:local:fastapi`,
`bun run verify:local:llm`, `bun run verify:web:proxy`.

## Done criteria

1. Run the narrowest relevant verification command.
2. Web-affecting changes: `bun run verify:web` passes.
3. Backend-affecting changes: `bun run verify:local` (or the narrower
   `verify:local:fastapi` / `verify:local:llm` / `verify:backend`) passes.
4. If you change required env vars or setup steps, update the root README, the
   relevant module README, and `server/.env.example` / `llm/.env.example` together.

## Git conventions

- Conventional Commits: `type: description` or `type(scope): description`
  (`feat`, `fix`, `chore`, `test`, `docs`). Lowercase after the prefix, present
  tense.
- No AI tool names in commit messages or PR descriptions. No `Co-Authored-By`
  trailers. No `--no-verify`. No git config changes.
- Branch names: `type/short-description` (e.g. `feat/handoff-expansion`).
