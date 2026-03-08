"""Full-path caching and commitment for GameState."""

from typing import Optional

from grocery_bot.constants import PATH_RECHECK_INTERVAL
from grocery_bot.pathfinding import bfs_full_path


class PathCacheMixin:
    """Mixin providing deterministic path caching to avoid flip-flopping."""

    def get_cached_next_step(
        self,
        bot_id: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        dynamic_blocked: set[tuple[int, int]],
        current_round: int,
    ) -> Optional[tuple[int, int]]:
        """Return the next step toward *target* using a cached full path.

        The cache is invalidated when:
        (a) the target changed,
        (b) the bot is not on the expected position,
        (c) the next step is dynamically blocked,
        (d) every PATH_RECHECK_INTERVAL rounds a cheaper path exists.
        """
        if pos == target:
            self.bot_planned_paths.pop(bot_id, None)
            return None

        entry = self.bot_planned_paths.get(bot_id)

        if entry is None:
            return None

        cached_target, cached_path, last_recheck = entry

        if cached_target != target:
            self.bot_planned_paths.pop(bot_id, None)
            return None

        if not cached_path or cached_path[0] != pos:
            self.bot_planned_paths.pop(bot_id, None)
            return None

        if len(cached_path) < 2:
            self.bot_planned_paths.pop(bot_id, None)
            return None

        next_step = cached_path[1]

        if next_step in dynamic_blocked:
            return None

        if current_round - last_recheck >= PATH_RECHECK_INTERVAL:
            new_dist = self.dist_static(pos, target)
            if new_dist < len(cached_path) - 1:
                self.bot_planned_paths.pop(bot_id, None)
                return None
            last_recheck = current_round

        remaining = cached_path[1:]
        self.bot_planned_paths[bot_id] = (target, remaining, last_recheck)
        return next_step

    def store_path_for_step(
        self,
        bot_id: int,
        pos: tuple[int, int],
        next_pos: tuple[int, int],
        target: tuple[int, int],
        current_round: int,
    ) -> None:
        """Build and cache the full path after the caller chose a BFS step."""
        if pos == target:
            return
        path = bfs_full_path(pos, target, self.blocked_static)
        if path and len(path) >= 2:
            self.bot_planned_paths[bot_id] = (target, path, current_round)

    def invalidate_path(self, bot_id: int) -> None:
        """Remove cached path for a bot."""
        self.bot_planned_paths.pop(bot_id, None)
