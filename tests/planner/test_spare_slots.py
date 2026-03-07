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

    def test_full_inv_always_zero_or_negative(self):
        p = _planner(
            [{"id": 0, "position": [3, 3], "inventory": ["a", "b", "c"]}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese", "a", "b", "c"])],
        )
        assert p._spare_slots(["a", "b", "c"]) <= 0
