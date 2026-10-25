import json
import logging
from typing import Any, Awaitable, Callable
from src.agent_tools import (
    execute_get_menu_items,
    execute_update_order_state,
    execute_submit_order,
    execute_get_order_analytics,
)

logger = logging.getLogger(__name__)


def dispatch_tool(name: str, arguments: dict[str, Any], session_id: str) -> str:
    if name == "get_menu_items":
        return execute_get_menu_items(arguments)
    if name == "update_order_state":
        return execute_update_order_state(arguments)
    if name == "submit_order":
        return execute_submit_order(arguments, session_id=session_id)
    if name == "get_order_analytics":
        return execute_get_order_analytics(arguments)
    logger.warning("Unknown tool requested by agent: %s", name)
    return json.dumps({"success": False, "error": f"Unknown tool: {name}"})


async def handle_function_call(
    *,
    call_id: str,
    name: str,
    arguments_json: str,
    session_id: str,
    send_to_voicelive: Callable[[str], Awaitable[None]],
    create_response: bool = False,
) -> str:
    try:
        arguments = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as e:
        logger.error("Invalid function arguments JSON for %s: %s", name, e)
        arguments = {}

    logger.info("Tool call: %s call_id=%s args=%s", name, call_id, arguments)
    output_json = dispatch_tool(name, arguments, session_id)

    await send_to_voicelive(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output_json,
        },
    }))
    if create_response:
        await send_to_voicelive(json.dumps({"type": "response.create"}))
    return output_json
