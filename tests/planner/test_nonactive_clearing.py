"""Test _step_clear_nonactive_inventory team-size gating.

This step was the root cause of bots holding useless items for 75+ rounds
on large teams. Tests verify the team-size thresholds are preserved.
"""

import bot
from grocery_bot.planner.round_planner import RoundPlanner
from tests.conftest import make_state


def _order(items):
    return {
        "id": "o0",
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": "active",
    }


def _planner(bots, items, orders, **kw):
    """Create planner with init but no plan() — for calling steps directly."""
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


class TestLargeTeamClearsWhenFull:
    def test_8bot_full_clears(self):
        """Large teams clear when inventory is completely full with non-active items."""
        bots = [{"id": 0, "position": [2, 4], "inventory": ["bread", "butter", "eggs"]}] + [
            {"id": i, "position": [i + 2, 4], "inventory": []} for i in range(1, 8)
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True

    def test_10bot_unassigned_clears_when_2_items(self):
        """Large teams: unassigned bots clear when 2+ non-active items (min_inv=2)."""
        bots = [{"id": 0, "position": [2, 4], "inventory": ["bread", "butter"]}] + [
            {"id": i, "position": [i + 2, 4], "inventory": []} for i in range(1, 10)
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese"])], width=14)
        ctx = p._build_bot_context(p.bots_by_id[0])
        # Bot 0 has no assignment, min_inv=2; 2 items >= 2 → clear
        assert p._step_clear_nonactive_inventory(ctx) is True

    def test_10bot_unassigned_keeps_1_speculative(self):
        """Large teams: unassigned bots keep 1 speculative item."""
        bots = [{"id": 0, "position": [2, 4], "inventory": ["bread"]}] + [
            {"id": i, "position": [i + 2, 4], "inventory": []} for i in range(1, 10)
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese"])], width=14)
        ctx = p._build_bot_context(p.bots_by_id[0])
        # Bot 0 has no assignment, min_inv=2; 1 item < 2 → keep
        assert p._step_clear_nonactive_inventory(ctx) is False


class TestSmallTeamClears:
    def test_2items_on_3bot_team(self):
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread", "butter"]},
            {"id": 1, "position": [7, 4], "inventory": []},
            {"id": 2, "position": [9, 4], "inventory": []},
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True

    def test_1item_skips(self):
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread"]},
            {"id": 1, "position": [7, 4], "inventory": []},
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is False


class TestMediumTeamFullOnly:
    """Medium teams (4-7 bots) clear non-active items at 2+ items."""

    def test_partial_clears(self):
        """5-bot team SHOULD clear at 2 items (lowered from 3)."""
        bots = [{"id": 0, "position": [5, 4], "inventory": ["bread", "butter"]}] + [
            {"id": i, "position": [i + 5, 4], "inventory": []} for i in range(1, 5)
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True

    def test_full_clears(self):
        bots = [{"id": 0, "position": [5, 4], "inventory": ["bread", "butter", "eggs"]}] + [
            {"id": i, "position": [i + 5, 4], "inventory": []} for i in range(1, 5)
        ]
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True


class TestNonactiveDeliveryThrottle:
    """Verify enough bots can clear non-active inventory simultaneously."""

    def test_10bot_allows_multiple_clearers(self):
        """With 10 bots, at least 3 bots should be allowed to clear simultaneously."""
        bots_list = [
            {"id": 0, "position": [2, 4], "inventory": ["bread", "butter", "eggs"]},
            {"id": 1, "position": [3, 4], "inventory": ["milk", "flour", "sugar"]},
            {"id": 2, "position": [4, 4], "inventory": ["jam", "rice", "pasta"]},
            {"id": 3, "position": [5, 4], "inventory": ["tea", "honey", "salt"]},
        ] + [{"id": i, "position": [i + 5, 4], "inventory": []} for i in range(4, 10)]
        p = _planner(
            bots_list,
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])],
            width=18,
        )
        cleared = 0
        for bid in [0, 1, 2, 3]:
            ctx = p._build_bot_context(p.bots_by_id[bid])
            if p._step_clear_nonactive_inventory(ctx):
                cleared += 1
        assert cleared >= 3, f"Only {cleared} bots cleared; expected >= 3"


class TestGuards:
    def test_skips_when_has_active(self):
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["cheese", "bread"]},
            {"id": 1, "position": [7, 4], "inventory": []},
        ]
        items = [{"id": "i0", "type": "milk", "position": [4, 2]}]
        p = _planner(bots, items, [_order(["cheese", "milk"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is False

    def test_skips_when_no_active_on_shelves(self):
        """When all active items are already carried, don't clear non-active."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread", "butter"]},
            {"id": 1, "position": [7, 4], "inventory": ["cheese"]},
        ]
        # cheese is carried by bot 1 -> active_on_shelves = 0
        p = _planner(bots, [], [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is False
