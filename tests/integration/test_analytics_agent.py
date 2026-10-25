"""Integration tests for AnalyticsAgent delegation using mocked LLM clients."""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.agent_tools.analytics_tools import execute_get_order_analytics


@pytest.fixture
def mock_agent_framework(monkeypatch):
    """Mock agent-framework classes to prevent network calls and return pre-defined responses."""
    monkeypatch.setenv("PROJECT_ENDPOINT", "https://mock.services.ai.azure.com/api/projects/proj-mock")
    monkeypatch.setenv("MODEL_DEPLOYMENT_NAME", "gpt-mock")
    
    mock_client = MagicMock()
    
    # Create an async mock for the context manager __aenter__ / __aexit__
    mock_chat_agent = MagicMock()
    mock_chat_agent.__aenter__ = AsyncMock(return_value=mock_chat_agent)
    mock_chat_agent.__aexit__ = AsyncMock(return_value=None)
    
    # Set the mock run response
    mock_response = MagicMock()
    mock_response.text = "Mocked Analytics Insight: French Fries and milkshakes are popular today."
    mock_chat_agent.run = AsyncMock(return_value=mock_response)
    
    with patch("src.agents.analytics_agent.FoundryChatClient", return_value=mock_client), \
         patch("src.agents.analytics_agent.Agent", return_value=mock_chat_agent) as mock_agent_class:
        yield mock_agent_class, mock_chat_agent, mock_response


class TestAnalyticsAgentIntegration:
    def test_execute_get_order_analytics_delegation(self, mock_agent_framework):
        mock_agent_class, mock_chat_agent, mock_response = mock_agent_framework
        
        args = {"query": "What is the most popular menu item?"}
        
        # Execute the tool
        result_json = execute_get_order_analytics(args)
        result = json.loads(result_json)
        
        # Verify success and returned value
        assert result["success"] is True
        assert "French Fries" in result["insights"]
        
        # Verify that Agent was initialized with correct instructions and tools
        mock_agent_class.assert_called_once()
        kwargs = mock_agent_class.call_args[1]
        assert kwargs["name"] == "drivethru-analytics-agent"
        assert len(kwargs["tools"]) == 1
        assert kwargs["tools"][0].name == "query_database_analytics"
        
        # Verify agent.run() was called with our query
        mock_chat_agent.run.assert_called_once_with("What is the most popular menu item?")

    def test_execute_get_order_analytics_missing_query(self):
        result_json = execute_get_order_analytics({})
        result = json.loads(result_json)
        assert result["success"] is False
        assert "No query" in result["error"]
