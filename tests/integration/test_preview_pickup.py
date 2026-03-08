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

    def test_active_prioritized_over_adjacent_preview(self):
        """Active items take priority: bot moves toward active cheese
        instead of picking up adjacent preview milk."""
        reset_bot()
        # Bot heading toward active cheese at (8,2). Preview milk at (4,5) is adjacent.
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
        # Bot should move toward active item, not pick up preview.
        # The +5 order bonus makes completing active orders faster more valuable.
        assert action["action"] != "pick_up" or action["item_id"] != "item_1", (
            "Bot should prioritize active item over adjacent preview"
        )

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
