"""Unit tests for tool_dispatcher.handle_function_call and dispatch_tool."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from src.backend.tool_dispatcher import dispatch_tool, handle_function_call


class TestDispatchTool:
    def test_dispatches_get_menu_items(self):
        with patch(
            "src.backend.tool_dispatcher.execute_get_menu_items", return_value='{"success": true}'
        ) as mock_exec:
            result = dispatch_tool("get_menu_items", {"category": "burgers"}, "sess-1")
        mock_exec.assert_called_once_with({"category": "burgers"})
        assert result == '{"success": true}'

    def test_dispatches_submit_order_with_session(self):
        with patch(
            "src.backend.tool_dispatcher.execute_submit_order", return_value='{"order_id": "x"}'
        ) as mock_exec:
            result = dispatch_tool(
                "submit_order", {"items": [{"menu_item_id": "B1"}]}, "sess-1"
            )
        mock_exec.assert_called_once_with({"items": [{"menu_item_id": "B1"}]}, session_id="sess-1")
        assert result == '{"order_id": "x"}'

    def test_unknown_tool_returns_error(self):
        result = dispatch_tool("does_not_exist", {}, "sess-1")
        payload = json.loads(result)
        assert payload["success"] is False
        assert "Unknown tool" in payload["error"]


class TestHandleFunctionCall:
    @pytest.mark.asyncio
    async def test_sends_function_output_without_response_create(self):
        send = AsyncMock()
        with patch(
            "src.backend.tool_dispatcher.execute_get_menu_items",
            return_value='{"success": true, "items": []}',
        ):
            output = await handle_function_call(
                call_id="call-123",
                name="get_menu_items",
                arguments_json='{"category": "burgers"}',
                session_id="sess-1",
                send_to_voicelive=send,
                create_response=False,
            )

        assert output == '{"success": true, "items": []}'
        assert send.await_count == 1
        first = json.loads(send.await_args_list[0].args[0])

        assert first["type"] == "conversation.item.create"
        assert first["item"]["type"] == "function_call_output"
        assert first["item"]["call_id"] == "call-123"
        assert first["item"]["output"] == '{"success": true, "items": []}'

    @pytest.mark.asyncio
    async def test_sends_function_output_and_response_create_when_requested(self):
        send = AsyncMock()
        with patch(
            "src.backend.tool_dispatcher.execute_get_menu_items",
            return_value='{"success": true, "items": []}',
        ):
            output = await handle_function_call(
                call_id="call-123",
                name="get_menu_items",
                arguments_json='{"category": "burgers"}',
                session_id="sess-1",
                send_to_voicelive=send,
                create_response=True,
            )

        assert output == '{"success": true, "items": []}'
        assert send.await_count == 2
        first = json.loads(send.await_args_list[0].args[0])
        second = json.loads(send.await_args_list[1].args[0])

        assert first["type"] == "conversation.item.create"
        assert second["type"] == "response.create"

    @pytest.mark.asyncio
    async def test_handles_invalid_arguments_json(self):
        send = AsyncMock()
        with patch(
            "src.backend.tool_dispatcher.execute_get_menu_items", return_value='{"success": true}'
        ) as mock_exec:
            await handle_function_call(
                call_id="call-bad",
                name="get_menu_items",
                arguments_json="{not valid json",
                session_id="sess-1",
                send_to_voicelive=send,
            )
        # Falls back to empty dict, still calls executor and sends events
        mock_exec.assert_called_once_with({})
        assert send.await_count == 1

    @pytest.mark.asyncio
    async def test_handles_empty_arguments(self):
        send = AsyncMock()
        with patch(
            "src.backend.tool_dispatcher.execute_get_menu_items", return_value='{"success": true}'
        ) as mock_exec:
            await handle_function_call(
                call_id="call-empty",
                name="get_menu_items",
                arguments_json="",
                session_id="",
                send_to_voicelive=send,
            )
        mock_exec.assert_called_once_with({})
        assert send.await_count == 1
