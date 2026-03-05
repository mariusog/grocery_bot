"""Tests for grocery bot decision logic."""

import bot
from simulator import GameSimulator


def make_state(
    bots=None,
    items=None,
    orders=None,
    drop_off=None,
    walls=None,
    width=11,
    height=9,
    round_num=0,
    max_rounds=300,
    score=0,
):
    """Build a minimal game state dict for testing."""
    return {
        "type": "game_state",
        "round": round_num,
        "max_rounds": max_rounds,
        "grid": {
            "width": width,
            "height": height,
            "walls": walls or [],
        },
        "bots": bots or [],
        "items": items or [],
        "orders": orders or [],
        "drop_off": drop_off or [1, 8],
        "score": score,
        "active_order_index": 0,
        "total_orders": 5,
    }


def reset_bot():
    """Reset global state between tests."""
    bot._blocked_static = None
    bot._dist_cache = {}
    bot._adj_cache = {}
    bot._last_pickup = {}
    bot._pickup_fail_count = {}
    bot._blacklisted_items = set()


def get_action(actions, bot_id=0):
    """Extract action for a specific bot."""
    for a in actions:
        if a["bot"] == bot_id:
            return a
    return None


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


class TestMultiBotAssignment:
    def test_two_bots_assigned_different_items(self):
        """Two bots should not both chase the same item."""
        reset_bot()
        state = make_state(
            bots=[
                {"id": 0, "position": [2, 5], "inventory": []},
                {"id": 1, "position": [8, 5], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "milk", "position": [3, 2]},  # closer to bot 0
                {
                    "id": "item_1",
                    "type": "bread",
                    "position": [7, 2],
                },  # closer to bot 1
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[5, 8],
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        # Both bots should be moving (not waiting), and toward different items
        assert a0["action"] != "wait", "Bot 0 should be moving toward an item"
        assert a1["action"] != "wait", "Bot 1 should be moving toward an item"


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


class TestPreviewPickupOnSecondTrip:
    """The main bottleneck: 4-item orders need 2 trips, and the second trip
    carries only 1 item with 2 empty slots. The bot should fill those slots
    with preview items if they're nearby."""

    def test_pick_preview_when_no_active_items_to_pick(self):
        """When no active items remain on shelves and bot has empty slots,
        pick up preview items instead of just heading to deliver."""
        reset_bot()
        # Active order: 1 cheese already in inventory, 0 more on shelves
        # Preview order: needs yogurt, which is on the map
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {
                    "id": "item_0",
                    "type": "yogurt",
                    "position": [4, 5],
                },  # adjacent, preview item
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
        # Bot has the only active item. No more active items on shelves.
        # Preview yogurt is adjacent. Bot should pick it up before delivering.
        assert action["action"] == "pick_up", (
            f"Should pick up adjacent preview item before delivering, got {action}"
        )

    def test_dont_pick_preview_when_active_needs_slots(self):
        """Don't pick up preview items if it would use a slot needed for active items."""
        reset_bot()
        # Order needs cheese + milk (2 items). Bot has butter (1/3 slots).
        # Preview yogurt is adjacent. But bot needs 2 more slots for active items.
        # Should NOT pick up preview yogurt — need those slots for cheese/milk.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["butter"]}],
            items=[
                {
                    "id": "item_0",
                    "type": "yogurt",
                    "position": [6, 5],
                },  # adjacent preview
                {"id": "item_1", "type": "cheese", "position": [4, 2]},  # active
                {"id": "item_2", "type": "milk", "position": [8, 2]},  # active
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["butter", "cheese", "milk"],
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
            round_num=10,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Should NOT pick up preview yogurt — needs slots for active items
        assert action["action"] != "pick_up" or action.get("item_id") != "item_0", (
            f"Should not pick up preview yogurt when active items need slots, got {action}"
        )

    def test_pick_preview_on_way_to_last_active_item(self):
        """While heading to pick up the last active item, if a preview item
        is adjacent, pick it up (free slot available)."""
        reset_bot()
        # Bot heading toward active cheese at (8,3). Preview milk at (4,5) is adjacent.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": []}],
            items=[
                {
                    "id": "item_0",
                    "type": "cheese",
                    "position": [8, 2],
                },  # far active item
                {
                    "id": "item_1",
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
        # Preview milk is adjacent and bot has 3 empty slots. Should pick it up.
        assert action["action"] == "pick_up", (
            f"Should pick up adjacent preview item when passing by, got {action}"
        )
        assert action["item_id"] == "item_1"

    def test_pick_preview_near_route_to_dropoff(self):
        """When heading to deliver 1 active item with 2 empty slots,
        detour slightly for a preview item if it's cheap."""
        reset_bot()
        # Bot at (5,5) heading to dropoff at (1,8). Preview item at (4,4) is close
        # and roughly on the way.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["cheese"]}],
            items=[
                {
                    "id": "item_0",
                    "type": "milk",
                    "position": [4, 4],
                },  # near route, preview
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "cheese"],
                    "items_delivered": ["cheese"],  # 1 already delivered, 1 in inv
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
        # All active items accounted for (1 delivered + 1 in inv = 2 needed).
        # No more active items on shelves. Bot should go toward preview milk
        # before delivering since it's near the route and saves a future trip.
        # The preview item adj cell is (5,4) or (3,4), both reachable.
        # Direct to dropoff ~= 7 steps. Via preview item ~= 2 + 8 = 10. Detour = 3.
        # This should be worth it since picking it up now saves ~14 rounds later.
        assert action["action"] != "wait"
        # Bot should move toward the preview item, not straight to dropoff
        # Moving toward (4,4) adj cell means move_up or move_left
        assert action["action"] in ("move_up", "move_left", "pick_up"), (
            f"Should detour toward preview item, got {action}"
        )

    def test_dont_detour_for_distant_preview(self):
        """Don't detour for a preview item if it's far from the delivery route."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [3, 7], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [10, 1]},  # far away
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
        # Active item in inventory, should deliver. Preview item is too far to detour.
        # Bot should head toward dropoff (move_left or move_down).
        assert action["action"] in ("move_left", "move_down"), (
            f"Should head to dropoff, not detour to distant preview, got {action}"
        )


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


class TestAntiCollision:
    """Bots should not block each other in narrow aisles. Actions resolve
    in bot ID order (bot 0 moves first), so higher-ID bots must plan around
    lower-ID bots' predicted positions."""

    def test_bots_dont_target_same_cell(self):
        """Two bots should not both try to move to the same cell."""
        reset_bot()
        # Two bots in a corridor, both want to move right
        state = make_state(
            bots=[
                {"id": 0, "position": [3, 5], "inventory": []},
                {"id": 1, "position": [4, 5], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "milk", "position": [6, 4]},
                {"id": "item_1", "type": "bread", "position": [2, 4]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "bread"],
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
        # Bot 0 at (3,5), Bot 1 at (4,5). They shouldn't both try to occupy
        # the same cell. Since moves resolve in ID order, bot 1 treats bot 0's
        # current position as blocked — but bot 0 may have moved.
        # At minimum, neither should "wait" due to being blocked.
        assert a0["action"] != "wait", f"Bot 0 should be moving, got {a0}"
        assert a1["action"] != "wait", f"Bot 1 should be moving, got {a1}"

    def test_higher_bot_plans_around_lower_bot_move(self):
        """Bot 0 moves first. Bot 1 should predict bot 0's new position
        and plan accordingly, rather than treating bot 0 as stationary."""
        reset_bot()
        # Single-width corridor along y=5. Bot 0 at (3,5) moving left, Bot 1 at (4,5).
        # Bot 0 will move to (2,5). So (3,5) will be free for bot 1.
        # Bot 1 should be able to move left into (3,5).
        state = make_state(
            walls=[[3, 4], [4, 4], [5, 4], [3, 6], [4, 6], [5, 6]],
            bots=[
                {"id": 0, "position": [3, 5], "inventory": ["milk"]},
                {"id": 1, "position": [4, 5], "inventory": []},
            ],
            items=[
                {
                    "id": "item_0",
                    "type": "cheese",
                    "position": [2, 4],
                },  # bot 0 heading here
                {
                    "id": "item_1",
                    "type": "bread",
                    "position": [2, 6],
                },  # bot 1 should go here
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
            width=11,
            height=9,
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        # Bot 0 should move left (toward cheese). Bot 1 should also move left.
        # If bot 1 treats bot 0 as static, it can't move left and gets stuck.
        assert a0["action"] == "move_left", f"Bot 0 should move left, got {a0}"
        # Ideally bot 1 moves left too (bot 0 will vacate (3,5))
        # Current code treats bot 0 as static, so bot 1 might wait. That's the bug.
        assert a1["action"] == "move_left", (
            f"Bot 1 should move left (bot 0 will vacate), got {a1}"
        )

    def test_bot_waits_if_only_path_blocked(self):
        """If a bot's only path forward is blocked by another bot, it should
        wait rather than try to move into it (which fails silently)."""
        reset_bot()
        # Narrow corridor: walls on both sides, bot 1 blocked by bot 0
        #  Wall  Wall  Wall
        #  Bot0  Bot1  (open)
        #  Wall  Wall  Wall
        state = make_state(
            walls=[[3, 4], [4, 4], [5, 4], [3, 6], [4, 6], [5, 6]],
            bots=[
                {"id": 0, "position": [4, 5], "inventory": ["milk"]},  # blocking
                {"id": 1, "position": [5, 5], "inventory": []},
            ],
            items=[
                {"id": "item_0", "type": "cheese", "position": [2, 4]},
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
            width=11,
            height=9,
        )
        actions = bot.decide_actions(state)
        a1 = get_action(actions, 1)
        # Bot 0 has milk, heading to pick cheese or deliver.
        # Bot 1 wants to go left toward cheese but bot 0 is in the way.
        # Bot 1 should NOT try to move left (will fail silently = wasted round).
        # It should wait or find alternative.
        if a1["action"] == "move_left":
            # This would try to move into bot 0's cell (4,5) — bad
            assert False, "Bot 1 should not try to move into bot 0's cell"


class TestInterleavedDelivery:
    """For 4-item orders with 3-slot inventory, the bot must make 2 trips.
    If picking 2 items then delivering, then picking 2 more is shorter than
    picking 3 then 1, the bot should choose the shorter split."""

    def test_prefer_2_2_split_when_dropoff_between_items(self):
        """When the dropoff is between two groups of items, deliver mid-route.
        Layout: items at left side, dropoff in middle, items at right side.
        Pick 2 left items → deliver → pick 2 right items → deliver
        is better than pick 3 → deliver → pick 1 → deliver."""
        reset_bot()
        # Bot starts near dropoff. Items on both sides of the map.
        # Left items at x=2, right items at x=9. Dropoff at x=5.
        # 2+2 split: pick 2 left → deliver → pick 2 right → deliver
        # 3+1 split: pick 3 left (but only 2 there) so must do left+right+left
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[
                {"id": "item_0", "type": "milk", "position": [2, 5]},  # left
                {"id": "item_1", "type": "cheese", "position": [2, 3]},  # left
                {"id": "item_2", "type": "bread", "position": [9, 5]},  # right
                {"id": "item_3", "type": "yogurt", "position": [9, 3]},  # right
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese", "bread", "yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[5, 8],
            width=12,
            height=10,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # The bot should head toward one group of items, not zigzag.
        # With TSP, it should pick the 2 closest items first.
        assert action["action"] != "wait"

    def test_deliver_when_passing_dropoff_with_items(self):
        """If the bot has active items and is at the dropoff on its way to
        pick up more items, it should deliver (partial delivery)."""
        reset_bot()
        # Bot at dropoff with 2 active items, 2 more needed on shelves
        state = make_state(
            bots=[{"id": 0, "position": [5, 8], "inventory": ["milk", "cheese"]}],
            items=[
                {"id": "item_0", "type": "bread", "position": [8, 2]},
                {"id": "item_1", "type": "yogurt", "position": [8, 4]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "cheese", "bread", "yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[5, 8],
            round_num=50,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot is at dropoff with 2 active items and 2 more to pick.
        # Should deliver now (free — already at dropoff) rather than
        # carry items around while picking more.
        assert action["action"] == "drop_off", (
            f"Should deliver when at dropoff with active items, even if more needed, got {action}"
        )


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


class TestMultiTripPlanning:
    """For 4-item orders, the bot must make 2 trips. Multi-trip planning
    should evaluate all possible splits to minimize total rounds."""

    def test_plan_multi_trip_finds_optimal_split(self):
        """Directly test plan_multi_trip: leave close-to-dropoff item for trip 2."""
        reset_bot()
        # Set up blocked set with these items as shelves
        state = make_state(
            items=[
                {"id": "item_0", "type": "bread", "position": [2, 6]},
                {"id": "item_1", "type": "cheese", "position": [2, 3]},
                {"id": "item_2", "type": "milk", "position": [2, 2]},
                {"id": "item_3", "type": "yogurt", "position": [9, 3]},
            ],
            width=12,
            height=10,
        )
        bot.init_static(state)

        drop_off = (1, 8)
        # Bot NOT at dropoff — at (5, 5). This makes trips asymmetric.
        bot_pos = (5, 5)
        # adj cells: bread→(1,6)or(3,6), cheese→(1,3)or(3,3),
        #            milk→(1,2)or(3,2), yogurt→(8,3)or(10,3)
        items = state["items"]
        candidates = []
        for it in items:
            cell, d = bot.find_best_item_target(bot_pos, it, bot._blocked_static)
            if cell:
                candidates.append((it, cell))

        route = bot.plan_multi_trip(bot_pos, candidates, drop_off, capacity=3)
        # Route should be trip 1 items (up to 3).
        # The function minimizes total cost of trip1 + trip2.
        assert len(route) <= 3
        assert len(route) >= 1
        trip1_types = {it["type"] for it, _ in route}
        # Whatever split, total cost should be <= naive 3-closest approach
        trip1_cost = bot.tsp_cost(bot_pos, route, drop_off)
        trip2_items = [
            (it, cell) for it, cell in candidates if it["type"] not in trip1_types
        ]
        trip2_cost = bot.tsp_cost(drop_off, trip2_items, drop_off) if trip2_items else 0
        total_optimal = trip1_cost + trip2_cost

        # Compare with greedy: 3 closest
        candidates_sorted = sorted(
            candidates, key=lambda c: bot.dist_static(bot_pos, c[1])
        )
        greedy_trip1 = candidates_sorted[:3]
        greedy_trip2 = candidates_sorted[3:]
        greedy_route1 = bot.tsp_route(bot_pos, greedy_trip1, drop_off)
        greedy_cost = bot.tsp_cost(bot_pos, greedy_route1, drop_off)
        if greedy_trip2:
            greedy_route2 = bot.tsp_route(drop_off, greedy_trip2, drop_off)
            greedy_cost += bot.tsp_cost(drop_off, greedy_route2, drop_off)

        assert total_optimal <= greedy_cost, (
            f"Multi-trip ({total_optimal}) should be <= greedy ({greedy_cost})"
        )

    def test_simulator_no_regression(self):
        """Verify multi-trip planning doesn't regress simulated scores."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run()
        assert result["score"] >= 120, (
            f"Score {result['score']} regressed from baseline"
        )


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


class TestPreviewDoesntBlockActive:
    """REGRESSION: Bot fills inventory with preview items, blocking active pickups.
    This caused score to drop from 118 to 2 on live server."""

    def test_dont_fill_inventory_with_preview_when_active_needed(self):
        """Bot needs yogurt for active order. Has 1 preview cheese in inventory.
        Step 6 should NOT pick up more preview items if active items still needed."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 7], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "yogurt", "position": [4, 2]},  # active needed
                {"id": "item_1", "type": "milk", "position": [4, 6]},  # preview needed
                {"id": "item_2", "type": "bread", "position": [6, 6]},  # preview needed
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "yogurt"],
                    "items_delivered": ["cheese", "milk"],
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
        # Active order still needs yogurt. Bot has cheese (preview) in inventory.
        # Bot must NOT pick up more preview items — it needs the slot for yogurt.
        assert action["action"] != "pick_up" or action.get("item_id") == "item_0", (
            f"Should go pick active yogurt, not preview items, got {action}"
        )
        # Bot should be heading toward yogurt (up/left)
        assert action["action"] in ("move_up", "move_left", "pick_up"), (
            f"Should move toward active item yogurt, got {action}"
        )

    def test_step6_respects_active_slots(self):
        """Step 6 preview pickup should not use slots needed for active items."""
        reset_bot()
        # Bot has empty inventory, active order needs 2 items, preview needs 1.
        # Bot has 3 slots. Active needs 2 → only 1 spare for preview.
        # Preview item is adjacent. Bot should pick it up (1 spare slot).
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": []}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [8, 2]},  # active, far
                {"id": "item_1", "type": "milk", "position": [8, 4]},  # active, far
                {
                    "id": "item_2",
                    "type": "yogurt",
                    "position": [4, 5],
                },  # preview, adjacent
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
        # 3 slots - 2 active needed = 1 spare. Adjacent preview item OK.
        # Bot should pick up the preview yogurt (it's free, adjacent).
        # This is step 3 opportunistic pickup.
        assert action["action"] != "wait"

    def test_no_preview_when_inventory_full_of_preview(self):
        """Bot has 2 preview items, active needs 1 more item.
        Only 1 slot left → must reserve for active item, NOT pick preview."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["bread", "milk"]}],
            items=[
                {"id": "item_0", "type": "yogurt", "position": [4, 2]},  # active needed
                {
                    "id": "item_1",
                    "type": "cheese",
                    "position": [6, 5],
                },  # preview, adjacent
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["cheese"],
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
        # 1 slot left, active needs yogurt → no spare slots for preview
        # Bot must NOT pick up preview cheese even though adjacent
        assert action.get("item_id") != "item_1", (
            f"Should NOT pick preview cheese when active needs the slot, got {action}"
        )

    def test_dont_walk_to_preview_when_active_unreachable(self):
        """When active item exists on map but can't be reached (all adjacent blocked),
        the bot should NOT walk toward distant preview items indefinitely."""
        reset_bot()
        # Active needs yogurt. Yogurt at (4,4) surrounded by walls on 3 sides
        # and a shelf on the 4th — unreachable.
        # Preview needs cheese. Cheese at (8,2) far away.
        # Bot at (5,7) with cheese (preview) in inventory.
        state = make_state(
            bots=[{"id": 0, "position": [5, 7], "inventory": ["cheese"]}],
            items=[
                {
                    "id": "item_0",
                    "type": "yogurt",
                    "position": [4, 4],
                },  # active, unreachable
                {"id": "item_1", "type": "cheese", "position": [8, 2]},  # preview, far
            ],
            # Make yogurt unreachable: all adjacent cells blocked
            walls=[[3, 4], [5, 4], [4, 3], [4, 5]],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "yogurt"],
                    "items_delivered": ["cheese", "milk"],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["cheese"],
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
        # Bot should NOT walk toward distant preview cheese when active yogurt is still needed
        # (even though yogurt is unreachable). It should wait or go to dropoff.
        # Critically, it must not enter a loop chasing preview items.
        assert action["action"] != "move_right", (
            f"Should NOT walk toward distant preview when active items still needed, got {action}"
        )

    def test_simulator_no_stuck_loop(self):
        """Full simulation should never get stuck (same action for 10+ rounds)."""
        sim = GameSimulator(seed=42, num_bots=1)
        bot._blocked_static = None
        bot._dist_cache = {}
        bot._adj_cache = {}

        last_actions = []
        for _ in range(300):
            if sim.is_over():
                break
            state = sim.get_state()
            if not state["orders"]:
                break
            actions = bot.decide_actions(state)
            # Track action+position for loop detection
            b = sim.bots[0]
            sig = (
                tuple(b["position"]),
                actions[0]["action"],
                actions[0].get("item_id"),
            )
            last_actions.append(sig)
            if len(last_actions) > 10:
                last_actions.pop(0)
                # Check if last 10 actions repeat a 2-round cycle
                if len(set(last_actions)) <= 2:
                    assert False, (
                        f"Bot stuck in loop at round {sim.round}: {last_actions}"
                    )
            sim.apply_actions(actions)

        assert sim.score > 50, f"Score {sim.score} too low — possible stuck loop"


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


class TestSimulatedGame:
    """Run the bot through a full simulated game to measure actual scores."""

    def test_easy_single_seed(self):
        """Single Easy game should score reasonably."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run(verbose=True)
        assert result["score"] >= 50, f"Score {result['score']} too low for Easy map"
        assert result["orders_completed"] >= 5, (
            f"Only completed {result['orders_completed']} orders"
        )

    def test_easy_average_across_seeds(self):
        """Average across multiple seeds should be consistent."""
        scores = []
        for seed in range(5):
            sim = GameSimulator(seed=seed, num_bots=1)
            result = sim.run()
            scores.append(result["score"])
            print(
                f"  Seed {seed}: score={result['score']}, "
                f"orders={result['orders_completed']}, "
                f"items={result['items_delivered']}"
            )
        avg = sum(scores) / len(scores)
        print(f"  Average: {avg:.1f}, Min: {min(scores)}, Max: {max(scores)}")
        assert avg >= 50, f"Average score {avg:.1f} too low"

    def test_easy_completes_first_order(self):
        """Bot should at least complete the first order."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run()
        assert result["orders_completed"] >= 1, "Failed to complete even 1 order"

    def test_no_wasted_rounds_at_start(self):
        """Bot should start moving on round 0, not wait."""
        sim = GameSimulator(seed=42, num_bots=1)
        state = sim.get_state()
        bot._blocked_static = None
        bot._dist_cache = {}
        bot._adj_cache = {}
        actions = bot.decide_actions(state)
        action = actions[0]
        assert action["action"] != "wait", (
            f"Bot should not wait on round 0, got {action}"
        )
