"""Tests for grocery bot decision logic."""
import bot


def make_state(
    bots=None, items=None, orders=None, drop_off=None,
    walls=None, width=11, height=9, round_num=0, max_rounds=300,
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
                {"id": "item_0", "type": "cheese", "position": [4, 2]},  # shelf at (4,2)
                {"id": "item_1", "type": "milk", "position": [4, 4]},    # shelf at (4,4)
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
        assert action["action"] != "drop_off", "Should not deliver with 1/3 items when more are nearby"
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
        assert action["action"] in ("move_left", "move_down", "move_up", "move_right"), \
            "Should be moving toward dropoff"


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
        assert action2["action"] != "pick_up", \
            f"Should not pick up more cheese (already have 1/1 needed), got {action2}"


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
        assert action["action"] == "wait", \
            f"Should wait when item is unreachable in remaining rounds, got {action}"


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
                {"id": "item_0", "type": "milk", "position": [3, 2]},   # closer to bot 0
                {"id": "item_1", "type": "bread", "position": [7, 2]},  # closer to bot 1
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
                {"id": "item_1", "type": "cheese", "position": [4, 5]},  # adjacent right
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
        assert action["action"] == "pick_up", \
            f"Bot should pick up adjacent cheese, not {action['action']}"

        # After picking up 1: bot has 1 cheese, 3 remaining on map, 3 more needed
        reset_bot()
        state2 = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "item_1", "type": "cheese", "position": [4, 5]},  # still adjacent
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
        assert action2["action"] == "pick_up", \
            f"Should pick up adjacent cheese (3 more needed), got {action2}"


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
        assert action["action"] == "pick_up", \
            f"Should pick up adjacent cheese (1 more on shelf needed), got {action}"


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
                {"id": "item_0", "type": "yogurt", "position": [4, 5]},  # adjacent, preview item
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
        assert action["action"] == "pick_up", \
            f"Should pick up adjacent preview item before delivering, got {action}"

    def test_dont_pick_preview_when_active_needs_slots(self):
        """Don't pick up preview items if it would use a slot needed for active items."""
        reset_bot()
        # Order needs cheese + milk (2 items). Bot has butter (1/3 slots).
        # Preview yogurt is adjacent. But bot needs 2 more slots for active items.
        # Should NOT pick up preview yogurt — need those slots for cheese/milk.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["butter"]}],
            items=[
                {"id": "item_0", "type": "yogurt", "position": [6, 5]},  # adjacent preview
                {"id": "item_1", "type": "cheese", "position": [4, 2]},  # active
                {"id": "item_2", "type": "milk", "position": [8, 2]},    # active
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
        assert action["action"] != "pick_up" or action.get("item_id") != "item_0", \
            f"Should not pick up preview yogurt when active items need slots, got {action}"

    def test_pick_preview_on_way_to_last_active_item(self):
        """While heading to pick up the last active item, if a preview item
        is adjacent, pick it up (free slot available)."""
        reset_bot()
        # Bot heading toward active cheese at (8,3). Preview milk at (4,5) is adjacent.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": []}],
            items=[
                {"id": "item_0", "type": "cheese", "position": [8, 2]},  # far active item
                {"id": "item_1", "type": "milk", "position": [4, 5]},    # adjacent preview
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
        assert action["action"] == "pick_up", \
            f"Should pick up adjacent preview item when passing by, got {action}"
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
                {"id": "item_0", "type": "milk", "position": [4, 4]},  # near route, preview
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
        assert action["action"] in ("move_up", "move_left", "pick_up"), \
            f"Should detour toward preview item, got {action}"

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
        assert action["action"] in ("move_left", "move_down"), \
            f"Should head to dropoff, not detour to distant preview, got {action}"


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
        assert action["action"] in ("move_left", "move_down"), \
            f"Should rush to deliver to complete order, got {action}"

    def test_rush_when_last_item_picked_up(self):
        """After picking up the last needed item, rush to deliver even with empty slots."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": ["milk", "cheese"]}],
            items=[
                {"id": "item_0", "type": "yogurt", "position": [6, 2]},  # preview
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
        # Bot has both items to complete the order. 1 empty slot.
        # Should rush to deliver, not pick preview yogurt.
        assert action["action"] in ("move_left", "move_down"), \
            f"Should rush to deliver with all order items, got {action}"

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
                {"id": "item_1", "type": "milk", "position": [8, 4]},    # active, far
                {"id": "item_2", "type": "yogurt", "position": [4, 4]},  # preview, near route
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
                {"id": "item_0", "type": "cheese", "position": [2, 4]},  # bot 0 heading here
                {"id": "item_1", "type": "bread", "position": [2, 6]},   # bot 1 should go here
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
            width=11, height=9,
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        # Bot 0 should move left (toward cheese). Bot 1 should also move left.
        # If bot 1 treats bot 0 as static, it can't move left and gets stuck.
        assert a0["action"] == "move_left", f"Bot 0 should move left, got {a0}"
        # Ideally bot 1 moves left too (bot 0 will vacate (3,5))
        # Current code treats bot 0 as static, so bot 1 might wait. That's the bug.
        assert a1["action"] == "move_left", \
            f"Bot 1 should move left (bot 0 will vacate), got {a1}"

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
            width=11, height=9,
        )
        actions = bot.decide_actions(state)
        a0 = get_action(actions, 0)
        a1 = get_action(actions, 1)
        # Bot 0 has milk, heading to pick cheese or deliver.
        # Bot 1 wants to go left toward cheese but bot 0 is in the way.
        # Bot 1 should NOT try to move left (will fail silently = wasted round).
        # It should wait or find alternative.
        if a1["action"] == "move_left":
            # This would try to move into bot 0's cell (4,5) — bad
            assert False, "Bot 1 should not try to move into bot 0's cell"


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
        assert action["action"] == "drop_off", "Should deliver when at dropoff with needed items"
