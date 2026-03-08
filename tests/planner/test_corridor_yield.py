"""Tests for corridor yielding — idle bots move out of active bots' paths.

When an active bot needs to traverse a corridor and an idle bot is sitting
in its path, the idle bot should detect this and move perpendicular to
clear the way. This prevents wasteful detours for active bots.
"""

from tests.conftest import make_state, get_action
import bot


def _order(items, status="active"):
    return {
        "id": "o0",
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": status,
    }


def _store_layout():
    """Return walls + items for a realistic 11x9 store layout."""
    from grocery_bot.simulator.map_generator import generate_store_layout

    walls_raw, _, item_shelves, _ = generate_store_layout(11, 9, 4)
    walls = [list(w) for w in walls_raw]
    items = [
        {"id": f"i{i}", "type": itype, "position": [x, y]}
        for i, (x, y, itype) in enumerate(item_shelves)
    ]
    return walls, items


class TestIdleBotYieldsToActive:
    """Idle bots should move out of the way when an active bot's path goes through them."""

    def test_idle_yields_when_blocking_rush_to_dropoff(self):
        """Idle bot at (4,1) blocks active bot rushing RIGHT to dropoff at (9,7).

        Bot 0 carries cheese, rushing to dropoff. Optimal path goes right
        along y=1 through (4,1). Without yield, the 12-step detour through
        aisles wastes many rounds.
        """
        walls, items = _store_layout()
        bots = [
            {"id": 0, "position": [2, 1], "inventory": ["cheese"]},
            {"id": 1, "position": [4, 1], "inventory": []},
            {"id": 2, "position": [8, 7], "inventory": []},
        ]
        orders = [_order(["cheese"])]
        state = make_state(
            bots=bots, items=items, orders=orders,
            drop_off=[9, 7], walls=walls, width=11, height=9,
        )

        actions = bot.decide_actions(state)
        a0 = get_action(actions, bot_id=0)

        # Bot 0 should move right (direct path toward dropoff)
        assert a0["action"] == "move_right", \
            f"Active bot should go directly right, got {a0['action']}"

    def test_idle_bot_moves_when_blocking(self):
        """Idle bot should not just wait when it's blocking an active bot."""
        walls, items = _store_layout()
        bots = [
            {"id": 0, "position": [2, 1], "inventory": ["cheese"]},
            {"id": 1, "position": [4, 1], "inventory": []},
            {"id": 2, "position": [8, 7], "inventory": []},
        ]
        orders = [_order(["cheese"])]
        state = make_state(
            bots=bots, items=items, orders=orders,
            drop_off=[9, 7], walls=walls, width=11, height=9,
        )

        actions = bot.decide_actions(state)
        a1 = get_action(actions, bot_id=1)

        # Bot 1 should not just wait — it should move out of the way
        assert a1["action"] != "wait", \
            "Idle bot should not wait when blocking active bot's path"

    def test_no_yield_when_not_in_path(self):
        """Idle bot NOT in the active bot's path should not be forced to yield."""
        walls, items = _store_layout()
        bots = [
            {"id": 0, "position": [2, 1], "inventory": ["cheese"]},
            {"id": 1, "position": [6, 4], "inventory": []},
        ]
        orders = [_order(["cheese"])]
        state = make_state(
            bots=bots, items=items, orders=orders,
            drop_off=[9, 7], walls=walls, width=11, height=9,
        )

        actions = bot.decide_actions(state)
        a1 = get_action(actions, bot_id=1)
        assert a1 is not None


class TestYieldPrePrediction:
    """The _pre_predict method should predict idle bots yielding."""

    def test_predicted_position_changes_for_yielding_bot(self):
        """Idle bot's predicted position should differ from current when on active path."""
        from grocery_bot.planner.round_planner import RoundPlanner

        walls, items = _store_layout()
        bots = [
            {"id": 0, "position": [2, 1], "inventory": ["cheese"]},
            {"id": 1, "position": [4, 1], "inventory": []},
            {"id": 2, "position": [8, 7], "inventory": []},
        ]
        orders = [_order(["cheese"])]
        state = make_state(
            bots=bots, items=items, orders=orders,
            drop_off=[9, 7], walls=walls, width=11, height=9,
        )

        bot.reset_state()
        bot.decide_actions(state)
        gs = bot._gs

        p = RoundPlanner(gs, state, full_state=state)
        p.active = next(
            (o for o in p.orders if o.get("status") == "active" and not o["complete"]),
            None,
        )
        p.preview = next((o for o in p.orders if o.get("status") == "preview"), None)
        p._check_order_transition()
        p._compute_needs()
        p._compute_bot_assignments()
        p.bot_roles = {b["id"]: "pick" for b in p.bots}
        p._pre_predict()

        # Bot 1 should be predicted to yield (move away from (4, 1))
        assert p.predicted[1] != (4, 1), \
            f"Bot 1 should be predicted to yield, but predicted={p.predicted[1]}"

    def test_no_yield_prediction_when_not_blocking(self):
        """Idle bot not on any active path should stay predicted in place."""
        from grocery_bot.planner.round_planner import RoundPlanner

        walls, items = _store_layout()
        bots = [
            {"id": 0, "position": [2, 1], "inventory": ["cheese"]},
            {"id": 1, "position": [8, 7], "inventory": []},
        ]
        orders = [_order(["cheese"])]
        state = make_state(
            bots=bots, items=items, orders=orders,
            drop_off=[9, 7], walls=walls, width=11, height=9,
        )

        bot.reset_state()
        bot.decide_actions(state)
        gs = bot._gs

        p = RoundPlanner(gs, state, full_state=state)
        p.active = next(
            (o for o in p.orders if o.get("status") == "active" and not o["complete"]),
            None,
        )
        p.preview = next((o for o in p.orders if o.get("status") == "preview"), None)
        p._check_order_transition()
        p._compute_needs()
        p._compute_bot_assignments()
        p.bot_roles = {b["id"]: "pick" for b in p.bots}
        p._pre_predict()

        # Bot 1 is near the dropoff and NOT blocking — should stay in place
        assert p.predicted[1] == (8, 7), \
            f"Bot 1 should stay in place, but predicted={p.predicted[1]}"
