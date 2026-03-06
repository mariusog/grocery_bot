"""Tests for pathfinding helper functions and distance calculations."""

import bot
from tests.conftest import make_state, reset_bot


class TestHelperFunctions:
    """Tests for individual helper functions in bot.py."""

    def test_direction_to_same_position(self):
        """direction_to returns 'wait' when source equals target."""
        assert bot.direction_to(5, 5, 5, 5) == "wait"

    def test_direction_to_all_directions(self):
        assert bot.direction_to(5, 5, 6, 5) == "move_right"
        assert bot.direction_to(5, 5, 4, 5) == "move_left"
        assert bot.direction_to(5, 5, 5, 6) == "move_down"
        assert bot.direction_to(5, 5, 5, 4) == "move_up"

    def test_get_needed_items_fully_delivered(self):
        """Returns empty dict when all items delivered."""
        order = {"items_required": ["milk", "bread"], "items_delivered": ["milk", "bread"]}
        assert bot.get_needed_items(order) == {}

    def test_get_needed_items_partial(self):
        order = {"items_required": ["milk", "milk", "bread"], "items_delivered": ["milk"]}
        needed = bot.get_needed_items(order)
        assert needed == {"milk": 1, "bread": 1}

    def test_bfs_no_path(self):
        """bfs returns None when no path exists (completely walled off)."""
        # Surround goal with blocked cells
        blocked = {(4, 4), (4, 6), (3, 5), (5, 5), (6, 5)}
        result = bot.bfs((0, 0), (4, 5), blocked)
        assert result is None

    def test_bfs_start_equals_goal(self):
        assert bot.bfs((3, 3), (3, 3), set()) is None

    def test_find_adjacent_positions_uncached(self):
        """find_adjacent_positions works for positions not in _adj_cache."""
        reset_bot()
        bot._gs.adj_cache = {}  # ensure empty cache
        blocked = {(5, 4), (5, 6)}  # block two neighbors
        adj = bot.find_adjacent_positions(5, 5, blocked)
        assert (4, 5) in adj
        assert (6, 5) in adj
        assert (5, 4) not in adj
        assert (5, 6) not in adj

    def test_predict_pos(self):
        assert bot._predict_pos(5, 5, "move_up") == (5, 4)
        assert bot._predict_pos(5, 5, "move_down") == (5, 6)
        assert bot._predict_pos(5, 5, "move_left") == (4, 5)
        assert bot._predict_pos(5, 5, "move_right") == (6, 5)
        assert bot._predict_pos(5, 5, "pick_up") == (5, 5)
        assert bot._predict_pos(5, 5, "wait") == (5, 5)

    def test_tsp_cost_single_item(self):
        """tsp_cost calculates distance through items to drop-off."""
        reset_bot()
        # Set up static state for dist_static to work
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "i1", "type": "milk", "position": [3, 3]}],
            orders=[{
                "id": "o1", "status": "active", "complete": False,
                "items_required": ["milk"], "items_delivered": [],
            }],
        )
        bot.init_static(state)
        cost = bot.tsp_cost((5, 5), [("item", (3, 4))], (1, 8))
        assert cost > 0
        assert cost == bot.dist_static((5, 5), (3, 4)) + bot.dist_static((3, 4), (1, 8))


class TestGetDistancesFrom:
    """Test distance caching behavior."""

    def test_non_static_blocked_skips_cache(self):
        """get_distances_from with non-static blocked set doesn't use cache."""
        reset_bot()
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "i1", "type": "milk", "position": [3, 3]}],
            orders=[],
        )
        bot.init_static(state)
        custom_blocked = set(bot._gs.blocked_static)  # same contents, different object
        dists = bot.get_distances_from((5, 5), custom_blocked)
        assert (5, 5) in dists
        assert dists[(5, 5)] == 0
        # Should NOT have been cached since it's not the same object
        assert (5, 5) not in bot._gs.dist_cache
