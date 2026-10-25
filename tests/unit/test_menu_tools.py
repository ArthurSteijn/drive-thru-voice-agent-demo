"""Unit tests for menu_tools executor."""

import json
import pytest

from src.agent_tools.menu_tools import execute_get_menu_items
from tests.conftest import SAMPLE_MENU


class TestExecuteGetMenuItems:
    def test_returns_all_items_when_no_category(self, mock_db):
        result = json.loads(execute_get_menu_items({}, db=mock_db))

        assert result["success"] is True
        assert result["count"] == len(SAMPLE_MENU)
        assert result["items"] == SAMPLE_MENU
        mock_db.get_menu.assert_called_once_with(category=None)

    def test_filters_by_category(self, mock_db):
        mock_db.get_menu.return_value = [SAMPLE_MENU[0]]  # only burgers

        result = json.loads(execute_get_menu_items({"category": "burgers"}, db=mock_db))

        assert result["success"] is True
        assert result["count"] == 1
        mock_db.get_menu.assert_called_once_with(category="burgers")

    def test_returns_empty_list_when_no_matches(self, mock_db):
        mock_db.get_menu.return_value = []

        result = json.loads(execute_get_menu_items({"category": "desserts"}, db=mock_db))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["items"] == []

    def test_handles_db_error_gracefully(self, mock_db):
        mock_db.get_menu.side_effect = Exception("DB connection failed")

        result = json.loads(execute_get_menu_items({}, db=mock_db))

        assert result["success"] is False
        assert "error" in result
        assert len(result["error"]) > 0
