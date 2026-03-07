"""Tests for single-bot decision logic: pickup, delivery, endgame, edge cases."""

import bot
from grocery_bot.simulator import GameSimulator
from tests.conftest import make_state, reset_bot, get_action


# --- Test: bot should not deliver with only 1 item when more items are nearby ---


class TestPickupFailureRecovery:
    """Bot should recover when pick_up silently fails on the server.
    The server treats invalid pick_ups as 'wait' — no error, no penalty.
    If the bot keeps retrying the same failing pick_up, it gets stuck forever."""

    def test_blacklist_item_after_repeated_failures(self):
        """If pick_up for an item fails 3 times in a row, bot should try something else."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [7, 7], "inventory": []}],
            items=[
                {"id": "item_14", "type": "milk", "position": [8, 7]},
                {"id": "item_10", "type": "yogurt", "position": [8, 3]},
                {"id": "item_8", "type": "cheese", "position": [8, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=0,
        )

        # Round 0: bot should try to pick up item_14 (adjacent milk)
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "item_14"

        # Simulate: pick_up fails silently (inventory stays empty, position unchanged)
        # Call decide_actions with advancing rounds but unchanged state
        for round_num in range(1, 5):
            state["round"] = round_num
            actions = bot.decide_actions(state)
            action = get_action(actions)

        # After 3+ failures, bot should stop trying item_14
        assert action["action"] != "pick_up" or action.get("item_id") != "item_14", (
            f"Bot should give up on item_14 after repeated failures, got {action}"
        )

    def test_try_different_item_after_blacklist(self):
        """After blacklisting one item, bot should navigate to another item of same type."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [7, 7], "inventory": []}],
            items=[
                {"id": "item_14", "type": "milk", "position": [8, 7]},  # will fail
                {"id": "item_5", "type": "milk", "position": [4, 3]},  # backup
                {"id": "item_8", "type": "cheese", "position": [8, 2]},
                {"id": "item_10", "type": "yogurt", "position": [8, 5]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=0,
        )

        # Simulate 4 rounds of failed pick_up for item_14
        for round_num in range(4):
            state["round"] = round_num
            actions = bot.decide_actions(state)

        action = get_action(actions)
        # Bot should be moving toward other items, not stuck on item_14
        if action["action"] == "pick_up":
            assert action["item_id"] != "item_14", (
                "Should try a different item after blacklisting item_14"
            )
        else:
            # Moving toward another item is also acceptable
            assert action["action"].startswith("move_"), (
                f"Should be navigating to another item, got {action}"
            )

    def test_blacklist_resets_on_new_game(self):
        """Blacklist should be cleared when a new game starts (round 0, fresh init)."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [7, 7], "inventory": []}],
            items=[
                {"id": "item_14", "type": "milk", "position": [8, 7]},
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

        # Simulate failures to blacklist item_14
        for round_num in range(4):
            state["round"] = round_num
            bot.decide_actions(state)

        # Now reset and start a "new game" — blacklist should be gone
        reset_bot()
        state["round"] = 0
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Item_14 should be available again after reset
        assert action["action"] == "pick_up" and action["item_id"] == "item_14", (
            f"After reset, item_14 should be tried again, got {action}"
        )

    def test_simulator_with_failure_recovery(self):
        """Simulator should still score well (blacklist logic doesn't break normal flow)."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run()
        assert result["score"] >= 120, (
            f"Score {result['score']} regressed after adding failure recovery"
        )
