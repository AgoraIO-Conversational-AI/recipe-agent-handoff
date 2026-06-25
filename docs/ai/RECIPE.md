---
recipe_version: 1.0.0
recipe_status: experimental
extension_points:
  - id: api.routes
    name: Browser-facing API routes
  - id: agent.vendor-config
    name: CustomLLM URL/key/model, STT model, TTS model/voice, greeting, session parameters
  - id: llm.persona-fsm
    name: Persona handoff logic, SQLite itinerary schema, trigger keywords, handler functions
  - id: web.conversation-ui
    name: Conversation UI panels and controls
  - id: verification.contracts
    name: Contract, proxy, FastAPI smoke, and LLM endpoint verification
invariants:
  - id: api.rewrite-boundary
    summary: Browser calls stay on /api/* and Next rewrites to FastAPI; no Route Handlers for agent/token logic.
  - id: secrets.server-only
    summary: Agora App Certificate and CUSTOM_LLM_API_KEY stay in the Python backend.
  - id: llm.agora-free
    summary: server/src/llm.py has no agora_agent import; it is the provider-agnostic component you replace.
  - id: llm.no-tool-calls
    summary: The LLM endpoint streams only spoken text in OpenAI SSE format; Agora cloud never receives tool_call chunks.
  - id: persona.stateless
    summary: Active persona is derived fresh every turn from DB state + intent keywords; never stored as a session or DB field.
  - id: token.uid-concrete
    summary: Backend resolves missing, zero, or negative UIDs before issuing an RTC+RTM token.
stable_contracts:
  - id: env.required
    summary: AGORA_APP_ID, AGORA_APP_CERTIFICATE, CUSTOM_LLM_URL, and CUSTOM_LLM_API_KEY are required; AGENT_BACKEND_URL is required by deployed web rewrites.
  - id: api.core-routes
    summary: GET /api/get_config, POST /api/startAgent, and POST /api/stopAgent remain the browser-facing contract.
  - id: llm.endpoint
    summary: POST /llm/chat/completions accepts OpenAI ChatCompletionRequest (stream must be true) and returns text/event-stream SSE ending with data:[DONE].
  - id: response.envelope
    summary: Successful agent backend responses use { code, msg, data }.
---

# Recipe Contract

This base recipe defines the reusable surface for a Python-backed Agora Conversational AI **agent handoff** quickstart: a `CustomLLM` vendor pointing to an in-process OpenAI-compatible concierge endpoint that implements a 3-persona FSM (Triage → Booking → Trip Support) behind a Next.js web client.

## Recipe Role

- Role: `base` recipe (self-contained, clone-and-run; no `Extends` pin).
- Target audience: developers building a persona-routing or agent-handoff pattern on Agora Conversational AI, using a custom LLM endpoint they control.
- Reuse model: clone, bind project, expose backend via tunnel, set `CUSTOM_LLM_URL`, run, then customize the persona FSM or replace `llm.py` with a real model.

## Recipe Scope

- Python FastAPI token generation and managed agent lifecycle.
- A `CustomLLM` vendor chain (`CustomLLM` + `DeepgramSTT` + `MiniMaxTTS`) with a public `CUSTOM_LLM_URL`.
- An in-process OpenAI-compatible concierge endpoint (`/llm`) implementing a 3-persona SQLite-backed handoff FSM — zero external key needed.
- Next.js browser UI with RTC audio, RTM transcript/metrics, connection status.
- Rewrite-only `/api/*` browser facade hiding backend placement.
- Contract, proxy, FastAPI, and LLM endpoint smoke verification that need no live Agora calls.

## Baseline Implementation Guidance

Use this repo's source and progressive disclosure docs as the starting point, then customize. Do not recreate the Agora ConvoAI integration from memory — vendor schemas, SDK builder fields, token behavior, and RTM details drift. Copy verified patterns from this repo.

## Extension Points

| ID | Surface | How to extend | Required follow-up |
| -- | ------- | ------------- | ------------------ |
| `api.routes` | `server/src/server.py`, `web/next.config.ts`, `web/src/services/api.ts` | Add FastAPI route, add rewrite, add browser fetch helper. | Extend `web/scripts/verify-api-contracts.ts`; add coverage if it belongs in local verification. |
| `agent.vendor-config` | `server/src/agent.py` | Change `CUSTOM_LLM_URL`, `CUSTOM_LLM_MODEL`, STT/TTS vendor, `max_history`, greeting, session parameters. | Run `verify:backend` + `pytest tests`; document new env in `server/.env.example` (never add `PORT`). |
| `llm.persona-fsm` | `server/src/llm.py` | Modify `derive_persona`, `run_agent_turn`, handler functions, SQLite schema, destinations/options, or replace entirely with a real model. | Preserve `/chat/completions` SSE contract + `/health`; keep agora-free; add test cases in `test_handoff.py`. |
| `web.conversation-ui` | `web/src/components/*`, `web/src/lib/conversation.ts` | Customize pre-call, transcript, metrics, connection status, mic, or visualizer UI. | Preserve RTC/RTM lifecycle ownership and transcript UID normalization. |
| `verification.contracts` | `web/scripts/*.ts`, root `package.json` | Add checks for new browser/backend or LLM endpoint boundaries. | Keep checks runnable without live Agora credentials. |

## Invariants

- Browser code calls only `/api/get_config`, `/api/startAgent`, and `/api/stopAgent` for the default flow.
- Next.js owns `/api/*` through rewrites only; no `web/app/api/**/route.ts` for agent/token logic.
- FastAPI owns token generation, `AGORA_APP_CERTIFICATE`, `CUSTOM_LLM_API_KEY`, and agent lifecycle.
- `server/src/llm.py` has no `agora_agent` import; the AST check in `test_llm_mount.py` enforces this.
- The LLM endpoint streams only spoken text — no `tool_call` chunks.
- Persona is always derived from DB + intent; never stored as a field.
- The backend issues one RTC+RTM-capable token for a concrete non-zero UID.

## Stable Contracts

| Contract | Stable shape |
| -------- | ------------ |
| Required backend env | `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `CUSTOM_LLM_URL`, `CUSTOM_LLM_API_KEY` |
| Optional backend env | `CUSTOM_LLM_MODEL`, `AGENT_GREETING`, `ITINERARY_DB_PATH`, `PORT` (env only) |
| Required web deploy env | `AGENT_BACKEND_URL` |
| `GET /api/get_config` | Query `channel?`, `uid?`; returns `data.app_id`, `data.token`, `data.uid`, `data.channel_name`, `data.agent_uid`. |
| `POST /api/startAgent` | Body `{ channelName, rtcUid, userUid, parameters? }`; returns `data.agent_id`, `data.channel_name`, `data.status`. |
| `POST /api/stopAgent` | Body `{ agentId }`; returns `{ code: 0, msg: "success" }`. |
| `POST /llm/chat/completions` | Accepts OpenAI `ChatCompletionRequest` (`stream: true`); returns `text/event-stream` SSE ending with `data: [DONE]`. |
| `GET /llm/health` | Returns `{ "status": "ok", "service": "handoff-mock" }`. |
| Success envelope | `{ "code": 0, "msg": "success", "data": ... }` where the route has data. |
| Verification entry points | `bun run verify:web`, `bun run verify:backend`, `bun run verify:web:proxy`, `bun run verify:local:fastapi`, `bun run verify:local:llm`, `bun run verify:local`. |

## Internal / Subject to Change

- Visual layout, component composition, Tailwind classes, and assets under `web/src/components/`.
- Exact STT/TTS model names and voice IDs, as long as they stay documented extension points.
- In-memory `Agent._sessions` details; the stable behavior is start by channel/user and stop by returned `agent_id`.
- Mock persona logic, destinations, and options in `server/src/llm.py`; the stable surface is the OpenAI SSE contract.
- Verification internals under `web/scripts/`; the stable surface is the root script names and what they assert.
- `agora-agents` SDK minor-version behavior; this recipe lower-bounds `>=2.3.0` but does not freeze every field.

## Related Progressive Disclosure Docs

- `L1/01_setup.md` — setup, env, ngrok, and commands.
- `L1/02_architecture.md` — request flow, persona FSM, and topology.
- `L1/05_workflows.md` — common modification workflows.
- `L1/06_interfaces.md` — route, rewrite, env, and LLM endpoint contracts.
- `L1/L2/handoff_flow.md` — full FSM, SQLite schema, and SSE streaming detail.
- `L1/L2/session_lifecycle.md` — RTC/RTM/session orchestration.
