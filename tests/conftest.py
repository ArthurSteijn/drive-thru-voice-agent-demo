"""Shared pytest fixtures for the DriveThru test suite."""

import os
import pytest
from unittest.mock import MagicMock, patch
from dotenv import load_dotenv

# Load environment variables from .env before test collection
load_dotenv()


# ── Environment variable fixtures ───────────────────────────────────

@pytest.fixture(autouse=True)
def clear_env(request, monkeypatch):
    """Remove real credentials from env so unit tests never hit Azure."""
    # Skip clearing environment for integration and e2e tests
    if "integration" in str(request.node.fspath) or "e2e" in str(request.node.fspath):
        return
    for key in [
        "FABRIC_CONNECTION_STRING",
        "PROJECT_ENDPOINT",
        "VOICELIVE_ENDPOINT",
        "AGENT_NAME",
        "PROJECT_NAME",
    ]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def relay_env(monkeypatch):
    """Set minimal env vars for relay tests."""
    monkeypatch.setenv("VOICELIVE_ENDPOINT", "https://example.services.ai.azure.com/")
    monkeypatch.setenv("AGENT_NAME", "test-agent")
    monkeypatch.setenv("PROJECT_NAME", "test-project")
    monkeypatch.setenv("VOICELIVE_API_VERSION", "2026-04-10")


# ── Fabric DB fixtures ───────────────────────────────────────────────

SAMPLE_MENU = [
    {
        "menu_item_id": "BURGER_001",
        "name": "Classic Cheeseburger",
        "category": "burgers",
        "description": "Our signature cheeseburger",
        "price": 8.99,
        "calories": 650,
        "allergens": None,
    },
    {
        "menu_item_id": "DRINK_001",
        "name": "Soft Drink",
        "category": "drinks",
        "description": "Cold soft drink (Medium)",
        "price": 2.49,
        "calories": 210,
        "allergens": None,
    },
]

SAMPLE_ORDER_RESULT = {
    "order_id": "00000000-0000-0000-0000-000000000001",
    "total": 11.48,
    "tax": 0.92,
    "grand_total": 12.40,
    "item_count": 2,
}


@pytest.fixture
def mock_db():
    """Return a MagicMock FabricDBClient pre-configured with sample data."""
    db = MagicMock()
    db.get_menu.return_value = SAMPLE_MENU
    db.submit_order.return_value = SAMPLE_ORDER_RESULT
    return db


@pytest.fixture
def mock_db_class(mock_db):
    """Patch FabricDBClient construction to return mock_db."""
    with patch("src.fabric.db_client.FabricDBClient", return_value=mock_db) as patched:
        yield patched, mock_db
