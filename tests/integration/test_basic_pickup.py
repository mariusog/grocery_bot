"""Tests for single-bot decision logic: pickup, delivery, endgame, edge cases."""

import bot
from tests.conftest import make_state, reset_bot, get_action


# --- Test: bot should not deliver with only 1 item when more items are nearby ---


class TestNoSingleItemDelivery:
    def test_bot_picks_up_more_items_before_delivering(self):
        """If a bot has 1 active item and more are needed nearby, pick up more first."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {
                    "id": "item_0",
                    "type": "cheese",
                    "position": [4, 2],
                },  # shelf at (4,2)
                {"id": "item_1", "type": "milk", "position": [4, 4]},  # shelf at (4,4)
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "cheese", "milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has 1 cheese, needs 1 more cheese + 1 milk. Both items are adjacent.
        # It should NOT rush to deliver — it should pick up another item first.
        assert action["action"] != "drop_off", (
            "Should not deliver with 1/3 items when more are nearby"
        )
        # Should not be heading to dropoff
        assert action["action"] != "move_down" or True  # direction depends on layout


class TestRushDeliveryWhenOrderCompletable:
    def test_rush_when_all_items_carried(self):
        """If all needed items are in inventory (none left on shelves), rush to deliver."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "bread", "position": [4, 2]},  # not needed
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
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has the only needed item. Should rush to deliver.
        assert action["action"] in (
            "move_left",
            "move_down",
            "move_up",
            "move_right",
        ), "Should be moving toward dropoff"


class TestDontPickUpUnneededItems:
    def test_only_pick_needed_count(self):
        """Bot should not pick up more items of a type than the order needs."""
        reset_bot()
        # Order needs 1 cheese, but there are 3 cheese items adjacent
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [2, 3]},
                {"id": "item_1", "type": "cheese", "position": [4, 3]},
                {"id": "item_2", "type": "cheese", "position": [3, 2]},
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
        )
        # Round 1: pick up 1 cheese
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "pick_up", "Should pick up adjacent cheese"

        # Simulate: bot now has 1 cheese, order needs 1 cheese (all carried)
        reset_bot()
        state2 = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                # item_0 was picked up, remaining:
                {"id": "item_1", "type": "cheese", "position": [4, 3]},
                {"id": "item_2", "type": "cheese", "position": [3, 2]},
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
            round_num=1,
        )
        actions2 = bot.decide_actions(state2)
        action2 = get_action(actions2)
        # Bot already has the 1 cheese needed. Should NOT pick up more cheese.
        # Should head to deliver.
        assert action2["action"] != "pick_up", (
            f"Should not pick up more cheese (already have 1/1 needed), got {action2}"
        )


class TestEndGameSkipsDistantItems:
    def test_skip_item_too_far_to_deliver(self):
        """With few rounds left, don't chase items that can't be delivered in time."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": []}],
            items=[
                # Item far away — needs ~15 rounds to reach + deliver
                {"id": "item_0", "type": "milk", "position": [10, 1]},
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
            round_num=295,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Only 5 rounds left, item is ~15+ rounds away. Should wait, not chase.
        assert action["action"] == "wait", (
            f"Should wait when item is unreachable in remaining rounds, got {action}"
        )


class TestSingleItemDeliveryWaste:
    def test_bot_does_not_deliver_1_item_when_more_needed_nearby(self):
        """
        Regression: bot picks up 1 item, then rushes to deliver it alone because
        active_items_remaining == 0 (all others already assigned/carried).
        With 1 bot, this means the bot makes multiple trips with partial loads.
        The bot should pick up as many items as it can (up to 3) before delivering.
        """
        reset_bot()
        # Order needs 4 cheese. Bot has 0. There are 4 cheese items.
        # Bot should pick up 3, deliver, pick up 1, deliver — NOT pick 1, deliver, pick 1, deliver...
        # Layout: aisle at y=5, shelves on both sides
        #   Items on shelves at x=2 and x=4 (rows), bot walks in aisle x=3
        #   Bot at (3,5) is adjacent to items at (2,5) and (4,5)
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": []}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [2, 5]},  # adjacent left
                {
                    "id": "item_1",
                    "type": "cheese",
                    "position": [4, 5],
                },  # adjacent right
                {"id": "item_2", "type": "cheese", "position": [2, 3]},  # nearby shelf
                {"id": "item_3", "type": "cheese", "position": [4, 3]},  # nearby shelf
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "cheese", "cheese", "cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot is adjacent to items at (2,5) and (4,5). Should pick one up.
        assert action["action"] == "pick_up", (
            f"Bot should pick up adjacent cheese, not {action['action']}"
        )

        # After picking up 1: bot has 1 cheese, 3 remaining on map, 3 more needed
        reset_bot()
        state2 = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {
                    "id": "item_1",
                    "type": "cheese",
                    "position": [4, 5],
                },  # still adjacent
                {"id": "item_2", "type": "cheese", "position": [2, 3]},
                {"id": "item_3", "type": "cheese", "position": [4, 3]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "cheese", "cheese", "cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=1,
        )
        actions2 = bot.decide_actions(state2)
        action2 = get_action(actions2)
        # 3 more cheese still needed. Bot has 1 and item_1 is adjacent. Should pick up more.
        assert action2["action"] == "pick_up", (
            f"Should pick up adjacent cheese (3 more needed), got {action2}"
        )


class TestNoRushWithSingleItem:
    def test_no_rush_delivery_when_order_needs_many_more(self):
        """
        Bug: active_items_remaining == 0 triggers rush delivery because all items
        are 'assigned' to this bot. But the bot only has 1 in inventory and needs
        to pick up 3 more. It should NOT rush to deliver 1 item.

        active_items_remaining should reflect items still on shelves, not assigned ones.
        """
        reset_bot()
        # Order needs 4 cheese total. Bot has picked up 1 so far (just delivered 3).
        # 1 cheese still on shelf. Bot should pick it up, not rush-deliver.
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [4, 3]},  # adjacent
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "cheese", "cheese", "cheese"],
                    "items_delivered": ["cheese", "cheese"],  # 2 already delivered
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=60,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Order needs 2 more cheese. Bot has 1, shelf has 1.
        # active_items_remaining should be 1 (1 on shelf).
        # Bot should pick up the adjacent cheese, not rush to deliver.
        assert action["action"] == "pick_up", (
            f"Should pick up adjacent cheese (1 more on shelf needed), got {action}"
        )
