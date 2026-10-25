"""Integration tests for the FastAPI relay backend."""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


@pytest.fixture
def relay_client(relay_env):
    """Create a TestClient for the relay app with env vars set."""
    # Import after env is set so module-level config is picked up
    import importlib
    import src.backend.relay as relay_module
    importlib.reload(relay_module)
    return TestClient(relay_module.app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, relay_client):
        response = relay_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_architecture_returns_metadata(self, relay_client):
        response = relay_client.get("/api/architecture")
        assert response.status_code == 200
        data = response.json()
        assert data["architecture"] == "foundry-voice-agent-v1"
        assert data["agent_kind"] == "voice"
        assert data["session_update_required"] is False
        assert data["token_in_query_string"] is False
        assert "foundry_features" in data
        assert "project_endpoint" in data



class TestVoiceWebSocket:
    def test_returns_error_when_env_vars_missing(self, relay_env, monkeypatch):
        """When required env vars are absent the relay sends an error and closes."""
        import importlib
        import src.backend.relay as relay_module
        importlib.reload(relay_module)

        # Patch module-level vars after reload to simulate missing config
        monkeypatch.setattr(relay_module, "VOICELIVE_ENDPOINT", "")
        monkeypatch.setattr(relay_module, "AGENT_NAME", "")
        monkeypatch.setattr(relay_module, "PROJECT_NAME", "")

        client = TestClient(relay_module.app)

        with client.websocket_connect("/ws/voice") as ws:
            msg = ws.receive_json()

        assert msg["type"] == "error"
        assert "VOICELIVE_ENDPOINT" in msg["message"] or "misconfigured" in msg["message"].lower()

    def test_returns_auth_error_when_token_fails(self, relay_env, monkeypatch):
        """When Azure token acquisition fails, an auth error is sent to browser."""
        import importlib
        import src.backend.relay as relay_module
        importlib.reload(relay_module)

        with patch.object(relay_module, "get_azure_token", side_effect=Exception("no login")):
            client = TestClient(relay_module.app)
            with client.websocket_connect("/ws/voice") as ws:
                msg = ws.receive_json()

        assert msg["type"] == "error"
        assert "auth" in msg["message"].lower() or "Authentication" in msg["message"]

    def test_returns_error_when_upstream_connect_fails(self, relay_env, monkeypatch):
        """When upstream Voice Agent connection fails, error is forwarded to browser."""
        import importlib
        import websockets
        import src.backend.relay as relay_module
        importlib.reload(relay_module)

        monkeypatch.setattr(relay_module, "get_azure_token", lambda: "mock-token")

        with patch("websockets.connect", side_effect=Exception("connection refused")):
            client = TestClient(relay_module.app)
            with client.websocket_connect("/ws/voice") as ws:
                msg = ws.receive_json()

        assert msg["type"] == "error"
        assert "Upstream Voice Agent connection failed: connection refused" in msg["message"]


    def test_voice_relay_barge_in(self, relay_env, monkeypatch):
        """Verify that relay sends response.cancel to VoiceLive on speech_started."""
        import importlib
        import websockets
        import src.backend.relay as relay_module
        importlib.reload(relay_module)

        monkeypatch.setattr(relay_module, "get_azure_token", lambda: "mock-token")

        mock_events = [
            json.dumps({"type": "session.updated", "session": {"id": "mock-session-123"}}),
            json.dumps({"type": "response.audio.delta", "response_id": "mock-resp-123", "delta": "mock-audio-base64"}),
            json.dumps({"type": "input_audio_buffer.speech_started"}),
        ]

        class MockWebSocketConn:
            def __init__(self):
                self.sent_messages = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def send(self, message):
                self.sent_messages.append(message)

            async def __aiter__(self):
                for event in mock_events:
                    yield event
                raise websockets.exceptions.ConnectionClosed(None, None)

        mock_conn = MockWebSocketConn()

        with patch("websockets.connect", return_value=mock_conn) as mock_connect:
            client = TestClient(relay_module.app)
            with client.websocket_connect("/ws/voice") as ws:
                msg1 = ws.receive_json()
                assert msg1["type"] == "session.created"

                msg2 = ws.receive_json()
                assert msg2["type"] == "response.audio.delta"

                msg3 = ws.receive_json()
                assert msg3["type"] == "input_audio_buffer.speech_started"

        # Verify websockets.connect was called with Foundry Voice Agent headers
        assert mock_connect.called
        headers = mock_connect.call_args.kwargs.get("additional_headers", {})
        assert headers.get("Authorization") == "Bearer mock-token"
        assert "Foundry-Features" in headers

        # In Foundry Voice Agent architecture, no session.update is sent to upstream
        sent_types = [json.loads(m)["type"] for m in mock_conn.sent_messages]
        assert "session.update" not in sent_types
        assert "response.cancel" in sent_types

    def test_voice_relay_barge_in_during_latency(self, relay_env, monkeypatch):
        """Verify that relay sends response.cancel on speech_started even if agent is not speaking but response is active."""
        import importlib
        import websockets
        import src.backend.relay as relay_module
        importlib.reload(relay_module)

        monkeypatch.setattr(relay_module, "get_azure_token", lambda: "mock-token")

        mock_events = [
            json.dumps({"type": "session.updated", "session": {"id": "mock-session-123"}}),
            json.dumps({"type": "response.created", "response": {"id": "mock-resp-123"}}),
            json.dumps({"type": "input_audio_buffer.speech_started"}),
        ]

        class MockWebSocketConn:
            def __init__(self):
                self.sent_messages = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def send(self, message):
                self.sent_messages.append(message)

            async def __aiter__(self):
                for event in mock_events:
                    yield event
                raise websockets.exceptions.ConnectionClosed(None, None)

        mock_conn = MockWebSocketConn()

        with patch("websockets.connect", return_value=mock_conn):
            client = TestClient(relay_module.app)
            with client.websocket_connect("/ws/voice") as ws:
                msg1 = ws.receive_json()
                assert msg1["type"] == "session.created"

                msg2 = ws.receive_json()
                assert msg2["type"] == "response.created"

                msg3 = ws.receive_json()
                assert msg3["type"] == "input_audio_buffer.speech_started"

        # Check that response.cancel was sent
        sent_types = [json.loads(msg)["type"] for msg in mock_conn.sent_messages]
        assert "response.cancel" in sent_types

    def test_voice_relay_no_double_greeting_fast_server(self, relay_env, monkeypatch):
        """Verify that relay does not send fallback greeting when server responds quickly."""
        import importlib
        import asyncio
        import websockets
        import src.backend.relay as relay_module
        importlib.reload(relay_module)

        monkeypatch.setattr(relay_module, "get_azure_token", lambda: "mock-token")

        mock_events = [
            json.dumps({"type": "session.updated", "session": {"id": "mock-session-123"}}),
            json.dumps({"type": "response.created", "response": {"id": "mock-resp-123"}}),
        ]

        class MockWebSocketConn:
            def __init__(self):
                self.sent_messages = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def send(self, message):
                self.sent_messages.append(message)

            async def __aiter__(self):
                for event in mock_events:
                    yield event
                # Give some time for the background task to potentially fire
                await asyncio.sleep(0.5)
                raise websockets.exceptions.ConnectionClosed(None, None)

        mock_conn = MockWebSocketConn()

        with patch("websockets.connect", return_value=mock_conn):
            client = TestClient(relay_module.app)
            with client.websocket_connect("/ws/voice") as ws:
                msg1 = ws.receive_json()
                assert msg1["type"] == "session.created"

        # Verify no conversation.item.create was sent by the relay for fallback greeting
        sent_types = [json.loads(msg)["type"] for msg in mock_conn.sent_messages]
        assert "conversation.item.create" not in sent_types

    def test_voice_relay_no_double_greeting_slow_server(self, relay_env, monkeypatch):
        """Verify that relay does not send fallback greeting when server responds within the extended timeout (e.g. 1.2s)."""
        import importlib
        import asyncio
        import websockets
        import src.backend.relay as relay_module
        importlib.reload(relay_module)

        monkeypatch.setattr(relay_module, "get_azure_token", lambda: "mock-token")

        class MockWebSocketConn:
            def __init__(self):
                self.sent_messages = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def send(self, message):
                self.sent_messages.append(message)

            async def __aiter__(self):
                yield json.dumps({"type": "session.updated", "session": {"id": "mock-session-123"}})
                # Sleep longer than the original 0.8s but shorter than the new timeout (e.g. 1.2s)
                await asyncio.sleep(1.2)
                yield json.dumps({"type": "response.created", "response": {"id": "mock-resp-123"}})
                # Wait a bit more
                await asyncio.sleep(0.5)
                raise websockets.exceptions.ConnectionClosed(None, None)

        mock_conn = MockWebSocketConn()

        with patch("websockets.connect", return_value=mock_conn):
            client = TestClient(relay_module.app)
            with client.websocket_connect("/ws/voice") as ws:
                msg1 = ws.receive_json()
                assert msg1["type"] == "session.created"

        # Verify no conversation.item.create was sent by the relay
        sent_types = [json.loads(msg)["type"] for msg in mock_conn.sent_messages]
        assert "conversation.item.create" not in sent_types



