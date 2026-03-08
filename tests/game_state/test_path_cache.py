"""Unit tests for PathCacheMixin (game_state/path_cache.py)."""

from tests.game_state.conftest import _make_gs_with_dropoff


class TestGetCachedNextStep:
    def test_returns_none_when_no_cache(self) -> None:
        """No cached path -> returns None."""
        gs = _make_gs_with_dropoff()
        result = gs.get_cached_next_step(0, (3, 3), (5, 5), set(), 0)
        assert result is None

    def test_returns_none_when_at_target(self) -> None:
        """Already at target -> returns None and clears cache."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 5), [(5, 5)], 0)
        result = gs.get_cached_next_step(0, (5, 5), (5, 5), set(), 0)
        assert result is None
        assert 0 not in gs.bot_planned_paths

    def test_invalidates_on_target_change(self) -> None:
        """Cache invalidated when target changes."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 5), [(3, 3), (4, 3), (5, 3)], 0)
        result = gs.get_cached_next_step(0, (3, 3), (7, 7), set(), 0)
        assert result is None
        assert 0 not in gs.bot_planned_paths

    def test_invalidates_when_bot_off_path(self) -> None:
        """Cache invalidated when bot is not at expected path position."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 5), [(3, 3), (4, 3), (5, 3)], 0)
        # Bot is at (1,1) but path expects (3,3)
        result = gs.get_cached_next_step(0, (1, 1), (5, 5), set(), 0)
        assert result is None

    def test_returns_next_step_on_cache_hit(self) -> None:
        """Valid cache -> returns next step along path."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 3), [(3, 3), (4, 3), (5, 3)], 0)
        result = gs.get_cached_next_step(0, (3, 3), (5, 3), set(), 0)
        assert result == (4, 3)

    def test_advances_path_after_step(self) -> None:
        """After returning next step, the cached path is advanced."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 3), [(3, 3), (4, 3), (5, 3)], 0)
        gs.get_cached_next_step(0, (3, 3), (5, 3), set(), 0)
        _, remaining, _ = gs.bot_planned_paths[0]
        assert remaining == [(4, 3), (5, 3)]

    def test_returns_none_when_next_step_blocked(self) -> None:
        """Next step dynamically blocked -> returns None."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 3), [(3, 3), (4, 3), (5, 3)], 0)
        result = gs.get_cached_next_step(0, (3, 3), (5, 3), {(4, 3)}, 0)
        assert result is None

    def test_invalidates_short_path(self) -> None:
        """Path with only one cell (no next step) -> invalidated."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 5), [(3, 3)], 0)
        result = gs.get_cached_next_step(0, (3, 3), (5, 5), set(), 0)
        assert result is None

    def test_recheck_interval_finds_shorter_path(self) -> None:
        """At recheck interval, invalidates if shorter path exists."""
        from grocery_bot.game_state.path_cache import PATH_RECHECK_INTERVAL

        gs = _make_gs_with_dropoff()
        # Create a long cached path of 6 steps
        long_path = [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1)]
        gs.bot_planned_paths[0] = ((7, 1), long_path, 0)
        # After PATH_RECHECK_INTERVAL rounds, check if shorter path available
        round_num = PATH_RECHECK_INTERVAL
        result = gs.get_cached_next_step(0, (1, 1), (7, 1), set(), round_num)
        # dist_static from (1,1) to (7,1) is 6, cached path length-1 is 6
        # so no shorter path -> should still return cached step
        assert result == (2, 1)


class TestStorePathForStep:
    def test_stores_path(self) -> None:
        """Stores a full path from pos to target."""
        gs = _make_gs_with_dropoff()
        gs.store_path_for_step(0, (1, 1), (2, 1), (3, 1), 0)
        assert 0 in gs.bot_planned_paths
        target, path, rnd = gs.bot_planned_paths[0]
        assert target == (3, 1)
        assert path[0] == (1, 1)
        assert path[-1] == (3, 1)

    def test_does_not_store_when_at_target(self) -> None:
        """No path stored when pos == target."""
        gs = _make_gs_with_dropoff()
        gs.store_path_for_step(0, (3, 3), (4, 3), (3, 3), 0)
        assert 0 not in gs.bot_planned_paths

    def test_stores_round_number(self) -> None:
        """Stored path includes the current round number."""
        gs = _make_gs_with_dropoff()
        gs.store_path_for_step(0, (1, 1), (2, 1), (3, 1), 42)
        _, _, rnd = gs.bot_planned_paths[0]
        assert rnd == 42


class TestInvalidatePath:
    def test_removes_cached_path(self) -> None:
        """invalidate_path removes the bot's cached path."""
        gs = _make_gs_with_dropoff()
        gs.bot_planned_paths[0] = ((5, 5), [(3, 3), (4, 3)], 0)
        gs.invalidate_path(0)
        assert 0 not in gs.bot_planned_paths

    def test_no_error_when_not_cached(self) -> None:
        """invalidate_path does not raise if bot has no cached path."""
        gs = _make_gs_with_dropoff()
        gs.invalidate_path(99)  # no-op, should not raise
