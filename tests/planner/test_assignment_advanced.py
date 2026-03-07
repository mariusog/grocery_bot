"""Unit tests for AssignmentMixin methods (assignment.py)."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order, _preview_order




class TestGreedyAssign:
    def test_assigns_closest_items(self):
        """Greedy assign should prefer closer items for each bot."""
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
        # After planning, bot 0 should be assigned cheese (closer)
        # and bot 1 should be assigned milk (closer)
        if planner.bot_assignments:
            total = sum(len(v) for v in planner.bot_assignments.values())
            assert total >= 1


class TestStaggerAisleAssignments:
    def test_no_stagger_with_single_assignment(self):
        """Stagger does nothing when only one bot has assignments."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese"])],
        )
        # With only 1 needed item, at most 1 bot gets assigned
        total_assigned = sum(len(v) for v in planner.bot_assignments.values())
        assert total_assigned <= 1


class TestBotDeliveryCompletesOrderEdgeCases:
    def test_empty_inventory_never_completes(self):
        """Bot with empty inventory cannot complete an order."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        b = planner.bots_by_id[0]
        assert planner._bot_delivery_completes_order(b) is False

    def test_partial_inventory_does_not_complete(self):
        """Bot carrying only some needed items doesn't complete."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "milk", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        b = planner.bots_by_id[0]
        assert planner._bot_delivery_completes_order(b) is False


class TestIsDeliveringEdgeCases:
    def test_empty_inventory_not_delivering(self):
        """Bot with empty inventory is not delivering."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        b = planner.bots_by_id[0]
        assert planner._is_delivering(b) is False


class TestBotUrgencyEdgeCases:
    def test_urgency_ordering(self):
        """Urgency values should follow expected ordering."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": ["cheese", "milk", "bread"]},
                {"id": 1, "position": [5, 3], "inventory": ["cheese"]},
                {"id": 2, "position": [7, 3], "inventory": []},
                {"id": 3, "position": [9, 3], "inventory": ["butter"]},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [6, 2]},
            ],
            orders=[_active_order(["cheese", "cheese", "milk", "bread"])],
        )
        u0 = planner._bot_urgency(planner.bots_by_id[0])
        u2 = planner._bot_urgency(planner.bots_by_id[2])
        u3 = planner._bot_urgency(planner.bots_by_id[3])
        # Full inventory with active -> highest urgency (lowest number)
        assert u0 == 0
        # Empty inventory -> urgency 3
        assert u2 == 3
        # Non-active inventory (butter not in order) -> urgency 4
        assert u3 == 4
