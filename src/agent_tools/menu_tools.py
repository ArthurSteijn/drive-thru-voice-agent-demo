"""Menu query tools — FunctionTool definitions and execution logic."""

import json
import logging
import os
from typing import Any

from azure.ai.projects.models import FunctionTool

from src.fabric.db_client import FabricDBClient
from src.fabric.demo_data import MENU_SEED

logger = logging.getLogger(__name__)

# ── FunctionTool for Foundry Agent registration ─────────────────────

get_menu_items_tool = FunctionTool(
    name="get_menu_items",
    description=(
        "Get available menu items from the restaurant. "
        "Can filter by category: burgers, chicken, sides, drinks, desserts. "
        "Returns item names, descriptions, prices, and calorie counts."
    ),
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Menu category to filter by. Omit to get the full menu.",
                "enum": ["burgers", "chicken", "sides", "drinks", "desserts"],
            }
        },
        "required": [],
    },
)


def execute_get_menu_items(
    arguments: dict[str, Any],
    db: FabricDBClient | None = None,
) -> str:
    """
    Execute get_menu_items and return a JSON string suitable for
    a VoiceLive function_call result.
    """
    category = arguments.get("category")

    if db is None and not os.getenv("FABRIC_CONNECTION_STRING"):
        items = [
            dict(item)
            for item in MENU_SEED
            if not category or item["category"].lower() == category.lower()
        ]
        return json.dumps({"success": True, "items": items, "count": len(items)})

    try:
        db = db or FabricDBClient()
        items = db.get_menu(category=category)
        result = {"success": True, "items": items, "count": len(items)}
    except Exception as e:
        logger.error("get_menu_items failed: %s", e)
        result = {
            "success": False,
            "error": "Sorry, I couldn't load the menu right now. Please try again.",
        }

    return json.dumps(result)
