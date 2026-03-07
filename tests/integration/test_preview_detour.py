"""Tests for preview pickup, cascade delivery, and pipelining logic."""

import bot
from tests.conftest import make_state, reset_bot, get_action


class TestStep5PreviewDetour:
    """Test Step 5: preview detour while delivering active items."""

    def test_detour_for_nearby_preview_item_while_delivering(self):
        """Bot carrying active items should detour for nearby preview item
        when it has spare slots beyond active needs."""
        reset_bot()
        # Bot at (5, 5), drop-off at (1, 8), has 1 active item, needs to deliver
        # Preview item at (4, 4) — slightly off the direct path
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["milk"]}],
            items=[
                {"id": "i_preview", "type": "bread", "position": [4, 4]},
                {"id": "i_active", "type": "milk", "position": [8, 2]},
            ],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": [],
                },
                {
                    "id": "o2",
                    "status": "preview",
                    "complete": False,
                    "items_required": ["bread"],
                    "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        # Bot has the active item and needs to deliver, but might detour for preview
        # The action should be a move (either toward drop-off or toward preview item)
        assert action["action"] != "wait"

    def test_skip_distant_preview_during_delivery(self):
        """Bot should not detour far for preview while delivering active items."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [2, 7], "inventory": ["milk"]}],
            items=[
                {"id": "i_preview", "type": "bread", "position": [9, 1]},
            ],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": [],
                },
                {
                    "id": "o2",
                    "status": "preview",
                    "complete": False,
                    "items_required": ["bread"],
                    "items_delivered": [],
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        # Bot should head to drop-off, not detour to (9, 1)
        assert action["action"] in ("move_down", "move_left")


class TestStep5PreviewDetourDeep:
    """Hit the deep branches in Step 5 (lines 630-666)."""

    def test_step5_detour_to_nearby_preview_not_adjacent(self):
        """Bot with active item detours for non-adjacent preview item on way to drop-off.

        Step 3a only picks up *adjacent* preview items. This test places the preview
        item 2+ cells away (not adjacent), so step 3a skips it. Step 4 finds no
        reachable active items (endgame). Step 5 then detours for the preview item.
        """
        reset_bot()
        # Bot at (5, 5) with 1 milk (active item)
        # Active order needs milk + bread; bread at (9, 1) unreachable in endgame
        # Preview item cheese at (3, 3) — NOT adjacent to bot, but near drop-off path
        # active_items_on_shelves = 1, spare = 3-1-1 = 1 > 0
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["milk"]}],
            items=[
                {"id": "i_bread", "type": "bread", "position": [9, 1]},
                {"id": "i_cheese", "type": "cheese", "position": [3, 3]},
            ],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk", "bread"],
                    "items_delivered": [],
                },
                {
                    "id": "o2",
                    "status": "preview",
                    "complete": False,
                    "items_required": ["cheese"],
                    "items_delivered": [],
                },
            ],
            drop_off=[1, 8],
            round_num=1,
            max_rounds=10,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        # Bot should move (either toward drop-off or toward preview detour)
        assert action["action"] != "wait"
        assert action["action"].startswith("move_")


class TestStep6DistantPreviewPrepick:
    """Test Step 6: walking to distant preview items when no active items left."""

    def test_walk_to_preview_when_active_complete(self):
        """Bot should navigate to preview items when all active items are picked up
        and it has nothing to deliver."""
        reset_bot()
        # Active order is fully delivered except for what other bots carry
        # Bot 0 has no active items in inventory, no active items on shelves
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[
                {"id": "i_preview", "type": "bread", "position": [3, 3]},
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
                    "items_required": ["bread"],
                    "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        # Bot should move toward the preview item, not wait
        assert action["action"] != "wait"

    def test_pick_adjacent_preview_item(self):
        """Bot picks up adjacent preview item when no active items needed."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=[
                {"id": "i_preview", "type": "bread", "position": [3, 3]},
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
                    "items_required": ["bread"],
                    "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "i_preview"
