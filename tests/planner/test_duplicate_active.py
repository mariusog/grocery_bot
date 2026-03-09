"""Test that unallocated bots deliver when carrying active-matching items.

Root cause: _allocate_carried_need gives active credit to ONE bot per item
type. When active_on_shelves == 0, unallocated bots with matching items
are throttled by _step_idle_nonactive_deliver and wait 10+ rounds.

Fix: skip the non-active delivery throttle for bots carrying items that
match the active order when active_on_shelves == 0.
"""

from tests.conftest import make_state
from grocery_bot.planner.round_planner import RoundPlanner
import bot


def _order(items, status="active"):
    return {
        "id": "o0", "items_required": items,
        "items_delivered": [], "complete": False, "status": status,
    }


def _planner(bots, items, orders, **kw):
    """Create planner with compute_needs done, for calling steps directly."""
    state = make_state(bots=bots, items=items, orders=orders, **kw)
    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    p = RoundPlanner(gs, state, full_state=state)
    p._detect_pickup_failures()
    p.active = next(
        (o for o in p.orders if o.get("status") == "active" and not o["complete"]),
        None,
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


class TestMatchingItemsSkipThrottle:
    """Bots with active-matching items skip throttle when nothing to pick."""

    def test_matching_bot_delivers_past_throttle(self):
        """Bot carrying active item delivers even when throttle is consumed."""
        bots = [
            {"id": 0, "position": [2, 4], "inventory": ["yogurt"]},
            {"id": 1, "position": [5, 4], "inventory": ["cheese", "pasta"]},
            {"id": 2, "position": [7, 4], "inventory": []},
            {"id": 3, "position": [3, 4], "inventory": ["yogurt"]},
            {"id": 4, "position": [9, 4], "inventory": ["yogurt", "rice", "milk"]},
        ]
        p = _planner(bots, [], [_order(["yogurt", "pasta", "cheese"])])
        assert p.active_on_shelves == 0
        assert p.bot_has_active[4] is False  # unallocated

        # Simulate throttle already consumed by another bot
        p._nonactive_delivering = 1
        ctx = p._build_bot_context(p.bots_by_id[4])
        result = p._step_idle_nonactive_deliver(ctx)
        assert result is True, (
            "Bot with matching items should skip throttle when "
            "active_on_shelves=0"
        )

    def test_nonmatching_bot_still_throttled(self):
        """Bot with only non-matching items stays throttled."""
        bots = [
            {"id": 0, "position": [2, 4], "inventory": ["yogurt"]},
            {"id": 1, "position": [5, 4], "inventory": ["cheese", "pasta"]},
            {"id": 2, "position": [7, 4], "inventory": ["bread", "butter"]},
            {"id": 3, "position": [3, 4], "inventory": []},
            {"id": 4, "position": [9, 4], "inventory": []},
        ]
        p = _planner(bots, [], [_order(["yogurt", "pasta", "cheese"])])
        assert p.active_on_shelves == 0

        p._nonactive_delivering = 1  # throttle consumed
        ctx = p._build_bot_context(p.bots_by_id[2])
        result = p._step_idle_nonactive_deliver(ctx)
        assert result is False, (
            "Bot with non-matching items should stay throttled"
        )

    def test_throttle_applies_when_items_on_shelves(self):
        """Even matching bots are throttled when items remain on shelves."""
        bots = [
            {"id": 0, "position": [3, 4], "inventory": ["yogurt"]},
            {"id": 1, "position": [8, 4], "inventory": ["yogurt"]},
            {"id": 2, "position": [5, 4], "inventory": []},
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["yogurt", "cheese"])])
        assert p.active_on_shelves >= 1

        p._nonactive_delivering = 1
        ctx = p._build_bot_context(p.bots_by_id[1])
        result = p._step_idle_nonactive_deliver(ctx)
        assert result is False, (
            "Throttle should apply when active items remain on shelves"
        )

    def test_active_on_shelves_unchanged(self):
        """active_on_shelves counts only shelf items, not duplicates."""
        bots = [
            {"id": 0, "position": [3, 4], "inventory": ["yogurt"]},
            {"id": 1, "position": [8, 4], "inventory": ["yogurt"]},
        ]
        p = _planner(
            bots,
            [{"id": "i0", "type": "cheese", "position": [5, 2]}],
            [_order(["yogurt", "cheese"])],
        )
        assert p.active_on_shelves == 1
