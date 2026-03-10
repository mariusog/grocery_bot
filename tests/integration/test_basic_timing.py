"""Tests for single-bot decision logic: pickup, delivery, endgame, edge cases."""

import bot
from tests.conftest import get_action, make_state, reset_bot

# --- Test: bot should not deliver with only 1 item when more items are nearby ---


class TestSmarterDropoffTiming:
    def test_deliver_partial_to_complete_order(self):
        """Bot with partial inventory rushes to deliver when it completes the order."""
        reset_bot()
        # Order needs cheese + milk. Already delivered: cheese.
        # Bot has milk (1 item). active_on_shelves > 0 (there's a bread item on
        # shelves that isn't needed). Bot's milk delivery completes the order.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["milk"]}],
            items=[
                {"id": "item_0", "type": "bread", "position": [8, 2]},
                {"id": "item_1", "type": "milk", "position": [6, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk"],
                    "items_delivered": ["cheese"],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has the last needed item. Should rush to deliver for +5 bonus.
        assert action["action"] in ("move_left", "move_down"), (
            f"Should rush to deliver to complete order, got {action}"
        )

    def test_dont_rush_partial_when_not_completing(self):
        """Bot should NOT rush to deliver partial items that don't complete the order."""
        reset_bot()
        # Order needs cheese + milk + bread. Bot has cheese (1/3).
        # Delivering cheese alone doesn't complete the order.
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [4, 2]},
                {"id": "item_1", "type": "bread", "position": [6, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has 1/3 items. Should pick up more, not rush to deliver.
        assert action["action"] != "drop_off", (
            "Should not deliver partial items that don't complete order"
        )

    def test_zero_cost_delivery_when_adjacent_to_dropoff(self):
        """Bot delivers when adjacent to dropoff and next item is past dropoff."""
        reset_bot()
        # Bot at (2, 8), dropoff at (1, 8).
        # Next needed item (milk) is at (0, 2) — on the OTHER side of the dropoff.
        # Going via dropoff: 1 step to (1,8) + dist((1,8), (1,2)) = 1 + 6 = 7.
        # Going direct: dist((2,8), (1,2)) = 7.
        # Via-dropoff (7) <= direct (7) + 1, so zero-cost delivery triggers.
        state = make_state(
            bots=[{"id": 0, "position": [2, 8], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [0, 2]},
                {"id": "item_1", "type": "cheese", "position": [4, 2]},
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
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot is 1 step from dropoff. Next item is past dropoff.
        # Should move toward dropoff for zero-cost delivery.
        assert action["action"] == "move_left", (
            f"Should deliver at zero cost when adjacent to dropoff, got {action}"
        )


class TestImprovedEndGame:
    def test_rush_delivery_when_order_uncompletable(self):
        """In endgame, deliver what you have if order can't be completed in time."""
        reset_bot()
        # 15 rounds left. Bot has 1 cheese (active). Order needs cheese + milk + bread.
        # Milk at (8,2) — too far to pick up AND deliver in 15 rounds.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [8, 2]},
                {"id": "item_1", "type": "bread", "position": [9, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=285,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Can't complete order in 15 rounds. Should deliver cheese (+1 point)
        # rather than chasing unreachable items.
        assert action["action"] in ("move_left", "move_down"), (
            f"Should deliver partial items in endgame, got {action}"
        )

    def test_keep_picking_when_completable_in_endgame(self):
        """In endgame, if order is completable, keep picking up items."""
        reset_bot()
        # 25 rounds left. Bot has cheese, milk is adjacent. Order needs both.
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [4, 3]},
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
            round_num=275,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Milk is adjacent. Order is completable. Should pick up milk.
        assert action["action"] == "pick_up", (
            f"Should pick up adjacent item when order is completable, got {action}"
        )


class TestBotStuckInCorner:
    """Bot surrounded by walls/shelves on most sides."""

    def test_bot_in_dead_end(self):
        """Bot in a dead-end corridor with only one exit should still navigate out."""
        reset_bot()
        # Bot at (1,1) with walls on 3 sides, open at (1,2)
        state = make_state(
            bots=[{"id": 0, "position": [1, 1], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [5, 4]}],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            walls=[[0, 1], [1, 0], [2, 1]],  # walls around bot except (1,2)
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Only exit is (1,2) = move_down
        assert action["action"] == "move_down", (
            f"Bot in dead end should move to only exit, got {action}"
        )
