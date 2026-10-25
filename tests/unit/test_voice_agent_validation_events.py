"""Unit tests for Voice Agent event normalization and handling in voice_agent_validation.py."""

import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.voice_agent_validation import (
    DriveThruVoiceAssistant,
    WebSocketVoiceAgentConnectionAdapter,
    extract_event_dict,
)


class DummyTypedEvent:
    def as_dict(self):
        return {"type": "response.output_audio.delta", "delta": "AQID"}


class DummyObjectEvent:
    def __init__(self):
        self.type = "response.audio.delta"
        self.delta = "BAUG"


class DummyTypeOnlyEvent:
    def __init__(self):
        self.type = "input_audio_buffer.speech_stopped"


def test_extract_event_dict_from_mapping():
    raw = {"type": "session.updated", "session": {"id": "sess_1"}}
    assert extract_event_dict(raw) == raw


def test_extract_event_dict_from_sdk_model():
    ev = DummyTypedEvent()
    assert extract_event_dict(ev) == {
        "type": "response.output_audio.delta",
        "delta": "AQID",
    }


def test_extract_event_dict_from_object():
    ev = DummyObjectEvent()
    assert extract_event_dict(ev) == {
        "type": "response.audio.delta",
        "delta": "BAUG",
    }


def test_extract_event_dict_type_only():
    ev = DummyTypeOnlyEvent()
    assert extract_event_dict(ev) == {"type": "input_audio_buffer.speech_stopped"}


@pytest.mark.asyncio
async def test_websocket_adapter():
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = json.dumps({"type": "session.created", "session": {"id": "test"}})

    adapter = WebSocketVoiceAgentConnectionAdapter(mock_ws)

    # Test audio buffer append
    await adapter.input_audio_buffer.append(audio=b"123")
    assert mock_ws.send.called
    sent_audio = json.loads(mock_ws.send.call_args_list[-1][0][0])
    assert sent_audio["type"] == "input_audio_buffer.append"
    assert sent_audio["audio"] == base64.b64encode(b"123").decode("utf-8")

    # Test conversation item create
    await adapter.conversation.item.create(item={"type": "message", "role": "user"})
    sent_item = json.loads(mock_ws.send.call_args_list[-1][0][0])
    assert sent_item["type"] == "conversation.item.create"

    # Test response create & cancel
    await adapter.response.create()
    assert json.loads(mock_ws.send.call_args_list[-1][0][0])["type"] == "response.create"

    await adapter.response.cancel()
    assert json.loads(mock_ws.send.call_args_list[-1][0][0])["type"] == "response.cancel"

    # Test iteration
    events = []
    async for ev in adapter:
        events.append(ev)
        break
    assert len(events) == 1
    assert events[0]["type"] == "session.created"


@pytest.mark.asyncio
async def test_handle_event_session_updated_proactive_greeting():
    assistant = DriveThruVoiceAssistant(
        endpoint="https://demo.services.ai.azure.com/api/projects/proj-1",
        credential=MagicMock(),
        voice="en-US-Ava:DragonHDLatestNeural",
        agent_name="drivethru-ordering-agent",
        project_name="proj-1",
    )

    mock_conn = AsyncMock()
    mock_ap = MagicMock()
    assistant.connection = mock_conn
    assistant.audio_processor = mock_ap

    ev = {
        "type": "session.updated",
        "session": {
            "id": "sess_123",
            "agent": {"name": "drivethru-ordering-agent"},
            "voice": {"name": "en-US-Ava:DragonHDLatestNeural"},
        },
    }

    with patch("src.agents.voice_agent_validation._write_conversation_log", new=AsyncMock()):
        await assistant._handle_event(ev)

    assert assistant.session_ready is True
    assert assistant.session_id == "sess_123"
    assert assistant.greeting_sent is True
    assert mock_conn.conversation.item.create.called
    assert mock_conn.response.create.called
    assert mock_ap.start_capture.called


@pytest.mark.asyncio
async def test_handle_event_audio_deltas_both_names():
    assistant = DriveThruVoiceAssistant(
        endpoint="https://demo.services.ai.azure.com/api/projects/proj-1",
        credential=MagicMock(),
        voice="en-US-Ava:DragonHDLatestNeural",
        agent_name="drivethru-ordering-agent",
        project_name="proj-1",
    )

    mock_conn = AsyncMock()
    mock_ap = MagicMock()
    assistant.connection = mock_conn
    assistant.audio_processor = mock_ap

    # 1. response.output_audio.delta with base64 string
    pcm_bytes = b"\x01\x02\x03\x04"
    b64_pcm = base64.b64encode(pcm_bytes).decode("utf-8")
    await assistant._handle_event({
        "type": "response.output_audio.delta",
        "response_id": "resp_1",
        "delta": b64_pcm,
    })
    assert assistant.agent_speaking is True
    mock_ap.queue_audio.assert_called_with(pcm_bytes)

    # 2. response.audio.delta with raw bytes (typed SDK event style)
    await assistant._handle_event({
        "type": "response.audio.delta",
        "response_id": "resp_1",
        "delta": pcm_bytes,
    })
    mock_ap.queue_audio.assert_called_with(pcm_bytes)

    # 3. audio done
    await assistant._handle_event({"type": "response.output_audio.done"})
    assert assistant.agent_speaking is False


@pytest.mark.asyncio
async def test_handle_event_function_call_dispatches_tool():
    assistant = DriveThruVoiceAssistant(
        endpoint="https://demo.services.ai.azure.com/api/projects/proj-1",
        credential=MagicMock(),
        voice="en-US-Ava:DragonHDLatestNeural",
        agent_name="drivethru-ordering-agent",
        project_name="proj-1",
    )

    mock_conn = AsyncMock()
    mock_ap = MagicMock()
    assistant.connection = mock_conn
    assistant.audio_processor = mock_ap
    assistant.session_id = "sess_test"

    tool_ev = {
        "type": "response.function_call_arguments.done",
        "call_id": "call_abc",
        "name": "get_menu_items",
        "arguments": json.dumps({"category": "burgers"}),
    }

    with patch("src.agents.voice_agent_validation.dispatch_tool") as mock_dispatch:
        mock_dispatch.return_value = json.dumps({"success": True, "items": []})
        await assistant._handle_event(tool_ev)
        mock_dispatch.assert_called_once_with(
            "get_menu_items",
            {"category": "burgers"},
            session_id="sess_test",
        )

    # Verify function_call_output sent to connection
    mock_conn.conversation.item.create.assert_called_once_with(
        item={
            "type": "function_call_output",
            "call_id": "call_abc",
            "output": json.dumps({"success": True, "items": []}),
        }
    )
    mock_conn.response.create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_event_barge_in():
    assistant = DriveThruVoiceAssistant(
        endpoint="https://demo.services.ai.azure.com/api/projects/proj-1",
        credential=MagicMock(),
        voice="en-US-Ava:DragonHDLatestNeural",
        agent_name="drivethru-ordering-agent",
        project_name="proj-1",
    )

    mock_conn = AsyncMock()
    mock_ap = MagicMock()
    assistant.connection = mock_conn
    assistant.audio_processor = mock_ap

    assistant.agent_speaking = True
    assistant._active_response = True
    assistant._response_api_done = False
    assistant.current_response_id = "resp_to_cancel"

    await assistant._handle_event({"type": "input_audio_buffer.speech_started"})

    assert mock_ap.skip_pending_audio.called
    assert "resp_to_cancel" in assistant.cancelled_response_ids
    assert mock_conn.response.cancel.called
