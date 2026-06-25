# 08 · Security

> Trust boundaries, secret handling, and auth for the handoff recipe.

## Trust boundaries

| Hop                               | Auth                                                                           |
| --------------------------------- | ------------------------------------------------------------------------------ |
| Browser → agent backend           | None in local dev (the `/api/*` rewrite is same-origin).                       |
| Agent backend → Agora cloud       | Token007, generated from `AGORA_APP_ID` + `AGORA_APP_CERTIFICATE`.             |
| Agora cloud → concierge LLM endpoint | `Authorization: Bearer <CUSTOM_LLM_API_KEY>` (Agora cloud forwards it). The mock does not validate it; a production endpoint should. |

## Secret handling

- **Server-only secrets:** `AGORA_APP_CERTIFICATE` and `CUSTOM_LLM_API_KEY` live only in `server/.env.local` and never reach the browser. The browser receives a short-lived token, never the certificate or the LLM key.
- `server/.env.local` is gitignored; `server/.env.example` ships placeholders only.
- Tokens (`generate_convo_ai_token`) expire after 3600s and are minted per `get_config` call for a concrete non-zero UID.

## Co-public surface trade-off

The server at `:8000` is the public endpoint Agora calls (`/llm`). This co-locates the token endpoints (`/get_config`, `/startAgent`, `/stopAgent`) with a publicly reachable path. The App Certificate is only used in-memory to mint tokens — it never crosses a wire. However, the token endpoints are **unauthenticated** in this recipe. Add auth/rate-limiting at the ingress, gateway, or proxy layer before any real deployment.

## CORS

The backend sets `CORSMiddleware` with `allow_origins=["*"]` on both the agent app and the LLM sub-app — open by design for a local/dev recipe. **Lock this down to known origins before any production deployment.**

## Validation

- `Agent.__init__()` raises `ValueError` if `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `CUSTOM_LLM_URL`, or `CUSTOM_LLM_API_KEY` are missing.
- `Agent.start()` rejects empty `channel_name` and non-positive `agent_uid`/`user_uid`.
- Route errors are sanitized: `_log_route_error` logs only non-`None` context; SDK exceptions map to 400/500 without leaking internals.

## Deployment notes

- Set `AGENT_BACKEND_URL` only to a backend you control; the rewrite forwards browser requests there verbatim.
- Set `CUSTOM_LLM_URL` to the same host so Agora cloud and the web client reach the same process.
- The published Docker image is a **single-process backend** (`:8000`); it does not bundle secrets.
- The SQLite itinerary DB (`ITINERARY_DB_PATH`) is local to the process; in Docker it defaults to `/tmp/itinerary.db`.

## Related Deep Dives

- None.
