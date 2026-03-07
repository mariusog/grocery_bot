"""Tests for preview pickup, cascade delivery, and pipelining logic."""

import bot
from tests.conftest import make_state, reset_bot, get_action


class TestOrderCompletionPriority:
    """When delivering would complete the order (+5 bonus), rush to deliver.
    Don't detour for preview items — the bonus + unlocking next order is worth more."""

    def test_rush_to_complete_order_skip_preview_detour(self):
        """Bot has all items needed to complete the order. Should rush to deliver
        even if a preview item is available for a small detour."""
        reset_bot()
        # Order needs 1 cheese. Bot has 1 cheese. Preview milk nearby.
        # Delivering completes order (+5 bonus + unlocks next order).
        # Should rush to deliver, NOT detour for preview.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [4, 4]},  # preview, nearby
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
        # Bot should head straight to dropoff (left/down), not toward preview item
        assert action["action"] in ("move_left", "move_down"), (
            f"Should rush to deliver to complete order, got {action}"
        )

    def test_rush_when_last_item_picked_up_no_cascade(self):
        """After picking up the last needed item, rush to deliver if no cascade
        items are nearby (preview needs same types as active)."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": ["milk", "cheese"]}],
            items=[
                {
                    "id": "item_0",
                    "type": "milk",
                    "position": [6, 2],
                },  # preview, same type
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese"],
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
        # Bot has all items. Preview needs milk (same as active type) — no cascade benefit.
        # Small detour not worth it for same-type. Should rush to deliver.
        assert action["action"] in ("move_left", "move_down"), (
            f"Should rush to deliver (no cascade benefit), got {action}"
        )

    def test_detour_for_cascade_item_before_completing(self):
        """When completing an order, detour for cascade-worthy preview item
        (different type from active) because it auto-delivers for free."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": ["milk", "cheese"]}],
            items=[
                {"id": "item_0", "type": "yogurt", "position": [6, 2]},  # cascade item
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["yogurt"],
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
        # Bot has all active items. Preview yogurt is a cascade item (type not in active).
        # Detour ~4 rounds saves ~10 rounds on next order. Should detour.
        assert action["action"] not in ("move_left", "move_down", "wait"), (
            f"Should detour for cascade-worthy preview item, got {action}"
        )

    def test_still_detour_when_order_not_completable(self):
        """If delivering won't complete the order (more items on shelves),
        preview detour is still worthwhile."""
        reset_bot()
        # Order needs 3 items. Bot has 1. 2 more on shelves.
        # Delivering 1 item won't complete order. Preview detour is OK.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [8, 2]},  # active, far
                {"id": "item_1", "type": "milk", "position": [8, 4]},  # active, far
                {
                    "id": "item_2",
                    "type": "yogurt",
                    "position": [4, 4],
                },  # preview, near route
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "cheese", "milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["yogurt"],
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
        # Bot can't complete the order yet (2 more items needed on shelves).
        # Should pick up more active items, not rush to deliver 1.
        assert action["action"] != "drop_off"


class TestDeliveryCascade:
    """When completing an order at dropoff, preview items in inventory that
    match the new active order are auto-delivered. The bot should be aware
    of this and prioritize picking preview items when the order is almost complete."""

    def test_pick_preview_item_for_cascade_when_order_nearly_complete(self):
        """When active order needs just 1 more item and preview item is adjacent,
        picking the preview item is high-value because it'll auto-deliver."""
        reset_bot()
        # Active order: needs 1 cheese (in inventory). Preview: needs milk.
        # Milk is adjacent. Bot should pick it up before delivering because
        # completing the order will auto-deliver the milk.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {
                    "id": "item_0",
                    "type": "milk",
                    "position": [4, 5],
                },  # adjacent preview
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
        # Adjacent preview item should be picked up before rushing to deliver
        # because completing the order will cascade-deliver it
        assert action["action"] == "pick_up", (
            f"Should pick up adjacent preview milk for cascade delivery, got {action}"
        )
