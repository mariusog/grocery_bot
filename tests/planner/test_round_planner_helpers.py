"""Unit tests for RoundPlanner core helper methods."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


class TestIsAvailable:
    def test_available_item(self):
        """Unclaimed, non-blacklisted item is available."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.claimed = set()
        item = {"id": "i0", "type": "cheese"}
        assert planner._is_available(item) is True

    def test_claimed_item_not_available(self):
        """Claimed item is not available."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.claimed = {"i0"}
        item = {"id": "i0", "type": "cheese"}
        assert planner._is_available(item) is False

    def test_blacklisted_item_not_available(self):
        """Blacklisted item is not available."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.blacklisted_items.add("i0")
        planner.claimed = set()
        item = {"id": "i0", "type": "cheese"}
        assert planner._is_available(item) is False


class TestIterNeededItems:
    def test_yields_needed_items(self):
        """Should yield available items matching needed dict."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        planner.claimed = set()
        needed = {"cheese": 1, "milk": 1}
        items = list(planner._iter_needed_items(needed))
        types_yielded = {it["type"] for it, _ in items}
        assert "cheese" in types_yielded
        assert "milk" in types_yielded

    def test_skips_zero_count(self):
        """Should not yield items with count <= 0."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.claimed = set()
        needed = {"cheese": 0}
        items = list(planner._iter_needed_items(needed))
        assert len(items) == 0


class TestFindAdjacentNeeded:
    def test_finds_adjacent_item(self):
        """Should find a needed item adjacent to the bot."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 2], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.claimed = set()
        needed = {"cheese": 1}
        result = planner._find_adjacent_needed(3, 2, needed)
        assert result is not None
        assert result["type"] == "cheese"

    def test_returns_none_when_not_adjacent(self):
        """Should return None when no needed items are adjacent."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [6, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.claimed = set()
        needed = {"cheese": 1}
        result = planner._find_adjacent_needed(1, 4, needed)
        assert result is None


class TestSpareSlots:
    def test_spare_slots_empty_inventory(self):
        """Empty inventory with items on shelves."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # MAX_INVENTORY=3, inv=0, active_on_shelves=1 -> spare = 3 - 0 - 1 = 2
        result = planner._spare_slots([])
        assert result == 2

    def test_spare_slots_full_inventory(self):
        """Full inventory always returns negative or zero."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["a", "b", "c"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese", "a", "b", "c"])],
        )
        result = planner._spare_slots(["a", "b", "c"])
        assert result <= 0


class TestClaim:
    def test_claim_adds_to_claimed(self):
        """Claiming an item adds its ID to the claimed set."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.claimed = set()
        needed = {"cheese": 2}
        item = {"id": "i0", "type": "cheese"}
        planner._claim(item, needed)
        assert "i0" in planner.claimed
        assert needed["cheese"] == 1

    def test_claim_decrements_needed(self):
        """Claiming should decrement the needed count."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        needed = {"cheese": 1}
        item = {"id": "i0", "type": "cheese"}
        planner._claim(item, needed)
        assert needed["cheese"] == 0


class TestPickup:
    def test_pickup_returns_correct_action(self):
        """_pickup should return a pick_up action dict."""
        from grocery_bot.planner.round_planner import RoundPlanner

        action = RoundPlanner._pickup(0, {"id": "i0", "type": "cheese"})
        assert action == {"bot": 0, "action": "pick_up", "item_id": "i0"}
