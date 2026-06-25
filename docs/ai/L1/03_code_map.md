# 03 · Code Map

> Where things live. Two top-level modules: `web/` (Next.js client) and `server/` (FastAPI backend + concierge LLM endpoint). Orchestration is in the root `package.json`.

## Root

| Path                  | Responsibility                                                              |
| --------------------- | --------------------------------------------------------------------------- |
| `package.json`        | Bun workspace; `setup`, `dev`, `doctor*`, `verify*`, `clean` scripts.       |
| `README.md`           | Setup, run modes, env, ngrok, troubleshooting.                              |
| `ARCHITECTURE.md`     | System shape, persona FSM, component boundaries.                            |
| `AGENTS.md`           | Coding-agent handbook + Git conventions.                                    |
| `Dockerfile`          | Single-process backend-only image (`:8000`); bundles agent + LLM endpoint.  |
| `.github/workflows/`  | `ci.yml` (backend pytest matrix × Linux/macOS/Windows × py3.10+3.13 + web verify), `docker.yml`, `nightly.yml`. |

## `server/` — FastAPI backend (:8000)

| Path                              | Responsibility                                                              |
| --------------------------------- | --------------------------------------------------------------------------- |
| `src/server.py`                   | FastAPI app, CORS, route handlers, error mapping, mounts `llm.app` at `/llm`, uvicorn entrypoint. |
| `src/agent.py`                    | `Agent` class: `AsyncAgora` client, `CustomLLM` + `DeepgramSTT` + `MiniMaxTTS` vendor chain, `start()`/`stop()`, `_sessions`. |
| `src/llm.py`                      | OpenAI-compatible `POST /chat/completions` mock; 3-persona FSM (Triage → Booking → Trip Support) over SQLite itinerary; no `agora_agent` dependency. Replace this with a real model. |
| `scripts/run_fake_server.py`      | Boots `server.app` with a `FakeAgent` for the local FastAPI smoke test.     |
| `tests/test_agent_construction.py`| Builds the real `AgoraAgent` with `CustomLLM`, fakes the SDK session, asserts shape. |
| `tests/test_handoff.py`           | FSM unit tests: `derive_persona`, `search_trips`, `book_trip`, trip support, cancel. |
| `tests/test_llm.py`               | LLM endpoint contract tests: health, SSE streaming format, non-streaming rejection. |
| `tests/test_llm_mount.py`         | Integration: LLM is reachable at `/llm/*` through the mounted server app; `llm.py` is agora-free. |
| `tests/test_tools.py`             | Sanity: health endpoint returns correct `service` name (`handoff-mock`). |
| `tests/conftest.py`               | `fake_env` fixture + `FakeAgent`; no cloud, no real creds.                  |
| `.env.example`                    | Env template (do not add `PORT`).                                           |
| `requirements*.txt`               | Runtime + dev (pytest + httpx) deps.                                        |

## `server/src/server.py` routes

- `GET /get_config` — token + channel/UID config.
- `POST /startAgent` — start the handoff agent session.
- `POST /stopAgent` — stop by `agent_id`.
- `/llm/*` — mounted sub-app (`llm.app`); Agora cloud calls `POST /llm/chat/completions`.

## `web/` — Next.js client (:3000)

| Path                                      | Responsibility                                                         |
| ----------------------------------------- | ---------------------------------------------------------------------- |
| `next.config.ts`                          | `/api/*` rewrites to `AGENT_BACKEND_URL`; strict mode; Turbopack root. |
| `src/services/api.ts`                     | Browser API client: `getConfig`, `startAgent`, `stopAgent`.            |
| `src/lib/conversation.ts`                 | Transcript normalization, timestamp/UID mapping, visualizer state.     |
| `src/lib/agora.ts`                        | Agora RTC/RTM helpers.                                                 |
| `src/components/LandingPage.tsx`          | Conversation entry: config fetch, agent start, RTM login, teardown.    |
| `src/components/ConversationComponent.tsx`| RTC join, mic publish, transcript/metrics/state listeners.             |
| `src/components/Quickstart*.tsx`          | Pre-call, transcript, metrics, layout panels.                          |
| `scripts/verify-api-contracts.ts`         | Asserts rewrites + client paths + response envelope (no network).      |
| `scripts/verify-local-proxy.ts`           | Stub backend; proxies `/api/*` through the rewrite map.                |
| `scripts/verify-local-fastapi.ts`         | Spawns real FastAPI with `FakeAgent`; proxies routes end-to-end.       |
| `scripts/verify-local-llm.ts`             | Spawns the LLM endpoint standalone; asserts SSE contract.              |
| `scripts/doctor.ts`                       | Web prerequisite check.                                                |

## Related Deep Dives

- None. For runtime flow see [02_architecture](02_architecture.md); for contracts see [06_interfaces](06_interfaces.md).
