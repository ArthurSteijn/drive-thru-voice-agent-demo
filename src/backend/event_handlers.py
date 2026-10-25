import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from src.agent_tools.order_tools import ORDERING_STAGES
from src.backend.tool_dispatcher import handle_function_call

logger = logging.getLogger(__name__)


@dataclass
class RelaySessionState:
    voicelive_session_id: str = ""
    conversation_id: str = ""
    current_response_id: str = ""
    cancelled_response_ids: set[str] = field(default_factory=set)
    pending_calls: dict[str, str] = field(default_factory=dict)
    agent_speaking: bool = False
    response_active: bool = False
    current_stage: str = "burgers"
    basket_items: list[dict[str, Any]] = field(default_factory=list)
    has_unresponded_tool_outputs: bool = False


async def _trigger_response_create(
    state: RelaySessionState,
    send_to_voicelive: Callable[[str], Awaitable[None]],
) -> None:
    if not state.response_active and not state.pending_calls and state.has_unresponded_tool_outputs:
        state.has_unresponded_tool_outputs = False
        logger.info("Triggering response.create after tool execution")
        try:
            await send_to_voicelive(json.dumps({"type": "response.create"}))
        except Exception as e:
            logger.warning("Failed to send response.create: %s", e)


async def process_voicelive_event(
    event: dict[str, Any],
    state: RelaySessionState,
    browser_ws: Any,
    send_to_voicelive: Callable[[str], Awaitable[None]],
) -> None:
    etype = event.get("type", "")

    if etype in ("session.created", "session.updated"):
        state.voicelive_session_id = event.get("session", {}).get("id", "")
        logger.info("Voice Agent session ready: %s", state.voicelive_session_id)
        await browser_ws.send_json({
            "type": "session.created",
            "session": {"id": state.voicelive_session_id},
        })

    elif etype == "conversation.created":
        conv = event.get("conversation") or {}
        state.conversation_id = str(
            event.get("conversation_id")
            or (conv.get("id") if isinstance(conv, dict) else "")
            or state.conversation_id
        )
        logger.info("Voice Agent persisted conversation_id: %s", state.conversation_id)

    elif etype == "response.created":
        state.current_response_id = event.get("response", {}).get("id", "")
        state.agent_speaking = False
        state.response_active = True
        await browser_ws.send_json({
            "type": "response.created",
            "response": {"id": state.current_response_id},
        })

    elif etype == "input_audio_buffer.speech_started":
        # Always notify the browser so it immediately terminates local audio playback
        await browser_ws.send_json({"type": "input_audio_buffer.speech_started"})

        if state.agent_speaking or state.response_active:
            if state.current_response_id:
                state.cancelled_response_ids.add(state.current_response_id)
            try:
                await send_to_voicelive(json.dumps({"type": "response.cancel"}))
            except Exception as e:
                logger.warning("Failed to send response.cancel: %s", e)
            state.response_active = False
            state.has_unresponded_tool_outputs = False
            state.pending_calls.clear()
        state.agent_speaking = False

    elif etype == "input_audio_buffer.speech_stopped":
        await browser_ws.send_json({"type": "input_audio_buffer.speech_stopped"})

    elif etype in ("response.audio.delta", "response.output_audio.delta"):
        state.agent_speaking = True
        resp_id = event.get("response_id", "")
        if resp_id not in state.cancelled_response_ids:
            await browser_ws.send_json({
                "type": "response.audio.delta",
                "delta": event.get("delta", ""),
            })

    elif etype in ("response.audio.done", "response.output_audio.done"):
        state.agent_speaking = False
        await browser_ws.send_json({"type": "response.audio.done"})

    elif etype in ("response.audio_transcript.delta", "response.output_audio_transcript.delta"):
        resp_id = event.get("response_id", "")
        if resp_id not in state.cancelled_response_ids:
            await browser_ws.send_json({
                "type": "response.audio_transcript.delta",
                "delta": event.get("delta", ""),
                "item_id": event.get("item_id", ""),
            })

    elif etype == "conversation.item.input_audio_transcription.completed":
        await browser_ws.send_json({
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": event.get("transcript", ""),
        })

    elif etype == "response.output_item.added":
        item = event.get("item", {}) or {}
        if item.get("type") == "function_call":
            call_id = item.get("call_id", "")
            fn_name = item.get("name", "")
            if call_id and fn_name:
                state.pending_calls[call_id] = fn_name

    elif etype == "response.function_call_arguments.done":
        call_id = event.get("call_id", "")
        fn_name = state.pending_calls.pop(call_id, "")
        if not fn_name:
            fn_name = event.get("name", "")
        arguments_json = event.get("arguments", "")
        if fn_name:
            await browser_ws.send_json({
                "type": "tool.invoked",
                "name": fn_name,
                "call_id": call_id,
            })
            output_json = await handle_function_call(
                call_id=call_id,
                name=fn_name,
                arguments_json=arguments_json,
                session_id=state.voicelive_session_id,
                send_to_voicelive=send_to_voicelive,
                create_response=False,
            )
            state.has_unresponded_tool_outputs = True

            if fn_name == "update_order_state":
                try:
                    res = json.loads(output_json)
                    if res.get("success"):
                        state.current_stage = res.get("stage", state.current_stage)
                        state.basket_items = res.get("items", state.basket_items)
                        await browser_ws.send_json({
                            "type": "order_state_updated",
                            "stage": state.current_stage,
                            "items": state.basket_items,
                            "subtotal": res.get("subtotal", 0.0),
                            "tax": res.get("tax", 0.0),
                            "grand_total": res.get("grand_total", 0.0),
                            "item_count": res.get("item_count", 0),
                            "highlighted_item_ids": res.get("highlighted_item_ids", []),
                        })
                except Exception as e:
                    logger.error("Failed to parse update_order_state result for browser: %s", e)

            elif fn_name == "get_menu_items":
                try:
                    parsed_args = json.loads(arguments_json) if arguments_json else {}
                    category = str(parsed_args.get("category", "")).lower().strip()
                    if category in ORDERING_STAGES:
                        state.current_stage = category
                        await browser_ws.send_json({
                            "type": "menu_stage_updated",
                            "stage": category,
                        })
                except Exception as e:
                    logger.error("Failed to emit menu_stage_updated for browser: %s", e)

            elif fn_name == "submit_order":
                try:
                    res = json.loads(output_json)
                    if res.get("success"):
                        state.current_stage = "confirmed"
                        confirmed_items = res.get("items") or state.basket_items
                        await browser_ws.send_json({
                            "type": "order_confirmed",
                            "order_id": res.get("order_id"),
                            "subtotal": res.get("total", 0.0),
                            "tax": res.get("tax", 0.0),
                            "grand_total": res.get("grand_total"),
                            "item_count": res.get("item_count"),
                            "items": confirmed_items,
                        })
                except Exception as e:
                    logger.error("Failed to parse submit_order result for browser: %s", e)

            await _trigger_response_create(state, send_to_voicelive)

    elif etype == "response.done":
        state.agent_speaking = False
        state.response_active = False
        resp_id = event.get("response", {}).get("id", "")
        if not resp_id or resp_id not in state.cancelled_response_ids:
            await browser_ws.send_json({"type": "response.done"})
        await _trigger_response_create(state, send_to_voicelive)

    elif etype == "error":
        error_msg = event.get("error", {}).get("message", str(event))
        logger.error("VoiceLive error: %s", error_msg)
        await browser_ws.send_json({"type": "error", "message": error_msg})
