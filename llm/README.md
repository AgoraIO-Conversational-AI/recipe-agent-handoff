# Concierge LLM Endpoint — Mock

An OpenAI-compatible `POST /chat/completions` server (port 8001) that Agora cloud
calls during a conversation. This mock implements a **3-persona Travel Concierge
handoff FSM** entirely inside the endpoint — with no LLM API key required.

### Personas

| Persona | Active when | What it does |
| --- | --- | --- |
| **Triage** | No booking in DB, no booking keywords | Greets and asks for destination |
| **Booking** | No booking in DB, booking keyword detected | Searches flights or confirms a booking |
| **Trip Support** | Any booking exists in DB | Shows, modifies, or cancels the booked trip |

Persona is derived fresh on every turn from intent keywords and the `itinerary`
SQLite table — there is no stored persona field and no session id. The active
itinerary persists across restarts (`ITINERARY_DB_PATH`, default `itinerary.db`).

## The contract

Implement `POST /chat/completions` returning OpenAI-style SSE:

- first chunk sets `delta.role = "assistant"`
- content chunks carry `delta.content`
- a final chunk sets `finish_reason = "stop"`
- the stream terminates with `data: [DONE]`

Only streaming (`stream: true`) is supported; non-streaming requests return 400.

## Run

```bash
cd llm
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python src/custom_llm_server.py     # serves on CUSTOM_LLM_PORT (default 8001)
```

## Tests

```bash
cd llm
source venv/bin/activate
pytest tests -v
```

Six tests cover: triage fallback, booking detection, deterministic flight search,
full booking flow + trip-support recall, and cancel/state-clear.

## Expose it publicly

Agora cloud — not the browser — calls this server, so it must be reachable from
the public internet. For local dev, tunnel it:

```bash
ngrok http 8001
```

Then set `CUSTOM_LLM_URL=https://<tunnel>/chat/completions` in `server/.env.local`.

## Auth

This mock does **not** authenticate. A production endpoint should validate the
`Authorization: Bearer <CUSTOM_LLM_API_KEY>` header that Agora cloud forwards.

## Replace the mock

The key surface area in `src/custom_llm_server.py`:

- `derive_persona(conn, user_text)` — FSM state function
- `run_agent_turn(conn, messages)` — top-level dispatcher
- `search_trips(dest)` / `book_trip(conn, dest, choice_text)` — booking handlers
- `get_itinerary(conn)` / `cancel_booking(conn)` / `modify_booking(conn, text)` — trip-support handlers

In production, replace the keyword heuristics with a real LLM and persist the
itinerary to your own database.
