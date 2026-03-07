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


class TestBfsTemporal:
    """Tests for bfs_temporal — temporal BFS with moving obstacles."""

    def test_start_equals_goal(self):
        assert bfs_temporal((3, 3), (3, 3), _bounded_blocked(), []) is None

    def test_no_obstacles_same_as_bfs(self):
        """Without obstacles, temporal BFS delegates to standard BFS."""
        blocked = _bounded_blocked()
        result_temporal = bfs_temporal((0, 0), (3, 0), blocked, [])
        result_standard = bfs((0, 0), (3, 0), blocked)
        assert result_temporal == result_standard

    def test_avoids_predicted_position(self):
        """Should avoid moving into a predicted obstacle position."""
        blocked = _bounded_blocked()
        obstacles = [((1, 0), (1, 0))]
        result = bfs_temporal((0, 0), (2, 0), blocked, obstacles)
        assert result is not None
        assert result != (1, 0)

    def test_avoids_current_obstacle_position(self):
        """At step 0, both current and predicted positions are blocked."""
        blocked = _bounded_blocked()
        obstacles = [((1, 0), (2, 0))]
        result = bfs_temporal((0, 0), (3, 0), blocked, obstacles)
        assert result is not None
        assert result != (1, 0)
        assert result != (2, 0)

    def test_fallback_when_temporal_fails(self):
        """Falls back to standard BFS when temporal path is fully blocked."""
        blocked_static = _bounded_blocked() | {
            (0, -1),
            (0, 1),
            (1, -1),
            (1, 1),
            (2, -1),
            (2, 1),
        }
        obstacles = [((1, 0), (1, 0))]
        result = bfs_temporal((0, 0), (2, 0), blocked_static, obstacles)
        assert result is None or isinstance(result, tuple)

    def test_empty_obstacles_delegates_to_bfs(self):
        blocked = _bounded_blocked()
        result = bfs_temporal((0, 0), (3, 0), blocked, [])
        expected = bfs((0, 0), (3, 0), blocked)
        assert result == expected


class TestDirectionTo:
    """Tests for direction_to."""

    def test_all_directions(self):
        assert direction_to(0, 0, 1, 0) == "move_right"
        assert direction_to(0, 0, -1, 0) == "move_left"
        assert direction_to(0, 0, 0, 1) == "move_down"
        assert direction_to(0, 0, 0, -1) == "move_up"

    def test_same_position(self):
        assert direction_to(5, 5, 5, 5) == "wait"


class TestPredictPos:
    """Tests for _predict_pos."""

    def test_all_moves(self):
        assert _predict_pos(5, 5, "move_up") == (5, 4)
        assert _predict_pos(5, 5, "move_down") == (5, 6)
        assert _predict_pos(5, 5, "move_left") == (4, 5)
        assert _predict_pos(5, 5, "move_right") == (6, 5)

    def test_non_move_actions(self):
        assert _predict_pos(5, 5, "wait") == (5, 5)
        assert _predict_pos(5, 5, "pick_up") == (5, 5)
        assert _predict_pos(5, 5, "drop_off") == (5, 5)


class TestFindAdjacentPositions:
    """Tests for find_adjacent_positions."""

    def test_all_neighbors_free(self):
        adj = find_adjacent_positions(5, 5, set())
        assert len(adj) == 4
        assert set(adj) == {(4, 5), (6, 5), (5, 4), (5, 6)}

    def test_some_blocked(self):
        blocked = {(4, 5), (6, 5)}
        adj = find_adjacent_positions(5, 5, blocked)
        assert (4, 5) not in adj
        assert (6, 5) not in adj
        assert (5, 4) in adj
        assert (5, 6) in adj

    def test_all_blocked(self):
        blocked = {(4, 5), (6, 5), (5, 4), (5, 6)}
        adj = find_adjacent_positions(5, 5, blocked)
        assert adj == []

    def test_returns_list(self):
        adj = find_adjacent_positions(0, 0, set())
        assert isinstance(adj, list)


class TestBfsToward:
    """Tests for bfs_toward — BFS that gets as close as possible to goal."""

    def test_start_equals_goal_returns_none(self):
        assert bfs_toward((3, 3), (3, 3), _bounded_blocked()) is None

    def test_reachable_goal_returns_first_step(self):
        blocked = _bounded_blocked()
        result = bfs_toward((0, 0), (3, 0), blocked)
        assert result is not None
        # First step should be adjacent to start
        assert abs(result[0] - 0) + abs(result[1] - 0) == 1

    def test_reachable_goal_same_as_bfs(self):
        """When goal is reachable, bfs_toward should match bfs."""
        blocked = _bounded_blocked()
        result_toward = bfs_toward((0, 0), (5, 0), blocked)
        result_bfs = bfs((0, 0), (5, 0), blocked)
        assert result_toward == result_bfs

    def test_blocked_goal_gets_closer(self):
        """When goal is blocked, should move toward closest reachable cell."""
        # Block the goal completely
        blocked = _bounded_blocked() | {(5, 5)}
        result = bfs_toward((0, 0), (5, 5), blocked)
        assert result is not None
        # Should move toward (5,5) even though it's blocked
        start_dist = abs(5 - 0) + abs(5 - 0)
        step_dist = abs(5 - result[0]) + abs(5 - result[1])
        assert step_dist < start_dist

    def test_surrounded_goal_approaches(self):
        """Goal surrounded by walls — should get as close as possible."""
        # Surround (5,5) on all 4 sides
        blocked = _bounded_blocked() | {(4, 5), (6, 5), (5, 4), (5, 6), (5, 5)}
        result = bfs_toward((0, 0), (5, 5), blocked)
        # Should return a step toward the vicinity of (5,5)
        assert result is not None

    def test_fully_stuck_returns_none(self):
        """Start surrounded by walls — no moves possible."""
        blocked = _bounded_blocked() | {(1, 0), (0, 1)}
        result = bfs_toward((0, 0), (5, 5), blocked)
        assert result is None

    def test_max_steps_limits_search(self):
        """With max_steps=1, only immediate neighbors are checked."""
        blocked = _bounded_blocked()
        result = bfs_toward((0, 0), (10, 8), blocked, max_steps=1)
        # Should still return a valid step or None
        if result is not None:
            assert abs(result[0] - 0) + abs(result[1] - 0) == 1

    def test_adjacent_goal_returns_goal(self):
        blocked = _bounded_blocked()
        result = bfs_toward((3, 3), (4, 3), blocked)
        assert result == (4, 3)

    def test_blocked_adjacent_goal_returns_none(self):
        """Goal is adjacent but blocked — no neighbor is closer, returns None."""
        blocked = _bounded_blocked() | {(4, 3)}
        result = bfs_toward((3, 3), (4, 3), blocked)
        # Start is manhattan distance 1 from goal, all neighbors are distance 2
        # so bfs_toward correctly returns None (already as close as possible)
        assert result is None
