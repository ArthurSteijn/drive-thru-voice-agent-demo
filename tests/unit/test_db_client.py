"""Unit tests for FabricDBClient logic (mocked pyodbc)."""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

from src.fabric.db_client import FabricDBClient, TAX_RATE


def make_mock_row(*values):
    """Create a mock cursor row with index access."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    return row


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FABRIC_CONNECTION_STRING", "mock-connection-string")
    return FabricDBClient(connection_string="mock-connection-string")


@pytest.fixture
def mock_conn():
    """Context manager mock for pyodbc.connect."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn, cursor


class TestFabricDBClientInit:
    def test_raises_when_connection_string_missing(self, monkeypatch):
        monkeypatch.delenv("FABRIC_CONNECTION_STRING", raising=False)
        with pytest.raises(ValueError, match="FABRIC_CONNECTION_STRING"):
            FabricDBClient()

    def test_accepts_explicit_connection_string(self):
        db = FabricDBClient(connection_string="Driver=test")
        assert db.conn_str == "Driver=test"


class TestGetMenu:
    def test_returns_all_items(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [
            make_mock_row("BURGER_001", "Classic Cheeseburger", "burgers", "Desc", 8.99, 650, None)
        ]

        with patch("pyodbc.connect", return_value=conn):
            result = client.get_menu()

        assert len(result) == 1
        assert result[0]["menu_item_id"] == "BURGER_001"
        assert result[0]["price"] == 8.99

    def test_filters_by_category(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []

        with patch("pyodbc.connect", return_value=conn):
            client.get_menu(category="burgers")

        # Parameterized query should use the category arg
        call_args = cursor.execute.call_args
        assert "?" in call_args[0][0]
        assert call_args[0][1] == ("burgers",)

    def test_queries_all_when_no_category(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []

        with patch("pyodbc.connect", return_value=conn):
            client.get_menu()

        # No parameter tuple when fetching all
        call_args = cursor.execute.call_args
        assert len(call_args[0]) == 1  # only the SQL string, no params tuple


class TestSubmitOrder:
    ITEMS = [
        {"menu_item_id": "BURGER_001", "name": "Classic Cheeseburger", "quantity": 2, "price": 8.99},
        {"menu_item_id": "DRINK_001", "name": "Soft Drink", "quantity": 1, "price": 2.49},
    ]

    def test_calculates_totals_correctly(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = make_mock_row("00000000-0000-0000-0000-000000000001")

        with patch("pyodbc.connect", return_value=conn):
            result = client.submit_order(items=self.ITEMS)

        subtotal = 2 * 8.99 + 1 * 2.49  # 20.47
        expected_tax = round(subtotal * TAX_RATE, 2)
        expected_grand = round(subtotal + expected_tax, 2)

        assert result["total"] == round(subtotal, 2)
        assert result["tax"] == expected_tax
        assert result["grand_total"] == expected_grand

    def test_inserts_order_header_and_items(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = make_mock_row("00000000-0000-0000-0000-000000000001")

        with patch("pyodbc.connect", return_value=conn):
            client.submit_order(items=self.ITEMS, session_id="sess-abc")

        # 1 INSERT for Orders + 1 per item
        assert cursor.execute.call_count == 1 + len(self.ITEMS)
        conn.commit.assert_called_once()

    def test_returns_item_count_sum_of_quantities(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = make_mock_row("00000000-0000-0000-0000-000000000001")

        with patch("pyodbc.connect", return_value=conn):
            result = client.submit_order(items=self.ITEMS)

        assert result["item_count"] == 3  # 2 burgers + 1 drink
