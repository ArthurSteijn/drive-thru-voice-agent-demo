import pytest
from src.backend.config import (
    FOUNDRY_FEATURES,
    build_voice_agent_headers,
    build_voice_agent_ws_url,
    build_ws_url,
    resolve_project_endpoint,
)


def test_resolve_project_endpoint_from_full_project_url():
    url = resolve_project_endpoint(
        endpoint="https://myaccount.services.ai.azure.com/api/projects/my-proj/"
    )
    assert url == "https://myaccount.services.ai.azure.com/api/projects/my-proj"


def test_resolve_project_endpoint_from_resource_url_and_project_name():
    url = resolve_project_endpoint(
        endpoint="https://myaccount.services.ai.azure.com",
        project_name="my-proj",
    )
    assert url == "https://myaccount.services.ai.azure.com/api/projects/my-proj"


def test_build_voice_agent_ws_url_uses_protocols_voice_and_no_token():
    url = build_voice_agent_ws_url(
        endpoint="https://myaccount.services.ai.azure.com/api/projects/my-proj",
        agent_name="drivethru-ordering-agent",
        session_id="sess-123",
    )
    assert url == (
        "wss://myaccount.services.ai.azure.com/api/projects/my-proj"
        "/agents/drivethru-ordering-agent/endpoint/protocols/voice"
        "?api-version=v1&agent_session_id=sess-123&store=true"
    )
    assert "agent-access-token" not in url


def test_build_ws_url_never_leaks_access_token_in_query():
    token = "secret_bearer_token_should_not_be_in_url"
    url = build_ws_url(token, endpoint="https://custom.services.ai.azure.com")
    assert url.startswith("wss://custom.services.ai.azure.com/api/projects/")
    assert "/agents/" in url
    assert "/endpoint/protocols/voice" in url
    assert token not in url
    assert "agent-access-token" not in url


def test_build_voice_agent_headers_includes_bearer_and_foundry_features():
    headers = build_voice_agent_headers("my_token", client_request_id="req-001")
    assert headers["Authorization"] == "Bearer my_token"
    assert headers["Foundry-Features"] == FOUNDRY_FEATURES
    assert headers["x-ms-client-request-id"] == "req-001"
