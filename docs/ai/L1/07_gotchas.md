# 07 · Gotchas

> Non-obvious pitfalls specific to the handoff recipe. Read before changing the agent, LLM endpoint, env, or verify scripts.

## `CUSTOM_LLM_URL` must be public and has no localhost default

Agora cloud (not this backend) calls `CUSTOM_LLM_URL`. There is intentionally **no localhost default** — a localhost URL would let `POST /startAgent` succeed while LLM calls silently fail cloud-side. `Agent.__init__` raises `ValueError` if `CUSTOM_LLM_URL` is unset. For local dev, expose the backend on port 8000 via ngrok and set `CUSTOM_LLM_URL=https://<tunnel>/llm/chat/completions`.

## `CUSTOM_LLM_API_KEY` is required by the vendor

The `CustomLLM` vendor rejects a missing `api_key`. The default `any-key-here` is acceptable for the mock; a real endpoint should validate the bearer token.

## Do not put `PORT` in `server/.env.example`

`verify:local:fastapi` injects a random `PORT` and loads env with `load_dotenv(override=True)`. A `PORT` line in `.env.example` (copied to `.env.local`) would clobber the injected port and break the smoke test.

## `llm.py` must stay agora-free

`test_llm_mount.py` parses `llm.py` with `ast` and asserts no `agora*` root import. Adding any `agora_agent` import to `llm.py` will fail this test. Keep persona logic and SQLite itinerary entirely inside `llm.py`.

## Never stream `tool_call` chunks from the LLM endpoint

Agora ConvoAI expects only spoken text content in the SSE stream. The mock's `run_agent_turn()` materializes all DB work into a plain string before streaming. Do not add `tool_call` deltas — Agora cloud does not handle them.

## Do not store persona as a DB field or session variable

`derive_persona()` is called fresh every turn. Storing persona in the DB or in a session breaks the restart-safe, testable FSM guarantee.

## Keep `/api/*` ownership in rewrites

Adding `web/app/api/**/route.ts` for agent/token logic breaks the boundary — `verify-api-contracts.ts` explicitly fails if a `route.ts` exists under `app/api`. Token logic belongs in `server/`.

## camelCase request fields

`StartAgentRequest` uses `channelName`, `rtcUid`, `userUid` (camelCase) to match the browser client. Renaming one side without the other breaks the contract tests.

## UID normalization in transcripts

`normalizeTranscript` maps `uid === '0'` to the local UID. Token issuance also rejects zero/negative UIDs and generates a concrete one. Preserve both — speaker mapping and tokens depend on concrete UIDs.

## Local calls under a global proxy

Global proxies (Clash, etc.) can break `localhost`/RFC-1918 traffic. Configure the proxy to send `127.0.0.1`, `localhost`, and private ranges DIRECT, or use `socksio` (in `requirements.txt`) plus `all_proxy`.

## Related Deep Dives

- [handoff_flow](L2/handoff_flow.md) — correct FSM wiring and SSE contract.
