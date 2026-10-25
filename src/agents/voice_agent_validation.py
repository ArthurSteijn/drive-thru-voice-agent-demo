"""
DriveThru Voice Agent Validation Script — AIProjectClient Voice Agents Runtime.

Talk to the DriveThru ordering agent using your microphone and speakers.
Uses the Azure AI Foundry Voice Agents realtime client (AIProjectClient).

Prerequisites:
  - Agent created and enabled via: python -m src.agents.create_voice_agent
  - .env configured with PROJECT_ENDPOINT (or VOICELIVE_ENDPOINT), AGENT_NAME, PROJECT_NAME
  - az login completed (Entra ID required for agent mode)
  - Audio input/output devices available (PyAudio installed)

Usage:
  python -m src.agents.voice_agent_validation
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import queue
import signal
import sys
import uuid
from datetime import datetime
from typing import Any, Optional, Union, cast

from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
import websockets

from src.backend.config import (
    build_voice_agent_headers,
    build_voice_agent_ws_url,
    get_azure_token,
    resolve_project_endpoint,
)
from src.backend.tool_dispatcher import dispatch_tool

try:
    import pyaudio
except ImportError:
    pyaudio = None  # type: ignore[assignment]

# ── Environment & logging setup ─────────────────────────────────────

_script_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_script_dir, "../.."))
load_dotenv(os.path.join(_repo_root, ".env"), override=True)

# Logs directory at repo root
_logs_dir = os.path.join(_repo_root, "logs")
os.makedirs(_logs_dir, exist_ok=True)

_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_conversation_logfile = f"{_timestamp}_conversation.log"

logging.basicConfig(
    filename=os.path.join(_logs_dir, f"{_timestamp}_voicelive.log"),
    filemode="w",
    format="%(asctime)s:%(name)s:%(levelname)s:%(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Event Normalization Helper ──────────────────────────────────────


def extract_event_dict(event: Any) -> dict[str, Any]:
    """Normalize a typed Voice Agent SDK event or mapping into a plain dict."""
    if isinstance(event, dict):
        return event
    if hasattr(event, "as_dict"):
        return dict(event.as_dict())
    if hasattr(event, "__dict__"):
        return dict(event.__dict__)
    return {"type": getattr(event, "type", "")}


# ── WebSocket Adapter Fallback ──────────────────────────────────────


class WebSocketVoiceAgentConnectionAdapter:
    """Adapts websockets connection to Realtime connection resource interface."""

    class _InputAudioBuffer:
        def __init__(self, ws: Any) -> None:
            self._ws = ws

        async def append(self, *, audio: Union[str, bytes], **kwargs: Any) -> None:
            data = (
                audio
                if isinstance(audio, str)
                else base64.b64encode(audio).decode("utf-8")
            )
            await self._ws.send(
                json.dumps({"type": "input_audio_buffer.append", "audio": data})
            )

    class _ConversationItem:
        def __init__(self, ws: Any) -> None:
            self._ws = ws

        async def create(self, *, item: Any, **kwargs: Any) -> None:
            payload = extract_event_dict(item) if not isinstance(item, dict) else item
            await self._ws.send(
                json.dumps({"type": "conversation.item.create", "item": payload})
            )

    class _Conversation:
        def __init__(self, ws: Any) -> None:
            self.item = WebSocketVoiceAgentConnectionAdapter._ConversationItem(ws)

    class _Response:
        def __init__(self, ws: Any) -> None:
            self._ws = ws

        async def create(self, **kwargs: Any) -> None:
            await self._ws.send(json.dumps({"type": "response.create"}))

        async def cancel(self, **kwargs: Any) -> None:
            await self._ws.send(json.dumps({"type": "response.cancel"}))

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self.input_audio_buffer = self._InputAudioBuffer(ws)
        self.conversation = self._Conversation(ws)
        self.response = self._Response(ws)

    def __aiter__(self) -> WebSocketVoiceAgentConnectionAdapter:
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            raw = await self._ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception:
            raise StopAsyncIteration

    async def close(self) -> None:
        try:
            await self._ws.close()
        except Exception:
            pass


# ── Audio Processor ─────────────────────────────────────────────────


class AudioProcessor:
    """
    Handles real-time audio capture and playback for the voice assistant.

    Threading architecture:
    - Main thread: Event loop and UI
    - Capture thread: PyAudio input stream reading (callback-based)
    - Playback thread: PyAudio output stream writing (callback-based)
    """

    loop: asyncio.AbstractEventLoop

    class AudioPlaybackPacket:
        """Represents a packet that can be sent to the audio playback queue."""

        def __init__(self, seq_num: int, data: Optional[bytes]):
            self.seq_num = seq_num
            self.data = data

    def __init__(self, connection: Any) -> None:
        if pyaudio is None:
            raise RuntimeError(
                "PyAudio is not installed. Audio capture and playback requires PyAudio."
            )
        self.connection = connection
        self.audio = pyaudio.PyAudio()

        # Audio configuration — PCM16, 24kHz, mono
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 24000
        self.chunk_size = 1200  # 50ms at 24kHz

        # Capture state
        self.input_stream: Optional[pyaudio.Stream] = None

        # Playback state
        self.playback_queue: queue.Queue[AudioProcessor.AudioPlaybackPacket] = queue.Queue()
        self.playback_base = 0
        self.next_seq_num = 0
        self.output_stream: Optional[pyaudio.Stream] = None

        logger.info("AudioProcessor initialized with 24kHz PCM16 mono audio")

    def start_capture(self) -> None:
        """Start capturing audio from microphone."""

        def _capture_callback(in_data, _frame_count, _time_info, _status_flags):
            audio_base64 = base64.b64encode(in_data).decode("utf-8")
            asyncio.run_coroutine_threadsafe(
                self.connection.input_audio_buffer.append(audio=audio_base64),
                self.loop,
            )
            return (None, pyaudio.paContinue)

        if self.input_stream:
            return

        self.loop = asyncio.get_event_loop()

        try:
            self.input_stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=_capture_callback,
            )
            logger.info("Started audio capture")
        except Exception:
            logger.exception("Failed to start audio capture")
            raise

    def start_playback(self) -> None:
        """Initialize audio playback system."""
        if self.output_stream:
            return

        remaining = bytes()

        def _playback_callback(_in_data, frame_count, _time_info, _status_flags):
            nonlocal remaining
            frame_count *= pyaudio.get_sample_size(pyaudio.paInt16)

            out = remaining[:frame_count]
            remaining = remaining[frame_count:]

            while len(out) < frame_count:
                try:
                    packet = self.playback_queue.get_nowait()
                except queue.Empty:
                    out = out + bytes(frame_count - len(out))
                    continue
                except Exception:
                    logger.exception("Error in audio playback")
                    raise

                if not packet or not packet.data:
                    logger.info("End of playback queue.")
                    break

                if packet.seq_num < self.playback_base:
                    if len(remaining) > 0:
                        remaining = bytes()
                    continue

                num_to_take = frame_count - len(out)
                out = out + packet.data[:num_to_take]
                remaining = packet.data[num_to_take:]

            if len(out) >= frame_count:
                return (out, pyaudio.paContinue)
            else:
                return (out, pyaudio.paComplete)

        try:
            self.output_stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                output=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=_playback_callback,
            )
            logger.info("Audio playback system ready")
        except Exception:
            logger.exception("Failed to initialize audio playback")
            raise

    def _get_and_increase_seq_num(self) -> int:
        seq = self.next_seq_num
        self.next_seq_num += 1
        return seq

    def queue_audio(self, audio_data: Optional[bytes]) -> None:
        """Queue audio data for playback."""
        self.playback_queue.put(
            AudioProcessor.AudioPlaybackPacket(
                seq_num=self._get_and_increase_seq_num(),
                data=audio_data,
            )
        )

    def skip_pending_audio(self) -> None:
        """Skip current audio in playback queue (barge-in)."""
        self.playback_base = self._get_and_increase_seq_num()

    def shutdown(self) -> None:
        """Clean up audio resources."""
        if self.input_stream:
            try:
                self.input_stream.stop_stream()
                self.input_stream.close()
            except Exception:
                pass
            self.input_stream = None
        logger.info("Stopped audio capture")

        if self.output_stream:
            self.skip_pending_audio()
            self.queue_audio(None)
            try:
                self.output_stream.stop_stream()
                self.output_stream.close()
            except Exception:
                pass
            self.output_stream = None
        logger.info("Stopped audio playback")

        if self.audio:
            try:
                self.audio.terminate()
            except Exception:
                pass
        logger.info("Audio processor cleaned up")


# ── Voice Assistant ─────────────────────────────────────────────────


class DriveThruVoiceAssistant:
    """
    DriveThru voice assistant using AIProjectClient with Foundry Voice Agent.

    Uses strongly-typed agent configuration and event normalization.
    Collects conversation logs for review and testing.
    """

    def __init__(
        self,
        endpoint: str,
        credential: Any,
        voice: str,
        agent_name: str,
        project_name: str,
        agent_version: Optional[str] = None,
        conversation_id: Optional[str] = None,
        foundry_resource_override: Optional[str] = None,
        agent_authentication_identity_client_id: Optional[str] = None,
    ):
        self.endpoint = endpoint
        self.credential = credential
        self.voice = voice
        self.agent_name = agent_name
        self.project_name = project_name

        # Build agent configuration dictionary
        self.agent_config: dict[str, Any] = {
            "agent_name": agent_name,
            "agent_version": agent_version if agent_version else None,
            "project_name": project_name,
            "conversation_id": conversation_id if conversation_id else None,
            "foundry_resource_override": (
                foundry_resource_override if foundry_resource_override else None
            ),
            "authentication_identity_client_id": (
                agent_authentication_identity_client_id
                if agent_authentication_identity_client_id and foundry_resource_override
                else None
            ),
        }

        self.connection: Any = None
        self.audio_processor: Optional[AudioProcessor] = None
        self.session_ready = False
        self.greeting_sent = False
        self._active_response = False
        self._response_api_done = False
        self.current_response_id: Optional[str] = None
        self.cancelled_response_ids: set[str] = set()
        self.agent_speaking = False
        self.session_id: Optional[str] = None

    async def start(self) -> None:
        """Start the voice assistant session using AIProjectClient (or fallback)."""
        project_endpoint = resolve_project_endpoint(
            endpoint=self.endpoint,
            project_name=self.agent_config.get("project_name"),
        )
        logger.info(
            "Connecting to Voice Agent at %s with agent %s (version=%s)",
            project_endpoint,
            self.agent_name,
            self.agent_config.get("agent_version"),
        )

        try:
            # First attempt: native AIProjectClient beta realtime connection
            try:
                async with AIProjectClient(
                    endpoint=project_endpoint,
                    credential=self.credential,
                    allow_preview=True,
                ) as client:
                    if (
                        hasattr(client, "beta")
                        and hasattr(client.beta, "voice_agents")
                        and hasattr(client.beta.voice_agents, "realtime")
                    ):
                        async with client.beta.voice_agents.realtime.connect(
                            agent_name=self.agent_name,
                        ) as connection:
                            await self._run_session(connection)
                            return
                    raise AttributeError(
                        "client.beta.voice_agents.realtime is not available"
                    )
            except Exception as e:
                logger.warning(
                    "AIProjectClient voice_agents.realtime.connect unavailable or failed (%s); "
                    "falling back to websockets",
                    e,
                )

            # Fallback attempt: direct websockets connection
            if hasattr(self.credential, "get_token"):
                token_res = self.credential.get_token("https://ai.azure.com/.default")
                if asyncio.iscoroutine(token_res):
                    token_obj = await token_res
                else:
                    token_obj = token_res
                access_token = token_obj.token
            else:
                access_token = get_azure_token()

            session_id = f"cli-{uuid.uuid4().hex}"
            ws_url = build_voice_agent_ws_url(
                endpoint=project_endpoint,
                agent_name=self.agent_name,
                session_id=session_id,
            )
            headers = build_voice_agent_headers(access_token)
            async with websockets.connect(ws_url, additional_headers=headers) as ws:
                connection = WebSocketVoiceAgentConnectionAdapter(ws)
                await self._run_session(connection)
        finally:
            if self.audio_processor:
                self.audio_processor.shutdown()

    async def _run_session(self, connection: Any) -> None:
        """Run the active voice assistant session with the established connection."""
        self.connection = connection
        ap = AudioProcessor(connection)
        self.audio_processor = ap

        # In Foundry Voice Agent architecture (kind="voice"), all session settings
        # live in the versioned VoiceAgentDefinition on the server. No session.update needed!
        ap.start_playback()

        logger.info("Voice assistant ready! Start speaking...")
        print("\n" + "=" * 65)
        print("  DRIVETHRU VOICE AGENT VALIDATION")
        print("  Start speaking to place an order")
        print("  Press Ctrl+C to exit")
        print("=" * 65 + "\n")

        await self._process_events()

    async def _process_events(self) -> None:
        """Process events from the Voice Agent connection."""
        try:
            conn = self.connection
            if conn is None:
                raise RuntimeError("Connection must be established before processing events")
            async for event in conn:
                await self._handle_event(event)
        except Exception:
            logger.exception("Error processing events")
            raise

    async def _handle_event(self, event: Any) -> None:
        """Handle different types of events from Voice Agent."""
        ev = extract_event_dict(event)
        etype = ev.get("type", "")
        logger.debug("Received event: %s", etype)

        ap = self.audio_processor
        conn = self.connection
        if ap is None or conn is None:
            raise RuntimeError("AudioProcessor and Connection must be initialized")

        if etype in ("session.updated", "session.created"):
            session_data = ev.get("session") or {}
            if hasattr(session_data, "as_dict"):
                session_dict = session_data.as_dict()
            elif isinstance(session_data, dict):
                session_dict = session_data
            else:
                session_dict = getattr(session_data, "__dict__", {}) or {}

            session_id = session_dict.get("id") or getattr(session_data, "id", "")
            if session_id:
                self.session_id = session_id
                logger.info("Session ready: %s", session_id)
            self.session_ready = True

            agent_info = session_dict.get("agent", {}) or {}
            voice_info = session_dict.get("voice", {}) or {}
            await _write_conversation_log(
                "\n".join(
                    [
                        f"SessionID: {session_id}",
                        f"Agent Name: {agent_info.get('name', self.agent_name)}",
                        f"Voice Name: {voice_info.get('name', self.voice) if isinstance(voice_info, dict) else voice_info}",
                        "",
                    ]
                )
            )

            # Proactive greeting — the agent will welcome the customer
            if not self.greeting_sent:
                self.greeting_sent = True
                logger.info("Sending proactive greeting request")
                try:
                    await conn.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "system",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "Welcome the customer to DriveThru drive-through "
                                        "in a friendly bilingual greeting (English and Dutch). "
                                        "Ask what they would like to order today."
                                    ),
                                }
                            ],
                        }
                    )
                    await conn.response.create()
                except Exception:
                    logger.exception("Failed to send proactive greeting request")

            # Start audio capture once session is ready
            ap.start_capture()

        elif etype == "conversation.created":
            conv = ev.get("conversation") or {}
            conv_id = ev.get("conversation_id") or (
                conv.get("id") if isinstance(conv, dict) else getattr(conv, "id", "")
            )
            if conv_id:
                logger.info("Voice Agent conversation id: %s", conv_id)

        elif etype == "conversation.item.input_audio_transcription.completed":
            transcript = ev.get("transcript", "")
            print(f"  You said:\t{transcript}")
            await _write_conversation_log(f"User Input:\t{transcript}")

        elif etype in ("response.text.done", "response.output_item.done"):
            text = ev.get("text", "")
            if text:
                print(f"  Agent (text):\t{text}")
                await _write_conversation_log(f"Agent Text Response:\t{text}")

        elif etype in ("response.audio_transcript.done", "response.output_audio_transcript.done"):
            transcript = ev.get("transcript", "")
            if transcript:
                print(f"  Agent:\t{transcript}")
                await _write_conversation_log(f"Agent Audio Response:\t{transcript}")

        elif etype in ("response.audio_transcript.delta", "response.output_audio_transcript.delta"):
            delta = ev.get("delta", "")
            if delta:
                print(delta, end="", flush=True)

        elif etype == "input_audio_buffer.speech_started":
            logger.info("User started speaking")
            if self.agent_speaking or self._active_response:
                logger.info(
                    "Agent is active/speaking - stopping playback and cancelling response"
                )
                print("  Listening...")
                ap.skip_pending_audio()

                if self._active_response and not self._response_api_done:
                    if self.current_response_id:
                        self.cancelled_response_ids.add(self.current_response_id)
                        logger.debug(
                            "Added response %s to cancelled set",
                            self.current_response_id,
                        )
                    try:
                        await conn.response.cancel()
                        logger.debug("Cancelled in-progress response due to barge-in")
                    except Exception as e:
                        if "no active response" in str(e).lower():
                            logger.debug("Cancel ignored - response already completed")
                        else:
                            logger.warning("Cancel failed: %s", e)
            else:
                logger.info(
                    "Ignoring user speech start: agent is not speaking and no response is active"
                )

        elif etype == "input_audio_buffer.speech_stopped":
            logger.info("User stopped speaking")
            print("  Processing...")

        elif etype == "response.created":
            resp = ev.get("response") or {}
            resp_id = (
                resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", "")
            )
            logger.info("Assistant response created: %s", resp_id)
            self._active_response = True
            self._response_api_done = False
            self.current_response_id = resp_id
            self.agent_speaking = False
            self.greeting_sent = True

        elif etype in ("response.audio.delta", "response.output_audio.delta"):
            logger.debug("Received audio delta")
            self.agent_speaking = True
            resp_id = ev.get("response_id", "")
            if resp_id not in self.cancelled_response_ids:
                delta = ev.get("delta")
                if delta:
                    if isinstance(delta, str):
                        try:
                            audio_bytes = base64.b64decode(delta)
                        except Exception:
                            audio_bytes = delta.encode("utf-8")
                    else:
                        audio_bytes = delta
                    ap.queue_audio(audio_bytes)
            else:
                logger.debug(
                    "Discarding delta for cancelled response: %s", resp_id
                )

        elif etype in ("response.audio.done", "response.output_audio.done"):
            logger.info("Assistant finished speaking")
            self.agent_speaking = False
            print("  Ready for next input...")

        elif etype == "response.done":
            logger.info("Response complete")
            self._active_response = False
            self._response_api_done = True
            self.agent_speaking = False

        elif etype == "response.function_call_arguments.done":
            fn_name = ev.get("name") or getattr(event, "name", "")
            call_id = ev.get("call_id") or getattr(event, "call_id", "")
            raw_args = ev.get("arguments") or getattr(event, "arguments", "")
            logger.info("Agent requested tool call: %s (call_id=%s)", fn_name, call_id)
            print(f"  System (tool call):\t{fn_name}...")

            try:
                arguments = (
                    json.loads(raw_args)
                    if isinstance(raw_args, str) and raw_args
                    else (raw_args or {})
                )
            except Exception:
                arguments = {}

            session_id = self.session_id or "validation_session"
            output_json = dispatch_tool(fn_name, arguments, session_id=session_id)

            try:
                await conn.conversation.item.create(
                    item={
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": output_json,
                    }
                )
                logger.info("Sent function call output for %s", call_id)
                await conn.response.create()
            except Exception:
                logger.exception("Failed to send function call output")

        elif etype == "error":
            err = ev.get("error") or {}
            msg = (
                err.get("message")
                if isinstance(err, dict)
                else getattr(err, "message", str(err))
            )
            if "Cancellation failed: no active response" in str(msg):
                logger.debug("Benign cancellation error: %s", msg)
            else:
                logger.error("Voice Agent error: %s", msg)
                print(f"  Error: {msg}")

        else:
            logger.debug("Unhandled event type: %s", etype)


# ── Helpers ─────────────────────────────────────────────────────────


async def _write_conversation_log(message: str) -> None:
    """Append a message to the conversation log file."""
    log_path = os.path.join(_logs_dir, _conversation_logfile)
    await asyncio.to_thread(
        lambda: open(log_path, "a", encoding="utf-8").write(message + "\n")
    )


def _check_audio_devices() -> None:
    """Verify audio input/output devices are available."""
    if pyaudio is None:
        sys.exit(
            "PyAudio is not installed. Please install PyAudio to use microphone and speaker validation."
        )
    p = pyaudio.PyAudio()
    try:

        def _has_channels(key: str) -> bool:
            return any(
                cast(Union[int, float], p.get_device_info_by_index(i).get(key, 0) or 0)
                > 0
                for i in range(p.get_device_count())
            )

        if not _has_channels("maxInputChannels"):
            sys.exit("No audio input devices found. Please check your microphone.")
        if not _has_channels("maxOutputChannels"):
            sys.exit("No audio output devices found. Please check your speakers.")
    finally:
        p.terminate()


def main() -> None:
    """Main entry point."""
    endpoint = os.environ.get("PROJECT_ENDPOINT") or os.environ.get(
        "VOICELIVE_ENDPOINT", ""
    )
    voice_name = os.environ.get("AZURE_VOICE_AGENTS_VOICE") or os.environ.get(
        "VOICE_NAME", "en-US-Ava:DragonHDLatestNeural"
    )
    agent_name = os.environ.get("AGENT_NAME", "")
    agent_version = os.environ.get("AGENT_VERSION") or None
    project_name = os.environ.get("PROJECT_NAME", "")
    conversation_id = os.environ.get("CONVERSATION_ID") or None
    foundry_resource_override = os.environ.get("FOUNDRY_RESOURCE_OVERRIDE") or None
    agent_auth_id = os.environ.get("AGENT_AUTHENTICATION_IDENTITY_CLIENT_ID") or None

    print("Environment:")
    print(f"  ENDPOINT           : {endpoint}")
    print(f"  VOICE_NAME         : {voice_name}")
    print(f"  AGENT_NAME         : {agent_name}")
    print(f"  AGENT_VERSION      : {agent_version}")
    print(f"  PROJECT_NAME       : {project_name}")
    print(f"  CONVERSATION_ID    : {conversation_id}")

    if not endpoint or not agent_name or not project_name:
        sys.exit(
            "Set PROJECT_ENDPOINT (or VOICELIVE_ENDPOINT), AGENT_NAME, and PROJECT_NAME in your .env file."
        )

    credential = DefaultAzureCredential()
    logger.info("Using Default Azure Credential")

    assistant = DriveThruVoiceAssistant(
        endpoint=endpoint,
        credential=credential,
        voice=voice_name,
        agent_name=agent_name,
        agent_version=agent_version,
        project_name=project_name,
        conversation_id=conversation_id,
        foundry_resource_override=foundry_resource_override,
        agent_authentication_identity_client_id=agent_auth_id,
    )

    # Handle SIGTERM for graceful shutdown
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    try:
        asyncio.run(assistant.start())
    except KeyboardInterrupt:
        print("\n  Voice assistant shut down. Goodbye!")
    except Exception as e:
        print(f"Fatal Error: {e}")


if __name__ == "__main__":
    try:
        _check_audio_devices()
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"Audio system check failed: {e}")

    print("DriveThru Voice Agent Validation — AIProjectClient (Voice Agents)")
    print("=" * 65)
    main()
