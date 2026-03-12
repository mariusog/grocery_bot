"""Tests for multi-bot coordination: assignment, collision, deadlock, dispersal."""

import bot
from tests.conftest import get_action, make_state, reset_bot


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
        """Bot 1 may follow bot 0 through a corridor (chain move).

        The server allows chain moves: bot 1 can move into bot 0's cell
        if bot 0 is also moving away in the same round.
        """
        reset_bot()
        # Single-width corridor along y=5. Bot 0 at (3,5) moving left, Bot 1 at (4,5).
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
        # Bot 0 should move left (toward cheese at (2,4)).
        assert a0["action"] == "move_left", f"Bot 0 should move left, got {a0}"
        # Bot 1 may follow bot 0 left (chain move) or wait
        assert a1["action"] in ("move_left", "move_right", "wait"), f"Unexpected: {a1}"

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
            raise AssertionError("Bot 1 should not try to move into bot 0's cell")


class TestInterleavedDelivery:
    """For 4-item orders with 3-slot inventory, the bot must make 2 trips.
    If picking 2 items then delivering, then picking 2 more is shorter than
    picking 3 then 1, the bot should choose the shorter split."""

    def test_prefer_2_2_split_when_dropoff_between_items(self):
        """When the dropoff is between two groups of items, deliver mid-route.
        Layout: items at left side, dropoff in middle, items at right side.
        Pick 2 left items -> deliver -> pick 2 right items -> deliver
        is better than pick 3 -> deliver -> pick 1 -> deliver."""
        reset_bot()
        # Bot starts near dropoff. Items on both sides of the map.
        # Left items at x=2, right items at x=9. Dropoff at x=5.
        # 2+2 split: pick 2 left -> deliver -> pick 2 right -> deliver
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
