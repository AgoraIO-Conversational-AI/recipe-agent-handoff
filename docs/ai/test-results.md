# Progressive Disclosure — Test Results

> Test run for `recipe-agent-handoff` progressive disclosure docs.
> Date: 2026-06-25 · Standard: AgoraIO-Community/ai-devkit progressive-disclosure.

## Step 1 — Structural checks

| Check                                              | Result |
| -------------------------------------------------- | ------ |
| `L0_repo_card.md` ≤ 50 lines                       | Pass (36) |
| All 8 L1 files present                             | Pass |
| Each L1 has purpose blockquote + Related Deep Dives| Pass (8/8) |
| L1 line counts in 80–200 target                    | **Below target** (57–100) — see note |
| L2 `_index.md` present                             | Pass |
| Each L2 opens with "When to Read This" callout     | Pass (2/2) |
| Relative links resolve (`docs/ai/` + AGENTS.md)    | Pass (39/39, 0 broken) |
| AGENTS.md has How to Load / Git Conventions / Doc Commands | Pass |
| Recipe Role corrected to `base`                    | Pass |

**Note on L1 line counts:** files are table-dense and information-complete but
run 57–100 lines, under the 80–200 soft target. The standard favors tables over
prose and warns against bloat, so they were left concise rather than padded.
Accepted deviation; revisit if a section needs more depth.

## Step 2 — pytest (throwaway venv `/tmp/v_handoff`)

Venv created at `/tmp/v_handoff`; deps installed from `server/requirements.txt` +
`server/requirements-dev.txt`; pytest run against `server/tests/`; venv removed.

```
13 passed, 1 warning in 2.97s
```

| File | Collected | Passed |
| ---- | :-------: | :----: |
| `test_agent_construction.py` | 1 | 1 |
| `test_handoff.py` | 5 | 5 |
| `test_llm.py` | 3 | 3 |
| `test_llm_mount.py` | 3 | 3 |
| `test_tools.py` | 1 | 1 |
| **Total** | **13** | **13** |

Warning: `starlette.testclient` httpx deprecation (cosmetic; no test impact).

## Step 3 — Question runs

Questions span five standard categories. Each answer was checked against the
repo source before being marked Pass. "Level" is the lowest disclosure level
that fully answers the question.

### Setup & Build

| # | Question | Expected answer | Source of truth | Level | Status |
|---|----------|-----------------|-----------------|-------|--------|
| 1 | How do I install and run it locally? | `bun run setup`, expose backend via ngrok, set `CUSTOM_LLM_URL`, then `bun run dev` (backend :8000 + web :3000). | `L1/01_setup.md` ↔ `package.json` scripts, `README.md` | L1 | Pass |
| 2 | Which env vars are required? | `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `CUSTOM_LLM_URL`, `CUSTOM_LLM_API_KEY`. | `L1/01_setup.md`/`06_interfaces.md` ↔ `agent.py`, `.env.example` | L1 | Pass |
| 3 | Is this zero-key? | Yes — no external LLM API key needed; the mock concierge endpoint is bundled in the same process. | `L1/01_setup.md` ↔ `README.md`, `llm.py` header | L1 | Pass |

### Test & Run

| # | Question | Expected answer | Source of truth | Level | Status |
|---|----------|-----------------|-----------------|-------|--------|
| 4 | How do I run backend tests without cloud creds? | `cd server && pytest tests -v`; `conftest.py` fakes env + SDK session; FSM tests use temp SQLite DBs. | `L1/04_conventions.md`, `01_setup.md` ↔ `tests/conftest.py`, `test_handoff.py` | L1 | Pass (ran: 13 passed) |
| 5 | What's the narrowest gate for a web-only change? | `bun run verify:web`. | `L1/05_workflows.md` ↔ `package.json` | L1 | Pass |
| 6 | What does `verify:local:llm` do? | Spawns the LLM endpoint standalone and asserts the OpenAI SSE contract (role chunk, content chunks, `finish_reason: stop`, `data: [DONE]`, non-streaming 400). | `L1/03_code_map.md`, `05_workflows.md` ↔ `web/scripts/verify-local-llm.ts` | L1 | Pass |

### Conventions

| # | Question | Expected answer | Source of truth | Level | Status |
|---|----------|-----------------|-----------------|-------|--------|
| 7 | What response shape do backend routes use? | `{ code, msg, data }`; `data` only when there's a payload. Only agent backend routes; the LLM endpoint uses OpenAI SSE format. | `L1/04_conventions.md`, `06_interfaces.md` ↔ `server.py` | L1 | Pass |
| 8 | Why can't `llm.py` import `agora_agent`? | `test_llm_mount.py` checks via AST; the LLM endpoint must be provider-agnostic and replaceable. | `L1/04_conventions.md`, `07_gotchas.md` ↔ `tests/test_llm_mount.py` | L1 | Pass |
| 9 | What are the commit/branch conventions? | Conventional commits `type: description`; branches `type/short-description`; no AI tool names; no Co-Authored-By. | `AGENTS.md` Git Conventions | L1 | Pass |

### Development

| # | Question | Expected answer | Source of truth | Level | Status |
|---|----------|-----------------|-----------------|-------|--------|
| 10 | How do I replace the mock with a real LLM? | Edit `server/src/llm.py`; keep `POST /chat/completions` SSE contract + `GET /health`; no `agora_agent` import; add env vars to `.env.example`. | `L1/05_workflows.md` ↔ source | L1 | Pass |
| 11 | Why must `CUSTOM_LLM_URL` be public and have no localhost default? | Agora cloud (not this backend) calls the LLM endpoint; a localhost URL would let `/startAgent` succeed while LLM calls silently fail. | `L1/07_gotchas.md` ↔ `agent.py` `__init__` | L1 | Pass |
| 12 | Where does token generation live? | `server/` (`generate_convo_ai_token` in `server.py`); App Certificate stays server-only. | `L1/02_architecture.md`, `08_security.md` ↔ `server.py` | L1 | Pass |

### Deep Dive

| # | Question | Expected answer | Source of truth | Level | Status |
|---|----------|-----------------|-----------------|-------|--------|
| 13 | What signals does `derive_persona()` use and in what priority? | (1) SQLite booking row exists → `trip_support`; (2) booking keyword in user text → `booking`; (3) else → `triage`. | `L2/handoff_flow.md` ↔ `llm.py` `derive_persona` | L2 | Pass |
| 14 | What is the full SSE streaming format the LLM endpoint must return? | Role chunk (assistant role) → content chunks (one per word, 50ms delay) → stop chunk (`finish_reason: stop`) → `data: [DONE]`. Non-streaming requests return 400. | `L2/handoff_flow.md` ↔ `llm.py` `generate()` + `test_llm.py` | L2 | Pass |
| 15 | How does stop survive a backend restart? | `_sessions` is in-memory; missing session falls back to `client.stop_agent(agent_id)`. | `L2/session_lifecycle.md` ↔ `agent.py` `stop()` | L2 | Pass |

## Step 4 — Analysis

- All 15 questions answered at the expected disclosure level (12 at L1, 3 at L2).
  No "correct but needed L2 unnecessarily" or "wrong/missing L2" cases.
- No missing-coverage findings; no broken references (39/39 links pass).
- One soft deviation: L1 line counts below the 80–200 target (accepted; concise/table-dense).

## Step 5 — Summary

| Category       | Questions | Pass | Notes |
| -------------- | :-------: | :--: | ----- |
| Setup & Build  | 3 | 3 | — |
| Test & Run     | 3 | 3 | backend tests executed: 13 passed |
| Conventions    | 3 | 3 | — |
| Development    | 3 | 3 | — |
| Deep Dive      | 3 | 3 | resolved at L2 as designed |
| **Total**      | **15** | **15** | — |

## Step 6 — Fixes / Retest

No failing questions; no fixes required. Evidence executed during this run:

- `pytest tests -v` (throwaway venv `/tmp/v_handoff`, Python 3.14.4) → `13 passed`.
- Relative link check → `39 checked, 0 broken`.
- Structural checks → all pass (see Step 1 table).
