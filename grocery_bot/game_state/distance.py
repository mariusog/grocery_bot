"""Distance computation and caching for GameState."""

from typing import Any, Optional

from grocery_bot.constants import DIST_CACHE_MAX
from grocery_bot.pathfinding import bfs_all, find_adjacent_positions


class DistanceMixin:
    """Mixin providing BFS-based distance lookups with caching."""

    def get_distances_from(self, source: tuple[int, int]) -> dict[tuple[int, int], int]:
        if source not in self.dist_cache:
            if len(self.dist_cache) >= DIST_CACHE_MAX:
                keys = list(self.dist_cache)
                for k in keys[: len(keys) // 4]:
                    del self.dist_cache[k]
            self.dist_cache[source] = bfs_all(source, self.blocked_static)
        return self.dist_cache[source]

    def dist_static(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        if a == b:
            return 0
        return self.get_distances_from(a).get(b, float("inf"))

    def find_best_item_target(
        self, pos: tuple[int, int], item: dict[str, Any]
    ) -> tuple[Optional[tuple[int, int]], float]:
        """Find the closest adjacent cell to reach an item shelf."""
        ipos = tuple(item["position"])
        adj_cells = self.adj_cache.get(
            ipos, find_adjacent_positions(ipos[0], ipos[1], self.blocked_static)
        )
        if not adj_cells:
            return None, float("inf")
        best_cell: Optional[tuple[int, int]] = None
        best_d = float("inf")
        for ac in adj_cells:
            d = self.dist_static(pos, ac)
            if d < best_d:
                best_d = d
                best_cell = ac
        return best_cell, best_d
