"""Unit tests for backend diagnostics and deep health checks."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.backend.diagnostics import (
    check_fabric_database,
    check_voicelive_auth,
    check_analytics_agent,
    run_deep_diagnostics,
)
from src.backend.relay import app


class TestFabricDatabaseCheck:
    def test_missing_connection_string_returns_error(self, monkeypatch):
        monkeypatch.delenv("FABRIC_CONNECTION_STRING", raising=False)
        res = check_fabric_database()
        assert res["status"] == "error"
        assert "FABRIC_CONNECTION_STRING is not set" in res["message"]

    def test_successful_database_query(self, monkeypatch):
        monkeypatch.setenv("FABRIC_CONNECTION_STRING", "mock_conn_str")
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [23]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__.return_value = mock_conn

        with patch("src.backend.diagnostics.FabricDBClient") as mock_client:
            mock_client.return_value._get_connection.return_value = mock_conn
            res = check_fabric_database()

        assert res["status"] == "ok"
        assert "23 items in menu" in res["message"]
        assert res["latency_ms"] >= 0

    def test_database_connection_failure(self, monkeypatch):
        monkeypatch.setenv("FABRIC_CONNECTION_STRING", "mock_conn_str")
        with patch("src.backend.diagnostics.FabricDBClient") as mock_client:
            mock_client.return_value._get_connection.side_effect = Exception("DB Connection Timeout")
            res = check_fabric_database()

        assert res["status"] == "error"
        assert "DB Connection Timeout" in res["message"]


class TestVoiceLiveAuthCheck:
    def test_successful_token_and_url(self):
        with patch("src.backend.diagnostics.get_azure_token", return_value="fake_token"), \
             patch("src.backend.diagnostics.build_ws_url", return_value="wss://example.com/api/projects/my-proj/agents/drivethru-ordering-agent/endpoint/protocols/voice?api-version=v1&agent_session_id=123&store=true"):
            res = check_voicelive_auth()

        assert res["status"] == "ok"
        assert "Entra ID token acquired" in res["message"]

    def test_token_acquisition_failure(self):
        with patch("src.backend.diagnostics.get_azure_token", side_effect=Exception("MSI auth failed")):
            res = check_voicelive_auth()

        assert res["status"] == "error"
        assert "MSI auth failed" in res["message"]


class TestAnalyticsAgentCheck:
    def test_successful_client_init(self):
        mock_client = MagicMock()
        mock_client.project_endpoint = "https://example.com/project"
        mock_client.model = "gpt-5.4"

        with patch("src.backend.diagnostics.get_foundry_chat_client", return_value=mock_client):
            res = check_analytics_agent()

        assert res["status"] == "ok"
        assert "gpt-5.4" in res["message"]

    def test_failed_client_init(self):
        with patch("src.backend.diagnostics.get_foundry_chat_client", side_effect=ValueError("PROJECT_ENDPOINT missing")):
            res = check_analytics_agent()

        assert res["status"] == "error"
        assert "PROJECT_ENDPOINT missing" in res["message"]


class TestRunDeepDiagnostics:
    @pytest.mark.asyncio
    async def test_all_healthy_returns_200(self):
        with patch("src.backend.diagnostics.check_fabric_database", return_value={"status": "ok", "message": "DB OK"}), \
             patch("src.backend.diagnostics.check_voicelive_auth", return_value={"status": "ok", "message": "VL OK"}), \
             patch("src.backend.diagnostics.check_analytics_agent", return_value={"status": "ok", "message": "Analytics OK"}):
            status, payload, code = await run_deep_diagnostics()

        assert status == "healthy"
        assert code == 200
        assert payload["status"] == "healthy"
        assert payload["components"]["database"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_component_failure_returns_530(self):
        with patch("src.backend.diagnostics.check_fabric_database", return_value={"status": "error", "message": "DB Down"}), \
             patch("src.backend.diagnostics.check_voicelive_auth", return_value={"status": "ok", "message": "VL OK"}), \
             patch("src.backend.diagnostics.check_analytics_agent", return_value={"status": "ok", "message": "Analytics OK"}):
            status, payload, code = await run_deep_diagnostics()

        assert status == "unhealthy"
        assert code == 503
        assert payload["components"]["database"]["status"] == "error"


class TestDiagnosticsEndpoint:
    def test_endpoint_returns_json_response(self):
        client = TestClient(app)
        with patch(
            "src.backend.relay.run_deep_diagnostics",
            return_value=("healthy", {"status": "healthy", "components": {}}, 200),
        ):
            resp = client.get("/health/deep")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"

    def test_endpoint_returns_503_when_degraded(self):
        client = TestClient(app)
        with patch(
            "src.backend.relay.run_deep_diagnostics",
            return_value=("unhealthy", {"status": "unhealthy", "components": {}}, 503),
        ):
            resp = client.get("/health/deep")
            assert resp.status_code == 503
            assert resp.json()["status"] == "unhealthy"
