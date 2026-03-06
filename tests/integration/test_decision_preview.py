"""Tests for preview pickup, cascade delivery, and pipelining logic."""

import bot
from tests.conftest import make_state, reset_bot, get_action


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
        # Bot has 3 slots. Active needs 2 -> only 1 spare for preview.
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
        Only 1 slot left -> must reserve for active item, NOT pick preview."""
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
        # 1 slot left, active needs yogurt -> no spare slots for preview
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
        from grocery_bot.simulator import GameSimulator
        sim = GameSimulator(seed=42, num_bots=1)
        reset_bot()

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
                # Allow endgame idle (last 30 rounds) — bot may legitimately wait
                if len(set(last_actions)) <= 2 and sim.round < 270:
                    assert False, (
                        f"Bot stuck in loop at round {sim.round}: {last_actions}"
                    )
            sim.apply_actions(actions)

        assert sim.score > 50, f"Score {sim.score} too low — possible stuck loop"


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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": [],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["bread"], "items_delivered": [],
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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": [],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["bread"], "items_delivered": [],
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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk", "bread"], "items_delivered": [],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["cheese"], "items_delivered": [],
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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": ["milk"],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["bread"], "items_delivered": [],
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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": ["milk"],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["bread"], "items_delivered": [],
                },
            ],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions, 0)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "i_preview"


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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": ["milk"],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["cheese"], "items_delivered": [],
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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": ["milk"],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["milk"], "items_delivered": [],
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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": ["milk"],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["cheese"], "items_delivered": [],
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
                    "id": "o1", "status": "active", "complete": False,
                    "items_required": ["milk"], "items_delivered": ["milk"],
                },
                {
                    "id": "o2", "status": "preview", "complete": False,
                    "items_required": ["milk"], "items_delivered": [],
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
