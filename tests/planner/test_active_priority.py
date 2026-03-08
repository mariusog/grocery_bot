"""Tests for active item priority over preview/speculative pickup.

When active order items are still needed, bots must prioritize them
over preview items. The +5 order completion bonus makes this critical.

Also covers multiple drop-off zones (Nightmare difficulty).
"""

import bot
from tests.conftest import make_state, get_action
from tests.planner.conftest import _active_order, _preview_order


class TestActivePriorityOverPreview:
    """Bots must pick up active items before preview items."""

    def test_adjacent_active_preferred_over_adjacent_preview(self):
        """Bot adjacent to both active and preview items picks active."""
        state = make_state(
            bots=[{"id": 0, "position": [3, 2], "inventory": []}],
            items=[
                {"id": "i_cheese", "type": "cheese", "position": [4, 2]},
                {"id": "i_bread", "type": "bread", "position": [2, 2]},
            ],
            orders=[
                _active_order(["cheese"]),
                _preview_order(["bread"]),
            ],
        )
        actions = bot.decide_actions(state)
        act = get_action(actions, 0)
        assert act["action"] == "pick_up", "Should pick up an item"
        assert act["item_id"] == "i_cheese", (
            f"Should pick active item cheese, not preview item {act['item_id']}"
        )

    def test_no_preview_pickup_when_active_on_shelves(self):
        """Bot adjacent to preview item should navigate to active instead."""
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[
                {"id": "i_cheese", "type": "cheese", "position": [8, 2]},
                {"id": "i_bread", "type": "bread", "position": [6, 5]},
            ],
            orders=[
                _active_order(["cheese"]),
                _preview_order(["bread"]),
            ],
        )
        actions = bot.decide_actions(state)
        act = get_action(actions, 0)
        if act["action"] == "pick_up":
            assert act["item_id"] != "i_bread", (
                "Bot picked up preview item while active items remain"
            )

    def test_multi_bot_active_priority(self):
        """Each bot adjacent to both active and preview picks active."""
        state = make_state(
            bots=[
                {"id": 0, "position": [4, 3], "inventory": []},
                {"id": 1, "position": [6, 3], "inventory": []},
                {"id": 2, "position": [8, 3], "inventory": []},
            ],
            items=[
                # Active items (above bots, adjacent)
                {"id": "i_cheese", "type": "cheese", "position": [4, 2]},
                {"id": "i_milk", "type": "milk", "position": [6, 2]},
                {"id": "i_salt", "type": "salt", "position": [8, 2]},
                # Preview items (below bots, adjacent)
                {"id": "i_bread", "type": "bread", "position": [4, 4]},
                {"id": "i_eggs", "type": "eggs", "position": [6, 4]},
            ],
            orders=[
                _active_order(["cheese", "milk", "salt"]),
                _preview_order(["bread", "eggs"]),
            ],
        )
        actions = bot.decide_actions(state)
        preview_ids = {"i_bread", "i_eggs"}
        active_ids = {"i_cheese", "i_milk", "i_salt"}
        pickups = [a for a in actions if a["action"] == "pick_up"]
        assert len(pickups) == 3, f"Expected 3 pickups, got {len(pickups)}"
        for a in pickups:
            assert a["item_id"] in active_ids, (
                f"Bot {a['bot']} picked {a['item_id']} "
                f"(preview) instead of active item"
            )


class TestActivePriorityMultiDropoff:
    """Active priority with multiple drop-off zones (Nightmare)."""

    def test_active_priority_with_two_dropoff_zones(self):
        """Bots near different zones still prioritize active items."""
        # Two drop zones: (1, 8) and (9, 8)
        # Bots near each zone, active items on shelves, preview adjacent
        state = make_state(
            bots=[
                {"id": 0, "position": [2, 5], "inventory": []},
                {"id": 1, "position": [8, 5], "inventory": []},
            ],
            items=[
                # Active items near each zone
                {"id": "i_cheese", "type": "cheese", "position": [2, 2]},
                {"id": "i_milk", "type": "milk", "position": [8, 2]},
                # Preview items adjacent to bots
                {"id": "i_bread", "type": "bread", "position": [3, 5]},
                {"id": "i_eggs", "type": "eggs", "position": [9, 5]},
            ],
            orders=[
                _active_order(["cheese", "milk"]),
                _preview_order(["bread", "eggs"]),
            ],
            drop_off=[1, 8],
        )
        # Add multiple drop-off zones
        state["drop_off_zones"] = [[1, 8], [9, 8]]
        actions = bot.decide_actions(state)
        preview_ids = {"i_bread", "i_eggs"}
        for a in actions:
            if a["action"] == "pick_up":
                assert a["item_id"] not in preview_ids, (
                    f"Bot {a['bot']} picked preview {a['item_id']} "
                    f"with active items on shelves (multi-zone)"
                )

    def test_bot_uses_nearest_dropoff_for_delivery(self):
        """Bot with active items delivers to nearest drop-off zone."""
        state = make_state(
            bots=[
                {"id": 0, "position": [9, 8], "inventory": ["cheese"]},
            ],
            items=[
                {"id": "i_milk", "type": "milk", "position": [5, 2]},
            ],
            orders=[
                _active_order(["cheese", "milk"]),
            ],
            drop_off=[1, 8],
        )
        state["drop_off_zones"] = [[1, 8], [9, 8]]
        actions = bot.decide_actions(state)
        act = get_action(actions, 0)
        # Bot 0 is ON zone (9,8) — should deliver immediately
        assert act["action"] == "drop_off", (
            f"Bot at dropoff zone should deliver, got {act['action']}"
        )
