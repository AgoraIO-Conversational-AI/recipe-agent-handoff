# Deep Dive — Handoff Flow

> **When to Read This:** You are changing the persona FSM logic, SQLite schema, handoff trigger keywords, the SSE streaming format, or the way `run_agent_turn()` dispatches. For the high-level picture, start at [02_architecture](../02_architecture.md).

This recipe implements a 3-persona Travel Concierge handoff entirely inside `server/src/llm.py`. The component is provider-agnostic (no `agora_agent` import) and mounted into the backend at `/llm`. Agora cloud calls `POST /llm/chat/completions`; the mock returns only spoken text — no `tool_call` chunks.

## SQLite schema

`get_db(path)` creates two tables with `CREATE TABLE IF NOT EXISTS`:

```sql
CREATE TABLE IF NOT EXISTS itinerary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination TEXT NOT NULL,
    slot TEXT NOT NULL,
    price INTEGER NOT NULL,
    created_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS context (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
```

- `itinerary` — one row per booking. `_booked(conn)` fetches the most recent row; booking exists iff this returns non-None.
- `context` — key/value store for cross-turn state. Current key: `pending_dest` (last mentioned destination while no booking exists).

## Persona derivation

`derive_persona(conn, user_text) → "trip_support" | "booking" | "triage"`:

1. `_booked(conn)` non-None → `trip_support` (DB state wins; ignores keywords).
2. Any keyword in `_BOOK_KW` present in `user_text.lower()` → `booking`.
3. Otherwise → `triage`.

Keywords: `_BOOK_KW = ("book", "flight", "trip", "travel", "fly", "go to", "vacation", "holiday")`.

No session id, no stored persona field — the active persona is always derived fresh. This makes the FSM restart-safe and directly testable from a DB snapshot.

## Dispatch in `run_agent_turn(conn, messages)`

```
user_text = _extract_last_user_text(messages)
persona = derive_persona(conn, user_text)

trip_support:
  cancel keywords   → cancel_booking(conn)
  modify keywords   → modify_booking(conn, user_text)
  recall keywords   → get_itinerary(conn)
  otherwise         → get_itinerary(conn) + offer to change/cancel

booking:
  recall keywords   → get_itinerary(conn)   # even if no booking
  dest found        → cache pending_dest; if choice matched → book_trip; else → search_trips
  no dest           → prompt for destination

triage:
  catch-all         → greeting + ask for destination
```

`_match_choice(text, opts)` resolves slot selection: ordinal words (`first`, `second`, `third`), time names (`morning`, `midday`, `evening`), `cheapest` (min price), `earliest`/`morning` (first option).

## SSE streaming contract

The `generate()` async generator follows the OpenAI chat-completions chunk format:

1. **Role chunk** — `delta: { "role": "assistant", "content": "" }`, `finish_reason: null`.
2. **Content chunks** — one chunk per word, 50ms delay between each. `delta: { "content": "<token>" }`.
3. **Stop chunk** — `delta: {}`, `finish_reason: "stop"`.
4. **Terminal line** — `data: [DONE]`.

All DB work runs in `run_agent_turn()` **before** the generator is created. The `generate()` closure never touches SQLite.

`stream: false` requests return `400` — Agora ConvoAI always streams.

## Handler functions

| Function | Writes DB? | Reads DB? | Notes |
| -------- | :--------: | :--------: | ----- |
| `search_trips(dest)` | No | No | Returns deterministic flight list from `OPTIONS` dict |
| `book_trip(conn, dest, choice_text)` | Yes | No | INSERT into `itinerary`; returns confirmation with handoff notice |
| `get_itinerary(conn)` | No | Yes | SELECT latest row; returns "no trip" message if empty |
| `cancel_booking(conn)` | Yes | No | DELETE all `itinerary` rows |
| `modify_booking(conn, text)` | Yes | Yes | DELETE + INSERT; uses `_match_choice` on current destination |

## Destinations and options

`OPTIONS` dict (deterministic, no external calls):

```python
OPTIONS = {
    "paris": [(1, "morning", 420), (2, "midday", 480), (3, "evening", 390)],
    "tokyo": [(1, "morning", 910), (2, "midday", 870), (3, "evening", 940)],
    "rome":  [(1, "morning", 360), (2, "midday", 410), (3, "evening", 330)],
}
```

## Replacing the mock

Edit `server/src/llm.py`. Minimum contract to preserve:

- `POST /chat/completions` — accept `ChatCompletionRequest`; reject `stream: false` with 400; return `text/event-stream` ending with `data: [DONE]`.
- `GET /health` — return `{ "status": "ok", "service": "handoff-mock" }` (or update `test_tools.py`).
- No `agora_agent` import (enforced by `test_llm_mount.py`).

## Related L1

- [02_architecture](../02_architecture.md) · [06_interfaces](../06_interfaces.md) · [07_gotchas](../07_gotchas.md)
