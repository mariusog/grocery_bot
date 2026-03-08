"""Test _spare_slots gating that controls preview picking."""

from tests.conftest import make_state
from grocery_bot.planner.round_planner import RoundPlanner
from grocery_bot.constants import MAX_INVENTORY
import bot


def _order(items):
    return {"id": "o0", "items_required": items, "items_delivered": [], "complete": False, "status": "active"}


def _planner(bots, items, orders, **kw):
    state = make_state(bots=bots, items=items, orders=orders, **kw)
    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    p = RoundPlanner(gs, state, full_state=state)
    p._detect_pickup_failures()
    p.active = next((o for o in p.orders if o.get("status") == "active" and not o["complete"]), None)
    p.preview = None
    if p.active:
        p._check_order_transition()
        p._compute_needs()
    return p


class TestSpareSlotsMath:
    def test_empty_inv_2_active(self):
        """spare = 3 - 0 - 2 = 1"""
        p = _planner(
            [{"id": 0, "position": [3, 3], "inventory": []}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]},
             {"id": "i1", "type": "milk", "position": [6, 2]}],
            [_order(["cheese", "milk"])],
        )
        assert p._spare_slots([]) == MAX_INVENTORY - p.active_on_shelves

    def test_negative_blocks_preview(self):
        """4 active items, empty inv -> spare = 3-0-4 = -1"""
        p = _planner(
            [{"id": 0, "position": [3, 3], "inventory": []}],
            [{"id": f"i{i}", "type": f"t{i}", "position": [4 + i, 2]} for i in range(4)],
            [_order([f"t{i}" for i in range(4)])],
        )
        assert p._spare_slots([]) < 0

    def test_carrying_active_increases_spare(self):
        """Carrying 1 active item: active_on_shelves drops, spare goes up."""
        p = _planner(
            [{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            [{"id": "i0", "type": "milk", "position": [4, 2]}],
            [_order(["cheese", "milk"])],
        )
        assert p.active_on_shelves == 1
        assert p._spare_slots(["cheese"]) == 1  # 3 - 1 - 1

    def test_unassigned_bot_gets_spare_on_small_team(self):
        """T43: Unassigned bot on 3-bot team should have spare slots."""
        p = _planner(
            [
                {"id": 0, "position": [5, 4], "inventory": ["bread"]},
                {"id": 1, "position": [3, 3], "inventory": []},
                {"id": 2, "position": [7, 3], "inventory": []},
            ],
            [
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [6, 2]},
            ],
            [_order(["cheese", "milk"])],
        )
        p._compute_bot_assignments()
        # Bot 0 has "bread" (non-active) and no active items assigned
        # Other bots handle cheese and milk
        # Bot 0 should still be able to preview-pick (spare > 0)
        spare = p._spare_slots(["bread"], bid=0)
        assert spare > 0, (
            f"Unassigned bot spare={spare}, expected > 0. "
            f"active_on_shelves={p.active_on_shelves}, "
            f"assignments={p.bot_assignments}"
        )

    def test_assigned_bot_reserves_slots_on_small_team(self):
        """Assigned bot on 3-bot team should reserve slots for active items."""
        p = _planner(
            [
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
                {"id": 2, "position": [9, 4], "inventory": []},
            ],
            [
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [6, 2]},
            ],
            [_order(["cheese", "milk"])],
        )
        p._compute_bot_assignments()
        # Bot 0 is closest to cheese, should have assignment
        # With assignment, reserve should limit spare slots
        spare_with_bid = p._spare_slots([], bid=0)
        spare_without_bid = p._spare_slots([])
        assert spare_with_bid <= spare_without_bid + 1

    def test_full_inv_always_zero_or_negative(self):
        p = _planner(
            [{"id": 0, "position": [3, 3], "inventory": ["a", "b", "c"]}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese", "a", "b", "c"])],
        )
        assert p._spare_slots(["a", "b", "c"]) <= 0
