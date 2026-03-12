"""Test that plan() always produces valid output across team sizes."""

import bot
from tests.conftest import get_action, make_planner, make_state


def _order(items, oid="o0"):
    return {
        "id": oid,
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": "active",
    }


class TestOneActionPerBot:
    def test_1bot(self):
        p = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_order(["cheese"])],
        )
        assert len(p.actions) == 1
        assert p.actions[0]["bot"] == 0

    def test_3bot(self):
        p = make_planner(
            bots=[{"id": i, "position": [i * 3 + 2, 4], "inventory": []} for i in range(3)],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_order(["cheese"])],
        )
        assert len(p.actions) == 3
        assert {a["bot"] for a in p.actions} == {0, 1, 2}

    def test_5bot(self):
        p = make_planner(
            bots=[{"id": i, "position": [i * 2 + 1, 4], "inventory": []} for i in range(5)],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [6, 2]},
            ],
            orders=[_order(["cheese", "milk"])],
        )
        assert len(p.actions) == 5
        assert {a["bot"] for a in p.actions} == set(range(5))


class TestAllWaitWhenNoOrder:
    def test_completed_order(self):
        p = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[],
            orders=[
                {
                    "id": "o0",
                    "items_required": ["cheese"],
                    "items_delivered": ["cheese"],
                    "complete": True,
                    "status": "completed",
                }
            ],
        )
        assert all(a["action"] == "wait" for a in p.actions)


class TestBasicBehavior:
    def test_picks_adjacent_item(self):
        state = make_state(
            bots=[{"id": 0, "position": [3, 2], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_order(["cheese"])],
        )
        bot.reset_state()
        a = get_action(bot.decide_actions(state), 0)
        assert a["action"] == "pick_up"

    def test_delivers_when_all_picked(self):
        state = make_state(
            bots=[{"id": 0, "position": [5, 4], "inventory": ["cheese"]}],
            items=[],
            orders=[_order(["cheese"])],
            drop_off=[1, 8],
        )
        bot.reset_state()
        a = get_action(bot.decide_actions(state), 0)
        assert a["action"].startswith("move_")

    def test_drops_off_at_dropoff(self):
        state = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["cheese"]}],
            items=[],
            orders=[_order(["cheese"])],
            drop_off=[1, 8],
        )
        bot.reset_state()
        a = get_action(bot.decide_actions(state), 0)
        assert a["action"] == "drop_off"

    def test_mixed_inventory_at_dropoff(self):
        state = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["cheese", "bread"]}],
            items=[],
            orders=[_order(["cheese"])],
            drop_off=[1, 8],
        )
        bot.reset_state()
        a = get_action(bot.decide_actions(state), 0)
        assert a["action"] == "drop_off"
