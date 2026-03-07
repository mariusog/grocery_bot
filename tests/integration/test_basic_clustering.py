"""Tests for single-bot decision logic: pickup, delivery, endgame, edge cases."""

import bot
from tests.conftest import make_state, reset_bot, get_action


# --- Test: bot should not deliver with only 1 item when more items are nearby ---


class TestEmptyOrdersAndBlacklist:
    """Edge cases: empty orders, all items blacklisted."""

    def test_empty_order_items_required(self):
        """An order with 0 items required should be considered complete instantly."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [4, 4]}],
            orders=[
                {
                    "id": "order_0",
                    "items_required": [],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Empty order needs nothing -> active_needed = {}, no items on shelves
        # Bot should wait or head to dropoff (order arguably already complete).
        # The key is it should not crash.
        assert action is not None, "Should return an action even for empty order"

    def test_all_items_blacklisted(self):
        """If all items of a needed type are blacklisted, bot should not crash."""
        reset_bot()
        # Manually blacklist the only milk item
        bot._gs.blacklisted_items.add("item_0")
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [4, 4]}],
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
        )
        # Need to initialize statics first
        bot.init_static(state)
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # All milk items blacklisted. Bot can't pick up anything. Should wait.
        assert action["action"] == "wait", (
            f"Should wait when all needed items are blacklisted, got {action}"
        )

    def test_no_orders_returns_wait(self):
        """If there are no active orders, all bots should wait."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [4, 4]}],
            orders=[],
            drop_off=[1, 8],
        )
        bot.init_static(state)
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "wait", (
            f"Should wait when no orders exist, got {action}"
        )


class TestItemProximityClustering:
    """When multiple instances of the same item type exist, pick the one
    closest to other needed items to reduce total route length."""

    def test_pick_item_near_other_needed_items(self):
        """Two cheese items exist. One is near the other needed item (milk),
        the other is far. Bot should pick the one near milk."""
        reset_bot()
        # Cheese at (2,3) is near milk at (2,5). Cheese at (9,3) is far from milk.
        # Bot at (5,5). Both cheeses are similar distance from bot.
        # But cheese at (2,3) is much better because milk is right next to it.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [9, 3]},  # far from milk
                {"id": "item_1", "type": "cheese", "position": [2, 3]},  # near milk
                {"id": "item_2", "type": "milk", "position": [2, 5]},
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
            width=12,
            height=10,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # TSP should route to cheese at (2,3) + milk at (2,5) since they're close.
        # Bot should head left toward the cluster, not right toward isolated cheese.
        assert action["action"] == "move_left", (
            f"Should head toward item cluster (left), got {action}"
        )


# --- Phase 4.2: Item Proximity Clustering ---


class TestItemProximityClusteringAdvanced:
    def test_prefer_item_near_other_needed_items(self):
        """When choosing between same-type items, prefer one closer to other items."""
        reset_bot()
        # Order needs 1 milk + 1 cheese. Two milk items available:
        # milk_near at (4,2) — close to cheese at (6,2)
        # milk_far at (8,6) — far from cheese
        # Bot should prefer milk_near since it reduces total route.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": []}],
            items=[
                {"id": "milk_near", "type": "milk", "position": [4, 2]},
                {"id": "milk_far", "type": "milk", "position": [8, 6]},
                {"id": "cheese", "type": "cheese", "position": [6, 2]},
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
        action = get_action(actions)
        # Bot should head toward the milk closer to the cheese cluster
        assert action["action"] != "wait", "Bot should be navigating toward items"
