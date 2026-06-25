# 05 · Workflows

> Step-by-step guides for the common changes in this recipe. Each ends with the narrowest verify command to run.

## Add or change a browser-facing route

1. Add the FastAPI handler in `server/src/server.py` (return the `{ code, msg, data }` envelope).
2. Add the `/api/<name>` → `/<name>` mapping in `web/next.config.ts` `rewrites()`.
3. Add a client helper in `web/src/services/api.ts`.
4. Extend `web/scripts/verify-api-contracts.ts` with the new path + envelope assertions.
5. Verify: `bun run verify:web` (and `bun run verify:local:fastapi` if it should go through the real backend).

## Replace the mock LLM with a real model

1. Edit `server/src/llm.py`. Keep the same `POST /chat/completions` OpenAI SSE contract; keep the same `GET /health` endpoint.
2. Do **not** add `agora_agent` imports — `test_llm_mount.py` asserts this via AST.
3. If you add env vars (e.g. an API key), add them to `server/.env.example` and document them in `01_setup.md` and `06_interfaces.md`.
4. Verify: `bun run verify:backend` + `cd server && pytest tests -v`.

## Extend or modify the persona FSM

1. Edit `derive_persona()`, `run_agent_turn()`, or the handler functions in `server/src/llm.py`.
2. Add SQLite schema changes in `get_db()` — tables are created with `CREATE TABLE IF NOT EXISTS`.
3. Add test cases to `server/tests/test_handoff.py` using a temp DB (`fresh_db()`).
4. Verify: `cd server && pytest tests -v`.

## Change the agent greeting / model

1. Greeting: set `AGENT_GREETING` (env) or edit the default in `server/src/agent.py`.
2. STT model: edit `DeepgramSTT(model=...)` in `Agent.start()`.
3. TTS model/voice: edit `MiniMaxTTS(model=..., voice_id=...)` in `Agent.start()`.
4. `CustomLLM` model name: set `CUSTOM_LLM_MODEL` (env).
5. Verify: `bun run verify:backend` + `cd server && pytest tests -v`.

## Run / debug locally

```bash
ngrok http 8000              # expose backend; Agora cloud calls /llm/chat/completions
bun run dev                  # both processes
bun run doctor:local         # check creds + .env.local + CUSTOM_LLM_URL before a live call
```

## Verify before finishing

| Change touches…                       | Run                                                                       |
| ------------------------------------- | ------------------------------------------------------------------------- |
| Web only                              | `bun run verify:web`                                                       |
| Backend logic / Agent / FSM           | `bun run verify:backend` + `cd server && pytest tests -v`                  |
| LLM endpoint (`llm.py`) only          | `bun run verify:backend` + `cd server && pytest tests/test_llm*.py -v`    |
| Route/proxy boundary                  | `bun run verify:web:proxy` and/or `bun run verify:local:fastapi`          |
| LLM endpoint end-to-end               | `bun run verify:local:llm`                                                |
| Anything end-to-end (local)           | `bun run verify:local`                                                    |

## Deploy

1. Deploy `web/` as a Next.js app.
2. Deploy `server/` as a single publicly reachable FastAPI process — the same process serves `/llm`. The published single-process image is `ghcr.io/AgoraIO-Conversational-AI/recipe-agent-handoff` on `v*` tags.
3. Set `AGENT_BACKEND_URL` in the web deployment.
4. Set `CUSTOM_LLM_URL` to `<public-url>/llm/chat/completions` so Agora cloud can reach the endpoint.

## Related Deep Dives

- [handoff_flow](L2/handoff_flow.md) — FSM internals, SQLite schema, SSE streaming.
- [session_lifecycle](L2/session_lifecycle.md) — client-side join/renewal/teardown.
