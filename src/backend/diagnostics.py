"""
Diagnostic and deep health check utilities.

Provides parallel verification of all critical components:
1. Microsoft Fabric Database (SQL query & connection)
2. Azure AI Foundry VoiceLive Auth (Entra ID token & URL construction)
3. Analytics Agent (Microsoft Agent Framework & Foundry chat client)
"""

import asyncio
import datetime
import logging
import os
import time
from typing import Any

from src.backend.config import (
    AGENT_NAME,
    PROJECT_NAME,
    VOICELIVE_ENDPOINT,
    build_ws_url,
    get_azure_token,
)
from src.agents.analytics_agent import get_foundry_chat_client
from src.fabric.db_client import FabricDBClient

logger = logging.getLogger(__name__)


def check_fabric_database() -> dict[str, Any]:
    t0 = time.perf_counter()
    conn_str = os.getenv("FABRIC_CONNECTION_STRING", "")
    if not conn_str:
        return {
            "status": "error",
            "message": "FABRIC_CONNECTION_STRING is not set",
            "latency_ms": 0.0,
        }
    try:
        db = FabricDBClient()
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Menu")
            count = cursor.fetchone()[0]
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "status": "ok",
            "message": f"Fabric SQL connected ({count} items in menu)",
            "latency_ms": elapsed,
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.error("Fabric database health check failed: %s", e)
        return {
            "status": "error",
            "message": f"Database error: {e}",
            "latency_ms": elapsed,
        }


def check_voicelive_auth() -> dict[str, Any]:
    t0 = time.perf_counter()
    if not VOICELIVE_ENDPOINT and not os.getenv("PROJECT_ENDPOINT"):
        return {
            "status": "error",
            "message": "PROJECT_ENDPOINT / VOICELIVE_ENDPOINT is not configured",
            "latency_ms": 0.0,
        }
    try:
        token = get_azure_token()
        ws_url = build_ws_url(token)
        if not ws_url.startswith("wss://") or "/endpoint/protocols/voice" not in ws_url:
            raise ValueError(f"Invalid Voice Agent WebSocket URL generated: {ws_url}")
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "status": "ok",
            "message": f"Entra ID token acquired for Voice Agent ({AGENT_NAME})",
            "latency_ms": elapsed,
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.error("Voice Agent auth health check failed: %s", e)
        return {
            "status": "error",
            "message": f"Auth error: {e}",
            "latency_ms": elapsed,
        }


def check_analytics_agent() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        client = get_foundry_chat_client()
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        model_name = getattr(client, "model", os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-5.4"))
        return {
            "status": "ok",
            "message": f"FoundryChatClient configured (model: {model_name})",
            "latency_ms": elapsed,
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.error("Analytics agent health check failed: %s", e)
        return {
            "status": "error",
            "message": f"Analytics config error: {e}",
            "latency_ms": elapsed,
        }


async def run_deep_diagnostics() -> tuple[str, dict[str, Any], int]:
    """
    Run all health checks in parallel.
    Returns (status, payload, http_status_code).
    """
    db_task = asyncio.to_thread(check_fabric_database)
    vl_task = asyncio.to_thread(check_voicelive_auth)
    analytics_task = asyncio.to_thread(check_analytics_agent)

    db_res, vl_res, analytics_res = await asyncio.gather(
        db_task, vl_task, analytics_task, return_exceptions=False
    )

    components = {
        "database": db_res,
        "voicelive_auth": vl_res,
        "analytics_agent": analytics_res,
    }

    all_ok = all(c["status"] == "ok" for c in components.values())
    overall_status = "healthy" if all_ok else "unhealthy"
    status_code = 200 if all_ok else 503

    payload = {
        "status": overall_status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "components": components,
    }

    return overall_status, payload, status_code
