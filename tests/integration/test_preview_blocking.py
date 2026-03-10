"""Tests for preview pickup, cascade delivery, and pipelining logic."""

import bot
from tests.conftest import get_action, make_state, reset_bot


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
                    raise AssertionError(
                        f"Bot stuck in loop at round {sim.round}: {last_actions}"
                    )
            sim.apply_actions(actions)

        assert sim.score > 50, f"Score {sim.score} too low — possible stuck loop"
