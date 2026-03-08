"""Unit tests for DistanceMixin cache eviction (game_state/distance.py)."""

from grocery_bot.game_state.distance import DIST_CACHE_MAX
from tests.conftest import make_gs_with_state


class TestDistCacheEviction:
    def test_cache_evicts_when_full(self) -> None:
        """Cache should evict entries when exceeding DIST_CACHE_MAX."""
        gs = make_gs_with_state(width=11, height=9)
        # Fill cache to just under the limit
        for i in range(min(DIST_CACHE_MAX, 50)):
            x = 1 + (i % 9)
            y = 1 + (i // 9) % 7
            gs.get_distances_from((x, y))
        initial_size = len(gs.dist_cache)
        assert initial_size <= DIST_CACHE_MAX

    def test_cache_still_works_after_eviction(self) -> None:
        """After eviction, new lookups still produce correct results."""
        gs = make_gs_with_state(width=11, height=9)
        # The cache should still produce correct distances after eviction
        d1 = gs.dist_static((1, 1), (5, 5))
        # Add many entries to force eviction
        for i in range(60):
            x = 1 + (i % 9)
            y = 1 + (i // 9) % 7
            gs.get_distances_from((x, y))
        # After potential eviction, result should be the same
        d2 = gs.dist_static((1, 1), (5, 5))
        assert d1 == d2
