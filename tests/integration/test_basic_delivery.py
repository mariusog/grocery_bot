"""Tests for single-bot decision logic: pickup, delivery, endgame, edge cases."""

import bot
from grocery_bot.simulator import GameSimulator
from tests.conftest import make_state, reset_bot, get_action


# --- Test: bot should not deliver with only 1 item when more items are nearby ---


class TestDropoffAtDropoff:
    def test_deliver_when_at_dropoff_with_active_items(self):
        """Bot at dropoff with active order items should deliver."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["cheese"]}],
            items=[{"id": "item_0", "type": "milk", "position": [4, 2]}],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "drop_off", (
            "Should deliver when at dropoff with needed items"
        )


class TestEndGamePartialDelivery:
    """In the last ~30 rounds, if the order can't be completed, still deliver
    individual items for +1 each rather than waiting."""

    def test_pick_up_nearby_item_in_endgame(self):
        """With 8 rounds left, a nearby item should still be picked up and delivered."""
        reset_bot()
        # Bot at dropoff (1,8). Item at (2,7) — 2 steps away. Dropoff is 2 steps from item.
        # Total round trip: 2 (walk) + 1 (pickup) + 2 (return) = 5 rounds. Fits in 8.
        state = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": []}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [2, 7]},  # close
                {"id": "item_1", "type": "milk", "position": [8, 2]},  # far
                {"id": "item_2", "type": "bread", "position": [8, 4]},  # far
                {"id": "item_3", "type": "butter", "position": [8, 6]},  # far
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "bread", "butter"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=292,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # 8 rounds left. Can't complete the 4-item order. But cheese is close enough
        # to pick up and deliver for +1 point. Should NOT wait.
        assert action["action"] != "wait", (
            f"Should pick up nearby item in endgame for partial credit, got {action}"
        )

    def test_wait_when_nothing_reachable_in_endgame(self):
        """With 3 rounds left and all items far away, waiting is correct."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": []}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [10, 1]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=297,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "wait", (
            f"Should wait when no items reachable in 3 rounds, got {action}"
        )

    def test_deliver_partial_items_in_endgame(self):
        """Bot has items in inventory near end of game. Should deliver them for +1 each
        even if the order won't be completed."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [1, 7], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [10, 1]},  # too far
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=297,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has cheese, dropoff is 1 step away. Should deliver for +1.
        assert action["action"] == "move_down", (
            f"Should deliver partial items in endgame, got {action}"
        )


class TestNoActiveOrder:
    """Test behavior when no active order exists."""

    def test_all_bots_wait_when_no_active_order(self):
        """All bots should wait when there's no active order."""
        reset_bot()
        state = make_state(
            bots=[
                {"id": 0, "position": [5, 5], "inventory": []},
                {"id": 1, "position": [7, 5], "inventory": []},
            ],
            items=[{"id": "i1", "type": "milk", "position": [3, 3]}],
            orders=[],  # No orders at all
        )
        actions = bot.decide_actions(state)
        for a in actions:
            assert a["action"] == "wait"

    def test_bots_wait_when_all_orders_complete(self):
        """Bots wait when the only order is already complete."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "i1", "type": "milk", "position": [3, 3]}],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": True,
                    "items_required": ["milk"],
                    "items_delivered": ["milk"],
                }
            ],
        )
        actions = bot.decide_actions(state)
        assert actions[0]["action"] == "wait"


# =============================================================================
# Strategy agent tests (from agent-ae79b897)
# =============================================================================
