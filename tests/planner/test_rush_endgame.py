"""Test rush deliver and endgame step behaviors."""

import bot
from grocery_bot.planner.round_planner import RoundPlanner
from tests.conftest import get_action, make_state


def _order(items, oid="o0"):
    return {
        "id": oid,
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": "active",
    }


def _preview(items, oid="o1"):
    return {
        "id": oid,
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": "preview",
    }


def _planner(bots, items, orders, **kw):
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


class TestRushDeliver:
    def test_picks_adjacent_preview_while_rushing(self):
        p = _planner(
            [
                {"id": 0, "position": [3, 4], "inventory": ["cheese"]},
                {"id": 1, "position": [7, 4], "inventory": []},
            ],
            [{"id": "i1", "type": "bread", "position": [4, 4]}],
            [_order(["cheese"]), _preview(["bread"])],
            drop_off=[1, 8],
        )
        assert p.active_on_shelves == 0
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_rush_deliver(ctx) is True
        assert p.actions[-1]["action"] == "pick_up"

    def test_rushes_without_preview(self):
        p = _planner(
            [
                {"id": 0, "position": [5, 4], "inventory": ["cheese"]},
                {"id": 1, "position": [7, 4], "inventory": []},
            ],
            [],
            [_order(["cheese"])],
            drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_rush_deliver(ctx) is True
        assert p.actions[-1]["action"].startswith("move_")

    def test_skips_when_active_remain(self):
        p = _planner(
            [
                {"id": 0, "position": [5, 4], "inventory": ["cheese"]},
                {"id": 1, "position": [7, 4], "inventory": []},
            ],
            [{"id": "i0", "type": "milk", "position": [4, 2]}],
            [_order(["cheese", "milk"])],
            drop_off=[1, 8],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_rush_deliver(ctx) is False


class TestEndgame:
    def test_forces_delivery_when_tight(self):
        p = _planner(
            [{"id": 0, "position": [1, 7], "inventory": ["cheese"]}],
            [{"id": "i0", "type": "milk", "position": [9, 1]}],
            [_order(["cheese", "milk"])],
            drop_off=[1, 8],
            round_num=298,
            max_rounds=300,
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_endgame(ctx) is True

    def test_skips_with_plenty_of_time(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": ["cheese"]}],
            [{"id": "i0", "type": "milk", "position": [4, 2]}],
            [_order(["cheese", "milk"])],
            drop_off=[1, 8],
            round_num=100,
            max_rounds=300,
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_endgame(ctx) is False

    def test_skips_empty_inventory(self):
        p = _planner(
            [{"id": 0, "position": [5, 4], "inventory": []}],
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])],
            drop_off=[1, 8],
            round_num=298,
            max_rounds=300,
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_endgame(ctx) is False


class TestEndgameLive:
    def test_single_bot_delivers_last_items(self):
        state = make_state(
            bots=[{"id": 0, "position": [1, 7], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "milk", "position": [9, 1]}],
            orders=[_order(["cheese", "milk"])],
            drop_off=[1, 8],
            round_num=298,
            max_rounds=300,
        )
        bot.reset_state()
        actions = bot.decide_actions(state)
        a = get_action(actions, 0)
        assert a["action"] in ("move_down", "drop_off")
