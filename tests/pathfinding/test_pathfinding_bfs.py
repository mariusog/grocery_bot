"""Tests for pathfinding helper functions and distance calculations."""

import bot
from tests.conftest import make_state, reset_bot
from tests.pathfinding.conftest import _bounded_blocked

from grocery_bot.pathfinding import (
    bfs,
    bfs_all,
    bfs_full_path,
    bfs_temporal,
    bfs_toward,
    direction_to,
    _predict_pos,
    find_adjacent_positions,
)


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
        order = {
            "items_required": ["milk", "bread"],
            "items_delivered": ["milk", "bread"],
        }
        assert bot.get_needed_items(order) == {}

    def test_get_needed_items_partial(self):
        order = {
            "items_required": ["milk", "milk", "bread"],
            "items_delivered": ["milk"],
        }
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
            orders=[
                {
                    "id": "o1",
                    "status": "active",
                    "complete": False,
                    "items_required": ["milk"],
                    "items_delivered": [],
                }
            ],
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


# -----------------------------------------------------------------------
# Direct tests for grocery_bot.pathfinding functions
# -----------------------------------------------------------------------


def _bounded_blocked(width=11, height=9):
    """Create a border-walled blocked set so bfs_all terminates."""
    blocked = set()
    for x in range(-1, width + 1):
        blocked.add((x, -1))
        blocked.add((x, height))
    for y in range(-1, height + 1):
        blocked.add((-1, y))
        blocked.add((width, y))
    return blocked


class TestBfsAll:
    """Tests for bfs_all — BFS from source to ALL reachable cells."""

    def test_source_has_distance_zero(self):
        dists = bfs_all((3, 3), _bounded_blocked())
        assert dists[(3, 3)] == 0

    def test_adjacent_cells_distance_one(self):
        dists = bfs_all((3, 3), _bounded_blocked())
        assert dists[(4, 3)] == 1
        assert dists[(3, 4)] == 1
        assert dists[(2, 3)] == 1
        assert dists[(3, 2)] == 1

    def test_blocked_cells_excluded(self):
        blocked = _bounded_blocked() | {(4, 3), (2, 3), (3, 4), (3, 2)}
        dists = bfs_all((3, 3), blocked)
        # All 4 direct neighbors are blocked
        assert (4, 3) not in dists
        assert (2, 3) not in dists
        # Source itself is still reachable
        assert dists[(3, 3)] == 0

    def test_bounded_grid_reaches_all_free_cells(self):
        blocked = _bounded_blocked(width=5, height=5)
        dists = bfs_all((2, 2), blocked)
        assert dists[(2, 2)] == 0
        assert dists[(0, 0)] == 4
        assert dists[(4, 4)] == 4

    def test_manhattan_distance_no_obstacles(self):
        blocked = _bounded_blocked()
        dists = bfs_all((0, 0), blocked)
        # On a bounded grid without internal walls, BFS distance == Manhattan distance
        assert dists[(3, 4)] == 7

    def test_fully_surrounded_source(self):
        """Source surrounded on all sides can only reach itself."""
        blocked = _bounded_blocked() | {(2, 3), (4, 3), (3, 2), (3, 4)}
        dists = bfs_all((3, 3), blocked)
        assert len(dists) == 1
        assert dists[(3, 3)] == 0


class TestBfs:
    """Tests for bfs — next step from start toward goal."""

    def test_returns_adjacent_step(self):
        blocked = _bounded_blocked()
        result = bfs((0, 0), (5, 0), blocked)
        assert result is not None
        assert abs(result[0] - 0) + abs(result[1] - 0) == 1

    def test_start_equals_goal_returns_none(self):
        assert bfs((3, 3), (3, 3), _bounded_blocked()) is None

    def test_no_path_returns_none(self):
        # Completely surround goal
        blocked = _bounded_blocked() | {(4, 4), (4, 6), (3, 5), (5, 5)}
        assert bfs((0, 0), (4, 5), blocked) is None

    def test_routes_around_wall(self):
        blocked = _bounded_blocked() | {(1, 0)}
        result = bfs((0, 0), (2, 0), blocked)
        assert result is not None
        assert result != (1, 0)

    def test_adjacent_goal(self):
        result = bfs((3, 3), (4, 3), _bounded_blocked())
        assert result == (4, 3)


class TestBfsFullPath:
    """Tests for bfs_full_path — full shortest path."""

    def test_start_equals_goal(self):
        path = bfs_full_path((3, 3), (3, 3), _bounded_blocked())
        assert path == [(3, 3)]

    def test_adjacent_path(self):
        path = bfs_full_path((3, 3), (4, 3), _bounded_blocked())
        assert path == [(3, 3), (4, 3)]

    def test_longer_path_correct_length(self):
        path = bfs_full_path((0, 0), (3, 0), _bounded_blocked())
        assert len(path) == 4
        assert path[0] == (0, 0)
        assert path[-1] == (3, 0)

    def test_no_path_returns_empty(self):
        blocked = _bounded_blocked() | {(1, 0), (0, 1)}
        path = bfs_full_path((0, 0), (5, 5), blocked)
        assert path == []

    def test_path_avoids_blocked(self):
        blocked = _bounded_blocked() | {(1, 0)}
        path = bfs_full_path((0, 0), (2, 0), blocked)
        assert (1, 0) not in path
        assert path[0] == (0, 0)
        assert path[-1] == (2, 0)

    def test_path_is_contiguous(self):
        """Each step in the path is adjacent to the previous."""
        path = bfs_full_path((0, 0), (4, 3), _bounded_blocked())
        for i in range(1, len(path)):
            dx = abs(path[i][0] - path[i - 1][0])
            dy = abs(path[i][1] - path[i - 1][1])
            assert dx + dy == 1
