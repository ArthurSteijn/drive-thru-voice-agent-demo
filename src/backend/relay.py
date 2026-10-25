import asyncio
import json
import logging
import uuid
from pathlib import Path
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.backend.config import (
    VOICELIVE_ENDPOINT,
    AGENT_NAME,
    PROJECT_NAME,
    FOUNDRY_FEATURES,
    VOICE_AGENT_API_VERSION,
    get_azure_token,
    build_voice_agent_headers,
    build_voice_agent_ws_url,
    resolve_project_endpoint,
)
from src.backend.diagnostics import run_deep_diagnostics
from src.backend.event_handlers import RelaySessionState, process_voicelive_event
from src.fabric.db_client import FabricDBClient
from src.fabric.demo_data import MENU_SEED

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DriveThru Voice Agent Relay (Foundry Voice Agent v1)")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/deep")
async def health_deep():
    _, payload, code = await run_deep_diagnostics()
    return JSONResponse(content=payload, status_code=code)


@app.get("/api/architecture")
async def get_architecture():
    """Return architecture metadata for side-by-side comparison with main."""
    return {
        "architecture": "foundry-voice-agent-v1",
        "agent_kind": "voice",
        "agent_name": AGENT_NAME,
        "api_version": VOICE_AGENT_API_VERSION,
        "foundry_features": FOUNDRY_FEATURES,
        "project_endpoint": resolve_project_endpoint(),
        "session_update_required": False,
        "token_in_query_string": False,
    }


@app.get("/api/menu")
async def get_menu():
    try:
        db = FabricDBClient()
        items = db.get_menu()
        return {"success": True, "items": items}
    except Exception as e:
        logger.warning(
            "Fabric database connection unavailable. Falling back to local menu seed. Error: %s",
            e,
        )
        return {"success": True, "items": MENU_SEED}


@app.websocket("/ws/voice")
async def voice_relay(browser_ws: WebSocket):
    await browser_ws.accept()
    logger.info("Incoming browser connection on /ws/voice")
    if not VOICELIVE_ENDPOINT or not AGENT_NAME or not PROJECT_NAME:
        await browser_ws.send_json({"type": "error", "message": "Server misconfigured"})
        return

    try:
        access_token = get_azure_token()
    except Exception as e:
        await browser_ws.send_json({"type": "error", "message": f"Auth failed: {e}"})
        return

    session_id = f"drivethru-{uuid.uuid4().hex}"
    ws_url = build_voice_agent_ws_url(session_id=session_id)
    headers = build_voice_agent_headers(access_token)
    logger.info("Connecting to Foundry Voice Agent WebSocket: %s", ws_url.split("?")[0])
    try:
        async with websockets.connect(
            ws_url,
            additional_headers=headers,
        ) as vl_ws:
            # In Foundry Voice Agent architecture (kind="voice"), session settings
            # live in the versioned VoiceAgentDefinition on the server. No session.update needed!
            state = RelaySessionState()

            async def receive_from_browser():
                try:
                    while True:
                        raw = await browser_ws.receive_text()
                        msg = json.loads(raw)
                        if msg.get("type") in (
                            "input_audio_buffer.append",
                            "response.cancel",
                            "conversation.item.truncate",
                        ):
                            await vl_ws.send(json.dumps(msg))
                except (WebSocketDisconnect, Exception):
                    pass

            async def receive_from_voicelive():
                async def send_to_vl(payload: str) -> None:
                    await vl_ws.send(payload)

                try:
                    async for raw_msg in vl_ws:
                        event = json.loads(raw_msg)
                        await process_voicelive_event(event, state, browser_ws, send_to_vl)
                except Exception as e:
                    logger.error("Voice Agent stream error: %s", e)

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(receive_from_browser()),
                    asyncio.create_task(receive_from_voicelive()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except Exception as e:
        logger.error("Relay session error: %s", e)
        try:
            await browser_ws.send_json({
                "type": "error",
                "message": f"Upstream Voice Agent connection failed: {e}",
            })
        except Exception:
            pass



FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
