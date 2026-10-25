import os
import uuid
from urllib.parse import quote, urlencode, urlsplit
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

VOICELIVE_DEFAULT_ENDPOINT = "https://aif-voiceliveapi-demo.services.ai.azure.com"
VOICELIVE_ENDPOINT = (
    os.getenv("VOICELIVE_ENDPOINT") or VOICELIVE_DEFAULT_ENDPOINT
).rstrip("/")
PROJECT_NAME = os.getenv("PROJECT_NAME", "proj-voiceliveapi-demo")
PROJECT_ENDPOINT = (
    os.getenv("PROJECT_ENDPOINT")
    or os.getenv("AZURE_VOICE_AGENTS_ENDPOINT")
    or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    or ""
).rstrip("/")
AGENT_NAME = (
    os.getenv("VOICE_AGENT_NAME")
    or (
        os.getenv("AGENT_NAME")
        if os.getenv("AGENT_NAME") != "drivethru-ordering-agent"
        else "drivethru-voice-agent"
    )
    or "drivethru-voice-agent"
)
AGENT_VERSION = os.getenv("AGENT_VERSION", "2")
VOICE_AGENT_API_VERSION = os.getenv("VOICE_AGENT_API_VERSION", "v1")
FOUNDRY_FEATURES = os.getenv("FOUNDRY_FEATURES", "VoiceAgents=V1Preview")

# Backward-compatibility for relay.py (Task 3 will migrate relay):
SESSION_CONFIG: dict = {}

_credential = DefaultAzureCredential()


def get_azure_token() -> str:
    token = _credential.get_token("https://ai.azure.com/.default")
    return token.token


def resolve_project_endpoint(
    endpoint: str | None = None,
    project_name: str | None = None,
) -> str:
    """
    Resolve an Azure AI Foundry Project endpoint in the form:
    https://<account>.services.ai.azure.com/api/projects/<project-name>
    """
    raw = (
        endpoint
        or os.getenv("PROJECT_ENDPOINT")
        or os.getenv("AZURE_VOICE_AGENTS_ENDPOINT")
        or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        or os.getenv("VOICELIVE_ENDPOINT")
        or PROJECT_ENDPOINT
        or VOICELIVE_ENDPOINT
        or VOICELIVE_DEFAULT_ENDPOINT
    ).rstrip("/")

    if raw.startswith("wss://"):
        raw = raw.replace("wss://", "https://", 1)
    elif raw.startswith("ws://"):
        raw = raw.replace("ws://", "http://", 1)
    elif not raw.startswith("http://") and not raw.startswith("https://"):
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    if "/api/projects/" in parsed.path:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"

    proj = (project_name or os.getenv("PROJECT_NAME") or PROJECT_NAME).strip()
    return f"{parsed.scheme}://{parsed.netloc}/api/projects/{quote(proj, safe='')}"


def build_voice_agent_ws_url(
    endpoint: str | None = None,
    agent_name: str | None = None,
    session_id: str | None = None,
    store: bool = True,
) -> str:
    """
    Build the Foundry Voice Agent protocol WebSocket URL:
    wss://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent>/endpoint/protocols/voice
    """
    project_url = resolve_project_endpoint(endpoint=endpoint)
    if project_url.startswith("https://"):
        ws_project_url = project_url.replace("https://", "wss://", 1)
    elif project_url.startswith("http://"):
        ws_project_url = project_url.replace("http://", "ws://", 1)
    else:
        ws_project_url = project_url

    resolved_agent = (agent_name or AGENT_NAME).strip()
    resolved_session_id = (session_id or f"web-{uuid.uuid4().hex}").strip()
    api_version = (os.getenv("VOICE_AGENT_API_VERSION") or VOICE_AGENT_API_VERSION).strip()

    params: dict[str, str] = {
        "api-version": api_version,
        "agent_session_id": resolved_session_id,
    }
    if store:
        params["store"] = "true"

    return (
        f"{ws_project_url}/agents/{quote(resolved_agent, safe='')}"
        f"/endpoint/protocols/voice?{urlencode(params)}"
    )


def build_voice_agent_headers(
    access_token: str,
    client_request_id: str | None = None,
) -> dict[str, str]:
    """Build HTTP/WebSocket headers for Foundry Voice Agent connections."""
    features = (os.getenv("FOUNDRY_FEATURES") or FOUNDRY_FEATURES).strip()
    return {
        "Authorization": f"Bearer {access_token}",
        "Foundry-Features": features,
        "x-ms-client-request-id": client_request_id or str(uuid.uuid4()),
    }


def build_ws_url(
    access_token: str = "",
    endpoint: str | None = None,
    session_id: str | None = None,
) -> str:
    """
    Build the Voice Agent WebSocket URL.
    Note: access_token is intentionally NOT placed in query parameters in the new Voice Agent architecture.
    """
    _ = access_token
    return build_voice_agent_ws_url(endpoint=endpoint, session_id=session_id)
