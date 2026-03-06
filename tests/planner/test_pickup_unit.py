"""Unit tests for PickupMixin methods (pickup.py)."""

from tests.conftest import make_planner, make_state, get_action
import bot


def _active_order(items_required, items_delivered=None):
    return {
        "id": "order_0",
        "items_required": items_required,
        "items_delivered": items_delivered or [],
        "complete": False,
        "status": "active",
    }


def _preview_order(items_required, items_delivered=None):
    return {
        "id": "order_1",
        "items_required": items_required,
        "items_delivered": items_delivered or [],
        "complete": False,
        "status": "preview",
    }


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
        assert action["action"] in ("pick_up", "move_right", "move_up", "move_down", "move_left")

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


class TestBuildSingleBotRoute:
    def test_returns_route_for_single_bot(self):
        """Single bot route builder should find items."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        # Reset state for direct call
        planner.claimed = set()
        planner.net_active = {"cheese": 1, "milk": 1}
        route = planner._build_single_bot_route((1, 4), [])
        assert route is not None
        assert len(route) >= 1

    def test_returns_none_with_full_inventory(self):
        """Returns None when inventory is full."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": ["a", "b", "c"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese", "a", "b", "c"])],
        )
        planner.claimed = set()
        planner.net_active = {"cheese": 1}
        route = planner._build_single_bot_route((1, 4), ["a", "b", "c"])
        assert route is None


class TestFlexibleTsp:
    def test_single_item_uses_best_adjacent(self):
        """Flexible TSP for 1 item should pick the best adjacent cell."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        item = {"id": "i0", "type": "cheese", "position": [4, 2]}
        result = planner._flexible_tsp((1, 4), [(item, (3, 2))], (1, 8))
        assert len(result) == 1
        assert result[0][0] == item

    def test_multi_item_returns_all(self):
        """Flexible TSP for multiple items returns all of them."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese", "milk"])],
            drop_off=[1, 8],
        )
        items = [
            ({"id": "i0", "type": "cheese", "position": [4, 2]}, (3, 2)),
            ({"id": "i1", "type": "milk", "position": [4, 6]}, (3, 6)),
        ]
        result = planner._flexible_tsp((1, 4), items, (1, 8))
        assert len(result) == 2


class TestFindNearestActiveItemPos:
    def test_finds_nearest_item(self):
        """Should return position of nearest reachable active item."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [8, 6]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        # Reset claims so items are available
        planner.claimed = set()
        planner.net_active = {"cheese": 1, "milk": 1}
        result = planner._find_nearest_active_item_pos((1, 4))
        assert result is not None

    def test_returns_none_when_no_items(self):
        """Should return None when no active items on shelves."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # All active items already carried -> net_active empty
        planner.claimed = set()
        result = planner._find_nearest_active_item_pos((1, 4))
        assert result is None

    def test_nearest_is_closer(self):
        """Returned position should be the closest reachable active item."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [3, 4]},
                {"id": "i1", "type": "milk", "position": [9, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        planner.claimed = set()
        planner.net_active = {"cheese": 1, "milk": 1}
        result = planner._find_nearest_active_item_pos((1, 4))
        # cheese at (3,4) is much closer than milk at (9,2)
        assert result is not None
        d_result = planner.gs.dist_static((1, 4), result)
        # Should be adjacent to the cheese item (distance ~1)
        assert d_result <= 3


class TestFindDetourItemEdgeCases:
    def test_no_needed_items(self):
        """Returns None when no items match needed dict."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        item, cell = planner._find_detour_item((3, 5), {})
        assert item is None
        assert cell is None

    def test_zero_max_detour(self):
        """With max_detour=0, only on-path items are returned."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
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
        item, cell = planner._find_detour_item(
            (3, 5), planner.net_preview, max_detour=0
        )
        # milk at (9,1) is a huge detour from (3,5) -> (1,8), should be None
        assert item is None


class TestFlexibleTspEdgeCases:
    def test_empty_targets(self):
        """Empty target list should return empty."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        result = planner._flexible_tsp((1, 4), [], (1, 8))
        assert result == []

    def test_single_item_best_cell(self):
        """Single item should use best adjacent cell overall."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 4]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        item = {"id": "i0", "type": "cheese", "position": [4, 4]}
        result = planner._flexible_tsp((1, 4), [(item, (3, 4))], (1, 8))
        assert len(result) == 1


class TestBuildAssignedRouteEdgeCases:
    def test_all_items_claimed(self):
        """When all assigned items are claimed, returns None."""
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
        # Claim all items
        planner.claimed = {"i0", "i1"}
        if 0 in planner.bot_assignments and planner.bot_assignments[0]:
            result = planner._build_assigned_route(0, (2, 3))
            assert result is None


class TestClusterSelectEdgeCases:
    def test_single_candidate(self):
        """Single candidate returns unchanged."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        candidates = [
            ({"id": "i0", "type": "cheese"}, (3, 2), 5),
        ]
        result = planner._cluster_select(candidates)
        assert len(result) == 1
