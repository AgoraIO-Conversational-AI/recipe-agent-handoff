"""
Travel Concierge Handoff LLM Server — Mock Implementation

This server demonstrates how to implement an OpenAI-compatible Chat Completions
endpoint that works with Agora Conversational AI Engine.

Key points:
- Must implement POST /chat/completions
- Must support streaming responses (Server-Sent Events)
- Must follow OpenAI Chat Completions response format
- Agora cloud sends Authorization header with the api_key you configured

This mock implements a 3-persona handoff FSM for a travel concierge:
  Triage → Booking → Trip Support
Persona is derived at each turn from the user's intent and the SQLite itinerary
state — no session id, no stored persona field. Zero external LLM key needed.

Replace the mock logic with your own:
- Call your own model (local or remote)
- Persist itinerary to a real database
- Add multi-destination support
- Route to different models per persona
"""
import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from typing import Dict, List, Optional, Union

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Load environment variables.
# override=False so an explicitly-exported value (e.g. CUSTOM_LLM_PORT injected by
# the verify:local:llm harness, or a process manager) takes precedence over a
# checked-in .env.local. In normal `dev` no port is exported, so .env.local wins.
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_base_dir, ".env.local"), override=False)
load_dotenv(os.path.join(_base_dir, ".env"), override=False)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Travel Concierge Handoff LLM Server (Mock)",
    description=(
        "OpenAI-compatible Chat Completions endpoint for Agora Conversational AI Engine. "
        "This mock implements a 3-persona Travel Concierge Handoff FSM (Triage → Booking → "
        "Trip Support) derived from intent and SQLite itinerary state. Zero external key needed."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Request Models — These match what Agora ConvoAI Engine sends
# =============================================================================

class TextContent(BaseModel):
    type: str = "text"
    text: str


class SystemMessage(BaseModel):
    role: str = "system"
    content: Union[str, List[str]]


class UserMessage(BaseModel):
    role: str = "user"
    content: Union[str, List[Union[TextContent, Dict]]]


class AssistantMessage(BaseModel):
    role: str = "assistant"
    content: Union[str, List[TextContent], None] = None
    tool_calls: Optional[List[Dict]] = None


class ToolMessage(BaseModel):
    role: str = "tool"
    content: Union[str, List[str]]
    tool_call_id: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]]
    stream: bool = True
    stream_options: Optional[Dict] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[Union[str, Dict]] = None
    response_format: Optional[Dict] = None


# =============================================================================
# Persona handoff logic (mock, zero-key) — 3-persona FSM over SQLite itinerary
# -----------------------------------------------------------------------------
# Personas: triage → booking → trip_support
# Persona is DERIVED each turn from intent keywords + booked-trip DB state.
# No session id, no stored persona field.
# run_agent_turn() executes the right persona handler and returns only the final
# spoken reply; Agora cloud never sees a tool_call.
# =============================================================================

DB_PATH = os.getenv("ITINERARY_DB_PATH") or os.path.join(_base_dir, "itinerary.db")

OPTIONS = {
    "paris": [(1, "morning", 420), (2, "midday", 480), (3, "evening", 390)],
    "tokyo": [(1, "morning", 910), (2, "midday", 870), (3, "evening", 940)],
    "rome":  [(1, "morning", 360), (2, "midday", 410), (3, "evening", 330)],
}
DESTINATIONS = tuple(OPTIONS.keys())

_BOOK_KW = ("book", "flight", "trip", "travel", "fly", "go to", "vacation", "holiday")
_RECALL_KW = ("itinerary", "my trip", "my booking", "what did i book", "what's booked")
_CANCEL_KW = ("cancel", "scrap", "delete my")
_MODIFY_KW = ("change", "modify", "reschedule", "move my")
_CHOICE_ORD = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}


def get_db(path: str = DB_PATH) -> "sqlite3.Connection":
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS itinerary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destination TEXT NOT NULL, slot TEXT NOT NULL,
            price INTEGER NOT NULL, created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS context (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )"""
    )
    conn.commit()
    return conn


def _booked(conn) -> Optional[tuple]:
    return conn.execute(
        "SELECT destination, slot, price FROM itinerary ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _set_context(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO context (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()


def _get_context(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM context WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def derive_persona(conn, user_text: str) -> str:
    if _booked(conn):
        return "trip_support"
    if any(k in user_text.lower() for k in _BOOK_KW):
        return "booking"
    return "triage"


def _extract_last_user_text(messages: list) -> str:
    for msg in reversed(messages):
        if getattr(msg, "role", None) == "user":
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    return first.get("text", "")
                if hasattr(first, "text"):
                    return first.text
            return ""
    return ""


def _find_destination(messages: list, conn=None) -> Optional[str]:
    for msg in reversed(messages):
        if getattr(msg, "role", None) == "user":
            text = _extract_last_user_text([msg]).lower()
            for dest in DESTINATIONS:
                if dest in text:
                    return dest
    if conn is not None:
        return _get_context(conn, "pending_dest")
    return None


def _match_choice(text: str, opts: list) -> Optional[tuple]:
    low = text.lower()
    for word, idx in _CHOICE_ORD.items():
        if word in low and idx < len(opts):
            return opts[idx]
    for opt in opts:
        if opt[1] in low:
            return opt
    if "cheapest" in low:
        return min(opts, key=lambda o: o[2])
    if "earliest" in low or "morning" in low:
        return opts[0]
    return None


def search_trips(dest: str) -> str:
    opts = OPTIONS[dest]
    listing = ", ".join(f"{slot} for ${price}" for _id, slot, price in opts)
    return (f"Here are flights to {dest.title()}: {listing}. "
            "Which would you like — say the time or 'the cheapest'?")


def book_trip(conn, dest: str, choice_text: str) -> str:
    pick = _match_choice(choice_text, OPTIONS[dest])
    if not pick:
        return ("Which option would you like? You can say a time like 'the morning "
                "one' or 'the cheapest'.")
    conn.execute(
        "INSERT INTO itinerary (destination, slot, price, created_at) VALUES (?,?,?,?)",
        (dest, pick[1], pick[2], time.time()),
    )
    conn.commit()
    return (f"Booked your {pick[1]} flight to {dest.title()} for ${pick[2]}. "
            "I'm handing you to trip support — ask me to show, change, or cancel it.")


def get_itinerary(conn) -> str:
    row = _booked(conn)
    if not row:
        return "You don't have a trip booked yet. Tell me where you'd like to go."
    return f"Your itinerary: {row[1]} flight to {row[0].title()} for ${row[2]}."


def cancel_booking(conn) -> str:
    conn.execute("DELETE FROM itinerary")
    conn.commit()
    return "Your trip is cancelled. Anything else — I can help you book a new one."


def modify_booking(conn, text: str) -> str:
    row = _booked(conn)
    if not row:
        return "There's no trip to change yet."
    pick = _match_choice(text, OPTIONS[row[0]])
    if not pick:
        return f"Your current trip is the {row[1]} flight to {row[0].title()}. Which time would you like instead?"
    conn.execute("DELETE FROM itinerary")
    conn.execute(
        "INSERT INTO itinerary (destination, slot, price, created_at) VALUES (?,?,?,?)",
        (row[0], pick[1], pick[2], time.time()),
    )
    conn.commit()
    return f"Updated your {row[0].title()} trip to the {pick[1]} flight for ${pick[2]}."


def run_agent_turn(conn: "sqlite3.Connection", messages: list) -> str:
    """Route the turn to the active persona and return the spoken reply."""
    user_text = _extract_last_user_text(messages)
    low = user_text.lower()
    persona = derive_persona(conn, user_text)
    if persona == "trip_support":
        if any(k in low for k in _CANCEL_KW):
            return cancel_booking(conn)
        if any(k in low for k in _MODIFY_KW):
            return modify_booking(conn, user_text)
        if any(k in low for k in _RECALL_KW):
            return get_itinerary(conn)
        return get_itinerary(conn) + " I can change or cancel it for you."
    if any(k in low for k in _RECALL_KW):
        return get_itinerary(conn)
    if persona == "booking":
        dest = _find_destination(messages, conn)
        if dest:
            _set_context(conn, "pending_dest", dest)
            if _match_choice(user_text, OPTIONS[dest]):
                return book_trip(conn, dest, user_text)
            return search_trips(dest)
        return ("Welcome to booking! Where would you like to fly — I can search Paris, "
                "Tokyo, or Rome.")
    return ("Hi, I'm your travel concierge. Tell me where you'd like to go and I'll "
            "connect you to booking.")


# =============================================================================
# Streaming Response — Must follow OpenAI SSE format exactly
# =============================================================================
# Agora ConvoAI Engine expects:
# 1. Each chunk as "data: {json}\n\n"
# 2. Final "data: [DONE]\n\n"
# 3. Each chunk has: id, object, created, model, choices[{delta, index, finish_reason}]
# =============================================================================

def make_chunk(chunk_id: str, model: str, content: str, finish_reason=None) -> str:
    """Build a single SSE chunk in OpenAI format."""
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model or "mock-model",
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def make_role_chunk(chunk_id: str, model: str) -> str:
    """First chunk that sets the assistant role."""
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model or "mock-model",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n"


@app.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    OpenAI-compatible chat completions endpoint.

    This is the endpoint that Agora Conversational AI Engine calls.
    It must:
    - Accept the OpenAI Chat Completions request format
    - Return streaming SSE responses in OpenAI chunk format
    - End with "data: [DONE]"
    """
    logger.info(
        f"Received request: model={request.model}, "
        f"messages={len(request.messages)}, stream={request.stream}"
    )

    # Agora ConvoAI always uses streaming
    if not request.stream:
        raise HTTPException(
            status_code=400,
            detail="Only streaming mode is supported. Set stream=true.",
        )

    # Run the agent turn (internal tool loop). The tool's DB work fully
    # materializes the reply string before we close the connection, so the
    # streaming generator below never touches the DB.
    conn = get_db()
    try:
        response_text = run_agent_turn(conn, request.messages)
    finally:
        conn.close()
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    model = request.model or "mock-model"

    async def generate():
        """Stream the response word by word to simulate real LLM behavior."""
        # First chunk: role
        yield make_role_chunk(chunk_id, model)

        # Stream content word by word with small delays (simulates token generation)
        words = response_text.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else f" {word}"
            yield make_chunk(chunk_id, model, token)
            await asyncio.sleep(0.05)  # 50ms per token, ~realistic speed

        # Final chunk: finish_reason
        yield make_chunk(chunk_id, model, "", finish_reason="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "service": "handoff-mock"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting Travel Concierge Handoff LLM Server (Mock) on port {port}")
    logger.info("This server returns mock responses — no LLM API key needed.")
    logger.info(f"Endpoint: http://0.0.0.0:{port}/chat/completions")
    uvicorn.run(app, host="0.0.0.0", port=port)
