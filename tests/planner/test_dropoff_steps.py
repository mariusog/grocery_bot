"""Test delivery and dropoff step behaviors.

Covers _step_deliver_at_dropoff, _step_clear_dropoff,
_step_idle_nonactive_deliver, and _step_inventory_full_deliver.
"""

from tests.conftest import make_state
from grocery_bot.planner.round_planner import RoundPlanner
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
    p.preview = next((o for o in p.orders if o.get("status") == "preview"), None)
    if p.active:
        p._check_order_transition()
        p._compute_needs()
        p._compute_bot_assignments()
        p.bot_roles = {b["id"]: "pick" for b in p.bots}
        p._pre_predict()
        p._decided = set()
    return p


class TestInitStaticPassesDropoff:
    """Regression: init_static must receive drop_off so zones are precomputed."""

    def test_planner_precomputes_dropoff_zones(self):
        """After plan(), GameState must have dropoff zones populated."""
        state = make_state(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_order(["cheese"])],
            drop_off=[1, 8],
        )
        bot.reset_state()
        bot.decide_actions(state)
        gs = bot._gs
        assert gs.dropoff_adjacents, "dropoff_adjacents not precomputed"
        assert gs.dropoff_approach_cells, "dropoff_approach_cells not precomputed"
        assert gs.drop_off_pos == (1, 8)

    def test_planner_precomputes_wait_cells(self):
        """Wait cells must be populated for congestion management."""
        state = make_state(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_order(["cheese"])],
            drop_off=[1, 8],
        )
        bot.reset_state()
        bot.decide_actions(state)
        gs = bot._gs
        assert gs.dropoff_wait_cells, "dropoff_wait_cells not precomputed"


class TestDeliverAtDropoff:
    def test_active_at_dropoff_delivers(self):
        p = _planner(
            [{"id": 0, "position": [1, 8], "inventory": ["cheese"]}],
            [], [_order(["cheese"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_deliver_at_dropoff(ctx) is True
        assert p.actions[-1] == {"bot": 0, "action": "drop_off"}

    def test_nonactive_at_dropoff_skips(self):
        p = _planner(
            [{"id": 0, "position": [1, 8], "inventory": ["bread"]}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_deliver_at_dropoff(ctx) is False

    def test_away_from_dropoff_skips(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": ["cheese"]}],
            [], [_order(["cheese"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_deliver_at_dropoff(ctx) is False


class TestClearDropoff:
    def test_idle_near_dropoff_clears(self):
        p = _planner(
            [{"id": 0, "position": [2, 8], "inventory": []},
             {"id": 1, "position": [5, 3], "inventory": ["cheese"]}],
            [], [_order(["cheese"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_dropoff(ctx) is True

    def test_single_bot_never_clears(self):
        p = _planner(
            [{"id": 0, "position": [1, 7], "inventory": []}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_dropoff(ctx) is False

    def test_far_from_dropoff_skips(self):
        p = _planner(
            [{"id": 0, "position": [5, 1], "inventory": []},
             {"id": 1, "position": [7, 3], "inventory": []}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_dropoff(ctx) is False


class TestIdleNonactiveDeliver:
    def test_needs_min_items(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": ["bread"]},
             {"id": 1, "position": [7, 4], "inventory": []}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_idle_nonactive_deliver(ctx) is False

    def test_enough_items_delivers(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": ["bread", "butter"]},
             {"id": 1, "position": [7, 4], "inventory": []}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_idle_nonactive_deliver(ctx) is True

    def test_at_dropoff_does_not_spam_dropoff(self):
        p = _planner(
            [{"id": 0, "position": [1, 8], "inventory": ["bread", "butter"]},
             {"id": 1, "position": [7, 4], "inventory": []}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_idle_nonactive_deliver(ctx) is False

    def test_skips_with_active_items(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": ["cheese", "bread"]},
             {"id": 1, "position": [7, 4], "inventory": []}],
            [{"id": "i0", "type": "milk", "position": [4, 2]}],
            [_order(["cheese", "milk"])],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_idle_nonactive_deliver(ctx) is False


class TestInventoryFullDeliver:
    def test_full_active_delivers(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": ["cheese", "milk", "bread"]}],
            [], [_order(["cheese", "milk", "bread"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_inventory_full_deliver(ctx) is True

    def test_not_full_skips(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": ["cheese"]}],
            [{"id": "i0", "type": "milk", "position": [4, 2]}],
            [_order(["cheese", "milk"])], drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_inventory_full_deliver(ctx) is False
