"""
Integration tests for FabricDBClient against a real Fabric SQL Database.

These tests are skipped unless FABRIC_CONNECTION_STRING is set AND a live
connection can be established. Run locally after setting up the Fabric DB:

    set FABRIC_CONNECTION_STRING=Driver=...;Server=...;Database=DriveThru;...
    pytest tests/integration/test_fabric_db.py -v
"""

import os
import pytest


@pytest.fixture(scope="module", autouse=True)
def require_fabric_connection():
    """Skip entire module when Fabric DB is unavailable."""
    conn_str = os.getenv("FABRIC_CONNECTION_STRING", "")
    if not conn_str:
        pytest.skip("FABRIC_CONNECTION_STRING not set — skipping live Fabric DB tests")
    # Verify connectivity with a quick probe
    try:
        import pyodbc
        with pyodbc.connect(conn_str, timeout=5):
            pass
    except Exception as exc:
        pytest.skip(f"Fabric DB not reachable: {exc}")


@pytest.fixture(scope="module")
def db():
    from src.fabric.db_client import FabricDBClient
    return FabricDBClient()


class TestGetMenuLive:
    def test_returns_at_least_one_item(self, db):
        items = db.get_menu()
        assert len(items) > 0

    def test_item_has_required_fields(self, db):
        items = db.get_menu()
        required = {"menu_item_id", "name", "category", "price"}
        for item in items:
            assert required.issubset(item.keys()), f"Missing fields in {item}"

    def test_filter_by_category_returns_subset(self, db):
        all_items = db.get_menu()
        burgers = db.get_menu(category="burgers")
        assert len(burgers) <= len(all_items)
        for item in burgers:
            assert item["category"] == "burgers"

    def test_unknown_category_returns_empty(self, db):
        result = db.get_menu(category="nonexistent_category_xyz")
        assert result == []


class TestSubmitOrderLive:
    TEST_ITEMS = [
        {"menu_item_id": "BURGER_001", "name": "Classic Cheeseburger", "quantity": 1, "price": 8.99},
    ]

    def test_order_returns_order_id(self, db):
        result = db.submit_order(items=self.TEST_ITEMS, session_id="test-session-live")
        assert "order_id" in result
        assert len(result["order_id"]) > 0

    def test_order_calculates_tax(self, db):
        result = db.submit_order(items=self.TEST_ITEMS, session_id="test-session-live")
        assert result["tax"] > 0
        assert result["grand_total"] > result["total"]

    def test_order_persists_to_db(self, db):
        """Verify the submitted order actually appears in the Orders table."""
        result = db.submit_order(items=self.TEST_ITEMS, session_id="test-session-verify")
        order_id = result["order_id"]

        import pyodbc
        with pyodbc.connect(db.conn_str) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT OrderId FROM Orders WHERE OrderId = ?", (order_id,))
            row = cursor.fetchone()

        assert row is not None, f"Order {order_id} not found in DB"
