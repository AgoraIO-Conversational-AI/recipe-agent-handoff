"""
Tool-Calling LLM Server — Mock Implementation

This server demonstrates how to implement an OpenAI-compatible Chat Completions
endpoint that works with Agora Conversational AI Engine.

Key points:
- Must implement POST /chat/completions
- Must support streaming responses (Server-Sent Events)
- Must follow OpenAI Chat Completions response format
- Agora cloud sends Authorization header with the api_key you configured

This mock version returns pre-defined responses so you can test the full
voice pipeline (STT → Custom LLM → TTS) without any external LLM dependency.

Replace the mock logic with your own:
- Call your own model (local or remote)
- Add RAG context injection
- Implement tool calling
- Route to different models based on content
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
    title="Tool-Calling LLM Server (Mock)",
    description=(
        "OpenAI-compatible Chat Completions endpoint for Agora Conversational AI Engine. "
        "This mock implementation demonstrates tool calling via an internal log_message tool."
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
# Tool logic (mock, zero-key) — internal orchestration over SQLite
# -----------------------------------------------------------------------------
# Two tools execute HERE, inside the endpoint, which owns a SQLite message log:
#   log_message(conn, text)  — persist a note
#   list_messages(conn)      — read recent notes back
# run_agent_turn() routes by keyword and streams only the final answer; Agora
# cloud never sees a tool_call. A real endpoint would run the OpenAI tool-call
# loop against your model instead of this heuristic.
# =============================================================================

DB_PATH = os.getenv("MESSAGE_DB_PATH") or os.path.join(_base_dir, "messages.db")

_LOG_TRIGGERS = ("log", "print", "note", "record", "console")
# Recall is checked BEFORE logging so "what have I noted" reads back instead of
# logging a new note. Keep these phrases distinct from everyday note text; this
# is a keyword mock, so an utterance that mixes both (e.g. logging the word
# "list") may route to recall — a real model would decide.
_RECALL_TRIGGERS = (
    "list", "read back", "remind me", "what have i", "what i have",
    "what did i", "show me my", "my notes",
)


def get_db(path: str = DB_PATH) -> "sqlite3.Connection":
    # check_same_thread=False: a fresh connection is created and used per request;
    # this keeps it safe if the sync DB work is ever moved to a threadpool.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at REAL NOT NULL
        )"""
    )
    conn.commit()
    return conn


def log_message(conn: "sqlite3.Connection", text: str) -> str:
    """Tool: persist a message and return a confirmation."""
    conn.execute(
        "INSERT INTO messages (text, created_at) VALUES (?, ?)", (text, time.time())
    )
    conn.commit()
    logger.info("TOOL log_message recorded: %s", text)
    return f'Logged your message: "{text}".'


def list_messages(conn: "sqlite3.Connection") -> str:
    """Tool: read back the most recent logged messages."""
    rows = conn.execute(
        "SELECT text FROM messages ORDER BY created_at DESC, id DESC LIMIT 10"
    ).fetchall()
    if not rows:
        return "You haven't logged any messages yet."
    items = "; ".join(row[0] for row in rows)
    plural = "s" if len(rows) != 1 else ""
    return f"You have {len(rows)} logged message{plural}: {items}."


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


def _message_to_log(user_text: str) -> str:
    if ":" in user_text:
        tail = user_text.split(":", 1)[1].strip()
        if tail:
            return tail
    return user_text.strip()


def run_agent_turn(conn: "sqlite3.Connection", messages: list) -> str:
    """Route the turn to a tool (recall or log) and return the final text."""
    user_text = _extract_last_user_text(messages)
    lowered = user_text.lower()
    if any(trigger in lowered for trigger in _RECALL_TRIGGERS):
        return list_messages(conn)
    if any(trigger in lowered for trigger in _LOG_TRIGGERS):
        confirmation = log_message(conn, _message_to_log(user_text))
        return f"{confirmation} Anything else you'd like me to note?"
    return (
        "I'm a voice assistant that can log messages and read them back. Say "
        "'log this: buy milk' to save one, or 'list my notes' to hear them."
    )


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
    return {"status": "ok", "service": "custom-llm-mock"}


if __name__ == "__main__":
    port = int(os.getenv("CUSTOM_LLM_PORT", "8001"))
    logger.info(f"Starting Tool-Calling LLM Server (Mock) on port {port}")
    logger.info("This server returns mock responses — no LLM API key needed.")
    logger.info(f"Endpoint: http://0.0.0.0:{port}/chat/completions")
    uvicorn.run(app, host="0.0.0.0", port=port)
