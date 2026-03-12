"""Tests for deliverer priority and desync prevention."""

import json

import bot
from grocery_bot.pathfinding import _predict_pos
from grocery_bot.planner.round_planner import RoundPlanner
from tests.conftest import get_action, make_state


def _medium_corridor_state():
    """Reproduce the live Medium bug: B1 blocks B2's path to dropoff.

    Map layout (16x12) — column x=1 is a corridor.
    B2 at (1,5) has active items, heading to dropoff at (1,10).
    B1 at (1,7) has non-active [yogurt], blocking the corridor.
    """
    with open("maps/2026-03-12_16x12_3bot.json") as f:
        map_data = json.load(f)

    return make_state(
        bots=[
            {"id": 0, "position": [4, 9], "inventory": ["pasta", "pasta"]},
            {"id": 1, "position": [1, 7], "inventory": ["yogurt"]},
            {"id": 2, "position": [1, 5], "inventory": ["bread", "cheese", "cheese"]},
        ],
        items=map_data["items"],
        orders=[
            {
                "id": "o0",
                "items_required": ["eggs", "milk", "cream"],
                "items_delivered": ["eggs", "milk", "cream"],
                "complete": True,
                "status": "completed",
            },
            {
                "id": "o1",
                "items_required": ["eggs", "milk", "cream", "cheese"],
                "items_delivered": ["eggs", "milk", "cream", "cheese"],
                "complete": True,
                "status": "completed",
            },
            {
                "id": "o2",
                "items_required": ["eggs", "milk", "cream", "cheese", "bread"],
                "items_delivered": ["eggs", "milk", "cream"],
                "complete": False,
                "status": "active",
            },
            {
                "id": "o3",
                "items_required": ["pasta", "pasta", "yogurt", "bread", "cheese"],
                "items_delivered": [],
                "complete": False,
                "status": "pending",
            },
        ],
        drop_off=[1, 10],
        walls=map_data["grid"]["walls"],
        width=map_data["grid"]["width"],
        height=map_data["grid"]["height"],
        round_num=76,
    )


class TestDelivererPriority:
    """Active-carrying bots should be planned before idle bots."""

    def test_deliverer_moves_toward_dropoff(self):
        """B2 with active items should move down toward dropoff, not up."""
        state = _medium_corridor_state()

        bot.reset_state()
        bot.decide_actions(state)
        gs = bot._gs

        planner = RoundPlanner(gs, state, full_state=state)
        planner.plan()

        b2_action = get_action(planner.actions, bot_id=2)
        assert b2_action is not None
        assert b2_action["action"] == "move_down", (
            f"B2 at (1,5) with active items should move down toward dropoff (1,10), "
            f"got {b2_action['action']}. "
            f"Active-carrying bot should have priority over idle B1."
        )

    def test_idle_bot_does_not_block_deliverer(self):
        """B1 with non-active items should not claim the cell B2 needs."""
        state = _medium_corridor_state()

        bot.reset_state()
        bot.decide_actions(state)
        gs = bot._gs

        planner = RoundPlanner(gs, state, full_state=state)
        planner.plan()

        b1_action = get_action(planner.actions, bot_id=1)
        b2_action = get_action(planner.actions, bot_id=2)
        assert b1_action is not None
        assert b2_action is not None

        # B1 and B2 should not converge on the same cell
        from grocery_bot.pathfinding import _predict_pos

        b1_target = _predict_pos(1, 7, b1_action["action"])
        b2_target = _predict_pos(1, 5, b2_action["action"])
        assert b1_target != b2_target, (
            f"B1 and B2 converge on {b1_target}. "
            f"B1 (non-active) should yield to B2 (active deliverer)."
        )


class TestStaticBfsOverrideDesync:
    """Static BFS anti-oscillation must not route into occupied cells."""

    def _desync_state(self):
        """R123 desync: B1 tries move_down into B0's cell.

        B1 at (1,7) heading to dropoff (1,10). B0 sits at (1,8).
        B1's history makes (1,6) oscillate. Static BFS override must
        not choose (1,8) — B0 is there.
        """
        with open("maps/2026-03-12_16x12_3bot.json") as f:
            map_data = json.load(f)

        return make_state(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": []},
                {"id": 1, "position": [1, 7], "inventory": ["butter", "eggs", "cream"]},
                {"id": 2, "position": [2, 9], "inventory": ["cheese", "bread"]},
            ],
            items=map_data["items"],
            orders=[
                {
                    "id": "o4",
                    "items_required": ["butter", "eggs", "cream"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "o5",
                    "items_required": ["cheese", "bread", "yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "pending",
                },
            ],
            drop_off=[1, 10],
            walls=map_data["grid"]["walls"],
            width=map_data["grid"]["width"],
            height=map_data["grid"]["height"],
            round_num=123,
        )

    def test_no_move_into_occupied_cell(self):
        """B1 must not move into (1,8) where B0 sits."""
        state = self._desync_state()

        bot.reset_state()
        bot.decide_actions(state)
        gs = bot._gs
        # History that makes (1,6) trigger oscillation
        gs.bot_history[1] = [(1, 5), (1, 6), (1, 7)]

        planner = RoundPlanner(gs, state, full_state=state)
        planner.plan()

        b1_action = get_action(planner.actions, bot_id=1)
        assert b1_action is not None
        target = _predict_pos(1, 7, b1_action["action"])
        assert target != (1, 8), (
            f"B1 moves into B0's cell (1,8) — desync! Got {b1_action['action']}"
        )
