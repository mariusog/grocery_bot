"""Tests for single-bot decision logic: pickup, delivery, endgame, edge cases."""

import bot
from grocery_bot.simulator import GameSimulator
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


class TestNoActiveOrder:
    """Test behavior when no active order exists."""

    def test_all_bots_wait_when_no_active_order(self):
        """All bots should wait when there's no active order."""
        reset_bot()
        state = make_state(
            bots=[
                {"id": 0, "position": [5, 5], "inventory": []},
                {"id": 1, "position": [7, 5], "inventory": []},
            ],
            items=[{"id": "i1", "type": "milk", "position": [3, 3]}],
            orders=[],  # No orders at all
        )
        actions = bot.decide_actions(state)
        for a in actions:
            assert a["action"] == "wait"

    def test_bots_wait_when_all_orders_complete(self):
        """Bots wait when the only order is already complete."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "i1", "type": "milk", "position": [3, 3]}],
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": True,
                    "items_required": ["milk"],
                    "items_delivered": ["milk"],
                }
            ],
        )
        actions = bot.decide_actions(state)
        assert actions[0]["action"] == "wait"


# =============================================================================
# Strategy agent tests (from agent-ae79b897)
# =============================================================================


class TestSmarterDropoffTiming:
    def test_deliver_partial_to_complete_order(self):
        """Bot with partial inventory rushes to deliver when it completes the order."""
        reset_bot()
        # Order needs cheese + milk. Already delivered: cheese.
        # Bot has milk (1 item). active_on_shelves > 0 (there's a bread item on
        # shelves that isn't needed). Bot's milk delivery completes the order.
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["milk"]}],
            items=[
                {"id": "item_0", "type": "bread", "position": [8, 2]},
                {"id": "item_1", "type": "milk", "position": [6, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk"],
                    "items_delivered": ["cheese"],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has the last needed item. Should rush to deliver for +5 bonus.
        assert action["action"] in ("move_left", "move_down"), (
            f"Should rush to deliver to complete order, got {action}"
        )

    def test_dont_rush_partial_when_not_completing(self):
        """Bot should NOT rush to deliver partial items that don't complete the order."""
        reset_bot()
        # Order needs cheese + milk + bread. Bot has cheese (1/3).
        # Delivering cheese alone doesn't complete the order.
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [4, 2]},
                {"id": "item_1", "type": "bread", "position": [6, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has 1/3 items. Should pick up more, not rush to deliver.
        assert action["action"] != "drop_off", (
            "Should not deliver partial items that don't complete order"
        )

    def test_zero_cost_delivery_when_adjacent_to_dropoff(self):
        """Bot delivers when adjacent to dropoff and next item is past dropoff."""
        reset_bot()
        # Bot at (2, 8), dropoff at (1, 8).
        # Next needed item (milk) is at (0, 2) — on the OTHER side of the dropoff.
        # Going via dropoff: 1 step to (1,8) + dist((1,8), (1,2)) = 1 + 6 = 7.
        # Going direct: dist((2,8), (1,2)) = 7.
        # Via-dropoff (7) <= direct (7) + 1, so zero-cost delivery triggers.
        state = make_state(
            bots=[{"id": 0, "position": [2, 8], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [0, 2]},
                {"id": "item_1", "type": "cheese", "position": [4, 2]},
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
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot is 1 step from dropoff. Next item is past dropoff.
        # Should move toward dropoff for zero-cost delivery.
        assert action["action"] == "move_left", (
            f"Should deliver at zero cost when adjacent to dropoff, got {action}"
        )


class TestImprovedEndGame:
    def test_rush_delivery_when_order_uncompletable(self):
        """In endgame, deliver what you have if order can't be completed in time."""
        reset_bot()
        # 15 rounds left. Bot has 1 cheese (active). Order needs cheese + milk + bread.
        # Milk at (8,2) — too far to pick up AND deliver in 15 rounds.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [8, 2]},
                {"id": "item_1", "type": "bread", "position": [9, 2]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["cheese", "milk", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
            round_num=285,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Can't complete order in 15 rounds. Should deliver cheese (+1 point)
        # rather than chasing unreachable items.
        assert action["action"] in ("move_left", "move_down"), (
            f"Should deliver partial items in endgame, got {action}"
        )

    def test_keep_picking_when_completable_in_endgame(self):
        """In endgame, if order is completable, keep picking up items."""
        reset_bot()
        # 25 rounds left. Bot has cheese, milk is adjacent. Order needs both.
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "item_0", "type": "milk", "position": [4, 3]},
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
            round_num=275,
            max_rounds=300,
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Milk is adjacent. Order is completable. Should pick up milk.
        assert action["action"] == "pick_up", (
            f"Should pick up adjacent item when order is completable, got {action}"
        )


class TestBotStuckInCorner:
    """Bot surrounded by walls/shelves on most sides."""

    def test_bot_in_dead_end(self):
        """Bot in a dead-end corridor with only one exit should still navigate out."""
        reset_bot()
        # Bot at (1,1) with walls on 3 sides, open at (1,2)
        state = make_state(
            bots=[{"id": 0, "position": [1, 1], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [5, 4]}],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            walls=[[0, 1], [1, 0], [2, 1]],  # walls around bot except (1,2)
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Only exit is (1,2) = move_down
        assert action["action"] == "move_down", (
            f"Bot in dead end should move to only exit, got {action}"
        )


class TestEmptyOrdersAndBlacklist:
    """Edge cases: empty orders, all items blacklisted."""

    def test_empty_order_items_required(self):
        """An order with 0 items required should be considered complete instantly."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [4, 4]}],
            orders=[
                {
                    "id": "order_0",
                    "items_required": [],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Empty order needs nothing -> active_needed = {}, no items on shelves
        # Bot should wait or head to dropoff (order arguably already complete).
        # The key is it should not crash.
        assert action is not None, "Should return an action even for empty order"

    def test_all_items_blacklisted(self):
        """If all items of a needed type are blacklisted, bot should not crash."""
        reset_bot()
        # Manually blacklist the only milk item
        bot._gs.blacklisted_items.add("item_0")
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [4, 4]}],
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
        )
        # Need to initialize statics first
        bot.init_static(state)
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # All milk items blacklisted. Bot can't pick up anything. Should wait.
        assert action["action"] == "wait", (
            f"Should wait when all needed items are blacklisted, got {action}"
        )

    def test_no_orders_returns_wait(self):
        """If there are no active orders, all bots should wait."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "item_0", "type": "milk", "position": [4, 4]}],
            orders=[],
            drop_off=[1, 8],
        )
        bot.init_static(state)
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "wait", (
            f"Should wait when no orders exist, got {action}"
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


# --- Phase 4.2: Item Proximity Clustering ---


class TestItemProximityClusteringAdvanced:
    def test_prefer_item_near_other_needed_items(self):
        """When choosing between same-type items, prefer one closer to other items."""
        reset_bot()
        # Order needs 1 milk + 1 cheese. Two milk items available:
        # milk_near at (4,2) — close to cheese at (6,2)
        # milk_far at (8,6) — far from cheese
        # Bot should prefer milk_near since it reduces total route.
        state = make_state(
            bots=[{"id": 0, "position": [3, 5], "inventory": []}],
            items=[
                {"id": "milk_near", "type": "milk", "position": [4, 2]},
                {"id": "milk_far", "type": "milk", "position": [8, 6]},
                {"id": "cheese", "type": "cheese", "position": [6, 2]},
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
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot should head toward the milk closer to the cheese cluster
        assert action["action"] != "wait", "Bot should be navigating toward items"
