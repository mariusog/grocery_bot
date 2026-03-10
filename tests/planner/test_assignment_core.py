"""Unit tests for AssignmentMixin methods (assignment.py)."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order, _preview_order


class TestIsDelivering:
    def test_full_inventory_with_active_items(self):
        """Bot with full inventory and active items is delivering."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": ["cheese", "milk", "bread"]}
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "milk", "bread"])],
        )
        b = planner.bots_by_id[0]
        assert planner._is_delivering(b) is True

    def test_at_dropoff_with_active_items(self):
        """Bot at dropoff with active items is delivering."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "cheese"])],
        )
        b = planner.bots_by_id[0]
        assert planner._is_delivering(b) is True

    def test_no_active_items_not_delivering(self):
        """Bot without active items is not delivering."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["milk"]}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese"])],
        )
        b = planner.bots_by_id[0]
        assert planner._is_delivering(b) is False

    def test_active_items_but_more_on_shelves(self):
        """Bot with active items but not full and items still on shelves -> not delivering."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 4]},
            ],
            orders=[_active_order(["cheese", "milk", "cheese"])],
        )
        b = planner.bots_by_id[0]
        # Has active item, not full, items still on shelves, not at dropoff
        assert planner._is_delivering(b) is False

    def test_all_active_picked_up_delivering(self):
        """When active_on_shelves == 0 and bot has active items, it's delivering."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "bread", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese"])],
        )
        b = planner.bots_by_id[0]
        assert planner._is_delivering(b) is True


class TestBotUrgency:
    def test_urgency_full_inventory_active_gets_0(self):
        """Full inventory with active items -> urgency 0 (highest)."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": ["cheese", "milk", "bread"]}
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese", "milk", "bread"])],
        )
        assert planner._bot_urgency(planner.bots_by_id[0]) == 0

    def test_urgency_no_shelves_active_gets_1(self):
        """Active items carried but none on shelves -> urgency 1."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        assert planner._bot_urgency(planner.bots_by_id[0]) == 1

    def test_urgency_active_items_on_shelves_gets_2(self):
        """Active items carried and more on shelves -> urgency 2."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 4]},
            ],
            orders=[_active_order(["cheese", "cheese", "milk"])],
        )
        assert planner._bot_urgency(planner.bots_by_id[0]) == 2

    def test_urgency_empty_inventory_gets_3(self):
        """No active items, empty inventory -> urgency 3."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        assert planner._bot_urgency(planner.bots_by_id[0]) == 3

    def test_urgency_non_active_inventory_gets_4(self):
        """Non-active items in inventory -> urgency 4 (lowest)."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["bread"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        assert planner._bot_urgency(planner.bots_by_id[0]) == 4


class TestAssignPreviewBot:
    def test_no_preview_bot_for_single_bot(self):
        """Single bot teams should never assign a preview bot."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[
                _active_order(["cheese"]),
                _preview_order(["milk"]),
            ],
        )
        assert len(planner.preview_bot_ids) == 0

    def test_preview_bot_assigned_with_surplus(self):
        """With 3 bots and 1 active item, surplus bots become preview bots."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
                {"id": 2, "position": [7, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[
                _active_order(["cheese"]),
                _preview_order(["milk"]),
            ],
        )
        # With 3 bots and 1 active item, there's surplus
        # Preview bots should be assigned (the furthest from active items)
        assert len(planner.preview_bot_ids) >= 1


class TestComputeBotAssignments:
    def test_no_assignments_for_single_bot(self):
        """Single bot doesn't get pre-assignments."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 4]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        assert planner.bot_assignments == {}

    def test_assignments_for_two_bots(self):
        """Two bots with items should get assignments."""
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
        # Both bots should have assignments
        assert len(planner.bot_assignments) >= 1


class TestBotDeliveryCompletesOrder:
    def test_completes_when_bot_has_all_remaining(self):
        """Bot carrying all remaining needed items completes the order."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese", "milk"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese", "milk"], items_delivered=[])],
        )
        b = planner.bots_by_id[0]
        assert planner._bot_delivery_completes_order(b) is True

    def test_does_not_complete_when_items_missing(self):
        """Bot missing some required items does not complete the order."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "milk", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        b = planner.bots_by_id[0]
        assert planner._bot_delivery_completes_order(b) is False
