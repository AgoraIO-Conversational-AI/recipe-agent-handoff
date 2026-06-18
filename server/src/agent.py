"""
Agent — Travel Concierge Handoff Recipe

High-level API for managing Agora Conversational AI Agents with a Custom LLM.

Instead of using the built-in OpenAI vendor, this recipe configures the agent
to use a custom LLM endpoint (your own proxy server) that is compatible with
the OpenAI Chat Completions API format. The LLM mock implements a 3-persona
handoff FSM (Triage → Booking → Trip Support) derived from intent and SQLite
itinerary state — no session id, no stored persona field.
"""
import logging
import os
from typing import Any, Dict, Optional

from agora_agent import Area, AsyncAgora
from agora_agent.agentkit import Agent as AgoraAgent
from agora_agent.agentkit.vendors import CustomLLM, DeepgramSTT, MiniMaxTTS

logger = logging.getLogger("uvicorn.error")

CUSTOM_LLM_PROMPT = """You are a friendly travel concierge connected to Agora's \
Conversational AI Engine. Your role shifts as the user progresses: first you \
greet and understand where they want to go (Triage), then you search flights and \
book (Booking), then you manage the booked trip (Trip Support). Keep replies \
short — one or two sentences — suitable for voice. Do not mention internal \
persona names to the user."""


class Agent:
    """
    High-level wrapper for Agora Conversational AI Agent with Custom LLM.

    The key difference from the quickstart is that this uses the OpenAI vendor
    with a custom `base_url` pointing to your own OpenAI-compatible endpoint
    (the custom_llm_server.py proxy). The Agora cloud will call your proxy
    for chat completions instead of calling OpenAI directly.

    IMPORTANT: The custom LLM URL must be publicly accessible for the Agora
    Conversational AI Engine (cloud) to reach it. For local development, use
    a tunnel (ngrok, Cloudflare Tunnel) or GitHub Codespaces with public ports.
    """

    def __init__(self):
        self.app_id = os.getenv("AGORA_APP_ID")
        self.app_certificate = os.getenv("AGORA_APP_CERTIFICATE")
        self.greeting = os.getenv(
            "AGENT_GREETING",
            "Hi! I'm your travel concierge. Where would you like to go?",
        )

        # Custom LLM configuration.
        # CUSTOM_LLM_URL is the FULL OpenAI-compatible chat-completions URL and must be
        # PUBLICLY reachable: Agora cloud (not this backend) calls it. For local dev,
        # expose the backend on port 8000 via ngrok; Agora cloud calls /llm/chat/completions.
        # There is intentionally no localhost default: a localhost URL would let the
        # agent "start" while its LLM calls silently fail cloud-side.
        self.custom_llm_url = os.getenv("CUSTOM_LLM_URL")
        self.custom_llm_api_key = os.getenv("CUSTOM_LLM_API_KEY", "any-key-here")
        self.custom_llm_model = os.getenv("CUSTOM_LLM_MODEL", "handoff-mock")

        if not self.app_id or not self.app_certificate:
            raise ValueError("AGORA_APP_ID and AGORA_APP_CERTIFICATE are required")

        if not self.custom_llm_url:
            raise ValueError(
                "CUSTOM_LLM_URL is required (the public chat-completions URL of your "
                "custom LLM endpoint, e.g. https://<tunnel>/chat/completions)"
            )

        if not self.custom_llm_api_key:
            # CustomLLM rejects a missing api_key, and base_url is only valid with a key.
            raise ValueError(
                "CUSTOM_LLM_API_KEY is required when using a custom LLM endpoint"
            )

        self.client = AsyncAgora(
            area=Area.US,
            app_id=self.app_id,
            app_certificate=self.app_certificate,
        )

        # Track active sessions by agent_id
        self._sessions: Dict[str, Any] = {}

    async def start(
        self,
        channel_name: str,
        agent_uid: int,
        user_uid: int,
        output_audio_codec: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start agent with Custom LLM vendor chain."""
        if not channel_name or not str(channel_name).strip():
            raise ValueError("channel_name is required and cannot be empty")
        if agent_uid <= 0:
            raise ValueError("agent_uid is required and cannot be empty")
        if user_uid <= 0:
            raise ValueError("user_uid is required and cannot be empty")

        # ============================================================
        # KEY DIFFERENCE: Use the SDK's CustomLLM vendor
        # ============================================================
        # The base quickstart uses a managed `OpenAI(model="gpt-4o-mini")`.
        # This recipe instead points the LLM stage at our own OpenAI-compatible
        # endpoint (the llm/ server) via the purpose-built `CustomLLM` vendor.
        # CustomLLM stamps `vendor: "custom"` in the wire config and requires
        # both base_url and api_key. Your endpoint can then:
        # - Add custom preprocessing (RAG, context injection)
        # - Route to different models dynamically
        # - Add logging and analytics
        # - Implement custom tool calling
        # ============================================================
        llm = CustomLLM(
            base_url=self.custom_llm_url,
            api_key=self.custom_llm_api_key,
            model=self.custom_llm_model,
            greeting_message=self.greeting,
            failure_message="Please wait a moment.",
            max_history=15,
            max_tokens=1024,
            temperature=0.7,
            top_p=0.95,
        )

        # STT and TTS remain the same as the quickstart
        stt = DeepgramSTT(model="nova-3", language="en")
        tts = MiniMaxTTS(model="speech_2_6_turbo", voice_id="English_captivating_female1")

        parameters = {
            "audio_scenario": "chorus",  # web client — ultra-low-latency chorus profile
            "data_channel": "rtm",
            "enable_error_message": True,
            "enable_metrics": True,
        }
        if isinstance(output_audio_codec, str) and output_audio_codec.strip():
            parameters["output_audio_codec"] = output_audio_codec.strip()

        agora_agent = AgoraAgent(
            client=self.client,
            instructions=CUSTOM_LLM_PROMPT,
            greeting=self.greeting,
            failure_message="Please wait a moment.",
            max_history=50,
            turn_detection={
                "config": {
                    "speech_threshold": 0.5,
                    "start_of_speech": {
                        "mode": "vad",
                        "vad_config": {
                            "interrupt_duration_ms": 160,
                            "prefix_padding_ms": 300,
                        },
                    },
                    "end_of_speech": {
                        "mode": "vad",
                        "vad_config": {
                            "silence_duration_ms": 480,
                        },
                    },
                },
            },
            advanced_features={"enable_rtm": True},
            parameters=parameters,
        )

        agora_agent = (
            agora_agent
            .with_stt(stt)
            .with_llm(llm)
            .with_tts(tts)
        )

        session = agora_agent.create_async_session(
            channel=channel_name,
            agent_uid=str(agent_uid),
            remote_uids=[str(user_uid)],
            enable_string_uid=False,
            idle_timeout=30,
            expires_in=3600,
        )

        logger.info(
            "Starting concierge handoff agent channel=%s agent_uid=%s user_uid=%s llm_url=%s",
            channel_name,
            agent_uid,
            user_uid,
            self.custom_llm_url,
        )

        try:
            agent_id = await session.start()
        except Exception:
            logger.exception(
                "Failed to start Custom LLM agent channel=%s agent_uid=%s user_uid=%s",
                channel_name,
                agent_uid,
                user_uid,
            )
            raise

        # Save session for later stop
        self._sessions[agent_id] = session

        logger.info(
            "Started concierge handoff agent agent_id=%s channel=%s",
            agent_id,
            channel_name,
        )

        return {
            "agent_id": agent_id,
            "channel_name": channel_name,
            "status": "started",
        }

    async def stop(self, agent_id: str) -> None:
        """Stop a running agent. Falls back to the stateless client path."""
        if not agent_id or not str(agent_id).strip():
            raise ValueError("agent_id is required and cannot be empty")

        session = self._sessions.pop(agent_id, None)
        if session:
            try:
                await session.stop()
                logger.info("Stopped agent from active session agent_id=%s", agent_id)
                return
            except Exception:
                logger.warning(
                    "Failed to stop agent from active session; falling back agent_id=%s",
                    agent_id,
                    exc_info=True,
                )

        logger.info("Stopping agent through client.stop_agent agent_id=%s", agent_id)
        await self.client.stop_agent(agent_id)
