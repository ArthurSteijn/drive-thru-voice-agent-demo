"""Unit tests for order_tools executor."""

import json
import pytest

from src.agent_tools.order_tools import (
    _normalize_basket_items,
    execute_submit_order,
    execute_update_order_state,
)
from tests.conftest import SAMPLE_ORDER_RESULT

VALID_ITEMS = [
    {"menu_item_id": "BURGER_001", "name": "Classic Cheeseburger", "quantity": 1, "price": 8.99},
    {"menu_item_id": "DRINK_001", "name": "Soft Drink", "quantity": 1, "price": 2.49},
]


class TestExecuteSubmitOrder:
    def test_successful_order_submission(self, mock_db):
        result = json.loads(
            execute_submit_order({"items": VALID_ITEMS}, db=mock_db, session_id="sess-123")
        )

        assert result["success"] is True
        assert result["order_id"] == SAMPLE_ORDER_RESULT["order_id"]
        assert result["grand_total"] == SAMPLE_ORDER_RESULT["grand_total"]
        assert len(result["items"]) == 2
        assert result["items"][0]["line_total"] == 8.99
        mock_db.submit_order.assert_called_once_with(
            items=VALID_ITEMS, session_id="sess-123"
        )

    def test_returns_error_when_no_items(self, mock_db):
        result = json.loads(execute_submit_order({"items": []}, db=mock_db))

        assert result["success"] is False
        assert "error" in result
        mock_db.submit_order.assert_not_called()

    def test_returns_error_when_items_key_missing(self, mock_db):
        result = json.loads(execute_submit_order({}, db=mock_db))

        assert result["success"] is False
        mock_db.submit_order.assert_not_called()

    def test_handles_db_error_gracefully(self, mock_db):
        mock_db.submit_order.side_effect = Exception("Fabric unavailable")

        result = json.loads(execute_submit_order({"items": VALID_ITEMS}, db=mock_db))

        assert result["success"] is False
        assert "error" in result

    def test_default_session_id_is_empty_string(self, mock_db):
        execute_submit_order({"items": VALID_ITEMS}, db=mock_db)

        _, kwargs = mock_db.submit_order.call_args
        assert kwargs.get("session_id", "") == ""

    def test_handles_invalid_item_structures_gracefully(self, mock_db):
        result = json.loads(execute_submit_order({"items": ["not-a-dict"]}, db=mock_db))
        assert result["success"] is False
        assert "error" in result


class TestNormalizeBasketItems:
    @pytest.mark.parametrize("qty", [0, -1, -10])
    def test_boundary_quantity_clamped_to_one(self, qty):
        items = [{"menu_item_id": "B1", "name": "Burger", "quantity": qty, "price": 5.0}]
        normalized = _normalize_basket_items(items)
        assert normalized[0]["quantity"] == 1
        assert normalized[0]["line_total"] == 5.0

    @pytest.mark.parametrize("qty", [None, "invalid", "", []])
    def test_null_or_non_numeric_quantity_fallback(self, qty):
        items = [{"menu_item_id": "B1", "name": "Burger", "quantity": qty, "price": 5.0}]
        normalized = _normalize_basket_items(items)
        assert normalized[0]["quantity"] == 1
        assert normalized[0]["line_total"] == 5.0

    @pytest.mark.parametrize("price,expected", [(None, 0.0), ("bad_price", 0.0), ("", 0.0)])
    def test_null_or_non_numeric_price_fallback(self, price, expected):
        items = [{"menu_item_id": "B1", "name": "Burger", "quantity": 2, "price": price}]
        normalized = _normalize_basket_items(items)
        assert normalized[0]["price"] == expected
        assert normalized[0]["line_total"] == 0.0


class TestExecuteUpdateOrderState:
    def test_updates_basket_and_computes_totals(self):
        result = json.loads(
            execute_update_order_state(
                {
                    "items": [
                        {
                            "menu_item_id": "BURGER_001",
                            "name": "Classic Cheeseburger",
                            "quantity": 2,
                            "price": 8.99,
                            "customizations": "no pickles",
                        },
                        {
                            "menu_item_id": "SIDE_001",
                            "name": "French Fries",
                            "quantity": 1,
                            "price": 3.49,
                        },
                    ],
                    "next_stage": "drinks",
                    "highlighted_item_ids": ["DRINK_001", "DRINK_002"],
                }
            )
        )

        assert result["success"] is True
        assert result["stage"] == "drinks"
        assert result["item_count"] == 3
        assert result["subtotal"] == 21.47
        assert result["tax"] == 1.72
        assert result["grand_total"] == 23.19
        assert result["highlighted_item_ids"] == ["DRINK_001", "DRINK_002"]
        assert result["items"][0]["line_total"] == 17.98
        assert result["items"][0]["customizations"] == "no pickles"

    def test_supports_stage_change_with_empty_basket(self):
        result = json.loads(
            execute_update_order_state(
                {
                    "items": [],
                    "next_stage": "chicken",
                }
            )
        )

        assert result["success"] is True
        assert result["stage"] == "chicken"
        assert result["items"] == []
        assert result["item_count"] == 0
        assert result["subtotal"] == 0.0
        assert result["tax"] == 0.0
        assert result["grand_total"] == 0.0

    def test_invalid_stage_defaults_to_burgers(self):
        result = json.loads(
            execute_update_order_state(
                {
                    "items": [],
                    "next_stage": "invalid_stage",
                }
            )
        )

        assert result["success"] is True
        assert result["stage"] == "burgers"

    def test_update_order_state_tolerates_invalid_item_types(self):
        result = json.loads(
            execute_update_order_state(
                {
                    "items": [
                        {"menu_item_id": "B1", "name": "Burger", "quantity": 0, "price": None},
                        {"menu_item_id": "B2", "name": "Drink", "quantity": -5, "price": "bad"},
                    ],
                    "next_stage": "burgers",
                }
            )
        )

        assert result["success"] is True
        assert result["item_count"] == 2
        assert result["items"][0]["quantity"] == 1
        assert result["items"][0]["price"] == 0.0
        assert result["items"][1]["quantity"] == 1
        assert result["items"][1]["price"] == 0.0
