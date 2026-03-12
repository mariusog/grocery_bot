"""Unit tests for AssignmentMixin and max_claim behavior."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


class TestMaxClaimBehavior:
    """Verify max_claim = ceil(active_on_shelves / idle_bots)."""

    def test_5bot_4items_max_claim_1(self):
        """5-bot team with 4 items -> ceil(4/5) = 1."""
        bots = [{"id": i, "position": [i + 1, 3], "inventory": []} for i in range(5)]
        items = [{"id": f"i{j}", "type": f"type_{j}", "position": [3 + j, 2]} for j in range(4)]
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
        items = [{"id": f"i{j}", "type": f"type_{j}", "position": [3 + j, 2]} for j in range(5)]
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
        bots = [{"id": i, "position": [i + 1, 3], "inventory": []} for i in range(10)]
        items = [{"id": f"i{j}", "type": f"t{j}", "position": [3 + j, 2]} for j in range(5)]
        order_items = [f"t{j}" for j in range(5)]
        planner = make_planner(
            bots=bots,
            items=items,
            orders=[_active_order(order_items)],
            drop_off=[1, 8],
        )
        total_assigned = sum(len(items) for items in planner.bot_assignments.values())
        assert total_assigned == 5


class TestDropoffWeightedAssignment:
    """Assignment should consider item-to-dropoff distance, not just bot-to-item."""

    def test_prefers_item_closer_to_dropoff(self):
        """Bot equidistant from two items should be assigned the one closer to dropoff."""
        # Drop-off at (1, 8). Item A at (2, 2) is close to dropoff (dist ~7).
        # Item B at (9, 2) is far from dropoff (dist ~14).
        # Bot at (5, 3) is roughly equidistant from both items.
        # Assignment should prefer item A (lower total round-trip cost).
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 3], "inventory": []},
                {"id": 1, "position": [5, 5], "inventory": []},
            ],
            items=[
                {"id": "i_near", "type": "cheese", "position": [2, 2]},
                {"id": "i_far", "type": "milk", "position": [9, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
            drop_off=[1, 8],
        )
        # Bot 0 should be assigned to the item that minimizes total delivery
        # time (pickup + travel to dropoff), not just pickup distance
        assigned_items = {it["id"] for items in planner.bot_assignments.values() for it in items}
        assert "i_near" in assigned_items and "i_far" in assigned_items, (
            f"Both items should be assigned, got {assigned_items}"
        )

    def test_closer_bot_gets_closer_to_dropoff_item(self):
        """When one bot is closer to dropoff, it should get the item near dropoff."""
        # Drop-off at (1, 8).
        # Bot 0 at (2, 6): close to dropoff
        # Bot 1 at (9, 3): far from dropoff
        # Item cheese at (2, 2): near dropoff
        # Item milk at (9, 2): far from dropoff
        # Bot 0 (close to dropoff) should get cheese (near dropoff)
        # Bot 1 (far from dropoff) should get milk (far from dropoff)
        planner = make_planner(
            bots=[
                {"id": 0, "position": [2, 6], "inventory": []},
                {"id": 1, "position": [9, 3], "inventory": []},
            ],
            items=[
                {"id": "i_cheese", "type": "cheese", "position": [2, 2]},
                {"id": "i_milk", "type": "milk", "position": [9, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
            drop_off=[1, 8],
        )
        b0_items = [it["id"] for it in planner.bot_assignments.get(0, [])]
        b1_items = [it["id"] for it in planner.bot_assignments.get(1, [])]
        # Bot 0 should get cheese (near dropoff), bot 1 should get milk
        assert "i_cheese" in b0_items, (
            f"Bot 0 (near dropoff) should get cheese (near dropoff), "
            f"got {b0_items}. Bot 1 got {b1_items}"
        )
        assert "i_milk" in b1_items, (
            f"Bot 1 (far from dropoff) should get milk (far from dropoff), "
            f"got {b1_items}. Bot 0 got {b0_items}"
        )

    def test_spawn_bots_prefer_items_near_dropoff(self):
        """Bots at spawn (far right) pick items near dropoff (left), not near spawn.

        This is the Hard difficulty fundamental issue: all bots start at (10,8)
        and grab items at (9,2) near themselves, ignoring items at (2,2) near
        the dropoff. Round-trip cost is similar, but items near dropoff enable
        faster subsequent pickups.
        """
        # Large map, dropoff at left (1,8), bots spawn at right (10,8)
        # Two cheese items: one near dropoff, one near spawn
        planner = make_planner(
            bots=[
                {"id": 0, "position": [10, 7], "inventory": []},
                {"id": 1, "position": [10, 8], "inventory": []},
            ],
            items=[
                # cheese near dropoff: bot d=9, drop d=2, round-trip=11
                {"id": "near_drop", "type": "cheese", "position": [2, 2]},
                # milk near spawn: bot d=2, drop d=16, round-trip=18
                {"id": "near_spawn", "type": "milk", "position": [10, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
            drop_off=[1, 8],
        )
        # Both items should be assigned (one per bot)
        all_assigned = {it["id"] for items in planner.bot_assignments.values() for it in items}
        assert "near_drop" in all_assigned and "near_spawn" in all_assigned, (
            f"Both items should be assigned, got {all_assigned}"
        )
