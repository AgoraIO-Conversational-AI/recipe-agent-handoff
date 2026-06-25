# 06 · Interfaces

> Boundary contracts: backend routes, the `/api/*` rewrite map, env vars, the response envelope, and the `/llm/chat/completions` OpenAI SSE contract.

## Backend routes (port 8000)

The browser calls the first three as `/api/<name>`; Next rewrites to the backend `/<name>`. Agora cloud calls `/llm/chat/completions` directly (public URL required).

### `GET /get_config`

- Query (optional): `channel?: string`, `uid?: int` (≤ 0 or missing → backend generates one).
- Returns `data`: `{ app_id, token, uid (string), channel_name, agent_uid (string) }`.
- Token is a Token007 RTC+RTM token, expiry 3600s, for a concrete non-zero UID.

### `POST /startAgent`

- Body: `{ channelName: string, rtcUid: int, userUid: int, parameters?: object }`.
  - `parameters.output_audio_codec?: string` is the only honored parameter field.
- Returns `data`: `{ agent_id, channel_name, status: "started" }`.
- 400 if `AGORA_APP_ID`/`AGORA_APP_CERTIFICATE`/`CUSTOM_LLM_URL`/`CUSTOM_LLM_API_KEY` unset, or `channelName`/`rtcUid`/`userUid` invalid.

### `POST /stopAgent`

- Body: `{ agentId: string }`.
- Returns `{ code: 0, msg: "success" }` (no `data`).

### `POST /llm/chat/completions` (concierge LLM endpoint)

- Called by **Agora cloud**, not the browser.
- Accepts OpenAI `ChatCompletionRequest` JSON. `stream` must be `true` (400 otherwise).
- Returns `text/event-stream` SSE: role chunk → content chunks → `finish_reason: "stop"` → `data: [DONE]`.
- No `tool_call` chunks — Agora cloud never sees function calling.
- `Authorization: Bearer <CUSTOM_LLM_API_KEY>` is forwarded by Agora cloud; the mock does not validate it.

### `GET /llm/health`

- Returns `{ "status": "ok", "service": "handoff-mock" }`.

## Response envelope

```json
{ "code": 0, "msg": "success", "data": { } }
```

`data` omitted when the route has no payload. Non-zero `code` or missing `data` = error on the client side. Only applies to the agent backend routes — the LLM endpoint uses the OpenAI SSE format.

## Rewrite map (`web/next.config.ts`)

| Browser path        | Backend destination |
| ------------------- | ------------------- |
| `/api/get_config`   | `/get_config`       |
| `/api/startAgent`   | `/startAgent`       |
| `/api/stopAgent`    | `/stopAgent`        |

`rewrites()` returns `[]` when `AGENT_BACKEND_URL` is unset. The contract is asserted by `verify-api-contracts.ts`.

## Browser API client (`web/src/services/api.ts`)

- `getConfig({ channel?, uid? }) → GetConfigResponse`
- `startAgent(channelName, rtcUid, userUid) → agent_id`
- `stopAgent(agentId) → void`

## Environment variables

| Variable                | Scope          | Required | Default           |
| ----------------------- | -------------- | :------: | ----------------- |
| `AGORA_APP_ID`          | backend        |    ✅    | —                 |
| `AGORA_APP_CERTIFICATE` | backend        |    ✅    | —                 |
| `CUSTOM_LLM_URL`        | backend        |    ✅    | — (no localhost default) |
| `CUSTOM_LLM_API_KEY`    | backend        |    ✅    | `any-key-here`    |
| `CUSTOM_LLM_MODEL`      | backend        |          | `handoff-mock`    |
| `AGENT_GREETING`        | backend        |          | built-in line     |
| `ITINERARY_DB_PATH`     | backend        |          | `itinerary.db`    |
| `AGENT_BACKEND_URL`     | web (deploy)   |  ✅\*    | `http://localhost:8000` (dev) |
| `PORT`                  | backend (env only) |      | `8000` — do **not** put in `.env.example` |

\* Required wherever the web app is deployed; rewrites are empty without it.

## `CustomLLM` vendor config (`agent.py`)

`Agent.start()` builds the vendor chain:

| Vendor       | SDK class      | Key params                                                      |
| ------------ | -------------- | --------------------------------------------------------------- |
| LLM          | `CustomLLM`    | `base_url=CUSTOM_LLM_URL`, `api_key=CUSTOM_LLM_API_KEY`, `model=CUSTOM_LLM_MODEL`, `max_history=15`, `max_tokens=1024`, `temperature=0.7` |
| STT          | `DeepgramSTT`  | `model="nova-3"`, `language="en"`                               |
| TTS          | `MiniMaxTTS`   | `model="speech_2_6_turbo"`, `voice_id="English_captivating_female1"` |

Session parameters: `audio_scenario="chorus"`, `data_channel="rtm"`, `enable_error_message=True`, `enable_metrics=True`.

## Related Deep Dives

- [handoff_flow](L2/handoff_flow.md) — full FSM dispatch, SQLite schema, SSE format detail.
