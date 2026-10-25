"""Order submission and live basket state tools — FunctionTool definitions and execution logic."""

import json
import logging
from typing import Any

from azure.ai.projects.models import FunctionTool

from src.fabric.db_client import FabricDBClient, TAX_RATE

logger = logging.getLogger(__name__)

ORDERING_STAGES: tuple[str, ...] = (
    "burgers",
    "chicken",
    "sides",
    "drinks",
    "desserts",
    "review",
)

# ── FunctionTools for Foundry Agent registration ────────────────────

update_order_state_tool = FunctionTool(
    name="update_order_state",
    description=(
        "Update the live drive-thru screen with the customer's current basket items "
        "and switch the displayed menu board to the relevant stage of the ordering process. "
        "Call this whenever the customer adds, modifies, or removes items, or asks to see "
        "a different menu category, or when guiding them to the next course."
    ),
    parameters={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": (
                    "Full current list of items in the customer's basket. "
                    "Pass an empty list if no items are in the basket yet."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "menu_item_id": {
                            "type": "string",
                            "description": "The MenuItemId (e.g. BURGER_001).",
                        },
                        "name": {
                            "type": "string",
                            "description": "Display name of the item.",
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "Quantity of this item in the basket.",
                            "minimum": 1,
                        },
                        "price": {
                            "type": "number",
                            "description": "Unit price of the item.",
                        },
                        "customizations": {
                            "type": "string",
                            "description": "Optional special requests or modifications (e.g. 'no pickles', 'extra sauce').",
                        },
                    },
                    "required": ["menu_item_id", "name", "quantity", "price"],
                },
            },
            "next_stage": {
                "type": "string",
                "description": (
                    "Which menu category or ordering stage to display on the drive-thru screen now. "
                    "Use 'burgers' or 'chicken' for mains, 'sides' for side dishes, 'drinks' for beverages, "
                    "'desserts' for sweet treats, and 'review' when reading back the full order for confirmation."
                ),
                "enum": list(ORDERING_STAGES),
            },
            "highlighted_item_ids": {
                "type": "array",
                "description": "Optional list of menu_item_id values to visually spotlight on the screen.",
                "items": {"type": "string"},
            },
        },
        "required": ["items", "next_stage"],
    },
)

submit_order_tool = FunctionTool(
    name="submit_order",
    description=(
        "Submit a confirmed order to the kitchen. Call this only after the customer "
        "has confirmed the items they want. Returns an order ID and total price."
    ),
    parameters={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "List of menu items the customer wants to order.",
                "items": {
                    "type": "object",
                    "properties": {
                        "menu_item_id": {
                            "type": "string",
                            "description": "The MenuItemId (e.g. BURGER_001).",
                        },
                        "name": {
                            "type": "string",
                            "description": "Display name of the item.",
                        },
                        "quantity": {
                            "type": "integer",
                            "description": "How many of this item.",
                            "minimum": 1,
                        },
                        "price": {
                            "type": "number",
                            "description": "Unit price of the item.",
                        },
                        "customizations": {
                            "type": "string",
                            "description": "Optional special requests or modifications.",
                        },
                    },
                    "required": ["menu_item_id", "name", "quantity", "price"],
                },
            }
        },
        "required": ["items"],
    },
)


def _normalize_basket_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize basket item dicts and compute line_total for each item."""
    normalized: list[dict[str, Any]] = []
    for raw in items:
        try:
            qty = max(1, int(raw.get("quantity") or 1))
        except (TypeError, ValueError):
            qty = 1
        try:
            price = round(float(raw.get("price") or 0.0), 2)
        except (TypeError, ValueError):
            price = 0.0
        line_total = round(price * qty, 2)
        entry: dict[str, Any] = {
            "menu_item_id": str(raw.get("menu_item_id", "")),
            "name": str(raw.get("name", "")),
            "quantity": qty,
            "price": price,
            "line_total": line_total,
        }
        customizations = raw.get("customizations")
        if customizations and str(customizations).strip():
            entry["customizations"] = str(customizations).strip()
        normalized.append(entry)
    return normalized


def execute_update_order_state(arguments: dict[str, Any]) -> str:
    """
    Execute update_order_state in-memory and return a JSON string suitable for
    both VoiceLive function_call_output and browser WebSocket synchronization.
    """
    raw_items = arguments.get("items", []) or []
    raw_stage = str(arguments.get("next_stage", "burgers")).lower().strip()
    stage = raw_stage if raw_stage in ORDERING_STAGES else "burgers"
    highlighted = [
        str(item_id) for item_id in (arguments.get("highlighted_item_ids") or []) if item_id
    ]

    normalized_items = _normalize_basket_items(raw_items)
    subtotal = round(sum(i["line_total"] for i in normalized_items), 2)
    tax = round(subtotal * TAX_RATE, 2)
    grand_total = round(subtotal + tax, 2)
    item_count = sum(i["quantity"] for i in normalized_items)

    return json.dumps(
        {
            "success": True,
            "stage": stage,
            "items": normalized_items,
            "subtotal": subtotal,
            "tax": tax,
            "grand_total": grand_total,
            "item_count": item_count,
            "highlighted_item_ids": highlighted,
        }
    )


def execute_submit_order(
    arguments: dict[str, Any],
    db: FabricDBClient | None = None,
    session_id: str = "",
) -> str:
    """
    Execute submit_order and return a JSON string suitable for
    a VoiceLive function_call result.
    """
    items = arguments.get("items", [])

    if not items:
        return json.dumps({"success": False, "error": "No items provided."})

    try:
        normalized_items = _normalize_basket_items(items)
        db = db or FabricDBClient()
        result = db.submit_order(items=items, session_id=session_id)
        result["success"] = True
        result["items"] = normalized_items
        return json.dumps(result)
    except Exception as e:
        logger.error("submit_order failed: %s", e)
        return json.dumps(
            {
                "success": False,
                "error": "Sorry, I couldn't place your order. Please try again.",
            }
        )
