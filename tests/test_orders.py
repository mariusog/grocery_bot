"""Unit tests for grocery_bot.orders module."""

from grocery_bot.orders import get_needed_items


class TestGetNeededItems:
    def test_all_delivered(self):
        order = {
            "items_required": ["milk", "bread"],
            "items_delivered": ["milk", "bread"],
        }
        assert get_needed_items(order) == {}

    def test_none_delivered(self):
        order = {"items_required": ["milk", "bread"], "items_delivered": []}
        assert get_needed_items(order) == {"milk": 1, "bread": 1}

    def test_partial_delivery(self):
        order = {
            "items_required": ["milk", "milk", "bread"],
            "items_delivered": ["milk"],
        }
        assert get_needed_items(order) == {"milk": 1, "bread": 1}

    def test_duplicate_items(self):
        order = {
            "items_required": ["cheese", "cheese", "cheese"],
            "items_delivered": ["cheese"],
        }
        assert get_needed_items(order) == {"cheese": 2}

    def test_empty_order(self):
        order = {"items_required": [], "items_delivered": []}
        assert get_needed_items(order) == {}

    def test_single_item_needed(self):
        order = {"items_required": ["butter"], "items_delivered": []}
        assert get_needed_items(order) == {"butter": 1}

    def test_over_delivered_excluded(self):
        """If somehow more delivered than required, the type should not appear."""
        order = {"items_required": ["milk"], "items_delivered": ["milk", "milk"]}
        assert get_needed_items(order) == {}

    def test_mixed_types(self):
        order = {
            "items_required": ["a", "b", "c", "a", "b"],
            "items_delivered": ["a", "b"],
        }
        result = get_needed_items(order)
        assert result == {"a": 1, "b": 1, "c": 1}
