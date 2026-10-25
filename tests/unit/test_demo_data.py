"""Unit tests for src/fabric/demo_data.py — pure-Python data generators."""

from datetime import datetime, timedelta, timezone

import pytest

from src.fabric.demo_data import (
    CUSTOMER_SEED,
    MENU_SEED,
    ORDER_STATUS_WEIGHTS,
    TAX_RATE,
    GeneratedOrder,
    generate_customers,
    generate_menu,
    generate_orders,
)


# ── Menu / customer generators ──────────────────────────────────────


class TestGenerateMenu:
    def test_returns_all_seeded_items(self):
        menu = generate_menu()
        assert len(menu) == len(MENU_SEED)

    def test_returns_independent_copies(self):
        m1 = generate_menu()
        m1[0]["price"] = 0.0
        m2 = generate_menu()
        assert m2[0]["price"] != 0.0

    def test_every_item_has_required_fields(self):
        for item in generate_menu():
            for key in ("menu_item_id", "name", "category", "price", "calories"):
                assert key in item
            assert item["price"] > 0
            assert item["category"] in {"burgers", "chicken", "sides", "drinks", "desserts"}


class TestGenerateCustomers:
    def test_returns_seeded_customers(self):
        customers = generate_customers()
        assert len(customers) == len(CUSTOMER_SEED)

    def test_emails_are_derived(self):
        customers = generate_customers()
        first = customers[0]
        assert first["email"].endswith("@example.com")
        assert first["first_name"].lower() in first["email"]

    def test_loyalty_points_increase(self):
        customers = generate_customers()
        points = [c["loyalty_points"] for c in customers]
        assert points == sorted(points)
        assert all(p > 0 for p in points)


# ── Order generator ─────────────────────────────────────────────────


class TestGenerateOrders:
    def setup_method(self):
        self.menu = generate_menu()
        self.customers = generate_customers()
        self.end = datetime(2026, 4, 1, tzinfo=timezone.utc)

    def test_returns_orders_within_date_range(self):
        orders = generate_orders(
            menu=self.menu, customers=self.customers,
            days=7, orders_per_day=10, end_date=self.end, seed=1,
        )
        assert orders, "expected at least one order"
        oldest = self.end - timedelta(days=7)
        for o in orders:
            assert oldest <= o.timestamp <= self.end + timedelta(hours=24)

    def test_deterministic_with_same_seed(self):
        a = generate_orders(menu=self.menu, customers=self.customers,
                            days=5, orders_per_day=8, end_date=self.end, seed=99)
        b = generate_orders(menu=self.menu, customers=self.customers,
                            days=5, orders_per_day=8, end_date=self.end, seed=99)
        assert len(a) == len(b)
        assert [o.order_id for o in a] == [o.order_id for o in b]

    def test_different_seeds_produce_different_orders(self):
        a = generate_orders(menu=self.menu, customers=self.customers,
                            days=5, orders_per_day=8, end_date=self.end, seed=1)
        b = generate_orders(menu=self.menu, customers=self.customers,
                            days=5, orders_per_day=8, end_date=self.end, seed=2)
        assert [o.order_id for o in a] != [o.order_id for o in b]

    def test_status_distribution_roughly_matches_weights(self):
        orders = generate_orders(
            menu=self.menu, customers=self.customers,
            days=30, orders_per_day=50, end_date=self.end, seed=7,
        )
        completed = sum(1 for o in orders if o.status == "completed")
        ratio = completed / len(orders)
        # weight is 0.85 — allow ±0.10 tolerance
        assert 0.75 <= ratio <= 0.95

    def test_all_statuses_in_allowed_set(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=30, orders_per_day=20, end_date=self.end, seed=7)
        allowed = set(ORDER_STATUS_WEIGHTS.keys())
        assert {o.status for o in orders}.issubset(allowed)

    def test_items_reference_real_menu_ids(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=10, orders_per_day=10, end_date=self.end, seed=3)
        valid_ids = {m["menu_item_id"] for m in self.menu}
        for o in orders:
            assert o.items, "order must have items"
            for it in o.items:
                assert it["menu_item_id"] in valid_ids
                assert it["quantity"] >= 1
                assert it["price"] > 0

    def test_totals_match_items_plus_tax(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=3, orders_per_day=20, end_date=self.end, seed=4)
        for o in orders:
            subtotal = sum(it["price"] * it["quantity"] for it in o.items)
            expected_tax = round(subtotal * TAX_RATE, 2)
            expected_total = round(subtotal + expected_tax, 2)
            assert o.tax_amount == pytest.approx(expected_tax, abs=0.01)
            assert o.total_amount == pytest.approx(expected_total, abs=0.01)

    def test_sorted_by_timestamp_ascending(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=10, orders_per_day=15, end_date=self.end, seed=5)
        timestamps = [o.timestamp for o in orders]
        assert timestamps == sorted(timestamps)

    def test_some_orders_have_customer_some_dont(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=15, orders_per_day=20, end_date=self.end, seed=6,
                                 customer_attach_rate=0.30)
        with_customer = sum(1 for o in orders if o.customer_id is not None)
        without = len(orders) - with_customer
        assert with_customer > 0
        assert without > 0
        # attach rate is 0.30
        ratio = with_customer / len(orders)
        assert 0.20 <= ratio <= 0.40

    def test_default_customer_attach_rate_is_one(self):
        orders = generate_orders(
            menu=self.menu, customers=self.customers,
            days=5, orders_per_day=10, end_date=self.end, seed=8,
        )
        assert all(o.customer_id is not None for o in orders)

    def test_customer_attach_rate_zero_means_no_customers(self):
        orders = generate_orders(
            menu=self.menu, customers=self.customers,
            days=5, orders_per_day=10, end_date=self.end, seed=8,
            customer_attach_rate=0.0,
        )
        assert all(o.customer_id is None for o in orders)

    def test_lunch_and_dinner_peaks(self):
        """Hours 11–13 + 17–20 should hold the majority of orders."""
        orders = generate_orders(
            menu=self.menu, customers=self.customers,
            days=30, orders_per_day=40, end_date=self.end, seed=9,
        )
        peak_hours = {11, 12, 13, 17, 18, 19, 20}
        peak = sum(1 for o in orders if o.timestamp.hour in peak_hours)
        assert peak / len(orders) > 0.5

    def test_unique_order_ids(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=20, orders_per_day=30, end_date=self.end, seed=10)
        ids = [o.order_id for o in orders]
        assert len(ids) == len(set(ids))

    def test_no_duplicate_items_within_an_order(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=5, orders_per_day=20, end_date=self.end, seed=11)
        for o in orders:
            ids = [it["menu_item_id"] for it in o.items]
            assert len(ids) == len(set(ids))

    def test_returns_typed_objects(self):
        orders = generate_orders(menu=self.menu, customers=self.customers,
                                 days=2, orders_per_day=5, end_date=self.end, seed=12)
        assert all(isinstance(o, GeneratedOrder) for o in orders)

    def test_invalid_args_raise(self):
        with pytest.raises(ValueError):
            generate_orders(menu=[], customers=self.customers, days=1, orders_per_day=1, seed=1)
        with pytest.raises(ValueError):
            generate_orders(menu=self.menu, customers=self.customers, days=0, orders_per_day=1, seed=1)
        with pytest.raises(ValueError):
            generate_orders(menu=self.menu, customers=self.customers, days=1, orders_per_day=0, seed=1)
