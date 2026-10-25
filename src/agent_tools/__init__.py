"""Agent tool definitions — FunctionTool objects for Foundry Agent registration."""

from src.agent_tools.menu_tools import get_menu_items_tool, execute_get_menu_items
from src.agent_tools.order_tools import (
    ORDERING_STAGES,
    update_order_state_tool,
    execute_update_order_state,
    submit_order_tool,
    execute_submit_order,
)
from src.agent_tools.analytics_tools import get_order_analytics_tool, execute_get_order_analytics

# All FunctionTool objects to register with the agent
ALL_TOOLS = [
    get_menu_items_tool,
    update_order_state_tool,
    submit_order_tool,
    get_order_analytics_tool,
]

__all__ = [
    "ALL_TOOLS",
    "ORDERING_STAGES",
    "get_menu_items_tool",
    "update_order_state_tool",
    "submit_order_tool",
    "get_order_analytics_tool",
    "execute_get_menu_items",
    "execute_update_order_state",
    "execute_submit_order",
    "execute_get_order_analytics",
]
