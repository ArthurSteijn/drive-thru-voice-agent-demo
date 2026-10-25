"""Unit tests for get_order_analytics query logic in FabricDBClient."""

import pytest
from unittest.mock import MagicMock, patch

from src.fabric.db_client import FabricDBClient
from tests.unit.test_db_client import make_mock_row, client, mock_conn


class TestGetOrderAnalytics:
    def test_popular_items_query_building(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchall.return_value = [
            make_mock_row("BURGER_001", "Classic Cheeseburger", "burgers", 10, 89.90)
        ]

        with patch("pyodbc.connect", return_value=conn):
            result = client.get_order_analytics(metric="popular_items", time_period="week")

        assert len(result) == 1
        assert result[0]["menu_item_id"] == "BURGER_001"
        assert result[0]["quantity_sold"] == 10
        assert result[0]["revenue"] == 89.90

        call_args = cursor.execute.call_args[0][0]
        assert "OrderAnalytics" in call_args
        assert "SUM(TotalQuantitySold)" in call_args
        assert "DATEADD(day, -7" in call_args

    def test_order_count_query_building(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = make_mock_row(42)

        with patch("pyodbc.connect", return_value=conn):
            result = client.get_order_analytics(metric="order_count", time_period="today")

        assert result["metric"] == "order_count"
        assert result["value"] == 42
        assert result["time_period"] == "today"

        call_args = cursor.execute.call_args[0][0]
        assert "COUNT(OrderId)" in call_args
        assert "Orders" in call_args
        assert "CAST(GETUTCDATE() AS DATE)" in call_args

    def test_revenue_query_building(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = make_mock_row(500.50)

        with patch("pyodbc.connect", return_value=conn):
            result = client.get_order_analytics(metric="revenue", time_period="month")

        assert result["metric"] == "revenue"
        assert result["value"] == 500.50
        assert result["time_period"] == "month"

        call_args = cursor.execute.call_args[0][0]
        assert "SUM(TotalAmount)" in call_args
        assert "Orders" in call_args
        assert "DATEADD(month, -1" in call_args

    def test_average_order_value_query_building(self, client, mock_conn):
        conn, cursor = mock_conn
        cursor.fetchone.return_value = make_mock_row(12.50)

        with patch("pyodbc.connect", return_value=conn):
            result = client.get_order_analytics(metric="average_order_value", time_period="week")

        assert result["metric"] == "average_order_value"
        assert result["value"] == 12.50
        assert result["time_period"] == "week"

        call_args = cursor.execute.call_args[0][0]
        assert "AVG(TotalAmount)" in call_args
        assert "Orders" in call_args
        assert "DATEADD(day, -7" in call_args

    def test_raises_on_unknown_metric(self, client, mock_conn):
        conn, cursor = mock_conn
        with patch("pyodbc.connect", return_value=conn):
            with pytest.raises(ValueError, match="Unknown metric"):
                client.get_order_analytics(metric="unknown_metric")
