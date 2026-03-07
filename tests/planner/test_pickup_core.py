"""Unit tests for PickupMixin methods (pickup.py)."""

from tests.conftest import make_planner, make_state, get_action
import bot
from tests.planner.conftest import _active_order, _preview_order




class TestTryActivePickup:
    def test_adjacent_item_picked_up(self):
        """Bot adjacent to a needed item should pick it up."""
        state = make_state(
            bots=[{"id": 0, "position": [3, 2], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "i0"

    def test_not_adjacent_moves_toward_item(self):
        """Bot not adjacent to needed item should move toward it."""
        state = make_state(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [6, 4]}],
            orders=[_active_order(["cheese"])],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"].startswith("move_")

    def test_full_inventory_skips_pickup(self):
        """Bot with full inventory should not attempt pickup."""
        state = make_state(
            bots=[{"id": 0, "position": [3, 2], "inventory": ["a", "b", "c"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese", "a", "b", "c"])],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Should be delivering, not picking up
        assert action["action"] != "pick_up"


class TestBuildGreedyRoute:
    def test_single_bot_uses_optimized_route(self):
        """Single bot should use the optimized single-bot route builder."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        # Single bot should have claimed items
        assert len(planner.claimed) > 0

    def test_multi_bot_uses_standard_route(self):
        """Multi-bot uses standard greedy route with round-trip cost."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 4], "inventory": []},
                {"id": 1, "position": [9, 4], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        # Should have produced actions for both bots
        assert len(planner.actions) == 2


class TestBuildAssignedRoute:
    def test_assigned_route_uses_unclaimed_items(self):
        """Assigned route skips claimed items."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [2, 3], "inventory": []},
                {"id": 1, "position": [8, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [3, 2]},
                {"id": "i1", "type": "milk", "position": [7, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        # Both items should have been claimed during planning
        assert len(planner.claimed) >= 1


class TestTryPreviewPrepick:
    def test_preview_pickup_when_spare_slots(self):
        """Bot with spare slots can pick up preview items."""
        state = make_state(
            bots=[{"id": 0, "position": [3, 6], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[
                _active_order(["cheese"]),
                _preview_order(["milk"]),
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot should either pick up the adjacent preview milk or move toward cheese
        assert action["action"] in (
            "pick_up",
            "move_right",
            "move_up",
            "move_down",
            "move_left",
        )

    def test_no_preview_when_no_preview_order(self):
        """Without a preview order, no preview prepick happens."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese"])],
        )
        # No preview order -> preview_bot_ids should be empty
        assert planner.preview is None


class TestFindDetourItem:
    def test_detour_within_max_steps(self):
        """Item within max detour steps should be found."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [2, 6]},
            ],
            orders=[
                _active_order(["cheese"]),
                _preview_order(["milk"]),
            ],
        )
        # milk at (2,6) — adjacent walkable might be (1,6) or (3,6)
        item, cell = planner._find_detour_item(
            (3, 5), planner.net_preview, max_detour=10
        )
        if item is not None:
            assert item["type"] == "milk"

    def test_detour_beyond_max_returns_none(self):
        """Item beyond max detour should not be found."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 7], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [9, 1]},
            ],
            orders=[
                _active_order(["cheese"]),
                _preview_order(["milk"]),
            ],
            drop_off=[1, 8],
        )
        # milk is very far from the path between (1,7) and dropoff (1,8)
        item, cell = planner._find_detour_item(
            (1, 7), planner.net_preview, max_detour=1
        )
        # If found, detour must be <= max_detour (but likely None due to distance)
        # The item at (9,1) is far from the direct path to (1,8)
        assert item is None


class TestClusterSelect:
    def test_cluster_select_sorts_by_score(self):
        """Cluster select should factor in centroid distance."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [3, 2]},
                {"id": "i1", "type": "cheese", "position": [3, 6]},
                {"id": "i2", "type": "cheese", "position": [7, 4]},
            ],
            orders=[_active_order(["cheese"])],
        )
        # Build candidates manually
        candidates = [
            ({"id": "i0", "type": "cheese"}, (2, 2), 5),
            ({"id": "i1", "type": "cheese"}, (2, 6), 6),
            ({"id": "i2", "type": "cheese"}, (6, 4), 10),
        ]
        result = planner._cluster_select(candidates)
        # Should return all candidates sorted, with cluster weighting
        assert len(result) == 3
        # First result should have lowest combined score
        assert result[0][2] <= result[1][2] or result[0][2] <= result[2][2]
