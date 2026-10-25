import json
from unittest.mock import patch
from src.backend.tool_dispatcher import dispatch_tool


def test_dispatch_unknown_tool():
    result_str = dispatch_tool("unknown_tool", {}, "session_123")
    res = json.loads(result_str)
    assert res["success"] is False
    assert "Unknown tool" in res["error"]


@patch("src.agent_tools.menu_tools.FabricDBClient")
def test_dispatch_get_menu_items(mock_db_class):
    mock_db = mock_db_class.return_value
    mock_db.get_menu.return_value = [{"name": "Burger", "price": 5.99}]

    result_str = dispatch_tool("get_menu_items", {}, "session_123")
    res = json.loads(result_str)
    assert res["success"] is True
    assert len(res["items"]) >= 1


def test_dispatch_update_order_state():
    result_str = dispatch_tool(
        "update_order_state",
        {
            "items": [
                {"menu_item_id": "BURGER_001", "name": "Classic Cheeseburger", "quantity": 1, "price": 8.99}
            ],
            "next_stage": "sides",
        },
        "session_123",
    )
    res = json.loads(result_str)
    assert res["success"] is True
    assert res["stage"] == "sides"
    assert res["item_count"] == 1
    assert res["subtotal"] == 8.99
