"""Tests for _step_shadow_deliver.

This step routes preview-item-carrying bots toward the dropoff when all active
items are already picked up (active_on_shelves == 0), so they trail the active
deliverer instead of being pulled away by _step_preview_prepick.
"""

import bot
from grocery_bot.planner.round_planner import RoundPlanner
from tests.conftest import make_state


def _order(items, status="active"):
    return {
        "id": "o0",
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": status,
    }


def _preview_order(items):
    return {
        "id": "o1",
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": "preview",
    }


def _planner(bots, items, orders, **kw):
    """Create a RoundPlanner ready for calling _step_shadow_deliver directly."""
    state = make_state(bots=bots, items=items, orders=orders, **kw)
    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    p = RoundPlanner(gs, state, full_state=state)
    p._detect_pickup_failures()
    p.active = next(
        (o for o in p.orders if o.get("status") == "active" and not o["complete"]), None
    )
    p.preview = next((o for o in p.orders if o.get("status") == "preview"), None)
    if p.active:
        p._check_order_transition()
        p._compute_needs()
        p._compute_bot_assignments()
        p.bot_roles = {b["id"]: "pick" for b in p.bots}
        p._pre_predict()
        p._decided = set()
    return p


class TestShadowDeliverRoutesTowardDropoff:
    def test_shadow_deliver_routes_toward_dropoff(self):
        """active_on_shelves=0, bot carries preview items -> returns True, moves toward dropoff."""
        # Bot 1 carries the active item (cheese) — so active_on_shelves=0.
        # Bot 0 carries a preview item (milk) and is far from dropoff.
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["milk"]},
            {"id": 1, "position": [3, 4], "inventory": ["cheese"]},
            {"id": 2, "position": [7, 4], "inventory": []},
        ]
        items = []  # No items on shelves; cheese is carried by bot 1
        orders = [
            _order(["cheese"]),
            _preview_order(["milk"]),
        ]
        p = _planner(bots, items, orders)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is True

    def test_shadow_deliver_skips_when_active_on_shelves(self):
        """active_on_shelves > 0 -> returns False (don't tail when work remains)."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["milk"]},
            {"id": 1, "position": [7, 4], "inventory": []},
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        orders = [
            _order(["cheese"]),
            _preview_order(["milk"]),
        ]
        p = _planner(bots, items, orders)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is False

    def test_shadow_deliver_skips_when_has_active(self):
        """Bot already carries active items -> returns False."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["cheese", "milk"]},
            {"id": 1, "position": [7, 4], "inventory": []},
        ]
        items = []
        orders = [
            _order(["cheese"]),
            _preview_order(["milk"]),
        ]
        p = _planner(bots, items, orders)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is False

    def test_shadow_deliver_skips_no_preview(self):
        """No preview order pending -> returns False."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["milk"]},
            {"id": 1, "position": [3, 4], "inventory": ["cheese"]},
        ]
        items = []
        orders = [_order(["cheese"])]  # No preview order
        p = _planner(bots, items, orders)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is False

    def test_shadow_deliver_skips_no_preview_items_in_inv(self):
        """Bot carries items but none are preview types -> returns False."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread"]},  # bread not in preview
            {"id": 1, "position": [3, 4], "inventory": ["cheese"]},
            {"id": 2, "position": [7, 4], "inventory": []},
        ]
        items = []
        orders = [
            _order(["cheese"]),
            _preview_order(["milk"]),  # preview wants milk, bot has bread
        ]
        p = _planner(bots, items, orders)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is False

    def test_shadow_deliver_cap_at_one(self):
        """Two eligible bots: first fires (True), second falls through (False)."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["milk"]},
            {"id": 1, "position": [3, 4], "inventory": ["milk"]},
            {"id": 2, "position": [7, 4], "inventory": ["cheese"]},
        ]
        items = []
        orders = [
            _order(["cheese"]),
            _preview_order(["milk", "milk"]),
        ]
        p = _planner(bots, items, orders, width=13)
        ctx0 = p._build_bot_context(p.bots_by_id[0])
        ctx1 = p._build_bot_context(p.bots_by_id[1])
        first = p._step_shadow_deliver(ctx0)
        second = p._step_shadow_deliver(ctx1)
        assert first is True
        assert second is False

    def test_shadow_deliver_skips_large_teams(self):
        """use_predictions=True (8+ bots) -> returns False."""
        bots = [{"id": 0, "position": [5, 4], "inventory": ["milk"]}] + [
            {"id": i, "position": [i + 2, 4], "inventory": ["cheese"] if i == 1 else []}
            for i in range(1, 8)
        ]
        items = []
        orders = [
            _order(["cheese"]),
            _preview_order(["milk"]),
        ]
        p = _planner(bots, items, orders, width=14)
        assert p.cfg.use_predictions is True
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is False

    def test_shadow_deliver_at_dropoff_falls_through(self):
        """Bot AT dropoff (d=0) with preview items -> returns False.

        No d=0 escape-hatch: routing would cause A-B-A oscillation between
        the dropoff and the adjacent cell, blocking the active deliverer.
        Returning False delegates to _step_clear_dropoff instead.
        """
        drop = [1, 8]
        bots = [
            {"id": 0, "position": drop, "inventory": ["milk"]},
            {"id": 1, "position": [5, 4], "inventory": ["cheese"]},
            {"id": 2, "position": [7, 4], "inventory": []},
        ]
        items = []
        orders = [
            _order(["cheese"]),
            _preview_order(["milk"]),
        ]
        p = _planner(bots, items, orders, drop_off=drop)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is False

    def test_shadow_deliver_within_approach_zone_falls_through(self):
        """Bot within DROPOFF_CLEAR_RADIUS of dropoff -> returns False.

        When d <= DROPOFF_CLEAR_RADIUS, shadow_deliver falls through so the bot
        can be routed away by preview_prepick, unblocking the active deliverer's
        approach corridor.  Firing here would cause deadlocks in narrow corridors.
        """
        from grocery_bot.constants import DROPOFF_CLEAR_RADIUS

        drop = [1, 8]
        # Place bot at exactly d=DROPOFF_CLEAR_RADIUS from dropoff (d=3 from (1,8) → (4,8) or (1,5))
        near_pos = [1 + DROPOFF_CLEAR_RADIUS, 8]  # d = DROPOFF_CLEAR_RADIUS
        bots = [
            {"id": 0, "position": near_pos, "inventory": ["milk"]},
            {"id": 1, "position": [8, 4], "inventory": ["cheese"]},
            {"id": 2, "position": [9, 4], "inventory": []},
        ]
        items = []
        orders = [
            _order(["cheese"]),
            _preview_order(["milk"]),
        ]
        p = _planner(bots, items, orders, drop_off=drop)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_shadow_deliver(ctx)
        assert result is False
