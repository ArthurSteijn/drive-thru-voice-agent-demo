"""Analytics query tools — FunctionTool definitions and execution logic."""

import json
import logging
import asyncio
import concurrent.futures
from typing import Any

from azure.ai.projects.models import FunctionTool

from src.agents.analytics_agent import AnalyticsAgent

logger = logging.getLogger(__name__)

# ── FunctionTool for Foundry Agent registration ─────────────────────

get_order_analytics_tool = FunctionTool(
    name="get_order_analytics",
    description=(
        "Query sales trends, popular items, order counts, revenue, and average order value. "
        "Use this tool whenever the customer asks about popular items, recommendation trends, "
        "or general sales metrics. Returns a textual summary of the insights."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The natural language question about analytics (e.g. 'What is the most popular burger today?', 'What is our total revenue this week?').",
            }
        },
        "required": ["query"],
    },
)


def execute_get_order_analytics(
    arguments: dict[str, Any],
) -> str:
    """
    Execute get_order_analytics and return a JSON string suitable for
    a VoiceLive function_call result. Delegates to the MAF AnalyticsAgent.
    """
    query = arguments.get("query")
    if not query:
        return json.dumps({"success": False, "error": "No query provided."})

    try:
        agent = AnalyticsAgent()
        
        # Run the async agent query in a separate thread so it works properly
        # in both async (e.g., FastAPI) and sync (e.g., CLI) environments.
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(agent.get_insights(query)))
            insights = future.result()
            
        result = {"success": True, "insights": insights}
    except Exception as e:
        logger.error("get_order_analytics via AnalyticsAgent failed: %s. Falling back to direct DB analytics.", e)
        try:
            from src.fabric.db_client import FabricDBClient
            db = FabricDBClient()
            data = db.get_order_analytics("popular_items", "today")
            if data and isinstance(data, list):
                top_items = [f"{item['name']} ({item['quantity_sold']} sold)" for item in data[:3]]
                summary = f"Our top selling items today are {', '.join(top_items)}."
                return json.dumps({"success": True, "insights": summary})
        except Exception as db_err:
            logger.error("Direct DB analytics fallback failed: %s", db_err)

        result = {
            "success": False,
            "error": "Sorry, I couldn't load the analytics data right now. Please try again.",
        }

    return json.dumps(result)
