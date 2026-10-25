import json
import pytest
from unittest.mock import AsyncMock, patch
from src.backend.event_handlers import RelaySessionState, process_voicelive_event


@pytest.mark.asyncio
async def test_process_session_updated():
    state = RelaySessionState()
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    event = {"type": "session.updated", "session": {"id": "test_sess_123"}}
    await process_voicelive_event(event, state, mock_browser, mock_send_vl)

    assert state.voicelive_session_id == "test_sess_123"
    mock_browser.send_json.assert_called_once_with({
        "type": "session.created",
        "session": {"id": "test_sess_123"},
    })


@pytest.mark.asyncio
async def test_process_session_created():
    state = RelaySessionState()
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    event = {"type": "session.created", "session": {"id": "sess_created_456"}}
    await process_voicelive_event(event, state, mock_browser, mock_send_vl)

    assert state.voicelive_session_id == "sess_created_456"
    mock_browser.send_json.assert_called_once_with({
        "type": "session.created",
        "session": {"id": "sess_created_456"},
    })



@pytest.mark.asyncio
async def test_process_update_order_state_emits_browser_event():
    state = RelaySessionState(voicelive_session_id="sess_1")
    state.pending_calls["call_1"] = "update_order_state"
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    args = {
        "items": [
            {"menu_item_id": "BURGER_001", "name": "Classic Cheeseburger", "quantity": 1, "price": 8.99}
        ],
        "next_stage": "sides",
        "highlighted_item_ids": ["SIDE_001"],
    }
    event = {
        "type": "response.function_call_arguments.done",
        "call_id": "call_1",
        "arguments": json.dumps(args),
    }

    await process_voicelive_event(event, state, mock_browser, mock_send_vl)

    assert state.current_stage == "sides"
    assert len(state.basket_items) == 1
    assert mock_browser.send_json.call_count == 2
    second_call = mock_browser.send_json.call_args_list[1].args[0]
    assert second_call["type"] == "order_state_updated"
    assert second_call["stage"] == "sides"
    assert second_call["item_count"] == 1
    assert second_call["subtotal"] == 8.99
    assert second_call["highlighted_item_ids"] == ["SIDE_001"]


@pytest.mark.asyncio
async def test_process_get_menu_items_with_category_emits_menu_stage_updated():
    state = RelaySessionState(voicelive_session_id="sess_1")
    state.pending_calls["call_2"] = "get_menu_items"
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    event = {
        "type": "response.function_call_arguments.done",
        "call_id": "call_2",
        "arguments": json.dumps({"category": "drinks"}),
    }

    await process_voicelive_event(event, state, mock_browser, mock_send_vl)

    assert state.current_stage == "drinks"
    second_call = mock_browser.send_json.call_args_list[1].args[0]
    assert second_call == {
        "type": "menu_stage_updated",
        "stage": "drinks",
    }


@pytest.mark.asyncio
async def test_process_submit_order_emits_enriched_order_confirmed():
    state = RelaySessionState(voicelive_session_id="sess_1")
    state.pending_calls["call_submit"] = "submit_order"
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    submit_result = {
        "success": True,
        "order_id": "ord-999",
        "total": 12.50,
        "tax": 1.00,
        "grand_total": 13.50,
        "item_count": 2,
        "items": [
            {"menu_item_id": "BURGER_001", "name": "Burger", "quantity": 1, "price": 8.50, "line_total": 8.50},
            {"menu_item_id": "SIDE_001", "name": "Fries", "quantity": 1, "price": 4.00, "line_total": 4.00},
        ],
    }

    with patch(
        "src.backend.event_handlers.handle_function_call",
        return_value=json.dumps(submit_result),
    ):
        event = {
            "type": "response.function_call_arguments.done",
            "call_id": "call_submit",
            "arguments": json.dumps({"items": [{"menu_item_id": "BURGER_001", "quantity": 1}]}),
        }
        await process_voicelive_event(event, state, mock_browser, mock_send_vl)

    assert state.current_stage == "confirmed"
    assert mock_browser.send_json.call_count == 2
    tool_invoked_call = mock_browser.send_json.call_args_list[0].args[0]
    assert tool_invoked_call == {
        "type": "tool.invoked",
        "name": "submit_order",
        "call_id": "call_submit",
    }
    order_confirmed_call = mock_browser.send_json.call_args_list[1].args[0]
    assert order_confirmed_call == {
        "type": "order_confirmed",
        "order_id": "ord-999",
        "subtotal": 12.50,
        "tax": 1.00,
        "grand_total": 13.50,
        "item_count": 2,
        "items": submit_result["items"],
    }


@pytest.mark.asyncio
async def test_response_create_deferred_while_response_active():
    state = RelaySessionState(voicelive_session_id="sess_1", response_active=True)
    state.pending_calls["call_1"] = "update_order_state"
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    args = {"items": [{"menu_item_id": "BURGER_001", "name": "Burger", "quantity": 1, "price": 8.99}]}
    event_done = {
        "type": "response.function_call_arguments.done",
        "call_id": "call_1",
        "arguments": json.dumps(args),
    }

    # Tool finishes while response_active is True (e.g. agent said 'One moment')
    await process_voicelive_event(event_done, state, mock_browser, mock_send_vl)

    # Function call output was sent via mock_send_vl, but response.create was NOT yet sent
    sent_types = [json.loads(c.args[0]).get("type") for c in mock_send_vl.call_args_list]
    assert "response.create" not in sent_types
    assert state.has_unresponded_tool_outputs is True

    # Now VoiceLive response finishes (response.done arrives)
    event_resp_done = {"type": "response.done"}
    await process_voicelive_event(event_resp_done, state, mock_browser, mock_send_vl)

    assert state.response_active is False
    assert state.has_unresponded_tool_outputs is False
    all_sent_types = [json.loads(c.args[0]).get("type") for c in mock_send_vl.call_args_list]
    assert "response.create" in all_sent_types


@pytest.mark.asyncio
async def test_response_create_waits_for_all_parallel_tool_calls():
    state = RelaySessionState(voicelive_session_id="sess_1", response_active=False)
    state.pending_calls["call_1"] = "get_menu_items"
    state.pending_calls["call_2"] = "update_order_state"
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    # Call 1 finishes
    event_1 = {
        "type": "response.function_call_arguments.done",
        "call_id": "call_1",
        "arguments": json.dumps({"category": "sides"}),
    }
    await process_voicelive_event(event_1, state, mock_browser, mock_send_vl)

    # Call 2 is still pending, so response.create must NOT be sent
    sent_types_1 = [json.loads(c.args[0]).get("type") for c in mock_send_vl.call_args_list]
    assert "response.create" not in sent_types_1

    # Call 2 finishes
    event_2 = {
        "type": "response.function_call_arguments.done",
        "call_id": "call_2",
        "arguments": json.dumps({"items": [{"menu_item_id": "BURGER_001", "name": "Burger", "quantity": 1, "price": 8.99}]}),
    }
    await process_voicelive_event(event_2, state, mock_browser, mock_send_vl)

    # Now all calls are done and response_active is False -> response.create sent
    sent_types_2 = [json.loads(c.args[0]).get("type") for c in mock_send_vl.call_args_list]
    assert "response.create" in sent_types_2


@pytest.mark.asyncio
async def test_process_v1_output_audio_and_transcript_deltas():
    state = RelaySessionState(voicelive_session_id="sess_v1")
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    audio_event = {
        "type": "response.output_audio.delta",
        "response_id": "resp_1",
        "delta": "pcm_base64_chunk",
    }
    await process_voicelive_event(audio_event, state, mock_browser, mock_send_vl)

    assert state.agent_speaking is True
    mock_browser.send_json.assert_called_with({
        "type": "response.audio.delta",
        "delta": "pcm_base64_chunk",
    })

    transcript_event = {
        "type": "response.output_audio_transcript.delta",
        "item_id": "item_1",
        "delta": "Welcome to Drive-Thru Z!",
    }
    await process_voicelive_event(transcript_event, state, mock_browser, mock_send_vl)
    mock_browser.send_json.assert_called_with({
        "type": "response.audio_transcript.delta",
        "delta": "Welcome to Drive-Thru Z!",
        "item_id": "item_1",
    })

    done_event = {"type": "response.output_audio.done"}
    await process_voicelive_event(done_event, state, mock_browser, mock_send_vl)
    assert state.agent_speaking is False
    mock_browser.send_json.assert_called_with({"type": "response.audio.done"})


@pytest.mark.asyncio
async def test_process_conversation_created_stores_conversation_id():
    state = RelaySessionState(voicelive_session_id="sess_v1")
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    event = {
        "type": "conversation.created",
        "conversation": {"id": "conv_abc_999"},
    }
    await process_voicelive_event(event, state, mock_browser, mock_send_vl)

    assert state.conversation_id == "conv_abc_999"


@pytest.mark.asyncio
async def test_process_speech_started_always_notifies_browser_when_idle():
    """Verify browser is always told speech_started even when response is already done on server."""
    state = RelaySessionState(voicelive_session_id="sess_v1", response_active=False, agent_speaking=False)
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    event = {"type": "input_audio_buffer.speech_started"}
    await process_voicelive_event(event, state, mock_browser, mock_send_vl)

    mock_browser.send_json.assert_called_once_with({"type": "input_audio_buffer.speech_started"})
    mock_send_vl.assert_not_called()


@pytest.mark.asyncio
async def test_process_drops_audio_and_transcript_for_cancelled_response():
    state = RelaySessionState(voicelive_session_id="sess_v1", response_active=True, current_response_id="resp_cancelled")
    mock_browser = AsyncMock()
    mock_send_vl = AsyncMock()

    # Cancel via speech_started
    await process_voicelive_event({"type": "input_audio_buffer.speech_started"}, state, mock_browser, mock_send_vl)
    assert "resp_cancelled" in state.cancelled_response_ids

    mock_browser.reset_mock()
    # Late audio delta from cancelled response
    await process_voicelive_event(
        {"type": "response.output_audio.delta", "response_id": "resp_cancelled", "delta": "audio_chunk"},
        state,
        mock_browser,
        mock_send_vl,
    )
    mock_browser.send_json.assert_not_called()

    # Late transcript delta from cancelled response
    await process_voicelive_event(
        {"type": "response.output_audio_transcript.delta", "response_id": "resp_cancelled", "delta": "text_chunk"},
        state,
        mock_browser,
        mock_send_vl,
    )
    mock_browser.send_json.assert_not_called()


