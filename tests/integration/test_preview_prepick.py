"""Tests for preview pickup, cascade delivery, and pipelining logic."""

import bot
from tests.conftest import get_action, make_state, reset_bot


class TestStep6AdjacentPreviewPickup:
    """Hit Step 6 adjacent preview pickup (lines 700-736)."""

    def test_step6_adjacent_cascade_preview_pickup(self):
        """Bot with no active items picks up adjacent cascade preview item in Step 6."""
        reset_bot()
        # Active order needs milk which is fully delivered
        # Bot has no items, is adjacent to a preview item
        # Preview item type != active type -> cascade-able
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=[
                {"id": "i_cheese", "type": "cheese", "position": [3, 3]},
            ],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": ["milk"],
                },
                {
                    "id": "o2",
                    "status": "preview",
                    "complete": False,
                    "items_required": ["cheese"],
                    "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "i_cheese"

    def test_step6_adjacent_noncascade_preview_pickup(self):
        """Bot picks up adjacent non-cascade preview item when no cascade available."""
        reset_bot()
        # Active order needs milk (delivered), preview needs milk too
        # Same type -> not cascade-able, but still should pick up
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=[
                {"id": "i_milk", "type": "milk", "position": [3, 3]},
            ],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": ["milk"],
                },
                {
                    "id": "o2",
                    "status": "preview",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "i_milk"

    def test_step6_walk_to_distant_cascade_preview(self):
        """Bot walks to distant cascade preview item when no active items on shelves."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[
                {"id": "i_cheese", "type": "cheese", "position": [2, 2]},
            ],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": ["milk"],
                },
                {
                    "id": "o2",
                    "status": "preview",
                    "complete": False,
                    "items_required": ["cheese"],
                    "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        # Should navigate toward the cheese item
        assert action["action"] != "wait"
        assert action["action"].startswith("move_")

    def test_step6_distant_noncascade_preview(self):
        """Bot walks to distant non-cascade preview item when no active items."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[
                {"id": "i_milk2", "type": "milk", "position": [2, 2]},
            ],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": ["milk"],
                },
                {
                    "id": "o2",
                    "status": "preview",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        assert action["action"].startswith("move_")


class TestDedicatedPreviewBot:
    def test_preview_bot_assigned_when_order_nearly_complete(self):
        """With 2 bots, 1 active item on shelves, spare bot goes for preview items."""
        reset_bot()
        # Order needs cheese (1 item). Bot 0 is nearby. Bot 1 is far.
        # Bot 1 should be assigned as preview bot and head for preview items.
        state = make_state(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [8, 7], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "cheese", "position": [4, 2]},
                {"id": "item_1", "type": "milk", "position": [8, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        # Bot 0 should head for active cheese
        assert a0["action"] != "wait", "Bot 0 should pursue active item"
        # Bot 1 should head for preview milk (not toward active cheese)
        assert a1["action"] != "wait", "Bot 1 should pursue preview item"

    def test_no_preview_bot_when_not_enough_idle(self):
        """Don't assign preview bot when all bots are needed for active items."""
        reset_bot()
        # Order needs 2 items (cheese + milk). 2 bots, both needed.
        # No preview bot should be assigned.
        state = make_state(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [8, 5], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "cheese", "position": [4, 2]},
                {"id": "item_1", "type": "milk", "position": [8, 2]},
                {"id": "item_2", "type": "bread", "position": [6, 6]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        # Both should be pursuing active items (not preview)
        assert a0["action"] != "wait"
        assert a1["action"] != "wait"


class TestPreviewPipeliningNearlyComplete:
    """Preview pipelining when active order is nearly complete."""

    def test_pipeline_preview_items_on_last_delivery_trip(self):
        """When bot is carrying the last active item to deliver and has 2 empty slots,
        pick up preview items on the way if they're cheap to grab."""
        reset_bot()
        # Bot has cheese (last active item needed). Preview needs milk + bread.
        # Milk shelf is adjacent to bot on the way to dropoff.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [4, 5]},  # adjacent
                {"id": "item_1", "type": "bread", "position": [8, 2]},  # far
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["milk", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 8],
            round_num=50,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # All active items accounted for. Preview milk is adjacent (free pickup).
        # Bot should pick it up before heading to deliver.
        assert action["action"] == "pick_up", (
            f"Should pick up adjacent preview milk when carrying last active item, got {action}"
        )

    def test_no_pipeline_when_detour_too_expensive(self):
        """Don't pipeline preview items if the detour would cost too many rounds."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [2, 7], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [10, 1]},  # very far
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 8],
            round_num=50,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Preview milk is very far. Should head straight to dropoff.
        assert action["action"] in ("move_left", "move_down"), (
            f"Should not detour for distant preview item, got {action}"
        )
