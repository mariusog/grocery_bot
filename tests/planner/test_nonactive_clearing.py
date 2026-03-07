"""Test _step_clear_nonactive_inventory team-size gating.

This step was the root cause of bots holding useless items for 75+ rounds
on large teams. Tests verify the team-size thresholds are preserved.
"""

from tests.conftest import make_state
from grocery_bot.planner.round_planner import RoundPlanner
import bot


def _order(items):
    return {"id": "o0", "items_required": items, "items_delivered": [], "complete": False, "status": "active"}


def _planner(bots, items, orders, **kw):
    """Create planner with init but no plan() — for calling steps directly."""
    state = make_state(bots=bots, items=items, orders=orders, **kw)
    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    p = RoundPlanner(gs, state, full_state=state)
    p._detect_pickup_failures()
    p.active = next((o for o in p.orders if o.get("status") == "active" and not o["complete"]), None)
    p.preview = next((o for o in p.orders if o.get("status") == "preview"), None)
    if p.active:
        p._check_order_transition()
        p._compute_needs()
        p._compute_bot_assignments()
        p.bot_roles = {b["id"]: "pick" for b in p.bots}
        p._pre_predict()
        p._decided = set()
    return p


class TestLargeTeamNeverClears:
    def test_8bot_skips(self):
        bots = [{"id": 0, "position": [2, 4], "inventory": ["bread", "butter", "eggs"]}
                ] + [{"id": i, "position": [i + 2, 4], "inventory": []} for i in range(1, 8)]
        p = _planner(bots, [{"id": "i0", "type": "cheese", "position": [4, 2]}], [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is False

    def test_10bot_skips(self):
        bots = [{"id": 0, "position": [2, 4], "inventory": ["bread", "butter", "eggs"]}
                ] + [{"id": i, "position": [i + 2, 4], "inventory": []} for i in range(1, 10)]
        p = _planner(bots, [{"id": "i0", "type": "cheese", "position": [4, 2]}], [_order(["cheese"])], width=14)
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is False


class TestSmallTeamClears:
    def test_2items_on_3bot_team(self):
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread", "butter"]},
            {"id": 1, "position": [7, 4], "inventory": []},
            {"id": 2, "position": [9, 4], "inventory": []},
        ]
        p = _planner(bots, [{"id": "i0", "type": "cheese", "position": [4, 2]}], [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True

    def test_1item_skips(self):
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread"]},
            {"id": 1, "position": [7, 4], "inventory": []},
        ]
        p = _planner(bots, [{"id": "i0", "type": "cheese", "position": [4, 2]}], [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is False


class TestMediumTeamFullOnly:
    def test_partial_skips(self):
        bots = [{"id": 0, "position": [5, 4], "inventory": ["bread", "butter"]}
                ] + [{"id": i, "position": [i + 5, 4], "inventory": []} for i in range(1, 5)]
        p = _planner(bots, [{"id": "i0", "type": "cheese", "position": [4, 2]}], [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is False

    def test_full_clears(self):
        bots = [{"id": 0, "position": [5, 4], "inventory": ["bread", "butter", "eggs"]}
                ] + [{"id": i, "position": [i + 5, 4], "inventory": []} for i in range(1, 5)]
        p = _planner(bots, [{"id": "i0", "type": "cheese", "position": [4, 2]}], [_order(["cheese"])])
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True


class TestGuards:
    def test_skips_when_has_active(self):
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["cheese", "bread"]},
            {"id": 1, "position": [7, 4], "inventory": []},
        ]
        p = _planner(bots, [{"id": "i0", "type": "milk", "position": [4, 2]}], [_order(["cheese", "milk"])])
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
