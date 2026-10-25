"""Unit tests for src/fabric/seed_demo_data.py CLI."""

from unittest.mock import MagicMock, patch

import pytest

from src.fabric import seed_demo_data


class TestDryRun:
    def test_dry_run_does_not_touch_db(self, capsys, monkeypatch):
        monkeypatch.delenv("FABRIC_CONNECTION_STRING", raising=False)
        with patch("src.fabric.seed_demo_data.FabricDBClient") as mock_db:
            rc = seed_demo_data.main(["--dry-run", "--days", "3", "--orders-per-day", "5"])
        assert rc == 0
        mock_db.assert_not_called()
        out = capsys.readouterr().out
        assert "Generated demo data" in out
        assert "[--dry-run]" in out


class TestMissingConnectionString:
    def test_returns_error_code(self, monkeypatch, capsys):
        monkeypatch.delenv("FABRIC_CONNECTION_STRING", raising=False)
        rc = seed_demo_data.main(["--days", "1", "--orders-per-day", "1", "--yes"])
        assert rc == 2
        err = capsys.readouterr().err
        assert "FABRIC_CONNECTION_STRING" in err


class TestSeedingFlow:
    @pytest.fixture
    def fake_db(self, monkeypatch):
        monkeypatch.setenv("FABRIC_CONNECTION_STRING", "Driver=...")
        mock_db = MagicMock()
        with patch("src.fabric.seed_demo_data.FabricDBClient", return_value=mock_db):
            yield mock_db

    def test_seeds_menu_customers_and_orders(self, fake_db):
        rc = seed_demo_data.main(["--days", "2", "--orders-per-day", "3", "--yes"])
        assert rc == 0
        fake_db.upsert_menu.assert_called_once()
        fake_db.upsert_customers.assert_called_once()
        fake_db.insert_orders_bulk.assert_called_once()
        # No reset by default
        fake_db.reset_orders.assert_not_called()

        # Each call received non-empty data
        assert len(fake_db.upsert_menu.call_args.args[0]) > 0
        assert len(fake_db.upsert_customers.call_args.args[0]) > 0
        assert len(fake_db.insert_orders_bulk.call_args.args[0]) > 0

    def test_reset_calls_reset_orders_first(self, fake_db):
        rc = seed_demo_data.main(["--reset", "--yes", "--days", "2", "--orders-per-day", "3"])
        assert rc == 0
        fake_db.reset_orders.assert_called_once()

    def test_reset_without_yes_prompts(self, fake_db, monkeypatch):
        with patch("builtins.input", return_value="n"):
            rc = seed_demo_data.main(["--reset", "--days", "1", "--orders-per-day", "1"])
        assert rc == 1
        fake_db.reset_orders.assert_not_called()

    def test_reset_confirmed_via_prompt(self, fake_db):
        with patch("builtins.input", return_value="y"):
            rc = seed_demo_data.main(["--reset", "--days", "1", "--orders-per-day", "1"])
        assert rc == 0
        fake_db.reset_orders.assert_called_once()

    def test_seed_arg_makes_run_reproducible(self, fake_db):
        seed_demo_data.main(["--days", "2", "--orders-per-day", "5", "--seed", "123", "--yes"])
        first_call = fake_db.insert_orders_bulk.call_args.args[0]
        first_ids = [o.order_id for o in first_call]

        fake_db.reset_mock()
        seed_demo_data.main(["--days", "2", "--orders-per-day", "5", "--seed", "123", "--yes"])
        second_call = fake_db.insert_orders_bulk.call_args.args[0]
        second_ids = [o.order_id for o in second_call]

        assert first_ids == second_ids
