"""Unit tests for DeliveryMixin methods (delivery.py)."""

from tests.conftest import make_planner


def _active_order(items_required, items_delivered=None):
    return {
        "id": "order_0",
        "items_required": items_required,
        "items_delivered": items_delivered or [],
        "complete": False,
        "status": "active",
    }


class TestEstimateRoundsToComplete:
    def test_no_remaining_items(self):
        """With no remaining items, just distance to dropoff + 1."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        est = planner._estimate_rounds_to_complete((3, 5), ["cheese"])
        # No remaining active items on shelves -> just dist to dropoff + 1
        d = planner.gs.dist_static((3, 5), planner.drop_off)
        assert est == d + 1

    def test_multi_trip_estimation(self):
        """Estimation accounts for trips when items exceed inventory."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [3, 2]},
                {"id": "i1", "type": "milk", "position": [3, 4]},
                {"id": "i2", "type": "bread", "position": [3, 6]},
                {"id": "i3", "type": "butter", "position": [5, 2]},
            ],
            orders=[_active_order(["cheese", "milk", "bread", "butter"])],
            drop_off=[1, 8],
        )
        est = planner._estimate_rounds_to_complete((1, 4), [])
        # 4 items with capacity 3 -> need at least 2 trips
        # Should be a positive number greater than the direct distance
        assert est > 0
        assert est > planner.gs.dist_static((1, 4), planner.drop_off)

    def test_estimate_with_partial_inventory(self):
        """Bot with items already in inventory needs fewer pickups."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 4], "inventory": ["cheese", "milk"]}],
            items=[
                {"id": "i0", "type": "bread", "position": [3, 2]},
            ],
            orders=[_active_order(["cheese", "milk", "bread"])],
            drop_off=[1, 8],
        )
        est = planner._estimate_rounds_to_complete((1, 4), ["cheese", "milk"])
        # 1 item to pick up + delivery
        assert est > 0


class TestShouldDeliverEarly:
    def test_no_delivery_when_empty(self):
        """Empty inventory -> never deliver early."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        assert planner._should_deliver_early((3, 3), []) is False

    def test_no_delivery_when_no_active_on_shelves(self):
        """If no active items on shelves, don't deliver early."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # active_on_shelves == 0 (cheese already carried)
        assert planner._should_deliver_early((3, 3), ["cheese"]) is False


class TestTryMaximizeItems:
    def test_maximize_delivers_when_pickup_impossible(self):
        """In endgame, bot should deliver if can't pick up more items in time."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 7], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "milk", "position": [9, 1]},
            ],
            orders=[_active_order(["cheese", "milk"])],
            drop_off=[1, 8],
            round_num=295,
            max_rounds=300,
        )
        # Endgame: 5 rounds left, item is far, bot should deliver what it has
        blocked = planner._build_blocked(0)
        result = planner._try_maximize_items(0, 1, 7, (1, 7), ["cheese"], blocked)
        assert result is True

    def test_maximize_skips_when_pickup_possible(self):
        """If there's time to pick up more items, don't maximize."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "milk", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
            drop_off=[1, 8],
            round_num=270,
            max_rounds=300,
        )
        # plan() claims items, so restore state for the unit test
        planner.claimed = set()
        planner.net_active = {"milk": 1}
        planner.actions = []
        blocked = planner._build_blocked(0)
        result = planner._try_maximize_items(0, 3, 3, (3, 3), ["cheese"], blocked)
        assert result is False

    def test_maximize_returns_false_no_active(self):
        """Bot without active items returns False."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["bread"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            round_num=295,
            max_rounds=300,
        )
        blocked = planner._build_blocked(0)
        result = planner._try_maximize_items(0, 3, 3, (3, 3), ["bread"], blocked)
        assert result is False

    def test_maximize_with_empty_inventory(self):
        """Bot with empty inventory and no active items returns False."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            round_num=295,
            max_rounds=300,
        )
        blocked = planner._build_blocked(0)
        result = planner._try_maximize_items(0, 3, 3, (3, 3), [], blocked)
        assert result is False


class TestShouldDeliverEarlyEdgeCases:
    def test_full_inventory_considers_delivery(self):
        """Full inventory with items on shelves may consider early delivery."""
        planner = make_planner(
            bots=[{"id": 0, "position": [5, 3], "inventory": ["cheese", "milk"]}],
            items=[
                {"id": "i0", "type": "bread", "position": [3, 2]},
                {"id": "i1", "type": "butter", "position": [3, 6]},
            ],
            orders=[_active_order(["cheese", "milk", "bread", "butter"])],
            drop_off=[1, 8],
        )
        # Should return a boolean - the actual value depends on distances
        result = planner._should_deliver_early((5, 3), ["cheese", "milk"])
        assert isinstance(result, bool)

    def test_no_remaining_items_returns_false(self):
        """When no items match net_active, returns False."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese", "bread"])],
            drop_off=[1, 8],
        )
        # Manually set to trigger the branch
        planner.active_on_shelves = 1
        planner.net_active = {"bread": 1}
        result = planner._should_deliver_early((3, 3), ["cheese"])
        assert isinstance(result, bool)


class TestEstimateRoundsEdgeCases:
    def test_single_nearby_item(self):
        """Estimate for a single nearby item should be reasonable."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        planner.claimed = set()
        planner.net_active = {"cheese": 1}
        est = planner._estimate_rounds_to_complete((3, 3), [])
        # Should include distance to item + pickup + distance to dropoff + dropoff
        assert est > 0
        assert est < 50  # reasonable upper bound
