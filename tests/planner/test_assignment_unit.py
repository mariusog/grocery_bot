"""Unit tests for AssignmentMixin and max_claim behavior."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


class TestMaxClaimBehavior:
    """Verify max_claim = ceil(active_on_shelves / idle_bots)."""

    def test_5bot_4items_max_claim_1(self):
        """5-bot team with 4 items -> ceil(4/5) = 1."""
        bots = [{"id": i, "position": [i + 1, 3], "inventory": []} for i in range(5)]
        items = [
            {"id": f"i{j}", "type": f"type_{j}", "position": [3 + j, 2]}
            for j in range(4)
        ]
        order_items = [f"type_{j}" for j in range(4)]
        planner = make_planner(
            bots=bots,
            items=items,
            orders=[_active_order(order_items)],
            drop_off=[1, 8],
        )
        assert planner.max_claim == 1

    def test_2bot_5items_max_claim_3(self):
        """2-bot team with 5 items -> ceil(5/2) = 3."""
        bots = [{"id": i, "position": [i + 1, 3], "inventory": []} for i in range(2)]
        items = [
            {"id": f"i{j}", "type": f"type_{j}", "position": [3 + j, 2]}
            for j in range(5)
        ]
        order_items = [f"type_{j}" for j in range(5)]
        planner = make_planner(
            bots=bots,
            items=items,
            orders=[_active_order(order_items)],
            drop_off=[1, 8],
        )
        assert planner.max_claim == 3


class TestTotalAssignments:
    """Verify all items get assigned when there are enough bots."""

    def test_total_assignments_preserved(self):
        """All items should be assigned with 10 bots and 5 items."""
        bots = [
            {"id": i, "position": [i + 1, 3], "inventory": []}
            for i in range(10)
        ]
        items = [
            {"id": f"i{j}", "type": f"t{j}", "position": [3 + j, 2]}
            for j in range(5)
        ]
        order_items = [f"t{j}" for j in range(5)]
        planner = make_planner(
            bots=bots,
            items=items,
            orders=[_active_order(order_items)],
            drop_off=[1, 8],
        )
        total_assigned = sum(
            len(items) for items in planner.bot_assignments.values()
        )
        assert total_assigned == 5
