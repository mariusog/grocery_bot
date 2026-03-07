"""Tests for multi-bot coordination: assignment, collision, deadlock, dispersal."""

import bot
from tests.conftest import make_state, reset_bot, get_action


class TestMultiBotCollisionEdgeCases:
    """T6: Multi-bot collision edge cases -- narrow aisles, yield, spawn blocking."""

    def test_head_on_collision_in_narrow_corridor(self):
        """Two bots moving toward each other in a 1-wide corridor.
        They should not both try to move into each other's cell."""
        reset_bot()
        # Corridor at y=5 between walls at y=4 and y=6
        state = make_state(
            walls=[[3, 4], [4, 4], [5, 4], [6, 4], [3, 6], [4, 6], [5, 6], [6, 6]],
            bots=[
                {"id": 0, "position": [3, 5], "inventory": ["milk"]},
                {"id": 1, "position": [6, 5], "inventory": ["cheese"]},
            ],
            items=[
                {"id": "item_0", "type": "bread", "position": [7, 4]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        # Both bots have active items, both want to reach dropoff (left).
        # They should not collide — predicted positions must differ.
        from grocery_bot.pathfinding import _predict_pos

        p0 = _predict_pos(3, 5, a0["action"])
        p1 = _predict_pos(6, 5, a1["action"])
        assert p0 != p1, (
            f"Bots predicted to same cell: bot0->{p0} ({a0['action']}), "
            f"bot1->{p1} ({a1['action']})"
        )

    def test_yield_to_delivering_bot(self):
        """A bot with active items (urgency 2) should get priority over
        an empty bot (urgency 3). The empty bot should yield."""
        reset_bot()
        # Bot 0 is empty (urgency 3), Bot 1 has active items (urgency 2).
        # Bot 1 is higher urgency (lower number). Bot 0 should yield.
        state = make_state(
            bots=[
                {"id": 0, "position": [2, 7], "inventory": []},
                {"id": 1, "position": [2, 8], "inventory": ["milk"]},
            ],
            items=[
                {"id": "item_0", "type": "cheese", "position": [4, 4]},
                {"id": "item_1", "type": "milk", "position": [4, 6]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        _ = get_action(actions, 1)
        # Both bots produce valid actions
        assert len(actions) == 2
        # Bot 1 (at dropoff with active item) should drop_off
        # Bot 0 should not move into Bot 1's position
        from grocery_bot.pathfinding import _predict_pos

        p0 = _predict_pos(2, 7, a0["action"])
        assert p0 != (2, 8), (
            f"Bot 0 should yield to bot 1 at dropoff, but moved to {p0}"
        )

    def test_bots_at_spawn_disperse(self):
        """Multiple bots starting near each other should spread out,
        not all wait or block each other permanently."""
        reset_bot()
        state = make_state(
            bots=[
                {"id": 0, "position": [5, 7], "inventory": []},
                {"id": 1, "position": [5, 8], "inventory": []},
                {"id": 2, "position": [6, 7], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "milk", "position": [3, 4]},
                {"id": "item_1", "type": "cheese", "position": [7, 4]},
                {"id": "item_2", "type": "bread", "position": [5, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        moving = sum(1 for a in actions if a["action"] != "wait")
        assert moving >= 2, (
            f"At least 2 of 3 bots should be moving from spawn, "
            f"but only {moving} moved: {actions}"
        )

    def test_dropoff_congestion_three_bots(self):
        """Three bots near dropoff with items should not all deadlock.
        At least one should deliver each round."""
        reset_bot()
        state = make_state(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": ["milk"]},
                {"id": 1, "position": [1, 7], "inventory": ["cheese"]},
                {"id": 2, "position": [2, 8], "inventory": ["bread"]},
            ],
            items=[
                {"id": "item_0", "type": "yogurt", "position": [5, 4]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        # Bot 0 is AT the dropoff with an active item — must drop_off
        assert a0["action"] == "drop_off", (
            f"Bot 0 at dropoff with active item should drop_off, got {a0['action']}"
        )
        # Bot 1 and 2 should not deadlock — at least one should move
        a1 = get_action(actions, 1)
        a2 = get_action(actions, 2)
        either_moves = a1["action"] != "wait" or a2["action"] != "wait"
        assert either_moves, f"Bot 1 and 2 both waiting near dropoff: {a1}, {a2}"

    def test_five_bots_no_total_deadlock(self):
        """Five bots in a walled map should produce actions without total deadlock."""
        reset_bot()
        state = make_state(
            width=22,
            height=14,
            walls=[[x, 0] for x in range(22)]
            + [[x, 13] for x in range(22)]
            + [[0, y] for y in range(14)]
            + [[21, y] for y in range(14)]
            + [[5, y] for y in range(3, 6)]
            + [[5, y] for y in range(8, 11)],
            bots=[
                {"id": 0, "position": [3, 7], "inventory": []},
                {"id": 1, "position": [7, 7], "inventory": []},
                {"id": 2, "position": [10, 7], "inventory": []},
                {"id": 3, "position": [14, 7], "inventory": []},
                {"id": 4, "position": [17, 7], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "milk", "position": [4, 4]},
                {"id": "item_1", "type": "cheese", "position": [8, 4]},
                {"id": "item_2", "type": "bread", "position": [12, 4]},
                {"id": "item_3", "type": "yogurt", "position": [16, 4]},
                {"id": "item_4", "type": "butter", "position": [19, 4]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[2, 12],
        )
        actions = bot.decide_actions(state)
        assert len(actions) == 5, f"Expected 5 actions, got {len(actions)}"
        moving = sum(1 for a in actions if a["action"] != "wait")
        assert moving >= 3, f"At least 3 of 5 bots should move, but only {moving} did"

    def test_oscillation_detection_breaks_deadlock(self):
        """A bot that would oscillate between two positions should break
        the pattern after the history detects it."""
        reset_bot()
        # Simulate bot history by running two rounds that create oscillation
        state1 = make_state(
            walls=[[3, 4], [4, 4], [5, 4], [3, 6], [4, 6], [5, 6]],
            bots=[
                {"id": 0, "position": [3, 5], "inventory": []},
                {"id": 1, "position": [5, 5], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "milk", "position": [6, 4]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=0,
        )
        # Run 3 rounds to build history
        bot.decide_actions(state1)
        state1["round"] = 1
        state1["bots"][0]["position"] = [4, 5]
        bot.decide_actions(state1)
        state1["round"] = 2
        state1["bots"][0]["position"] = [3, 5]  # back to start = oscillation
        actions = bot.decide_actions(state1)
        # Should produce valid actions (not crash)
        assert len(actions) == 2

    def test_corridor_bots_dont_swap_positions(self):
        """Two bots in a corridor should not try to swap positions
        (both moving into each other's current cell)."""
        reset_bot()
        state = make_state(
            walls=[[4, 3], [5, 3], [4, 5], [5, 5]],
            bots=[
                {"id": 0, "position": [4, 4], "inventory": ["milk"]},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "cheese", "position": [3, 3]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        from grocery_bot.pathfinding import _predict_pos

        p0 = _predict_pos(4, 4, a0["action"])
        p1 = _predict_pos(5, 4, a1["action"])
        # They should not swap — bot 0 going to (5,4) while bot 1 goes to (4,4)
        swapped = p0 == (5, 4) and p1 == (4, 4)
        assert not swapped, f"Bots trying to swap positions: bot0->{p0}, bot1->{p1}"
