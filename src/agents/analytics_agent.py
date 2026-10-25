"""
Analytics Agent module using the Microsoft Agent Framework.

Provides the AnalyticsAgent class which acts as a database analytics summarizer,
querying Microsoft Fabric database views using MAF's tool and agent abstractions.
"""

import os
import json
import logging
from typing import Annotated, Any

from azure.identity import DefaultAzureCredential
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient

from src.fabric.db_client import FabricDBClient

logger = logging.getLogger(__name__)

# ── Analytics Agent Tool ────────────────────────────────────────────

@tool
def query_database_analytics(
    metric: Annotated[
        str,
        "The analytics metric to query. Must be one of: 'popular_items', 'order_count', 'revenue', 'average_order_value'."
    ],
    time_period: Annotated[
        str,
        "The time period for analytics. Must be one of: 'today', 'week', 'month'."
    ] = "today"
) -> str:
    """
    Query historical sales, orders, revenue, and popular items analytics from the Microsoft Fabric database.
    """
    logger.info("Analytics tool called: metric=%s, time_period=%s", metric, time_period)
    try:
        db = FabricDBClient()
        result = db.get_order_analytics(metric=metric, time_period=time_period)
        return json.dumps(result)
    except Exception as e:
        logger.exception("Error querying database analytics in tool")
        return json.dumps({"success": False, "error": str(e)})


# ── Client Resolution ───────────────────────────────────────────────

def get_foundry_chat_client() -> FoundryChatClient:
    """
    Initialize FoundryChatClient using project endpoint and model configuration from env.
    """
    project_endpoint = os.environ.get("PROJECT_ENDPOINT")
    if not project_endpoint:
        voicelive_endpoint = os.environ.get("VOICELIVE_ENDPOINT", "").rstrip("/")
        project_name = os.environ.get("PROJECT_NAME", "")
        if voicelive_endpoint and project_name:
            project_endpoint = f"{voicelive_endpoint}/api/projects/{project_name}"

    deployment_name = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-5.4")
    
    if not project_endpoint:
        raise ValueError(
            "PROJECT_ENDPOINT is not configured in the environment. "
            "Please check your .env file."
        )

    logger.info("Creating FoundryChatClient with endpoint: %s, model: %s", project_endpoint, deployment_name)
    return FoundryChatClient(
        project_endpoint=project_endpoint,
        model=deployment_name,
        credential=DefaultAzureCredential()
    )


# ── Analytics Agent Implementation ──────────────────────────────────

class AnalyticsAgent:
    """
    Specialized business analytics agent utilizing Microsoft Agent Framework.
    """

    def __init__(self) -> None:
        self.client = get_foundry_chat_client()
        
        self.instructions = (
            "You are a specialized business analytics agent for DriveThru, a fast-food restaurant.\n"
            "Your role is to analyze sales data and provide clear summaries regarding:\n"
            "1. Most popular menu items (best sellers)\n"
            "2. Total order counts\n"
            "3. Total revenue generated\n"
            "4. Average order value\n\n"
            "Rules:\n"
            "- You MUST use the `query_database_analytics` tool to fetch actual metrics. Do not invent any numbers.\n"
            "- Summarize findings concisely, professionally, and naturally.\n"
            "- Keep your response short and formatted for a voice/chat relay (no markdown tables, write in conversational text)."
        )

    async def get_insights(self, query: str) -> str:
        """
        Ask the Analytics Agent a query and return its analysis text.
        """
        # Instantiate Agent contextually to manage thread state cleanly
        async with Agent(
            client=self.client,
            name="drivethru-analytics-agent",
            instructions=self.instructions,
            tools=[query_database_analytics]
        ) as agent:
            logger.info("Running query on AnalyticsAgent: %s", query)
            response = await agent.run(query)
            return response.text
